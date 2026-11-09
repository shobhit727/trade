"""Step 02b — TRAIN-ONLY signal-level diagnostics.

A portfolio backtest of a sparse gated signal confounds three things: (a) does the
signal predict, (b) how much of the book is invested, (c) transaction costs. This
script isolates (a) and (b) with exposure-free and cost-free measures so the TRAIN
verdict is not an artefact of a 29%-invested book.

Measures:
  * cross-sectional rank IC  (Spearman, per day, averaged) vs 21d forward return
  * top-minus-bottom spread inside the gated set, equal-weighted, 21d
  * beta to the equal-weight universe + average invested fraction, per variant

All of this is TRAIN only.
"""

from __future__ import annotations

import sys

sys.path.insert(0, "research/agent_bollinger_bands")
sys.path.insert(0, "src")

import numpy as np
import pandas as pd
from common import TRAIN, bollinger_position, gate, load_panel, make_score, run

panel_full = load_panel()
panel = panel_full.loc[: TRAIN[1]].copy()
fwd21 = (panel.shift(-21) / panel - 1.0)
mkt = panel.pct_change(fill_method=None).mean(axis=1).fillna(0.0)

VARIANTS = [
    ("V1 bb_pure_default", 20, 2.0, 1.0, "pure"),
    ("V2 bb_hybrid_mom6m", 20, 2.0, 1.0, "hybrid"),
    ("V3 bb_pure_deep", 20, 2.5, 1.0, "pure"),
    ("V4 bb_pure_slow", 60, 2.0, 1.0, "pure"),
    ("V5 bb_pure_fast", 10, 2.0, 1.0, "pure"),
]


def rank_ic(score, fwd):
    """Per-day Spearman rank correlation, averaged over days with >=5 valid names."""
    ics = []
    for i in range(len(score)):
        s, f = score.iloc[i], fwd.iloc[i]
        ok = s.notna() & f.notna()
        if int(ok.sum()) < 5:
            continue
        a, b = s[ok], f[ok]
        if a.nunique() < 2 or b.nunique() < 2:
            continue
        ics.append(a.rank().corr(b.rank()))
    return (float(np.mean(ics)), float(np.std(ics) / np.sqrt(len(ics))), len(ics)) if ics else (np.nan,) * 3


def gated_spread(panel, period, n_std, entry, horizon=21):
    """Within-gate equal-weight top-minus-bottom, renormalised to 1 unit of exposure.

    The gated set is typically only 2-3 names, so a 1.0-long / -1.0-short spread is
    not expressible; this returns the equal-weight mean forward return of the gated
    names only, alongside the same quantity for the whole universe, so the two are
    directly comparable without leverage.
    """
    g = gate(bollinger_position(panel, period, n_std), entry)
    f = (panel.shift(-horizon) / panel - 1.0)
    gm = pd.DataFrame(np.where(g.to_numpy(), f.to_numpy(), np.nan), index=f.index, columns=f.columns)
    per_day = gm.mean(axis=1, skipna=True)
    cnt = g.sum(axis=1)
    sel = per_day[cnt > 0].dropna()
    base = f.mean(axis=1).dropna()
    return sel, base


print("=" * 104)
print(f"TRAIN-ONLY signal-level diagnostics  {panel.index.min().date()} -> "
      f"{panel.index.max().date()}")
print("=" * 104)

print("\n" + "-" * 104)
print("1) CROSS-SECTIONAL RANK IC vs 21d forward return, measured INSIDE THE GATED SET ONLY")
print("   (higher = the signal orders names correctly within its own picks)")
print("-" * 104)
for name, period, n_std, entry, constr in VARIANTS:
    score = make_score(panel, period, n_std, entry, constr)
    ic, se, nd = rank_ic(score, fwd21)
    star = "  *" if abs(ic / se) > 2 else ""
    print(f"  {name:<22} IC {ic:+.4f}  (se {se:.4f}, t={ic/se:+.2f}, {nd} days){star}")

print("\n" + "-" * 104)
print("2) FORWARD RETURN OF GATED NAMES vs WHOLE UNIVERSE (equal-weight, no leverage)")
print("-" * 104)
for name, period, n_std, entry, _constr in VARIANTS:
    sel, base = gated_spread(panel, period, n_std, entry)
    exc = sel.mean() - base.mean()
    t = exc / (sel.std() / np.sqrt(len(sel)))
    print(f"  {name:<22} gated {sel.mean()*1e4:>7.0f} bps/21d   "
          f"universe {base.mean()*1e4:>7.0f} bps   "
          f"excess {exc*1e4:>+7.0f} bps  (t={t:+5.2f}, n={len(sel)})")

print("\n" + "-" * 104)
print("3) EXPOSURE / BETA DECOMPOSITION (why the portfolio CAGR is low)")
print("-" * 104)
print("  invested = mean sum of held weights. beta = cov(strategy, universe)/var(universe).")
print(f"  {'variant':<22} {'invested%':>10} {'beta':>7} {'strat CAGR%':>12} "
      f"{'beta x mkt%':>12} {'alpha pp':>9}")
for name, period, n_std, entry, constr in VARIANTS:
    score = make_score(panel, period, n_std, entry, constr)
    res = run(panel, score)
    inv = float(res.weights.sum(axis=1).mean())
    r = res.returns.reindex(panel.index).fillna(0.0)
    mk = mkt.reindex(panel.index).fillna(0.0)
    beta = float(r.cov(mk) / mk.var())
    mkt_cagr = (1 + mk).prod() ** (244 / len(mk)) - 1
    print(f"  {name:<22} {inv*100:>9.1f}% {beta:>7.3f} {res.metrics.cagr*100:>11.2f}% "
          f"{beta*mkt_cagr*100:>11.2f}% {(res.metrics.cagr-beta*mkt_cagr)*100:>8.2f}")

print("\n  A sparse gate structurally caps exposure. If `beta x mkt` already explains")
print("  the whole shortfall, the strategy is not 'wrong', it is just not investable")
print("  as a standalone book — which is itself the finding.")

print("\n" + "-" * 104)
print("4) MONOTONICITY CHECK — mean 21d forward return vs Bollinger z (TRAIN)")
print("   SIGN CONVENTION: z = (close - mean)/sd, so z < 0 is OVERSOLD.")
print("   MEAN REVERSION  =>  oversold predicts HIGH fwd return => corr(z, fwd) < 0.")
print("   MOMENTUM/CONTIN. =>  oversold predicts LOW  fwd return => corr(z, fwd) > 0.")
print("-" * 104)
z = bollinger_position(panel, 20, 2.0) * 2.0
bins = [-np.inf, -3, -2.5, -2, -1.5, -1, 0, 1, 2, np.inf]
labels = ["<-3", "-3..-2.5", "-2.5..-2", "-2..-1.5", "-1.5..-1", "-1..0",
          "0..1", "1..2", ">2"]
zf, ff = z.to_numpy().ravel(), fwd21.to_numpy().ravel()
ok = np.isfinite(zf) & np.isfinite(ff)
long = pd.DataFrame({"z": zf[ok], "fwd": ff[ok]})
long["b"] = pd.cut(long["z"], bins=bins, labels=labels)
agg = long.groupby("b", observed=True)["fwd"].mean() * 1e4
print("  bucket (oversold -> overbought), mean 21d fwd return:")
for k, v in agg.items():
    print(f"    z {k:>10}  {v:>8,.0f} bps")
mid = np.array([-3.25, -2.75, -2.25, -1.75, -1.25, -0.5, 0.5, 1.5, 2.5])
corr = float(np.corrcoef(mid, agg.to_numpy())[0, 1])
print(f"\n  corr(bucket midpoint z, mean fwd return) = {corr:+.3f}")
verdict = ("MEAN REVERSION present" if corr < -0.3
           else "MEAN REVERSION ABSENT" if abs(corr) <= 0.3
           else "MOMENTUM/CONTINUATION — mean reversion is INVERTED")
print(f"  -> {verdict}")
print("\n  This is the decisive evidence and it is exposure-free and cost-free:")
print("  it says what the signal predicts, independent of portfolio construction.")
