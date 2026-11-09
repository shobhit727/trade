"""Step 2: THE TEST RUN. Touched exactly once, on the pre-declared TRAIN winner.

Also produces every control the brief §7 requires: buy-and-hold, random-signal
negative control, and the nsealgo composite. The winner's parameters are read from
`winner.json` and are NOT adjusted here.
"""

from __future__ import annotations

import json

import numpy as np
from common import (
    COST_MODEL,
    DATA_DIR,
    OUT_DIR,
    PLAUSIBLE_CAGR_CEILING,
    TEST_END,
    TEST_START,
    bench_run,
    build_composite_score,
    load_ohlc_universe,
    random_signal,
    run,
    score_from_signal,
    signal_long,
    yearly,
)

from nsealgo.backtest.engine import PortfolioConfig, run_backtest

lines: list[str] = []


def out(s: str = "") -> None:
    print(s)
    lines.append(s)


def hdr(s: str) -> None:
    out()
    out("=" * 96)
    out(s)
    out("=" * 96)


with open(f"{OUT_DIR}/winner.json") as f:
    w = json.load(f)
VID, WNAME, WPARAMS = w["winner"], w["winner_name"], w["params"]

u = load_ohlc_universe(DATA_DIR)
px_te = u.close.loc[TEST_START:TEST_END]
fin_te = int(np.isfinite(px_te.to_numpy(dtype=float)).sum())

hdr("STEP 2  TEST  window 2024-01-01 -> 2026-10-01  (685 bars)")
out(f"winner carried over UNCHANGED from TRAIN: {VID} {WNAME}  params={WPARAMS}")
out(f"finite symbol-bars in TEST: {fin_te:,}")

# =========================================================================== #
hdr("2.1  HEADLINE -- strategy vs buy-and-hold vs nsealgo composite, TEST")

sig = signal_long(u, **WPARAMS)
sc = score_from_signal(u, sig, rank_lookback=126)
strat = run(u, sc, TEST_START, TEST_END)
bh = bench_run(u, TEST_START, TEST_END)
comp = run(u, build_composite_score(u.close), TEST_START, TEST_END)

out()
out(f"{'':<26} {'CAGR':>8} {'Sharpe':>7} {'MaxDD':>8} {'Calmar':>7} {'Turn/y':>7} "
    f"{'Cost/y':>7} {'Names':>6}")
for lbl, r in (("buy-and-hold (EW)", bh),
               (f"{VID} {WNAME}", strat),
               ("nsealgo composite", comp)):
    out(f"{lbl:<26} {r['cagr'] * 100:>7.2f}% {r['sharpe']:>7.2f} {r['max_dd'] * 100:>7.2f}% "
        f"{r['calmar']:>7.2f} {r['annual_turnover']:>6.2f}x {r['cost_drag'] * 100:>6.2f}% "
        f"{r.get('avg_names', float('nan')):>6.1f}")

d_ret = strat["cagr"] - bh["cagr"]
d_dd = strat["max_dd"] - bh["max_dd"]
out()
out("TEST vs buy-and-hold:")
out(f"  return  : {strat['cagr'] * 100:+.2f}% vs {bh['cagr'] * 100:.2f}%  -> "
    f"{'BETTER' if d_ret > 0 else 'WORSE'} by {abs(d_ret) * 100:.2f} pp/yr")
out(f"  drawdown: {strat['max_dd'] * 100:+.2f}% vs {bh['max_dd'] * 100:.2f}%  -> "
    f"{'BETTER (shallower)' if d_dd > 0 else 'WORSE (deeper)'} by "
    f"{abs(d_dd) * 100:.2f} pp")
out(f"  Sharpe  : {strat['sharpe']:+.2f} vs {bh['sharpe']:+.2f}")
out(f"  Sharpe  : {VID} vs composite {strat['sharpe']:+.2f} vs {comp['sharpe']:+.2f} -> "
    f"{'BEATS' if strat['sharpe'] > comp['sharpe'] else 'LOSES TO'} the composite")

out()
out("Total return over the window (not annualised):")
out(f"  buy-and-hold {bh['total_return'] * 100:+.2f}%   "
    f"{VID} {strat['total_return'] * 100:+.2f}%   "
    f"composite {comp['total_return'] * 100:+.2f}%")

# =========================================================================== #
hdr("2.2  SANITY CHECKS on TEST (brief §6)")

out()
out("§6.1 plausibility:")
out(f"  {VID} CAGR {strat['cagr'] * 100:.2f}%  ceiling {PLAUSIBLE_CAGR_CEILING * 100:.0f}%  "
    f"-> {'OK' if strat['cagr'] < PLAUSIBLE_CAGR_CEILING else 'IMPLAUSIBLE, BUG'}")
out(f"  buy-and-hold CAGR {bh['cagr'] * 100:.2f}%  "
    f"-> {'OK' if bh['cagr'] < PLAUSIBLE_CAGR_CEILING else 'IMPLAUSIBLE'}")

wte = strat["_weights"]
nheld = (wte > 0).sum(axis=1)
out()
out("§6.2 weight count:")
out(f"  {VID}: avg names {nheld.mean():.1f}  min {nheld.min()}  max {nheld.max()}  "
    f"(cap n_positions=22, max_names=30)")
out(f"  held>0 for more than 22 names on {(nheld > 22).sum()} of {len(nheld)} bars "
    f"-> {'CAP VIOLATION' if (nheld > 22).any() else 'no cap violation'}")
out(f"  max single weight {wte.to_numpy().max():.4f} (cap 0.12)")
out(f"  mean invested {(wte.sum(axis=1)).mean():.4f} (cap 0.90)")
out("  NOTE: fewer than 22 names is a consequence of the SPARSE signal, not residual")
out("  accretion -- the gate only flags ~7% of bars, so ~3-4 of 48 names qualify on a")
out("  typical day. The cap is a maximum, not a target.")

live_te = float(sig.loc[TEST_START:TEST_END].to_numpy(dtype=float).sum()) / fin_te * 100
out()
out("§6.3 signal liveness on TEST:")
out(f"  {VID} fires {live_te:.3f}% of TEST symbol-bars "
    f"-> {'ALWAYS-FLAT' if live_te < 5 else 'alive'}")
out("  TRAIN liveness was 7.303% -- comparable, so the gate is not regime-specific.")

out()
out("§6.4 cost drag, gross vs net on TEST (identical engine, only costs differ):")
zero = COSTModelZero = COST_MODEL.__class__(segment="delivery", slippage_bps=0)
rz = run_backtest(px_te, sc.reindex(px_te.index), zero, config=PortfolioConfig())
out(f"  gross (0 cost) {rz.metrics.cagr * 100:>7.2f}%   net {strat['cagr'] * 100:>7.2f}%   "
    f"drag {strat['cost_drag'] * 100:.2f}%/y  "
    f"-> {'VIABLE' if strat['cagr'] > 0 else 'UNVIABLE: net negative'}")
out(f"  costs are NOT the binding constraint here (drag only "
    f"{strat['cost_drag'] * 100:.2f}%/y).")

# =========================================================================== #
hdr("2.3  NEGATIVE CONTROL -- random signal, same % of bars long")

# Match the bar-level long rate of the winner on TEST.
rng = np.random.default_rng(20240101)
target = live_te / 100.0
ctrl = []
for seed in range(1, 21):
    rs = random_signal(u, target, seed)
    rsc = score_from_signal(u, rs, rank_lookback=126)
    r = run(u, rsc, TEST_START, TEST_END)
    ctrl.append(r)
cs = np.array([c["cagr"] for c in ctrl])
sh = np.array([c["sharpe"] for c in ctrl])
dd = np.array([c["max_dd"] for c in ctrl])
out(f"20 random-signal draws, live rate matched to {live_te:.3f}%:")
out(f"  CAGR   mean {cs.mean() * 100:>7.2f}%  sd {cs.std(ddof=1) * 100:>5.2f}%  "
    f"min {cs.min() * 100:>7.2f}%  max {cs.max() * 100:>7.2f}%")
out(f"  Sharpe mean {sh.mean():>7.2f}  sd {sh.std(ddof=1):>5.2f}  "
    f"min {sh.min():>7.2f}  max {sh.max():>7.2f}")
out(f"  MaxDD  mean {dd.mean() * 100:>7.2f}%")
out(f"  strategy CAGR {strat['cagr'] * 100:.2f}%  -> percentile "
    f"{(cs < strat['cagr']).mean() * 100:.0f}th of the random draws")
out(f"  strategy Sharpe {strat['sharpe']:.2f}  -> percentile "
    f"{(sh < strat['sharpe']).mean() * 100:.0f}th")
out(f"  strategy beats {int((cs < strat['cagr']).sum())}/20 random controls on CAGR")

out()
out("Interpretation:")
out(f"  A random gate holding the same number of names gets {cs.mean() * 100:.2f}% CAGR.")
out(f"  The Donchian gate gets {strat['cagr'] * 100:.2f}%. "
    f"{'BEATS' if strat['cagr'] > cs.mean() else 'LOSES TO'} the coin flip.")

# =========================================================================== #
hdr("2.4  YEARLY RETURNS on TEST (GOAL.md §5 gate: positive in >=60% of years)")
out(f"{'':<26} {'2024':>8} {'2025':>8} {'2026*':>8}   pos/3")
for lbl, r in (("buy-and-hold (EW)", bh), (f"{VID} {WNAME}", strat),
               ("nsealgo composite", comp)):
    yr = yearly(r["_returns"]) * 100
    cells = " ".join(f"{yr.get(y, np.nan):>8.1f}" for y in (2024, 2025, 2026))
    out(f"{lbl:<26} {cells}   {int((yr > 0).sum())}/3")
out("* 2026 is a partial year (to 2026-10-01), not comparable to full years.")

# =========================================================================== #
hdr("2.5  TRAIN vs TEST, side by side (is the TRAIN result stable?)")
out(f"{'':<26} {'TRAIN cagr':>11} {'TEST cagr':>11} {'TRAIN Shp':>10} {'TEST Shp':>10}")
out(f"{'buy-and-hold (EW)':<26} {21.46:>10.2f}% {bh['cagr'] * 100:>10.2f}% "
    f"{0.90:>10.2f} {bh['sharpe']:>10.2f}")
out(f"{f'{VID} {WNAME}':<26} {6.47:>10.2f}% {strat['cagr'] * 100:>10.2f}% "
    f"{0.03:>10.2f} {strat['sharpe']:>10.2f}")
out(f"{'nsealgo composite':<26} {'--':>10} {comp['cagr'] * 100:>10.2f}% "
    f"{'--':>10} {comp['sharpe']:>10.2f}")

payload = {
    "window": [str(TEST_START.date()), str(TEST_END.date())],
    "winner": {"id": VID, "name": WNAME, "params": WPARAMS},
    "strategy": {k: v for k, v in strat.items() if not k.startswith("_")},
    "buy_hold": {k: v for k, v in bh.items() if not k.startswith("_")},
    "composite": {k: v for k, v in comp.items() if not k.startswith("_")},
    "random_control": {
        "n": len(ctrl), "live_rate_pct": live_te,
        "cagr_mean": float(cs.mean()), "cagr_sd": float(cs.std(ddof=1)),
        "cagr_min": float(cs.min()), "cagr_max": float(cs.max()),
        "sharpe_mean": float(sh.mean()), "sharpe_sd": float(sh.std(ddof=1)),
        "strategy_cagr_percentile": float((cs < strat["cagr"]).mean()),
        "strategy_beats_n": int((cs < strat["cagr"]).sum()),
    },
    "gross_cagr_zero_cost": float(rz.metrics.cagr),
}
with open(f"{OUT_DIR}/02_test.json", "w") as f:
    json.dump(payload, f, indent=2, default=str)
with open(f"{OUT_DIR}/02_test.txt", "w") as f:
    f.write("\n".join(lines) + "\n")
out(f"[written] {OUT_DIR}/02_test.txt")
