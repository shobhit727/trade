"""Step 20 — TRAIN-window selection over the 5 declared variants.

SELECTION RULE (declared before this ran, and fixed):
    highest TRAIN Sharpe; ties broken by the SHALLOWEST TRAIN MaxDD.
    (`max_drawdown` is stored negative, so "shallowest" == largest value ==
     `ascending=False` on that column. Fixed here after review: the original
     docstring said "lower TRAIN MaxDD", which under the negative sign convention
     reads backwards. No outcome changed — V1's TRAIN Sharpe is the unique max.)
    Only the winner is ever run on TEST.

TEST data is not touched in this file — the panel slice handed to `run_backtest`
ends 2023-12-31 and the score panel is built from that same slice.
"""

from __future__ import annotations

import json
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "research/agent_cross_sectional")

import pandas as pd  # noqa: E402
from common import (  # noqa: E402
    COST,
    PORTFOLIO,
    TEST_END,
    TRAIN_END,
    TRAIN_START,
    VARIANTS,
    build_score,
    diagnostics,
    liveness,
    metrics_table,
    run_backtest,
)

from nsealgo.backtest.engine import _rebalance_dates  # noqa: E402
from nsealgo.data.loader import load_universe  # noqa: E402

print("DECLARED PARAMETER BUDGET — exactly 5 variants, no more will be run:")
for v in VARIANTS:
    print(f"  {v}   [{v.note}]")
print("\nSELECTION RULE: max TRAIN Sharpe, tie-break shallowest TRAIN MaxDD")
print(f"TRAIN window: {TRAIN_START.date()} .. {TRAIN_END.date()}")
print(f"cost model  : {COST}")
print(f"portfolio   : {PORTFOLIO}\n")

panel, symbols, _ = load_universe("data/nse")

# Guard: hard-slice to TRAIN. Nothing downstream can see 2024+.
train = panel.loc[(panel.index >= TRAIN_START) & (panel.index <= TRAIN_END)]
assert train.index.max() <= TRAIN_END, "TRAIN leak guard"
assert train.index.max() < pd.Timestamp("2024-01-01", tz="Asia/Kolkata")
print(f"TRAIN panel: {train.shape}  {train.index[0].date()} .. {train.index[-1].date()}")
print("NOTE: factor warm-up uses only bars inside this slice, so the first "
      "~126 TRAIN bars are cold-start. Costed, honest, unchanged.\n")

rows = []
results = {}
for v in VARIANTS:
    score, sig = build_score(train, v.period, v.threshold, v.rank_days)
    res = run_backtest(train, score, COST, PORTFOLIO, v.rebalance)
    results[v.tag] = res

    # How binding is the strategy's threshold? Eligible = signal>0 count per rebalance.
    rb = _rebalance_dates(train.index, v.rebalance)
    elig = sig.loc[rb].gt(0).sum(axis=1)
    pct_saturated = float((elig >= PORTFOLIO.n_positions).mean())

    print(f"--- {v}  [{v.note}]")
    print(liveness(sig, "signal liveness"))
    print(f"    eligible/rebalance     : mean {elig.mean():.1f}  "
          f"min {int(elig.min())}  max {int(elig.max())}  "
          f"({pct_saturated * 100:.0f}% of rebalances have >= {PORTFOLIO.n_positions} eligible)")
    print(diagnostics(res))
    print(f"    CAGR {res.metrics.cagr * 100:6.2f}%  Sharpe {res.metrics.sharpe:5.2f}  "
          f"MaxDD {res.metrics.max_drawdown * 100:7.2f}%  "
          f"Calmar {res.metrics.calmar:5.2f}  CostDrag {res.metrics.cost_drag_annual * 100:.2f}%/y")
    print()

    rows.append(
        {
            "tag": v.tag, "period": v.period, "threshold": v.threshold,
            "rank_days": v.rank_days, "rebalance": v.rebalance,
            "cagr": res.metrics.cagr, "sharpe": res.metrics.sharpe,
            "maxdd": res.metrics.max_drawdown, "calmar": res.metrics.calmar,
            "turnover": res.metrics.annual_turnover,
            "cost_drag": res.metrics.cost_drag_annual,
            "avg_names": res.diag["avg_names"],
            "mean_eligible": float(elig.mean()),
        }
    )

df = pd.DataFrame(rows)
print("=" * 78)
print("TRAIN SUMMARY (all 5 declared variants)")
print("=" * 78)
print(df.to_string(index=False, float_format=lambda x: f"{x:9.3f}"))
print()

# `maxdd` is negative, so descending on it == shallowest drawdown first.
best = df.sort_values(["sharpe", "maxdd"], ascending=[False, False]).iloc[0]
print(f"SELECTED ON TRAIN: {best['tag']}  "
      f"(Sharpe {best['sharpe']:.2f}, MaxDD {best['maxdd'] * 100:.2f}%)")

out = {
    "declared_variants": [
        {"tag": v.tag, "period": v.period, "threshold": v.threshold,
         "rank_days": v.rank_days, "rebalance": v.rebalance, "note": v.note}
        for v in VARIANTS
    ],
    "train_rows": rows,
    "selected": best["tag"],
}
with open("research/agent_cross_sectional/20_train.json", "w") as fh:
    json.dump(out, fh, indent=2, default=float)
print("wrote research/agent_cross_sectional/20_train.json")

print()
print(metrics_table([(r["tag"], results[r["tag"]].metrics) for r in rows]))
assert TEST_END is not None
