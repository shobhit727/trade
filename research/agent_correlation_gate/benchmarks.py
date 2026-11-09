"""Benchmarks + negative controls. Validated on TRAIN first, then used on TEST.

1. buy-and-hold, the literal brief form: equal-weight daily mean of the panel.
   Gross (no cost) -- reported because that is what the brief specifies; a fair
   cost-aware B&H is also provided (see `bh_constrained`).
2. buy-and-hold constrained & cost-aware: the SAME engine, a constant score, so the
   benchmark pays the same entry cost, respects the same 22/12%/25%/10% limits, and
   is held to the end of the window.
3. negative control: a random signal with the *same fraction of bars long*, built
   from a fixed seed and an independent draw each run.
4. the nsealgo composite score (`build_composite_score`) on the same panel.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from common import backtest, score_from_signal, signal_panel

from nsealgo.backtest.metrics import compute_metrics
from nsealgo.factors.core import build_composite_score


def bh_gross(panel, start, end):
    """Equal-weight buy-and-hold, gross of costs (the brief's literal formula)."""
    rets = panel.loc[start:end].pct_change(fill_method=None).mean(axis=1).fillna(0.0)
    eq = (1.0 + rets).cumprod()
    return rets, eq, compute_metrics(rets, eq, annual_turnover=2.0,
                                    cost_drag_annual=0.0, trades_per_year=2.0)


def bh_constrained(panel, start, end):
    """Cost-aware, constraint-respecting, 22-name equal-conviction buy-and-hold."""
    p = panel.loc[start:end]
    sc = pd.DataFrame(1.0, index=p.index, columns=p.columns)  # every name equal
    return backtest(panel, sc, start, end)


def random_control(panel, live_fraction, start, end, seed=0, n=5):
    """n random long-only books with the same overall % of symbol-days long.

    Each draw is an i.i.d. Bernoulli mask calibrated to `live_fraction`, so the
    control has the same average position count and the same turnover budget
    pressure -- it differs from the strategy only in that its signal is noise.
    """
    out = []
    sub = panel.loc[start:end]
    target = live_fraction
    for k in range(n):
        rng = np.random.default_rng(seed * 1000 + k)
        mask = rng.random(sub.shape) < target
        sig = pd.DataFrame(np.where(mask, 1.0, 0.0), index=sub.index, columns=sub.columns)
        # rank the always-on conviction measure -> a real cross-sectional book
        sc = pd.DataFrame(1.0, index=sub.index, columns=sub.columns).where(
            sig > 0
        ).rank(axis=1, pct=True)
        res = backtest(panel, sc, start, end)
        out.append(res.metrics)
    return out


def composite(panel, start, end):
    return backtest(panel, build_composite_score(panel), start, end)


def strategy(panel, period, threshold, start, end):
    sig = signal_panel(panel, period, threshold)
    return sig, backtest(panel, score_from_signal(sig, panel, period), start, end)
