"""Step 00 — data check. TRAIN window only. No TEST inspection."""

from __future__ import annotations

import numpy as np
import pandas as pd
from common import (
    ENGINE_SHA,
    TRAIN_END,
    TRAIN_START,
    liveness,
    load_panel,
    mean_names_flagged,
    ts_zscore,
)

pd.set_option("display.width", 200)


def main() -> None:
    panel, symbols, txt = load_panel()
    print("=" * 78)
    print("CLEANING REPORT (nsealgo.data.loader)")
    print("=" * 78)
    print(txt)

    print("=" * 78)
    print("PANEL")
    print("=" * 78)
    print(f"symbols            : {len(symbols)}")
    print(f"rows               : {len(panel):,}")
    print(f"span               : {panel.index[0].date()} -> {panel.index[-1].date()}")
    print(f"NaN fraction       : {panel.isna().to_numpy().mean():.6f}")
    print(f"NaN cells total    : {int(panel.isna().to_numpy().sum()):,}")
    # per-name NaN, worst offenders
    per = panel.isna().sum().sort_values(ascending=False)
    print(f"worst 5 NaN names  : {dict(per.head(5))}")
    print(f"engine_sha         : {ENGINE_SHA}")

    tr = panel.loc[(panel.index >= TRAIN_START) & (panel.index <= TRAIN_END)]
    print()
    print("=" * 78)
    print("TRAIN WINDOW ONLY  (TEST deliberately not inspected here)")
    print("=" * 78)
    print(f"TRAIN span         : {tr.index[0].date()} -> {tr.index[-1].date()}")
    print(f"TRAIN rows         : {len(tr):,}   symbols: {tr.shape[1]}")
    print(f"TRAIN NaN frac     : {tr.isna().to_numpy().mean():.6f}")

    print()
    print("=" * 78)
    print("SIGNAL DIAGNOSTICS — TRAIN only")
    print("=" * 78)
    print(
        f"{'L':>5} {'entry':>6} {'live%':>7} {'mean#flag':>10} {'p5 z':>7} "
        f"{'p50 z':>7} {'p95 z':>7} {'z<=-0.8':>8}"
    )
    for L in (20, 60, 300):
        z = ts_zscore(tr, L)
        zv = z.stack().dropna()
        for entry in (0.5, 0.8, 1.2):
            print(
                f"{L:>5} {entry:>6.1f} {liveness(tr, L, entry) * 100:>6.2f}% "
                f"{mean_names_flagged(tr, L, entry):>10.2f} "
                f"{np.percentile(zv, 5):>7.2f} {np.percentile(zv, 50):>7.2f} "
                f"{np.percentile(zv, 95):>7.2f} "
                f"{float((z <= -0.8).to_numpy().mean()) * 100:>7.2f}%"
            )

    # How many names are flagged *per day* — determines whether the book can even
    # reach 22 positions, and therefore how much cash drag is structural.
    print()
    print("per-day flagged-name count (TRAIN), lookback=60 entry=0.8:")
    z60 = ts_zscore(tr, 60)
    cnt = (z60 <= -0.8).sum(axis=1)
    print(
        f"  min {int(cnt.min())}  p10 {cnt.quantile(0.10):.0f}  "
        f"median {cnt.median():.0f}  p90 {cnt.quantile(0.90):.0f}  "
        f"max {int(cnt.max())}  mean {cnt.mean():.1f}"
    )
    print(f"  days with >=22 flagged : {float((cnt >= 22).mean()) * 100:.1f}%")
    print(f"  days with 0 flagged    : {float((cnt == 0).mean()) * 100:.1f}%")

    # Cross-sectional z-score alternative, for reference only (not a variant).
    xs = tr.pct_change(fill_method=None).rolling(60, min_periods=20).sum()
    xs_z = (xs - xs.mean(axis=1)) / xs.std(axis=1, ddof=0)
    print()
    print("reference: fraction of days where the *market median* name is below its own "
          "0.8 sigma floor (i.e. how often the whole board is oversold):")
    frac_below = (tr.pct_change(fill_method=None).rolling(20, min_periods=10).mean()
                  < 0).mean(axis=1)
    print(f"  median fraction of names with a negative 20d return: {frac_below.median():.2f}")
    del xs_z


if __name__ == "__main__":
    main()
