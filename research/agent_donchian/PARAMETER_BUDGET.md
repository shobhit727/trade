# DECLARED PARAMETER BUDGET — donchian_channel agent run

**Frozen 2026-10-07, before any backtest was executed.** Exceeding 5 variants
invalidates the run. This file is the record.

## The 5 variants (exactly 5, no more)

| # | Label | Signal semantics | Channel period |
|---|-------|------------------|----------------|
| V1 | `literal_p20` | **As shipped.** Channel window INCLUDES today: `close >= max(high[-p:])` | 20 |
| V2 | `breakout_p20` | **Classic Donchian.** Channel is the PRIOR p bars, today excluded: `close > max(high[t-p:t])` | 20 |
| V3 | `breakout_p55` | Classic Donchian | 55 |
| V4 | `breakout_p10` | Classic Donchian | 10 |
| V5 | `breakout_p100` | Classic Donchian | 100 |

V1 exists because the as-shipped signal must be measured, not assumed. It is the
baseline. The only change from V1 to V2-V5 is the *semantic* one (exclude today
from the window); the period is the strategy's own knob.

## Held constant across all 5 — NOT tuned, so the budget is spent only on the period

| Setting | Value | Why |
|---------|-------|-----|
| Cross-sectional ranking lookback | 126d (6-month) trailing momentum | brief §5 recommended form; held fixed so period is the only free knob |
| Rebalance | Monthly (`"M"`) | engine default; no Indian study supports weekly (engine docstring) |
| `PortfolioConfig` | `PortfolioConfig()` — 22 names, 12% single, 25% sector, 10% cash, 35% turnover budget | `GOAL.md` §3.2; **not bypassed** |
| Costs | `CostModel(segment="delivery", slippage_bps=5)` | full Indian delivery stack, mandatory |
| Direction | Long-only. `-1` signals are discarded, never held. | delivery accounts cannot short |

## Selection rule — declared before the TRAIN numbers were seen

**Highest TRAIN Sharpe.** Tie-break: TRAIN Calmar. The winner is then run on
TEST **exactly once, with no parameter change of any kind.**

## Controls (required by brief §6; these are NOT parameter variants)

* Buy-and-hold over the identical window.
* Random-signal control with the same % of bars long (5 seeds).
* The `nsealgo` composite (`build_composite_score`) on the same panel.

## Disclosure: what TEST was touched before the TRAIN run

* `recon.py` measured **signal liveness only** (fraction of name-bars long /
  short / flat) on TEST. It computed **no return, no equity curve and no
  performance metric on TEST**, and selected nothing.
* No TEST return was inspected before the single post-selection TEST run below.