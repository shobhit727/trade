"""Stage 4 — THE TEST RUN. Touches 2024-01-01 .. 2026-10-01 exactly once.

Parameters are frozen at V1 (period=10, multiplier=1.0), selected on TRAIN by max
Sharpe in `s2_train_select.py`. Nothing is re-tuned here.

Reports, per the brief:
  - TEST metrics for V1, buy-and-hold, nsealgo composite
  - gross vs net (cost drag) for V1
  - random-signal control with the same % of bars long
  - per-year returns
  - liveness / weight-count / plausibility sanity checks
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "src")

import signal as sigmod  # noqa: E402

import common  # noqa: E402
import s2_train_select as s2  # noqa: E402

from nsealgo.backtest.engine import PortfolioConfig, run_backtest  # noqa: E402
from nsealgo.backtest.metrics import yearly_returns  # noqa: E402
from nsealgo.costs import CostModel  # noqa: E402
from nsealgo.factors.core import build_composite_score  # noqa: E402

#: Frozen selection from TRAIN. Not changed after seeing TEST.
FROZEN = ("V1", 10, 1.0)
N_RANDOM_SEEDS = 10


def full(idx, panel, score, cost=None):
    res = run_backtest(
        panel.loc[slice(*idx)],
        score.loc[slice(*idx)],
        cost or CostModel(segment="delivery", slippage_bps=5),
        PortfolioConfig(),
        rebalance="M",
    )
    return res


def line(tag, res):
    m = res.metrics
    n = (res.weights > 0).sum(axis=1)
    return (f"{tag:>12} {m.cagr * 100:>7.2f}% {m.sharpe:>7.2f} "
            f"{m.max_drawdown * 100:>8.2f}% {m.calmar:>7.2f} "
            f"{m.annual_turnover:>7.2f} {m.cost_drag_annual * 100:>6.2f}% "
            f"{n.mean():>6.1f} {m.total_return * 100:>8.1f}%")


HEADER = (f"{'':>12} {'CAGR':>8} {'Sharpe':>7} {'MaxDD':>9} {'Calmar':>7} "
          f"{'Turn/y':>7} {'Cost/y':>7} {'Names':>6} {'Total':>9}")


def main() -> None:
    o, h, lo, c, syms = common.load()
    te0, te1 = s2.TEST
    tag, period, mult = FROZEN

    sig = sigmod.signal_panel(h, lo, c, period, mult)
    score = s2.build_score(c, sig)
    live_test = sigmod.liveness(sig, c.loc[te0:te1].index)

    res = full((te0, te1), c, score)
    res_gross = full((te0, te1), c, score,
                     CostModel(segment="delivery", slippage_bps=0))
    bh = s2.buy_and_hold(c, (te0, te1), "BH")
    comp = full((te0, te1), c, build_composite_score(c))

    print(f"=== TEST 2024-01-01 -> 2026-10-01 | frozen params {tag} "
          f"(period={period}, multiplier={mult}) ===")
    print(f"signal liveness on TEST: {live_test:.2%} of symbol-bars long")
    print(f"round-trip cost: {res.diag['round_trip_bps']} bps @ Rs1L/position")
    print()
    print(HEADER)
    print(line(tag, res))
    print(f"{'  gross(0)':>12} {res_gross.metrics.cagr * 100:>7.2f}% "
          f"{res_gross.metrics.sharpe:>7.2f} "
          f"{res_gross.metrics.max_drawdown * 100:>8.2f}% "
          f"{res_gross.metrics.calmar:>7.2f} "
          f"{res_gross.metrics.annual_turnover:>7.2f} "
          f"{0.0:>6.2f}% "
          f"{(res_gross.weights > 0).sum(axis=1).mean():>6.1f} "
          f"{res_gross.metrics.total_return * 100:>8.1f}%")
    print(f"{'BUY-HOLD(ew)':>12} {bh.cagr * 100:>7.2f}% {bh.sharpe:>7.2f} "
          f"{bh.maxdd * 100:>8.2f}% {bh.calmar:>7.2f} "
          f"{0.0:>7.2f} {bh.cost_drag * 100:>6.2f}% "
          f"{bh.avg_names:>6.1f} {0.0:>8.1f}%")
    print(line("COMPOSITE", comp))

    print()
    m, b = res.metrics, bh
    print(f"vs equal-weight buy-and-hold: "
          f"CAGR {m.cagr * 100:.2f}% vs {b.cagr * 100:.2f}% "
          f"({(m.cagr - b.cagr) * 100:+.2f}pp) | "
          f"Sharpe {m.sharpe:.2f} vs {b.sharpe:.2f} | "
          f"MaxDD {m.max_drawdown * 100:.2f}% vs {b.maxdd * 100:.2f}% "
          f"({(m.max_drawdown - b.maxdd) * 100:+.2f}pp)")
    print(f"gross CAGR {res_gross.metrics.cagr * 100:.2f}% -> net "
          f"{m.cagr * 100:.2f}%  (drag {m.cost_drag_annual * 100:.2f}%/yr)")

    # ---- negative control: random signal with the same % of bars long
    print(f"\n--- negative control: {N_RANDOM_SEEDS} random signals, "
          f"same liveness ({live_test:.2%}) ---")
    rng = np.random.default_rng(20261007)
    base = sig.loc[te0:te1]
    rands = []
    for k in range(N_RANDOM_SEEDS):
        draw = rng.random(base.shape)
        rsig = pd.DataFrame(np.where(draw < live_test, 1.0, 0.0),
                            index=base.index, columns=base.columns)
        rsc = s2.build_score(c, rsig)
        rres = full((te0, te1), c, rsc)
        rands.append(rres.metrics.cagr)
        print(f"  seed {k:>2}: CAGR {rres.metrics.cagr * 100:>7.2f}% "
              f"Sharpe {rres.metrics.sharpe:>6.2f} "
              f"MaxDD {rres.metrics.max_drawdown * 100:>7.2f}% "
              f"names {(rres.weights > 0).sum(axis=1).mean():.1f}")
    ra = np.array(rands)
    print(f"  random: mean {ra.mean() * 100:.2f}%  median {np.median(ra) * 100:.2f}%  "
          f"best {ra.max() * 100:.2f}%  worst {ra.min() * 100:.2f}%")
    print(f"  V1 beats {int((ra < m.cagr).sum())}/{N_RANDOM_SEEDS} random controls")

    print("\n--- TEST calendar-year returns (V1) ---")
    yr = yearly_returns(res.returns)
    for y, v in yr.items():
        print(f"  {y}: {v * 100:>7.2f}%")
    print(f"  positive years: {int((yr > 0).sum())}/{len(yr)}")

    print("\n--- plausibility ---")
    n = (res.weights > 0).sum(axis=1)
    print(f"  CAGR {m.cagr * 100:.1f}% (long-only unlevered NIFTY-50 plausible band "
          f"40-50% max) -> {'OK' if m.cagr < 0.5 else 'IMPLAUSIBLE, INVESTIGATE'}")
    print(f"  avg names held {n.mean():.1f} (config band 22-30) -> "
          f"{'OK' if n.mean() <= 30.5 else 'BUG'}")
    print(f"  liveness {live_test:.2%} (brief floor ~5%) -> "
          f"{'OK' if live_test >= 0.05 else 'EFFECTIVELY FLAT'}")
    print(f"  max single-name weight {res.weights.max().max() * 100:.2f}% (cap 12%)")


if __name__ == "__main__":
    main()
