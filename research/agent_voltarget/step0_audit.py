"""Step 0 — data audit + mechanical verification of the source signal.

Runs before anything else: confirms the panel, the cost figure the engine will
charge, the ATR regime levels the strategy actually sees on NSE, and asserts that
`VolTargetStrategy.signal` is the two-part flag described in REPORT.md section 0.

Nothing here looks at TEST performance.
"""

from __future__ import annotations

import sys

import numpy as np

sys.path.insert(0, "research/agent_voltarget")

from harness import (  # noqa: E402
    DESCRIPTIONS,
    RT_BPS,
    TEST_END,
    TEST_START,
    TRAIN_END,
    TRAIN_START,
    VARIANTS,
    assert_engine_pinned,
    load_panel,  # noqa: E402
    natr,
    source_flag,
    verify_source_signal,
)


def main() -> None:
    assert_engine_pinned()
    panel, symbols = load_panel()
    print("=" * 78)
    print("STEP 0 — AUDIT")
    print("=" * 78)
    print(f"symbols          : {len(symbols)}")
    print(f"index            : {panel.index[0].date()} -> {panel.index[-1].date()}")
    print(f"bars             : {len(panel)}")
    print(f"all-in RT bps    : {RT_BPS:.2f}  (engine charges this, net of everything)")
    print()
    print("declared parameter budget (5 variants, TRAIN-only selection):")
    for v in VARIANTS:
        print(f"  {v:<22}{DESCRIPTIONS[v]}")
    print()

    n = natr(panel, 14)
    print("NATR(14) = ATR/close, the exact quantity the strategy thresholds")
    for label, sub in [
        ("full", n),
        ("TRAIN", n.loc[TRAIN_START:TRAIN_END]),
        ("TEST", n.loc[TEST_START:TEST_END]),
    ]:
        q = sub.to_numpy().ravel()
        q = q[np.isfinite(q)]
        print(
            f"  {label:<6} mean {np.nanmean(q) * 100:6.3f}%  "
            f"p10 {np.nanpercentile(q, 10) * 100:6.3f}%  "
            f"p50 {np.nanpercentile(q, 50) * 100:6.3f}%  "
            f"p90 {np.nanpercentile(q, 90) * 100:6.3f}%"
        )
    print()
    print("fraction of name-days satisfying each half of the flag:")
    for label, sl in [("TRAIN", slice(TRAIN_START, TRAIN_END)),
                      ("TEST", slice(TEST_START, TEST_END))]:
        p = panel.loc[sl]
        d = (p > p.shift(1))
        for thresh in (0.02, 0.03):
            calm = natr(p, 14) < thresh
            both = (d & calm)
            print(
                f"  {label:<6} NATR<{thresh * 100:.0f}%: calm {calm.to_numpy().mean() * 100:5.1f}%"
                f"  up-day {d.to_numpy().mean() * 100:5.1f}%"
                f"  BOTH {both.to_numpy().mean() * 100:5.1f}%"
            )
    print()

    flag = source_flag(panel)
    fl_tr = flag.loc[TRAIN_START:TRAIN_END].to_numpy().ravel()
    fl_te = flag.loc[TEST_START:TEST_END].to_numpy().ravel()
    print(f"flag active  TRAIN {np.nanmean(fl_tr) * 100:.2f}%  "
          f"TEST {np.nanmean(fl_te) * 100:.2f}%  of name-days")
    live = flag.sum(axis=1) > 0
    print(f"bars with >=1 eligible name: TRAIN {live.loc[TRAIN_START:TRAIN_END].mean() * 100:.1f}%  "
          f"TEST {live.loc[TEST_START:TEST_END].mean() * 100:.1f}%")
    print(f"median eligible names on a live bar: {flag.sum(axis=1).median():.0f}")
    print()

    print("=" * 78)
    print("SOURCE-SIGNAL VERIFICATION (synthetic, mechanical)")
    print("=" * 78)
    for k, v in verify_source_signal().items():
        print(f"  {k:<28}{v}")


if __name__ == "__main__":
    main()
