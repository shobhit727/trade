# Phase 1 → 2 → 0 — what actually works, and what does not

**Verdict: there is no edge. What works is being invested.**

This supersedes every prior performance claim in `reports/`. It is written against
the corrected cost stack (32.32 bp/round trip, was understated 1.469×), the C10-repaired
panel, and the point-in-time universe.

## The one thing that made money

A cross-sectional book of the top-20 NIFTY names, ranked on distance-above-200dma,
rebalanced annually with a +20 rank hysteresis buffer, on Rs21L:

| window | CAGR | benchmark | alpha | Sharpe | MaxDD |
|---|---|---|---|---|---|
| TRAIN 2016–23 | +21.7% | +15.9% | +5.7 pp | 1.16 | −40.8% |
| TEST 2024–26 | +11.2% | +6.8% | +4.4 pp | 0.71 | −23.3% |
| PIT-corrected ALL | +16.9% | +19.2% | −2.3 pp | 1.04 | −33.8% |

It reliably makes money in absolute terms. **And it has no edge**: see below.

## Why there is no edge

Every measurement is against a **signal-scrambled null** — each date's cross-section
independently permuted, preserving the score distribution while destroying the
symbol↔score association. Not a time-shift, which would smuggle real lagged
information back in.

Walk-forward, annual folds, params fixed (re-selected once on the first fold only):

| universe | folds | beat null | mean edge | t-test p | binom p |
|---|---|---|---|---|---|
| fixed50 | 13 | 6/13 (46.2%) | +0.61 pp | 0.778 | 0.709 |
| **point-in-time** | 13 | 8/13 (61.5%) | +1.49 pp | **0.386** | **0.291** |

A coin flip. `p=0.386` on the corrected universe is the number that governs, and it
says the signal is indistinguishable from a random ranking of the same names.

Under the corrected universe the TRAIN advantage nearly vanishes:
**trend +2.64 pp → +0.41 pp; composite +4.18 pp → −0.79 pp.**

## What each phase actually established

**Phase 1 — the rebalance clock (9,024 runs).** Cutting turnover 55× (daily→annual)
drove fees from 0.883% to 0.016% and tax to zero, and bought **~0.8%/yr**. Not the lever.
The binding constraint was **exposure**: median exposure ~0.45 at every clock, and the
only bucket with a positive median CAGR was >60%. A book in cash 55% of the time cannot
earn an absolute return.

**Phase 2 — buffered cross-sectional (528 runs).** Forced exposure to 1.000, and the
hysteresis buffer works as designed (turnover 4.41 → 2.81 at buffer 0→20, CAGR unchanged).
On TEST the trend family beat its null in 43/44 configs (p=2.6e-12) — **which was
selection**. 44 configs on one 2.75-year window; the walk-forward erased it.

**Phase 0 — survivorship (point-in-time universe).** Worth **1.6–7.2 pp/yr**. It inflated
the signal *and* the null, which is precisely why Phase 2's result looked good: a universe
containing only today's winners flatters any strategy run inside it.

## Bugs found and fixed (both were corrupting prior results)

1. **Cost stack understated 1.469×.** `STATUTORY_BPS` documented as bps-of-turnover but
   consumed as bps-of-notional. True delivery round trip is **32.32 bp, not 21.92**; cost
   drag is ~249 bp/yr, not 169. Now derived from `nsealgo.costs.CostModel`.
2. **TRENT 1:1.5 bonus on 2026-01-01**, inside the TEST window, read as only −33.0% and
   slipped under C5's 45% bar — a phantom −33% crash in every TRENT result. New loader
   rule C10 repairs it, and is deliberately one-sided: an earlier draft truncated on
   ambiguity and **would have deleted real 2008 drawdowns**.
3. **NaN-masked PIT panel** poisoned equity curves (206 NaN bars, nonsense −100% MaxDD).
   Membership now gates selection only; prices stay observed.

Every stored nsealgo result predates (1) and (2) and is **stale**.

## Honest target

Under the stated bar — *positive absolute return, all costs and tax* — the achievable
result is **a mostly-invested, low-turnover, mildly-tilted large-cap equity book
returning roughly 12–17% net, with drawdown no better than the index.**

The signal contributes nothing measurable. What earns the return is being invested, and
the book's real deliverable is **capital efficiency: ~100% exposure at ~1–3 round trips
a year on 32.32 bp**, versus the single-stock book's 45% exposure at 14–55 round trips.

## GOAL.md must change

- **3%/month (42.6%/yr) is unreachable** and must be retired as the headline target.
- Replace with: net **12–17%/yr**, MaxDD no better than index, must clear the scrambled
  null at q<0.05 — which on current evidence it does not.
- Band D stands. **No capital deployment.** The instrument remains research-only.
- `TMPV` excluded (2025-10-14 demerger, unpriceable); universe is **47**.

## What would change this conclusion

Only new information, not more search:
- **Fundamentals** (value/quality/earnings revisions) — the strongest documented Indian
  premia and genuinely absent from a price-only panel. Deferred by decision until now.
- **The short side** — untested; market-neutral (β≈0) is the one quadrant never measured,
  and the edge decomposition is what pointed there.
- **Execution realism** — a live paper run on actual fills, which no backtest substitutes
  for. Real slippage on Rs21L across 20 names is the largest untested assumption left.

Re-running any of this on the same 47 symbols, same signals, and searching harder is
guaranteed to produce nothing: the null is already beaten at p=0.386.