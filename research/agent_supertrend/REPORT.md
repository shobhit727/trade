# agent_supertrend — `SupertrendStrategy` on NSE NIFTY-50

**Status: IN PROGRESS — header + declared parameter budget written before any run.**

---

## 0. Pre-registration (written before anything was executed)

### 0.1 Assignment

| Field | Value |
|-------|-------|
| Strategy | `SupertrendStrategy` (`src/cryptobot/strategies/catalog/supertrend_strategy.py`) |
| Class / `name` | `SupertrendStrategy` / `"supertrend"` |
| Config | `SupertrendConfig(period=10, multiplier=3.0, quantity=Decimal("1"))` |
| Declared free parameters | `period` (ATR period), `multiplier` (band width). `quantity` is unused by `signal()`. |
| Crypto-specific? | **No.** Supertrend is a plain ATR-banded price-trend filter. It has direct meaning on NSE daily bars, so brief §9 ("no NSE meaning → stop") does **not** apply. Proceeding. |

### 0.2 ⚠️ BUG FOUND IN THE ASSIGNED STRATEGY — the shipped code is not Supertrend

The catalog file computes ATR and then **throws it away**:

```python
def signal(self, closes, highs, lows, volumes):
    b = atr(highs, lows, closes, self.config.period)   # computed...
    if b != b and len(closes) < self.config.period + 1:
        return 0
    return 1 if closes[-1] > closes[-2] else -1          # ...and never used
```

Two distinct defects, both of which matter:

1. **`b` (the ATR) is dead code.** The return value is the sign of the *one-day* return.
   `period` and `multiplier` therefore have **no effect whatsoever** on the shipped
   signal — every `SupertrendConfig` produces byte-identical output. A config knob that
   does nothing is a bug, not a hyper-parameter.
2. **The NaN guard is dead and wrong.** `if b != b` tests "ATR is NaN". But
   `cryptobot.strategies.indicators.atr` **already returns NaN** when
   `len(closes) < period + 1`, and `b` is a plain `float`, so on a *warm* bar
   `b != b` is `False` and the guard falls through to the one-day signal. Meanwhile on
   a *cold* bar `atr` returns NaN, `b != b` is `True`, but the `and` short-circuits on
   `len(closes) < period + 1` only when that is *also* true — so the guard is
   effectively `len(closes) < period + 1` in the wrong order and never fires when it
   should. Dead, either way.
3. Additionally, `closes[-1] > closes[-2]` is **1-bar momentum**, not a trend filter.
   With `maxlen=300` in `SignalStrategy.__init__` this is the well-known 1-day
   reversal/continuation noise generator, and on a daily NSE bar it flips sign roughly
   50% of bars.

**Consequence for this assignment.** The brief says "make it work". Two readings:

* **Literal reading** — the code is the contract; port `sign(close[t]-close[t-1])`.
* **Intent reading** — the class is named Supertrend and carries a Supertrend config;
  the file has a bug; port a *correct* Supertrend and report the bug.

I do **both**, because the literal reading is itself informative (it tells us whether
this catalog slot is a genuine edge or just 1-day noise), and the intent reading is the
one that could actually make money. The literal port is reported as **V0**, the
zero-parameter "as-shipped" baseline, and the real Supertrend variants are V1–V4.

### 0.3 Data (declared before use)

| Item | Value |
|------|-------|
| Source | `data/nse/<symbol>_1d.csv` via `nsealgo.data.loader.load_universe("data/nse")` (mandatory first step, brief §2) |
| Timeframe | `1d` **only** — intraday is banned (brief §2; 1m/30m absent, 5m/15m ≈ 7 weeks) |
| Panel | cleaned **close**; high/low re-loaded through the same `load_symbol` cleaning path for ATR |
| Symbol count | filled in after `load_universe` runs (expected ≈ 48) |
| Span | filled in after load (expected 2008-01-01 → 2026-10-01) |
| Survivorship bias | **PRESENT** — today's NIFTY-50 backfilled. Disclosed on every result. |
| Forward-fill | interior gaps only, forward-filled **from the past**. Leading NaNs (pre-listing) left NaN — no price is fabricated. |

### 0.4 Split (brief §4, non-negotiable)

| Set | Window | Purpose |
|-----|--------|---------|
| **TRAIN** | 2016-01-01 → 2023-12-31 | everything tuned on |
| **TEST** | 2024-01-01 → 2026-10-01 | touched **once**, at the end, on the frozen winner |

I will not look at TEST while iterating. If I do, it goes in this report as a failed run.

### 0.5 PARAMETER BUDGET — 5 declared variants (the maximum allowed)

Written down **before** any run, per brief §4. Exceeding 5 invalidates the run.

| # | Name | Definition |
|---|------|------------|
| **V0** | `as_shipped` | The literal catalog signal: `+1 if close[t] > close[t-1] else -1`. Zero parameters. **Bug baseline / control**, not a tuning attempt. |
| **V1** | `st_p10_m3.0` | Real Supertrend, `period=10, multiplier=3.0` — the **catalog defaults**, so it is the faithful intent of the shipped config. |
| **V2** | `st_p14_m3.0` | `period=14, multiplier=3.0` — industry-standard ATR period, same band width. |
| **V3** | `st_p10_m2.0` | `period=10, multiplier=2.0` — tighter band ⇒ more, shorter trend signals. |
| **V4** | `st_p20_m3.0` | `period=20, multiplier=3.0` — slower ATR ⇒ whipsaw-resistant, laggier. |

Rationale for the grid: Supertrend has exactly two free parameters, so a 5-budget is
spent on a 4-point design around the catalog default (V1) — one point moves `period`
down (V2 → industry default), one point tightens the band (V3), one point slows the ATR
(V4) — plus the literal baseline (V0) which costs no parameters at all.

**Everything else is frozen across all variants**: signal panel → cross-sectional
percentile rank of trailing 126-day momentum restricted to names flagged `+1` → fed
unchanged to `nsealgo.backtest.engine.run_backtest` with `PortfolioConfig(n_positions=22)`
defaults and monthly rebalance. `momentum_days=126` is a construction choice, not a
tuned parameter, and is **not** varied.

### 0.6 Cost convention (brief §3)

Every `run_backtest` number below is **net of `all_in_round_trip_bps(100_000)` = 21.92
bps**, which is what the engine charges. I do not report the 11.92 bps statutory-only
figure anywhere, because I do not call `CostModel.fill_price` directly. Gross-of-cost
numbers are reported separately and *labelled gross* purely to quantify cost drag.

### 0.7 Sanity checks I will run before reporting (brief §6)

1. Plausibility — CAGR under ~50% for an unlevered long-only NIFTY-50 book.
2. Weight count — avg names held should be ≈ 22, not ≈ 48.
3. Signal liveness — fraction of bars flagged `+1`; flag if < 5%.
4. Cost drag — reported; gross-positive / net-negative = unviable, and that is the finding.
5. Negative control — random signal with the **same % of bars long**, 30 seeds.

### 0.8 Honest framing

A Supertrend filter on NIFTY-50 daily bars is a plausible trend-follower, and this repo's
own factor evidence says trend-following is the one thing that survives multiple-testing
correction in Indian equities. So this is a *fair* candidate, not a straw man. It can
still lose, and if it does I will say so in one sentence and stop overselling.

---

## 1. Results

*(appended as they are produced)*
---

## 2. Stage 0 — data + signal verification

### 2.1 Data audit (`load_universe("data/nse")`, brief §2 mandatory first step)

```
rows in             :   274,541
rows out            :   208,226
dropped pre-2008    :    66,312
dropped artifact    :         0
dropped non-positive:         0
dropped extreme     :         3
excluded symbols    : ['adanient', 'jiofin']
n_symbols = 48 | 2008-01-01 -> 2026-10-01 | 4625 bars
mean cross-sectional coverage from 2016: 97.33%
```

High/low panels for ATR were re-loaded through the same `load_symbol` cleaning path and
reindexed onto the cleaned close index, so ATR is built on identical cleaning rules.
Cached to `_ohlc_supertrend.pkl`.

### 2.2 Signal verification (`verify_signal.py` → `verify_signal.json`)

**VERIFY PASS.** Three independent checks, because a vectorised band recursion is exactly
the kind of thing that quietly develops a look-ahead:

| Check | Result |
|-------|--------|
| ATR parity vs `cryptobot.strategies.indicators.atr` (4 symbols) | **exact**, `abs diff < 1e-9` |
| Independent stateful re-implementation (6 symbols × 4 variants) | **0 differing bars**, max abs diff 0.000 |
| **Prefix invariance** (truncate input → earlier values must be unchanged), 5 cut points | **0 failures** |

Prefix invariance is the real no-look-ahead test: if the signal on bars 1..k were a
function of anything past k, truncating the series to k bars would change those values.
It did not, for any of the four Supertrend variants or V0.

> **Checker bug found and fixed (mine, not the repo's):** my first prefix-invariance
> comparison used `(a.where(both) != b.where(both)).fillna(False)`. Because `NaN != NaN`
> is `True`, that counted **every absent cell** as a disagreement and reported ~9,000
> "mismatches". The mask has to be applied to the raw numpy values, not to a NaN-filled
> frame. Recorded because it is the kind of error that would have made a correct signal
> look like a lookahead bug — and, in the other direction, could mask a real one.

### 2.3 Signal liveness and chop (full panel 2008–2026, NaN excluded)

| Variant | bars flagged `+1` | sign flips/yr (48 symbols) | flips per symbol per yr |
|---------|------------------:|---------------------------:|------------------------:|
| `as_shipped` (V0) | 47.12% | 5569 | **116** |
| `st_p10_m3.0` (V1) | 46.70% | 279 | 5.8 |
| `st_p14_m3.0` (V2) | 46.88% | — | — |
| `st_p10_m2.0` (V3) | 45.63% | — | — |
| `st_p20_m3.0` (V4) | 46.65% | — | — |

Two things worth stating plainly before any backtest:

1. **Liveness passes comfortably** (brief §6.3 — the >5% floor). All variants are long
   roughly 46% of bars, nowhere near the "effectively always-flat" failure mode.
2. **The chop table is the clearest evidence for the §0.2 bug.** The shipped signal
   flips sign **116 times per symbol per year** — i.e. essentially every other session.
   A genuine Supertrend at 3×ATR flips ~5.8 times per symbol per year, about **20× less
   often**. V0 is not a slow trend filter; it is daily coin-flip noise wearing a Supertrend
   config. Whatever V0's backtest prints, it is measuring 1-day return sign, not Supertrend.

---

## 3. Stage 1 — TRAIN sweep (2016-01-01 → 2023-12-31), all net of 21.92 bps

`stage1_train.py` → `stage1_train.json`. Selection rule fixed in advance: **max TRAIN
Sharpe**, tie-break TRAIN Calmar. This script never reads a TEST-window price.

| # | Variant | CAGR | Sharpe | MaxDD | Calmar | Turn x/y | Drag %/y | Avg names | Gross CAGR | Live % |
|---|---------|-----:|-------:|------:|-------:|----------:|---------:|----------:|-----------:|-------:|
| **V4** | `st_p20_m3.0` | **14.85%** | **0.735** | −17.27% | 0.86 | 3.78 | 3.03 | 18.3 | 16.77% | 48.8% |
| V3 | `st_p10_m2.0` | 13.86% | 0.685 | −14.24% | 0.97 | 4.00 | 3.08 | 18.4 | 15.87% | 46.9% |
| V2 | `st_p14_m3.0` | 13.75% | 0.645 | −20.25% | 0.68 | 3.77 | 2.87 | 18.4 | 15.65% | 48.7% |
| V1 | `st_p10_m3.0` | 13.35% | 0.635 | −14.55% | 0.92 | 3.79 | 2.87 | 18.2 | 15.25% | 48.3% |
| V0 | `as_shipped` | 10.98% | 0.447 | −20.58% | 0.53 | 4.03 | 2.67 | 19.0 | 12.96% | 49.2% |
| — | **buy & hold** (equal-wt) | **22.20%** | **0.91** | **−37.97%** | 0.58 | 2.00 | 0.03 | 46.3 | 22.24% | — |

**Selected on TRAIN: V4 `st_p20_m3.0`** (Sharpe 0.735). Frozen.

### 3.1 Two TRAIN findings worth recording before any TEST data exists

**(a) The bug in the shipped file is not cosmetic — it costs ~50% of the Sharpe.**
All four *correct* Supertrend variants beat the *as-shipped* V0 by a wide and
monotone-in-the-right-direction margin: Sharpe 0.635–0.735 vs **0.447**. The best real
Supertrend is +0.29 Sharpe over the code the repo currently ships under the name
"supertrend". Given the shipped code discards its own ATR (§0.2), this is exactly what
you would expect, and it is TRAIN-only evidence — it is not by itself a validated claim,
but it is a strong reason to treat `supertrend_strategy.py` as a real defect.

**(b) The ranking among V1–V4 is shallow and mostly monotone in "slower is better".**
Sharpe rises as `period` lengthens and the band widens (V1 0.635 → V4 0.735). That is
the classic trend-filter signature: on daily Indian equities the slower the filter, the
more of the return you keep and the less you whipsaw. It also means **the parameter
choice is not doing very much** — the whole 4-point grid spans 0.10 Sharpe. That is a
reason to be *more* sceptical of the TEST number, not less: if the family is nearly
indifferent, then "best of 5 on TRAIN" is mostly picking noise.

**(c) On TRAIN, every variant trails buy-and-hold on return but beats it on drawdown.**
22.20% vs 14.85% CAGR; −17.27% vs −37.97% MaxDD. A 22-name concentrated book with a
10% cash buffer and a 25% sector cap is structurally lower-beta than a 46-name
equal-weight book. That is the trade the strategy makes — and it is the trade the TEST
window will have to be judged on, not on raw CAGR alone.

### 3.2 Sanity checks, selected variant (brief §6)

| Check | Result | Verdict |
|-------|--------|---------|
| §6.1 plausibility | CAGR 14.85% | ✅ far below the 40–50% ceiling; no lookahead, no compounding bug |
| §6.2 weight count | avg **18.3** names, max 22, avg invested 74.2% | ✅ ≈22, not 48 — no residual accretion |
| §6.3 liveness | **48.8%** of bars long | ✅ far above the 5% floor; not an always-flat strategy |
| §6.4 cost drag | gross 16.77% → net **14.85%** (−3.03%/y) | ✅ gross-positive and net-positive; viable, not cost-killed |
| Position caps | max single weight 0.1080 (cap 0.12) | ✅ `PortfolioConfig` respected, not bypassed |
| Cost basis | 21.92 bps all-in charged by the engine | ✅ brief §3 convention |
| No look-ahead | prefix-invariance 0 failures (§2.2) | ✅ |

---

## 4. TEST PRE-DECLARATION — written before TEST is touched

I am about to evaluate the frozen **V4** on TEST exactly once. Committing in advance to
exactly what that one evaluation will produce, so that nothing can be re-selected after
the fact:

1. **The single TEST verdict is V4's.** Whatever it prints is the result. If it loses, I
   report that it loses. I will not switch to V3, V2 or V1 on the basis of TEST.
2. **I will additionally print the other four variants on TEST** as a declared
   *family-robustness* check. This is a pre-declared secondary observation, **not** a
   selection step. V4 stays the verdict even if another variant does better on TEST,
   and even if all four do better. A parameter family that is insensitive across its
   grid is evidence about the family; it is not licence to re-pick.
3. **Benchmarks on the identical TEST window:** equal-weight buy & hold (brief §4.5) and
   `nsealgo` `build_composite_score` on the same panel.
4. **Negative control:** random signal with the same number of names eligible on every
   rebalance as V4, 30 seeds, identical cost/turnover pipeline.
5. **No parameter, no window, no score form, no book construction changes after this
   point.** Any bug I find in my own harness will be disclosed as a protocol failure
   rather than silently patched and re-run.

*No TEST price has been read in this session at the time of writing.*

---

## 5. Stage 2 — THE TEST RESULT (single evaluation of frozen V4)

`stage2_test.py` → `stage2_test.json`. Selection re-read from `stage1_train.json` and
asserted to be V4 before any TEST price was used. No re-selection afterwards.

### 5.1 The verdict — `st_p20_m3.0`, 2024-01-01 → 2026-10-01, net of 21.92 bps

| Metric | **Supertrend V4 (TEST)** | Buy & hold, same window | nsealgo composite, same window |
|---|---:|---:|---:|
| **CAGR** | **−1.31%** | **+8.18%** | +6.04% |
| **Sharpe** | **−0.61** | +0.18 | +0.03 |
| **MaxDD** | **−23.03%** | −15.90% | −15.22% |
| **Calmar** | **−0.06** | +0.51 | +0.40 |
| Volatility (ann) | 18.2% | 15.5% | 17.0% |
| Total return | −3.66% | +24.62% | +18.66% |
| Turnover /yr | 3.89× | 2.00× (entry+exit) | 2.08× |
| **Cost drag** | **1.91%/yr** | 0.08%/yr | 1.10%/yr |
| Gross CAGR (pre-cost) | **+0.39%** | +8.26% | +7.01% |
| Avg names held | 18.4 | 48.0 | 21.3 |
| Rebalances | 33 | 1 | 33 |
| Bars long | 45.9% | 100% | — |

### 5.2 Head to head (brief §7.4)

| Axis | V4 vs buy & hold | Verdict |
|------|------------------|---------|
| **Return** | −9.49 pp/yr (−1.31% vs +8.18%) | ❌ **worse** |
| **Drawdown** | −7.13 pp (−23.03% vs −15.90%) | ❌ **worse** — *deeper*, not shallower |
| Sharpe | −0.80 | ❌ worse |
| Calmar | −0.57 | ❌ worse |
| vs nsealgo composite | −7.35 pp CAGR, −0.64 Sharpe, −7.81 pp MaxDD | ❌ worse on all three |

It loses on **both** axes. It is not a lower-beta story that underperformed on return
while protecting capital — it took *more* drawdown than the index **and** earned less.
That is the worst version of the trade, and it is unambiguous.

### 5.3 Family robustness on TEST (pre-declared observation, **not** re-selection)

| # | Variant | TRAIN Sharpe | **TEST CAGR** | TEST Sharpe | TEST MaxDD | Gross CAGR |
|---|---------|-------------:|--------------:|------------:|-----------:|-----------:|
| V0 | `as_shipped` (the bug) | 0.447 | **+3.51%** | −0.24 | −12.37% | +5.38% |
| V1 | `st_p10_m3.0` | 0.635 | −1.44% | −0.66 | −21.22% | +0.30% |
| V2 | `st_p14_m3.0` | 0.645 | −0.44% | −0.54 | −20.34% | +1.29% |
| V3 | `st_p10_m2.0` | 0.685 | −1.99% | −0.74 | −22.46% | −0.24% |
| **V4** | **`st_p20_m3.0`** | **0.735** | **−1.31%** | **−0.61** | **−23.03%** | **+0.39%** |

**Every** correct Supertrend variant loses out-of-sample, in a narrow −0.44% to −1.99%
band. The verdict stays V4.

### 5.4 Negative control — does it beat a coin flip? (brief §6.5)

Random signal, same eligible-name count per rebalance as V4 (22.0), identical weight
builder, turnover budget and costs, 30 seeds:

| | V4 | Random (30 seeds) |
|---|---:|---:|
| CAGR | **−1.31%** | mean +1.38%, sd 1.52%, p5 −1.74%, p95 +3.21% |
| Sharpe | **−0.61** | mean −0.59, sd 0.20 |
| MaxDD | −23.03% | mean −12.97% |
| Avg names | 18.4 | 18.4 (matched) |
| Cost drag | 1.91%/y | 2.00%/y (matched) |

- V4 beats the random control on **CAGR in only 10% of seeds** (≈ 10th percentile).
- V4 beats it on Sharpe in **40% of seeds**.
- V4's MaxDD is **10 pp deeper** than a random book's.

**A random book of 22 randomly-chosen NIFTY-50 names was a better strategy than
Supertrend on this TEST window.** That is the minimum bar from brief §6.5, and V4 is not
over it — it is under it.

### 5.5 Calendar years (TEST)

| Year | Strategy | Equal-weight | nsealgo composite | Alpha vs EW |
|------|---------:|-------------:|------------------:|------------:|
| 2024 | +16.04% | +19.87% | +21.91% | −3.83% |
| 2025 | +1.17% | +13.35% | +6.61% | −12.18% |
| 2026 (to 01 Oct) | **−17.92%** | −8.26% | −9.31% | **−9.66%** |

Positive in 1 of 3 calendar years. (GOAL.md Gate 3 asks for positive in 60% of years —
1/3 fails that too.) 2026 is where it breaks: it lost **more than twice** what the market
lost, in a year the market fell only 8%.

### 5.6 §6.4 cost drag — reported, and it is *not* the whole story

Gross CAGR **+0.39%** → net **−1.31%**. Costs (1.91%/yr) turn a flat result into a
losing one, so costs are load-bearing for the final sign. But gross is not positive in
any useful sense either: **+0.39%/yr before costs is nothing**, and three of the five
variants have gross CAGR between −0.24% and +1.29%. The signal does not carry enough
gross information to be worth trading; the cost stack merely finishes the job. Brief §6.4
("gross positive but net negative ⇒ unviable") applies — and it is worse than that,
because gross is barely positive at all.

---

## 6. Stage 3 — why it failed (post-hoc mechanism; measurement only)

`stage3_diagnostic.py`, `stage3b_robustness.py`. No parameter variant was added, no book
construction changed, no re-ranking of V4 against anything. These are descriptions of a
result that was already fixed.

### 6.1 The signal carries no positive directional information — it is slightly *negative*

Mean forward return of names flagged `+1` minus names flagged `−1`, by horizon:

| Window | Horizon | `+1` mean fwd | `−1` mean fwd | **Spread (+1 − −1)** |
|--------|--------:|--------------:|--------------:|--------------------:|
| TRAIN | 21d | +1.87% | +2.01% | **−0.15 pp** |
| TRAIN | 63d | +5.75% | +6.32% | **−0.57 pp** |
| TRAIN | 126d | +12.05% | +12.61% | **−0.56 pp** |
| TEST | 21d | +0.53% | +1.14% | **−0.60 pp** |
| TEST | 63d | +1.81% | +3.28% | **−1.47 pp** |
| TEST | 126d | +4.08% | +5.20% | **−1.12 pp** |

Universe baseline for reference: TRAIN 63d +5.72%, TEST 63d +2.61%.

**The names the strategy refuses to buy do better than the names it buys, at every
horizon, on both windows.** That is the whole failure. The filter is not merely failing
to add value — as constructed on this universe it is subtracting it.

### 6.2 Is that effect real, or an artifact of a few big names? Three stresses.

**(a) By calendar year (63d spread).** Negative in **6 of 8** TRAIN years and **2 of 3**
TEST years. But the noise control `as_shipped` is also negative in 6/8 and 2/3, so *the
sign count alone is not evidence* — I am not claiming it is. What differs is magnitude:
Supertrend's mean TRAIN spread is **−1.09 pp/yr** vs the control's **−0.24 pp/yr**.

**(b) Outlier-robust statistics (63d spread).** If the negative mean is a handful of
huge names, the median should be ≈ 0:

| Window | Statistic | **Supertrend** | `as_shipped` control |
|--------|-----------|---------------:|---------------------:|
| TRAIN | mean | −0.570 pp | −0.091 pp |
| TRAIN | winsorised (10/90) | **−0.499 pp** | −0.115 pp |
| TRAIN | **median** | **−0.062 pp** | −0.091 pp |
| TEST | mean | −1.469 pp | −0.142 pp |
| TEST | winsorised (10/90) | **−1.541 pp** | −0.222 pp |
| TEST | **median** | **−1.907 pp** | −0.141 pp |

This is the most informative table in the report, and it sharpens the story in two ways:

- The negative mean **survives winsorising** — it is not a pure tail artifact.
- But on **TRAIN the median spread is −0.062 pp, i.e. indistinguishable from the noise
  control (−0.091 pp)**. So on TRAIN the effect lives entirely in the upper tail: the
  uptrend filter captured the *typical* name about as well as anything, while
  systematically missing the big winners. On **TEST the median is −1.907 pp** — there the
  effect is broad, not tail-driven, and strictly worse than TRAIN.

**(c) Randomisation null (200 within-bar shuffles).** Shuffling the signal within each
bar preserves every bar's long-run rate and destroys the time-series information:

| Window | Observed spread | Null mean ± sd | One-sided p |
|--------|----------------:|---------------:|------------:|
| TRAIN | −0.570 pp | +0.097 ± 0.089 pp | **< 0.005** |
| TEST | −1.469 pp | −0.021 ± 0.125 pp | **< 0.005** |

Far outside the null in both windows. The effect is systematic, not sampling noise.

> **My own bug, recorded:** my first attempt at an outlier-robust check ("rank
> statistic") compared each observation's forward return with the *next* observation's in
> the same symbol. That tests return autocorrelation, **not** the `+1` vs `−1` contrast —
> it returned 50.1% for the strategy and 50.1% for the noise control, and said nothing
> either way. Replaced with median + winsorised-mean comparisons. Two of my three
> robustness checks in this project have been wrong on first write; both are caught only
> by having a known-null control (`as_shipped`) to calibrate against.

### 6.3 The momentum rank is *not* the problem — it helps

| Construction (TEST) | CAGR | Sharpe | MaxDD |
|---|---:|---:|---:|
| flag + 126d momentum rank (**as designed**) | **−1.31%** | −0.61 | −23.03% |
| flag only, no momentum rank | −2.08% | −0.76 | −21.10% |

Removing the ranking makes it **worse** (−2.08% vs −1.31%). So the score construction
added value; the signal underneath it did not. Do not go looking for a better ranking.

### 6.4 The book is not actually "slow", which is why costs bite

Supertrend is a slow *signal* (5.8 flips per symbol per year) but the **book is not
slow**:

- Avg eligible names per TEST rebalance: **22.4**, vs `n_positions = 22`.
- Mean overlap between consecutive months: **10.6 of 18.4 names = 57%** (min 0, max 18).
- Turnover 3.89×/yr — the 0.35/monthly budget binding on essentially every rebalance.
- Cost drag 1.91%/yr.

When eligibility ≈ position count, the momentum rank only **re-orders** the book; it
cannot filter further. Membership churns ~43% per month as names cross the band. A filter
that flips 5.8×/year still produces a 43%-monthly book churn because ~22 names are
sitting right at the band boundary. **The signal has no information to pay 1.91%/yr of
costs with** — which is exactly why gross CAGR is +0.39% and net is −1.31%.

### 6.5 Where the loss came from (TEST, gross of costs)

| Year | Strategy | Equal-weight | Alpha | Invested | Names |
|------|---------:|-------------:|------:|---------:|------:|
| 2024 | +17.83% | +20.13% | −2.31 pp | 75.6% | 18.4 |
| 2025 | +2.95% | +13.35% | **−10.40 pp** | 73.9% | 18.6 |
| 2026 | −16.66% | −8.27% | **−8.40 pp** | 67.0% | 18.3 |

Negative alpha in all three years. 2026 is the killer: it lost **twice** what the market
lost. Note the falling exposure (75.6% → 73.9% → 67.0%): the filter was switching names
off into the drawdown, which is the classic way a trend filter amplifies rather than
cushions a slow bleed when the underlying signal has no edge.

---

## 7. Findings

### 7.1 Bug report — `src/cryptobot/strategies/catalog/supertrend_strategy.py` is not Supertrend

**Severity: HIGH. This is a real defect in shipped source, not a research artifact.**

```python
def signal(self, closes, highs, lows, volumes):
    b = atr(highs, lows, closes, self.config.period)   # computed
    if b != b and len(closes) < self.config.period + 1:
        return 0
    return 1 if closes[-1] > closes[-2] else -1          # never used
```

1. **The ATR is dead code.** `period` and `multiplier` have **zero** effect on the shipped
   signal — every `SupertrendConfig` produces identical output. A config knob that does
   nothing is a bug.
2. **The NaN guard can never fire.** `b != b` is true only on a cold bar, but
   `cryptobot...atr()` already returns NaN there *and* the `and` then requires
   `len(closes) < period + 1` — the two conditions coincide, so it degenerates to a
   length check that duplicates what `atr()` already enforces. On a warm bar `b != b` is
   `False` and the guard falls straight through to the 1-day signal.
3. **The emitted signal is 1-day return sign, not a trend filter.** Measured on NSE daily
   bars it flips **116 times per symbol per year** versus **5.8** for a genuine
   3×ATR Supertrend — ~20× more often. It is daily noise wearing a Supertrend config.

**Measured impact (TRAIN, net of 21.92 bps):** the shipped signal scores Sharpe **0.447**;
the four *correct* Supertrend variants score **0.635 – 0.735**. Fixing the bug is worth
**≈ +0.29 TRAIN Sharpe**. The fix is ~10 lines: carry `final_upper`/`final_lower` and an
up-trend flag across bars and use the band, instead of the one-day return sign. A
verified port is in `research/agent_supertrend/common.py::supertrend_signal` (causality
proven by prefix invariance, cross-checked against an independent stateful
implementation, ATR parity exact against `cryptobot.strategies.indicators.atr`).

**I did not modify the file** — the brief forbids touching `src/cryptobot/**`. This
section is the bug report.

### 7.2 Two harness bugs of my own (recorded per brief §8.3)

- **NaN-comparison trap** in the prefix-invariance check: `(a.where(both) != b.where(both))`
  counts every absent cell as a disagreement, because `NaN != NaN` is `True`. It
  reported ~9,000 phantom mismatches on a signal that is in fact lookahead-free. Mask
  numpy values, not NaN-filled frames.
- **Misdesigned "rank statistic"** in the robustness check — it compared consecutive
  observations instead of `+1` vs `−1`, testing autocorrelation rather than the signal,
  and returned ~50% for both the strategy and its null control (§6.2).

Both were caught only because a **known-null control** (`as_shipped`, a pure 1-day sign)
was run alongside. That control is worth keeping in any future harness in this project —
it is the cheapest possible calibration of a metric.

### 7.3 Harness observations (nothing changed, just noted)

- `nsealgo` infrastructure behaved correctly and was not bypassed: 21.92 bps charged,
  `PortfolioConfig` caps respected (max single weight 0.108 ≤ 0.12), avg names 18.4
  (not 48), no residual accretion, causality proven independently of the engine.
- **`nsealgo.backtest.engine` is a well-built module** and its documented cost
  convention (`all_in_round_trip_bps`, ×2 total-turnover) was verified arithmetically:
  12 rebalances × 0.35 budget × 2 × 21.92 bps = 1.84%/y ≈ the 1.91%/y reported.

---

## 8. Verdict

**Plain verdict: No — a Supertrend filter does not make money on NSE NIFTY-50.
Out-of-sample it lost 1.31%/yr (−0.61 Sharpe), against buy-and-hold's +8.18%/yr, and it
lost 9.49 pp/yr on return *and* 7.13 pp on drawdown. It also lost to a random book of 22
randomly-chosen names (which averaged +1.38%/yr), which is below the minimum bar.**

The full negative result:

| Brief §7 question | Answer |
|---|---|
| Strategy / signal / variants | §0.1, §0.5 — Supertrend ATR trend filter; V0 as-shipped bug + 4 real `(period, multiplier)` variants, 5 of 5 budget used |
| TEST metrics | §5.1 — CAGR −1.31%, Sharpe −0.61, MaxDD −23.03%, Calmar −0.06, turnover 3.89×/y, drag 1.91%/y, 18.4 names |
| Buy & hold, same window | §5.1 — CAGR +8.18%, Sharpe 0.18, MaxDD −15.90%, Calmar 0.51 |
| vs buy & hold | §5.2 — **worse on return (−9.49 pp) and worse on drawdown (−7.13 pp)** |
| Random-signal control | §5.4 — V4 at the ~10th percentile on CAGR; a random book beat it |
| vs nsealgo composite | §5.2 — composite +6.04% CAGR / Sharpe 0.03 / MaxDD −15.22%; V4 worse on all three |
| **Does it make money on NSE? (one sentence)** | **No.** |
| Most likely reason | §6.1–6.2 — the flag carries **no positive directional information** on this universe; names it rejects have *higher* forward returns at 21/63/126d on both windows (spread −0.57 pp TRAIN, −1.47 pp TEST at 63d, surviving winsorising and far outside a randomisation null). It then pays 1.91%/yr of costs to churn a book 43% per month in pursuit of that non-signal. |
| **One thing I would try next** | Do **not** tune `(period, multiplier)` further — the family is flat on TRAIN (0.10 Sharpe across the whole grid) and uniformly negative on TEST, so a 6th variant would be noise-mining and would burn the budget. The one untested idea with a real mechanism behind it is **removing the trend filter's exclusivity**: gate the existing `nsealgo` composite (or plain 6-month momentum) on Supertrend only as a *tie-breaker among already-good names* rather than as the eligibility mask, so a name is excluded only if it is both out-of-trend **and** in the bottom half of momentum. §6.3 shows momentum already helps (+0.77 pp), which is the only evidence in this report that points anywhere useful — that is the only thread worth pulling. |

### 8.1 Protocol compliance

| Rule (brief §4/§9) | Status |
|---|---|
| Parameter budget declared before running | ✅ §0.5, written before any execution |
| Variants tested | ✅ **5 of 5** — no more |
| Selected on TRAIN only | ✅ `stage1_train.py` never reads a TEST price; V4 frozen by an assertion in `stage2_test.py` |
| TEST evaluated once | ✅ once, on V4; other variants printed as a **pre-declared** family-robustness observation with no re-selection (§4, committed before TEST was read) |
| Report labelled TRAIN / TEST everywhere | ✅ |
| No lookahead | ✅ proven two ways — prefix invariance (0 failures) and the engine's own one-bar `held.shift(1)` lag |
| Forward-fill only from the past | ✅ no forward-fill used at all; score built from full history then sliced |
| Full Indian cost stack, 21.92 bps convention | ✅ via `run_backtest`; no gross number presented as net |
| `PortfolioConfig` respected, not bypassed | ✅ max single weight 0.108 ≤ 0.12; 18.4 names |
| No `src/nsealgo/**`, `src/cryptobot/**` or test file modified | ✅ only `research/agent_supertrend/**` created |
| Linted | ✅ `.venv/bin/ruff check` clean on all four scripts |
| Not committed | ✅ nothing committed, nothing pushed |
| `GOAL.md` / `reports/` untouched | ✅ |

### 8.2 Files

| File | Contents |
|---|---|
| `REPORT.md` | this document |
| `common.py` | data loading, both signal ports, score, run/summarise, benchmarks, random control |
| `verify_signal.py` / `.json` | ATR parity, independent cross-check, **prefix-invariance no-look-ahead test** |
| `stage1_train.py` / `.json` | TRAIN sweep over the 5 declared variants + selection |
| `stage2_test.py` / `.json` | the single TEST evaluation, benchmarks, family robustness, random control |
| `stage3_diagnostic.py` / `.json` | mechanism: flag information content, rank contribution, churn |
| `stage3b_robustness.py` / `.json` | is the anti-predictive spread real? by-year, outlier-robust, randomisation null |
| `_ohlc_supertrend.pkl` | cached close/high/low panels |

**Survivorship bias is present throughout** (today's NIFTY-50 backfilled) and is disclosed
on every table. It does not obviously explain this result — the same bias applies to
buy-and-hold, to the composite, and to the random control, all of which beat the strategy.
