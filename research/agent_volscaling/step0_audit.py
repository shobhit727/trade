"""Step 0 — audit: data, source-signal verification, gate liveness, thresholds.

Everything here is computed on TRAIN unless explicitly labelled TEST. No backtest is
run in this script, so choosing `min_vol` from TRAIN percentiles cannot be accused of
fitting to an equity curve.
"""

from __future__ import annotations

import numpy as np
from harness import (
    ENGINE_SHA,
    RT_BPS,
    TEST_END,
    TEST_START,
    TRAIN_END,
    TRAIN_START,
    flag_panel,
    get_panel,
    natr,
    true_range,
    verify_source_signal,
)


def main() -> None:
    panel, symbols = get_panel()
    print("=" * 78)
    print("STEP 0 — AUDIT")
    print("=" * 78)
    print(f"engine_sha           : {ENGINE_SHA}")
    print(f"round_trip_bps (all-in): {RT_BPS:.2f}")
    print(f"panel                : {panel.shape}  {panel.index.min().date()} -> {panel.index.max().date()}")
    print(f"symbols              : {len(symbols)}")

    # ---- 1. does the vectorised flag equal the shipped class? ----
    print("\n--- source-signal verification (real VolScalingStrategy, synthetic bars) ---")
    for period, min_vol in ((14, 0.001), (14, 0.02), (5, 0.01), (20, 0.03)):
        m, t = verify_source_signal(n_bars=300, period=period, min_vol=min_vol)
        flag = "OK " if m == t else "FAIL"
        print(f"  [{flag}] period={period:<3d} min_vol={min_vol:<6.3f}  {m}/{t} bars match")

    # ---- 2. gate liveness: is `min_vol` reachable at all? ----
    tr = true_range()
    print("\n--- ATR(14)/close (NATR) distribution, by set ---")
    n = natr(14)
    for name, sl in (
        ("TRAIN", n.loc[TRAIN_START:TRAIN_END]),
        ("TEST ", n.loc[TEST_START:TEST_END]),
    ):
        v = sl.stack().dropna().values
        qs = np.percentile(v, [1, 5, 25, 50, 75, 95, 99])
        print(
            f"  {name}  n={len(v):>7d}  min={v.min() * 100:6.3f}%  p1={qs[0] * 100:6.3f}%  "
            f"p5={qs[1] * 100:6.3f}%  p25={qs[2] * 100:6.3f}%  **p50={qs[3] * 100:6.3f}%**  "
            f"p75={qs[4] * 100:6.3f}%  p95={qs[5] * 100:6.3f}%  max={v.max() * 100:6.3f}%"
        )

    print("\n--- GATE LIVENESS: fraction of name-days passing `NATR14 > min_vol` ---")
    trn = n.loc[TRAIN_START:TRAIN_END].stack()
    ten = n.loc[TEST_START:TEST_END].stack()
    print(f"  {'min_vol':>10}  {'TRAIN':>8}  {'TEST':>8}")
    for thr in (0.001, 0.005, 0.010, 0.015, 0.020, 0.025, 0.030, 0.035, 0.040, 0.050):
        a = float((trn > thr).mean()) * 100
        b = float((ten > thr).mean()) * 100
        note = ""
        if thr == 0.001:
            note = "   <-- SHIPPED DEFAULT"
        print(f"  {thr * 100:9.3f}%  {a:7.3f}%  {b:7.3f}%{note}")

    # ---- 3. signal liveness (fraction of name-days long) ----
    print("\n--- signal liveness: fraction of name-days flagged +1 ---")
    for label, kw in (
        ("shipped  min_vol=0.001, 1-bar dir", dict(min_vol=0.001, period=14, use_direction=True)),
        ("min_vol=0.001, gate only         ", dict(min_vol=0.001, period=14, use_direction=False)),
        ("min_vol=p50 gate only            ", dict(min_vol=float(trn.median()), period=14, use_direction=False)),
        ("min_vol=p50 + 1-bar dir          ", dict(min_vol=float(trn.median()), period=14, use_direction=True)),
        ("min_vol=p25 + 1-bar dir          ", dict(min_vol=float(trn.quantile(0.25)), period=14, use_direction=True)),
    ):
        f = flag_panel(**kw)
        a = float((f.loc[TRAIN_START:TRAIN_END] > 0).to_numpy().mean()) * 100
        b = float((f.loc[TEST_START:TEST_END] > 0).to_numpy().mean()) * 100
        print(f"  {label}  TRAIN {a:6.2f}%   TEST {b:6.2f}%")

    # ---- 4. the TRAIN thresholds V3/V4/V5 use ----
    print("\n--- TRAIN-derived thresholds (declared in the report) ---")
    print(f"  TRAIN p25 NATR14 = {float(trn.quantile(0.25)):.6f}")
    print(f"  TRAIN p50 NATR14 = {float(trn.median()):.6f}")
    print(f"  TEST  p50 NATR14 = {float(ten.median()):.6f}")

    # ---- 5. how much does the gate actually change the book? ----
    print("\n--- gate selectivity: distinct names held per rebalance date (mean) ---")
    for label, min_vol in (
        ("0.001 (shipped)", 0.001),
        ("p25", float(trn.quantile(0.25))),
        ("p50", float(trn.median())),
    ):
        for direction in (True, False):
            f = flag_panel(min_vol, period=14, use_direction=direction)
            cnt = (f > 0).sum(axis=1).loc[TRAIN_START:TRAIN_END]
            print(f"  min_vol={label:<15} direction={str(direction):<5}  mean flagged names/rebalance = {cnt.mean():5.1f}")

    print("\n--- true range sanity: is ATR an SMA of trailing TR (not Wilder)? ---")
    i = 100
    manual = tr.iloc[i - 13 : i + 1].mean(axis=0)
    got = tr.rolling(14, min_periods=14).mean().iloc[i]
    # Compare only where both are defined: NaN != NaN under np.isclose, and the
    # rolling(min_periods=14) legitimately stays NaN on names not yet listed.
    both = got.notna() & manual.notna()
    eq = np.isclose(got[both].to_numpy(), manual[both].to_numpy())
    print(f"  bar {i}: rolling(14).mean() == manual mean of the same 14 TRs on {eq.sum()}/{both.sum()} listed symbols")
    print(f"  TR>0 on {(tr > 0).to_numpy().mean() * 100:.2f}% of all name-days")
    print(f"  true_range shape {tr.shape} (expect 4625 x 48)")


if __name__ == "__main__":
    main()
