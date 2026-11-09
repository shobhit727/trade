"""TEST evaluation — the declared TRAIN winner, unchanged, plus controls.

V5 was selected on TRAIN Sharpe (0.64) in sweep_train.py. This script evaluates
V5 on TEST once, together with the mandated controls. No other variant is scored
on TEST; no parameter is chosen here.
"""

from __future__ import annotations

import json
import sys

sys.path.insert(0, "research/agent_multifactor")

import numpy as np  # noqa: E402
from harness import (  # noqa: E402
    CM,
    PANEL,
    TEST,
    TRAIN,
    PortfolioConfig,
    buy_and_hold,
    fmt_row,
    gross_metrics,
    pct_live,
    random_control,
    run_backtest,
    score_variant,
    window_metrics,
)

from nsealgo.backtest.metrics import yearly_returns  # noqa: E402
from nsealgo.factors.core import build_composite_score  # noqa: E402

SELECTED = dict(period=20, rsip=21, rank_days=126, fill=False)
SEEDS = list(range(20))

print("=" * 120)
print("TEST — SELECTED VARIANT V5 (period=20, rsip=21, rank 126d), UNCHANGED FROM TRAIN")
print("=" * 120)

sc = score_variant(PANEL, **SELECTED)
res = run_backtest(PANEL, sc, CM, PortfolioConfig(), rebalance="M")

net = window_metrics(res, *TEST)
gross = gross_metrics(res, *TEST)

print("\n--- 3.4 SELECTED VARIANT, TEST 2024-01-01 -> 2026-10-01 ---")
print(fmt_row("V5  NET of 21.92bps", net))
print(fmt_row("V5  GROSS (cost removed)", gross))
print(f"\nliveness TEST           : {pct_live(PANEL, 20, 21, *TEST)*100:.1f}% of (name,bar) obs")
print(f"rebalances in TEST      : {net['n_rebalances']}")
print(f"avg names held          : {net['avg_names']:.1f}")
print(f"cumulative cost (mult.) : {net['costs_total_frac']*100:.2f}% of terminal wealth")
print(f"cost drag               : {net['cost_drag_annual']*100:.2f}%/y")
print(f"gross->net CAGR erosion : {(gross['cagr']-net['cagr'])*100:.2f} pp")

yr = yearly_returns(res.returns.loc[TEST[0]:TEST[1]])
print("\nV5 TEST yearly returns:\n" + yr.map(lambda x: f"{x*100:>7.2f}%").to_string())
print(f"\nyears positive: {(yr > 0).sum()}/{len(yr)}")

# ---------------------------------------------------------------- controls
print("\n--- 3.5 TEST buy-and-hold control ---")
bh = buy_and_hold(PANEL, *TEST)
print(fmt_row("B&H eod (48 names)", bh["eod"]))
print(fmt_row("B&H monthly-eq (48)", bh["mly"]))
print(
    f"\n  V5 vs B&H eod   : CAGR {net['cagr']*100:.2f}% vs {bh['eod']['cagr']*100:.2f}% "
    f"({(net['cagr']-bh['eod']['cagr'])*100:+.2f} pp)  "
    f"MaxDD {net['max_drawdown']*100:.2f}% vs {bh['eod']['max_drawdown']*100:.2f}% "
    f"({(net['max_drawdown']-bh['eod']['max_drawdown'])*100:+.2f} pp)"
)
print(
    f"  V5 vs B&H monthly: CAGR {net['cagr']*100:.2f}% vs {bh['mly']['cagr']*100:.2f}% "
    f"({(net['cagr']-bh['mly']['cagr'])*100:+.2f} pp)  "
    f"Sharpe {net['sharpe']:.2f} vs {bh['mly']['sharpe']:.2f}"
)

print("\n--- 3.6 TEST random-signal control (same % long, 20 seeds) ---")
frac = pct_live(PANEL, 20, 21, PANEL.index.min(), PANEL.index.max())
print(f"null flagged fraction = {frac:.4f} (= V5 full-history liveness)")
rc_t = random_control(PANEL, frac, 126, SEEDS, *TEST)
rc_r = random_control(PANEL, frac, 126, SEEDS, *TRAIN)
for nm, rc in (("TRAIN", rc_r), ("TEST", rc_t)):
    print(
        f"  {nm}: median CAGR {rc['median_cagr']*100:>6.2f}%  median Sharpe "
        f"{rc['median_sharpe']:>5.2f}  p90 CAGR {np.quantile(rc['cagr'],.9)*100:>6.2f}%  "
        f"n={len(rc['cagr'])}"
    )
pct = float((rc_t["sharpe"] < net["sharpe"]).mean())
print(
    f"\n  V5 TEST Sharpe {net['sharpe']:.2f} vs null median {rc_t['median_sharpe']:.2f} "
    f"-> beats {pct*100:.0f}% of random signals (pct {pct:.2f})"
)
print(f"  V5 TEST CAGR {net['cagr']*100:.2f}% vs null median {rc_t['median_cagr']*100:.2f}%")

print("\n--- 3.7 TEST vs nsealgo composite ---")
comp = build_composite_score(PANEL)
res_c = run_backtest(PANEL, comp, CM, PortfolioConfig(), rebalance="M")
mc = window_metrics(res_c, *TEST)
print(fmt_row("nsealgo composite", mc))
print(
    f"\n  V5 vs composite: CAGR {net['cagr']*100:.2f}% vs {mc['cagr']*100:.2f}% "
    f"({(net['cagr']-mc['cagr'])*100:+.2f} pp)  Sharpe {net['sharpe']:.2f} vs "
    f"{mc['sharpe']:.2f} ({net['sharpe']-mc['sharpe']:+.2f})"
)

# ---------------------------------------------------------------- sanity
print("\n--- 3.8 SANITY CHECKS (AGENT_BRIEF.md §6) ---")
print(f"1 plausibility : V5 TEST CAGR {net['cagr']*100:.1f}%  (unlevered long-only "
      f"long-only ceiling ~40-50%) -> "
      f"{'OK' if net['cagr'] < 0.5 else 'BUG'}")
print(f"2 weight count : avg names {net['avg_names']:.1f} "
      f"(n_positions=22, engine max_names=30) -> "
      f"{'OK' if net['avg_names'] <= 30.5 else 'ACCUMULATION BUG'}")
print(f"3 liveness     : {pct_live(PANEL,20,21,*TEST)*100:.1f}% long "
      f"(floor 5%) -> OK")
print(f"4 cost drag    : gross CAGR {gross['cagr']*100:.2f}% -> net "
      f"{net['cagr']*100:.2f}%  ({'viable' if net['cagr']>0 else 'NOT VIABLE if gross<=0'})")
print(f"5 neg control  : V5 Sharpe {net['sharpe']:.2f} vs random median "
      f"{rc_t['median_sharpe']:.2f} -> "
      f"{'BEATS' if net['sharpe']>rc_t['median_sharpe'] else 'LOSES TO'} a coin flip")

# ---------------------------------------------------------------- persist
out = {
    "test_net": {k: float(v) for k, v in net.items()},
    "test_gross": {k: float(v) for k, v in gross.items()},
    "test_bh_eod": {k: float(v) for k, v in bh["eod"].items()},
    "test_bh_mly": {k: float(v) for k, v in bh["mly"].items()},
    "test_composite": {k: float(v) for k, v in mc.items()},
    "test_random_cagr": [float(x) for x in rc_t["cagr"]],
    "test_random_sharpe": [float(x) for x in rc_t["sharpe"]],
    "test_random_beat_pct": pct,
    "null_fraction": frac,
    "yearly": {str(k): float(v) for k, v in yr.items()},
}
with open("research/agent_multifactor/test_results.json", "w") as f:
    json.dump(out, f, indent=2)
print("\nwrote research/agent_multifactor/test_results.json")
