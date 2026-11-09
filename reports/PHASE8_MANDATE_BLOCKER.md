# Phase 8 — the binding blocker is the mandate, not the strategy

**Status:** complete. The money-making strategy exists and is measured.
**What is missing is permission to run it.**

## The strategy that makes money

Cross-sectional book, top-20 of the point-in-time NIFTY-50 universe, ranked on
distance above the 200-day moving average, annual rebalance with a +20 rank hysteresis
buffer, ₹21,00,000, full statutory cost stack (32.32 bp round trip) plus FIFO lots and
STCG/LTCG.

| window | CAGR (net) | Sharpe | MaxDD | exposure | round trips/yr |
|---|---|---|---|---|---|
| TRAIN 2016–23 | +17.2% | 1.10 | −32.9% | 100% | ~1 |
| TEST 2024–26 | +7.7% | 0.56 | −21.0% | 100% | ~1 |
| ALL 2009–26 | +16.9% | 1.04 | −33.8% | 100% | ~1 |

It makes money in absolute terms in 12 of 13 walk-forward folds. **It has no edge**
(Phase 7: 8/13 vs holding the universe, p=0.240) — the return is from being invested,
cheaply. That is the honest characterisation and it is what gets shipped.

## Why it cannot be deployed as configured

`nsealgo/risk/limits.py` hard-codes, per GOAL.md §3.3:

```
max_drawdown_halt     -15%   -> flatten and stop trading
max_drawdown_absolute  -25%   -> permanent capital-preservation mode
```

The book's MaxDD is **−33.8%**. Deployed, the kill switch fires and the account sits in
cash permanently. This is not a marginal miss: it is the strategy being switched off.

## Why the limit is incompatible with the asset

Measured on the equal-weight universe, 2009–2026:

| threshold | fraction of time below |
|---|---|
| −5% | 47.7% |
| −10% | **28.2%** |
| −15% | 16.5% |
| −25% | 9.2% |

Worst drawdown **−67.9%** (Dec 2008). Indian largecaps are simply a high-volatility asset
class; a −15% portfolio drawdown is an ordinary event, not a signal that something broke.

## Simulating the kill switch (equal-weight universe)

| rule | CAGR | MaxDD | time in cash | cost |
|---|---|---|---|---|
| buy & hold | **+12.22%** | −67.9% | 0% | — |
| flatten at −15%, re-enter at −10% | +4.87% | **−34.4%** | 21% | **−7.4 pp/yr** |
| flatten at −15%, re-enter at −5% | +4.49% | −30.8% | 31% | −7.7 pp/yr |
| flatten at −25%, re-enter at −20% | +5.88% | −52.4% | 11% | −6.3 pp/yr |

The switch is not even effective on its own terms: it **gives up 7.4 pp/yr and still
leaves a −34.4% drawdown**, because a −15% trigger on a −68% asset means re-entering
into a continuing decline, repeatedly.

## The decision

The −15% halt was written for a **single-stock, 5–60 day** book, where a 15% portfolio
drawdown genuinely means something is broken and the right response is to stop. It is
inherited unchanged into a **diversified, always-invested** book, where the same number
is a normal event and where obeying it destroys 60% of the return.

Three coherent options, and only the human can choose:

**A. Widen the halt to fit the asset class.** −15% → −35% halt, −25% → −50% absolute.
Keeps the book intact, keeps ~17%/yr, and the limit still fires on a genuine
catastrophe. The constitution changes, not the code's shape.

**B. Keep the limits, cut exposure to fit.** Scale the book to e.g. 50% invested so a
−68% asset drawdown maps to ~−34%... which still breaches. Even 25% exposure breaches
−15% in 2008. **There is no exposure level that satisfies −15% while holding this asset.**

**C. Change the asset, keep the mandate.** An Nifty ETF has the same 2008 drawdown, so
this does not help for the limit — it only cuts the cost stack 5× (6.42 vs 32.32 bp all-in
per `reports/INSTRUMENT_COSTS.md`) and removes single-stock risk. Useful, but it does
**not** resolve the −15% conflict.

## Recommendation

**A**, on the evidence: the limits are the binding constraint, they were calibrated for
a mandate that no longer exists, and option B has no solution. The halt must not be
removed — a catastrophic drawdown guard is genuinely valuable — but it must be
re-calibrated to the volatility of what is actually held.

The alternative, if the −15% limit is non-negotiable, is that **no long-only Indian
equity strategy can be run under this constitution**, and the honest response is to say
so rather than to search for a strategy that magically avoids a −15% drawdown. Four
independent tests have already shown no such edge exists in price-only technicals.

## What happens after the decision

1. Recalibrate `risk/limits.py` (or leave it, per the decision) with the new numbers
   written into GOAL.md §3.3 and `verify_limits()` updated to match.
2. Wire the measured book into the live engine — the current `EngineConfig` is monthly,
   22 positions, with a per-stock regime overlay that Phase 1 proved destroys returns
   (exposure 0.45 → median CAGR 0.000). It needs annual rebalance, N=20, the +20
   buffer, and no per-stock regime cut.
3. Point-in-time membership must gate selection in the live path (Phase 0's lagged
   membership), or the live book will silently reintroduce the 1.6–7.2 pp/yr
   survivorship bias.
4. Paper trade to validate real fills — the largest untested assumption left, since
   every number here assumes 32.32 bp and 5 bp/side slippage across 20 names.
5. Then, and only then, live capital.

**No capital deploys until steps 1–4 are done.** Band D stands.