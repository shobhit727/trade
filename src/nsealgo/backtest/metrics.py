"""Performance metrics with correct annualisation.

The parent repo's 2026-08-22 audit logged Sharpe/drawdown bugs as issues #20/#32/#39/#40.
This module exists to make those mistakes impossible:

* Returns are **daily**, and we annualise with ``sqrt(244)``. The parent code used
  ``sqrt(252)`` (a US assumption) in places and ``252`` scaling in others.
* Volatility is the **sample** stdev (``ddof=1``), not population.
* Drawdown is computed on the **equity curve**, not on the return series.
* Sharpe is annualised *from the mean/std of daily returns*, then multiplied — never
  by annualising the raw Sharpe a second time.
* Risk-free rate is subtracted **daily then annualised**, and defaults to the
  Indian T-bill proxy (~6.5%), not 0.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

TRADING_DAYS = 244
#: Indian 6-month T-bill proxy. Sharpe must be risk-adjusted; assuming 0% inflates it.
DEFAULT_RF_ANNUAL = 0.065


@dataclass(frozen=True)
class Metrics:
    """Full performance summary of a daily-return series."""

    n_periods: int
    total_return: float
    cagr: float
    volatility: float
    sharpe: float
    sortino: float
    calmar: float
    max_drawdown: float
    max_drawdown_days: int
    win_rate: float
    best_day: float
    worst_day: float
    skew: float
    kurtosis: float
    # turnover / cost diagnostics
    annual_turnover: float = 0.0
    cost_drag_annual: float = 0.0
    trades_per_year: float = 0.0

    def as_dict(self) -> dict[str, float | int]:
        return asdict(self)

    def fmt(self) -> str:
        return (
            f"CAGR {self.cagr * 100:>7.2f}%   Vol {self.volatility * 100:>6.2f}%\n"
            f"Sharpe {self.sharpe:>7.2f}    Sortino {self.sortino:>6.2f}\n"
            f"Calmar {self.calmar:>7.2f}    MaxDD {self.max_drawdown * 100:>6.2f}% "
            f"({self.max_drawdown_days}d)\n"
            f"WinRate {self.win_rate * 100:>6.1f}%  Best {self.best_day * 100:>6.2f}%  "
            f"Worst {self.worst_day * 100:>7.2f}%\n"
            f"Turnover {self.annual_turnover:>5.2f}x/y  "
            f"CostDrag {self.cost_drag_annual * 100:>5.2f}%/y  "
            f"Trades {self.trades_per_year:>5.1f}/y"
        )


def drawdown_series(equity: pd.Series) -> pd.Series:
    """Drawdown as a fraction (0 at peak, negative in a drawdown)."""
    peak = equity.cummax()
    return equity / peak - 1.0


def max_drawdown(equity: pd.Series) -> tuple[float, int]:
    """(max drawdown as negative fraction, number of trading days underwater)."""
    dd = drawdown_series(equity)
    if dd.empty:
        return 0.0, 0
    trough = dd.idxmin()
    peak_idx = equity.loc[:trough].idxmax()
    # days from the peak to the trough
    span = len(equity.loc[peak_idx:trough])
    return float(dd.min()), int(span)


def compute_metrics(
    returns: pd.Series,
    equity: pd.Series | None = None,
    rf_annual: float = DEFAULT_RF_ANNUAL,
    annual_turnover: float = 0.0,
    cost_drag_annual: float = 0.0,
    trades_per_year: float = 0.0,
) -> Metrics:
    """Compute the full metric suite from a **daily** return series.

    Parameters
    ----------
    returns
        Daily simple returns, NaN-dropped.
    equity
        Optional pre-computed equity curve (starts at 1.0). Derived from
        ``returns`` if omitted.
    """
    r = returns.dropna()
    if len(r) < 2:
        return Metrics(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)

    if equity is None:
        equity = (1.0 + r).cumprod()
    equity = equity.reindex(r.index)

    n = len(r)
    years = n / TRADING_DAYS

    total = float(equity.iloc[-1] - 1.0)
    cagr = float(equity.iloc[-1] ** (1.0 / years) - 1.0) if years > 0 else 0.0

    # Daily risk-free, then annualise.
    rf_daily = (1.0 + rf_annual) ** (1.0 / TRADING_DAYS) - 1.0
    excess = r - rf_daily

    vol = float(r.std(ddof=1))  # sample stdev
    excess_vol = float(excess.std(ddof=1))
    ann_vol = vol * np.sqrt(TRADING_DAYS)

    sharpe = (
        float(excess.mean() / excess_vol * np.sqrt(TRADING_DAYS))
        if excess_vol > 0
        else 0.0
    )

    downside = excess[excess < 0]
    dvol = float(downside.std(ddof=1)) if len(downside) > 1 else 0.0
    sortino = (
        float(excess.mean() / dvol * np.sqrt(TRADING_DAYS)) if dvol > 0 else 0.0
    )

    mdd, mdd_days = max_drawdown(equity)
    calmar = float(cagr / abs(mdd)) if mdd < 0 else 0.0

    return Metrics(
        n_periods=n,
        total_return=total,
        cagr=cagr,
        volatility=float(ann_vol),
        sharpe=sharpe,
        sortino=sortino,
        calmar=calmar,
        max_drawdown=mdd,
        max_drawdown_days=mdd_days,
        win_rate=float((r > 0).mean()),
        best_day=float(r.max()),
        worst_day=float(r.min()),
        skew=float(r.skew()),
        kurtosis=float(r.kurtosis()),
        annual_turnover=annual_turnover,
        cost_drag_annual=cost_drag_annual,
        trades_per_year=trades_per_year,
    )


def yearly_returns(returns: pd.Series) -> pd.Series:
    """Calendar-year returns, for the `GOAL.md` §5 Gate 3 'positive in 60% of
    years' requirement.

    Each year is the growth **within** that year, i.e. the year's return measured from
    the previous year-end equity, not the cumulative equity at year end.
    """
    if returns.empty:
        return pd.Series(dtype=float)
    r = returns.fillna(0.0)
    eq = (1.0 + r).cumprod()
    # Equity at each year boundary; the ratio of consecutive boundaries is the
    # calendar-year return.
    year_end = eq.groupby(r.index.year).last()
    out = year_end.pct_change()
    out.iloc[0] = year_end.iloc[0] - 1.0  # first year vs a starting equity of 1.0
    return out.rename("ret")


def pnl_concentration(
    trades_pnl: pd.Series, top_n: int = 1
) -> tuple[float, float]:
    """Share of total P&L from the best ``top_n`` trades.

    Gate 4 requires no single *year* or *stock* to dominate. A high concentration
    means the result is a handful of lucky bets, not an edge.
    """
    if trades_pnl.empty:
        return 0.0, 0.0
    total = float(trades_pnl.sum())
    if total == 0:
        return 0.0, 0.0
    top = float(trades_pnl.nlargest(top_n).sum())
    return top / total, total
