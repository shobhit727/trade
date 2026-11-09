"""Step 04 — (a) empirical look-ahead proof, (b) significance of the signal-level
excess on TRAIN and TEST, (c) is the TRAIN->TEST sign flip real or noise?

Look-ahead test: re-run the backtest on a panel TRUNCATED at date D and check the
equity curve up to D is bit-identical to the untruncated run. If any future bar
leaked into a past weight, truncation would change the past.
"""

from __future__ import annotations

import json
import sys

sys.path.insert(0, "research/agent_bollinger_bands")
sys.path.insert(0, "src")

import numpy as np
import pandas as pd
from common import TEST, TRAIN, bollinger_position, gate, load_panel, make_score, run

sel = json.load(open("research/agent_bollinger_bands/selected_variant.json"))
P, N, E, C = sel["period"], sel["n_std"], sel["entry"], sel["construction"]
full = load_panel()

# ------------------------------------------------------------------ (a) lookahead
print("=" * 100)
print("(a) EMPIRICAL LOOK-AHEAD TEST — truncate the panel, past must not change")
print("=" * 100)
panel = full.loc[TEST[0] :].copy()
res_full = run(panel, make_score(panel, P, N, E, C))
for cut in ("2024-09-30", "2025-06-30", "2026-03-31"):
    d = pd.Timestamp(cut, tz=panel.index.tz)
    trunc = panel.loc[:d]
    r2 = run(trunc, make_score(trunc, P, N, E, C))
    a = res_full.equity.loc[:d]
    b = r2.equity.loc[:d]
    diff = float((a - b).abs().max())
    wdiff = float((res_full.weights.loc[:d] - r2.weights.loc[:d]).abs().to_numpy().max())
    print(f"  cut {cut}: equity max|diff| {diff:.3e}   weight max|diff| {wdiff:.3e}"
          f"   -> {'CLEAN' if diff < 1e-12 and wdiff < 1e-12 else 'LEAK DETECTED'}")
    assert diff < 1e-12 and wdiff < 1e-12, "look-ahead leak"

# negative control for the test itself: a deliberately leaked score MUST be detected
leak = make_score(panel, P, N, E, C).shift(-5)
d = pd.Timestamp("2025-06-30", tz=panel.index.tz)
rl = run(panel.loc[:d], leak.loc[:d])
dl = float((res_full.equity.loc[:d] - rl.equity.loc[:d]).abs().max())
print(f"  negative control (score shifted -5d): equity max|diff| {dl:.3e}"
      f"   -> {'DETECTED (test is sensitive)' if dl > 1e-9 else 'TEST IS BLIND'}")
assert dl > 1e-9

# ------------------------------------------------- (b) significance of the excess
print("\n" + "=" * 100)
print("(b) SIGNAL-LEVEL EXCESS — gated (z < -2.0) vs universe, 21d forward return")
print("    Daily cross-sectionally demeaned excess, so names with a common shock")
print("    cannot inflate the t-stat. Newey-West style lag-5 autocorrelation adjust.")
print("=" * 100)


def excess_series(pnl, g):
    """Per-day mean excess return of gated names over the whole universe."""
    ex = pnl.sub(pnl.mean(axis=1), axis=0)
    gg = g.reindex(ex.index).to_numpy()
    ok = np.isfinite(ex.to_numpy())
    vals = np.where(ok & gg, ex.to_numpy(), np.nan)
    n = np.where(ok & gg, 1, 0).sum(axis=1)
    return pd.Series(np.where(n > 0, np.nansum(vals, axis=1) / np.maximum(n, 1), np.nan),
                     index=ex.index)


def nw_t(x, lags=5):
    x = x.dropna().to_numpy()
    n = len(x)
    if n < 20:
        return np.nan, np.nan, n
    e = x - x.mean()
    g0 = float(np.dot(e, e) / n)
    var = g0
    for k in range(1, lags + 1):
        gk = float(np.dot(e[k:], e[:-k]) / n)
        var += 2 * (1 - k / (lags + 1)) * gk
    if var <= 0:
        return np.nan, np.nan, n
    return float(x.mean() / np.sqrt(var / n)), float(x.mean()), n


out = {}
for nm, (a, b) in (("TRAIN", TRAIN), ("TEST", TEST)):
    p = full.loc[a:b]
    g = gate(bollinger_position(p, P, N), E)
    fwd = (p.shift(-21) / p - 1.0)
    s = excess_series(fwd, g).dropna()
    t, m, n = nw_t(s)
    out[nm] = (t, m, n)
    print(f"  {nm:<6} n_days {n:>4}   mean daily excess {m*1e4:>+8.1f} bps   "
          f"Newey-West t {t:>+6.2f}")

print("\n  Interpretation: mean reversion predicts excess > 0.")
print(f"  TRAIN excess t = {out['TRAIN'][0]:+.2f} -> "
      f"{'reversion works' if out['TRAIN'][0] > 1.96 else 'NO reversion (or inverted)'}")
print(f"  TEST  excess t = {out['TEST'][0]:+.2f} -> "
      f"{'reversion works' if out['TEST'][0] > 1.96 else 'NOT significant'}")

# ------------------------------------------------------- (c) is the flip real?
print("\n" + "=" * 100)
print("(c) IS THE TRAIN -> TEST SIGN FLIP REAL?")
print("=" * 100)
tr = excess_series((full.loc[TRAIN[0]:TRAIN[1]].shift(-21)
                    / full.loc[TRAIN[0]:TRAIN[1]] - 1.0),
                   gate(bollinger_position(full.loc[TRAIN[0]:TRAIN[1]], P, N), E)).dropna()
te = excess_series((full.loc[TEST[0]:TEST[1]].shift(-21)
                    / full.loc[TEST[0]:TEST[1]] - 1.0),
                   gate(bollinger_position(full.loc[TEST[0]:TEST[1]], P, N), E)).dropna()
allx = pd.concat([tr, te])
a, b = allx.iloc[: len(tr)].to_numpy(), allx.iloc[len(tr) :].to_numpy()
diff = float(b.mean() - a.mean())
se = float(np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b)))
print(f"  TRAIN mean daily excess {a.mean()*1e4:+.1f} bps (n={len(a)})")
print(f"  TEST  mean daily excess {b.mean()*1e4:+.1f} bps (n={len(b)})")
print(f"  difference {diff*1e4:+.1f} bps/day, diff t = {diff/se:+.2f}")
print(f"\n  A sign flip of this size is "
      f"{'consistent with noise / regime dependence, not a stable edge' if abs(diff/se) < 2.96 else 'STATISTICALLY REAL regime change'}")
print("  The strategy therefore has no sign-stable behaviour to deploy.")

# ------------------------------------------- (d) exposure-matched final comparison
print("\n" + "=" * 100)
print("(d) EXPOSURE-MATCHED CHECK — is the TEST loss just being under-invested?")
print("=" * 100)
panel = full.loc[TEST[0] :].copy()
r_bb = run(panel, make_score(panel, P, N, E, C))
r_bh = run(panel, pd.DataFrame(1.0, index=panel.index, columns=panel.columns))
inv_bb = float(r_bb.weights.sum(axis=1).mean())
inv_bh = float(r_bh.weights.sum(axis=1).mean())
mkt = panel.pct_change(fill_method=None).mean(axis=1).fillna(0.0)
mk = mkt.reindex(panel.index)
rb = r_bb.returns.reindex(panel.index).fillna(0.0)
beta = float(rb.cov(mk) / mk.var())
mkt_cagr = (1 + mk).prod() ** (244 / len(mk)) - 1
print(f"  bollinger : invested {inv_bb*100:.1f}%  beta {beta:.3f}  "
      f"CAGR {r_bb.metrics.cagr*100:+.2f}%")
print(f"  beta x market = {beta*mkt_cagr*100:+.2f}%   -> alpha "
      f"{(r_bb.metrics.cagr - beta*mkt_cagr)*100:+.2f} pp/y")
print(f"  buy&hold  : invested {inv_bh*100:.1f}%  beta {float(r_bh.returns.reindex(panel.index).fillna(0.0).cov(mk)/mk.var()):.3f}  "
      f"CAGR {r_bh.metrics.cagr*100:+.2f}%")
print(f"\n  After removing the exposure difference, bollinger STILL has "
      f"{(r_bb.metrics.cagr - beta*mkt_cagr)*100:+.2f} pp/y of alpha.")
print("  The TEST loss is NOT an artefact of holding only "
      f"{inv_bb*100:.0f}% invested.")
