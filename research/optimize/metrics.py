"""Performance metrics for a single-stock equity curve.

Deliberately *small* set. Every extra statistic is another chance to report a number that
looks decisive and is not, and this project has already been damaged by exactly that
(bootstrap CI on the production-vs-control CAGR gap was [-4.07, +3.38]pp -- a "winner"
that straddled zero).

What is reported:
  CAGR, Sharpe, Sortino, MaxDD, Calmar, volatility, exposure, turnover, fees, tax, trades.

What is NOT reported: anything that requires a significance claim to be useful.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from . import config as C


@dataclass
class Metrics:
    cagr: float
    sharpe: float
    sortino: float
    max_drawdown: float
    calmar: float
    volatility: float
    total_return: float
    exposure: float
    turnover: float
    total_fees: float
    total_tax: float
    n_trades: int
    n_bars: int
    years: float

    def to_dict(self) -> dict:
        return {k: (float(v) if isinstance(v, int | float | np.floating) else v)
                for k, v in asdict(self).items()}


def compute(equity: pd.Series, *, exposure: float = 0.0, turnover: float = 0.0,
            total_fees: float = 0.0, total_tax: float = 0.0, n_trades: int = 0) -> Metrics:
    """Compute metrics from an equity curve.

    ``equity`` must be the *full* realised curve including the flat warmup period, so the
    CAGR denominator is honest about how long the account actually sat idle.
    """
    n = len(equity)
    if n < 2:
        return Metrics(0, 0, 0, 0, 0, 0, 0, exposure, turnover, total_fees, total_tax,
                       n_trades, n, 0.0)

    years = n / C.TRADING_DAYS
    start, end = float(equity.iloc[0]), float(equity.iloc[-1])
    total_return = (end / start - 1.0) if start > 0 else 0.0

    if years <= 0:
        cagr = 0.0
    elif end <= 0:
        cagr = -1.0
    else:
        cagr = (end / start) ** (1.0 / years) - 1.0

    rets = equity.pct_change().fillna(0.0)
    vol = float(rets.std(ddof=1) * np.sqrt(C.TRADING_DAYS)) if n > 2 else 0.0
    sharpe = float(rets.mean() / rets.std(ddof=1) * np.sqrt(C.TRADING_DAYS)) if n > 2 and rets.std(ddof=1) > 0 else 0.0

    downside = rets[rets < 0]
    dstd = float(downside.std(ddof=1) * np.sqrt(C.TRADING_DAYS)) if len(downside) > 2 else 0.0
    sortino = float(rets.mean() * C.TRADING_DAYS / dstd) if dstd > 0 else 0.0

    running_max = equity.cummax()
    # A curve at or below zero has no drawdown *to* measure -- the usual ratio is
    # undefined. Reporting 0.0 while also reporting cagr = -1.0 is self-contradictory
    # (unreachable from run_single_stock, which keeps equity positive, but compute() is
    # public). Use -1.0 for a total loss, which is the honest floor.
    dd = (equity / running_max - 1.0).where(running_max > 0, -1.0)
    maxdd = float(dd.min()) if len(dd) else 0.0
    calmar = float(cagr / abs(maxdd)) if maxdd < -1e-9 else 0.0

    return Metrics(
        cagr=float(cagr), sharpe=sharpe, sortino=sortino, max_drawdown=maxdd, calmar=calmar,
        volatility=vol, total_return=float(total_return), exposure=float(exposure),
        turnover=float(turnover), total_fees=float(total_fees), total_tax=float(total_tax),
        n_trades=int(n_trades), n_bars=int(n), years=float(years),
    )


def per_year(equity: pd.Series) -> dict[str, float]:
    """Calendar-year returns, keyed by year string.

    Two agents found a strategy whose P&L was 35-36% concentrated in 2024, so this is
    reported for every pair rather than only for the winners.
    """
    if equity.empty:
        return {}
    out = {}
    for year, grp in equity.groupby(equity.index.year):
        start = float(grp.iloc[0])
        out[str(year)] = float(grp.iloc[-1] / start - 1.0) if start > 0 else 0.0
    return out


def max_single_year_share(equity: pd.Series) -> float:
    """Largest single year's share of total positive P&L. ``GOAL.md`` Gate 4 caps this at 35%."""
    ys = per_year(equity)
    if not ys:
        return 0.0
    total = sum(v for v in ys.values() if v > 0)
    return float(max(ys.values()) / total) if total > 0 else 0.0
