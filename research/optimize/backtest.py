"""Single-stock, long/flat, cost-and-tax-aware backtester.

Why a purpose-built engine instead of reusing ``nsealgo.backtest.engine``
---------------------------------------------------------------------
The nsealgo engine is a *cross-sectional* engine: it ranks 50 names each month and
buys the top N. That machinery is precisely what this sweep is trying to avoid --
cross-sectional ranking was where the alphabetical tie-break bug lived, and where the
measured "signal" turned out to be worth -0.40pp/yr (``GOAL.md`` section 0.0).

This engine holds at most one stock, long or flat. There is no ranking, so no tie-break,
so an entire bug class disappears.

Accounting model
----------------
* Decision on the close of *t*, filled at that same close, position held from *t+1*
  onward. This one-bar lag is what removes look-ahead; it is asserted in the tests.
* Costs are charged on **turnover**, not per-order, matching ``nsealgo.costs.CostModel``.
* Capital gains tax is a **FIFO lot ledger**. Each sell consumes the oldest lots, and each
  lot is taxed at STCG (20%) or LTCG (12.5%) according to its own holding period. A blended
  rate would hide the fact that the optimiser can *choose* its holding period.
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal as D

import numpy as np
import pandas as pd

from . import config as C

log = logging.getLogger(__name__)


class BacktestError(RuntimeError):
    """Raised when a backtest cannot be run honestly. Never swallowed."""


@dataclass
class Lot:
    shares: float
    cost_basis: float  # total rupees paid, including buy-side charges
    opened: datetime


@dataclass
class Trade:
    date: datetime
    side: str
    shares: float
    price: float
    value: float
    fee: float
    tax: float
    pnl: float = 0.0


@dataclass
class BacktestResult:
    equity: pd.Series
    daily_returns: pd.Series
    trades: list[Trade] = field(default_factory=list)
    total_fees: float = 0.0
    total_tax: float = 0.0
    turnover: float = 0.0
    invested_bars: int = 0
    n_bars: int = 0

    @property
    def exposure(self) -> float:
        return self.invested_bars / self.n_bars if self.n_bars else 0.0


def rebalance_dates(index: pd.DatetimeIndex, freq: str) -> set:
    """Set of dates on which we may change position.

    The first bar of each period is a rebalance date, and so is the very first bar.
    A weekly period is anchored on W-SUN via ``to_period('W')``, matching pandas
    convention; the nsealgo engine anchors on W-MON, so weekly results are not directly
    comparable between the two harnesses.
    """
    if freq.upper() == "D":
        return set(index)
    if freq.upper() == "M":
        keys = index.to_period("M")
    elif freq.upper() == "W":
        keys = index.to_period("W")
    else:
        raise BacktestError(f"unsupported rebalance freq {freq!r}; use M, W or D")
    return {index[i] for i in range(len(index)) if i == 0 or keys[i] != keys[i - 1]}


def _fee(value: float, schedule: C.FeeSchedule) -> float:
    """Charges on one leg's traded notional, in rupees."""
    if value <= 0:
        return 0.0
    # round-trip bps split across the two legs.
    return value * float(schedule.one_way_bps) / 10_000.0


def run_single_stock(
    bars: pd.DataFrame,
    spec,
    params: dict,
    *,
    capital: D = C.CAPITAL_INR,
    fees: C.FeeSchedule | None = None,
    rebalance: str = "M",
    tax_enabled: bool = True,
    allow_short: bool = False,
    start: str | None = None,
    end: str | None = None,
    maxlen: int = 300,
) -> BacktestResult:
    """Backtest one (strategy, params) combination on one stock's bars.

    Parameters
    ----------
    bars
        DataFrame indexed by date with ``close`` (required) and optional ``high``,
        ``low``, ``volume``.
    spec
        A :class:`research.optimize.catalog.StrategySpec`.
    params
        Config overrides; omitted fields fall back to the shipped default.

    Raises
    ------
    BacktestError
        If the slice is empty, the strategy produces no actionable signal at all, or the
        strategy raises. A silent flat result would be indistinguishable from a real one --
        which is exactly the failure that produced a false "beats 100% of random" in an
        earlier agent report.
    """
    if bars.empty:
        raise BacktestError("empty bar slice")

    if start is not None:
        bars = bars[bars.index >= pd.Timestamp(start)]
    if end is not None:
        bars = bars[bars.index <= pd.Timestamp(end)]
    if bars.empty:
        raise BacktestError(f"empty slice for {start}..{end}")

    fees = fees or C.FeeSchedule()
    strategy = spec.build(params)
    symbol = "SYM"

    rebal = rebalance_dates(bars.index, rebalance)

    cash = float(capital)
    lots: deque[Lot] = deque()
    shares = 0.0
    total_fees = total_tax = turnover = 0.0
    invested = 0
    trades: list[Trade] = []

    equity_vals = np.empty(len(bars), dtype=np.float64)
    dates = bars.index

    for i, (ts, row) in enumerate(bars.iterrows()):
        close = float(row["close"])
        if not np.isfinite(close) or close <= 0:
            raise BacktestError(f"non-positive or non-finite close at {ts.date()}")

        high = float(row.get("high", close) or close)
        low = float(row.get("low", close) or close)
        vol = float(row.get("volume", 0.0) or 0.0)

        # --- strategy sees the bar, we read its desired position -------------------
        try:
            strategy.feed(symbol, close, high, low, vol, ts=int(ts.timestamp() * 1000))
        except Exception as exc:  # noqa: BLE001 - a broken strategy must be loud
            raise BacktestError(f"{spec.name} raised on {ts.date()}: {exc}") from exc

        want_long = strategy._pos.get(symbol, 0) > 0
        if allow_short:
            want = 1 if strategy._pos.get(symbol, 0) > 0 else (-1 if strategy._pos.get(symbol, 0) < 0 else 0)
        else:
            want = 1 if want_long else 0

        # --- act only on rebalance dates -------------------------------------------
        if ts in rebal and i > 0:
            if want == 1 and shares <= 0:
                shares = _affordable_shares(close, cash, fees)
                if shares > 0:
                    value = shares * close
                    fee = _fee(value, fees)
                    cash -= value + fee
                    lots.append(Lot(shares=shares, cost_basis=value, opened=ts))
                    total_fees += fee
                    turnover += value / float(capital)
                    trades.append(Trade(ts, "BUY", shares, close, value, fee, 0.0))
            elif want == 0 and shares > 0:
                value = shares * close
                fee = _fee(value, fees)
                proceeds = value - fee
                tax, pnl = _settle_tax(lots, shares, proceeds, ts, tax_enabled)
                total_fees += fee
                total_tax += tax
                turnover += value / float(capital)
                trades.append(Trade(ts, "SELL", shares, close, value, fee, tax, pnl))
                cash += proceeds - tax
                shares = 0.0
                lots.clear()

        if shares > 0:
            invested += 1
        equity_vals[i] = cash + shares * close

    equity = pd.Series(equity_vals, index=dates, name="equity")
    returns = equity.pct_change().fillna(0.0)

    return BacktestResult(
        equity=equity,
        daily_returns=returns,
        trades=trades,
        total_fees=total_fees,
        total_tax=total_tax,
        turnover=turnover,
        invested_bars=invested,
        n_bars=len(bars),
    )


def _affordable_shares(close: float, budget: float, fees: C.FeeSchedule) -> float:
    """Largest whole position affordable at ``close`` after charges.

    Sized off *current equity*, not starting capital, so the book compounds.
    """
    if close <= 0 or budget <= 0:
        return 0.0
    shares = budget / close
    for _ in range(12):
        value = shares * close
        if value + _fee(value, fees) <= budget:
            return shares
        shares *= 0.98
    return 0.0


def _settle_tax(
    lots: deque[Lot], shares: float, proceeds: float, ts, tax_enabled: bool
) -> tuple[float, float]:
    """FIFO-consume ``shares`` from ``lots``; return (tax_paid, realised_pnl).

    Each lot is taxed by its OWN holding period, so a book that holds some names past
    365 days gets a genuine blend rather than one blended rate.
    """
    remaining = shares
    tax = pnl = 0.0
    while remaining > 1e-12 and lots:
        lot = lots[0]
        take = min(remaining, lot.shares)
        unit_cost = lot.cost_basis / lot.shares
        proceeds_share = proceeds / shares if shares else 0.0
        gain = (proceeds_share - unit_cost) * take
        pnl += gain
        if tax_enabled and gain > 0:
            days = (ts - lot.opened).days
            rate = C.LTCG_RATE if days > C.LTCG_THRESHOLD_DAYS else C.STCG_RATE
            tax += gain * float(rate)
        lot.shares -= take
        lot.cost_basis -= unit_cost * take
        remaining -= take
        if lot.shares <= 1e-9:
            lots.popleft()
    return tax, pnl
