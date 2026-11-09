"""Step 1: TRAIN-only sweep over the 5 DECLARED variants.

TEST is not touched anywhere in this file.
"""

from __future__ import annotations

import json

import numpy as np
from common import (
    DATA_DIR,
    OUT_DIR,
    PLAUSIBLE_CAGR_CEILING,
    TRAIN_END,
    TRAIN_START,
    bench_run,
    fmt_row,
    load_ohlc_universe,
    run,
    score_from_signal,
    signal_long,
    yearly,
)

# The 5 DECLARED variants -- see DECLARED_BUDGET.md. Do not add a 6th.
VARIANTS = [
    ("V1", "FAITHFUL", dict(channel="incl", period=20, mom_period=10)),
    ("V2", "EXCL20", dict(channel="excl", period=20, mom_period=10)),
    ("V3", "EXCL20_NOMOM", dict(channel="excl", period=20, mom_period=0)),
    ("V4", "EXCL55", dict(channel="excl", period=55, mom_period=10)),
    ("V5", "EXCL55_MOM63", dict(channel="excl", period=55, mom_period=63)),
]

lines: list[str] = []


def out(s: str = "") -> None:
    print(s)
    lines.append(s)


def hdr(s: str) -> None:
    out()
    out("=" * 96)
    out(s)
    out("=" * 96)


u = load_ohlc_universe(DATA_DIR)
px_tr = u.close.loc[TRAIN_START:TRAIN_END]
fin_tr = int(np.isfinite(px_tr.to_numpy(dtype=float)).sum())

hdr("STEP 1  TRAIN SWEEP   window 2016-01-01 -> 2023-12-31  (1975 bars)")
out(f"finite symbol-bars in TRAIN: {fin_tr:,}")
out("all costs net (delivery, 5bps slippage => 21.92bps all-in round trip)")
out()
out(f"{'variant':<18} {'live%':>7} {'CAGR':>8} {'Sharpe':>7} {'MaxDD':>8} "
    f"{'Calmar':>7} {'Turn':>7} {'Cost/y':>8} {'Names':>6} {'TopW':>6} {'Rebal':>6}")

results = {}
live_pct = {}
for vid, name, kw in VARIANTS:
    sig = signal_long(u, **kw)
    s_tr = sig.loc[TRAIN_START:TRAIN_END].to_numpy(dtype=float)
    live_pct[vid] = float(s_tr.sum()) / fin_tr * 100
    sc = score_from_signal(u, sig, rank_lookback=126)
    r = run(u, sc, TRAIN_START, TRAIN_END)
    results[vid] = dict(name=name, params=kw, live=live_pct[vid], **{
        k: v for k, v in r.items() if not k.startswith("_")})
    out(f"{vid + ' ' + name:<18} {live_pct[vid]:>6.3f}% {r['cagr'] * 100:>7.2f}% "
        f"{r['sharpe']:>7.2f} {r['max_dd'] * 100:>7.2f}% {r['calmar']:>7.2f} "
        f"{r['annual_turnover']:>6.2f}x {r['cost_drag'] * 100:>7.2f}% "
        f"{r['avg_names']:>6.1f} {r['avg_top_weight']:>6.3f} {r['n_rebalances']:>6d}")

bh = bench_run(u, TRAIN_START, TRAIN_END)
out()
out("TRAIN benchmarks:")
out("  " + fmt_row("buy-and-hold (EW)", bh))

# ---- sanity checks from brief §6 ------------------------------------------ #
hdr("SANITY CHECKS (brief §6) on TRAIN")

out()
out("§6.1 plausibility (unlevered long-only NIFTY-50 ceiling ~40-50% CAGR):")
for vid, r in results.items():
    flag = "  <-- IMPLAUSIBLE, investigate" if r["cagr"] > PLAUSIBLE_CAGR_CEILING else ""
    out(f"  {vid:<4} CAGR {r['cagr'] * 100:>7.2f}%{flag}")
out(f"  ceiling used: {PLAUSIBLE_CAGR_CEILING * 100:.0f}%")

out()
out("§6.2 weight count (should be ~22, not 48):")
for vid, r in results.items():
    flag = "  <-- RESIDUAL ACCRETION, BUG" if r["avg_names"] > 30 else ""
    out(f"  {vid:<4} avg names {r['avg_names']:>5.1f}   "
        f"max top weight {r['avg_top_weight']:.3f}{flag}")

out()
out("§6.3 signal liveness (below ~5% = effectively always-flat):")
for vid, r in results.items():
    verdict = "ALWAYS-FLAT" if r["live"] < 5.0 else "alive"
    out(f"  {vid:<4} {r['live']:>6.3f}% of TRAIN symbol-bars  -> {verdict}")

out()
out("§6.4 cost drag: gross vs net. Same engine, zero-cost model, for the record.")
from common import COST_MODEL  # noqa: E402

from nsealgo.backtest.engine import PortfolioConfig, run_backtest  # noqa: E402

zero = COST_MODEL.__class__(segment="delivery", slippage_bps=0)
for vid, _name, kw in VARIANTS:
    sig = signal_long(u, **kw)
    sc = score_from_signal(u, sig, rank_lookback=126)
    rz = run_backtest(px_tr, sc.reindex(px_tr.index), zero, config=PortfolioConfig())
    rn = results[vid]
    g, n = rz.metrics.cagr, rn["cagr"]
    out(f"  {vid:<4} gross(0 cost) {g * 100:>7.2f}%  net {n * 100:>7.2f}%  "
        f"drag {rn['cost_drag'] * 100:>5.2f}%/y  "
        f"{'VIABLE' if n > 0 else 'UNVIABLE (net negative)'}")

out()
out("§6.5 negative control -- random signal with the SAME % of bars long.")
out("    (done properly in step 2; here just noting each variant's live rate:)")
for vid, r in results.items():
    out(f"  {vid:<4} live {r['live']:>6.3f}%")

# ---- yearly returns, to expose single-year dependence ---------------------- #
hdr("TRAIN YEARLY RETURNS (gate: positive in >=60% of years, GOAL.md §5)")
sig_cache = {vid: score_from_signal(u, signal_long(u, **kw), rank_lookback=126)
             for vid, _, kw in VARIANTS}
out(f"{'variant':<18} " + " ".join(f"{y:>8}" for y in range(2016, 2024)))
for vid, name, _kw in VARIANTS:
    r = run(u, sig_cache[vid], TRAIN_START, TRAIN_END)
    yr = yearly(r["_returns"]) * 100
    cells = " ".join(f"{yr.get(y, np.nan):>8.1f}" for y in range(2016, 2024))
    pos = int((yr > 0).sum())
    out(f"{vid + ' ' + name:<18} {cells}   pos {pos}/8")
yr = yearly(bh["_returns"]) * 100
cells = " ".join(f"{yr.get(y, np.nan):>8.1f}" for y in range(2016, 2024))
out(f"{'buy-and-hold':<18} {cells}   pos {int((yr > 0).sum())}/8")

# ---- selection ------------------------------------------------------------ #
hdr("SELECTION (rule fixed in advance: TRAIN net CAGR, tie-break Sharpe then MaxDD)")
ranked = sorted(results.items(),
                key=lambda kv: (-kv[1]["cagr"], -kv[1]["sharpe"], kv[1]["max_dd"]))
for vid, r in ranked:
    out(f"  {vid:<4} {r['name']:<16} CAGR {r['cagr'] * 100:>7.2f}%  "
        f"Sharpe {r['sharpe']:>5.2f}  MaxDD {r['max_dd'] * 100:>7.2f}%")
winner = ranked[0][0]
out()
out(f"WINNER: {winner} ({results[winner]['name']}) -> will be run UNCHANGED on TEST")
out("Note: V2 and V3 must be numerically identical (see DECLARED_BUDGET.md fact (c)).")

v2, v3 = results["V2"], results["V3"]
same = (abs(v2["cagr"] - v3["cagr"]) < 1e-12 and abs(v2["sharpe"] - v3["sharpe"]) < 1e-12)
out(f"  V2 CAGR {v2['cagr']:.12f}  V3 CAGR {v3['cagr']:.12f}  identical: {same}")
if not same:
    out("  -> V2 != V3, so the redundancy argument is wrong somewhere. Investigate.")

with open(f"{OUT_DIR}/01_train_sweep.json", "w") as f:
    json.dump({vid: {k: v for k, v in r.items()} for vid, r in results.items()},
              f, indent=2, default=str)
with open(f"{OUT_DIR}/01_train_sweep.txt", "w") as f:
    f.write("\n".join(lines) + "\n")
out(f"[written] {OUT_DIR}/01_train_sweep.txt")

# stash the winner for step 2
with open(f"{OUT_DIR}/winner.json", "w") as f:
    json.dump({"winner": winner, "winner_name": results[winner]["name"],
               "params": next(kw for v, n, kw in VARIANTS if v == winner)}, f, indent=2)
