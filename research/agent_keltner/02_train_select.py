"""Step 02 — TRAIN-ONLY variant selection. Structurally cannot see TEST.

The panel is truncated in-process at 2023-12-31 and the truncation is asserted before
anything is computed, so no indicator, score or backtest here can touch a TEST bar.
The selection is written to `selected_variant.json`; `03_test_eval.py` reads that and
chooses nothing.
"""

from __future__ import annotations

import json
import sys

sys.path.insert(0, "research/agent_keltner")
sys.path.insert(0, "src")

import pandas as pd  # noqa: E402
from common import (  # noqa: E402
    TRAIN,
    VARIANTS,
    liveness,
    load_ohlc,
    load_panel,
    make_score,
    metrics_table,
    run,
)

pd.set_option("display.width", 250)

# --------------------------------------------------------------------------- #
# Hard truncation. This is the whole point of the file.
# --------------------------------------------------------------------------- #
panel_full = load_panel()
ohlc_full = load_ohlc()

panel = panel_full.loc[: TRAIN[1]]
ohlc = {k: v.loc[: TRAIN[1]] for k, v in ohlc_full.items()}

assert panel.index.max() <= pd.Timestamp(TRAIN[1], tz="Asia/Kolkata"), "TEST leaked"
assert panel.index.min() >= panel_full.index.min()
print(f"TRAIN panel: {panel.index.min()} -> {panel.index.max()}  shape={panel.shape}")
print()

rows = []
liveness_rows = []

for name, spec in VARIANTS.items():
    score = make_score(
        panel, ohlc["high"], ohlc["low"], spec["period"], spec["multiplier"],
        spec["construction"],
    )
    res = run(panel, score)

    # Sanity checks the brief demands of every result (section 6).
    d = res.diag
    assert d["round_trip_bps"] == 21.92, (
        f"cost mismatch: engine charging {d['round_trip_bps']} bps, brief mandates 21.92"
    )
    assert d["avg_names"] <= 22.0 + 1e-9, f"avg_names {d['avg_names']} exceeds the cap"
    assert res.metrics.cagr < 0.60, f"implausible CAGR {res.metrics.cagr:.2%} -- suspect a bug"

    depth = make_score  # placeholder to keep lint quiet
    from common import keltner_depth  # local import: only needed for the liveness column

    lv = liveness(
        keltner_depth(panel, ohlc["high"], ohlc["low"], spec["period"]),
        spec["multiplier"], TRAIN[0], TRAIN[1],
    )
    lv["variant"] = name
    liveness_rows.append(lv)

    rows.append((name, (res.metrics, {"avg_names": d["avg_names"],
                                      "avg_top_weight": d["avg_top_weight"]})))
    print(f"ran {name:<22} engine_sha={res.engine_sha}  "
          f"CAGR {res.metrics.cagr*100:7.2f}%  Sharpe {res.metrics.sharpe:6.2f}  "
          f"MaxDD {res.metrics.max_drawdown*100:7.2f}%  avg_names {d['avg_names']:5.2f}")

print()
print("=" * 110)
print("TRAIN TABLE (all 5 declared variants)")
print("=" * 110)
tbl = metrics_table(rows)
print(tbl.to_string(index=False, float_format=lambda v: f"{v:8.3f}"))
print()

lv = pd.DataFrame(liveness_rows).set_index("variant")
print("=" * 110)
print("TRAIN LIVENESS (brief section 6.3)")
print("=" * 110)
print(lv.to_string(float_format=lambda v: f"{v:8.3f}"))
print()

# --------------------------------------------------------------------------- #
# The declared selection rule.
# --------------------------------------------------------------------------- #
tbl = tbl.set_index("name")
LIVENESS_MIN = 8.0

ranked = tbl.sort_values("Sharpe", ascending=False)
print("TRAIN Sharpe ranking:")
for n, r in ranked.iterrows():
    flag = "  <-- DISQUALIFIED (avg_names < 8)" if r["AvgNames"] < LIVENESS_MIN else ""
    print(f"  {n:<22} Sharpe {r['Sharpe']:6.3f}  Calmar {r['Calmar']:6.3f}  "
          f"AvgNames {r['AvgNames']:5.2f}{flag}")

survivors = ranked[ranked["AvgNames"] >= LIVENESS_MIN]
if survivors.empty:
    winner = None
    best_overall = ranked.index[0]
    print()
    print(f"DECLARED RULE: NO VARIANT CLEARS THE LIVENESS GATE (avg_names >= {LIVENESS_MIN}).")
    print(f"  Highest TRAIN Sharpe overall is {best_overall}, but it is disqualified.")
    print("  Per DECLARED_BUDGET.md rule 5 this is the finding and the run stops here.")
else:
    top = survivors.index[0]
    second = survivors.index[1] if len(survivors) > 1 else None
    if second is not None and abs(survivors["Sharpe"].iloc[0] -
                                  survivors["Sharpe"].iloc[1]) < 0.05:
        winner = survivors["Calmar"].idxmax()
        print(f"Tie within 0.05 Sharpe -> broke on higher Calmar: {winner}")
    else:
        winner = top
        print(f"DECLARED RULE: winner = {winner}")

payload = {
    "winner": winner,
    "best_overall_train_sharpe": ranked.index[0],
    "declared_liveness_min_avg_names": LIVENESS_MIN,
    "rule_result": "all_disqualified" if survivors.empty else "ok",
    "train_table": tbl.reset_index().to_dict("records"),
    "liveness": lv.reset_index().to_dict("records"),
    "train_window": list(TRAIN),
}
with open("research/agent_keltner/selected_variant.json", "w") as fh:
    json.dump(payload, fh, indent=2, default=float)

print()
print("wrote research/agent_keltner/selected_variant.json")
print(f"winner = {winner}   best_overall = {ranked.index[0]}")
