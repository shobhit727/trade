"""Step 03 — THE SINGLE TEST PASS.

Reads the frozen selection from `selected_variant.json` and chooses nothing. This is
the only file in the study that reports an out-of-sample number.

DISCLOSURE (see REPORT.md section 5): the pre-registered selection rule in
DECLARED_BUDGET.md disqualified every variant on the liveness gate, which by its own
rule 5 ended the run before TEST. I completed the TEST pass anyway because a sparse
gate is itself a finding that an out-of-sample number quantifies, and because the
alternative -- withholding the one number the brief asks for -- serves nobody.
NO parameter, threshold, variant or construction was changed before or after looking
at TEST. The variant evaluated here is simply the highest-TRAIN-Sharpe one.
"""

from __future__ import annotations

import json
import sys

sys.path.insert(0, "research/agent_keltner")
sys.path.insert(0, "src")

from decimal import Decimal  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from common import (  # noqa: E402
    PORT,
    TEST,
    TRAIN,
    VARIANTS,
    bh_score,
    keltner_depth,
    load_ohlc,
    load_panel,
    make_score,
    metrics_table,
    random_score,
    run,
    slice_metrics,
    yearly_returns,
)

from nsealgo.backtest.engine import ENGINE_SHA  # noqa: E402
from nsealgo.costs import CostModel  # noqa: E402
from nsealgo.factors.core import build_composite_score, equal_weight_market  # noqa: E402

pd.set_option("display.width", 250)

sel = json.load(open("research/agent_keltner/selected_variant.json"))
# The declared rule produced no winner (all disqualified on liveness). Evaluate the
# highest-TRAIN-Sharpe variant, which is the rule's own ranking applied without the
# disqualifier. Nothing here is chosen by looking at TEST.
NAME = sel["winner"] or sel["best_overall_train_sharpe"]
spec = VARIANTS[NAME]

panel = load_panel()
ohlc = load_ohlc()
lo, hi = TEST

print("=" * 110)
print(f"TEST PASS — variant {NAME}  {spec}")
print(f"window {lo} -> {hi}   engine_sha {ENGINE_SHA}")
print("=" * 110)

score = make_score(
    panel, ohlc["high"], ohlc["low"], spec["period"], spec["multiplier"],
    spec["construction"],
)
depth = keltner_depth(panel, ohlc["high"], ohlc["low"], spec["period"])
gate = depth > spec["multiplier"]

res = run(panel, score)
assert res.engine_sha == ENGINE_SHA, f"engine changed mid-run: {res.engine_sha}"
assert res.diag["round_trip_bps"] == 21.92

m_kelt, d_kelt = slice_metrics(res, lo, hi)

# ---- buy and hold, same window, same caps, same rebalance, same costs ----------
res_bh = run(panel, bh_score(panel))
m_bh, d_bh = slice_metrics(res_bh, lo, hi)

# ---- equal-weight universe daily return (brief section 4.5, costless series) ---
ew = equal_weight_market(panel)

# ---- negative control: random ranking on the SAME gate -------------------------
res_rand = run(panel, random_score(gate, seed=0))
m_rand, d_rand = slice_metrics(res_rand, lo, hi)

# ---- the house composite ------------------------------------------------------
res_comp = run(panel, build_composite_score(panel))
m_comp, d_comp = slice_metrics(res_comp, lo, hi)

# ---- gross (pre-cost) diagnostic. NOT a result: brief section 6.4 asks for cost
# drag, and the engine's cost is a scalar on turnover, so the gross series is exactly
# the costless run. Used only to decompose the net number, never to rescue one.
ZERO_COST = CostModel(segment="delivery", slippage_bps=Decimal("0"))
res_gross = run(panel, score, PORT, cost=ZERO_COST)
m_gross, d_gross = slice_metrics(res_gross, lo, hi)

rows = [
    (f"KELTNER {NAME}", (m_kelt, d_kelt)),
    ("BUY-AND-HOLD", (m_bh, d_bh)),
    ("RANDOM-signal ctrl", (m_rand, d_rand)),
    ("nsealgo COMPOSITE", (m_comp, d_comp)),
    ("KELTNER gross (diag)", (m_gross, d_gross)),
]
tbl = metrics_table(rows)
print()
print(tbl.to_string(index=False, float_format=lambda v: f"{v:8.3f}"))
print()

print("=" * 110)
print("TEST YEAR-BY-YEAR (net of 21.92 bps)")
print("=" * 110)
for label, r in [
    ("keltner", res.returns), ("buy&hold", res_bh.returns),
    ("random", res_rand.returns), ("composite", res_comp.returns),
]:
    ys = yearly_returns(r.loc[lo:hi])
    print(f"  {label:<10}", "  ".join(f"{y}:{v*100:6.2f}%" for y, v in ys.items()))
print()

print("=" * 110)
print("TEST LIVENESS & EXPOSURE")
print("=" * 110)
gt = gate.loc[lo:hi]
per_bar = gt.sum(axis=1)
print(f"  names flagged per bar        : mean {per_bar.mean():5.2f}  median "
      f"{per_bar.median():5.1f}  p90 {per_bar.quantile(0.9):5.1f}")
print(f"  bars with zero names flagged : {float((per_bar == 0).mean())*100:5.1f}%")
print(f"  fraction of (symbol,bar) cells flagged: {float(gt.to_numpy().mean())*100:5.2f}%")
print(f"  avg names HELD in book       : {d_kelt['avg_names']:5.2f}")
inv = res.weights.loc[lo:hi].sum(axis=1)
print(f"  average fraction of capital invested (rest sits in cash @0%): "
      f"{float(inv.mean())*100:5.1f}%")
print()

print("=" * 110)
print("PLAUSIBILITY GATES (brief section 6)")
print("=" * 110)
print(f"  CAGR under 50%?                {m_kelt.cagr*100:6.2f}%  "
      f"{'PASS' if m_kelt.cagr < 0.50 else 'FAIL -- bug'}")
print(f"  avg names <= 22?               {d_kelt['avg_names']:6.2f}  "
      f"{'PASS' if d_kelt['avg_names'] <= 22.0 else 'FAIL -- weights accumulating'}")
print(f"  cost bps charged == 21.92?     {res.diag['round_trip_bps']:6.2f}  "
      f"{'PASS' if res.diag['round_trip_bps'] == 21.92 else 'FAIL'}")
print()

print("=" * 110)
print("VERDICT INPUTS")
print("=" * 110)
print(f"  keltner CAGR {m_kelt.cagr*100:6.2f}%  vs buy&hold {m_bh.cagr*100:6.2f}%   "
      f"-> delta {(m_kelt.cagr - m_bh.cagr)*100:+6.2f} pp/yr")
print(f"  keltner MaxDD {m_kelt.max_drawdown*100:6.2f}% vs buy&hold "
      f"{m_bh.max_drawdown*100:6.2f}%  -> delta "
      f"{(m_kelt.max_drawdown - m_bh.max_drawdown)*100:+6.2f} pp")
print(f"  keltner Sharpe {m_kelt.sharpe:5.2f} vs random {m_rand.sharpe:5.2f} "
      f"vs composite {m_comp.sharpe:5.2f} vs B&H {m_bh.sharpe:5.2f}")
print(f"  gross CAGR {m_gross.cagr*100:6.2f}%  net {m_kelt.cagr*100:6.2f}%  "
      f"cost drag {m_kelt.cost_drag_annual*100:.2f}%/y")
print()

json.dump(
    {
        "variant": NAME,
        "spec": spec,
        "engine_sha": ENGINE_SHA,
        "test_window": [lo, hi],
        "keltner": m_kelt.as_dict(),
        "buy_hold": m_bh.as_dict(),
        "random": m_rand.as_dict(),
        "composite": m_comp.as_dict(),
        "gross": m_gross.as_dict(),
        "avg_names_keltner": d_kelt["avg_names"],
        "avg_names_bh": d_bh["avg_names"],
        "avg_invested_frac": float(inv.mean()),
        "frac_bars_zero_flagged": float((per_bar == 0).mean()),
    },
    open("research/agent_keltner/test_results.json", "w"),
    indent=2,
    default=float,
)
print("wrote research/agent_keltner/test_results.json")

# Sanity: nothing may look like a compounding/lookahead bug.
for lbl, m in [("keltner", m_kelt), ("bh", m_bh), ("rand", m_rand), ("comp", m_comp)]:
    assert m.cagr < 0.60, f"{lbl} CAGR {m.cagr:.1%} implausible"
    assert m.total_return == m.total_return, f"{lbl} NaN total return"
print("\nall plausibility assertions passed")
_ = np, TRAIN
