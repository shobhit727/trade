# agent_dema — DECLARED PLAN (written BEFORE any run)

Strategy: `DemaStrategy` (`src/cryptobot/strategies/catalog/dema_strategy.py`)
Signal: `+1 if close > DEMA(close, period) else -1`, DEMA = `2*EMA1 - EMA(EMA1, period)`,
EMA seeded at the first available close, `k = 2/(period+1)`.

Verdict on crypto-specificity: **not** crypto-specific. A double exponential moving
average is a plain price-trend indicator; it has direct meaning on NSE daily bars. So
the "no NSE meaning" escape clause does NOT apply and I proceed.

## Split

| Set | Window |
|-----|--------|
| TRAIN | 2016-01-01 -> 2023-12-31 (tune only) |
| TEST  | 2024-01-01 -> 2026-10-01 (touched once, at the end) |

## PARAMETER BUDGET — 5 declared variants (the maximum allowed)

The strategy has exactly one free knob: `period`. The book construction is fixed
across all variants (brief §5 recipe), **except** in V5 which is a deliberate control.

| # | period | cross-sectional score |
|---|--------|----------------------|
| V1 | 20 (catalog default) | DEMA>0 gate, then rank by trailing 126d (6m) momentum |
| V2 | 50  | DEMA>0 gate, then rank by trailing 126d (6m) momentum |
| V3 | 100 | DEMA>0 gate, then rank by trailing 126d (6m) momentum |
| V4 | 200 | DEMA>0 gate, then rank by trailing 126d (6m) momentum |
| V5 | 20 (catalog default) | **pure DEMA**: rank by close/DEMA - 1, no momentum overlay |

Fixed and NOT tuned (identical in every run):
- rebalance = monthly (`"M"`), the engine default
- `PortfolioConfig(n_positions=22)` — engine defaults for max_weight 12%, sector 25%,
  cash buffer 10%, turnover budget 0.35, max_names 30
- cost model `CostModel(segment="delivery", slippage_bps=5)`
- momentum ranking lookback 126d (from `nsealgo.factors.core.momentum_6m`, the
  project's own documented best long-only Indian momentum variant)

Selection rule, fixed in advance: pick the V with the best TRAIN Sharpe. Ties broken by
best TRAIN MaxDD. Then run that ONE variant, unchanged, on TEST. No re-selection after
seeing TEST.

V5 exists because V1-V4 all share the momentum overlay; without it I could not tell
whether the DEMA period "works" or whether the overlay is silently carrying the result.
It is a control, not a candidate for selection.

## Reported controls (not parameter variants)

- buy-and-hold equal-weight over the identical window
- random signal with matched % of bars long (20 seeds, TEST)
- `build_composite_score` benchmark over the identical window
- cost stress (Gate 4): zero / base / double / triple slippage
- plausibility, avg-names, signal-liveness checks per brief §6