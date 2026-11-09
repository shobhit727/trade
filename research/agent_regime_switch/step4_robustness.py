"""STEP 4 — robustness. Is the TEST finding an artefact of one window?

Decomposition, both directions, on every window:
    ranking worth = (GATE + RANK)          - (GATE + RANDOM RANK)
    gate    worth = (GATE + RANK)          - (RANDOM GATE + RANDOM RANK)

Note every quantity below is computed on the FULL panel and then sliced, never on a
truncated window -- computing a 200-bar rolling indicator on a 684-bar window
silently zeroes its first 199 bars.

Nothing here changes the selected variant.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness import (  # noqa: E402
    TEST_END,
    TEST_START,
    TRAIN_END,
    TRAIN_START,
    cost_model,
    gate_only_score,
    load,
    long_flag,
    portfolio_config,
    run_backtest,
    strategy_score,
    window,
)

PERIOD = 200
N_SEEDS = 10
SUBWINDOWS = [
    ("2009-2013", "2009-01-01", "2013-12-31"),
    ("2014-2018", "2014-01-01", "2018-12-31"),
    ("2019-2021", "2019-01-01", "2021-12-31"),
    ("2022-2023", "2022-01-01", "2023-12-31"),
    ("TRAIN all", "2016-01-01", "2023-12-31"),
    ("TEST 2024-26", "2024-01-01", "2026-10-01"),
    ("full 2008-26", "2008-01-01", "2026-10-01"),
]


def random_gate_score(panel: pd.DataFrame, period: int, seed: int) -> pd.DataFrame:
    """Pure-random eligible set of the same daily size, randomly ordered."""
    flag = long_flag(panel, period)
    n_flagged = flag.sum(axis=1)
    rng = np.random.default_rng(50_000 + seed)
    noise = pd.DataFrame(rng.random(panel.shape), index=panel.index, columns=panel.columns)
    order = noise.rank(axis=1, ascending=False)
    return (1.0 - noise).where(order.le(n_flagged, axis=0))


def cagr(px, sc, cm, cfg):
    return run_backtest(px, sc.reindex(px.index), cm, cfg, rebalance="M").metrics.cagr


def main() -> None:
    panel, _, _ = load()
    cm, cfg = cost_model(), portfolio_config()
    real = strategy_score(panel, PERIOD)
    rank_rand = gate_only_score(panel, PERIOD, 1)

    print("=== decomposition, every window, mean over 10 seeds ===")
    print(f"{'window':<14}{'GATE+RANK':>11}{'gate worth':>12}{'rank worth':>12}"
          f"{'GATE+RRANK':>12}{'RGATE+RRANK':>13}")
    rows = []
    for name, a, b in SUBWINDOWS:
        px = window(panel, pd.Timestamp(a), pd.Timestamp(b))
        c_real = cagr(px, real, cm, cfg)
        c_rr = float(np.mean([cagr(px, rank_rand, cm, cfg) for _ in range(1)]))
        c_gr = float(np.mean([cagr(px, random_gate_score(panel, PERIOD, s), cm, cfg)
                              for s in range(N_SEEDS)]))
        gate_w = c_real - c_gr
        rank_w = c_real - c_rr
        rows.append({"window": name, "cagr": c_real, "gate_worth": gate_w,
                     "rank_worth": rank_w})
        print(f"{name:<14}{c_real * 100:>10.2f}%{gate_w * 100:>+11.2f}pp"
              f"{rank_w * 100:>+11.2f}pp{c_rr * 100:>11.2f}%{c_gr * 100:>12.2f}%")

    d = pd.DataFrame(rows)
    for col, lab in (("gate_worth", "GATE"), ("rank_worth", "RANKING")):
        pos = int((d[col] > 0).sum())
        print(f"{lab}: positive in {pos}/{len(d)} windows; "
              f"mean {d[col].mean() * 100:+.2f}pp, median {d[col].median() * 100:+.2f}pp, "
              f"best {d[col].max() * 100:+.2f}pp, worst {d[col].min() * 100:+.2f}pp")
    d.to_csv(HERE / "robustness_windows.csv", index=False)

    print("\n=== lookback ablation on TEST (selected variant unchanged) ===")
    px = window(panel, TEST_START, TEST_END)
    ptr = window(panel, TRAIN_START, TRAIN_END)
    print(f"{'period':>7}{'TRAIN Sharpe':>14}{'TEST CAGR':>12}{'TEST Sharpe':>13}"
          f"{'TEST MaxDD':>12}{'held%TEST':>11}")
    for p in (10, 20, 50, 100, 200):
        sc = strategy_score(panel, p)                       # full panel, then sliced
        rt = run_backtest(ptr, sc.reindex(ptr.index), cm, cfg, rebalance="M")
        rx = run_backtest(px, sc.reindex(px.index), cm, cfg, rebalance="M")
        held = float(np.nanmean(long_flag(panel, p).loc[px.index].to_numpy()))
        star = "  <- selected" if p == PERIOD else ""
        print(f"{p:>7}{rt.metrics.sharpe:>14.2f}{rx.metrics.cagr * 100:>11.2f}%"
              f"{rx.metrics.sharpe:>13.2f}{rx.metrics.max_drawdown * 100:>11.2f}%"
              f"{held * 100:>10.1f}%{star}")

    print("\n=== gate liveness through the whole history (period=200) ===")
    flag = long_flag(panel, PERIOD)
    per_year = flag.groupby(flag.index.year).apply(
        lambda g: float(np.nanmean(g.to_numpy()))
    )
    for y, v in per_year.items():
        print(f"  {y}: held {v * 100:>5.1f}% of (name,bar) cells")
    print(f"  ALL 2008-2026: held {np.nanmean(flag.to_numpy()) * 100:.1f}% of cells, "
          f"mean {flag.sum(axis=1).mean():.1f} names long per day")


if __name__ == "__main__":
    main()
