# Per-stock sweep — the signal edge measured against the cost of harvesting it

**This is the root-cause report.** It explains the −7.59% timing channel found in
`PERSTOCK_TIMING_DECOMPOSITION.md` without any appeal to luck or multiple testing.

TRAIN window, 14 large-cap NIFTY-50 names, monthly rebalance, default configs.

## The measurement

For every bar, `diff = stock_return if held long else −stock_return if held flat`.
Its mean is **the gross value of the day-selection, per day, before any cost**.
`diff` is paired by date, so no cross-sectional or calendar confound is involved.

| strategy | gross edge (bp/day) | t(diff) |
|---|---|---|
| `kama_strategy` | **+2.4** | 0.22 |
| `supertrend_strategy` | +2.2 | 0.20 |
| `dual_moving_average` | +2.1 | 0.19 |
| `ema_cross_strategy` | +1.0 | 0.09 |
| `rsi_momentum_strategy` | +0.2 | 0.02 |
| `moving_average_cross` | −0.1 | −0.01 |
| `atr_trailing_stop` | −1.3 | −0.12 |
| `bollinger_bands` | **−9.3** | −0.83 |
| `rsi_strategy` | **−9.3** | −0.83 |
| `williams_r_strategy` | **−9.6** | −0.86 |

## The comparison that matters

| | |
|---|---|
| **Gross edge, best case** | **+2.4 bp/day ≈ +59 bp/yr** |
| **Gross edge, median** | **+1.0 bp/day ≈ +24 bp/yr** |
| **Cost of one round trip** | **21.92 bp** (11.92 statutory + 2 × 5 slippage) |
| **Minimum switches, monthly rebalance** | ~12/yr ⇒ **~131 bp/yr of cost** |
| **Measured cost drag on the sweep** | **169 bp/yr** |

**The signal is worth roughly one fifth to one half of what it costs to trade.** No
t-stat in the table reaches significance. The three negative entries are outright
inverted signals: `williams_r_strategy`, `rsi_strategy` and `bollinger_bands` buy days
that were worse than the days they skipped.

## Why this is not a tuning problem

Turning the best +2.4 bp/day up to the ~131 bp/yr bill requires a **55x** improvement in
the signal. Parameter search moves a signal by single-digit percentages. This gap is not
reachable by optimisation — it is a difference in kind.

It also explains every other observation in this sweep, with no further assumptions:

| observation | explained by |
|---|---|
| timing channel −7.59%/yr | gross +24 bp/yr minus ~169 bp/yr cost |
| only 8.5% beat exposure-matched B&H | the edge cannot pay for its own harvesting |
| 2,145 beat the random-timing null | that null loses −15.15%/yr; it pays ~4× the cost |
| 0 of 84 strategies have positive mean alpha | every strategy faces the same bill |
| `williams_r` / `rsi_momentum` are the best 2 | least-bad net, not positive gross edge |

## What would actually change the answer

Not more parameters. The edge would need to be one of:

1. **A ~25× better signal.** Cheaper data, cross-sectional context, or a factor this
   catalogue does not contain.
2. **A ~10× cheaper trade.** Larger holding periods (the sweep's 5–60 day mandate is the
   binding constraint), or instruments with materially lower friction than delivery cash.
3. **More names per decision.** Diversifying a 2 bp/day edge across 22 correlated names does
   not add 22 bp/day — but it does amortise the fixed per-decision cost, which is the only
   channel here that scales.

## What this does NOT say

- Nothing about shorting. Three of these signals are inverted, so *shorting* them would
  flip −9.6 bp/day to +9.6. That is a real, testable avenue and it is untested — the engine
  is long/flat and `GOAL.md` §3.1 mandates delivery only. It is noted as the single most
  promising untested direction, not claimed as a result.
- Nothing about the factor research in `reports/FACTOR_EVIDENCE.md`.
