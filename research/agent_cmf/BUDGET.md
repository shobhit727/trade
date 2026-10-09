# PARAMETER BUDGET — DECLARED BEFORE ANY BACKTEST WAS RUN

Strategy: `cmf_strategy` (`src/cryptobot/strategies/catalog/cmf_strategy.py`)
Signal: CMF(period) > +0.10 -> long(+1); CMF < -0.10 -> short(-1). Long-only NSE
book cannot short, so the short leg must be expressed either by inverting the
signal (long the LOW-CMF names) or by ignoring it.

Justification for the budget (TRAIN-only diagnostics, `02_diag_train.py`, run
before this file was written; TEST never opened):

| CMF period | IC vs 21d fwd return (all names, TRAIN) | t     | hit rate |
|-----------|--------------------------------------------|-------|----------|
| 10        | -0.01509                                   | -3.65 | 46.7%    |
| 20        | -0.02019                                   | -5.04 | 45.2%    |
| 60        | -0.00303                                   | -0.72 | 48.7%    |

The information coefficient is **negative** at 10d and 20d with |t| > 3.6. So the
catalog's long leg (high CMF) is *anti*-predictive on TRAIN and its short leg
(low CMF) is the predictive one. Sign is therefore the first thing to test, not
a detail. A budget that only explored the literal long leg would have tested
nothing.

Liveness on TRAIN (fraction of bars): CMF(20) > +0.10 on 23.2%; CMF(20) < -0.10
on 27.4%; CMF(10) > +0.10 on 28.9%; CMF(60) > +0.10 on 11.9%. Flagged names per
monthly rebalance date, median: 10 (p20/+0.10), 12 (p10/+0.10), 5 (p60/+0.10).
So thresholded variants will typically hold fewer than the 22 permitted names —
that is a real property of the signal, not an artefact, and will be reported.

## The 5 variants (this list is exhaustive; running a 6th invalidates the run)

| # | period | threshold | direction | construction | note |
|---|--------|-----------|-----------|--------------|------|
| V1 | 20 | +0.10 | literal (long HIGH CMF) | momentum-126d rank among flagged | catalog strategy exactly as written |
| V2 | 20 | +0.10 | FLIPPED (long LOW CMF) | momentum-126d rank among flagged | sign-flip motivated by negative TRAIN IC |
| V3 | 10 | +0.10 | FLIPPED | momentum-126d rank among flagged | faster window |
| V4 | 60 | +0.10 | FLIPPED | momentum-126d rank among flagged | slower window, smoothest CMF |
| V5 | 20 | none | FLIPPED (continuous) | cross-sectional rank of -CMF | no threshold, no momentum gate: isolates CMF alone and always fills 22 names |

Common to all: `PortfolioConfig()` defaults (22 names, 12% single name, 25% sector,
10% cash, 0.35 turnover budget, max 30 names), monthly rebalance, `CostModel
(segment="delivery", slippage_bps=5)`. No variant changes costs, portfolio
constraints, rebalance frequency, or the momentum lookback.

## Selection rule (fixed now, before results exist)

1. Rank the 5 variants by **TRAIN** Sharpe. Highest wins.
2. Tie-break on TRAIN Calmar, then TRAIN MaxDD (least negative).
3. Run the single winner **once, unchanged**, on TEST. Report that number.
4. Report all 5 TRAIN rows anyway, so the selection is auditable.

## Controls (required by the brief; not parameter variants)

* buy-and-hold equal-weight universe over the identical TEST window, same costs
* random signal at the winner's TRAIN liveness, same % of bars long
* nsealgo composite (`build_composite_score`) on the same panel

## Honest pre-registration

If V1 (the literal strategy) wins on TRAIN and the flipped variants lose, the
finding is "CMF as written works on NSE" and I report it. If a flipped variant
wins, the finding is that the *sign* is wrong for Indian equities, which means
the strategy does not work as written — I will say so plainly rather than
claiming a win by inverting it.