"""Step 2 — TRAIN only. All 5 declared variants + the ablation controls.

Selection happens here and ONLY here. TEST is never read by this script.

Every scored book goes through ``common.windowed`` / ``score_window`` so the 126d
momentum key is built on the FULL panel and only then sliced -- otherwise the first
126 bars of TRAIN would hold nothing (defect found in s4_verify, now fixed).
"""

from __future__ import annotations

import json

import common as C

panel, symbols, _ = C.load_all()
C.align(panel)
train = C.slice_panel(panel, C.TRAIN_START, C.TRAIN_END)
print(f"TRAIN window {C.TRAIN_START.date()} -> {C.TRAIN_END.date()}  "
      f"bars={len(train)}  symbols={train.shape[1]}")
print()

rows = []

# --- the 5 declared variants ------------------------------------------------
for vid, spec in C.VARIANTS.items():
    tp, score = C.score_window(panel, C.TRAIN_START, C.TRAIN_END,
                               spec["L"], spec["threshold"])
    res = C.backtest(tp, score)
    frac, nday = C.liveness(C.gap_flag(train, spec["L"], spec["threshold"]),
                            C.TRAIN_START, C.TRAIN_END)
    label = f"{vid} L={spec['L']} thr={spec['threshold']:.3f}"
    rows.append({
        "label": label,
        "metrics": res.metrics,
        "avg_names": res.diag["avg_names"],
        "live_frac": frac,
        "flagged_per_day": nday,
    })
    print(f"  ran {label:<24} names={res.diag['avg_names']:.1f} "
          f"CAGR={res.metrics.cagr * 100:>7.2f}%  Sharpe={res.metrics.sharpe:>6.2f}")

print()
print("=" * 78)
print("TRAIN — 5 DECLARED VARIANTS  (all net of 21.92 bps)")
print("=" * 78)
print(C.metrics_table(rows))

# --- ablation: momentum only, no gap filter at all --------------------------
print()
print("=" * 78)
print("TRAIN — ABLATION: momentum-only (NO gap filter)")
print("=" * 78)
mp, ms = C.windowed(panel, C.TRAIN_START, C.TRAIN_END,
                    lambda key: C.momentum_only_score(panel, key=key))
mo = C.backtest(mp, ms)
print(C.metrics_table([C.summarise("momentum-only", mo)]))

# --- negative control: random mask, same per-day count as the SHIPPED signal -
print()
print("=" * 78)
print("TRAIN — NEGATIVE CONTROL: random names, same n/day as V1")
print("=" * 78)
v1_flag = C.gap_flag(train, C.VARIANTS["V1"]["L"], C.VARIANTS["V1"]["threshold"])
v1_flag_full = C.gap_flag(panel, C.VARIANTS["V1"]["L"], C.VARIANTS["V1"]["threshold"])
rand_rows = []
for seed in C.CONTROL_SEEDS:
    rm_full = C.random_mask_like(v1_flag_full, seed)
    rp, rs = C.windowed(panel, C.TRAIN_START, C.TRAIN_END,
                        lambda key, rm=rm_full: C.score_from_flag(panel, rm, key=key))
    r = C.backtest(rp, rs)
    rand_rows.append(C.summarise(f"random seed={seed}", r))
    print(f"  seed {seed:>4}  CAGR={r.metrics.cagr * 100:>7.2f}%  "
          f"Sharpe={r.metrics.sharpe:>6.2f}  names={r.diag['avg_names']:.1f}")
print()
print(C.metrics_table(rand_rows))

# --- reference: nsealgo composite on the same TRAIN window ------------------
cp, cs = C.composite_window(panel, C.TRAIN_START, C.TRAIN_END)
comp = C.backtest(cp, cs)
print()
print(C.metrics_table([C.summarise("nsealgo composite", comp)]))

# --- reference: buy-and-hold -------------------------------------------------
bh_r, bh_m, bh_c = C.equal_weight_bh(train)
print(C.metrics_table([{"label": "buy-and-hold (net)", "metrics": bh_m,
                       "avg_names": float(train.shape[1])}]))

# --- SELECTION (declared rule: max TRAIN Sharpe, ties -> lower turnover) -----
ranked = sorted(rows, key=lambda r: -r["metrics"].sharpe)
best = ranked[0]
print()
print("=" * 78)
print("SELECTION (TRAIN Sharpe, net of costs) — recorded before TEST is touched")
print("=" * 78)
print(f"  SELECTED: {best['label']}")
print(f"  TRAIN CAGR  {best['metrics'].cagr * 100:.2f}%   "
      f"Sharpe {best['metrics'].sharpe:.2f}   "
      f"MaxDD {best['metrics'].max_drawdown * 100:.2f}%   "
      f"Turn {best['metrics'].annual_turnover:.2f}x/y   "
      f"Drag {best['metrics'].cost_drag_annual * 100:.2f}%/y")
print(f"  runner-up: {ranked[1]['label']}  Sharpe {ranked[1]['metrics'].sharpe:.2f}")
print(f"  momentum-only Sharpe {mo.metrics.sharpe:.2f}   "
      f"composite Sharpe {comp.metrics.sharpe:.2f}   "
      f"buy-and-hold Sharpe {bh_m.sharpe:.2f}")

payload = {
    "selected": best["label"],
    "selected_id": best["label"].split()[0],
    "variants": [
        {"label": r["label"], "cagr": r["metrics"].cagr,
         "sharpe": r["metrics"].sharpe, "max_dd": r["metrics"].max_drawdown,
         "calmar": r["metrics"].calmar, "turn": r["metrics"].annual_turnover,
         "drag": r["metrics"].cost_drag_annual, "names": r["avg_names"],
         "live_frac": r["live_frac"]}
        for r in rows
    ],
    "momentum_only": {"cagr": mo.metrics.cagr, "sharpe": mo.metrics.sharpe,
                      "max_dd": mo.metrics.max_drawdown,
                      "calmar": mo.metrics.calmar,
                      "turn": mo.metrics.annual_turnover,
                      "drag": mo.metrics.cost_drag_annual,
                      "names": mo.diag["avg_names"]},
    "random": [{"seed": s, "cagr": r["metrics"].cagr, "sharpe": r["metrics"].sharpe}
               for s, r in zip(C.CONTROL_SEEDS, rand_rows, strict=True)],
    "composite": {"cagr": comp.metrics.cagr, "sharpe": comp.metrics.sharpe,
                  "max_dd": comp.metrics.max_drawdown,
                  "calmar": comp.metrics.calmar,
                  "turn": comp.metrics.annual_turnover,
                  "drag": comp.metrics.cost_drag_annual,
                  "names": comp.diag["avg_names"]},
    "buy_hold": {"cagr": bh_m.cagr, "sharpe": bh_m.sharpe,
                 "max_dd": bh_m.max_drawdown, "calmar": bh_m.calmar},
    "selection_rule": "max TRAIN Sharpe net of 21.92bps; ties -> lower turnover",
    "round_trip_bps": mo.diag["round_trip_bps"],
    "warmup_fix": "score built on full panel then sliced (s4_verify defect)",
}
with open("train_results.json", "w") as f:
    json.dump(payload, f, indent=2)
print()
print("wrote train_results.json  (TEST untouched by this script)")
