# Declared parameter budget — `distance_moving_average`

Written **before** any backtest was run, per brief §4. Exactly **5 variants** will be
evaluated. Nothing outside this list gets a performance number in this study.

## The source strategy

`src/cryptobot/strategies/catalog/distance_moving_average.py`

```python
dev = (close - sma(close, period)) / sma(close, period)
dev >  +threshold  ->  -1   # short  (price stretched ABOVE its MA)
dev <  -threshold  ->  +1   # long   (price stretched BELOW its MA)
otherwise          ->   0   # flat
```

It is a **pure mean-reversion** rule, `period=20`, `threshold=0.03` by default.

## Long-only translation — one deliberate, disclosed change

`GOAL.md` and the brief both forbid shorting: an Indian delivery account cannot take
the `-1` leg. **The short leg is discarded, not inverted.** So the tradable rule is
exactly one half of the source strategy:

> **Buy when the close is more than `threshold` below its `period`-day SMA.**

That is a strictly weaker strategy than the source. Any result below is a statement
about that half only.

## The 5 variants (exhaustive)

A variant is `(construction, period, threshold)`.

| # | construction | period | threshold | note |
|---|--------------|--------|-----------|------|
| V1 | `dev_depth` | 20 | 0.03 | **the source strategy's own defaults** |
| V2 | `dev_depth` | 20 | 0.05 | same MA, looser trigger |
| V3 | `dev_depth` | 50 | 0.05 | longer MA, looser trigger |
| V4 | `dev_depth` | 100 | 0.08 | quarter-year MA, wide trigger |
| V5 | `mom_ranked` | 20 | 0.03 | defaults, but rank signalled names by 126d momentum instead of by deviation depth |

Rationale for the grid, decided a priori from the strategy's own structure:

* The default `(20, 0.03)` is the only defensible starting point — V1.
* `period` and `threshold` are **not** independent. A longer MA makes `dev` smaller
  for the same price stretch, so holding `threshold` fixed while raising `period`
  would silently starve the signal. V2→V3→V4 therefore lengthens the MA *and*
  widens the threshold together, staying near a constant ~4% stretch.
* V5 exists to test the one genuinely open construction question: the brief (§5)
  recommends ranking signalled names by trailing momentum, while the literal reading
  of the strategy ranks them by how far below the MA they sit. These are different
  strategies and only one of them is really "distance MA". Testing it at the
  defaults keeps the construction question separable from the parameter question.

## Selection rule (fixed now, before seeing any number)

The TRAIN winner is chosen by **TRAIN Sharpe, net of costs**, highest wins. Ties
within 0.05 break toward the lower `period` (shorter MA, closer to the source
strategy). The winner is then run **unchanged** on TEST. I will not re-select after
seeing TEST.

## Controls (required by brief §6–§7, not counted as variants)

| control | purpose |
|---------|---------|
| equal-weight buy-and-hold, same 22 names | the bar to beat |
| `nsealgo.factors.build_composite_score` | the in-house composite |
| random signal, same % of name-days long, 3 seeds | a coin flip is the minimum bar |
| `reversal_20d` composite | literature-cited mean-reversion negative control |
| cost stress ×2, ×3 slippage | `GOAL.md` §5 Gate 4 |

## Pre-registered prior

`reports/FACTOR_EVIDENCE.md` (cited in `nsealgo/factors/core.py`) records that the
only multiple-testing-corrected study of Indian technical rules found 7 of 8
surviving configurations were trend-following, while RSI_25_75, RSI_30_70,
Bollinger_20/2.0 and Bollinger_20/2.5 all failed. `distance_moving_average` is a
Bollinger-band rule with a one-sided trigger. **The prior is that all five variants
underperform buy-and-hold out-of-sample.** I am recording that now so the finding
cannot be re-framed after the fact.