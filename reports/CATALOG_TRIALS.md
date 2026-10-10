# Catalog Strategy Trials — 38 agents, NSE NIFTY-50

**Protocol:** `research/AGENT_BRIEF.md`. One catalog strategy per agent. Parameters
declared up front (max 5 variants), selected on **TRAIN** (2016–2023), evaluated once on
**TEST** (2024–2026), net of the full Indian delivery cost stack (**21.92 bps all-in** =
11.92 statutory + 2 × 5 slippage).

---

## Headline: 38 of 38 failed. Zero made money.

No strategy beat plain buy-and-hold out-of-sample. Several could not beat a **random
signal of the same exposure**, which §6.5 of the brief names as the minimum bar.

**The most valuable output of these 38 trials was not a strategy. It was two critical bugs
in the shared backtest engine** — one of which had been inflating *every* headline number
this project had ever published.

---

## Wave 1 — 27 agents (2026-10-07 → 2026-10-09)

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
| hull_moving_average | NO — 3.85% CAGR, Sharpe −0.14; beat only **2 of 20** random seeds. See the corrected Hull finding below |

---

## Wave 2 — 11 more agents (2026-10-09 → 2026-10-10)

**Every one negative.** TEST CAGR is net of the full Indian cost stack; buy-and-hold on the
same 2024–2026 TEST window is ≈8.2% CAGR / Sharpe +0.18 for most of these runs.

| Strategy | TEST CAGR | Sharpe | Verdict and why |
|---|---:|---:|---|
| **momentum_factor** | **−0.36%** | **−0.48** | NO — the "factor" contains **no cross-sectional information at all**; nothing in the file compares one symbol to another. Lost to a coin flip by **5.81 pp/yr** and 0.44 of Sharpe, on a book drawn down 11.06pp *less*. Composite +6.04% beat it by 6.40pp. |
| **momentum_volatility** | **+2.59%** | **−0.32** | NO — the `atr` term enters only as the predicate `b > 0` and is a tautology in-window: **despite the name this is a plain ROC filter**, not "momentum + volatility". Beat all 20 random seeds and the composite (+0.71%) — but still 7.05 pp/yr behind buy-and-hold. A *selection* failure, not a noise failure. |
| **multi_factor** | **+1.79%** | **−0.38** | NO — "multi-factor" is **two binary votes summed**: `close>SMA` and `RSI>50`. No weighting, no cross-section, no fundamentals. Gross Sharpe is negative too (−0.21), so costs are not the cause. Beats random on only **40%** of seeds. Composite beats it by **5.82pp CAGR, 0.52 Sharpe and 3.75pp of drawdown**. |
| **supertrend** | **−1.31%** | **−0.61** | NO — and this is the sharpest bug finding in wave 2: **the shipped `supertrend_strategy.py` is not Supertrend.** It computes ATR and throws it away; the signal is `sign(close[t]−close[t−1])`. `period` and `multiplier` have *no effect whatsoever* — every config produces byte-identical output. Porting a *correct* Supertrend lifts TRAIN Sharpe 0.447 → 0.735 (**+0.29**), but even that loses to a random book on **90% of seeds**. Gross +0.39% → net −1.31%: costs turn flat into negative, but the strategy is not cost-limited, it is signal-limited. |
| **rsi** | **+3.38%** | **−0.41** | NO — below the 6.50% Indian T-bill, so the negative Sharpe is not a rounding artefact. Loses to buy-and-hold, to the composite, and to an untilted book. *(Also the agent that caught the engine changing mid-run — see `engine_sha` below.)* |
| **macd** | **+4.07%** | — | NO — vs buy-and-hold **8.18%**. Also: the "signal line" is a **simple mean**, not an EMA, and `warmup()` is short by `signal` bars (harmless here). All TEST numbers verified byte-identical across repeated runs. |
| **relative_strength** | **−0.36%** | **−0.48** | NO — **despite the name, nothing in the file compares one symbol to another**; `roc()` is a pure per-symbol time-series function. A genuinely cross-sectional reading (ROC vs the universe median) was also measured and is no better. **Lost to a fully random score 20 times out of 20.** |
| **regime_switch** | **+3.76%** | **−0.22** | NO — worse return, worse Sharpe and worse Calmar than buy-and-hold (8.18% / +0.18). **The assignment's thesis was half right, and the half that was wrong is the interesting half:** mapping `−1 → cash` *does* work, and the one genuine out-of-sample effect is the expected one — a **4.2pp smaller drawdown**. But it buys that with 4.4pp of annual return, and a boring constant-beta book beats it on return, Sharpe *and* drawdown simultaneously. The cash leg is real; **the edge in choosing when to use it is not.** The catalog default `period=20` returns **−1.23%**. |
| **volatility_target** | **+2.59%** | **−0.40** | NO — the unit error is the finding: `target=0.01` is compared against `ATR/close`, so the effective threshold is **2.0% of price**, which is the **25th percentile of the TRAIN distribution**. Worse, out of sample the signal is **significantly worse than random at the name-day level** (−5.86 bps/day, Welch **p = 0.0014**). |
| **trend_momentum** | **−0.27%** | — | NO — fails the negative control **0 of 20**; it was the worst of 21 books compared. Also worse on drawdown (−22.58% vs −15.90%), worse on Sharpe by 0.62, worse on Calmar by 0.52. |
| **hull_moving_average** *(re-run, corrected)* | **+3.85%** | **−0.14** | NO — see the corrected Hull finding below. Beat only 2 of 20 random seeds. |

**Buy-and-hold on this TEST window scores ≈8.2% CAGR / Sharpe +0.18** (it varies by a few
tens of bps across agents because of universe and weighting choices — `8.18%` in five
runs, `8.22%` and `9.64%` in two others, `2.60%` in the Hull run's own harness).

**The nsealgo composite's TEST figure varies more — ≈6.0% / +0.03 in most runs but 7.61% /
+0.14 in `multi_factor`'s.** That spread is not a disagreement between agents; it is the
`engine_sha` problem in miniature — several wave-2 agents ran against different engine
revisions. Cross-agent composite comparisons below ~1.5pp should not be treated as
meaningful.

Note also that the composite's own TEST Sharpe is barely positive: the 2024–2026 window is
a grinding stretch in which almost nothing made a risk-adjusted return. That is a property
of the window, stated here so none of these negatives is mistaken for evidence about the
window.

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

Wave 2 sharpened this rather than contradicting it: the one strategy whose thesis *is*
expressible long-only — `regime_switch`, where `−1 → cash` — got the drawdown reduction it
predicted and still lost on return, Sharpe and Calmar to a static beta book.

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
−0.11%). `supertrend` is the cleanest demonstration: gross **+0.39%** → net **−1.31%**,
and even at **zero cost** it reaches only +4.26% — below the 5.25% median of its own random
control. Strategies lost on **selection**, not on fees. Fixing turnover would not
rescue any of them.

---

## Real bugs found — these outlast the strategies

### In `src/nsealgo` (all fixed)

| Bug | Severity | Impact |
|-----|----------|--------|
| **Costs charged at exactly half** | **CRITICAL** | `all_in_round_trip_bps` is per *total* turnover, but the engine multiplied it by *one-way* turnover (`sum\|dW\|/2`). Ratio proven exactly **0.500000**. **Every CAGR in the project was flattered** — the headline fell **10.97% → 9.89%**, Sharpe 0.44 → 0.35 — and the **Gate 4 slippage stress ran at half strength**, i.e. a gate was certifying a robustness property the backtest never tested. |
| **Residual-weight dilution** | HIGH | `apply_turnover_budget` blended the whole book toward the new target, so names that stop being flagged **decay instead of exiting**. For a low-liveness oscillator (fisher flags ~13 of 48) **59% of the book was stale residue**, and realised exposure averaged **~0.6 of the intended 0.9**. The book was measuring the harness, not the signal. Headline fell **9.89% → 9.71%**. Fixed with whole-position exits and all-or-nothing adoption when the budget binds. |
| Stray weekend bars | HIGH | 4 bogus weekend dates (2010-02-06 Sat, 2019-10-27 Sun, 2020-11-14 Sat, 2025-02-01 Sat) each landed an **interior NaN in 42 symbols**, corrupting every rolling/ewm indicator for `period` bars after the hole — silently, because the loader only validated *within* each symbol. Fixed as cleaning rule **C8**; panel is 4,625 days. |

### Two high-value infrastructure findings

**1. `engine_sha` — results are now fingerprinted.** `BacktestResult` carries a hash of the
engine source, computed at import and printed with every result.

This exists because **the engine was rewritten by another process mid-experiment, twice**,
uncommitted, both times changing `apply_turnover_budget`. Wave-2 agents found themselves
comparing numbers against other agents' reports with no way to tell which engine produced
them. One agent had to **discard an entire TRAIN table** on discovering it had been measured
on the pre-fix engine — it had shown Sharpe **+0.42** where the fixed engine gave **−0.08**.
The signal was bit-identical; only the engine differed.

> **Rule: if the `engine_sha` on a stored result does not match the working tree, the result
> is stale and must be re-run rather than quoted.** An unreproducible number is an opinion.

**2. Cost-model units must be asserted, not assumed.** The half-cost bug was not caught by
any plausibility check, because a book that pays half the real cost still produces a
perfectly plausible equity curve. It was caught by an agent that **proved the realised
ratio was exactly 0.500000** rather than approximately — which is what distinguishes a
unit-convention bug from a modelling choice. Any ratio between two paths that ought to be
equal should be asserted, not eyeballed.

### In the crypto catalog — 8 strategies and 1 shared indicator fixed

`src/cryptobot/strategies/catalog/` was outside the agents' write scope; the fixes below were
made afterwards by the orchestrator. These are **crypto** code and have no bearing on the
nsealgo result.

| File | Bug | Fix |
|------|-----|-----|
| **`indicators.py::hull()`** | **The two WMA terms are swapped**: `2*WMA(period) − WMA(half)` where it should be `2*WMA(half) − WMA(period)` | ✅ Corrected. **See the correction below — the original diagnosis was wrong.** |
| `adx_trend_strategy.py` | ATR computed then discarded — no trend strength is ever used; the signal is bar direction | ✅ Fixed |
| `donchian_channel` | Channel includes today's high, so a breakout can **never** fire | ✅ Fixed — fire rate **0.25% → 10.8%** |
| `correlation_gate.py` | No correlation statistic of any kind despite the name | ✅ Fixed — real correlation logic |
| `flag_pattern.py` | `period` is dead code — hardcoded 3-bar chain | ✅ Fixed |
| `gaussian_strategy.py` | `period` decorative — z-score always uses the 300-bar buffer | ✅ Fixed |
| `cointegration_strategy.py` | No pair, no spread, no hedge ratio — single-name z-score mean reversion | ✅ Fixed — now a real **OLS-hedge pairs** strategy |
| `gap_strategy.py` | Computes close-to-close return, not a gap; `threshold=0.0` default is a no-op (fires 49%) | ✅ Fixed |
| `atr_trailing_stop.py` | Contains no trailing stop: no peak, no trail, no stop | ✅ Fixed — now a **Chandelier stop** |
| Dead config | `period` inert in `cross_sectional`, `gap`, `cointegration` (read only by `warmup()`) | Noted |

#### ⚠️ CORRECTION — the Hull bug is a LAG defect, not an inverted signal

The first diagnosis recorded here was: *"`hull()` returns the negative of the intended
smoother, so every consumer's signal is **inverted**."*

**That framing was wrong, and the error was found by an agent that actually measured it
rather than reasoning from the algebra.** The swapped terms make the line **lag ~0.5× the
period instead of tracking sub-bar** — it correlates **+0.91 with the intended line**. It is
not a sign flip. A line that correlates +0.91 with the correct one produces a *slow* signal,
not an *opposite* one, and those two failures look completely different in a backtest.

The evidence that settled it: re-running the identical pipeline with the terms in textbook
order gives a **worse** TRAIN result, not a better one — which is what a lag defect looks
like and is not what a sign flip looks like.

**The lesson generalises past Hull:** "the sign is wrong" and "the line is late" are
different failures with different fixes, and algebraic reasoning alone will not tell you
which one you have. Measure the correlation against the intended line before naming the
defect.

### In the dataset — one earlier claim was wrong and is retracted

The first wave reported `high == open` on **6.68% of bars** and concluded that every
breakout-level strategy read a corrupted column. **Both the rate and the conclusion were
wrong.** A dedicated re-audit (`research/data_quality/FINDINGS.md`, 281,342 bars) found:

| Claim | Corrected finding |
|---|---|
| `high == open` on 6.68% | **10.06%** pooled (8.70% on live bars) |
| `high` is corrupt | **`high` is sound** — accurate to a median 0.15 rupees; the daily low is **never** above the true low (0.00%) |
| breakout strategies are impaired | **−0.08% of Donchian events (15 of 18,495).** Not impaired. **Do not exclude them.** |
| — | The **`open` column is corrupt**: wrong on **90.81%** of days, outside the true intraday range on **20.12%** |
| — | `close` is **clean**: 97.12% exact match against intraday aggregation |

**The `high == open` artifact is a downstream symptom of the phantom `open`, not a defect
in `high`.** The genuinely exposed strategy is `open_range_breakout`, which reads `open`
directly and was *not* on the original list. Full analysis in
[`reports/DATA_AUDIT.md`](DATA_AUDIT.md) §0.1.

---

## Methodology notes the agents forced

These affect how much the numbers above can be trusted:

- **pandas 3.0.5 changed `stack()`** — it no longer drops NaN. Any `.where(mask).stack()`
  followed by `len()` silently uses the unmasked count, deflating t-stats by up to √60×.
- **Slicing a panel before computing indicators destroys warmup.** `build_composite_score`
  has a 252-bar factor, so scoring a sliced window silently loses ~12 months of history.
  One agent measured this as **6.5pp of CAGR**.
- **Residual weights dilute sparse signals** (see the engine-bug table above — this one
  propagated all the way to the headline).
- **Concordance, not one word.** Several catalog strategies are the same signal family
  under different names: `momentum_factor` and `cross_sectional` are byte-identical apart
  from a default `threshold` (0.005 vs 0.015), and `momentum_factor` and
  `relative_strength` both selected ROC(126) > +8% and landed on identical numbers
  (−0.36% / −0.48). **"38 strategies" is closer to 34 distinct signals.**
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
3. **The most valuable output was the bugs.** The half-cost one alone moved this project's
   headline by **1.08pp of CAGR and 0.09 of Sharpe**, and it had been silently flattering
   every number reported before 2026-10-09.
4. **Adversarial probing of the harness, run against the engine while experiments were on
   top of it, is worth more than any single strategy trial in this report.** That is the
   actual lesson, and it is not about crypto.

## If someone continues

The untested ideas, in rough order of promise:

- **Index-level application.** `absolute_momentum`'s agent proposed this: the crypto
  thesis is expressible only at the index level in a delivery account, via
  `regime.exposure_series`. That is what `src/nsealgo` already does — and it is the one
  place a "regime switch" survived. `regime_switch`'s own agent confirms the finding from
  the other direction: the cash leg works, the timing does not.
- **Rank, don't gate.** Every failure above is a gate failing. A continuous
  cross-sectional score on the *whole* universe (e.g. normalised distance-to-HMA) can
  differentiate where a binary `close > MA` cannot.
- **Supertrend as a tie-breaker, not an eligibility mask.** `supertrend`'s agent measured
  that momentum still helps **+0.77pp** — the only evidence in that report pointing
  anywhere useful. Gate the existing composite on Supertrend only among already-good names,
  rather than using it as the mask. A 6th Supertrend variant would be noise-mining: the
  whole 4-point `(period, multiplier)` grid spans **0.10 Sharpe** on TRAIN.
- **The 3% of names with real information** (quality, payout) is unavailable from OHLCV
  alone. Getting fundamentals would change the question entirely.

**Nothing above has been tested. Do not treat it as a result.**