# DECLARED PARAMETER BUDGET — dual_momentum (written BEFORE any backtest was run)

The strategy has exactly two knobs (`DualMomentumConfig.fast`, `.slow`). The score
construction is **fixed, not tuned**, to the AGENT_BRIEF §5 recipe verbatim:

```python
score = (panel / panel.shift(126) - 1.0).where(signal_panel > 0).rank(axis=1, pct=True)
```

All other engine settings are `nsealgo` defaults and are identical for every variant,
the composite baseline, and the controls: monthly rebalance, 22 positions, 12% single
name, 25% sector, 10% cash, 35% turnover budget, `CostModel(segment="delivery",
slippage_bps=5)`.

## The 5 variants I am allowed to test

| # | fast | slow | note |
|---|------|------|------|
| V1 | 10 | 30  | the catalog default, verbatim — 2wk / 6wk, calibrated for crypto intraday |
| V2 | 20 | 60  | 1mo / 2.5mo |
| V3 | 50 | 200 | 2mo / 8mo, the classic 10-month trend template |
| V4 | 10 | 100 | 2wk / 4mo, isolates "slow EMA too slow to matter at 10" |
| V5 | 30 | 120 | 6wk / 5mo |

Selection rule, fixed in advance: **pick the TRAIN-window Calmar**, with TRAIN CAGR as
the tie-break. Calmar because GOAL.md §2.3 grades on drawdown and §5 Gate 2 requires
Sharpe > 0.5 — a variant that wins on return while eating a 40% drawdown is not
deployable. Whatever wins on TRAIN goes to TEST **unchanged**, once.

## Things I will NOT do

- Not more than these 5. If the code below ever needs a 6th, that is a failed run.
- Not re-score on TEST.
- Not swap the score recipe on the basis of any TRAIN or TEST equity curve.
- Not touch `src/nsealgo/**`, `src/cryptobot/**`, any test, `GOAL.md`, or `reports/`.
