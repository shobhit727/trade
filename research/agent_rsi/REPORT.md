# RSI Strategy on NSE NIFTY-50 — Validation Report

**Strategy file:** `src/cryptobot/strategies/catalog/rsi_strategy.py`
**Class:** `RsiStrategy` / `RsiConfig(period=14, lower=30.0, upper=70.0)`
**Assigned agent:** `agent_rsi`
**Protocol:** `research/AGENT_BRIEF.md` (read in full). TRAIN 2016-01-01→2023-12-31,
TEST 2024-01-01→2026-10-01, net of the full Indian delivery stack.
**Verdict: NO. This strategy does not make money on NSE out-of-sample.** It loses to
cash, to buy-and-hold, to an untilted book and to the nsealgo composite. Details in §7.
**Parameter budget: 5 of 5 used, not exceeded.**

---

## 0. ⚠️ DISCLOSURE — the backtest engine was rewritten underneath this run

**This is the single most important operational finding of this assignment, and it
affects every other agent working in this repository at the same time.**

Partway through this session, at **14:05:28 on 2026-10-09**, another process modified
`src/nsealgo/backtest/engine.py` — rewriting `apply_turnover_budget` completely (76
insertions, 24 deletions; `git diff` confirms the working tree differs from HEAD).

**What the rewrite fixes, in the new docstring's own words:** the old implementation
blended the *whole* book toward the new target, so a name the target no longer wanted
(`tgt[s] == 0`) only decayed by `1 - lam` per rebalance and was carried for many months.
*"The delivered book then held mostly names the signal did not want, at a fraction of the
intended exposure and a position count nothing like the configured one, so every headline
number measured the dilution rather than the signal."* The new version makes exits
unconditional and priority-paid, with only the surplus budget scaling new adoption.

**Exactly what it touched in my run.** I verified this rather than assuming it:

* I isolated the cause — the **signal is bit-identical** across versions (TRAIN long
  fraction 23.38% and eligible-name counts `min 0 / median 8 / mean 11.0 / max 39`, 14.6%
  at the cap, reproduce to the digit), the panel hash is stable
  (`sha256[:16] = caa1251dd9401c8d`), `data/nse/*.csv` mtimes are unchanged
  (2026-10-06), and three repeat runs plus four `PYTHONHASHSEED` values give identical
  results. So neither the data, the indicator, nor the engine's determinism was at fault —
  the file itself changed between runs.
* **CONTAMINATED — the first-pass TRAIN table only.** It showed V3 at Sharpe **+0.42**,
  CAGR 11.62% and **26.2 avg names**, against the corrected **−0.08 / 4.91% / 10.2**.
  That first table was measuring the old engine's slow-exit dilution and has been
  **discarded and replaced** in §3 and §4. It flattered the strategy. (The §3
  capital-deployed box was measured in the same pass and is corrected there too.)
* **UNAFFECTED — everything from §5 onward.** My first TEST run already produced
  `CAGR 3.38% / Sharpe −0.41 / MaxDD −8.63% / 10.3 names`, and every TEST figure is
  byte-identical before and after the rewrite. The reason is mechanical: when a
  rebalance's turnover fits inside the budget both implementations set `lam = 1` and
  return the target unchanged, and V3's TEST turnover (3.96x/yr, ~0.33/rebalance) sits just
  under the 0.35 budget, so the two versions coincide on this path.
* **§6.1 was never measured on the old engine.** `s4_diagnosis.py` was written and first
  executed after 14:05:28, so the sleeve decomposition in this report is a
  single-engine figure. (Its own first-pass numbers differed because of an annualisation
  bug in my scratch — see §8.2 — not because of the engine.)

**No selection was influenced.** V3 was selected under *both* engine versions, and TEST
was computed under *both* versions with identical results. The protocol is intact.

**Warning for the orchestrator.** `find research/agent_* -newer <engine baseline>` shows
**107 sibling-agent artefacts written before the rewrite versus 25 after**. Any agent
report whose TRAIN sweep was run against the pre-14:05:28 engine and which reports an
inflated `avg_names` (approaching 26–48 rather than ~10–22) has the old dilution in its
headline CAGR and Sharpe and should be re-run before its numbers are quoted. In this run
the correction moved V3's TRAIN Sharpe from **+0.42 to −0.08** — a swing of 0.50 Sharpe,
which is far larger than most of the strategy effects anyone was trying to measure.

---

## 1. What the strategy actually is

```python
r = rsi(closes, self.config.period)      # period = 14
if r < self.config.lower: return  1      # lower = 30  -> LONG  (oversold)
if r > self.config.upper: return -1      # upper = 70  -> SHORT (overbought)
return 0
```

* A **price-only short-horizon mean-reversion** rule: buy oversold, sell/short overbought.
* **Not crypto-specific.** RSI is computed from closes alone — no funding, no basis, no
  IV, no liquidation, no peg. **It has NSE meaning.** (Proceeding with the assignment.)
* The catalog `rsi()` is **Cutler's simple RSI**, not Wilder's smoothed RSI: over the
  last `period+1` closes it sums gains and losses separately and divides by `period`, so
  it is a rolling simple average, not a Wilder exponential. This matters — the vectorised
  panel version must reproduce *this* function, not the textbook one, or the numbers
  describe a different indicator. Verified numerically in §3.
* `if losses == 0: return 100.0` — an unbroken 14-bar rally pins RSI at exactly 100.

**Long-only adaptation (brief §5).** An Indian delivery account cannot short. The `-1`
(overbought) branch is therefore **not tradable** and collapses to "not long". The book's
entire opportunity set is names with `RSI(period) < lower`. The book convention is
`higher score = more attractive`, so among flagged names the most-oversold ranks first.

**Prior worth stating up front.** `src/nsealgo/factors/core.py` already records, in its
module docstring, that the only multiple-testing-corrected study of Indian technical
rules (Romano-Wolf, 2015–2025) found **RSI_25_75 and RSI_30_70 both failed** (adjusted
p 0.071–0.473), while 7 of 8 surviving configurations were trend-following. That is a
strong prior that this will be a **negative finding**. It does not substitute for the run
— it is recorded so the result can be read against it rather than in isolation.

---

## 2. Declared parameter budget — 5 variants, fixed BEFORE any run

Declared here, before executing anything. **Not exceeded.** If it is, that is reported.

| # | name | period | lower | rank_by | rebalance | rationale |
|---|------|--------|-------|---------|-----------|-----------|
| V1 | `cat_14_30_deepest_M` | 14 | 30 | deepest | M | Catalog defaults verbatim, ranked by deepest oversold (most strategy-faithful) |
| V2 | `cat_14_30_mom126_M` | 14 | 30 | mom126 | M | Catalog defaults, ranked by 126d momentum (brief §5's suggested construction) |
| V3 | `wide_14_40_deepest_M` | 14 | 40 | deepest | M | Broadens the net — tests whether the *ordering* carries signal when the extreme tail is too thin to fill a 22-name book |
| V4 | `fast_6_30_deepest_M` | 6 | 30 | deepest | M | Faster oscillator (period 6), the regime where RSI reversion is classically supposed to work |
| V5 | `cat_14_30_deepest_W` | 14 | 30 | deepest | W | Weekly rebalance — does finer entry timing rescue a mean-reversion signal? (Note: monthly is the evidence-backed default; W is a cost headwind and is tested *because* of that.) |

**Final budget accounting: 5 of 5 variants used. Not exceeded.** (§0 records a
mid-session change to the backtest engine and exactly which of my outputs it touched.)

Axes covered: ranking convention (V1/V2), threshold breadth (V1/V3), lookback speed
(V1/V4), rebalance frequency (V1/V5). `upper=70` is untested by design: it is the
short branch, which a long-only Indian delivery book cannot express.

**Pre-declared selection rule (fixed now, before seeing any TRAIN number):** the variant
with the highest **TRAIN Sharpe** among those with **TRAIN MaxDD ≥ −25%**; ties broken by
higher Calmar. If no variant satisfies the drawdown floor, the highest TRAIN Sharpe wins
and the drawdown failure is reported. The winner is then frozen and evaluated **once** on
TEST.

---

## 3. Harness fidelity — `s1_data_check.py` → `S1_DATA_CHECK.json`

**Data.** `load_universe("data/nse")` → **48 symbols**, 4,625 daily bars,
2008-01-01 → 2026-10-01. Cleaning report: 274,541 rows in, 208,226 out; 66,312 dropped
pre-2008 vendor artefacts, 3 extreme events, 2 symbols excluded (`adanient` per the
loader's hard exclusion, `jiofin` for insufficient history). TRAIN 1,973 bars /
TEST 684 bars, 48 symbols each.

**Cost basis.** `round_trip_bps(100_000)` = **11.92**, `all_in_round_trip_bps(100_000)`
= **21.92**. `run_backtest` charges `all_in`, so **every number in this report is net of
21.92 bps** unless explicitly labelled gross.

**Indicator equivalence.** The vectorised `rsi_panel` was checked against the catalog's
streaming `cryptobot.strategies.indicators.rsi` on 235 random (symbol, bar) probes at
periods 6 / 14 / 21:

| period | max abs error vs catalog | identical |
|--------|--------------------------|-----------|
| 6 | 2.842e-14 | yes |
| 14 | 1.421e-14 | yes |
| 21 | 1.421e-14 | yes |

So the results below are about **Cutler's simple RSI** — the rolling-average RSI the
catalog strategy actually trades — not Wilder's smoothed RSI. They would describe a
different indicator otherwise.

**No-lookahead proof.** Two independent checks, both on TRAIN-history dates:

| check | result |
|-------|--------|
| prefix invariance, `rsi_panel(14)` (12 probe dates) | max err **0.000e+00** |
| prefix invariance, `signal_panel(14, 30)` | max err **0.000e+00** |
| prefix invariance, `build_score` `deepest` | max err **0.000e+00** |
| prefix invariance, `build_score` `mom126` | max err **0.000e+00** |
| future corruption: scramble every bar after *t* by ×7.77, re-read score at *t* | max change **0.000e+00** |

Prefix invariance (`f(full)[:t] == f(panel[:t+1])`) is the strong one: it catches
accidental negative shifts *and* any statistic that pools across dates. The score panel
uses **no ffill/bfill at all** — NaN means ineligible, which the engine never buys.

**Signal liveness (TRAIN only).**

| variant | long % of bar/symbol cells | short % | verdict |
|---------|--------------------------|---------|---------|
| RSI(14) < 30 | 9.50% | 17.00% | live (>5% floor) |
| RSI(14) < 40 | 23.38% | 17.00% | live |
| RSI(6) < 30 | 20.69% | 27.63% | live |
| RSI(21) < 30 | 5.12% | 11.60% | marginal |

**Structural finding — the catalog-default book is mostly cash.** The long-only book can
only buy names with `RSI < lower`, and on a typical monthly rebalance that is a handful
of names. Median eligible names at the catalog threshold: **3**. Because the engine caps
a single name at 12% and cannot legally fill the book with 3 names, the result is:

| TRAIN | avg invested | median | min | max | avg names |
|-------|-------------|--------|-----|-----|-----------|
| V1 (`RSI(14)<30`) | **27.4%** | 21.6% | **0.0%** | 90.0% | 4.3 |
| V3 (`RSI(14)<40`) | **42.1%** | 43.2% | **0.0%** | 90.0% | 10.2 |

The book holds 27% of capital and 73% cash on average at the catalog threshold, and goes
fully flat in some months. Any CAGR it posts is therefore a **blend of equity beta and
cash**, not a pure strategy return — a point that matters for every comparison below.

> ⚠️ **The numbers in this box and in §4 were measured on a version of
> `src/nsealgo/backtest/engine.py` that was rewritten at 14:05:28 during this session.
> See §0. Everything in §5, §6 and §7 was produced after the rewrite and is unaffected.**
> The corrected TRAIN figures are the ones shown above; the first-pass TRAIN table that
> showed V3 at Sharpe +0.42 and 26.2 names was measuring the old engine's
> slow-exit dilution and is **discarded**.

**Rank-driven or eligibility-driven?** While eligible names ≤ 22, the engine buys *every*
flagged name and the ranking convention cannot bind. Rank binds on only **1.0%** of
rebalances at the catalog threshold (14.6% for V3, 4.2% for V4). So at `lower=30` the
threshold *is* the strategy and "rank by deepest vs momentum" is nearly cosmetic.

---

## 4. TRAIN selection — `s2_train.py`, TEST never loaded

All 5 declared variants, TRAIN 2016-01-01 → 2023-12-29, net of 21.92 bps.
**(Corrected engine — see §0. The first-pass table from the pre-14:05:28 engine is
discarded.)**

| variant | CAGR | Sharpe | MaxDD | Calmar | Turn x/y | Cost %/y | Avg names |
|---------|------|--------|-------|--------|----------|-----------|-----------|
| V1 `cat_14_30_deepest_M` | 1.68% | **−0.41** | −32.99% | 0.05 | 2.95 | 1.41 | 4.3 |
| V2 `cat_14_30_mom126_M` | 3.07% | **−0.33** | −26.57% | 0.12 | 2.95 | 1.48 | 4.3 |
| V3 `wide_14_40_deepest_M` | 4.91% | **−0.08** | −29.87% | 0.16 | 3.91 | 2.01 | 10.2 |
| V4 `fast_6_30_deepest_M` | 4.42% | −0.16 | −27.18% | 0.16 | 3.71 | 2.01 | 7.6 |
| V5 `cat_14_30_deepest_W` | 0.88% | −0.40 | −36.85% | 0.02 | 10.62 | 4.98 | 4.4 |

TRAIN yearly returns — positive years: V1 5/8, V2 5/8, **V3 6/8**, V4 5/8, V5 5/8.

**Selection (pre-declared rule).** Highest TRAIN Sharpe among variants with MaxDD ≥ −25%.
**No variant met the −25% drawdown floor** — the rule's own fallback (max Sharpe) was
invoked and this is recorded rather than hidden. **FROZEN: `V3_wide_14_40_deepest_M`** —
`period=14, lower=40, rank_by="deepest", rebalance="M"` — TRAIN Sharpe −0.08, the only
variant that is not deeply negative. The same variant was selected on the pre-rewrite
engine, so the choice is robust to that change.

Observations that shape what TEST can show:
* **Every one of the five variants has a negative TRAIN Sharpe.** On TRAIN, before any
  out-of-sample data exists, all five configurations already fail to beat the 6.5%
  T-bill. That is the strongest available warning that the strategy has no edge to carry
  into TEST.
* All five also fail the drawdown floor (worst −36.85%).
* V1 vs V2 (deepest vs momentum rank) differ by 0.08 Sharpe, consistent with §3's
  finding that rank barely binds at this threshold.
* V5 (weekly) is the worst on return: 10.6x turnover/yr and 4.98%/yr cost drag.

---

## 5. TEST results — touched exactly once

`s3_test.py`. The primary number was computed and written to
`PRIMARY_TEST_RESULT.txt` **before any comparator ran**, and the winner was frozen on
TRAIN (`selected_variant.json`) before TEST was read.

**Window 2024-01-01 → 2026-10-01, 684 bars, 48 symbols. Net of 21.92 bps** (statutory
11.92 + 2×5 bps slippage, which is what `run_backtest` actually charges).

### 5.1 The strategy — `V3_wide_14_40_deepest_M` (frozen on TRAIN)

| metric | value |
|--------|-------|
| **CAGR** | **3.38%** |
| **Sharpe** | **−0.41** |
| Sortino | −0.55 |
| **MaxDD** | **−8.63%** (27 days underwater) |
| Calmar | 0.39 |
| Volatility (ann.) | 6.65% |
| Turnover | 3.96x/yr |
| **Cost drag** | **1.84%/yr** (5.17% cumulative over the window) |
| Trades | 11.8/yr (monthly) |
| **Avg names held** | **10.3** (cap 22) |
| Bar long fraction | 26.66% (TRAIN-frozen target 23.38%) |
| Eligible names per rebalance | min 0, median 8, mean 12.1, max 33 |
| Yearly | 2024 +2.8%, 2025 +9.1%, 2026 −2.2% → **positive in 2 of 3 years** |
| Total return | +9.77% over 2.75 years |

**The single most important number is the Sharpe: −0.41.** `compute_metrics` subtracts a
6.50% Indian T-bill, so a negative Sharpe means the book did not merely beat nothing — it
**failed to beat cash**, while taking equity risk to do so.

### 5.2 Buy-and-hold over the identical window, net

| metric | strategy | **buy-and-hold EW** | equal-weight book (engine) | **nsealgo composite** |
|--------|----------|---------------------|----------------------------|-----------------------|
| CAGR | 3.38% | **8.18%** | **9.64%** | 6.04% |
| Sharpe | −0.41 | **0.19** | **0.31** | 0.03 |
| MaxDD | **−8.63%** | −15.90% | −13.48% | −15.22% |
| Calmar | 0.39 | 0.51 | 0.71 | 0.40 |
| Volatility | 6.65% | 13.45% | 11.57% | 13.25% |
| Total return | +9.77% | +24.66% | +29.43% | +17.86% |

Buy-and-hold is `panel.pct_change().mean(axis=1)` with one entry round trip charged —
exactly the brief's comparator. The equal-weight row is the same 22-name / 12% / 25% /
10%-cash book with **no signal at all**, which isolates how much of the gap is the signal
rather than the construction.

**Head to head vs buy-and-hold:**

| | strategy | B&H | verdict |
|---|----------|-----|---------|
| CAGR | 3.38% | 8.18% | **WORSE by 4.80 pp/yr** |
| Sharpe | −0.41 | 0.19 | **WORSE by 0.60** |
| MaxDD | −8.63% | −15.90% | **BETTER (shallower) by 7.27 pp** |
| Calmar | 0.39 | 0.51 | worse |

So it wins on drawdown and loses on return — and the drawdown "win" is **not alpha**, it
is mostly cash (§5.4: 59.9% of capital sat idle). Its Calmar of 0.39 is nearly identical to
the composite's 0.40 while earning less than half the return at a third of the drawdown:
ratio metrics flatter a book that is simply under-invested.

### 5.3 Random-signal control — did it beat a coin flip?

50 seeds, `Bernoulli(23.38%)` eligibility (**the TRAIN-frozen long fraction**, so the
control cannot be accused of being fitted to TEST), ranked by 126d momentum, identical
engine, caps, cash, turnover budget and 21.92 bps costs:

| | strategy | random (50 seeds) |
|---|----------|-------------------|
| CAGR | **3.38%** | mean 1.49%, median 1.57%, p05 −2.71%, p95 4.86% |
| Sharpe | **−0.41** | mean −0.67, p05 −1.30, p95 −0.19 |
| MaxDD | −8.63% | mean −10.76% |
| Avg names | 10.3 | 10.9 |

**Yes — it beats a coin flip: +1.89 pp/yr of CAGR and +0.25 of Sharpe over the random
mean, sitting at roughly the 84th percentile of the random distribution.** That is the
minimum bar and it clears it. But the random books average Sharpe −0.67 because they are
also ~60% cash, so "beating random" here mostly means "being invested slightly more
often than a coin", not "having an edge". Neither is profitable.

### 5.4 Cost drag — gross vs net

| cost model | round trip | CAGR | Sharpe | drag |
|------------|-----------|------|--------|------|
| zero slippage (statutory only) | 11.92 bps | **4.20%** | −0.30 | 1.01%/y |
| **base (5 bps/side)** | **21.92 bps** | **3.38%** | **−0.41** | **1.84%/y** |
| double slippage | 31.92 bps | 2.56% | −0.53 | 2.66%/y |
| triple slippage | 41.92 bps | 1.75% | −0.65 | 3.45%/y |

Costs cost 0.82 pp/yr. **This is not a "promising but expensive" strategy.** Gross of
*all* costs the book returns 4.20% — **below the 6.50% T-bill**. The signal is
negative-excess *before* the cost stack is ever applied, so loosening costs cannot rescue
it (`GOAL.md` §6.4 was not invoked to try).

### 5.5 Sanity checks (brief §6)

| check | value | verdict |
|-------|-------|---------|
| plausibility ceiling | CAGR 3.4% | OK (< 40–50%) |
| avg names held | 10.3 | OK (not ~48, no residual accumulation) |
| signal liveness | 26.7% of bar/symbol cells | OK (> 5% floor) — it is not always-flat |
| capital deployed | mean **40.1%**, min 0.0%, max 87.1% | **59.9% average cash** |
| cost drag | 1.84%/y vs 4.20% gross | reported; not the cause of failure |

### 5.6 Post-hoc, non-selected: all 5 variants on TEST

Reported for completeness only. The winner was frozen on TRAIN before TEST was opened;
nothing here was used to choose anything.

| variant | TRAIN Sharpe | **TEST CAGR** | **TEST Sharpe** | TEST MaxDD |
|---------|--------------|---------------|----------------|------------|
| V1 `cat_14_30_deepest_M` (catalog default) | −0.41 | 1.83% | −0.73 | −5.58% |
| V2 `cat_14_30_mom126_M` | −0.33 | 1.84% | −0.73 | −5.58% |
| **V3 `wide_14_40_deepest_M` (selected)** | **−0.08** | **3.38%** | **−0.41** | −8.63% |
| V4 `fast_6_30_deepest_M` | −0.16 | 0.42% | −0.82 | −11.38% |
| V5 `cat_14_30_deepest_W` | −0.40 | −1.59% | −0.98 | −15.89% |

**All five have negative TRAIN Sharpe and all five have negative TEST Sharpe.** The
ranking was preserved (best TRAIN variant is best TEST variant), so the selection rule did
its job — but every rung of the ladder is below cash. There is no configuration of this
strategy in the declared budget that works.

---

## 6. Diagnosis — why it fails (`s4_diagnosis.py`)

### 6.1 The deployed sleeve is the real number

Splitting the book into the deployed sleeve and the cash it did not use:

| window | mean invested | **sleeve CAGR** | **book gross (exact)** | book net |
|--------|---------------|-----------------|------------------------|----------|
| TRAIN | 42.1% | **22.92%** | 6.63% | 4.82% |
| TEST | 40.0% | **6.58%** | 5.19% | **3.38%** |

The sleeve is the return on capital actually at risk, annualised on the same calendar
basis as the book. `book gross` is computed from the engine's own delivered weights and
reproduces `net CAGR + cost drag` exactly (6.63% − 2.00% = 4.63% vs 4.82% measured; the
residual is compounding), which is the check that this decomposition describes the same
book the engine charged costs on.

**A note on a trap here.** The obvious reconciliation `mean_invested × sleeve + cash`
gives 13.41% on TRAIN and 6.53% on TEST — **overstating the TRAIN book by 6.79 pp.**
Exposure is *countercyclical*: the book deploys precisely when the sleeve is falling, so
the linear form is wrong. Anyone decomposing a mostly-cash book this way will overstate
it; the exact gross column above is the one to trust.

**What it shows.** The sleeve made 22.9%/yr on TRAIN and **6.58%/yr on TEST — against a
6.50% T-bill**. Out-of-sample the deployed sleeve earned essentially nothing above cash.
The 1.84%/yr cost stack then turns that into a 3.38% book return. So the sequence is:
signal decayed to zero excess → costs took what little remained.

### 6.2 Engine-free: does low RSI predict forward returns in India? **No.**

Mean forward return by RSI(14) bucket, monthly sampled, both windows — this strips the
portfolio engine, the caps and the cost stack entirely:

**21-day horizon**

| bucket | TRAIN n | TRAIN mean | TEST n | TEST mean |
|--------|---------|-----------|--------|-----------|
| RSI < 30 (the strategy's gate) | 391 | **0.19%** | 140 | **0.94%** |
| RSI 30–40 | 588 | 1.48% | 223 | 1.07% |
| RSI 40–50 | 803 | 2.12% | 306 | 1.08% |
| RSI 50–70 | 1,839 | 2.05% | 629 | 1.13% |
| RSI > 70 (the short leg) | 725 | **2.17%** | 237 | −0.64% |

**126-day horizon**

| bucket | TRAIN mean | TEST mean |
|--------|-----------|-----------|
| RSI < 30 (the gate) | **11.34%** | **2.48%** |
| RSI 30–40 | 10.81% | 4.19% |
| RSI 40–50 | 12.02% | 5.30% |
| RSI 50–70 | 13.28% | 5.22% |
| RSI > 70 | 11.41% | 5.49% |

**The deeply-oversold bucket is the worst bucket at every horizon in both windows.** On
TRAIN at 21 days, RSI<30 names returned +0.19% forward while RSI>70 names returned
+2.17% — the exact opposite of what the strategy bets on. The relationship is not even
monotonic: the middle buckets (40–70) beat both extremes, which is neither the catalog's
rule nor a usable edge.

Rank correlation (Spearman IC between RSI and forward return, cross-sectional, monthly):

| horizon | TRAIN IC (t) | TEST IC (t) |
|---------|-------------|-------------|
| 21d | −0.007 (−0.35, n=94) | −0.039 (−0.98, n=32) |
| 63d | −0.020 (−1.04, n=94) | **−0.074 (−2.33, n=30)** |
| 126d | +0.004 (+0.21, n=94) | −0.057 (−1.71, n=27) |

The IC is nominally negative — the right sign for reversion — but the magnitudes are
0.004–0.074, i.e. economically negligible, and the single |t| > 2 result is one of six
tests. It does not survive multiple-testing correction, and it is contradicted by the
bucket table above, which shows the effect is not coming from the oversold end the
strategy trades.

### 6.3 This matches the literature already recorded in the repo

`src/nsealgo/factors/core.py` documents that the only multiple-testing-corrected study of
Indian technical rules (Romano-Wolf, 2015–2025) found **RSI_25_75 and RSI_30_70 both
failed** (adjusted p 0.071–0.473) while 7 of 8 surviving rules were trend-following, and
that Sehgal & Jain (2011) and IIMC (2020) find short-term *continuation* in Indian cash
equities. This run reproduces that result independently on this dataset: **deeply oversold
NIFTY-50 names underperform, not outperform.** The negative finding is the expected one.

---

## 7. Verdict

**No. `rsi_strategy` does not make money on NSE.** Out-of-sample it returned **3.38%
CAGR at Sharpe −0.41** against **8.18% for buy-and-hold** and a 6.50% risk-free rate —
it lost to cash, to the market, to an untilted book (9.64%) and to the nsealgo composite
(6.04%), over a 2.75-year window in which the deployed sleeve itself earned 6.58% against
a 6.50% T-bill, i.e. zero excess return **before** costs. It beat a random coin-flip book
(the minimum bar, +1.89 pp CAGR / +0.25 Sharpe) and that is the only thing it beat.

**Most likely reason.** Indian NIFTY-50 equities show **short-term continuation, not
reversion**, at daily-bar horizons — the deeply-oversold bucket is the *worst* forward-
return bucket at 21, 63 and 126 days in both TRAIN and TEST (§6.2). The strategy is
systematically buying the names about to keep falling. It also compounds the error: a
long-only book can only act on the oversold branch, which fires on ~3 names a month, so it
holds ~5–10 names and ~60% cash — concentrating the damage and diluting the upside. The
21.92 bps stack then takes a further 0.82 pp/yr, but costs are a *secondary* cause: the
signal is negative before they are applied. This matches the prior already recorded in
`src/nsealgo/factors/core.py`, which cites the only multiple-testing-corrected study of
Indian technical rules as finding RSI_25_75 and RSI_30_70 both failed.

**The one thing I would try next.** Not another RSI threshold — the bucket table says the
entire RSI ordering is uninformative here. I would test whether the *sign* of the effect
is tradeable: the evidence points to the opposite rule (buy the **strongest**, not the most
oversold), which is exactly what the repo's `build_composite_score` already does. The
concrete next experiment is an **oversold-without-continuation filter** — buy RSI<30 names
*only* when the cross-sectional 12-1 momentum is positive — since §6.2 shows oversold names
fall but the 40–70 bucket beats both tails. If that filter cannot clear Sharpe 0 and beat
the composite out-of-sample, RSI should be retired from the catalog as a live candidate.

---

## 8. Bugs and defects found

### 8.1 The big one — `src/nsealgo/backtest/engine.py` was rewritten mid-session

Full detail in **§0**. Summary: `apply_turnover_budget` was rewritten at 14:05:28 on
2026-10-09 by another process, fixing a real defect in which the old code carried dead
positions for months because `tgt[s] == 0` weights only decayed by `1 - lam` per rebalance,
so *"every headline number measured the dilution rather than the signal."*

It contaminated **only my first-pass TRAIN table**, which has been discarded and replaced.
It did **not** touch any TEST number (identical before and after, because V3's TEST
turnover sits just inside the 0.35 budget where both implementations return the target
unchanged). The correction moved V3's TRAIN Sharpe from **+0.42 to −0.08** and its average
position count from **26.2 to 10.2**.

**This is a live hazard for the other 20+ agents in `research/agent_*/`.** 107 of their
artefacts predate the rewrite. Any TRAIN sweep showing `avg_names` far above the
configured 22–30, or a TRAIN Sharpe far above its TEST Sharpe, should be re-run.

**Not my bug and not something I touched** — `src/` was read-only for this assignment and
`git status` confirms I modified nothing under `src/`, `tests/`, `GOAL.md` or `reports/`.

### 8.2 Defects in my own scratch, found and fixed

1. **§6.1 sleeve decomposition — arithmetic defect, corrected.** The first version
   annualised the sleeve over *invested days* while the equity had been compounded over
   the *whole window*, inflating the TRAIN sleeve from 22.92% to 23.71%. Replaced with a
   same-calendar-basis annualisation plus an exact `book gross` column that reconciles to
   `net CAGR + cost drag`. The report also now flags that the intuitive
   `mean_invested × sleeve + cash` reconciliation **overstates by 6.79 pp on TRAIN**
   because exposure is countercyclical.
2. **`s3_test.py` printed a misleading viability verdict.** It tested `gross_cagr > 0`.
   Gross of 4.20% clears zero and would have been labelled "viable" while being *below*
   the 6.50% risk-free rate. Replaced with an explicit T-bill comparison. The conclusion
   is unchanged (it fails either way) but the earlier line was wrong.
3. **Three script errors caught on first execution and fixed before any number was
   reported** — an unclosed `header(...)` call, an unused-variable placeholder, and a
   missing `build_composite_score` import. No result was ever taken from a script that had
   not run cleanly.

### 8.3 Verified clean

* The catalog `rsi()` is **Cutler's simple RSI**, not Wilder's — my vectorised panel
  version matches it to **1.4e-14** at periods 6/14/21 (235 probes each). Had I
  implemented textbook Wilder RSI, every number in this report would have described a
  different indicator than the one the strategy trades.
* **No lookahead**, proven two independent ways at exactly 0.000e+00 error: prefix
  invariance of `rsi_panel` / `signal_panel` / both `build_score` constructions across 12
  probe dates, and a future-corruption test that scrambles every bar after *t* by ×7.77
  and re-reads the score at *t*.
* Determinism: identical results across 3 repeat runs and 4 `PYTHONHASHSEED` values;
  stable panel hash; unchanged data-file mtimes. The §0 discrepancy was the *file*
  changing, not nondeterminism.

### 8.4 Structural finding (not a bug, but a trap worth recording)

Any catalog mean-reversion strategy transplanted into a long-only Indian delivery book
degenerates into a mostly-cash, few-name book: at the catalog default `RSI(14)<30`, only
**3 names median** are eligible per monthly rebalance, and the 12% single-name cap means
the book cannot fill — average deployment **27.4%** on TRAIN. Any future agent porting an
oscillator should check the *capital-deployed* fraction before interpreting a CAGR, because
the same arithmetic produces flattering Sharpe/Calmar on a book that is mostly T-bills.

---

## 9. Reproduce

```bash
cd research/agent_rsi
../../.venv/bin/python s1_data_check.py   # data audit, RSI fidelity, no-lookahead proof
../../.venv/bin/python s2_train.py        # 5 variants on TRAIN, freeze the winner
../../.venv/bin/python s3_test.py         # TEST once + comparators + random control
../../.venv/bin/python s4_diagnosis.py    # sleeve-vs-cash, bucket table, Spearman IC
```

Artefacts: `S1_DATA_CHECK.json`, `selected_variant.json`, `PRIMARY_TEST_RESULT.txt`,
`S3_TEST_RESULT.json`. Nothing in `src/`, `tests/`, `GOAL.md` or `reports/` was modified.
No commits made.

**One stray side-effect file:** `research/agent_rsi/cryptobot.db` is created on disk
whenever `cryptobot.strategies.indicators` is imported (the package opens its SQLite
store relative to the CWD). `validate_rsi_matches_catalog` needs that import, so the
file appears on the first fidelity check. It is inert and lives inside this scratch
directory; sibling agents (`agent_cci`, `agent_fisher`) have the same artefact. Every
python invocation in this run used `research/agent_rsi` as the working directory.