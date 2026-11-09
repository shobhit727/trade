"""TRAIN-only selection across the 5 DECLARED variants (brief section 4).

Selection rule was declared in REPORT.md section 2 BEFORE any backtest ran:
    highest TRAIN Sharpe; ties broken by lower TRAIN MaxDD.

Nothing here touches TEST. The winner is frozen to selected_variant.json together
with the engine_sha it was selected under, so 03 can assert nothing moved.
"""

from __future__ import annotations

import json

from common import (
    ENGINE_SHA,
    HDR,
    avg_names,
    buy_and_hold,
    full_panel,
    invested_frac,
    liveness,
    row,
    run,
    tmr_score,
    train_slice,
)

VARIANTS = {
    "V1": (40, 1.5),
    "V2": (20, 1.5),
    "V3": (60, 1.5),
    "V4": (40, 1.0),
    "V5": (40, 2.0),
}

panel = full_panel()
tr_panel = train_slice(panel)

print("Signal scores are computed on the FULL panel so the 300-bar z window is")
print("saturated at TRAIN start, then sliced. Nothing is computed forward-looking.\n")

results = {}
print(HDR)
for name, (slow, entry) in VARIANTS.items():
    score = tmr_score(panel, slow, entry)
    tr_score = train_slice(score)
    # Drop bars with no flagged name at all: the engine has nothing to do there and
    # they would otherwise dilute the daily-return series with exact zeros.
    live = liveness(tr_panel, slow, entry)
    res = run(tr_panel, tr_score, label=f"TRAIN {name}")
    results[name] = {
        "slow": slow,
        "entry": entry,
        "metrics": res.metrics,
        "returns": res.returns,
        "equity": res.equity,
        "costs_paid": res.costs_paid,
        "live_frac": live,
        "avg_names": avg_names(res),
        "invested": invested_frac(res),
    }
    print(
        row(
            f"TRAIN {name} (s{slow},e{entry})",
            res.metrics,
            f"live {live * 100:.1f}%, names {avg_names(res):.1f}, inv {invested_frac(res) * 100:.0f}%",
        )
    )

bh = buy_and_hold(tr_panel, "TRAIN buy_and_hold")
print(
    row(
        "TRAIN buy-and-hold",
        bh["metrics"],
        f"whole universe, net {bh['round_trip_bps']:.2f}bps",
    )
)

# ---- selection (declared rule) ------------------------------------------------
winner = max(
    results.items(),
    key=lambda kv: (kv[1]["metrics"].sharpe, -kv[1]["metrics"].max_drawdown),
)
wname = winner[0]
slow, entry = VARIANTS[wname]
print()
print(f"SELECTED (TRAIN Sharpe {winner[1]['metrics'].sharpe:.3f}) -> {wname} "
      f"slow={slow} entry={entry}")

frozen = {
    "variant": wname,
    "slow": slow,
    "entry": entry,
    "mom_days": 126,
    "z_window": 300,
    "selected_on": "TRAIN 2016-01-01..2023-12-31",
    "rule": "max TRAIN Sharpe, tie-break lower TRAIN MaxDD",
    "train_sharpe": float(winner[1]["metrics"].sharpe),
    "train_cagr": float(winner[1]["metrics"].cagr),
    "train_maxdd": float(winner[1]["metrics"].max_drawdown),
    "engine_sha": ENGINE_SHA,
}
with open("selected_variant.json", "w") as fh:
    json.dump(frozen, fh, indent=2)

with open("train_results.json", "w") as fh:
    json.dump(
        {
            name: {
                "slow": r["slow"],
                "entry": r["entry"],
                "cagr": float(r["metrics"].cagr),
                "sharpe": float(r["metrics"].sharpe),
                "calmar": float(r["metrics"].calmar),
                "max_drawdown": float(r["metrics"].max_drawdown),
                "total_return": float(r["metrics"].total_return),
                "annual_turnover": float(r["metrics"].annual_turnover),
                "cost_drag_annual": float(r["metrics"].cost_drag_annual),
                "live_frac": r["live_frac"],
                "avg_names": r["avg_names"],
                "invested": r["invested"],
            }
            for name, r in results.items()
        }
        | {
            "buy_and_hold": {
                "cagr": float(bh["metrics"].cagr),
                "sharpe": float(bh["metrics"].sharpe),
                "max_drawdown": float(bh["metrics"].max_drawdown),
            }
        },
        fh,
        indent=2,
    )

print("wrote selected_variant.json, train_results.json")
