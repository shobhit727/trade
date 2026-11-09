"""Step 1 — mandatory load_universe + signal diagnostics. No backtest here."""

from __future__ import annotations

import common as C
import pandas as pd

panel, symbols, report = C.load_all()
C.align(panel)

print("=" * 78)
print("CLEANING REPORT")
print("=" * 78)
print(report.describe())
print()
print("symbols retained :", len(symbols))
print("panel shape      :", panel.shape)
print("index            :", panel.index.min(), "->", panel.index.max())
print("index dtype/tz   :", panel.index.dtype, getattr(panel.index, "tz", None))
print("bars             :", len(panel.index))
print()

# Window checks mandated by the brief.
for name, lo, hi in (
    ("TRAIN", C.TRAIN_START, C.TRAIN_END),
    ("TEST", C.TEST_START, C.TEST_END),
):
    sub = panel.loc[lo:hi]
    print(
        f"{name:<6} {lo.date()} -> {hi.date()}  "
        f"bars={len(sub):>5}  symbols={sub.notna().any(axis=0).sum():>3}  "
        f"date range actual {sub.index.min().date()} -> {sub.index.max().date()}"
    )
print()

# --- Signal diagnostics, per variant. TRAIN vs TEST. No backtest. -----------
print("=" * 78)
print("SIGNAL DIAGNOSTICS  (gap = close[t]/close[t-L]-1 ; flag = gap > threshold)")
print("=" * 78)
print(
    f"  {'ID':<4}{'L':>4}{'thr':>8}   {'TRAIN %flag':>12}{'TEST %flag':>12}"
    f"{'TRAIN n/day':>12}{'TEST n/day':>12}{'nan-safe':>10}"
)
rows = []
for vid, spec in C.VARIANTS.items():
    flag = C.gap_flag(panel, spec["L"], spec["threshold"])
    tr_frac, tr_n = C.liveness(flag, C.TRAIN_START, C.TRAIN_END)
    te_frac, te_n = C.liveness(flag, C.TEST_START, C.TEST_END)
    # "nan-safe": fraction of flagged bars whose momentum key also exists, i.e.
    # the fraction that can actually reach the book rather than being NaN-dropped.
    key = C.momentum(panel)
    joint = (flag & key.notna())
    frac_joint = float(joint.sum().sum()) / float(flag.sum().sum())
    print(
        f"  {vid:<4}{spec['L']:>4}{spec['threshold']:>8.3f}   "
        f"{tr_frac * 100:>11.2f}%{te_frac * 100:>11.2f}%"
        f"{tr_n:>12.1f}{te_n:>12.1f}{frac_joint * 100:>9.1f}%"
    )
    rows.append(
        {
            "id": vid,
            "L": spec["L"],
            "threshold": spec["threshold"],
            "train_frac": tr_frac,
            "test_frac": te_frac,
            "train_names": tr_n,
            "test_names": te_n,
            "momentum_ok": frac_joint,
        }
    )

# --- The degeneracy check: is the raw signal usable as a cross-sectional score?
print()
print("=" * 78)
print("TIE DEGENERACY CHECK — why the raw +1/-1 signal cannot be the score")
print("=" * 78)
raw = C.gap_flag(panel, 1, 0.0).astype(float)
for lo, hi, nm in (
    (C.TRAIN_START, C.TRAIN_END, "TRAIN"),
    (C.TEST_START, C.TEST_END, "TEST"),
):
    r = raw.loc[lo:hi]
    n_tied_top = (r == 1.0).sum(axis=1)
    print(
        f"  {nm}: names tied at +1.0 per day -> mean {n_tied_top.mean():.1f}, "
        f"min {n_tied_top.min()}, max {n_tied_top.max()}  "
        f"(book wants 22; ties would be broken ALPHABETICALLY by the stable sort)"
    )
print()
print("  -> hence flag-as-mask + momentum rank. This is the brief's §5 construction.")

pd.DataFrame(rows).to_csv("signal_diagnostics.csv", index=False)
print()
print("wrote signal_diagnostics.csv")
