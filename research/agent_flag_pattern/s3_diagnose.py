"""STEP 3 -- diagnosis. NOT a parameter variant and NOT used to select anything.

Everything here is post-hoc explanation of a result already fixed by s1 (TRAIN winner)
and s2 (TEST). It exists to answer "why", and its most useful output is a direct event
study: does the shipped signal carry ANY information about forward returns at all?

No parameter is chosen from this file. No TEST number is used to pick anything.

Run: .venv/bin/python research/agent_flag_pattern/s3_diagnose.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from common import (
    TEST_END,
    TEST_START,
    TRAIN_END,
    TRAIN_START,
    VARIANTS,
    backtest,
    build_score,
    load_all,
    run_signal,
)

pd.set_option("display.width", 200)

PANEL, HIGH, LOW, SYMBOLS, _ = load_all()
sig = run_signal(PANEL, HIGH, LOW, VARIANTS["V0_LITERAL"])
fwd = {h: PANEL.shift(-h) / PANEL - 1.0 for h in (1, 5, 21, 63)}

# --------------------------------------------------------------------------- #
# 1. EVENT STUDY -- the decisive test. Does the flag predict forward returns?
# --------------------------------------------------------------------------- #
print("=" * 78)
print("EVENT STUDY: mean forward return of flagged vs unflagged names")
print("=" * 78)
print("pooled across all 48 names, equal-weighted, no costs, no portfolio\n")
hdr = (f"  {'set':<6}{'h(days)':>9}{'n_flag':>10}{'flagged':>11}"
       f"{'unflagged':>11}{'spread':>10}{'t-stat':>9}")
print(hdr)
print("  " + "-" * (len(hdr) - 2))

for label, lo, hi in (("TRAIN", TRAIN_START, TRAIN_END),
                      ("TEST", TEST_START, TEST_END)):
    s = sig.loc[lo:hi].to_numpy(dtype=float)
    for h in (1, 5, 21, 63):
        r = fwd[h].loc[lo:hi].to_numpy(dtype=float)
        ok = np.isfinite(r) & np.isfinite(s)
        a = r[ok & (s > 0)]
        b = r[ok & (s <= 0)]
        if len(a) < 30 or len(b) < 30:
            continue
        diff = a.mean() - b.mean()
        se = np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
        t = diff / se if se > 0 else float("nan")
        print(f"  {label:<6}{h:>9}{len(a):>10}{a.mean():>10.2%}"
              f"{b.mean():>11.2%}{diff:>10.2%}{t:>9.2f}")

print("\n  t-stat is a two-sample approximation; |t| < ~2 means the spread is not")
print("  distinguishable from noise. This is the whole ballgame: if 'spread' is")
print("  ~0 with |t| < 2, the signal carries no information and no portfolio")
print("  construction can rescue it.")

# --------------------------------------------------------------------------- #
# 2. ABLATION -- how much does the flag contribute vs the ranking layer?
# --------------------------------------------------------------------------- #
print("\n" + "=" * 78)
print("ABLATION on TEST: which layer of the construction carries the return?")
print("=" * 78)
te = slice(TEST_START, TEST_END)
tr = slice(TRAIN_START, TRAIN_END)
p_te, p_tr = PANEL.loc[te], PANEL.loc[tr]

s_te = sig.loc[te]
mom126 = PANEL / PANEL.shift(126) - 1.0

from nsealgo.factors.core import rank_cross_sectional  # noqa: E402

cases = {
    "A signal+126dmom (shipped construction)": build_score(s_te, p_te),
    "B 126dmom ONLY (flag removed)": rank_cross_sectional(mom126.loc[te]),
    "C FLAG ONLY (no momentum rank)": s_te.where(s_te > 0).mask(s_te <= 0, 0.0),
    "D signal only, no rank (as above)": s_te.where(s_te > 0).mask(s_te <= 0, 0.0),
}
print(f"  {'construction':<42}{'CAGR':>9}{'Sharpe':>9}{'MaxDD':>9}{'N':>7}")
print("  " + "-" * 76)
for label, sc in cases.items():
    if label.startswith("D"):
        continue
    r = backtest(p_te, sc)
    print(f"  {label:<42}{r.metrics.cagr:>8.2%}{r.metrics.sharpe:>9.2f}"
          f"{r.metrics.max_drawdown:>8.2%}{r.diag['avg_names']:>7.1f}")

print("\n  If B ~= A, the flag contributes nothing and the result is just 126d momentum.")

# --------------------------------------------------------------------------- #
# 3. Does the flag survive a stricter read -- conditioning on it being a NEW signal?
# --------------------------------------------------------------------------- #
print("\n" + "=" * 78)
print("Was the flag informative on TRAIN but decayed? (signal quality by half-period)")
print("=" * 78)
half = pd.Timestamp("2020-01-01", tz="Asia/Kolkata")
for label, lo, hi in (("TRAIN 16-19", TRAIN_START, half),
                      ("TRAIN 20-23", half, TRAIN_END),
                      ("TEST 24-26", TEST_START, TEST_END)):
    s = sig.loc[lo:hi].to_numpy(dtype=float)
    r = fwd[21].loc[lo:hi].to_numpy(dtype=float)
    ok = np.isfinite(r) & np.isfinite(s)
    a = r[ok & (s > 0)]
    b = r[ok & (s <= 0)]
    se = np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
    d = a.mean() - b.mean()
    print(f"  {label:<14} 21d spread {d:>7.2%}  t {d / se:>6.2f}  "
          f"(flagged n={len(a)})")

# --------------------------------------------------------------------------- #
# 4. Turnover-budget accretion -- the mechanism behind finding 5.2.1(c)
# --------------------------------------------------------------------------- #
print("\n" + "=" * 78)
print("MECHANISM: how much of the book is actually the flag's idea?")
print("=" * 78)
for label, lo, hi in (("TRAIN", TRAIN_START, TRAIN_END),
                      ("TEST", TEST_START, TEST_END)):
    s = sig.loc[lo:hi]
    n_flag = (s > 0).sum(axis=1)
    r = backtest(PANEL.loc[lo:hi], build_score(s, PANEL.loc[lo:hi]))
    held = r.weights
    fresh = (s.loc[held.index] > 0)
    # on each day, what fraction of deployed weight sits in a currently-flagged name?
    tot = held.sum(axis=1).replace(0.0, np.nan)
    in_flag = held.where(fresh).sum(axis=1) / tot
    print(f"  {label:<6} avg names flagged {n_flag.mean():>5.1f} / 48   "
          f"book holds {r.diag['avg_names']:>5.1f}   "
          f"deployed weight sitting in a CURRENTLY-flagged name: "
          f"{float(in_flag.mean()):.1%}")
print("\n  The turnover budget blends rather than replaces, so the book keeps names the")
print("  flag has already abandoned. That is why V0/V1/V2 (liveness 25.7% / 12.7% /")
print("  3.1%) all produced similar books and similar results.")
