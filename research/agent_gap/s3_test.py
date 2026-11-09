"""Step 3 — TEST. The SELECTED variant only, evaluated once, unchanged.

TEST was not read by s1_data.py beyond confirming it exists, nor by s2_train.py at all.
This script applies exactly the parameters chosen on TRAIN (V4: L=5, threshold=0.01)
with the same declared selection rule and the same no-warmup fix.
"""

from __future__ import annotations

import json

import common as C

with open("train_results.json") as f:
    tr = json.load(f)

sel_id = tr["selected_id"]
spec = C.VARIANTS[sel_id]
print(f"SELECTED ON TRAIN (unchanged here): {sel_id}  "
      f"L={spec['L']}  threshold={spec['threshold']}  ({spec['note']})")
print(f"selection rule: {tr['selection_rule']}")
print(f"round-trip bps charged by the engine: {tr['round_trip_bps']}")
print(f"warmup fix applied: {tr['warmup_fix']}")
print()

panel, symbols, _ = C.load_all()
C.align(panel)
test = C.slice_panel(panel, C.TEST_START, C.TEST_END)
print(f"TEST window {C.TEST_START.date()} -> {C.TEST_END.date()}  "
      f"bars={len(test)}  symbols={test.shape[1]}")
print()

rows = []
sel_flag_full = C.gap_flag(panel, spec["L"], spec["threshold"])

# --- the SELECTED variant ---------------------------------------------------
tp, ts = C.score_window(panel, C.TEST_START, C.TEST_END, spec["L"], spec["threshold"])
res = C.backtest(tp, ts)
# liveness from the FULL-panel flag: this is how the score is actually built, so the
# first 5 bars of TEST have a valid gap (shift(5) reaches into 2023). Slicing first
# would leave 5 all-NaN rows and understate the fraction.
flag = sel_flag_full
frac, nday = C.liveness(flag, C.TEST_START, C.TEST_END)
rows.append(C.summarise(f"{sel_id} gap+momentum", res))
m = res.metrics
print(f"  CAGR {m.cagr * 100:.2f}%  Sharpe {m.sharpe:.2f}  MaxDD {m.max_drawdown * 100:.2f}%"
      f"  Calmar {m.calmar:.2f}  Turn {m.annual_turnover:.2f}x/y"
      f"  Drag {m.cost_drag_annual * 100:.2f}%/y  Names {res.diag['avg_names']:.1f}")
print(f"  signal liveness on TEST: {frac * 100:.2f}% of name-bars flagged, "
      f"{nday:.1f} names/day  (brief §6.3 floor is 5%)")

# --- gross vs net: is the strategy only winning before costs? ---------------
gross = C.backtest(tp, ts, gross=True)
print(f"  GROSS (all costs removed): CAGR {gross.metrics.cagr * 100:.2f}%  "
      f"Sharpe {gross.metrics.sharpe:.2f}")
print(f"  -> net {m.cagr * 100:.2f}% vs gross {gross.metrics.cagr * 100:.2f}%: "
      f"costs cost {(m.cagr - gross.metrics.cagr) * 100:+.2f}pp/yr")

print()
print("=" * 78)
print("TEST (2024-01-01 -> 2026-10-01) — net of 21.92 bps")
print("=" * 78)

# --- ablation: momentum only, no gap filter ---------------------------------
mp, ms = C.windowed(panel, C.TEST_START, C.TEST_END,
                    lambda key: C.momentum_only_score(panel, key=key))
mo = C.backtest(mp, ms)
rows.append(C.summarise("ABLATION momentum-only", mo))
print(f"  ablation momentum-only: CAGR {mo.metrics.cagr * 100:.2f}%  "
      f"Sharpe {mo.metrics.sharpe:.2f}  MaxDD {mo.metrics.max_drawdown * 100:.2f}%")

# --- the AS-SHIPPED variant (V1), reported for completeness ------------------
v1_flag = C.gap_flag(test, C.VARIANTS["V1"]["L"], C.VARIANTS["V1"]["threshold"])
vp, vs = C.score_window(panel, C.TEST_START, C.TEST_END,
                        C.VARIANTS["V1"]["L"], C.VARIANTS["V1"]["threshold"])
v1 = C.backtest(vp, vs)
rows.append(C.summarise("V1 as-shipped L=1", v1))
print(f"  V1 as-shipped (L=1):   CAGR {v1.metrics.cagr * 100:.2f}%  "
      f"Sharpe {v1.metrics.sharpe:.2f}  MaxDD {v1.metrics.max_drawdown * 100:.2f}%")

# --- negative control: random, matched to the SELECTED variant's liveness ----
rand_rows = []
for seed in C.CONTROL_SEEDS:
    rm = C.random_mask_like(sel_flag_full, seed)
    rp, rs = C.windowed(panel, C.TEST_START, C.TEST_END,
                        lambda key, rm=rm: C.score_from_flag(panel, rm, key=key))
    r = C.backtest(rp, rs)
    rand_rows.append(C.summarise(f"random s={seed}", r))
rsh = [r["metrics"].sharpe for r in rand_rows]
rcg = [r["metrics"].cagr for r in rand_rows]
beat = sum(1 for s in rsh if s < m.sharpe)
print(f"  random control (matched to SELECTED n/day {nday:.1f}): "
      f"CAGR {min(rcg) * 100:.2f}%..{max(rcg) * 100:.2f}%  "
      f"Sharpe {min(rsh):.2f}..{max(rsh):.2f}")
print(f"  -> SELECTED beat {beat}/{len(rsh)} random seeds on Sharpe")

# --- nsealgo composite on the SAME TEST window ------------------------------
cp, cs = C.composite_window(panel, C.TEST_START, C.TEST_END)
comp = C.backtest(cp, cs)
rows.append(C.summarise("nsealgo composite", comp))
print(f"  nsealgo composite:      CAGR {comp.metrics.cagr * 100:.2f}%  "
      f"Sharpe {comp.metrics.sharpe:.2f}  MaxDD {comp.metrics.max_drawdown * 100:.2f}%")

# --- buy-and-hold on the SAME TEST window ------------------------------------
bh_r, bh_m, bh_c = C.equal_weight_bh(test)
rows.append({"label": "buy-and-hold (net)", "metrics": bh_m,
             "avg_names": float(test.shape[1])})
print(f"  buy-and-hold (net):    CAGR {bh_m.cagr * 100:.2f}%  "
      f"Sharpe {bh_m.sharpe:.2f}  MaxDD {bh_m.max_drawdown * 100:.2f}%")

print()
print(C.metrics_table(rows))

# --- Gate 3: positive in >=60% of calendar years ---------------------------
yr = C.yearly(res.returns)
pos = int((yr > 0).sum())
print()
print(f"  GOAL.md Gate 3 (positive in >=60% of years): {pos}/{len(yr)} positive "
      f"-> {'PASS' if pos / len(yr) >= 0.60 else 'FAIL'}")
print("  yearly: " + "  ".join(f"{int(y)}:{v * 100:+.1f}%" for y, v in yr.items())
      + "   (2026 is a PARTIAL year: TEST ends 2026-10-01)")

payload = {
    "selected": sel_id, "spec": spec,
    "cagr": m.cagr, "sharpe": m.sharpe, "max_dd": m.max_drawdown,
    "calmar": m.calmar, "turn": m.annual_turnover, "drag": m.cost_drag_annual,
    "names": res.diag["avg_names"], "liveness": frac, "flagged_per_day": nday,
    "gross_cagr": gross.metrics.cagr, "gross_sharpe": gross.metrics.sharpe,
    "momentum_only": {"cagr": mo.metrics.cagr, "sharpe": mo.metrics.sharpe,
                      "max_dd": mo.metrics.max_drawdown},
    "v1_shipped": {"cagr": v1.metrics.cagr, "sharpe": v1.metrics.sharpe,
                   "max_dd": v1.metrics.max_drawdown},
    "random": [{"seed": s, "cagr": r["metrics"].cagr, "sharpe": r["metrics"].sharpe}
               for s, r in zip(C.CONTROL_SEEDS, rand_rows, strict=True)],
    "random_beat": f"{beat}/{len(rsh)}",
    "composite": {"cagr": comp.metrics.cagr, "sharpe": comp.metrics.sharpe,
                  "max_dd": comp.metrics.max_drawdown},
    "buy_hold": {"cagr": bh_m.cagr, "sharpe": bh_m.sharpe,
                 "max_dd": bh_m.max_drawdown},
    "yearly": {int(y): float(v) for y, v in yr.items()},
    "years_positive": f"{pos}/{len(yr)}",
}
with open("test_results.json", "w") as f:
    json.dump(payload, f, indent=2)
print()
print("wrote test_results.json")
