"""Lookahead audit for the cointegration score panel.

Two independent checks, because a score that peeks is the single most common way a
result of this shape turns out to be fiction.

A. **Truncation test.** Recompute the score on a panel cut at date *T* and compare to
   the score from the full panel up to *T*. If they are identical, ``score[t]`` uses no
   data after *t*. Any lookahead shows up as a mismatch.

B. **Shuffle test.** Scramble the *order* of symbols in the panel (a pure relabelling,
   no value is changed). Every per-symbol statistic — which is all the z-score is — must
   be invariant under relabelling. A violation would mean the score is reading
   cross-sectional information, i.e. today's peer group.

C. **Lag test.** The engine holds weights from *t+1*. Confirm the score genuinely has
   fresh information at *t* (i.e. it is not constant), which is what makes the one-bar
   lag meaningful.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from coinlib import TRAIN_END, TRAIN_START, build_score, panel, zscore_panel  # noqa: E402

W, ENTRY = 126, 1.0


def main() -> None:
    px = panel().loc[(panel().index >= TRAIN_START) & (panel().index <= TRAIN_END)]
    rng = np.random.default_rng(0)
    cuts = sorted(rng.choice(np.arange(W + 5, len(px)), size=4, replace=False))

    full = build_score(px, W, ENTRY)
    print("A. TRUNCATION TEST — score[:T] from full panel vs score recomputed on px[:T]")
    ok = True
    for T in cuts:
        T = int(T)
        d = px.index[T]
        a = full.loc[:d]
        b = build_score(px.loc[:d], W, ENTRY)
        diff = (a - b).abs().stack().to_numpy()
        diff = diff[~np.isnan(diff)]
        mx = float(diff.max()) if diff.size else 0.0
        n_nan_mismatch = int((a.isna() != b.isna()).to_numpy().sum())
        ok &= mx == 0.0 and n_nan_mismatch == 0
        print(f"   cut {d.date()}: max |diff| {mx:.3e}  "
              f"NaN-pattern mismatches {n_nan_mismatch}")

    print("\nB. RELABELLING TEST — permute columns, score must be invariant")
    perm = list(rng.permutation(px.columns))
    p2 = px[perm]
    s1, s2 = build_score(px, W, ENTRY), build_score(p2, W, ENTRY)
    # Each column's statistic is computed independently, so permuting the columns and
    # permuting them back is the inverse. No rename: labels already ride with the data.
    inv = s2.reindex(columns=px.columns)
    cols = list(px.columns)
    d = (s1[cols] - inv[cols]).abs().stack().to_numpy()
    d = d[~np.isnan(d)]
    mx = float(d.max()) if d.size else 0.0
    print(f"   max |diff| {mx:.3e}")
    ok &= mx == 0.0

    print("\nC. SCORE IS LIVE (a constant score would make the lag vacuous)")
    live = full.notna()
    chg = (full.diff().abs().sum(axis=1) > 0).mean()
    print(f"   live cells {live.to_numpy().mean() * 100:.2f}%   "
          f"bars where the score set changed {chg * 100:.1f}%")

    print("\nD. Z-SCORE SANITY vs catalog formula")
    z = zscore_panel(px, W)
    row = z.iloc[W + 10].dropna()
    sub = px.iloc[W + 10 - W + 1: W + 11]
    ref = (sub - sub.mean()) / sub.std(ddof=0)
    j = row.index[3]
    ours, want = float(z.loc[z.index[W + 10], j]), float(ref.loc[sub.index[-1], j])
    print(f"   {j}: ours {ours:.10f}  catalog-formula {want:.10f}")
    ok &= abs(ours - want) < 1e-9

    print(f"\nLOOKAHEAD AUDIT: {'PASS' if ok else 'FAIL'}")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
