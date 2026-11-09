"""Step 1 — data audit + signal liveness on TRAIN. No TEST numbers here.

Run: .venv/bin/python research/agent_anchored_vwap/01_liveness.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from common import (
    TEST,
    TRAIN,
    VARIANTS,
    deviation,
    eligible,
    load,
)

pd.set_option("display.width", 200)


def main() -> None:
    u = load()
    print(u.report.describe())
    print(
        f"\nUniverse: {len(u.symbols)} symbols | "
        f"{u.close.index[0].date()} -> {u.close.index[-1].date()} | {len(u.close)} bars"
    )
    print(f"volume: zeros={int((u.volume.fillna(0) == 0).sum().sum())}  "
          f"NaN rows={int(u.volume.isna().all(axis=1).sum())}")

    tr = slice(*TRAIN)
    print(f"\nTRAIN {TRAIN[0].date()} -> {TRAIN[1].date()}: "
          f"{int((u.close.index >= TRAIN[0]).sum())} bars")
    print(f"TEST  {TEST[0].date()} -> {TEST[1].date()}  (untouched this step)")

    print("\n" + "=" * 78)
    print("SIGNAL LIVENESS (TRAIN only)")
    print("=" * 78)
    print(f"{'variant':<22} {'period':>6} {'thresh':>7} {'kind':>5} "
          f"{'name-days':>10} {'%name-days':>10} {'avg/day':>8} "
          f"{'reb-dates':>9} {'avg_elig@reb':>12}")

    for v in VARIANTS:
        dev = deviation(u.close, v.period)
        mask = eligible(dev, v.threshold)
        sel = u.close.loc[tr].index
        md = mask.loc[tr]
        frac = float(md.values.mean())
        # eligible count on the dates the engine actually rebalances on
        from common import rebalance_dates

        rb = rebalance_dates(u.close.index)
        rb = [d for d in rb if d in md.index][1:]
        elig_rb = [int(md.loc[d].sum()) for d in rb]
        print(
            f"{v.name:<22} {v.period:>6} {v.threshold:>7.2f} {v.score_kind:>5} "
            f"{int(md.values.sum()):>10,} {frac * 100:>9.1f}% "
            f"{float(md.values.sum() / len(sel)):>8.2f} "
            f"{len(rb):>9} {np.mean(elig_rb):>12.1f}"
        )

    print("\nInterpretation: 'name-days long' counts name x day. The book wants ~22")
    print("names on a rebalance date; if avg_elig@reb < 22 the book is structurally")
    print("under-invested and sits in cash that much of the time.")

    # Sanity: does the deviation look like a real VWAP, not a constant?
    dev50 = deviation(u.close, 50).loc[tr]
    print("\ndev(period=50) TRAIN distribution:")
    print(dev50.stack().describe(percentiles=[0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99])
          .to_string(float_format=lambda v: f"{v * 100:>8.2f}%"))
    print(f"\nfinite fraction: {float(np.isfinite(dev50.values).mean()) * 100:.1f}%")

    # Sanity: a VWAP with zero volume weighting would equal an SMA. Show they differ.
    vw = deviation(u.close, 50).loc[tr]
    sma = u.close.loc[tr].rolling(50).mean()
    dev_sma = (u.close.loc[tr] / sma - 1.0)
    print(f"\nvol-weighted VWAP vs plain 50d SMA deviation, TRAIN mean abs diff = "
          f"{float((vw - dev_sma).abs().stack().mean()) * 100:.3f} pp "
          f"(must be > 0 — volume weighting must actually do something)")


if __name__ == "__main__":
    main()
