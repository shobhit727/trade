# Morning report — 2026-08-23 night shift

## 1. Matrix sweep COMPLETE (phase 1)

1,068 backtests: 89 algos × 6 timeframes × BTC+ETH, real data, honest
per-bar mark-to-market, taker costs (5bps fee + 3bps slip per side).
Runtime ~7.5h on 8 cores. Full tables: `PROJECT_MEMORY/30_HFT_Matrix_Sweep.md`.

## 2. The headline finding — taker-fee intraday is annihilated

| timeframe | BTC profitable | ETH profitable | character |
|---|---|---|---|
| 1m | 1/89 | 2/89 | catastrophic (-14,000% equity runs) |
| 5m | 2/89 | 1/89 | catastrophic |
| 15m | 2/89 | 1/89 | catastrophic |
| 1h | 2/89 | 4/89 | catastrophic |
| **4h** | **7/89** | **15/89** | mixed; open_range ETH +288% |
| **1d** | **29/89** | **31/89** | the only healthy zone |

At 9,000–13,700 trades per run on 1m bars, round-trip costs compound to
total account destruction. This is not marginal — it is absolute.

## 3. What this means for the HFT goal

- **Market-order HFT at bar close cannot work at taker fees.** Proven across
  every algorithm we have. No parameter tuning fixes a -16bps/round-trip
  structural drain at 10k trades.
- **The genuine HFT path is maker execution**: limit orders resting on the
  book (1bp or rebate instead of 5bps+slip). Fee-survival estimates say
  43–73 algos per short TF *flip positive* under maker pricing — but those
  estimates are unreliable until two prerequisites land:
    1. **Bankruptcy guard** (#55): many runs went to negative equity,
       invalidating their rows.
    2. **Maker-fill simulation**: resting-limit logic (fill when price
       trades through), queue-position honesty, adverse-selection cost.
- **4h is the sweet spot that exists today**: 7–15 survivors with real
  returns (open_range ETH +288%). Worth walk-forward validation now.

## 4. Other night deliverables

- **MultiAlgoTrader shipped** (`live/multi_trader.py`): N strategies per
  symbol in one process, per-algo equity slices + attribution;
  `bot --algos-json` / BOT_ALGOS env. Phase-4 blocker removed.
- **Live fills now update the position book** (was empty → risk blind).
- **Issues filed**: #54 (17 duplicate/fake catalog algos — dema/hull/kama/
  tema are plain EMA stubs), #55 (no bankruptcy guard).
- Gate bots healthy: day 2/60, both ₹10k, zero fills yet (expected for 1d).

## 5. Recommended next steps (in order)

1. Implement bankruptcy guard (#55) — small, unblocks honest retests.
2. Walk-forward validate the 4h survivors (open_range, macd, funding_trend…)
   using `tools/wf_validate.py`.
3. Build maker-fill simulation; re-run 5m/15m grids under maker assumptions.
4. Then decide the production gate config: likely top-N from {4h validated}
   ∪ {maker-mode intraday survivors}, run via MultiAlgoTrader.
