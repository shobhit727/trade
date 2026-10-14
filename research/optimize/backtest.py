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


#: Cache of rebalance-date masks, keyed by (length, first, last, freq).
#:
#: Profiling a 1,975-bar backtest showed ``rebalance_dates`` consuming **38%** of runtime --
#: more than the strategy itself. It is pure, deterministic pandas indexing, and it was
#: being recomputed on every one of ~161,000 backtests for the same ~48 distinct index
#: slices. This turns the largest single cost into a dict lookup.
_REBAL_CACHE: dict[tuple, frozenset] = {}


def rebalance_dates(index: pd.DatetimeIndex, freq: str) -> frozenset:
    """Set of dates on which we may change position.

    The first bar of each period is a rebalance date, and so is the very first bar.
    A weekly period is anchored on W-SUN via ``to_period('W')``, matching pandas
    convention; the nsealgo engine anchors on W-MON, so weekly results are not directly
    comparable between the two harnesses.
    """
    key = (len(index), index[0], index[-1], freq)
    hit = _REBAL_CACHE.get(key)
    if hit is not None:
        return hit

    if freq.upper() == "D":
        out = frozenset(index)
    elif freq.upper() == "M":
        keys = index.to_period("M")
        out = frozenset(index[i] for i in range(len(index)) if i == 0 or keys[i] != keys[i - 1])
    elif freq.upper() == "W":
        keys = index.to_period("W")
        out = frozenset(index[i] for i in range(len(index)) if i == 0 or keys[i] != keys[i - 1])
    else:
        raise BacktestError(f"unsupported rebalance freq {freq!r}; use M, W or D")

    _REBAL_CACHE[key] = out
    return out


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

    # Lazily install the indicator fast path here, not in run.py: by the time any
    # backtest runs, discover() has imported all 84 catalog modules, so the rebind can
    # actually reach them. See fastpath.ensure().
    from . import fastpath

    fastpath.ensure()

    fees = fees or C.FeeSchedule()
    strategy = spec.build(params)
    symbol = "SYM"

    rebal = rebalance_dates(bars.index, rebalance)

    # Pull the OHLCV columns into numpy once. ``iterrows()`` was the second-largest cost
    # in the profile (24%): it materialises a pandas Series per bar, which then costs a
    # dict lookup per field. This loop runs ~161,000 times, so that overhead is paid
    # ~320 million times.
    dates = bars.index
    n_bars = len(bars)
    close_a = bars["close"].to_numpy(dtype=np.float64, copy=False)
    high_a = (bars["high"].to_numpy(dtype=np.float64, copy=False)
              if "high" in bars.columns else close_a)
    low_a = (bars["low"].to_numpy(dtype=np.float64, copy=False)
             if "low" in bars.columns else close_a)
    vol_a = (bars["volume"].to_numpy(dtype=np.float64, copy=False)
             if "volume" in bars.columns else np.zeros(n_bars))
    # Epoch milliseconds without a per-bar Timestamp.timestamp() call.
    ts_ms = dates.asi8 // 1_000_000
    rebal_flags = np.fromiter((d in rebal for d in dates), dtype=bool, count=n_bars)
    # DatetimeIndex.__getitem__ was 49% of the remaining time after the numpy
    # conversion. It is only needed to stamp a Trade or to raise, so it is looked up
    # lazily instead of once per bar.
    _ts_at = dates.__getitem__

    cash = float(capital)
    lots: deque[Lot] = deque()
    shares = 0.0
    total_fees = total_tax = turnover = 0.0
    invested = 0
    trades: list[Trade] = []

    equity_vals = np.empty(n_bars, dtype=np.float64)

    for i in range(n_bars):
        close = close_a[i]
        if not np.isfinite(close) or close <= 0:
            raise BacktestError(
                f"non-positive or non-finite close at {_ts_at(i).date()}")

        # --- strategy sees the bar, we read its desired position -------------------
        try:
            strategy.feed(symbol, close, high_a[i], low_a[i], vol_a[i], ts=int(ts_ms[i]))
        except Exception as exc:  # noqa: BLE001 - a broken strategy must be loud
            raise BacktestError(
                f"{spec.name} raised on {_ts_at(i).date()}: {exc}") from exc

        pos = strategy._pos.get(symbol, 0)
        if allow_short:
            want = 1 if pos > 0 else (-1 if pos < 0 else 0)
        else:
            want = 1 if pos > 0 else 0

        # --- act only on rebalance dates -------------------------------------------
        if rebal_flags[i] and i > 0:
            ts = _ts_at(i)
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
