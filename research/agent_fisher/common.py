"""Shared helpers for the `fisher_transform` NSE validation run.

Everything here is point-in-time: a value on day ``t`` uses only data up to ``t``.
No function in this module looks forward.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from nsealgo.backtest.engine import PortfolioConfig, run_backtest  # noqa: E402
from nsealgo.backtest.metrics import compute_metrics  # noqa: E402
from nsealgo.costs import CostModel  # noqa: E402
from nsealgo.data.loader import load_universe  # noqa: E402

TRAIN = ("2016-01-01", "2023-12-31")
TEST = ("2024-01-01", "2026-10-01")
MOM_LOOKBACK = 126  # fixed construction choice, not a tuned parameter


def cost_model() -> CostModel:
    return CostModel(segment="delivery", slippage_bps=5)


def load() -> tuple[pd.DataFrame, list[str]]:
    panel, symbols, _report = load_universe(str(REPO / "data" / "nse"))
    return panel, symbols


def fisher_panel(panel: pd.DataFrame, period: int) -> pd.DataFrame:
    """Vectorised equivalent of ``cryptobot.strategies.indicators.fisher_transform``.

    Mirrors the scalar implementation exactly, including the ``hi == lo -> 0.0``
    short-circuit and the NaN warm-up (the scalar returns NaN when
    ``len(closes) < period``).
    """
    hi = panel.rolling(period, min_periods=period).max()
    lo = panel.rolling(period, min_periods=period).min()
    rng = (hi - lo).replace(0.0, np.nan)
    norm = 2.0 * ((panel - lo) / rng - 0.5)
    norm = norm.clip(-0.999, 0.999)
    f = np.arctanh(norm)
    # `hi == lo` over a *full* window -> 0.0, exactly as the scalar does. Before the
    # window fills the scalar returns NaN, so NaN must be preserved there.
    return f.mask(hi.notna() & rng.isna(), 0.0)


def fisher_signal(fisher: pd.DataFrame, entry: float) -> pd.DataFrame:
    """+1 where the Fisher value is at or below -entry, -1 at/above +entry, else 0."""
    sig = pd.DataFrame(0.0, index=fisher.index, columns=fisher.columns)
    sig = sig.mask(fisher >= entry, -1.0)
    sig = sig.mask(fisher <= -entry, 1.0)
    return sig


def momentum(panel: pd.DataFrame, days: int = MOM_LOOKBACK) -> pd.DataFrame:
    return panel / panel.shift(days) - 1.0


def fisher_score(
    panel: pd.DataFrame, period: int, entry: float
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Construction under test: Fisher gate + cross-sectional momentum rank.

    Returns ``(score, signal)``. Names are long only if the Fisher signal is +1,
    and among those the highest 126d trailing momentum wins.
    """
    sig = fisher_signal(fisher_panel(panel, period), entry)
    score = momentum(panel).where(sig > 0).rank(axis=1, pct=True)
    return score, sig


def random_signal_score(
    panel: pd.DataFrame, sig: pd.DataFrame, seed: int = 20261001
) -> pd.DataFrame:
    """Negative control: random gate with the *same* per-bar long fraction."""
    rng = np.random.default_rng(seed)
    frac = (sig > 0).mean(axis=1)
    out = pd.DataFrame(np.nan, index=panel.index, columns=panel.columns)
    mom = momentum(panel).to_numpy(dtype=float)
    frac_v = frac.to_numpy(dtype=float)
    n = len(panel.columns)
    for i in range(len(panel.index)):
        k = int(round(frac_v[i] * n))
        if k <= 0:
            continue
        cols = rng.choice(n, size=k, replace=False)
        out.iloc[i, cols] = mom[i, cols]
    return out.rank(axis=1, pct=True)


def slice_metrics(
    equity: pd.Series, returns: pd.Series, start: str, end: str, **kw
):
    """Metrics over a window, with equity properly rebased to 1.0 at window start."""
    idx = equity.index
    lo = int(idx.searchsorted(pd.Timestamp(start, tz=idx.tz)))
    hi = int(idx.searchsorted(pd.Timestamp(end, tz=idx.tz))) + 1
    hi = min(hi, len(idx))
    sub_eq = equity.iloc[lo:hi]
    sub_rt = returns.iloc[lo:hi]
    prev = float(equity.iloc[lo - 1]) if lo > 0 else float(sub_eq.iloc[0]) / (
        1.0 + float(sub_rt.iloc[0])
    )
    rebased = sub_eq / prev
    win = rebased.pct_change()
    win.iloc[0] = rebased.iloc[0] - 1.0
    return compute_metrics(win, rebased, **kw)


def window_diag(result, start: str, end: str, gross_result=None) -> dict:
    """Window turnover / cost drag / material-position count for a backtest.

    ``cost_drag_annual`` is the *difference* between a zero-cost rerun and the real
    run over the same window, both annualised — an auditable gross-vs-net split
    rather than a bookkept estimate.
    """
    idx = result.equity.index
    lo = int(idx.searchsorted(pd.Timestamp(start, tz=idx.tz)))
    hi = min(int(idx.searchsorted(pd.Timestamp(end, tz=idx.tz))) + 1, len(idx))
    years = max((hi - lo) / 244.0, 1e-9)

    w = result.weights
    chg = w.diff().abs().sum(axis=1)
    changed = chg.index[chg > 1e-9]
    turn = (w.loc[changed] - w.shift(1).loc[changed]).abs().sum(axis=1) / 2.0
    turn = turn.loc[(turn.index >= idx[lo]) & (turn.index <= idx[hi - 1])]

    sub = w.iloc[lo:hi]
    drag = 0.0
    if gross_result is not None:
        g = float(
            (gross_result.equity.iloc[hi - 1] / gross_result.equity.iloc[lo - 1])
            ** (1.0 / years)
        )
        n = float(
            (result.equity.iloc[hi - 1] / result.equity.iloc[lo - 1])
            ** (1.0 / years)
        )
        drag = g - n
    return {
        "annual_turnover": float(turn.sum() / years),
        "cost_drag_annual": drag,
        "trades_per_year": float(len(turn) / years),
        "avg_names": float((sub > 0).sum(axis=1).mean()),
        "avg_material_names": float((sub > 1e-4).sum(axis=1).mean()),
        "avg_book_weight": float(sub.sum(axis=1).mean()),
    }


class ZeroCostModel(CostModel):
    """Identical interface, zero drag — for the gross-vs-net cost split."""

    def all_in_round_trip_bps(self, notional):  # noqa: D102, ANN001, ANN201
        return 0.0


def bt(
    panel: pd.DataFrame,
    score: pd.DataFrame,
    config=None,
    rebalance: str = "M",
    zero_cost: bool = False,
):
    cm = ZeroCostModel(segment="delivery", slippage_bps=0) if zero_cost else cost_model()
    return run_backtest(panel, score, cm, config or PortfolioConfig(), rebalance=rebalance)


def bh_returns(
    panel: pd.DataFrame, rebalance: str | None, rate: float
) -> tuple[pd.Series, pd.Series, float]:
    """Equal-weight buy-and-hold over **all** names, with exact turnover accounting.

    Turnover is the real one-way turnover of an equal-weight book held to equal
    weights, computed from weight drift:

        turn = 0.5 * sum_i | w_target_i - w_drifted_i |

    NOT ``100%`` per rebalance. Assuming 100% would charge ~53%/y on a daily
    rebalance and turn the benchmark into a cost pump rather than a benchmark.

    ``rebalance=None`` -> buy once and hold (single entry cost).
    ``'M'`` / ``'D'`` -> rebalanced on the first trading day of each month / daily.

    Costs use the same ``rt_bps + 2 x slippage`` rate as ``run_backtest`` and are
    charged against the *compounding* equity, exactly as the engine does.
    """
    idx = panel.index
    R = panel.pct_change(fill_method=None).fillna(0.0).to_numpy()
    n, n_sym = R.shape
    target = np.full(n_sym, 1.0 / n_sym)

    do = np.zeros(n, dtype=bool)
    if rebalance == "D":
        do[1:] = True
    elif rebalance == "M":
        keys = idx.tz_localize(None).to_period("M")
        firsts = set(pd.Series(idx, index=idx).groupby(keys).apply(lambda g: g.index[0]))
        do[1:] = [d in firsts for d in idx[1:]]
    elif rebalance is None:
        do[1:] = False  # entry cost charged once, on day 0, below
    else:
        raise ValueError("rebalance must be None, 'M' or 'D'")

    eq = 1.0 - rate  # entry cost on day 0: buy the book and pay one round trip
    w = target.copy()
    daily = np.zeros(n)
    turns = np.zeros(n)
    for t in range(n):
        prev = eq
        eq *= 1.0 + float(w @ R[t])
        drifted = w * (1.0 + R[t])
        s = drifted.sum()
        drifted = drifted / s if s > 0 else target
        if do[t]:
            turn = 0.5 * np.abs(target - drifted).sum()
            eq *= 1.0 - turn * rate
            turns[t] = turn
            drifted = target
        w = drifted
        daily[t] = eq / prev - 1.0
    return (
        pd.Series(daily, index=idx),
        pd.Series(np.cumprod(1.0 + daily), index=idx),
        float(turns.sum() + rate),
    )


def fmt(m, tag: str) -> str:
    return (
        f"{tag:<22} CAGR {m.cagr*100:>7.2f}%  Sharpe {m.sharpe:>5.2f}  "
        f"MaxDD {m.max_drawdown*100:>7.2f}%  Calmar {m.calmar:>5.2f}  "
        f"Turn {m.annual_turnover:>5.2f}x/y  CostDrag {m.cost_drag_annual*100:>5.2f}%/y  "
        f"Total {m.total_return*100:>8.2f}%"
    )
