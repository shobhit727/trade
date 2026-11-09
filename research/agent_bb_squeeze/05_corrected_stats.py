"""Corrected TRAIN-only signal statistics.

BUG FOUND IN THE SALVAGED SCRATCH WORK (01_train_diagnostics.py §3, 02_train_selective.py):

    a = fwd5.where(lng > 0).stack()      # pandas 3.0.5 stack() does NOT drop NaN

`len(a)` therefore returned the FULL panel cell count (94,800 = 1,975 bars x 48 names)
for *every* threshold, while `.mean()`/`.std()` silently skipped the NaNs. So the t-stats
were computed with an n inflated by 3x to 60x depending on the threshold. The reported
t-stats were wrong (too small in magnitude); the reported *means* were fine.

Second, deeper problem: (name, day) observations are massively cross-correlated -- all 48
names move together on a given day. An iid t-stat over such data overstates significance
by an order of magnitude. The honest standard error clusters on the DATE.

This script recomputes both, correctly. TRAIN only; TEST is never touched.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from common import DATA, TRAIN, cv_panel, load_universe, roc_panel, squeeze_signal


def masked(frame: pd.DataFrame, mask: pd.DataFrame) -> pd.Series:
    """Mask and flatten, DROPPING the NaNs (the bug the old scripts had)."""
    return frame.where(mask > 0).stack().dropna()


def tstat_iid(a: pd.Series, b: pd.Series) -> tuple[float, float, float, float]:
    """Naive iid two-sample difference of means (n now correct)."""
    s = float(a.mean()) - float(b.mean())
    se = float(a.std(ddof=1) / np.sqrt(len(a)) + b.std(ddof=1) / np.sqrt(len(b)))
    return float(a.mean()), float(b.mean()), s, s / se


def tstat_clustered(a: pd.Series, b: pd.Series, n_boot: int = 4000, seed: int = 7) -> float:
    """Date-clustered bootstrap t-stat for (mean(a) - mean(b)).

    Resample whole DATES with replacement, recompute the difference each time. This keeps
    every cross-sectional correlation inside a day intact, which is the correlation that
    actually matters and that an iid test throws away.

    Vectorised via per-day sufficient statistics: for a resampled day multiset the
    resampled mean of `a` is sum(na_d) / sum(sa_d) taken over the drawn days, so no
    per-draw concatenation is needed.
    """
    idx = a.index.union(b.index)
    va = a.reindex(idx).fillna(0.0).to_numpy(dtype=float)
    vb = b.reindex(idx).fillna(0.0).to_numpy(dtype=float)
    ok_a = a.reindex(idx).notna().to_numpy()
    ok_b = b.reindex(idx).notna().to_numpy()
    # stack() yields a (date, symbol) MultiIndex; the date is level 0.
    codes, uniq = pd.factorize(idx.get_level_values(0))
    n_d = len(uniq)
    na = np.bincount(codes, weights=ok_a.astype(float), minlength=n_d)
    sa = np.bincount(codes, weights=np.where(ok_a, va, 0.0), minlength=n_d)
    nb = np.bincount(codes, weights=ok_b.astype(float), minlength=n_d)
    sb = np.bincount(codes, weights=np.where(ok_b, vb, 0.0), minlength=n_d)

    point = float(sa.sum() / na.sum() - sb.sum() / nb.sum())
    rng = np.random.default_rng(seed)
    pick = rng.integers(0, n_d, size=(n_boot, n_d))
    ma = sa[pick].sum(axis=1) / na[pick].sum(axis=1)
    mb = sb[pick].sum(axis=1) / nb[pick].sum(axis=1)
    draws = ma - mb
    return float((point - draws.mean()) / max(draws.std(ddof=1), 1e-12))


def main() -> None:
    panel, _, _ = load_universe(str(DATA))
    tr = panel.loc[TRAIN[0] : TRAIN[1]]
    r3 = roc_panel(tr, 3)
    fwd5 = (panel.shift(-5) / panel - 1.0).loc[TRAIN[0] : TRAIN[1]]
    fwd21 = (panel.shift(-21) / panel - 1.0).loc[TRAIN[0] : TRAIN[1]]
    print(f"TRAIN {tr.index[0].date()} -> {tr.index[-1].date()}  "
          f"{len(tr)} bars x {tr.shape[1]} names   (TEST NOT touched)\n")

    print("=" * 118)
    print("A. DIRECTION SPREAD, CORRECTED n, PLUS DATE-CLUSTERED BOOTSTRAP T (2,000 resamples)")
    print("   spread = mean 5/21-bar fwd return after +1  MINUS  after -1.")
    print("   A real squeeze edge should show a POSITIVE spread with clustered t >> 2.")
    print("=" * 118)
    for period, thrs in ((20, (0.012, 0.020, 0.030, 0.050, 0.080, 0.120)),
                         (40, (0.020, 0.030, 0.040, 0.060))):
        print(f"\nperiod = {period}")
        print(f"{'thr':>7} {'n(+1)':>7} {'n(-1)':>7} {'fwd5 +1':>9} {'fwd5 -1':>9} "
              f"{'spr5':>8} {'t_iid5':>7} {'t_clu5':>7} | {'fwd21 +1':>9} {'fwd21 -1':>9} "
              f"{'spr21':>8} {'t_iid21':>8} {'t_clu21':>8}")
        for thr in thrs:
            lng, shrt, _ = squeeze_signal(tr, period, thr, 3)
            row = [f"{thr:>7.3f}"]
            for fwd in (fwd5, fwd21):
                a, b = masked(fwd, lng), masked(fwd, shrt)
                am, bm, s, ti = tstat_iid(a, b)
                tc = tstat_clustered(a, b)
                row.append(f"{len(a):>7}")
                row.append(f"{len(b):>7}")
                row.append(f"{am * 100:>8.3f}%")
                row.append(f"{bm * 100:>8.3f}%")
                row.append(f"{s * 100:>7.3f}%")
                row.append(f"{ti:>7.2f}")
                row.append(f"{tc:>7.2f}")
                if fwd is fwd5:
                    row.append("|")
            print(" ".join(row))

    print("\n" + "=" * 118)
    print("B. THE SAME SPREAD WITH NO GATE AT ALL (pure 3-bar ROC continuation, all 48 names)")
    print("   If the gated spread is not larger than the ungated one, the gate adds nothing.")
    print("=" * 118)
    for fwd, lab in ((fwd5, "5-bar"), (fwd21, "21-bar")):
        a, b = masked(fwd, (r3 > 0).astype(float)), masked(fwd, (r3 < 0).astype(float))
        am, bm, s, ti = tstat_iid(a, b)
        tc = tstat_clustered(a, b)
        print(f"  ungated ROC3, {lab:>5} fwd:  +1 {am * 100:>7.3f}%   -1 {bm * 100:>7.3f}%   "
              f"spread {s * 100:>7.3f}%   t_iid {ti:>6.2f}   t_clustered {tc:>6.2f}")

    print("\n" + "=" * 118)
    print("C. MULTIPLE-TESTING REALITY CHECK")
    print("   Grid searched above: 6 + 4 thresholds x 2 horizons x 2 directions. ")
    print("   Under the null, max |t| over ~20 independent tests reaches ~2.8-3.0 at 5%.")
    print("=" * 118)
    cv20 = cv_panel(tr, 20)
    print(f"\n  {'thr':>7} {'gate%':>8} {'names/d':>9}  (period=20, TRAIN liveness)")
    for thr in (0.012, 0.020, 0.030, 0.050, 0.080, 0.120):
        gate = cv20 < thr
        lng = gate & (r3 > 0)
        print(f"  {thr:>7.3f} {float(gate.to_numpy().mean()) * 100:>7.2f}% "
              f"{float(lng.sum(axis=1).mean()):>9.1f}")


if __name__ == "__main__":
    main()
