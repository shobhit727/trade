# Phase 1 — Does the rebalance clock decide whether this book makes money?

**Status:** complete. 9,024 runs, zero failures.
**Artifact:** `tem/phase1/rows.jsonl` (16 strategies × 47 symbols × 6 clocks × 2 windows)
**Code:** `research/optimize/phase1.py`
**Panel:** post-C10 (TRENT repaired, TMPV excluded → 47 symbols)
**Cost stack:** corrected — 32.32 bp/round trip of notional, derived from `nsealgo.costs.CostModel`

## Why this experiment had to exist

The earlier sweep concluded "turnover is the constraint" from `corr(turnover, alpha) = -0.065`
across 4,032 pairs. That inference is confounded: low-turnover pairs traded rarely *because the
strategy had little signal*, not because holding paid. Mixing strategies of differing signal
liveness measures "is this strategy dead", not "does holding pay".

The clean test fixes the signal and varies only the clock. That is what this does.

## Method

Fixed: Rs21L book, full statutory stack + 18% GST, FIFO lots, STCG 20% / LTCG 12.5%, one
config per strategy (no parameter search). Varied: rebalance clock only.

`D` daily · `W` weekly · `M` monthly · `Q` quarterly · `2Q` semi-annual · `A` annual.
Quarterly/semi-annual/annual grouping was added for this experiment (the engine previously
offered only D/W/M).

16 strategies chosen for **family coverage**, not performance: 6 trend, 3 momentum,
3 mean-reversion, 2 volatility, 2 cross-sectional/multi-factor.

## Result

### TRAIN (2016–2023)

| clock | median CAGR | mean CAGR | exposure | turnover | fees % | tax % | % stocks positive |
|---|---|---|---|---|---|---|---|
| D | −0.003 | 0.001 | 0.491 | 151.3 | 2.446 | 2.908 | 48.7 |
| W | +0.019 | 0.026 | 0.484 | 84.0 | 1.357 | 2.731 | 64.8 |
| M | +0.037 | 0.047 | 0.490 | 44.3 | 0.716 | 2.115 | 73.9 |
| Q | +0.028 | 0.042 | 0.450 | 14.8 | 0.239 | 1.288 | 69.5 |
| 2Q | +0.052 | 0.064 | 0.492 | 7.4 | 0.119 | 0.792 | 78.1 |
| A | +0.058 | 0.065 | 0.378 | 3.4 | 0.055 | 0.561 | 74.5 |

### TEST (2024–2026-10-01)

| clock | median CAGR | mean CAGR | exposure | turnover | fees % | tax % | % stocks positive |
|---|---|---|---|---|---|---|---|
| D | −0.056 | −0.064 | 0.453 | 54.6 | 0.883 | 0.695 | 21.0 |
| W | −0.031 | −0.032 | 0.447 | 29.6 | 0.479 | 0.581 | 28.6 |
| M | −0.008 | −0.008 | 0.445 | 14.3 | 0.231 | 0.433 | 44.4 |
| Q | −0.000 | −0.001 | 0.455 | 5.5 | 0.088 | 0.209 | 44.5 |
| 2Q | +0.000 | −0.007 | 0.461 | 2.6 | 0.043 | 0.000 | 37.6 |
| A | +0.000 | −0.008 | 0.277 | 1.0 | 0.016 | 0.000 | 28.5 |

## What this establishes

**1. The cost hypothesis is confirmed and quantified.** Going daily → annual cuts the fee
bill **55×** (0.883% → 0.016%) and drives tax to exactly zero (every lot clears 365 days, so
nothing is taxed as short-term). So cost was real, and the corrected 32.32 bp stack makes it
realer than previously thought.

**2. But cost is not what is killing the book.** Removing 87% of the cost buys ~0.8%/yr.
TEST median CAGR moves from −0.008 (M) to 0.000 (A). The account still earns nothing.

**3. The binding constraint is exposure, not turnover.** Median exposure sits at ~0.45 for
every clock from daily to semi-annual — the book is in cash more than half the time — and
collapses to 0.277 at annual. Relationship is monotone at the top:

| exposure bucket | n | median CAGR | mean CAGR | % positive |
|---|---|---|---|---|
| <30% | 1,612 | 0.000 | −0.012 | 30.6 |
| 30–40% | 624 | −0.029 | −0.029 | 32.7 |
| 40–50% | 1,001 | −0.046 | −0.050 | 24.1 |
| 50–60% | 732 | −0.016 | −0.015 | 39.1 |
| **>60%** | 543 | **+0.019** | **+0.015** | **58.0** |

The highest-exposure bucket is the only one with a positive median. **For a single-stock
long/flat book, the signal's problem is that it says "be in cash" too often.**

**4. Annual rebalancing is worse than quarterly despite 5× lower cost**, because forcing one
decision a year collapses exposure to 0.277 and misses the opportunities that were profitable.
Cost and exposure trade off against each other; the quarterly point is the knee.

## The one cell worth naming — and why it is not yet a finding

`zscore_strategy` @ M is the best TEST cell: **74.5% of the 47 stocks profitable (35/47),
median +2.89%, Sharpe 0.28, MaxDD −10.9%.** `volatility_scaling` @ M is second (61.7%).

Three reasons this is a hypothesis, not a result:

1. **It is 1 of 96 TEST cells selected after the fact.** Across all 96 cells the median cell
   has 36% of stocks positive and the 95th percentile is 60.1%. zscore @ M at 74.5% is the
   maximum of the family — which is roughly what noise plus selection produces.
2. **The edge is concentrated.** Excluding the best 5 symbols, zscore @ M falls from +2.27%
   mean to +1.26%; `volatility_scaling` goes **negative** (−0.17%). One of the two survivors
   is pure outlier.
3. **Exposure is 0.149.** It is profitable largely *by being in cash 85% of the time*, so it
   is not a usable book as constructed.

Its median CAGR is also only +3% — a high hit rate on small gains, not a return stream.

## Verdict on the Phase 1 hypothesis

I predicted the frequency lever would be "the whole story". **It is not.** Cost elimination
is worth ~0.8%/yr and stops there.

What the experiment actually found is more useful: **the constraint is deployment, not
signal.** A book that is in cash 55% of the time cannot earn an absolute return, regardless
of how cheap the trading is. `zscore_strategy` hints that some edge exists (it is the only
cell above the family distribution) but cannot deploy it.

## What this sets up

Phase 2 (buffered cross-sectional rebalance) is now clearly the right next move, because it
attacks both defects at once:

- forces continuous investment (top-N of the universe always held) → fixes exposure
- replaces names only on rank exit, not on every rebalance → keeps turnover near quarterly's

Kill criterion unchanged: it must beat a **signal-scrambled** version of itself at
FDR q<0.05. Given the selection problem documented above, a scrambled null is mandatory
rather than optional, and the multiple-comparison family (96 cells) must be carried through.

## Caveats

- 3 symbols were dropped this round: `adanient` (C3 corruption), `jiofin` (corrupt),
  `tmpv` (2025-10-14 demerger, unpriceable). Universe is 47, not 50.
- Every number above is **post-C10 and post-cost-fix**. The 9.52% headline and the 4,032-pair
  sweep predate both and are stale.
- Survivorship bias is still uncorrected and estimated at ~8.9 pp/yr (measured, floor).
- One config per strategy. This is a cost-schedule experiment, not a parameter search.