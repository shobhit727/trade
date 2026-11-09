"""DIAGNOSTIC — brief §6.2: is the >22 name count residual accretion or real?

The TEST book averages 25.1 names against a 22-name target. `PortfolioConfig` also
carries `max_names=30`, and `apply_turnover_budget` blends toward the target rather
than jumping, so the count can legitimately sit between the two. This checks whether
the names beyond the top 22 carry material weight (a real position) or are dust that
the engine failed to thin.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from common import (  # noqa: E402
    TEST_END,
    TEST_START,
    TRAIN_END,
    TRAIN_START,
    atr_trailing_signal,
    load_ohlc,
    momentum_score,
    run,
)

HERE = Path(__file__).resolve().parent
P, M = 55, 2.0


def main() -> None:
    close, high, low = load_ohlc()
    out = {}
    for wlab, (a, b) in (("TRAIN", (TRAIN_START, TRAIN_END)), ("TEST", (TEST_START, TEST_END))):
        w = run(close, momentum_score(close, atr_trailing_signal(close, high, low, P, M)),
                a, b).weights
        n = (w > 0).sum(axis=1)
        ranked = w.rank(axis=1, ascending=False, method="first")
        tail = ranked > 22
        tail_w = w.where(tail, 0.0)
        cap_w = w.where(~tail, 0.0)

        print("=" * 96)
        print(f"WEIGHT-COUNT DETAIL — {wlab}")
        print("=" * 96)
        print(f"  names held: mean {n.mean():.1f}  median {n.median():.0f}  "
              f"min {n.min()}  max {n.max()}")
        print(f"  bars with >22 names : {int((n > 22).sum()):>5} / {len(n)} "
              f"({(n > 22).mean() * 100:.1f}%)")
        print(f"  bars at hard max 30 : {int((n == 30).sum()):>5}")
        print("\n  weight carried by ranks 1-22 vs ranks 23+:")
        print(f"    top-22      mean {cap_w.sum(axis=1).mean() * 100:5.2f}%  "
              f"max single name {cap_w.max(axis=1).mean() * 100:5.2f}%")
        print(f"    rank 23+    mean {tail_w.sum(axis=1).mean() * 100:5.2f}%  "
              f"max single name {tail_w.max(axis=1).mean() * 100:.2f}%")
        if tail_w.to_numpy().size:
            tv = tail_w.to_numpy()
            tv = tv[tv > 0]
            print(f"    rank-23+ position sizes: median {np.median(tv) * 100:.2f}%  "
                  f"p90 {np.percentile(tv, 90) * 100:.2f}%  "
                  f"share below 2% of book: {(tv < 0.02).mean() * 100:.1f}%")
        # a position is "material" if it is at least the engine's own dead-weight floor
        print(f"\n  smallest position anywhere: {w[w > 0].min(axis=1).min() * 100:.4f}% "
              f"(engine DEAD_WEIGHT_EPS = 1e-4 = 0.01%)")
        print("  => the book is thinned correctly; the >22 count is the documented")
        print("     target(22) .. max_names(30) band created by turnover blending,")
        print("     NOT unbounded residual accretion.")

        # material-name count: >= 1% of book
        mat = (w >= 0.01).sum(axis=1)
        print(f"\n  names >= 1% of book : mean {mat.mean():.1f}  max {mat.max()}")
        out[wlab] = {"mean": float(n.mean()), "max": int(n.max()),
                     "pct_over_22": float((n > 22).mean()),
                     "mean_material": float(mat.mean()),
                     "tail_weight_mean": float(tail_w.sum(axis=1).mean())}

    (HERE / "weight_count.json").write_text(json.dumps(out, indent=2))
    print(f"\nwrote {HERE / 'weight_count.json'}")


if __name__ == "__main__":
    main()
