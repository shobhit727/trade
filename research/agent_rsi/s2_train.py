"""Step 2 — TRAIN-only selection across the 5 declared variants.

TEST is not loaded here in any form. The selection rule was declared in REPORT.md
before this ran: highest TRAIN Sharpe among variants with TRAIN MaxDD >= -25%, ties
broken by Calmar. The winner is written to selected_variant.json and frozen.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
from common import (
    CONFIG,
    TEST_END,
    TRAIN_END,
    TRAIN_START,
    build_score,
    eligible_counts,
    header,
    load_panels,
    row,
    rsi_panel,
    run_variant,
    signal_panel,
    yearly_returns,
)

# The 5 variants declared in REPORT.md section 2. This list is the budget.
VARIANTS = [
    dict(name="V1_cat_14_30_deepest_M", period=14, lower=30.0, rank_by="deepest", rebalance="M"),
    dict(name="V2_cat_14_30_mom126_M", period=14, lower=30.0, rank_by="mom126", rebalance="M"),
    dict(name="V3_wide_14_40_deepest_M", period=14, lower=40.0, rank_by="deepest", rebalance="M"),
    dict(name="V4_fast_6_30_deepest_M", period=6, lower=30.0, rank_by="deepest", rebalance="M"),
    dict(name="V5_cat_14_30_deepest_W", period=14, lower=30.0, rank_by="deepest", rebalance="W"),
]
assert len(VARIANTS) == 5, "parameter budget is 5 variants"

DD_FLOOR = -0.25

p = load_panels()
close_all = p.close
close = close_all.loc[TRAIN_START:TRAIN_END]

# RSI computed on the FULL history then sliced — the indicator needs 2008..onwards of
# lookback, and computing it only from 2016 would discard legitimate warm-up bars. The
# slice guarantees no bar after TRAIN_END can influence a TRAIN decision.
cache: dict[int, pd.DataFrame] = {}

results = []
print(header("TRAIN 2016-01-01 -> 2023-12-29 — all 5 declared variants (net of 21.92 bps)"))
for v in VARIANTS:
    per = v["period"]
    if per not in cache:
        cache[per] = rsi_panel(close_all, per)
    rsi = cache[per]
    score_all = build_score(close_all, rsi, v["lower"], v["rank_by"])
    score = score_all.loc[TRAIN_START:TRAIN_END]

    sig = signal_panel(rsi, v["lower"]).loc[TRAIN_START:TRAIN_END]
    n_fin = int((~np.isnan(rsi.loc[TRAIN_START:TRAIN_END])).to_numpy().sum())
    long_frac = float((sig > 0).to_numpy().sum()) / n_fin

    run = run_variant(v["name"], close, score, rebalance=v["rebalance"])
    ec = eligible_counts(score_all.loc[TRAIN_START:TRAIN_END], v["rebalance"])
    results.append(
        dict(
            **v,
            cagr=run.metrics.cagr,
            sharpe=run.metrics.sharpe,
            sortino=run.metrics.sortino,
            maxdd=run.metrics.max_drawdown,
            calmar=run.metrics.calmar,
            turnover=run.metrics.annual_turnover,
            cost_drag=run.metrics.cost_drag_annual,
            trades=run.metrics.trades_per_year,
            avg_names=run.avg_names,
            long_frac=long_frac,
            eligible=ec,
            equity=run.equity,
            returns=run.returns,
        )
    )
    print(row(v["name"], run))
    print(
        f"{'':<26} long_frac {long_frac * 100:>6.2f}%   eligible names per rebalance: "
        f"min {ec['min']}  median {ec['median']:.0f}  mean {ec['mean']:.1f}  "
        f"max {ec['max']}  at/above 22-cap on {ec['frac_at_or_above_cap'] * 100:.0f}% "
        f"of rebalances"
    )

print(header("TRAIN YEARLY RETURNS"))
for r in results:
    yr = yearly_returns(r["returns"])
    pos = int((yr > 0).sum())
    cells = "  ".join(f"{int(y)}:{v * 100:>6.1f}%" for y, v in yr.items())
    print(f"{r['name']:<26} +ve {pos}/{len(yr)}   {cells}")

print(header("SELECTION (rule declared in advance: max TRAIN Sharpe, DD floor -25%)"))
ok = [r for r in results if r["maxdd"] >= DD_FLOOR]
pool = ok if ok else results
chosen = max(pool, key=lambda r: (r["sharpe"], r["calmar"]))
if not ok:
    print(f"  NOTE: no variant met the {DD_FLOOR:.0%} drawdown floor; fell back to max Sharpe.")
for r in results:
    mark = " <= SELECTED" if r["name"] == chosen["name"] else ""
    flag = "" if r["maxdd"] >= DD_FLOOR else "  [DD floor fail]"
    print(
        f"  {r['name']:<26} Sharpe {r['sharpe']:>6.2f}  MaxDD {r['maxdd'] * 100:>7.2f}%  "
        f"Calmar {r['calmar']:>6.2f}  CAGR {r['cagr'] * 100:>7.2f}%{flag}{mark}"
    )

print(header("TRAIN-DIAGNOSTIC: is the book rank-driven or eligibility-driven?"))
print("  When eligible names <= 22 the engine buys EVERY flagged name, so the ranking")
print("  convention cannot matter. Only a threshold wide enough to clear 22 does.")
for r in results:
    print(
        f"  {r['name']:<26} median eligible {r['eligible']['median']:>5.1f}  "
        f"max {r['eligible']['max']:>3d}  -> rank binds on "
        f"{r['eligible']['frac_at_or_above_cap'] * 100:>5.1f}% of rebalances"
    )

payload = {k: v for k, v in chosen.items() if k not in ("equity", "returns")}
payload["all"] = [
    {k: v for k, v in r.items() if k not in ("equity", "returns")} for r in results
]
payload["dd_floor"] = DD_FLOOR
payload["used_pool"] = "dd_ok" if ok else "fallback_all"
payload["train_long_frac"] = chosen["long_frac"]
with open("selected_variant.json", "w") as f:
    json.dump(payload, f, indent=2, default=str)
print("\n>> wrote selected_variant.json")
print(f">> FROZEN FOR TEST: {json.dumps({k: chosen[k] for k in ('name', 'period', 'lower', 'rank_by', 'rebalance')})}")

_ = (TEST_END, CONFIG)  # keep the protocol windows imported and explicit
