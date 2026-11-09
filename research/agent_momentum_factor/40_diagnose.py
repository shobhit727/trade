"""40 — WHY it failed. Diagnostics on the frozen M4. Computes no new candidate.

The central question: is `roc(period)` a momentum or a reversal signal on this panel?
We measure the forward return of each *leg* of the strategy (long / flat / short) against
the forward 21-bar return, on TRAIN and TEST separately, plus the rank IC.

Three defects in the first version of this script, found and fixed before use:
  * the TRAIN/TEST loop masked the *leg* but never restricted the forward-return panel,
    so both windows printed identical numbers;
  * annualising with `(1 + vals).prod()` overflows to inf over ~10^5 name-bars, so
    geometric annualisation is done in log space;
  * `df.where(df >= df.quantile(0.8, axis=1), axis=1)` misaligns in this pandas
    version — the per-row threshold is broadcast row-wise explicitly instead.
"""

from __future__ import annotations

import common
import numpy as np

SELECTED = "M4"
FWD = 21  # forward horizon for the leg test (~1 month)

panel, symbols, _ = common.load_panel()
v = common.BY_TAG[SELECTED]

sig_full = common.strategy_signal(panel, v.period, v.threshold)
fwd_full = (panel.shift(-FWD) / panel - 1.0)

print(f"leg analysis: leg signal (period {v.period}, thr {v.threshold}) vs forward "
      f"{FWD}-bar return\n")


def ann_arith(vals: np.ndarray, horizon: int = FWD) -> float:
    """Naive annualisation of an OVERLAPPING-horizon return stream.

    A third defect fixed here: compounding overlapping `horizon`-bar forward returns
    as if they were sequential multiplies each bar ~horizon times, which produced
    nonsense (a "732 %/yr" leg). The standard treatment for overlapping horizons is
    the arithmetic mean scaled by (244 / horizon), which does not compound. Used for
    every leg/quintile figure below.
    """
    vals = vals[np.isfinite(vals)]
    if len(vals) == 0:
        return float("nan")
    return float(vals.mean() * 244.0 / horizon)


for label, S, E in (("TRAIN", common.TRAIN_START, common.TRAIN_END),
                    ("TEST", common.TEST_START, common.TEST_END)):
    m = (panel.index >= S) & (panel.index <= E)
    sig = sig_full.loc[m]
    fwd = fwd_full.loc[m]
    rows = []
    for leg, mask in (("long", sig > 0), ("flat", sig == 0), ("short", sig < 0)):
        vals = fwd.where(mask).to_numpy().ravel()
        vals = vals[np.isfinite(vals)]
        if len(vals) == 0:
            continue
        rows.append({
            "leg": leg, "n": len(vals), "mean_fwd": float(vals.mean()),
            "annualised": ann_arith(vals), "win": float((vals > 0).mean()),
            "t": float(vals.mean() / vals.std(ddof=1) * np.sqrt(len(vals))),
        })
    print(f"{label}  ({len(fwd)} bars)")
    print(common.fmt_table(rows, ["leg", "n", "mean_fwd", "annualised", "win", "t"]))
    lo = next((r for r in rows if r["leg"] == "long"), None)
    sh = next((r for r in rows if r["leg"] == "short"), None)
    if lo and sh:
        print(f"  long-minus-short spread: "
              f"{(lo['annualised'] - sh['annualised']) * 100:+.2f} pp/yr\n")
    else:
        print()

# ---- rank IC of the raw ROC against the forward 21-bar return, per day
print("cross-sectional rank IC of ROC(period) vs forward 21d return:")
for label, S, E in (("TRAIN", common.TRAIN_START, common.TRAIN_END),
                    ("TEST", common.TEST_START, common.TEST_END)):
    m = (panel.index >= S) & (panel.index <= E)
    mm, ff = common.roc_panel(panel, v.period).loc[m], fwd_full.loc[m]
    ics = []
    for dt in mm.index:
        a, b = mm.loc[dt], ff.loc[dt]
        ok = a.notna() & b.notna()
        if ok.sum() < 20:
            continue
        ics.append(float(a[ok].corr(b[ok], method="spearman")))
    ics = np.array(ics)
    print(f"  {label:5s} mean IC {ics.mean():+.4f}  "
          f"t {ics.mean() / ics.std(ddof=1) * np.sqrt(len(ics)):+.2f}  "
          f"positive on {100 * (ics > 0).mean():.1f}% of days  (n={len(ics)})")

# ---- horizon sweep: is ANY lookback a continuation signal?
print("\ntop-quintile vs bottom-quintile forward-21d return by trailing lookback "
      "(does momentum work at any horizon?):")
for label, S, E in (("TRAIN", common.TRAIN_START, common.TRAIN_END),
                    ("TEST", common.TEST_START, common.TEST_END)):
    m = (panel.index >= S) & (panel.index <= E)
    ff = fwd_full.loc[m]
    line = []
    for look in (20, 60, 126, 252):
        mm = common.roc_panel(panel, look).loc[m]
        q80 = mm.quantile(0.8, axis=1)
        q20 = mm.quantile(0.2, axis=1)
        top = mm.ge(q80, axis=0)
        bot = mm.le(q20, axis=0)
        a = ann_arith(ff.where(top).to_numpy().ravel())
        b = ann_arith(ff.where(bot).to_numpy().ravel())
        line.append(f"look{look}: top {a * 100:+.1f}% / bot {b * 100:+.1f}% "
                    f"(spread {(a - b) * 100:+.1f}pp)")
    print(f"  {label:5s} " + " | ".join(line))

# ---- is the deadband binding at all?
print("\ngate bindingness — how much does the threshold actually exclude?")
for vv in (common.BY_TAG["M1"], common.BY_TAG["M4"]):
    s2 = common.strategy_signal(panel, vv.period, vv.threshold)
    m = (s2.index >= common.TRAIN_START) & (s2.index <= common.TRAIN_END)
    w = s2.loc[m]
    elig = (w > 0).sum(axis=1)
    n = len(panel.columns)
    print(f"  {vv.tag} (thr {vv.threshold}): avg long-eligible {elig.mean():.1f}/{n}; "
          f"days with >=22 eligible {100 * (elig >= 22).mean():5.1f}%; "
          f"days with all {n} eligible {100 * (elig >= n).mean():5.1f}%")

