"""Shared harness for the `momentum_factor_strategy` NSE evaluation.

The declared parameter budget lives here in ``VARIANTS`` and was written BEFORE any
backtest was run (see ``REPORT.md`` §2). Do not add a sixth entry.

Nothing in this file imports the catalog class for *generating* signals — it uses a
vectorised equivalent that ``10_verify_signal.py`` proves bar-for-bar identical to the
real ``MomentumFactorStrategy.signal``. Verification is a separate, mandatory step.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

import numpy as np
import pandas as pd

sys.path.insert(0, "src")

from nsealgo.backtest.engine import PortfolioConfig, run_backtest  # noqa: E402
from nsealgo.backtest.metrics import compute_metrics, yearly_returns  # noqa: E402
from nsealgo.costs import CostModel  # noqa: E402
from nsealgo.data.loader import load_universe  # noqa: E402

DATA_DIR = "data/nse"
OUT_DIR = os.path.dirname(os.path.abspath(__file__))

TRAIN_START = pd.Timestamp("2016-01-01", tz="Asia/Kolkata")
TRAIN_END = pd.Timestamp("2023-12-31", tz="Asia/Kolkata")
TEST_START = pd.Timestamp("2024-01-01", tz="Asia/Kolkata")
TEST_END = pd.Timestamp("2026-10-01", tz="Asia/Kolkata")

#: The engine charges this; every reported backtest number is net of it.
COST = CostModel(segment="delivery", slippage_bps=5)
CFG = PortfolioConfig()


@dataclass(frozen=True)
class Variant:
    """One parameterisation of the assigned strategy."""

    tag: str
    period: int
    threshold: float
    rank_days: int
    rebalance: str = "M"


#: DECLARED BUDGET — exactly 5. See REPORT.md §2. Do not extend.
VARIANTS: list[Variant] = [
    Variant("M1", 20, 0.005, 20, "M"),    # catalog defaults, verbatim
    Variant("M2", 20, 0.005, 126, "M"),  # catalog flag, ranked by 6m momentum
    Variant("M3", 60, 0.05, 60, "M"),    # slower signal, scaled deadband
    Variant("M4", 126, 0.08, 126, "M"),  # 6m horizon (engine evidence favours it)
    Variant("M5", 20, 0.005, 20, "W"),   # catalog defaults, weekly rebalance
]

BY_TAG = {v.tag: v for v in VARIANTS}


def load_panel():
    """Cleaned daily close panel + symbols + cleaning report."""
    return load_universe(DATA_DIR)


def roc_panel(panel: pd.DataFrame, period: int) -> pd.DataFrame:
    """Trailing ``period``-bar return — the vectorised form of ``indicators.roc``."""
    return panel / panel.shift(period) - 1.0


def strategy_signal(panel: pd.DataFrame, period: int, threshold: float) -> pd.DataFrame:
    """+1 / 0 / -1 per name-bar. Faithful to ``MomentumFactorStrategy.signal``."""
    m = roc_panel(panel, period)
    sig = pd.DataFrame(np.nan, index=panel.index, columns=panel.columns)
    sig = sig.mask(m > threshold, 1.0)
    sig = sig.mask(m < -threshold, -1.0)
    return sig.fillna(0.0)


def build_score(panel: pd.DataFrame, variant: Variant) -> pd.DataFrame:
    """Long-only cross-sectional score: rank the strategy's long-flagged names by
    trailing momentum. Unsigned names get NaN so the engine cannot hold them."""
    sig = strategy_signal(panel, variant.period, variant.threshold)
    mom = roc_panel(panel, variant.rank_days)
    score = mom.where(sig > 0)
    return score


def slice_window(panel: pd.DataFrame, score: pd.DataFrame, start, end):
    """Restrict both to a window. The score is built on FULL history first so that
    trailing factors entering the window carry their pre-window history."""
    idx = panel.index[(panel.index >= start) & (panel.index <= end)]
    return panel.loc[idx], score.loc[panel.index.intersection(score.index)].loc[
        panel.index.intersection(score.index)
    ].reindex(idx)


def run(panel: pd.DataFrame, score: pd.DataFrame, variant: Variant, start, end):
    """Backtest ``score`` over [start, end] under the engine's default constraints."""
    idx = panel.index[(panel.index >= start) & (panel.index <= end)]
    p = panel.loc[idx]
    s = score.reindex(idx)
    return run_backtest(p, s, COST, CFG, rebalance=variant.rebalance)


def benchmark_buy_hold(panel: pd.DataFrame, start, end):
    """Equal-weight buy-and-hold over [start, end], charged a real deployment cost at
    the same all-in rate the engine charges.

    Buys the whole book once on the first bar, pays the full round trip for it, then
    holds. The cost is applied to EQUITY, not to a bare turnover fraction — the same
    bookkeeping the engine does (GOAL.md §6.4).

    NOTE: an earlier version of this function mangled the first bar by subtracting the
    cost from a *return* instead of from equity, which produced a fictitious +99.78%
    best day and a Sharpe of 20.8. Fixed; see REPORT.md §5.
    """
    idx = panel.index[(panel.index >= start) & (panel.index <= end)]
    p = panel.loc[idx]
    rate = float(COST.all_in_round_trip_bps(100_000)) / 10_000.0

    daily = p.pct_change(fill_method=None).fillna(0.0).mean(axis=1)
    # First bar: no return to earn yet. Deploy the whole book and pay for it.
    eq = 1.0 - rate
    daily.iloc[0] = eq - 1.0
    equity = pd.Series(1.0, index=p.index)
    running = eq
    equity.iloc[0] = running
    for dt in p.index[1:]:
        running *= (1.0 + float(daily.loc[dt]))
        equity.loc[dt] = running

    years = len(equity) / 244
    m = compute_metrics(
        daily,
        equity,
        annual_turnover=rate,
        cost_drag_annual=float(rate / max(years, 1e-9)),
        trades_per_year=1.0 / max(years, 1e-9),
    )
    n_names = float((p.notna().sum(axis=1) > 0).mean())
    return daily, equity, m, n_names


def random_control(panel: pd.DataFrame, variant: Variant, start, end, seed: int):
    """Negative control: random names, matched on how many the strategy had eligible
    at each rebalance, so turnover and cost drag are comparable and only the signal
    differs."""
    rng = np.random.default_rng(seed)
    sig = strategy_signal(panel, variant.period, variant.threshold)
    idx = panel.index[(panel.index >= start) & (panel.index <= end)]
    sig = sig.reindex(idx)
    cols = list(panel.columns)

    # How many names were eligible on each rebalance's first bar.
    from nsealgo.backtest.engine import _rebalance_dates

    rb = _rebalance_dates(idx, variant.rebalance)[1:]
    eligible = {d: int((sig.loc[d] > 0).sum()) for d in rb}

    # A random permutation-based score: same number of finite names as the strategy
    # had, assigned random cross-sectional ranks. The engine then picks from them.
    score = pd.DataFrame(0.0, index=idx, columns=cols)
    for d in rb:
        k = min(eligible[d], len(cols))
        if k <= 0:
            continue
        picks = rng.choice(len(cols), size=k, replace=False)
        score.loc[d, [cols[i] for i in picks]] = rng.random(k)
    return run_backtest(panel, score.reindex(idx), COST, CFG, rebalance=variant.rebalance)


def composite_score(panel: pd.DataFrame):
    from nsealgo.factors.core import build_composite_score

    return build_composite_score(panel)


def metrics_row(tag: str, m, extra: dict | None = None) -> dict:
    row = {
        "tag": tag,
        "cagr": m.cagr,
        "sharpe": m.sharpe,
        "sortino": m.sortino,
        "maxdd": m.max_drawdown,
        "calmar": m.calmar,
        "vol": m.volatility,
        "total": m.total_return,
        "turnover": m.annual_turnover,
        "cost_drag": m.cost_drag_annual,
        "trades": m.trades_per_year,
        "winrate": m.win_rate,
    }
    if extra:
        row.update(extra)
    return row


#: Columns whose values are fractions and should print as percentages.
PCT_COLS = {
    "cagr", "maxdd", "vol", "total", "cost_drag", "winrate",
}


def fmt_table(rows: list[dict], keys: list[str] | None = None) -> str:
    """Render rows. Percent-typed columns are scaled explicitly — never by magnitude.

    An earlier version used `abs(v) < 20` to guess whether a float was a fraction,
    which printed `avg_names = 19.57` as `1956.51` and Sharpe 0.649 as `64.90`.
    See REPORT.md §5.
    """
    if not rows:
        return "(none)"
    keys = keys or list(rows[0])
    out = ["| " + " | ".join(keys) + " |", "|" + "|".join(["---"] * len(keys)) + "|"]
    for r in rows:
        cells = []
        for k in keys:
            v = r.get(k)
            if v is None:
                cells.append("—")
            elif isinstance(v, float) and k in PCT_COLS:
                cells.append(f"{v * 100:.2f}")
            elif isinstance(v, float):
                cells.append(f"{v:.2f}")
            else:
                cells.append(str(v))
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out)


__all__ = [
    "Variant", "VARIANTS", "BY_TAG", "COST", "CFG", "TRAIN_START", "TRAIN_END",
    "TEST_START", "TEST_END", "load_panel", "roc_panel", "strategy_signal",
    "build_score", "run", "benchmark_buy_hold", "random_control", "composite_score",
    "compute_metrics", "yearly_returns", "metrics_row", "fmt_table", "slice_window",
]
