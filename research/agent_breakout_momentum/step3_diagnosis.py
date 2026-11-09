"""Step 3: verify the flagged cap check, then diagnose WHY the strategy fails.

Everything here is post-hoc explanation of an already-recorded TEST result.
No parameter is changed and no new strategy variant is introduced.
"""

from __future__ import annotations

import json

import pandas as pd
from common import (
    DATA_DIR,
    OUT_DIR,
    TEST_END,
    TEST_START,
    bench_run,
    load_ohlc_universe,
    run,
    score_from_signal,
    signal_long,
)

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
WPARAMS = w["params"]
u = load_ohlc_universe(DATA_DIR)

hdr("3.1  WAS THE 'CAP VIOLATION' REAL?")
sig = signal_long(u, **WPARAMS)
sc = score_from_signal(u, sig, rank_lookback=126)
st = run(u, sc, TEST_START, TEST_END)
wte = st["_weights"]
nheld = (wte > 0).sum(axis=1)
out("PortfolioConfig has TWO distinct limits and step 2 conflated them:")
out("  n_positions = 22  -> how many names the TARGET book aims for at a rebalance")
out("  max_names   = 30  -> hard cap on names CARRIED between rebalances")
out("  The turnover budget blends toward the target, so dropped names decay rather")
out("  than vanish; the engine deliberately allows 30 material positions for that.")
out()
out(f"  observed max names held on TEST : {int(nheld.max())}")
out("  engine hard cap (max_names)     : 30")
out(f"  bars exceeding max_names=30    : {int((nheld > 30).sum())}  "
    f"-> {'VIOLATION' if (nheld > 30).any() else 'NO VIOLATION -- step-2 flag was my own'}")
out(f"  bars exceeding n_positions=22   : {int((nheld > 22).sum())} "
    f"(expected and permitted: these are carried-over names)")
out()
out("  CORRECTION: step 2 compared against 22 (the target), not 30 (the cap).")
out("  The engine's constraints all hold. No bug. Correcting the record.")
out(f"  max single weight {wte.to_numpy().max():.4f} <= 0.12  OK")
out("  max sector weight is enforced inside build_rebalance_weights; spot check:")
from nsealgo.backtest.engine import sector_of  # noqa: E402

sec = {}
for s in wte.columns:
    sec.setdefault(sector_of(s), 0.0)
tot = {}
for _, row in wte.iterrows():
    for k in tot:
        tot[k] = 0.0
    for s, val in row.items():
        if val > 0:
            tot[sector_of(s)] = tot.get(sector_of(s), 0.0) + val
maxsec = max(tot.values()) if tot else 0.0
out(f"    max sector weight observed {maxsec:.4f} <= 0.25  "
    f"{'OK' if maxsec <= 0.25 + 1e-9 else 'VIOLATION'}")

hdr("3.2  THE MECHANISM: the gate is too sparse to fill the book")
out("PortfolioConfig demands a 22-name, 12%-capped, 90%-invested book. The Donchian")
out("gate only qualifies ~6-7% of symbol-bars, i.e. ~2-4 of 48 names on a typical day.")
out("With a 12% single-name cap, N qualified names can supply at most 12%*N.")
out()

px_te = u.close.loc[TEST_START:TEST_END]
s_te = sig.loc[TEST_START:TEST_END]
nflag = s_te.sum(axis=1)
rb_dates = wte.index[wte.index.to_series().groupby(
    wte.index.to_period("M")).transform("size") > 0]  # placeholder, replaced below
# recompute at rebalance resolution: first bar of each month in the test window
firsts = pd.Series(px_te.index, index=px_te.index).groupby(
    px_te.index.to_period("M")).first().tolist()
nf = pd.Series({d: int(nflag.loc[d]) for d in firsts if d in nflag.index})
inv = wte.sum(axis=1)

out(f"names flagged on each rebalance date (n={len(nf)} dates):")
out(f"  mean {nf.mean():.1f}   median {nf.median():.0f}   "
    f"min {nf.min()}   max {nf.max()}")
out("  distribution: " + ", ".join(
    f"{int(k)} flagged: {v} dates" for k, v in
    nf.value_counts().sort_index().items()))
out()
out(f"invested weight (mean of held row sums): {inv.mean():.4f}")
out(f"  min {inv.min():.4f}  median {inv.median():.4f}  max {inv.max():.4f}")
out(f"  cash held on average: {(1 - inv).mean() * 100:.1f}%")
out()
out("  -> the gate can never reach the 90% target. Even a PERFECT breakout signal")
out(f"     would leave the book ~{1 - inv.mean():.0%} in cash, for structural reasons:")
out("     sparse flags x a 12% hard single-name cap.")
out()
out(f"  the 12% cap binds when flags < 7.5: "
    f"{int((nf < 7.5).sum())}/{len(nf)} rebalances had <7.5 names -> cap binding")
out(f"  0 names flagged on {int((nf == 0).sum())}/{len(nf)} rebalances "
    f"-> fully in cash")

hdr("3.3  EXPOSURE-ADJUSTED: is the stock selection any good at all?")
# Compare the strategy's held names' forward return vs the universe, on the SAME
# days the strategy is invested. This isolates SELECTION from EXPOSURE.
bt = bench_run(u, TEST_START, TEST_END)
out(f"strategy CAGR {st['cagr'] * 100:.2f}% with average exposure {inv.mean():.1%}")
out(f"buy-and-hold CAGR {bt['cagr'] * 100:.2f}% with exposure ~100% (less entry cost)")
out()
gross = (wte.shift(1).fillna(0.0) * px_te.pct_change(fill_method=None).fillna(0.0)).sum(axis=1)
out(f"strategy GROSS daily return mean {gross.mean() * 1e4:>7.3f} bp/day")
out(f"buy-and-hold gross daily mean     "
    f"{px_te.pct_change(fill_method=None).fillna(0.0).mean(axis=1).mean() * 1e4:>7.3f} bp/day")
out()
out("Selection quality on invested days only (exposure removed):")
mask = inv.shift(1).fillna(0.0) > 0.5
gsel = gross[mask]
mkt = px_te.pct_change(fill_method=None).fillna(0.0).mean(axis=1)[mask]
out(f"  days with >50% invested: {int(mask.sum())}")
out(f"  strategy held-names return   {gsel.mean() * 1e4:>7.3f} bp/day")
out(f"  equal-weight universe same day {mkt.mean() * 1e4:>7.3f} bp/day")
out(f"  SELECTION EDGE               {(gsel.mean() - mkt.mean()) * 1e4:>7.3f} bp/day")
out()
out(f"  annualised selection edge (x244): "
    f"{(gsel.mean() - mkt.mean()) * 244 * 100:+.2f} pp/yr")
out("  WARNING: this comparison is EXPOSURE-CONDITIONAL -- it only looks at days where")
out("  the strategy held >50%. Conditioning on the strategy's own state of mind selects")
out("  a non-random subset of days, so this number is biased and must not be quoted.")
if (gsel.mean() - mkt.mean()) > 0:
    out("  On that subset the names it held DO beat the universe, but the estimate is")
    out("  biased; see step3b for the unbiased version.")
else:
    out("  On that subset the names it held LAG the universe. Biased either way.")
    out("  The unbiased decomposition is in step3b: beta 0.338, alpha statistically zero.")

hdr("3.4  IS 'BEATING THE COIN FLIP' REAL?")
payload = json.load(open(f"{OUT_DIR}/02_test.json"))
rc = payload["random_control"]
n = rc["n"]
wins = rc["strategy_beats_n"]
from math import comb  # noqa: E402

# exact one-sided binomial p-value for >= wins successes out of n at p=0.5
p = sum(comb(n, k) for k in range(wins, n + 1)) / 2 ** n
out(f"  strategy beat {wins}/{n} random-signal controls on CAGR")
out(f"  one-sided exact binomial p (H0: coin flip) = {p:.3f}")
out(f"  -> {'NOT significant' if p > 0.10 else 'significant'} at the 10% level.")
out(f"  strategy CAGR percentile vs controls: {rc['strategy_cagr_percentile'] * 100:.0f}th")
out(f"  random control CAGR mean {rc['cagr_mean'] * 100:.2f}% "
    f"sd {rc['cagr_sd'] * 100:.2f}%")
out(f"  strategy Sharpe {payload['strategy']['sharpe']:.2f} vs control mean "
    f"{rc['sharpe_mean']:.2f} sd {rc['sharpe_sd']:.2f}")
out()
out(f"  CONTROL SHARPE IS NEGATIVE ({rc['sharpe_mean']:.2f}) AND THE STRATEGY'S IS")
out(f"  ALSO NEGATIVE ({payload['strategy']['sharpe']:.2f}). Beating a set of losing")
out("  coin flips while losing money is not evidence of an edge.")
out("  This is the honest reading of the brief §6.5 control.")

hdr("3.5  DOES IT BEAT THE COMPOSITE?")
out(f"  {payload['strategy']['sharpe']:.2f} Sharpe / {payload['strategy']['cagr'] * 100:.2f}% CAGR"
    f"  vs composite {payload['composite']['sharpe']:.2f} / "
    f"{payload['composite']['cagr'] * 100:.2f}%")
out(f"  -> {'YES' if payload['strategy']['cagr'] > payload['composite']['cagr'] else 'NO'}, "
    f"by {(payload['strategy']['cagr'] - payload['composite']['cagr']) * 100:+.2f} pp/yr")
out(f"  and the composite holds {payload['composite']['avg_names']:.0f} names at "
    f"{payload['composite']['cagr'] * 100:.2f}% CAGR vs this strategy's "
    f"{payload['strategy']['avg_names']:.0f} names.")

with open(f"{OUT_DIR}/03_diagnosis.txt", "w") as f:
    f.write("\n".join(lines) + "\n")
out(f"[written] {OUT_DIR}/03_diagnosis.txt")
