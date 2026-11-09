"""Shared harness for the Williams %R NSE study.

Everything point-in-time: %R on day t uses closes/highs/lows from t-period+1 .. t only.
`run_backtest` holds weights decided at the close of t from t+1 onward, so there is no lookahead.
"""

from __future__ import annotations

import sys
from decimal import Decimal

import numpy as np
import pandas as pd

sys.path.insert(0, "src")

from nsealgo.backtest.engine import PortfolioConfig, run_backtest  # noqa: E402
from nsealgo.backtest.metrics import compute_metrics, yearly_returns  # noqa: E402
from nsealgo.costs import CostModel  # noqa: E402

DATA = "data/nse"
TRAIN = (pd.Timestamp("2016-01-01"), pd.Timestamp("2023-12-31"))
TEST = (pd.Timestamp("2024-01-01"), pd.Timestamp("2026-10-01"))

#: run_backtest charges all_in_round_trip_bps(100_000) = 11.92 + 2*5 = 21.92 bps.
BASE_COST = CostModel(segment="delivery", slippage_bps=5.0)
#: Zero-cost control: statutory only, 11.92 bps.
ZERO_COST = CostModel(segment="delivery", slippage_bps=0.0)


def load_panel():
    from nsealgo.data.loader import load_universe

    panel, symbols, report = load_universe(DATA)
    return panel, symbols, report


def williams_r(high, low, close, period: int) -> pd.DataFrame:
    """Williams %R, vectorised. (HH - C) / (HH - LL) * -100, trailing `period` bars.

    Rolling max/min include day t itself -- that is the strategy as written, and the
    engine's one-bar execution lag is what keeps it honest.
    """
    hh = high.rolling(period, min_periods=period).max()
    ll = low.rolling(period, min_periods=period).min()
    span = (hh - ll).replace(0.0, np.nan)
    return -100.0 * (hh - close) / span


def signal_panel(panel: pd.DataFrame, highs: pd.DataFrame, lows: pd.DataFrame,
                 period: int, lower: float, persistence: int | None) -> pd.DataFrame:
    """1.0 where the %R entry condition is met, else 0.0.

    persistence=None -> state only (`w <= lower` today).
    persistence=L     -> `w <= lower` at any point in the last L sessions (lagged entry).
    """
    w = williams_r(highs, lows, panel, period)
    state = (w <= lower).astype(float)
    if persistence is None:
        return state
    return state.rolling(persistence, min_periods=1).max()


def wr_score(panel: pd.DataFrame, sig: pd.DataFrame) -> pd.DataFrame:
    """Cross-sectional momentum rank among signalled names only (brief §5).

    Names that are not signalled stay NaN, which `build_rebalance_weights` treats as
    invalid and drops -- so the book holds only signalled names.
    """
    mom = panel / panel.shift(126) - 1.0
    return mom.where(sig > 0).rank(axis=1, pct=True)


def bh_score(panel: pd.DataFrame) -> pd.DataFrame:
    """Equal-weight buy-and-hold control: every name equally attractive, same constraints."""
    return pd.DataFrame(1.0, index=panel.index, columns=panel.columns)


def random_score(panel: pd.DataFrame, sig: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Negative control: same names flagged at each date, shuffled across the universe.

    Preserves the per-date breadth and therefore the turnover/holding structure exactly,
    so any difference in the result is attributable to *which* names were picked, not to
    how often the book was invested.

    BUG FOUND AND FIXED HERE (agent_williamsr): the first version assigned every flagged
    name a constant score of 1.0. ``build_rebalance_weights`` breaks score ties with a
    *stable* sort on ``-score``, so on every date it kept the 22 flagged names with the
    lowest column index -- i.e. an alphabetical subset, not a random one. The control was
    quietly biased toward the first symbols in the panel. Scores here are now drawn
    uniformly at random so the top-k cut is genuinely random.
    """
    rng = np.random.default_rng(seed)
    a = sig.to_numpy()
    out = np.full(a.shape, np.nan)
    for i in range(a.shape[0]):
        idx = np.flatnonzero(a[i] > 0)
        if idx.size == 0:
            continue
        pick = rng.choice(a.shape[1], size=idx.size, replace=False)
        out[i, pick] = rng.random(idx.size)
    return pd.DataFrame(out, index=sig.index, columns=sig.columns)


def run(score: pd.DataFrame, panel: pd.DataFrame, cost: CostModel = BASE_COST,
        config: PortfolioConfig | None = None, rebalance: str = "M"):
    return run_backtest(panel, score, cost, config or PortfolioConfig(), rebalance=rebalance)


def windowed(panel: pd.DataFrame, score: pd.DataFrame, win: tuple) -> pd.DataFrame:
    """Restrict both panel and score to a date window (indices are tz-aware)."""
    lo, hi = win
    idx = panel.index.intersection(score.index)
    idx = idx[(idx.tz_localize(None) >= lo) & (idx.tz_localize(None) <= hi)]
    return panel.loc[idx], score.loc[idx]


ALL_IN_BPS = 21.92
ZERO_BPS = 11.92


def slice_metrics(res, win, panel, cost_bps_rate: float = ALL_IN_BPS):
    """Metrics for `win` only, from a full-history `run_backtest` run.

    Running on the full panel then slicing gives every variant identical warmup (126d
    momentum, 60d vol) and identical look-ahead discipline: weights on a date depend
    only on the score at that date, so a TRAIN slice cannot see anything after it.
    Turnover is recovered from the ffill'd weight path (its diff is zero between
    rebalances, so summing the diff equals summing |dW| at the rebalance dates), and
    cost drag is recomputed on the compounding slice equity as the engine does.
    """

    lo, hi = win
    idx = panel.index.intersection(res.returns.index)
    idx = idx[(idx.tz_localize(None) >= lo) & (idx.tz_localize(None) <= hi)]
    r = res.returns.loc[idx]
    eq = (1.0 + r).cumprod()
    years = len(r) / 244.0
    turn = (res.weights.diff().abs().sum(axis=1) / 2.0).loc[idx]
    rate = cost_bps_rate / 10_000.0
    costs = float((2.0 * turn * eq * rate).sum())
    m = compute_metrics(r, eq, annual_turnover=float(turn.sum()) / years,
                        cost_drag_annual=costs / years,
                        trades_per_year=float((turn > 0).sum()) / years)
    out = {
        "CAGR%": m.cagr * 100, "Sharpe": m.sharpe, "MaxDD%": m.max_drawdown * 100,
        "Calmar": m.calmar, "Vol%": m.volatility * 100,
        "Turnover/y": m.annual_turnover, "CostDrag%/y": m.cost_drag_annual * 100,
        "AvgNames": float((res.weights.loc[idx] > 0).sum(axis=1).mean()),
        "TotalRet%": m.total_return * 100,
        "RupeesOn21L": float(eq.iloc[-1]) * 2_100_000.0 - 2_100_000.0,
    }
    return out, r, eq


def load_hl(symbols, panel):
    """High/low panels aligned to the cleaned close panel index."""
    from nsealgo.data.loader import load_symbol

    H = pd.DataFrame({s: load_symbol(f"{DATA}/{s}_1d.csv", s)["high"]
                      for s in symbols}).reindex(panel.index)[symbols]
    L = pd.DataFrame({s: load_symbol(f"{DATA}/{s}_1d.csv", s)["low"]
                      for s in symbols}).reindex(panel.index)[symbols]
    return H, L


def summarise(res) -> dict:
    m = res.metrics
    return {
        "CAGR%": m.cagr * 100,
        "Sharpe": m.sharpe,
        "MaxDD%": m.max_drawdown * 100,
        "Calmar": m.calmar,
        "Vol%": m.volatility * 100,
        "Turnover/y": m.annual_turnover,
        "CostDrag%/y": m.cost_drag_annual * 100,
        "AvgNames": res.diag["avg_names"],
        "TotalRet%": m.total_return * 100,
        "rt_bps": res.diag["round_trip_bps"],
        "RupeesOn21L": res.equity.iloc[-1] * 2_100_000.0 - 2_100_000.0,
    }


HDR = (f"{'name':<26}{'CAGR%':>8}{'Sharpe':>8}{'MaxDD%':>8}{'Calmar':>7}"
       f"{'Turn/y':>8}{'Drag%/y':>8}{'Names':>7}{'Rs on 21L':>12}")


def row(name: str, s: dict) -> str:
    return (f"{name:<26}{s['CAGR%']:>8.2f}{s['Sharpe']:>8.2f}{s['MaxDD%']:>8.2f}"
            f"{s['Calmar']:>7.2f}{s['Turnover/y']:>8.2f}{s['CostDrag%/y']:>8.2f}"
            f"{s['AvgNames']:>7.1f}{s['RupeesOn21L']:>12,.0f}")


def year_ret(r: pd.Series) -> str:
    return "  ".join(f"{int(y)}:{v * 100:+6.1f}%" for y, v in yearly_returns(r).items())


def cost_bps() -> dict:
    n = Decimal("100000")
    return {
        "round_trip_bps": float(BASE_COST.round_trip_bps(n)),
        "all_in_bps": float(BASE_COST.all_in_round_trip_bps(n)),
        "zero_cost_all_in_bps": float(ZERO_COST.all_in_round_trip_bps(n)),
    }
