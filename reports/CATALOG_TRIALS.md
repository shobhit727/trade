# Catalog Strategy Trials — 27 agents, NSE NIFTY-50

**Protocol:** `research/AGENT_BRIEF.md`. One catalog strategy per agent. Parameters
declared up front (max 5 variants), selected on **TRAIN** (2016–2023), evaluated once on
**TEST** (2024–2026), net of the full Indian delivery cost stack (21.92 bps all-in).

---

## Headline: 27 of 27 failed. Zero made money.

No strategy beat plain buy-and-hold out-of-sample. Most did not even beat a random
signal of the same exposure, which is the minimum bar.

| Strategy | Verdict |
|---|---|
| absolute_momentum | NO — its ROC gate contributes **−0.44 pp/yr**; removing it improves the book |
| adx_trend | NO — **the strategy has no signal**; ATR is computed then discarded, signal is `sign(close[t]−close[t−1])` |
| anchored_vwap | NO — +0.06 pp/yr excess, t = −0.00 |
| atr_breakout | NO — validated negative |
| atr_trailing_stop | NO — CAGR **−1.56%**; the ATR band is a cash-drag dial, not a selector (TRAIN R²=0.97 vs invested) |
| bollinger_band_squeeze | NO — signal spread within ±0.04 of zero at all 10 thresholds |
| bollinger_bands | NO — **−0.11%** CAGR; loses to a coin flip |
| breakout_momentum | NO — 0.00% CAGR |
| cci | NO — 4.56% CAGR, Sharpe −0.18, 24th percentile vs a 100-seed null |
| cmf | NO — 5.40% CAGR, below the 6.5% risk-free rate; beats only 49% of random seeds |
| cointegration | NO — 3.27%; real edge exists at 21d but **reverses at 126d** |
| correlation_gate | NO — 3.53%; **contains no correlation logic at all**, it is a ROC deadband |
| cross_sectional | NO — **−0.18%** CAGR; the signal is a reversal here, long the wrong side |
| cumulative_delta | NO — 0.34% CAGR; redundant re-expression of momentum |
| dema | NO — 6.86% CAGR; loses to 200 random seeds (p = 0.861) |
| dispersion | NO — return statistically indistinguishable from **zero** (p = 0.55) |
| distance_moving_average | NO — 1.21%; loses to a coin flip; depth ranking is flat (Q1≈Q5) |
| donchian_channel | NO — 2.05%; fires 0.25% of bars; **the book can't be built** (37.8% invested) |
| dual_moving_average | NO — 1.46%; lost to random on 20/20 seeds |
| dual_momentum | NO |
| ema_cross | NO — 1.46%, Sharpe −0.32, Band E |
| ensemble_signals | NO — 2.18%; not an ensemble: SMA(10) and EMA(10) agree 93.4% of bars |
| fisher_transform | NO — 3.32%; lost to a coin flip by 2.27 pp/yr |
| flag_pattern | NO — 0.73%; **period is dead code**, it is a 2-day up-tick |
| gap_strategy | NO — 3.24%; the shipped "gap" is a 1-day close-to-close return |
| gaussian_strategy | NO — 5.56%; **period is decorative**, z-score always uses a 300-bar buffer |
| hull_moving_average | NO — 3.85%; beat only 2/20 random seeds |

---

## Why they all failed — three meta-findings

### 1. The momentum ranking carries ~100% of the load, and each gate subtracts from it
Multiple agents ran ablations that isolate this. `adx_trend`: momentum alone scores
**8.82%** on TEST; adding the strategy's own flag drops it to 5.62%. `ema_cross`: removing
the gate lifts TRAIN from 1.46% to **18.38%**. The gates are not selecting names — they
are deleting the highest-momentum names the ranking was about to buy.

This is exactly what the evidence survey predicted: these are **crypto time-series
indicators** (built for a book that can go short) dropped into a **long-only
cross-sectional** NSE book. In crypto, `−1` means cut to cash and dodge a 70% drawdown.
In a delivery account, `−1` maps to "a slightly different basket of 22 large caps",
beta ~0.9. The risk-control mechanism simply isn't available.

### 2. Indian equities continued; they did not reverse
The decisive, repeated finding. Bollinger bands: `corr(z, fwd) = +0.746` on TRAIN —
gated names' excess return is **negative in both windows** (t = −0.92, −1.21).
Cross-sectional: the long-minus-short spread is **−2.26 pp/yr TRAIN, −6.82 pp/yr TEST**.
Gaussian: the bucket the strategy **shorts** is the best one; the bucket it buys is worst.
Mean reversion is not merely absent in India, it is **inverted**.

This independently confirms the correction that removed the reversal factors from
`src/nsealgo/factors/core.py`.

### 3. Costs were never the binding constraint
Gross-vs-net gaps were small everywhere (e.g. fisher 4.27% → 3.32%, bollinger +0.09% →
−0.11%). Strategies lost on **selection**, not on fees. Fixing turnover would not
rescue any of them.

---

## Real bugs found — these outlast the strategies

### In `src/nsealgo` (both fixed)

| Bug | Severity | Impact |
|-----|----------|--------|
| **Costs charged at exactly half** | **CRITICAL** | `all_in_round_trip_bps` is per *total* turnover, but the engine multiplied it by *one-way* turnover (`sum|dW|/2`). Ratio proven exactly 0.500000. **Every CAGR in the project was flattered** and the Gate 4 slippage stress ran at half strength. |
| Stray weekend bars | HIGH | 4 bogus weekend dates (2010-02-06 Sat, 2019-10-27 Sun, 2020-11-14 Sat, 2025-02-01 Sat) each landed an interior NaN in 42 symbols, corrupting every rolling/ewm indicator for `period` bars after the hole — silently, because the loader only validated within each symbol. |

### In the crypto catalog (reported, not fixed — out of scope)

| File | Bug |
|------|-----|
| `indicators.py:76` `hull()` | Terms swapped: `2*WMA(period) - WMA(half)` should be `2*WMA(half) - WMA(period)`. The line is the **negative** of the intended smoother, so every consumer's signal is **inverted**. |
| `adx_trend_strategy.py` | ATR computed then discarded — no trend strength is ever used |
| `correlation_gate.py` | No correlation statistic of any kind despite the name |
| `donchian_channel` | Channel includes today's high, so a breakout can never fire (0.25%, 0% on TRAIN) |
| `gap_strategy.py:30` | Computes close-to-close return, not a gap; `threshold=0.0` default is a no-op (fires 49%) |
| `flag_pattern.py` | `period` is dead code — hardcoded 3-bar chain |
| `gaussian_strategy.py` | `period` decorative — z-score always uses the 300-bar buffer |
| `cointegration_strategy.py` | No pair, no spread, no hedge ratio — it is single-name z-score mean reversion |
| `atr_trailing_stop.py` | Contains no trailing stop: no peak, no trail, no stop |
| Dead config | `period` is inert in cross_sectional, gap, cointegration (`period` is read only by `warmup()`) |

### In the dataset

- `high == open` on **6.68% of bars**, worst on violent days. Every breakout-level
  strategy (donchian, atr_breakout, squeeze, nr4) reads a column that is wrong precisely
  on the moves it exists to catch.

---

## Methodology notes the agents forced

These affect how much the numbers above can be trusted:

- **pandas 3.0.5 changed `stack()`** — it no longer drops NaN. Any `.where(mask).stack()`
  followed by `len()` silently uses the unmasked count, deflating t-stats by up to √60×.
- **Slicing a panel before computing indicators destroys warmup.** `build_composite_score`
  has a 252-bar factor, so scoring a sliced window silently loses ~12 months of history.
  One agent measured this as **6.5pp of CAGR**.
- **Residual weights dilute sparse signals.** `apply_turnover_budget` blends toward the
  previous target, so names that stop being flagged decay toward zero instead of exiting.
  For a low-liveness oscillator (fisher flags ~13 of 48), **59% of the book was stale
  residue**. This inflates headline Sharpe into something that is not a clean read on the
  signal.
- Several agents found and fixed bugs in **their own** harnesses (compounding errors
  producing impossible benchmarks, a `np.random.permutation` that permuted rows so the
  "random" control never changed holdings, vacuously-passing sector-cap assertions). The
  plausibility check in §6.1 of the brief is what caught them.

---

## What this means

1. **The crypto catalog does not transfer to NSE.** Not because the strategies are badly
   coded, but because a long-only cross-sectional Indian equity book is a different
   problem from a long/short crypto book.
2. **Nothing here beats buy-and-hold.** Not by a little — several lose to a coin flip.
3. **The most valuable output was the bugs**, especially the half-cost one, which had been
   inflating every headline number in this project.

## If someone continues

The untested ideas, in rough order of promise:

- **Index-level application.** `absolute_momentum`'s agent proposed this: the crypto
  thesis is expressible only at the index level in a delivery account, via
  `regime.exposure_series`. That is what `src/nsealgo` already does — and it is the one
  place a "regime switch" survived.
- **Rank, don't gate.** Every failure above is a gate failing. A continuous
  cross-sectional score on the *whole* universe (e.g. normalised distance-to-HMA) can
  differentiate where a binary `close > MA` cannot.
- **The 3% of names with real information** (quality, payout) is unavailable from OHLCV
  alone. Getting fundamentals would change the question entirely.

**Nothing above has been tested. Do not treat it as a result.**