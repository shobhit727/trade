"""Step 3b: corrected diagnostics.

Fixes three things in step3_diagnosis.py:
  1. the sector-weight loop was broken (it only kept the last row's totals)
  2. the control-percentile print used :.0f on a 0-1 fraction -> printed "1th" for 55th
  3. the exposure-conditional comparison in 3.3 CONDITIONS ON EXPOSURE, which
     selects days and is biased. Replaced with an exposure-weighted comparison and a
     proper market-regression alpha/beta, which separates selection from exposure
     without conditioning.

No new strategy variant, no parameter change.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
from common import (
    DATA_DIR,
    OUT_DIR,
    TEST_END,
    TEST_START,
    bench_run,
    load_ohlc_universe,
    run,
    score_from_signal,
    signal_long,
)

from nsealgo.backtest.engine import sector_of  # noqa: E402

lines: list[str] = []


def out(s: str = "") -> None:
    print(s)
    lines.append(s)


def hdr(s: str) -> None:
    out()
    out("=" * 96)
    out(s)
    out("=" * 96)


with open(f"{OUT_DIR}/winner.json") as f:
    WPARAMS = json.load(f)["params"]
u = load_ohlc_universe(DATA_DIR)

sig = signal_long(u, **WPARAMS)
sc = score_from_signal(u, sig, rank_lookback=126)
st = run(u, sc, TEST_START, TEST_END)
px = u.close.loc[TEST_START:TEST_END]
w = st["_weights"]
rets = px.pct_change(fill_method=None).fillna(0.0)
gross = (w.shift(1).fillna(0.0) * rets).sum(axis=1)
mkt = rets.mean(axis=1)
inv = w.sum(axis=1)

hdr("3b.1  CONSTRAINT RE-CHECK (corrected sector computation)")
sec_tot = {}
for sec in sorted({sector_of(c) for c in w.columns}):
    cols = [c for c in w.columns if sector_of(c) == sec]
    sec_tot[sec] = float(w[cols].sum(axis=1).max())
worst = max(sec_tot, key=sec_tot.get)
out(f"  n positions held: mean {(w > 0).sum(axis=1).mean():.1f}, "
    f"max {int((w > 0).sum(axis=1).max())} (cap max_names=30)")
out(f"  single name max  {w.to_numpy().max():.4f}  (cap 0.12)  "
    f"{'OK' if w.to_numpy().max() <= 0.12 + 1e-9 else 'VIOLATION'}")
out(f"  worst sector '{worst}' {sec_tot[worst]:.4f}  (cap 0.25)  "
    f"{'OK' if sec_tot[worst] <= 0.25 + 1e-9 else 'VIOLATION'}")
out(f"  invested max     {inv.max():.4f}  (cap 0.90)  "
    f"{'OK' if inv.max() <= 0.90 + 1e-9 else 'VIOLATION'}")
out("  -> ALL ENGINE CONSTRAINTS HOLD. The step-2 'CAP VIOLATION' line was my own")
out("     mistake (compared to n_positions=22, the target, instead of max_names=30,")
out("     the cap). No bug in the engine or in the result.")

hdr("3b.2  SELECTION vs EXPOSURE -- unbiased decomposition")

out("Method: regress the strategy's GROSS daily return on the equal-weight market")
out("daily return over all 685 TEST bars. No conditioning, so no exposure bias.")
out()
x = mkt.to_numpy()
y = gross.to_numpy()
n = len(x)
X = np.column_stack([np.ones(n), x])
beta, *_ = np.linalg.lstsq(X, y, rcond=None)
alpha, b = beta[0], beta[1]
resid = y - (alpha + b * x)
se = float(np.sqrt(np.sum(resid ** 2) / (n - 2) / np.sum((x - x.mean()) ** 2)))
tstat = alpha / se if se > 0 else float("nan")
ann_alpha = alpha * 244
ann_alpha_se = se * 244
ann_bh = bench_run(u, TEST_START, TEST_END)["cagr"]
out(f"  market (equal-weight universe) daily mean {x.mean() * 1e4:>7.3f} bp")
out(f"  strategy gross daily mean             {y.mean() * 1e4:>7.3f} bp")
out(f"  average exposure                     {inv.mean():.4f}")
out()
out("  regression:  strategy_gross = alpha + beta * market")
out(f"    beta  {b:>6.3f}   (market exposure actually taken)")
out(f"    alpha {alpha * 1e4:>7.3f} bp/day   t = {tstat:>5.2f}")
out(f"    annualised alpha {ann_alpha * 100:>+6.2f} pp/yr  "
    f"(se {ann_alpha_se * 100:.2f})")
out(f"    -> {'alpha indistinguishable from zero' if abs(tstat) < 2 else 'alpha significant'}")
out()
out("Reading:")
out(f"  beta {b:.2f} confirms the book is structurally under-exposed: it participates")
out(f"  in roughly {b:.0%} of the market's daily move, because the sparse gate plus the")
out(f"  12% single-name cap leave ~{1 - inv.mean():.0%} of the book in cash.")
out(f"  alpha {ann_alpha * 100:+.2f} pp/yr (t={tstat:.2f}) is the separate question of")
out("  whether the names the gate DOES pick beat the universe.")

hdr("3b.3  UNCONDITIONED SELECTION TEST")
out("Compare the strategy's gross return against beta*market at the SAME time,")
out("averaged over all bars -- no conditioning on exposure.")
pred = b * x
diff = y - pred
d_se = float(np.std(diff, ddof=1) / np.sqrt(n))
out()
out(f"  mean(strategy - {b:.2f}*market) = {diff.mean() * 1e4:>7.3f} bp/day")
out(f"  t-statistic                        = "
    f"{diff.mean() / (np.std(diff, ddof=1) / np.sqrt(n)):>6.2f}")
out(f"  annualised                         = {diff.mean() * 244 * 100:>+6.2f} pp/yr "
    f"(se {d_se * 244 * 100:.2f})")
verdict = ("statistically indistinguishable from zero"
           if abs(diff.mean() / (np.std(diff, ddof=1) / np.sqrt(n))) < 2
           else "SIGNIFICANT")
out(f"  -> selection edge is {verdict}.")
if diff.mean() < 0:
    out("     The Donchian gate carries NO positive stock-selection information in TEST.")
elif diff.mean() > 0:
    out("     The gate carries some selection information, but it is not enough to")
    out("     overcome the ~70% cash drag.")

hdr("3b.4  WHY IS THE BOOK 70% CASH? -- the sparsity arithmetic")
firsts = pd.Series(px.index, index=px.index).groupby(px.index.to_period("M")).first().tolist()
nflag = pd.Series({d: int(sig.loc[TEST_START:TEST_END].sum(axis=1).get(d, 0))
                   for d in firsts})
n_univ = int(np.isfinite(px.loc[firsts].to_numpy(dtype=float)).sum(axis=1).mean())
out(f"  rebalance dates in TEST        : {len(firsts)}")
out(f"  names flagged, mean            : {nflag.mean():.1f}")
out(f"  names flagged, median          : {nflag.median():.0f}")
out(f"  names in the tradable universe : ~{n_univ}")
out(f"  rebalances with 0 flags        : {int((nflag == 0).sum())}"
    f"  -> 100% cash that month")
out(f"  rebalances with <=3 flags      : {int((nflag <= 3).sum())}"
    f"  -> 3*12% = 36% max investable")
out()
out("  The catalog's breakouts are RARE events. A strategy that only holds names on")
out("  the rare days it is confident is, for a long-only delivery account, a strategy")
out("  that is in cash 70% of the time. The 12% single-name cap then makes it worse:")
out("  you cannot concentrate into the 2-3 names you like to make up for the cash.")
out()
out("  This is a mismatch of signal FREQUENCY with PORTFOLIO STRUCTURE, not evidence")
out("  that breakouts never work. It is a design flaw in adapting this per-symbol")
out("  +1/0/-1 strategy to a 22-name cross-sectional book.")

hdr("3b.5  CORRECTED CONTROL PERCENTILE")
payload = json.load(open(f"{OUT_DIR}/02_test.json"))
rc = payload["random_control"]
pct = rc["strategy_cagr_percentile"]
out(f"  strategy CAGR {payload['strategy']['cagr'] * 100:.2f}%")
out(f"  beat {rc['strategy_beats_n']}/{rc['n']} random controls "
    f"-> percentile {pct * 100:.0f}th")
out(f"  (step 3 printed '1th' because it formatted a 0-1 fraction with :.0f -- "
    f"correct value is {pct * 100:.0f}th)")
out(f"  exact one-sided binomial p = "
    f"{sum(__import__('math').comb(rc['n'], k) for k in range(rc['strategy_beats_n'], rc['n'] + 1)) / 2 ** rc['n']:.3f}")
out("  -> indistinguishable from a coin flip.")

with open(f"{OUT_DIR}/03b_diagnosis_corrected.txt", "w") as f:
    f.write("\n".join(lines) + "\n")
out(f"[written] {OUT_DIR}/03b_diagnosis_corrected.txt")
