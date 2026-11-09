"""STEP 4 — ROBUSTNESS of the negative finding.

step3 showed the absolute-momentum GATE contributes -0.44 pp/yr on TEST and -0.38
pp/yr on TRAIN. Before publishing "the gate is dead", check it is not an artefact of
one window:

  1. Is the gate contribution negative across many sub-windows?
  2. Is it negative for other lookbacks too (diagnostic, not parameter selection)?
  3. Does the full-history result agree?
  4. Random-control spread, to size the noise floor the -0.44pp must beat.

No variant here is a candidate for selection. The selected variant is unchanged.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness import (  # noqa: E402
    VARIANTS,
    cost_model,
    load,
    portfolio_config,
    roc_panel,
    run_backtest,
    window,
)

OUT = Path(__file__).resolve().parent


def main() -> None:
    panel, symbols, _ = load()
    selected = (OUT / "selected_variant.txt").read_text().strip()
    v = next(x for x in VARIANTS if x.name == selected)
    cost, cfg = cost_model(), portfolio_config()

    def cagr_over(px, period, threshold, gated):
        r = roc_panel(panel, period)
        s = (r.where(r > threshold) if gated else r).rank(axis=1, pct=True)
        return run_backtest(px, s.reindex(px.index), cost, cfg, rebalance="M").metrics

    # ---- 1. sub-windows ---------------------------------------------------
    print("=" * 88)
    print("1. GATE CONTRIBUTION BY SUB-WINDOW (period=252, selected period)")
    print("=" * 88)
    spans = [
        ("2009-2013", "2009-01-01", "2013-12-31"),
        ("2014-2018", "2014-01-01", "2018-12-31"),
        ("2019-2021", "2019-01-01", "2021-12-31"),
        ("2022-2023", "2022-01-01", "2023-12-31"),
        ("TRAIN all", "2016-01-01", "2023-12-31"),
        ("TEST 2024-26", "2024-01-01", "2026-10-01"),
        ("full 2008-26", "2008-01-01", "2026-10-01"),
    ]
    deltas = []
    print(f"{'window':<15} {'gate+rank':>11} {'rank only':>11} {'gate worth':>12}")
    for label, s, e in spans:
        px = window(panel, pd.Timestamp(s), pd.Timestamp(e))
        g = cagr_over(px, v.period, v.threshold, True).cagr
        n = cagr_over(px, v.period, v.threshold, False).cagr
        deltas.append((g - n) * 100)
        print(f"{label:<15} {g * 100:>10.2f}% {n * 100:>10.2f}% {(g - n) * 100:>+11.2f}pp")
    neg = sum(1 for d in deltas if d < 0)
    print(f"\n  gate is NEGATIVE in {neg}/{len(deltas)} windows, "
          f"mean {np.mean(deltas):+.2f}pp, median {np.median(deltas):+.2f}pp")

    # ---- 2. other lookbacks ----------------------------------------------
    print(f"\n{'=' * 88}")
    print("2. GATE CONTRIBUTION BY LOOKBACK, TRAIN and TEST separately")
    print("=" * 88)
    print(f"{'period':>7} | {'TRAIN gate+rank':>15} {'TRAIN rank':>11} {'gate':>8} "
          f"| {'TEST gate+rank':>15} {'TEST rank':>11} {'gate':>8}")
    tr = window(panel, pd.Timestamp("2016-01-01"), pd.Timestamp("2023-12-31"))
    te = window(panel, pd.Timestamp("2024-01-01"), pd.Timestamp("2026-10-01"))
    for p in (30, 63, 126, 252, 504):
        gt, nt = cagr_over(tr, p, 0.0, True), cagr_over(tr, p, 0.0, False)
        ge, ne = cagr_over(te, p, 0.0, True), cagr_over(te, p, 0.0, False)
        print(f"{p:>7} | {gt.cagr * 100:>14.2f}% {nt.cagr * 100:>10.2f}% "
              f"{(gt.cagr - nt.cagr) * 100:>+7.2f}pp "
              f"| {ge.cagr * 100:>14.2f}% {ne.cagr * 100:>10.2f}% "
              f"{(ge.cagr - ne.cagr) * 100:>+7.2f}pp")

    # ---- 3. noise floor ---------------------------------------------------
    print(f"\n{'=' * 88}")
    print("3. NOISE FLOOR — random-rank gate books, TEST (how big is a spurious effect?)")
    print("=" * 88)
    te_roc = roc_panel(panel, v.period)
    te_gate = te_roc.where(te_roc > 0.0)
    rng = np.random.default_rng(7)
    cands = []
    for _s in range(40):
        noise = pd.DataFrame(rng.random(te_gate.shape), index=te_gate.index,
                             columns=te_gate.columns)
        sc = noise.where(te_gate.notna()).rank(axis=1, pct=True).reindex(te.index)
        cands.append(run_backtest(te, sc, cost, cfg, rebalance="M").metrics.cagr * 100)
    real = cagr_over(te, v.period, v.threshold, True).cagr * 100
    rank_only = cagr_over(te, v.period, v.threshold, False).cagr * 100
    print(f"  gate + random rank : mean {np.mean(cands):.2f}%  "
          f"sd {np.std(cands):.2f}  range [{min(cands):.2f}, {max(cands):.2f}]")
    print(f"  gate + real rank   : {real:.2f}%  (top {sum(1 for c in cands if c > real)}/40)")
    print(f"  rank, no gate      : {rank_only:.2f}%  (top {sum(1 for c in cands if c > rank_only)}/40)")
    print(f"\n  => the ranking, not the gate, is what beats a coin flip. The gate's "
          f"{real - rank_only:+.2f}pp effect is "
          f"{'smaller' if abs(real - rank_only) < np.std(cands) else 'larger'} "
          f"than one seed's sd ({np.std(cands):.2f}pp).")


if __name__ == "__main__":
    main()
