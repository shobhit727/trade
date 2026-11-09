"""Shared harness for the ``gap`` agent run.

Reuses nsealgo infrastructure only. Nothing in ``src/`` is modified.

Three facts about the catalog strategy drive this module (see REPORT.md §1):

1. ``GapConfig.period`` is dead config -- ``signal()`` only ever reads ``closes[-2:]``.
   I repurpose ``period`` as the gap lookback ``L`` (a disclosed semantic repair).
2. The shipped quantity is a 1-bar close-to-close RETURN, not a gap, and its default
   ``threshold=0.0`` is a no-op (a return is essentially never exactly zero), so the
   signal is +/-1 on ~100% of bars.
3. A +/-1/0 signal is *degenerate* as a cross-sectional score: passing the raw signal
   into ``build_rebalance_weights`` leaves ~50 names tied at +1.0 and the stable sort
   then picks alphabetically, i.e. an artefact of the ticker list rather than a signal.
   So the flag is used as a MASK and momentum ranks the names inside it, exactly as the
   brief's §5 example specifies. The moment the rank key is momentum, the gap flag's
   only job is choosing *which* names get ranked -- which is why the momentum-only
   ablation in this module is the load-bearing control, not a nicety.
"""

from __future__ import annotations

import os
import sys
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from nsealgo.backtest.engine import PortfolioConfig, run_backtest  # noqa: E402
from nsealgo.backtest.metrics import (  # noqa: E402
    Metrics,
    compute_metrics,
    yearly_returns,
)
from nsealgo.costs import CostModel  # noqa: E402
from nsealgo.data.loader import load_universe  # noqa: E402
from nsealgo.factors.core import build_composite_score  # noqa: E402

__all__ = [
    "CONTROL_SEEDS",
    "RANK_LB",
    "TEST_END",
    "TEST_START",
    "TRAIN_END",
    "TRAIN_START",
    "VARIANTS",
    "ZeroCostModel",
    "align",
    "backtest",
    "composite_window",
    "cost_model",
    "equal_weight_bh",
    "gap_flag",
    "load_all",
    "liveness",
    "metrics_table",
    "momentum_only_score",
    "portfolio_config",
    "random_mask_like",
    "score_from_flag",
    "score_window",
    "slice_panel",
    "summarise",
    "windowed",
    "yearly",
]

DATA_DIR = str(ROOT / "data" / "nse")

TRAIN_START = pd.Timestamp("2016-01-01")
TRAIN_END = pd.Timestamp("2023-12-31")
TEST_START = pd.Timestamp("2024-01-01")
TEST_END = pd.Timestamp("2026-10-01")

#: Ranking lookback. NOT tuned -- held at the brief's recommended 126d (6-month)
#: momentum for every variant, so the whole parameter budget is spent on the gap
#: lookback and threshold (the strategy's own knobs).
RANK_LB = 126

#: The declared 5-variant budget (REPORT.md §0). Do not add to this.
VARIANTS: dict[str, dict] = {
    "V1": {"L": 1, "threshold": 0.000, "note": "as shipped"},
    "V2": {"L": 1, "threshold": 0.010, "note": "1-bar gap, 1% threshold"},
    "V3": {"L": 5, "threshold": 0.000, "note": "5-bar gap, no threshold"},
    "V4": {"L": 5, "threshold": 0.010, "note": "5-bar gap, 1% threshold"},
    "V5": {"L": 21, "threshold": 0.000, "note": "21-bar gap, no threshold"},
}

CONTROL_SEEDS = (11, 29, 47, 83, 101)


# --------------------------------------------------------------------------- #
# Costs
# --------------------------------------------------------------------------- #


def cost_model() -> CostModel:
    """The brief's cost stack: delivery segment, 5 bps slippage."""
    return CostModel(segment="delivery", slippage_bps=Decimal("5"))


class ZeroCostModel(CostModel):
    """Statutory charges removed entirely -- used ONLY to report gross-vs-net drag."""

    def round_trip_bps(self, notional: Decimal) -> Decimal:  # noqa: D102
        return Decimal("0")


def portfolio_config() -> PortfolioConfig:
    """Shipped defaults, untouched: 22 names, 12% single, 25% sector, 10% cash."""
    return PortfolioConfig()


# --------------------------------------------------------------------------- #
# Data
# --------------------------------------------------------------------------- #


def load_all():
    """The brief's mandatory first step."""
    return load_universe(DATA_DIR)


def align(panel: pd.DataFrame) -> None:
    """Make the tz-naive window bounds comparable with the tz-aware panel index.

    ``load_universe`` returns an Asia/Kolkata-aware index. Slicing it with naive
    timestamps raises, so every window bound is localised once, here. Done in place on
    the module-level constants so no caller can forget it.
    """
    for name in ("TRAIN_START", "TRAIN_END", "TEST_START", "TEST_END"):
        ts = globals()[name]
        if getattr(panel.index, "tz", None) is not None and ts.tzinfo is None:
            globals()[name] = ts.tz_localize(panel.index.tz)


def slice_panel(panel: pd.DataFrame, lo, hi) -> pd.DataFrame:
    return panel.loc[lo:hi]


# --------------------------------------------------------------------------- #
# The signal
# --------------------------------------------------------------------------- #


def gap_flag(panel: pd.DataFrame, lookback: int, threshold: float) -> pd.DataFrame:
    """Boolean mask: the shipped strategy's long signal, ``+1`` branch only.

    ``gap = close[t] / close[t-L] - 1`` and the flag is ``gap > threshold``. L=1 with
    threshold=0.0 reproduces ``signal() == +1`` exactly. Uses closes up to and
    including day t only, so no look-ahead.
    """
    gap = panel / panel.shift(lookback) - 1.0
    return gap > threshold


def momentum(panel: pd.DataFrame) -> pd.DataFrame:
    """126d trailing momentum -- the fixed ranking key."""
    return panel / panel.shift(RANK_LB) - 1.0


def score_from_flag(panel: pd.DataFrame, flag: pd.DataFrame,
                    key: pd.DataFrame | None = None) -> pd.DataFrame:
    """Mask by the gap signal, rank the survivors by momentum.

    This is the brief's §5 construction verbatim. Non-flagged names become NaN and are
    dropped by ``build_rebalance_weights`` (it requires a finite score and finite vol),
    so the book holds ``min(22, n_flagged)`` names.

    ``key`` is the momentum panel. Pass a FULL-panel key when slicing to a window --
    see ``score_window`` for why that matters.
    """
    return (momentum(panel) if key is None else key).where(flag).rank(axis=1, pct=True)


def momentum_only_score(panel: pd.DataFrame,
                        key: pd.DataFrame | None = None) -> pd.DataFrame:
    """ABLATION: rank momentum with NO gap filter.

    If this matches the strategy, the gap signal contributes nothing and the result is
    pure momentum. This is the load-bearing control for this strategy.
    """
    return (momentum(panel) if key is None else key).rank(axis=1, pct=True)


def random_mask_like(flag: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Negative control: random names, identical per-day count as the strategy."""
    rng = np.random.default_rng(seed)
    counts = flag.sum(axis=1).to_numpy()
    draws = rng.random(flag.shape)
    order = np.argsort(draws, axis=1)
    ranks = np.empty_like(order)
    np.put_along_axis(
        ranks, order, np.arange(flag.shape[1])[None, :].repeat(len(flag), 0), axis=1
    )
    return ranks < counts[:, None]


# --------------------------------------------------------------------------- #
# Backtest wrappers
# --------------------------------------------------------------------------- #


def score_window(panel: pd.DataFrame, lo, hi, lookback: int, threshold: float):
    """Score a window WITHOUT a warmup gap.

    BUG FOUND IN VERIFICATION (s4): slicing the panel to the window first and only then
    computing the score leaves the first ``RANK_LB``=126 bars with NaN momentum, so the
    book holds ~0 names for the first ~6 months. That silently truncated BOTH the TRAIN
    and the TEST evaluation (first weights landed 2024-08-01, and 2024 averaged 12.0
    names instead of ~30). The factor must be built on the FULL panel -- using closes
    from before the window is legitimate, it is not look-ahead -- and only then sliced.

    Returns (panel_window, score_window).
    """
    full_flag = gap_flag(panel, lookback, threshold)
    return windowed(panel, lo, hi,
                    lambda key: score_from_flag(panel, full_flag, key=key))


def windowed(panel: pd.DataFrame, lo, hi, score_fn):
    """Generic no-warmup window builder.

    ``score_fn(momentum_full_panel) -> score`` is called with the FULL-panel ranking
    key, and the result is sliced to ``[lo, hi]``. Every scored book in this report goes
    through here so no control can accidentally get a truncated warmup while the
    strategy does not.
    """
    return slice_panel(panel, lo, hi), score_fn(momentum(panel)).loc[lo:hi]


def composite_window(panel: pd.DataFrame, lo, hi):
    """nsealgo composite, also scored on the full panel (its slowest factor is 252d)."""
    return slice_panel(panel, lo, hi), build_composite_score(panel).loc[lo:hi]


def backtest(panel, score, rebalance: str = "M", gross: bool = False):
    cm = ZeroCostModel() if gross else cost_model()
    return run_backtest(panel, score, cm, portfolio_config(), rebalance=rebalance)


def equal_weight_bh(panel: pd.DataFrame) -> tuple[pd.Series, Metrics, float]:
    """Buy-and-hold: equal-weight all names, net of one entry+exit round trip.

    A buy-and-hold book pays a single round trip, not monthly turnover, so the cost is
    charged once on day 1. That is the *generous* reading for the benchmark.
    """
    rets = panel.pct_change(fill_method=None).mean(axis=1).fillna(0.0)
    rate = float(cost_model().all_in_round_trip_bps(Decimal("100000"))) / 10_000.0
    eq, costs, out = 1.0, 0.0, pd.Series(0.0, index=panel.index)
    for i, dt in enumerate(panel.index):
        prev = eq
        if i == 0:
            eq *= 1.0 - rate
            costs += rate
        else:
            eq *= 1.0 + float(rets.loc[dt])
        out.loc[dt] = eq / prev - 1.0
    return out, compute_metrics(out, (1.0 + out).cumprod()), costs


def liveness(flag: pd.DataFrame, lo, hi) -> tuple[float, float]:
    """(frac of valid name-bars flagged long, mean flagged names/day)."""
    f = flag.loc[lo:hi]
    valid = f.notna().sum(axis=1).clip(lower=1)
    return (
        float(f.sum(axis=1).div(valid).mean()),
        float(f.sum(axis=1).mean()),
    )


def yearly(returns: pd.Series) -> pd.Series:
    return yearly_returns(returns)


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #

_COLS = ("CAGR", "Sharpe", "MaxDD", "Calmar", "Turn", "Drag", "N")

_HEAD = (
    f"  {'Label':<22}{'CAGR':>10}{'Sharpe':>9}{'MaxDD':>10}"
    f"{'Calmar':>8}{'Turn':>8}{'Drag':>8}{'N':>7}"
)


def metrics_table(rows: list[dict]) -> str:
    out = [_HEAD, "  " + "-" * (len(_HEAD) - 2)]
    for r in rows:
        m: Metrics = r["metrics"]
        out.append(
            f"  {r['label']:<22}{m.cagr * 100:>9.2f}%{m.sharpe:>9.2f}"
            f"{m.max_drawdown * 100:>9.2f}%{m.calmar:>8.2f}"
            f"{m.annual_turnover:>7.2f}x{m.cost_drag_annual * 100:>7.2f}%"
            f"{r.get('avg_names', float('nan')):>7.1f}"
        )
    return "\n".join(out)


def summarise(label, result, avg_names=None) -> dict:
    return {
        "label": label,
        "metrics": result.metrics,
        "avg_names": result.diag["avg_names"] if avg_names is None else avg_names,
    }


os.environ.setdefault("PYTHONHASHSEED", "0")
