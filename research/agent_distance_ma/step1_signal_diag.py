"""Step 1: signal diagnostics on TRAIN only. No TEST data touched here.

Answers brief §6.3 (signal liveness) and §6.5 material for the negative control:
what fraction of name-days is each declared variant long, and how wide is the
cross-sectional spread of its score when it fires.
"""

from __future__ import annotations

import numpy as np
from common import (
    BUILDERS,
    TRAIN_END,
    TRAIN_START,
    deviation_panel,
    load_panel,
)

VARIANTS = [
    ("V1 dev_depth p20 t0.03", "dev_depth", 20, 0.03),
    ("V2 dev_depth p20 t0.05", "dev_depth", 20, 0.05),
    ("V3 dev_depth p50 t0.05", "dev_depth", 50, 0.05),
    ("V4 dev_depth p100 t0.08", "dev_depth", 100, 0.08),
    ("V5 mom_ranked p20 t0.03", "mom_ranked", 20, 0.03),
]


def main() -> None:
    panel, symbols, _ = load_panel()
    train = panel.loc[(panel.index >= TRAIN_START) & (panel.index <= TRAIN_END)]
    print(f"TRAIN bars {len(train)}  ({TRAIN_START.date()} .. {TRAIN_END.date()})")
    print(f"symbols    {len(symbols)}\n")

    hdr = (f"{'variant':<24}{'name-days long':>14}{'bars w/ >=1':>13}"
           f"{'bars w/ >=22':>14}{'median names':>13}{'spread':>9}")
    print(hdr)
    print("-" * len(hdr))

    for label, con, period, thr in VARIANTS:
        dev = deviation_panel(train, period)
        fire = dev < -abs(thr)
        names_long = fire.sum(axis=1)
        score = BUILDERS[con](train, period, thr)

        # Cross-sectional spread of the score on bars where the gate fires.
        spread = score.max(axis=1) - score.min(axis=1)
        sp = spread[names_long > 0].median()

        print(f"{label:<24}{fire.values.mean() * 100:>13.2f}%"
              f"{int((names_long >= 1).sum()):>13}"
              f"{int((names_long >= 22).sum()):>14}"
              f"{names_long[names_long > 0].median():>13.0f}"
              f"{sp:>9.3f}")

    print("\n--- what the gate actually looks like, defaults V1 (20, 0.03) ---")
    dev = deviation_panel(train, 20)
    d = dev.stack()
    print(f"  dev distribution:  p01 {d.quantile(0.01):+.3f}  p05 {d.quantile(0.05):+.3f}"
          f"  p50 {d.quantile(0.50):+.3f}  p95 {d.quantile(0.95):+.3f}"
          f"  p99 {d.quantile(0.99):+.3f}")
    print(f"  |dev| < 3% of the time: {(d.abs() < 0.03).mean() * 100:.1f}% of name-days"
          "   <- the strategy is FLAT most of the time")
    fire = dev < -0.03
    print(f"  long leg fires on      : {fire.values.mean() * 100:.1f}% of name-days")
    print(f"  short leg fires on     : {(dev > 0.03).values.mean() * 100:.1f}%"
          "   <- discarded, not tradable in delivery")

    # How persistent is a signal? Average run length of the long leg per name.
    print("\n--- signal persistence (V1 long leg), average consecutive bars long ---")
    runs = []
    for c in fire.columns:
        f = fire[c].to_numpy()
        cur = 0
        for v in f:
            if v:
                cur += 1
            elif cur:
                runs.append(cur)
                cur = 0
        if cur:
            runs.append(cur)
    r = np.array(runs)
    print(f"  {len(r):,} episodes, mean {r.mean():.1f} bars, median {np.median(r):.0f}, "
          f"p90 {np.percentile(r, 90):.0f}, max {r.max()}")

    # Is the signalled set a *market-wide* event or idiosyncratic? That decides
    # whether a cross-sectional book can even be built.
    n_long = fire.sum(axis=1)
    print(f"\n  bars with 0 names long   : {int((n_long == 0).sum()):>4}"
          f" ({ (n_long == 0).mean() * 100:.1f}%)  <- book forced to cash")
    print(f"  bars with 1-5 names long : {int(n_long.between(1, 5).sum()):>4}")
    print(f"  bars with >=22 names long: {int((n_long >= 22).sum()):>4}")


if __name__ == "__main__":
    main()
