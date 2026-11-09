"""Step 3 — TEST window. Touched exactly once, with the TRAIN-frozen winner V3.

Order is deliberate: the primary out-of-sample number is computed and written to disk
*before* any comparator or diagnostic runs, so it cannot have influenced anything else.
Nothing here selects a parameter — the winner was frozen in `selected_variant.json`.
"""

from __future__ import annotations

import json

import numpy as np
from common import (
    CONFIG,
    COST,
    TEST_END,
    TEST_START,
    build_composite_score,
    build_score,
    buy_and_hold,
    eligible_counts,
    equal_weight_score,
    header,
    load_panels,
    random_control,
    row,
    rsi_panel,
    run_variant,
    signal_panel,
    yearly_returns,
)

FROZEN = json.load(open("selected_variant.json"))
TRAIN_LONG_FRAC = FROZEN["train_long_frac"]

p = load_panels()
close_all = p.close
close = close_all.loc[TEST_START:TEST_END]

rsi_all = rsi_panel(close_all, FROZEN["period"])
score_all = build_score(close_all, rsi_all, FROZEN["lower"], FROZEN["rank_by"])
score = score_all.loc[TEST_START:TEST_END]

print(header("PRIMARY OOS RESULT — TEST 2024-01-01 -> 2026-10-01 (frozen V3, never tuned on TEST)"))
print(f"  strategy : RSI({FROZEN['period']}) < {FROZEN['lower']}, buy most-oversold first, "
      f"{FROZEN['rebalance']}onthly rebalance")
print(f"  selected on TRAIN: Sharpe {FROZEN['sharpe']:.2f}  CAGR {FROZEN['cagr'] * 100:.2f}%  "
      f"MaxDD {FROZEN['maxdd'] * 100:.2f}%")
print(f"  bars={len(close)}  symbols={close.shape[1]}  net of {FROZEN.get('rt_bps', 21.92)} bps")

primary = run_variant(FROZEN["name"], close, score, rebalance=FROZEN["rebalance"])
m = primary.metrics

sig_test = signal_panel(rsi_all, FROZEN["lower"]).loc[TEST_START:TEST_END]
n_fin = int((~np.isnan(rsi_all.loc[TEST_START:TEST_END])).to_numpy().sum())
test_long_frac = float((sig_test > 0).to_numpy().sum()) / n_fin
ec = eligible_counts(score, FROZEN["rebalance"])

lines = []
lines.append("PRIMARY OOS RESULT (TEST 2024-01-01 -> 2026-10-01)")
lines.append(f"variant: {FROZEN['name']}  (frozen on TRAIN, Sharpe {FROZEN['sharpe']:.2f})")
lines.append(f"bars={len(close)}  symbols={close.shape[1]}")
lines.append(f"CAGR            {m.cagr * 100:.2f}%")
lines.append(f"Sharpe          {m.sharpe:.2f}")
lines.append(f"Sortino         {m.sortino:.2f}")
lines.append(f"MaxDD           {m.max_drawdown * 100:.2f}%  ({m.max_drawdown_days}d)")
lines.append(f"Calmar          {m.calmar:.2f}")
lines.append(f"Volatility      {m.volatility * 100:.2f}%")
lines.append(f"Turnover        {m.annual_turnover:.2f}x/yr")
lines.append(f"Cost drag       {m.cost_drag_annual * 100:.2f}%/yr")
lines.append(f"Trades          {m.trades_per_year:.1f}/yr")
lines.append(f"Avg names held  {primary.avg_names:.1f}")
lines.append(f"Bar long frac   {test_long_frac * 100:.2f}%  (TRAIN-frozen target {TRAIN_LONG_FRAC * 100:.2f}%)")
lines.append(f"Eligible/rebal  min {ec['min']}  median {ec['median']:.0f}  mean {ec['mean']:.1f}  max {ec['max']}")
lines.append(f"Cumulative cost {m.cost_drag_annual * (len(close) / 244) * 100:.2f}% over the window")
yr = yearly_returns(primary.returns)
lines.append(f"Positive years  {int((yr > 0).sum())}/{len(yr)}  " +
             "  ".join(f"{int(y)}:{v * 100:.1f}%" for y, v in yr.items()))
with open("PRIMARY_TEST_RESULT.txt", "w") as f:
    f.write("\n".join(lines) + "\n")
print("\n".join(lines))
print("\n>> wrote PRIMARY_TEST_RESULT.txt (before any comparator ran)")

# --------------------------------------------------------------------------- #
# Comparators
# --------------------------------------------------------------------------- #
print(header("TEST COMPARATORS — identical window, identical engine, identical costs"))
bh = buy_and_hold(close)
print(row("buy_and_hold EW (brief)", bh))
ewb = run_variant("equal_weight_book", close, equal_weight_score(close))
print(row("equal_weight_book (engine)", ewb))
comp = build_composite_score(close_all).loc[TEST_START:TEST_END]
compr = run_variant("nsealgo_composite", close, comp, rebalance="M")
print(row("nsealgo_composite", compr))
print(row("RSI V3 (this strategy)", primary))

print(header("HEAD TO HEAD vs BUY-AND-HOLD"))
print(f"  CAGR   strategy {m.cagr * 100:>7.2f}%   B&H {bh.metrics.cagr * 100:>7.2f}%   "
      f"-> {'' if m.cagr >= bh.metrics.cagr else 'WORSE'} by "
      f"{abs(m.cagr - bh.metrics.cagr) * 100:.2f} pp")
print(f"  Sharpe strategy {m.sharpe:>7.2f}    B&H {bh.metrics.sharpe:>7.2f}    "
      f"-> {'' if m.sharpe >= bh.metrics.sharpe else 'WORSE'} by "
      f"{abs(m.sharpe - bh.metrics.sharpe):.2f}")
print(f"  MaxDD  strategy {m.max_drawdown * 100:>7.2f}%   B&H {bh.metrics.max_drawdown * 100:>7.2f}%   "
      f"-> {'BETTER (shallower)' if m.max_drawdown > bh.metrics.max_drawdown else 'WORSE (deeper)'} by "
      f"{abs(m.max_drawdown - bh.metrics.max_drawdown) * 100:.2f} pp")
print(f"  Calmar strategy {m.calmar:>7.2f}    B&H {bh.metrics.calmar:>7.2f}")
print("  B&H yearlies: " + "  ".join(f"{int(y)}:{v * 100:.1f}%" for y, v in yearly_returns(bh.returns).items()))

print(header("GROSS vs NET (cost stress, identical signals — GOAL.md gate 4)"))
from nsealgo.backtest.engine import run_backtest  # noqa: E402
from nsealgo.costs import STRESS_MODELS  # noqa: E402

gross = None
for nm, cm in (
    ("zero_cost (gross)", STRESS_MODELS["zero_cost"]),
    ("base 5bps/side", COST),
    ("double_slippage", STRESS_MODELS["double_slippage"]),
    ("triple_slippage", STRESS_MODELS["triple_slippage"]),
):
    res = run_backtest(close, score, cm, CONFIG, rebalance=FROZEN["rebalance"])
    if gross is None:
        gross = res.metrics.cagr
    print(
        f"  {nm:<20} CAGR {res.metrics.cagr * 100:>7.2f}%  Sharpe {res.metrics.sharpe:>6.2f}  "
        f"cost_drag {res.metrics.cost_drag_annual * 100:>5.2f}%/y  "
        f"rt_bps {res.diag['round_trip_bps']:>6.2f}"
    )
print(f"  -> gross {gross * 100:.2f}%  net {m.cagr * 100:.2f}%  "
      f"cost drag {(gross - m.cagr) * 100:.2f} pp/yr")
print(f"  -> viability must be judged against CASH, not zero: gross {gross * 100:.2f}% vs the "
      f"6.50% T-bill Sharpe is applied against")
print(f"     {'PASSES only because the book is under-invested' if gross > 0.065 else 'FAILS: gross is below the risk-free rate, so the signal is negative-excess BEFORE costs'}")

print(header("RANDOM-SIGNAL NEGATIVE CONTROL (same TRAIN-frozen long fraction)"))
rc = random_control(
    close_all, TRAIN_LONG_FRAC, FROZEN["rebalance"], n_seeds=50,
    window=(TEST_START, TEST_END),
)
print(f"  50 seeds, Bernoulli({TRAIN_LONG_FRAC * 100:.2f}%) eligibility, ranked by 126d momentum,")
print("  identical engine / caps / cash / turnover budget / 21.92 bps costs")
print(
    f"  random CAGR   mean {rc['cagr_mean'] * 100:>7.2f}%  median {rc['cagr_median'] * 100:>7.2f}%"
    f"  p05 {rc['cagr_p05'] * 100:>7.2f}%  p95 {rc['cagr_p95'] * 100:>7.2f}%"
)
print(
    f"  random Sharpe mean {rc['sharpe_mean']:>6.2f}  p05 {rc['sharpe_p05']:>6.2f}  "
    f"p95 {rc['sharpe_p95']:>6.2f}   random MaxDD mean {rc['maxdd_mean'] * 100:>7.2f}%"
)
print(f"  random avg names {rc['avg_names_mean']:.1f}   (strategy {primary.avg_names:.1f})")
print(
    f"  strategy CAGR {m.cagr * 100:.2f}% vs random mean {rc['cagr_mean'] * 100:.2f}%  "
    f"-> {'' if m.cagr >= rc['cagr_mean'] else 'WORSE by '}{abs(m.cagr - rc['cagr_mean']) * 100:.2f} pp"
)
print(
    f"  strategy Sharpe {m.sharpe:.2f} vs random mean {rc['sharpe_mean']:.2f}  "
    f"-> {'' if m.sharpe >= rc['sharpe_mean'] else 'WORSE by '}{abs(m.sharpe - rc['sharpe_mean']):.2f}"
)

print(header("PLAUSIBILITY / BUG CHECKS (brief section 6)"))
_w = run_backtest(close, score, COST, CONFIG, rebalance=FROZEN["rebalance"]).weights
_inv = _w.sum(axis=1)
print(f"  capital deployed  mean {_inv.mean() * 100:.1f}%  median {_inv.median() * 100:.1f}%  "
      f"min {_inv.min() * 100:.1f}%  max {_inv.max() * 100:.1f}%  "
      f"-> {(100 - _inv.mean() * 100):.1f}% average cash drag")
print(f"  CAGR {m.cagr * 100:.1f}%  -> below the 40-50% ceiling for an unlevered long-only book: "
      f"{'OK' if m.cagr < 0.50 else 'SUSPICIOUS'}")
print(f"  avg names {primary.avg_names:.1f}  -> not ~48, no residual accumulation: "
      f"{'OK' if primary.avg_names <= 30 else 'SUSPICIOUS'}")
print(f"  bar long frac {test_long_frac * 100:.1f}% -> above the 5% liveness floor: "
      f"{'OK' if test_long_frac > 0.05 else 'DEAD'}")
print(f"  cost drag {m.cost_drag_annual * 100:.2f}%/yr vs net CAGR {m.cagr * 100:.2f}% vs "
      f"gross CAGR {gross * 100:.2f}%")

print(header("POST-HOC, NON-SELECTED: all 5 declared variants on TEST"))
print("  Reported for completeness ONLY. The winner was frozen on TRAIN before TEST was")
print("  read; nothing below was used to choose anything. If the catalog-default V1 and")
print("  the selected V3 both fail here, that is a property of the STRATEGY, not of the")
print("  variant choice.")
rsi14 = rsi_all
rsi6 = rsi_panel(close_all, 6)
post = []
for v in (
    dict(name="V1_cat_14_30_deepest_M", period=14, lower=30.0, rank_by="deepest", rebalance="M"),
    dict(name="V2_cat_14_30_mom126_M", period=14, lower=30.0, rank_by="mom126", rebalance="M"),
    dict(name="V3_wide_14_40_deepest_M", period=14, lower=40.0, rank_by="deepest", rebalance="M"),
    dict(name="V4_fast_6_30_deepest_M", period=6, lower=30.0, rank_by="deepest", rebalance="M"),
    dict(name="V5_cat_14_30_deepest_W", period=14, lower=30.0, rank_by="deepest", rebalance="W"),
):
    rr = rsi6 if v["period"] == 6 else rsi14
    sc = build_score(close_all, rr, v["lower"], v["rank_by"]).loc[TEST_START:TEST_END]
    res = run_variant(v["name"], close, sc, rebalance=v["rebalance"])
    post.append(dict(name=v["name"], cagr=res.metrics.cagr, sharpe=res.metrics.sharpe,
                     maxdd=res.metrics.max_drawdown, names=res.avg_names))
    print(row(v["name"], res))

out = {
    "frozen": {k: FROZEN[k] for k in ("name", "period", "lower", "rank_by", "rebalance", "sharpe")},
    "test": m.as_dict(),
    "test_long_frac": test_long_frac,
    "train_long_frac": TRAIN_LONG_FRAC,
    "buy_and_hold": bh.metrics.as_dict(),
    "equal_weight_book": ewb.metrics.as_dict(),
    "nsealgo_composite": compr.metrics.as_dict(),
    "gross_cagr": gross,
    "random_control": rc,
    "post_hoc_all_variants": post,
}
with open("S3_TEST_RESULT.json", "w") as f:
    json.dump(out, f, indent=2, default=str)
print("\n>> wrote S3_TEST_RESULT.json")
