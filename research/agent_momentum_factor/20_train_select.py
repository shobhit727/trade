"""20 — TRAIN sweep of the 5 declared variants, then the declared TRAIN-only selection.

TEST is NOT touched here. Selection rule (declared in REPORT.md §2 before any run):
highest TRAIN Sharpe, tie-break shallowest TRAIN MaxDD.
"""

from __future__ import annotations

import json

import common

panel, symbols, _ = common.load_panel()

rows = []
for v in common.VARIANTS:
    score = common.build_score(panel, v)
    res = common.run(panel, score, v, common.TRAIN_START, common.TRAIN_END)
    row = common.metrics_row(v.tag, res.metrics)
    row["avg_names"] = res.diag["avg_names"]
    row["max_weight"] = res.diag["avg_top_weight"]
    rows.append(row)
    print(f"{v.tag} TRAIN  {res.summary()}")

# TRAIN buy-and-hold, same window, same costs — the beta yardstick.
_, _, bh_m, _ = common.benchmark_buy_hold(panel, common.TRAIN_START, common.TRAIN_END)
bh = common.metrics_row("BH", bh_m)
print(f"\nBH  TRAIN  {bh_m.fmt()}")
rows.append(bh)

# ---- declared selection rule
cands = [r for r in rows if r["tag"] != "BH"]
cands_sorted = sorted(cands, key=lambda r: (-r["sharpe"], r["maxdd"]))
selected = cands_sorted[0]["tag"]
ties = [r["tag"] for r in cands
        if abs(r["sharpe"] - cands_sorted[0]["sharpe"]) < 1e-12]

print("\n--- TRAIN table (net of 21.92 bps all-in) ---")
print(common.fmt_table(rows, ["tag", "cagr", "sharpe", "maxdd", "calmar", "turnover",
                              "cost_drag", "avg_names"]))
print(f"\nranked by TRAIN Sharpe: "
      f"{[(r['tag'], round(r['sharpe'], 3)) for r in cands_sorted]}")
print(f"SELECTED ON TRAIN: {selected}   (ties at the top: {ties})")
print("TRAIN edge vs buy-and-hold, per variant (pp/yr):")
for r in cands:
    print(f"  {r['tag']}: {(r['cagr'] - bh['cagr']) * 100:+.2f}")
print(f"  BH : {bh['cagr'] * 100:+.2f} CAGR")

with open(f"{common.OUT_DIR}/20_train.json", "w") as f:
    json.dump({"rows": rows, "selected": selected,
               "selection_rule": "max TRAIN Sharpe, tie-break shallowest TRAIN MaxDD",
               "budget": [v.tag for v in common.VARIANTS]}, f, indent=2)
print(f"\nwrote {common.OUT_DIR}/20_train.json")
