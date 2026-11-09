"""Shared, verified harness for the agent_cmf run.

Everything here is TRAIN-safe by construction: the only TEST constant is the date
bound, and no function in this module selects parameters.

Verified in `10_verify_panels.py`:
  * OHLCV panels rebuild bit-for-bit from `data/nse` via `nsealgo.data.loader`
  * CMF matches `cryptobot.strategies.indicators.chaikin_mf` to < 1e-14
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, "src")

import numpy as np
import pandas as pd

from nsealgo.backtest.engine import PortfolioConfig, run_backtest
from nsealgo.backtest.metrics import compute_metrics
from nsealgo.costs import CostModel
from nsealgo.factors.core import rank_cross_sectional

D = "research/agent_cmf"
P = os.path.join(D, "v_*.pkl")

# --------------------------------------------------------------------------- #
# Protocol windows. TRAIN is 2016-01-01..2023-12-31; TEST is 2024-01-01..2026-10-01.
# WARM is PRE-TEST history used only so the book is invested on the first TEST bar.
# --------------------------------------------------------------------------- #
TZ = "Asia/Kolkata"
TRAIN0 = pd.Timestamp("2016-01-01", tz=TZ)
TRAIN1 = pd.Timestamp("2023-12-31", tz=TZ)
TEST0 = pd.Timestamp("2024-01-01", tz=TZ)
TEST1 = pd.Timestamp("2026-10-01", tz=TZ)
WARM = pd.Timestamp("2023-07-01", tz=TZ)   # < TRAIN1, i.e. still TRAIN data

MOM_LOOKBACK = 126
COST = CostModel(segment="delivery", slippage_bps=5)
CFG = PortfolioConfig()
N_SEEDS = 300


# --------------------------------------------------------------------------- #
# Signal
# --------------------------------------------------------------------------- #

def cmf_panel(closes, highs, lows, vols, period):
    """Chaikin Money Flow, window ending at bar t. No lookahead."""
    rng = (highs - lows).replace(0.0, np.nan)
    mfm = ((closes - lows) - (highs - closes)) / rng
    num = (mfm * vols).rolling(period, min_periods=period).sum()
    den = vols.rolling(period, min_periods=period).sum()
    return num / den.replace(0.0, np.nan)


def load_panels():
    return (pd.read_pickle(os.path.join(D, "v_closes.pkl")),
            pd.read_pickle(os.path.join(D, "v_highs.pkl")),
            pd.read_pickle(os.path.join(D, "v_lows.pkl")),
            pd.read_pickle(os.path.join(D, "v_vols.pkl")))


# --------------------------------------------------------------------------- #
# The 5 declared variants (from BUDGET.md — not to be extended)
# --------------------------------------------------------------------------- #
# name, period, threshold, direction, construction
SPECS = [
    ("V1_p20_t10_literal",       20, 0.10, "literal", "mom_rank"),
    ("V2_p20_t10_flipped",       20, 0.10, "flipped", "mom_rank"),
    ("V3_p10_t10_flipped",       10, 0.10, "flipped", "mom_rank"),
    ("V4_p60_t10_flipped",       60, 0.10, "flipped", "mom_rank"),
    ("V5_p20_continuous_flip",   20, 0.00, "flipped", "cmf_rank"),
]
VARIANT_NAMES = [s[0] for s in SPECS]


def momentum_score(panel, mask):
    """Brief §5: 126d momentum ranked cross-sectionally among flagged names only."""
    mom = panel / panel.shift(MOM_LOOKBACK) - 1.0
    return mom.where(mask).rank(axis=1, pct=True)


def build_score(panel, closes, highs, lows, vols, spec):
    """Return (score, mask) for one declared variant."""
    name, period, thr, direction, construction = spec
    cmf = cmf_panel(closes, highs, lows, vols, period)
    if construction == "mom_rank":
        m = (cmf > thr) if direction == "literal" else (cmf < -thr)
        return momentum_score(panel, m), m
    if construction == "cmf_rank":
        return rank_cross_sectional(-cmf), cmf.notna()
    raise ValueError(construction)


# --------------------------------------------------------------------------- #
# Running / measuring
# --------------------------------------------------------------------------- #

def run_window(panel, score, lo, hi):
    """Backtest restricted to [lo, hi] with a pre-`lo` warmup slice for vol."""
    warm_lo = lo - pd.Timedelta(days=400)
    warm_lo = max(warm_lo, panel.index[0])
    sl = slice(warm_lo, hi)
    return run_backtest(panel.loc[sl], score.loc[sl], COST, CFG)


def window_turnover(res, lo, hi) -> float:
    """One-way turnover per year, measured strictly inside [lo, hi].

    Validated against the engine: `run_backtest` computes
    ``turnover_by_date = |tgt - tgt.shift(1)|.sum / 2`` on the *targets*, and
    ``held = tgt.ffill()``, so the same quantity can be recovered exactly from
    ``res.weights``.  (Asserted equal in `14_test.py`.)

    This must NOT be derived by rescaling ``res.metrics.annual_turnover``: that figure
    divides by the *whole engine span*, which starts ~400 days before `lo`, so its
    numerator contains turnover from outside the window. Rescaling it by the year
    ratio inflates turnover and cost drag by ~40%.
    """
    w = res.weights
    turn = (w - w.shift(1).fillna(0.0)).abs().sum(axis=1) / 2.0
    t = turn.loc[lo:hi]
    yrs = len(res.returns.loc[lo:hi]) / 244.0
    if yrs <= 0:
        return 0.0
    return float(t.sum() / yrs)


def window_cost_drag(res, lo, hi) -> float:
    """Annual cost drag inside [lo, hi], as a fraction of the equity at `lo`.

    Reconstructed exactly from the engine's own arithmetic rather than rescaled from
    the engine's aggregate. In `run_backtest`::

        eq *= (1 + g_t);  eq -= turn_t * eq * rate;  daily_t = eq/prev_eq - 1

    so ``daily_t = (1 + g_t) * (1 - turn_t*rate) - 1`` and therefore
    ``g_t = (1 + daily_t)/(1 - turn_t*rate) - 1``. Recovering ``g_t`` from
    ``res.returns`` (which is POST-cost) avoids the trap of treating it as price
    returns. Replaying from equity 1.0 makes the drag independent of the warmup path.

    Note ``res.returns`` is the post-cost portfolio return series, not a price panel.
    """
    rate = float(res.diag["round_trip_bps"]) / 10_000.0
    turn = (res.weights - res.weights.shift(1).fillna(0.0)).abs().sum(axis=1) / 2.0
    daily = res.returns.loc[lo:hi]
    tt = turn.reindex(daily.index).fillna(0.0)
    keep = tt * rate < 1.0
    daily, tt = daily[keep], tt[keep]
    gross = (1.0 + daily) / (1.0 - tt * rate) - 1.0
    eq, costs = 1.0, 0.0
    for dt in gross.index:
        eq *= 1.0 + float(gross.loc[dt])
        c = float(tt.loc[dt]) * eq * rate
        if c > 0:
            eq -= c
            costs += c
    yrs = len(res.returns.loc[lo:hi]) / 244.0
    return float(costs / yrs) if yrs > 0 else 0.0


def metrics_on(res, lo, hi):
    """Metrics restricted to [lo, hi], equity re-based to 1.0 at `lo`.

    Turnover/cost-drag are measured strictly inside the window so the reported drag
    belongs to the reported window.
    """
    r = res.returns.loc[lo:hi]
    eq = res.equity.loc[lo:hi]
    eq = eq / eq.iloc[0]
    if len(r) == 0:
        raise ValueError(f"empty window [{lo}, {hi}]")
    # A bare (returns, equity) stand-in (e.g. buy-and-hold) has no weights/metrics.
    if getattr(res, "weights", None) is None:
        return compute_metrics(r, eq)
    return compute_metrics(
        r, eq,
        annual_turnover=window_turnover(res, lo, hi),
        cost_drag_annual=window_cost_drag(res, lo, hi),
        trades_per_year=float(window_turnover(res, lo, hi) > 0) * (
            len([d for d in w_res_dates(res, lo, hi)]) / (len(r) / 244.0)),
    )


def w_res_dates(res, lo, hi):
    """Dates in [lo, hi] on which the book actually changed (a rebalance happened)."""
    w = res.weights
    turn = (w - w.shift(1).fillna(0.0)).abs().sum(axis=1) / 2.0
    return list(turn.loc[lo:hi][turn.loc[lo:hi] > 0].index)


def row(name, m, res=None, **extra):
    d = {
        "variant": name,
        "cagr_pct": round(m.cagr * 100, 3),
        "sharpe": round(m.sharpe, 3),
        "maxdd_pct": round(m.max_drawdown * 100, 2),
        "calmar": round(m.calmar, 3),
        "vol_pct": round(m.volatility * 100, 2),
        "turnover_x_y": round(m.annual_turnover, 3),
        "cost_drag_pct_y": round(m.cost_drag_annual * 100, 3),
        "trades_y": round(m.trades_per_year, 1),
        "win_rate_pct": round(m.win_rate * 100, 1),
        "total_ret_pct": round(m.total_return * 100, 2),
    }
    if res is not None:
        d["avg_names"] = round(res.diag["avg_names"], 2)
        d["avg_top_w_pct"] = round(res.diag["avg_top_weight"] * 100, 2)
        d["rt_bps"] = res.diag["round_trip_bps"]
    d.update(extra)
    return d


def banner(t):
    print()
    print("=" * 90)
    print(t)
    print("=" * 90)


def spearman_ic(factor, fwd):
    """Per-day Spearman IC of factor vs forward return."""
    rows = {}
    for d in factor.index:
        a = factor.loc[d]
        b = fwd.loc[d]
        m = a.notna() & b.notna()
        if m.sum() < 10:
            continue
        ra = a[m].rank()
        rb = b[m].rank()
        if ra.std() == 0 or rb.std() == 0:
            continue
        rows[d] = float(ra.corr(rb))
    return pd.Series(rows)


def ic_summary(ic: pd.Series):
    n = len(ic)
    t = float(ic.mean() / (ic.std(ddof=1) / np.sqrt(n))) if n > 2 else float("nan")
    return {"n": n, "mean": float(ic.mean()), "t": t,
            "hit_pct": float((ic > 0).mean() * 100)}


def show(df, title):
    banner(title)
    with pd.option_context("display.width", 240, "display.max_columns", 40):
        print(df.to_string(index=False))
