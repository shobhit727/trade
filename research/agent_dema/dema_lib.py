"""Shared helpers for the `dema_strategy` NSE adaptation.

Contains:
  * `dema_panel`    — point-in-time DEMA for every symbol, replicating
                      `cryptobot.strategies.indicators.dema` exactly.
  * `dema_signal`   — the strategy's own +1/-1 signal as a panel.
  * `score_from_gate` / `score_pure_dema` — the two cross-sectional score forms.
  * `benchmarks`    — buy-and-hold, random-signal control, nsealgo composite.
  * `bench_metrics` — equal-weight buy-and-hold with cost charged on entry.
  * `table`         — a compact metrics table for the report.

No lookahead: every quantity is built from `panel` rows up to and including *t* only.
`run_backtest` (engine.py) then holds weights decided on *t* from *t+1* onward, which
is the second, independent half of the no-lookahead guarantee.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from nsealgo.backtest.engine import PortfolioConfig, run_backtest  # noqa: E402
from nsealgo.backtest.metrics import Metrics, compute_metrics  # noqa: E402
from nsealgo.costs import CostModel  # noqa: E402
from nsealgo.factors.core import (  # noqa: E402
    momentum_6m,
    rank_cross_sectional,
)

TRAIN_START = pd.Timestamp("2016-01-01", tz="Asia/Kolkata")
TRAIN_END = pd.Timestamp("2023-12-31", tz="Asia/Kolkata")
TEST_START = pd.Timestamp("2024-01-01", tz="Asia/Kolkata")
TEST_END = pd.Timestamp("2026-10-01", tz="Asia/Kolkata")

BASE_COST = CostModel(segment="delivery", slippage_bps=5)
CFG = PortfolioConfig(n_positions=22)


# --------------------------------------------------------------------------- #
# DEMA
# --------------------------------------------------------------------------- #


def _ema_series(a: np.ndarray, period: int) -> np.ndarray:
    """Same recursion as `cryptobot.strategies.indicators._ema_series`, NaN-aware.

    One deviation, forced by the panel: the reference seeds at ``a[0]``. The panel is
    NaN before a symbol lists (eternal, maxhealth, hdfclife, sbilife, indigo,
    coalindia are recent listings/renames), so ``a[0]`` is NaN for them. Seeding on
    NaN propagates NaN through the entire recursion and silently kills the symbol
    forever -- which is exactly what my first version did, and the exactness test
    initially masked it by comparing two empty arrays. We seed at the first *valid*
    close instead, which is what the live system does anyway: it cannot have a DEMA
    before it has a price.

    Callers pass a forward-filled column (see `dema_panel`), so interior gaps never
    reach here -- that keeps the result bit-identical to the reference implementation.
    """
    k = 2.0 / (period + 1.0)
    n = len(a)
    out = np.full(n, np.nan, dtype=float)
    valid = np.flatnonzero(~np.isnan(a))
    if len(valid) == 0:
        return out
    s = int(valid[0])
    out[s] = a[s]
    for i in range(s + 1, n):
        prev = out[i - 1]
        if np.isnan(a[i]) or np.isnan(prev):
            out[i] = prev
        else:
            out[i] = k * a[i] + (1.0 - k) * prev
    return out


def _indicator_input(panel: pd.DataFrame) -> pd.DataFrame:
    """Closes with interior gaps carried forward *from the past*.

    Only 45 interior NaN cells exist in the whole 48x4629 panel (halted / missing
    bars). Leading NaNs -- pre-listing, where we must not fabricate a price -- are
    left untouched. Brief §4.6 permits forward-fill provided it comes from the past.
    """
    return panel.ffill()


def dema_panel(panel: pd.DataFrame, period: int) -> pd.DataFrame:
    """Point-in-time DEMA per symbol, NaN before the symbol's first valid bar."""
    src = _indicator_input(panel)
    e1 = src.apply(lambda col: _ema_series(col.to_numpy(dtype=float), period))
    e2 = e1.apply(lambda col: _ema_series(col.to_numpy(dtype=float), period))
    return 2.0 * e1 - e2


def dema_distance_panel(panel: pd.DataFrame, period: int) -> pd.DataFrame:
    """close / DEMA - 1. Positive = price above the DEMA (the strategy's long state)."""
    return panel / dema_panel(panel, period) - 1.0


def dema_signal(panel: pd.DataFrame, period: int) -> pd.DataFrame:
    """The catalog strategy's own signal: +1 above DEMA, -1 below."""
    dist = dema_distance_panel(panel, period)
    return (dist > 0).astype(float) * 2.0 - 1.0


# --------------------------------------------------------------------------- #
# Cross-sectional scores
# --------------------------------------------------------------------------- #


def score_from_gate(panel: pd.DataFrame, period: int) -> pd.DataFrame:
    """Brief §5 recipe: gate on the DEMA state, rank the survivors by 6m momentum.

    Names that are not above their DEMA get NaN so the engine cannot select them
    (`build_rebalance_weights` treats non-finite scores as ineligible). No ffill: a
    name that is below its DEMA stays unbuyable until it crosses back.
    """
    dist = dema_distance_panel(panel, period)
    mom = momentum_6m(panel)
    gated = mom.where(dist > 0)
    return rank_cross_sectional(gated)


def score_pure_dema(panel: pd.DataFrame, period: int) -> pd.DataFrame:
    """Control (V5): rank purely by distance above the DEMA, no momentum overlay."""
    return rank_cross_sectional(dema_distance_panel(panel, period))


# --------------------------------------------------------------------------- #
# Backtest wrapper
# --------------------------------------------------------------------------- #


def backtest(panel: pd.DataFrame, score: pd.DataFrame, cost: CostModel = BASE_COST):
    return run_backtest(panel, score, cost, CFG, rebalance="M")


# --------------------------------------------------------------------------- #
# Benchmarks
# --------------------------------------------------------------------------- #


def buy_and_hold(panel: pd.DataFrame, cost: CostModel = BASE_COST) -> tuple[pd.Series, Metrics]:
    """Equal-weight buy-and-hold, net of one full round-trip's entry cost.

    Brief §4.5 specifies `panel.pct_change().mean(axis=1)`. That is an equal-weight
    return series, so the whole book is bought once at the window start and never
    touched again. The entry (buy) leg is charged as a fraction of the book:
    half the all-in round trip in bps of turnover.
    """
    ew = panel.pct_change(fill_method=None).mean(axis=1).fillna(0.0)
    rt = float(cost.all_in_round_trip_bps(Decimal(str(100_000)))) / 10_000.0
    entry = pd.Series(0.0, index=ew.index)
    entry.iloc[0] = -rt / 2.0          # one-way entry = half the round trip
    net = (1.0 + ew + entry).cumprod()
    daily = net.pct_change(fill_method=None).fillna(0.0)
    daily.iloc[0] = net.iloc[0] - 1.0
    years = len(net) / 244.0
    m = compute_metrics(daily, net, annual_turnover=1.0 / years,
                        cost_drag_annual=rt / 2.0 / years,
                        trades_per_year=1.0 / years)
    return net, m


def random_signal_score(
    panel: pd.DataFrame, target_long_frac: float, seed: int
) -> pd.DataFrame:
    """Negative control: iid coin per (day, name) gated to the target long fraction.

    `target_long_frac` is matched to the strategy's own fraction of positive signals
    over the same window, so the two books are long the same amount of the time and
    differ only in whether the choice is informed.

    Fully vectorised. Survivors are ranked by a second random draw so the engine's
    top-22 selection is not biased by column order -- otherwise the control would be
    systematically worse than a fair coin for reasons unrelated to the signal.
    """
    rng = np.random.default_rng(seed)
    n_t, n_c = panel.shape
    long_mask = rng.random((n_t, n_c)) < target_long_frac

    key = rng.random((n_t, n_c))
    key[~long_mask] = np.inf
    order = np.argsort(key, axis=1, kind="stable")
    rank_idx = np.empty_like(order)
    np.put_along_axis(rank_idx, order, np.broadcast_to(np.arange(n_c), order.shape), axis=1)

    n_long = long_mask.sum(axis=1, keepdims=True)
    n_long[n_long == 0] = 1
    vals = np.where(long_mask, (rank_idx + 1) / n_long, np.nan)
    return pd.DataFrame(vals, index=panel.index, columns=panel.columns)


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #


def table(label: str, m: Metrics, extra: dict | None = None) -> str:
    extra = extra or {}
    return (
        f"{label:<34} CAGR {m.cagr * 100:>7.2f}%  Sharpe {m.sharpe:>6.2f}  "
        f"MaxDD {m.max_drawdown * 100:>7.2f}%  Calmar {m.calmar:>6.2f}  "
        f"Ret {m.total_return * 100:>7.1f}%"
        + (
            f"  Turn {m.annual_turnover:>4.2f}x/y  Drag {m.cost_drag_annual * 100:>4.2f}%/y"
            if m.annual_turnover
            else ""
        )
        + ("\n" + " " * 35 + " ".join(f"{k}={v}" for k, v in extra.items()) if extra else "")
    )


def live_fraction(panel: pd.DataFrame, period: int, start, end) -> float:
    """Fraction of (day, name) observations where the strategy is long."""
    sig = dema_signal(panel.loc[start:end], period)
    return float((sig > 0).to_numpy().mean())
