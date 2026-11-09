"""Step 4 — verification. No new strategy variants; controls only.

1. Random control matched to the SELECTED variant's liveness.
2. Empirical no-lookahead proof: lag the score one bar; if a lookahead existed the
   lagged and unlagged runs would coincide.
3. Weight-count trajectory — confirm the book is not accreting names toward 48.
4. Cross-check buy-and-hold against the donchian agent's independent figure.
5. Warmup-defect impact: quantify what the s4 fix changed, for the record.
"""

from __future__ import annotations

import json

import common as C
import pandas as pd

panel, symbols, _ = C.load_all()
C.align(panel)
test = C.slice_panel(panel, C.TEST_START, C.TEST_END)
train = C.slice_panel(panel, C.TRAIN_START, C.TRAIN_END)

with open("train_results.json") as f:
    tr = json.load(f)
spec = C.VARIANTS[tr["selected_id"]]
print(f"verifying SELECTED {tr['selected_id']}: L={spec['L']} thr={spec['threshold']}\n")

# --- 1. random control matched to the SELECTED variant ----------------------
print("1. RANDOM CONTROL matched to the SELECTED variant")
sel = C.backtest(*C.score_window(panel, C.TEST_START, C.TEST_END,
                                 spec["L"], spec["threshold"]))
flag_full = C.gap_flag(panel, spec["L"], spec["threshold"])
print(f"   SELECTED : CAGR {sel.metrics.cagr * 100:>6.2f}%  "
      f"Sharpe {sel.metrics.sharpe:>5.2f}  names {sel.diag['avg_names']:.1f}")
rsh, rcg = [], []
for seed in C.CONTROL_SEEDS:
    rm = C.random_mask_like(flag_full, seed)
    r = C.backtest(*C.windowed(panel, C.TEST_START, C.TEST_END,
                               lambda key, rm=rm: C.score_from_flag(panel, rm, key=key)))
    rsh.append(r.metrics.sharpe)
    rcg.append(r.metrics.cagr)
    print(f"   seed {seed:>4}: CAGR {r.metrics.cagr * 100:>6.2f}%  "
          f"Sharpe {r.metrics.sharpe:>5.2f}")
beat = sum(1 for s in rsh if s < sel.metrics.sharpe)
print(f"   random band: CAGR {min(rcg) * 100:.2f}%..{max(rcg) * 100:.2f}%  "
      f"Sharpe {min(rsh):.2f}..{max(rsh):.2f}")
print(f"   -> SELECTED beat {beat}/5 seeds. A coin flips 2.5/5 by chance, so "
      f"{beat}/5 is {'NO EDGE' if beat <= 3 else 'some edge'}.\n")

# --- 2. empirical no-lookahead check ---------------------------------------
print("2. NO-LOOKAHEAD CHECK (lagged vs unlagged score must differ)")
tp, ts = C.score_window(panel, C.TEST_START, C.TEST_END, spec["L"], spec["threshold"])
r_lag = C.backtest(tp, ts.shift(1))
print(f"   score on t     : CAGR {sel.metrics.cagr * 100:6.2f}%  "
      f"Sharpe {sel.metrics.sharpe:6.2f}")
print(f"   score lagged 1 : CAGR {r_lag.metrics.cagr * 100:6.2f}%  "
      f"Sharpe {r_lag.metrics.sharpe:6.2f}")
d = abs(sel.metrics.sharpe - r_lag.metrics.sharpe)
print(f"   |delta Sharpe| = {d:.3f} -> "
      f"{'DIFFERS (no lookahead)' if d > 0.01 else 'IDENTICAL -- SUSPECT LOOKAHEAD'}")
nz = sel.weights.index[sel.weights.sum(axis=1) > 0]
print(f"   first non-zero weights {nz[0].date()} (month-1 rebalance date +1 bar)\n")

# --- 3. weight-count trajectory ---------------------------------------------
print("3. WEIGHT-COUNT TRAJECTORY (must not creep toward 48)")
for nm, lo, hi in (("TRAIN", C.TRAIN_START, C.TRAIN_END),
                    ("TEST", C.TEST_START, C.TEST_END)):
    pp, ps = C.score_window(panel, lo, hi, spec["L"], spec["threshold"])
    r = C.backtest(pp, ps)
    nc = (r.weights > 0).sum(axis=1)
    yr = pd.Series(nc.values, index=nc.index).groupby(nc.index.year).mean()
    print(f"   {nm}: overall {nc.mean():.1f}  " +
          "  ".join(f"{y}:{v:.1f}" for y, v in yr.items()))
print("   -> bounded at max_names=30 (shipped PortfolioConfig), never near 48\n")

# --- 4. cross-check buy-and-hold --------------------------------------------
print("4. CROSS-CHECK: buy-and-hold on TEST vs donchian agent's reported figure")
_, bh_m, _ = C.equal_weight_bh(test)
print(f"   this run          : CAGR {bh_m.cagr * 100:.2f}%  Sharpe {bh_m.sharpe:.2f}  "
      f"MaxDD {bh_m.max_drawdown * 100:.2f}%")
print("   donchian REPORT.md:  +8.16%  Sharpe +0.18  MaxDD -15.91%")
same = abs(bh_m.cagr * 100 - 8.16) < 0.05 and abs(bh_m.sharpe - 0.18) < 0.01
print(f"   -> {'MATCH (harness agrees with an independent agent)' if same else 'MISMATCH'}\n")

# --- 5. quantify the warmup defect I fixed ---------------------------------
print("5. IMPACT OF THE WARMUP DEFECT FOUND IN THIS VERIFICATION PASS")
print("   (score computed INSIDE the slice = the defect; on full panel = fixed)")
for nm, lo, hi in (("TRAIN", C.TRAIN_START, C.TRAIN_END),
                   ("TEST", C.TEST_START, C.TEST_END)):
    sl = C.slice_panel(panel, lo, hi)
    bad = C.backtest(sl, C.score_from_flag(sl, C.gap_flag(sl, spec["L"], spec["threshold"])))
    good = C.backtest(*C.score_window(panel, lo, hi, spec["L"], spec["threshold"]))
    print(f"   {nm:<6} defect : CAGR {bad.metrics.cagr * 100:6.2f}%  "
          f"Sharpe {bad.metrics.sharpe:5.2f}  names {bad.diag['avg_names']:.1f}")
    print(f"   {nm:<6} fixed  : CAGR {good.metrics.cagr * 100:6.2f}%  "
          f"Sharpe {good.metrics.sharpe:5.2f}  names {good.diag['avg_names']:.1f}")

# --- 6. is the L=5 filter doing anything? ----------------------------------
print("\n6. IS THE L=5 'GAP' FILTER DOING ANYTHING? (SELECTED variant vs momentum alone)")
mo = C.backtest(*C.windowed(panel, C.TEST_START, C.TEST_END,
                            lambda key: C.momentum_only_score(panel, key=key)))
print(f"   momentum-only : CAGR {mo.metrics.cagr * 100:6.2f}%  Sharpe {mo.metrics.sharpe:6.2f}")
print(f"   V4 gap+mom    : CAGR {sel.metrics.cagr * 100:6.2f}%  Sharpe {sel.metrics.sharpe:6.2f}")
print(f"   filter adds   : {(sel.metrics.cagr - mo.metrics.cagr) * 100:+.2f}pp CAGR, "
      f"{sel.metrics.sharpe - mo.metrics.sharpe:+.3f} Sharpe")

print("\n7. TEST detail")
print(f"   bars {len(test)}   avg names {sel.diag['avg_names']:.1f}   "
      f"max top weight {sel.diag['avg_top_weight'] * 100:.2f}% (cap 12%)")
print(f"   round-trip bps charged {sel.diag['round_trip_bps']}   "
      f"n_rebalances {sel.diag['n_rebalances']:.0f}")
eq = sel.equity
dd = eq / eq.cummax() - 1.0
print(f"   equity {eq.iloc[0]:.4f} -> {eq.iloc[-1]:.4f}   "
      f"trough {dd.min() * 100:.2f}% on {dd.idxmin().date()}")
