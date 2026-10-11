# ROC (Rate of Change) Strategy on NSE NIFTY-50 — Validation Report

**Strategy file:** `src/cryptobot/strategies/catalog/rate_of_change.py`
**Class:** `RocStrategy` / `RocConfig(period=10, threshold=0.01, quantity=1)`
**Assigned agent:** `agent_roc`
**Protocol:** `research/AGENT_BRIEF.md` (read in full; TRAIN 2016-01-01→2023-12-31,
TEST 2024-01-01→2026-10-01)

> **Verdict: NO. This strategy does not make money on NSE.** On the untouched TEST
> window it returns **1.27% CAGR / Sharpe −0.42 / MaxDD −19.79%**, against
> buy-and-hold's **8.34% / +0.19 / −15.90%** on the identical window. It loses on
> return, on risk-adjusted return **and** on drawdown. Details in §6.

## Provenance

| item | value |
|---|---|
| **`engine_sha`** | **`970713f3eecf`** — every number in this report |
| `all_in_round_trip_bps(100_000)` charged by `run_backtest` | 21.92 bps (asserted at runtime on every result) |
| pandas / numpy | 3.0.5 / 2.5.3 |
| data | `data/nse/<sym>_1d.csv` via `nsealgo.data.loader.load_universe` |
| scratch | `research/agent_roc/` (nothing outside it was written) |
| date | 2026-10-10 |

> **Engine-change disclosure.** `src/nsealgo/backtest/engine.py` was fixed today (dead
> positions used to decay toward zero under the turnover budget instead of exiting).
> All results here were produced *after* that fix, under `engine_sha = 970713f3eecf`,
> confirmed at runtime from `BacktestResult.engine_sha` and from the `diag` block.
> **These numbers are not comparable to any pre-fix result in this repo.**

> **TEST-window disclosure.** TEST was entered exactly once, in `s2_test.py`, after the
> 5-variant budget and the selection rule were written down and TRAIN was run to
> completion. No parameter, variant or ranking was chosen after TEST was read. The
> post-hoc diagnostics in `s3_posthoc.py` touch TEST again, but they are **ablations,
> buckets and nulls** — none of them is a selectable variant, and none of them produced
> the frozen choice.

---

## 1. What the strategy actually is

```python
r = roc(closes, period)          # period = 10
if r != r:          return 0     # NaN warm-up
if r >  threshold:  return 1     # threshold = 0.01
if r < -threshold:  return -1
return 0
```

`roc(closes, n) = (close[-1] − close[−n−1]) / close[−n−1]` — the plain n-bar rate of
change, i.e. the n-day return. **Price-only: no funding, no basis, no IV, no
liquidation reference, no stablecoin peg. This strategy is not crypto-specific and has
genuine NSE meaning**, so the "no NSE meaning → stop" exit does not apply.

It is a **short-horizon continuation** rule: buy after 10 days of more than 1% gain.
That is the mirror image of the mean-reversion catalog strategies already recorded as
validated negatives (`agent_cci`), so the prior was genuinely open.

**Long-only adaptation (brief §5).** An Indian delivery account cannot short, so the
`-1` branch is not tradable and collapses into "not long" (score 0).

**Signal liveness (brief §6.3).** ROC(10) > 1% fires on **43.6%** of all bar/symbol
cells (**46.1%** in TRAIN, **52.4%** in TEST) — mean **20.9** of 48 names flagged per
bar. Well above the 5% "effectively always flat" floor; the book runs at 17–19 names
against a 22-name cap.

> **First substantive observation.** `threshold = 0.01` on a 10-day ROC is a *loose*
> gate. It means "this stock went up over the last fortnight", true a bit under half the
> time, so it excludes barely half the universe on any given day. And
> `corr(roc10, mom126) = 0.263`, so it is not a momentum proxy either. It behaves as a
> **broad market-direction / breadth overlay**, and §5.6 shows that is exactly — and
> only — where its TRAIN value came from.

---

## 2. Declared parameter budget — 5 variants, fixed BEFORE any run

| # | name | period | threshold | rebalance | rank_by | rationale |
|---|------|--------|-----------|-----------|---------|-----------|
| V1 | `V1_base` | 10 | 0.01 | M | `mom126` | catalog defaults + brief §5 construction |
| V2 | `V2_tight` | 20 | 0.01 | M | `mom126` | signal horizon doubled to one month |
| V3 | `V3_wide` | 10 | 0.00 | M | `mom126` | threshold opened (long whenever the 10d return > 0) |
| V4 | `V4_week` | 10 | 0.01 | W | `mom126` | rebalance matched to the 10-day signal horizon |
| V5 | `V5_raw` | 10 | 0.01 | M | `roc10` | rank by the ROC value itself, no momentum overlay |

**Selection rule, fixed in advance:** highest **TRAIN** Sharpe; ties broken by TRAIN
Calmar.

**Not variants** (comparators / diagnostics, never selectable): buy-and-hold,
`build_composite_score`, momentum-only ablation, random-signal nulls, cost-stress
models, ROC-quintile buckets, gate-timing buckets, the paired monthly test.

**Budget status: 5 declared, 5 run, not exceeded.** No 6th variant was tested.

---

## 3. Data and cost basis

```
CLEANING REPORT
  rows in 274,541 -> rows out 208,226
  dropped pre-2008 66,312 | artifact 0 | non-positive 0 | extreme 3
  excluded symbols ['adanient', 'jiofin']
symbols 48   panel 4,625 bars   span 2008-01-01 -> 2026-10-01   NaN cells 13,916
TRAIN  1,973 bars (2016-01-01 -> 2023-12-31)
TEST     684 bars (2024-01-01 -> 2026-10-01)
```

**Cost basis.** `CostModel(segment="delivery", slippage_bps=5)`.
`round_trip_bps(100_000)` = **11.92 bps** (statutory only).
`all_in_round_trip_bps(100_000)` = **21.92 bps**, and `run_backtest` charges the
latter — confirmed at runtime from `diag['round_trip_bps']` on every single result.
**Every strategy number in this report is net of 21.92 bps.** The 11.92 figure appears
only in the cost-stress table, labelled statutory-only.

**Library parity — the vectorised ROC *is* the catalog ROC.** `s0_data_check.py`
compares my `roc_panel` against `cryptobot.strategies.indicators.roc` over 96
(symbol, period, bar-index) probes at periods 10 and 20:
**`max_abs_err = 1.110e-16`** — float round-off, nothing else.

**No lookahead — proven, not asserted.** `s1b_lookahead.py` truncates the panel at 25
random cut points (bars 619–4524) and rebuilds the ROC gate and the full score from
the truncated panel only: **`max |full − truncated| = 0.000e+00` over 13,583 values.**
If the score at bar *t* had touched any bar after *t*, truncation would have changed
it. Independently, the delivered book changes on exactly **95 of 1,973** TRAIN bars —
the monthly rebalances and nothing else — and `run_backtest` attributes returns via
`gross = held.shift(1) * rets`.

---

## 4. TRAIN (selection window) — 2016-01-01 → 2023-12-31

`s1_train.py`, 1,973 bars × 48 symbols, engine `970713f3eecf`, net of 21.92 bps.
All five variants were run and the winner frozen here, before TEST was opened.

| book | CAGR | Sharpe | MaxDD | Calmar | Turn/y | Cost/y | Trades/y | Names |
|---|---|---|---|---|---|---|---|---|
| **V3_wide** | **15.37%** | **0.88** | **−10.71%** | **1.44** | 4.00x | 3.16% | 11.7 | 19.1 |
| V1_base | 12.25% | 0.63 | −10.45% | 1.17 | 4.07x | 2.85% | 11.7 | 17.7 |
| V5_raw | 9.58% | 0.38 | −10.11% | 0.95 | 4.11x | 2.58% | 11.7 | 17.8 |
| V2_tight | 8.95% | 0.28 | −24.87% | 0.36 | 4.06x | 2.50% | 11.7 | 18.7 |
| V4_week | 6.93% | 0.09 | −24.31% | 0.29 | 15.95x | 8.64% | 51.6 | 17.4 |
| *momentum126 only (comparator)* | *17.56%* | *0.73* | *−35.21%* | *0.50* | *2.64x* | *2.29%* | *11.7* | *21.8* |

**Winner, frozen on TRAIN: `V3_wide`** — period 10, threshold 0.0, monthly, ranked by
126-day momentum among flagged names. TRAIN Sharpe 0.88, Calmar 1.44.

Two TRAIN facts worth recording, because they are what the TEST result later explains:

1. **The gate's job on TRAIN was drawdown control, not return.** Plain 126-day momentum
   earns a *higher* CAGR (17.56% vs 15.37%) but with a **−35.21%** drawdown against
   **−10.71%** with the ROC gate on — a 3.3x reduction bought for 2.2 pp of CAGR. That
   −35% number alone would fail `GOAL.md` §2.3, which is presumably why a
   drawdown-reducing filter looked attractive.
2. **Weekly rebalancing is a trap here** (`V4_week`, Sharpe 0.09): turnover 15.95x/yr,
   cost drag 8.64%/yr. The 10-day signal horizon does not justify weekly rebalancing at
   Indian delivery costs. Recorded so the next agent does not re-derive it.

---

## 5. TEST (out-of-sample) — 2024-01-01 → 2026-10-01

`s2_test.py`, 684 bars × 48 symbols, engine `970713f3eecf`, net of 21.92 bps.

### 5.1 PRIMARY RESULT — frozen TRAIN winner `V3_wide`

| metric | value |
|---|---|
| **CAGR** | **1.27%** |
| **Sharpe** | **−0.42** |
| **Sortino** | −0.47 |
| **MaxDD** | **−19.79%** (502 trading days underwater) |
| **Calmar** | 0.06 |
| **Total return** | +3.61% over 2.80 years |
| Annualised vol | 10.68% |
| Turnover | 4.02x / yr |
| Cost drag | 2.02% / yr |
| Trades | 11.8 / yr |
| Avg names held | 18.4 |
| Win rate (daily) | 50.3% |
| Bar long fraction | 52.41% (TRAIN 50.71%) |
| Calendar years | 2024 **+19.16%**, 2025 **+0.17%**, 2026 **−13.20%** (2 of 3 positive) |

### 5.2 The whole declared family on TEST — family diagnostic, *not* a selection

| variant | CAGR | Sharpe | MaxDD | Calmar | Turn/y | Cost/y | Names | TRAIN Sharpe | TEST beat its own TRAIN? |
|---|---|---|---|---|---|---|---|---|---|
| V1_base | 0.78% | −0.51 | −16.86% | 0.05 | 4.11x | 1.99% | 16.9 | 0.63 | no |
| V2_tight | −1.41% | −0.69 | −22.85% | −0.06 | 4.14x | 1.99% | 17.8 | 0.28 | no |
| **V3_wide** (frozen) | **1.27%** | **−0.42** | −19.79% | 0.06 | 4.02x | 2.02% | 18.4 | 0.88 | no |
| V4_week | −7.52% | −1.28 | −26.60% | −0.28 | 16.32x | 6.60% | 16.5 | 0.09 | no |
| V5_raw | 0.96% | −0.60 | −13.80% | 0.07 | 4.16x | 2.01% | 16.9 | 0.38 | no |

**Every TRAIN Sharpe in the family was positive (0.09 → 0.88). Every TEST Sharpe is
negative (−0.42 → −1.28).** Not one variant reproduced. There is no "the other one was
better" reading available here, and none of these numbers was used to re-select.

### 5.3 Buy-and-hold over the identical TEST window (brief §4 rule 5)

`panel.pct_change().mean(axis=1)`, one entry round trip charged (21.92 bps).

| book | CAGR | Sharpe | MaxDD | Calmar | Names |
|---|---|---|---|---|---|
| **buy-and-hold (48, unconstrained)** | **8.34%** | **0.19** | **−15.90%** | **0.52** | 48 |
| 2024 / 2025 / 2026 | +20.40% / +13.35% / −8.27% | | | | |
| `nsealgo composite` (`build_composite_score`, same panel, monthly) | 6.04% | 0.03 | −15.22% | 0.40 | 21.3 |

### 5.4 TEST vs buy-and-hold and vs the composite

| | ROC `V3_wide` | buy-and-hold | composite | vs B&H | vs composite |
|---|---|---|---|---|---|
| CAGR | 1.27% | 8.34% | 6.04% | **−7.07 pp — worse** | **−4.77 pp — worse** |
| Sharpe | −0.42 | +0.19 | +0.03 | **−0.61 — worse** | **−0.45 — worse** |
| MaxDD | −19.79% | −15.90% | −15.22% | **−3.89 pp — worse** | **−4.56 pp — worse** |
| Calmar | 0.06 | 0.52 | 0.40 | −0.46 — worse | −0.33 — worse |

It loses on **all four** axes, to both comparators. There is no partial credit to give.

### 5.5 Negative controls — did it beat a coin? (brief §6.5)

Two nulls, both run through the identical engine, costs, caps and cash buffer.

**(a) true coin** — random scores on a randomly-chosen eligible subset at a matched
52.41% long fraction, 100 seeds (`s3_posthoc.py §E`, seeds 0–99):

```
true coin    CAGR  3.46% ± 1.62     Sharpe -0.30 ± 0.19     MaxDD -11.22%     names 21.0
ROC V3_wide  CAGR  1.27%            Sharpe -0.42             MaxDD -19.79%     names 18.4

percentile inside the null : CAGR   6th      Sharpe  26th      MaxDD   0th  (0th = worst of 100)
z vs the null              : CAGR -1.35     Sharpe -0.64
```

**(b) random eligibility + the same mom126 ranking**, 100 seeds (`s2_test.py §5.5`,
seeds 1000–1099):

```
random-elig+mom126  CAGR mean -1.49% sd 1.50 (p05 -3.60, p95 +1.06)  Sharpe mean -0.96 sd 0.18
ROC V3_wide         CAGR 1.27%   -> 97th percentile, z +1.85          Sharpe -0.42 -> 99th, z +2.92
```

> **Null (b) is not a valid null and must not be read as a pass.** Its mean is
> **−1.49%** because randomly deleting 47.6% of the universe destroys the momentum
> ranking that the *ranking* half of the book depends on — the null is measuring
> "momentum with sabotaged eligibility", not "ROC or no ROC". An eligibility-based null
> is only legitimate when eligibility carries no information; here it carries a
> great deal. **Against the matched coin (a), which is the null brief §6.5 actually
> asks for, the strategy is at the 6th percentile on CAGR and the 0th on drawdown.**

**Paired monthly test** (`s3_posthoc.py §C`, 34 months, vs the mean of 20
random-eligibility books): mean excess **+0.279%/mo**, positive in **16/34** months,
**t = +0.89** — not significant at 5%. Zero detectable advantage against that null, and
against the coin it is negative.

> **Answer to brief §6.5: NO. The strategy does not beat a random signal.** On CAGR it
> sits at the 6th percentile of a 100-seed matched-exposure coin null (z = −1.35), and
> its maximum drawdown is **worse than all 100** of those random books.

### 5.6 Why it fails — the gate is a market-timing overlay, and the timing inverted

**Ablation** (`s3_posthoc.py §A`; identical book, identical ranking, identical costs,
only the ROC gate toggled):

| window | book | CAGR | Sharpe | MaxDD | Calmar |
|---|---|---|---|---|---|
| TRAIN | momentum126 only | 17.56% | 0.73 | −35.21% | 0.50 |
| TRAIN | ROC gate + mom rank | 15.37% | 0.88 | **−10.71%** | **1.44** |
| | **gate effect** | −2.19 pp | **+0.15** | **+24.50 pp** | **+0.94** |
| TEST | momentum126 only | 1.58% | −0.30 | −18.82% | 0.08 |
| TEST | ROC gate + mom rank | 1.27% | −0.42 | −19.79% | 0.06 |
| | **gate effect** | −0.31 pp | **−0.12** | **−0.97 pp** | **−0.02** |

**The entire TRAIN advantage was the drawdown reduction, and it fully reversed
out-of-sample.** +24.50 pp on TRAIN became −0.97 pp on TEST. The ROC gate contributed
nothing durable.

**Gate timing** (`s3_posthoc.py §F`). The gate's pass-rate is a breadth measure, and
breadth's relationship with the *next* month's market return flips sign across the
split:

| gate pass-rate quartile | TRAIN next-21d market | TEST next-21d market |
|---|---|---|
| lowest (~0–37%) | +1.49% | +1.47% |
| 2nd | +1.96% | +1.13% |
| 3rd | +1.44% | +0.67% |
| highest (~73–100%) | **+2.94%** | **+0.17%** |
| **corr(pass-rate, next-21d market)** | **+0.094** | **−0.127** |

In TRAIN, wide breadth preceded better months — a working trend filter. In TEST the
relationship **inverted**, and the gate concentrated the book precisely when the market
was about to go nowhere. Consistently with that, the book shrank as the window
progressed — invested **74.3% → 58.5% → 53.7%** across 2024 / 2025 / 2026 — and still
underperformed the market in every year of the window:

| year | ROC book | EW market | buy-and-hold (48) | avg names | invested |
|---|---|---|---|---|---|
| 2024 | +19.16% | +20.26% | +20.40% | 19.4 | 74.3% |
| 2025 | +0.17% | +13.35% | +13.35% | 18.2 | 58.5% |
| 2026 | **−13.20%** | −8.26% | −8.27% | 17.2 | 53.7% |

39.0% of TEST bars have fewer than 22 names passing the gate (min 2, mean 25.2).

**Is the ROC *stock-selection* signal real at all?** (`s3_posthoc.py §B`) Mean 21-day
forward return by ROC-10 cross-sectional quintile, momentum-matched within mom126
quartiles, so the ranking half of the book is held constant:

| | raw Q5 − Q1 | **momentum-matched Q5 − Q1** |
|---|---|---|
| TRAIN (n = 90,702) | +0.309 pp / 21d | **+0.225 pp / 21d** |
| TEST (n = 31,821) | +0.162 pp / 21d | **+0.328 pp / 21d** |

The stock-selection signal is **positive in both windows** — ROC ordering is not noise,
it is just **small**: ~0.2–0.3 pp per 21 days ≈ 1.3–1.9%/yr gross on the spread, of
which a long-only book realises a fraction. Against a cost drag of **2.02%/yr** and a
100-seed null whose CAGR standard deviation is **1.62 pp**, that signal is below the
noise floor of both. **The signal is smaller than the costs of harvesting it.**

### 5.7 Cost drag (brief §6.4)

Same signal, cost model varied (`s2_test.py §5.6`):

| cost model | rt bps | CAGR | Sharpe | MaxDD |
|---|---|---|---|---|
| statutory only (`zero_cost`) | 11.92 | 2.09% | −0.34 | −18.38% |
| **base, 5 bps/side — reported** | **21.92** | **1.27%** | **−0.42** | −19.79% |
| `double_slippage` | 31.92 | 0.46% | −0.49 | −21.16% |
| `triple_slippage` | 41.92 | −0.34% | −0.57 | −22.52% |

Gross-of-slippage CAGR is **3.29%**, still far below buy-and-hold's 8.34% and below the
composite's 6.04%. So **this is not primarily a costs story** — the signal is absent
even at the statutory floor. But costs are not innocent either: 2.02%/yr of drag
against a 3.29% gross is most of why the net number is 1.27%, and at `triple_slippage`
the strategy is outright negative. A ₹21L book rebalanced 11.8x/yr cannot pay for a
signal this small.

### 5.8 Brief §6 sanity checks

| check | result |
|---|---|
| 1 plausibility (unlevered long-only CAGR < 40–50%) | 1.27% — **OK** |
| 2 weight count (not ~48) | avg 18.4 names, cap 22 — **OK**, no residual accumulation |
| 3 signal liveness (> 5% of bars) | 52.41% of bar/symbol cells — **OK**, genuinely long |
| 4 cost drag | 2.02%/yr vs 1.27% CAGR; gross 3.29% still ≪ market — drag is not the *only* problem |
| 5 random control | **FAIL** — 6th percentile CAGR, 0th percentile drawdown vs a matched coin |

---

## 6. Verdict

> **No. `rate_of_change` does not make money on NSE NIFTY-50.** Out-of-sample it
> returns **1.27% CAGR with a Sharpe of −0.42 and a −19.79% drawdown**, against
> buy-and-hold's **8.34% / +0.19 / −15.90%** on the identical window. It loses to
> buy-and-hold and to the `nsealgo` composite on return, Sharpe, drawdown and Calmar
> alike; it sits at the **6th percentile of a 100-seed matched-exposure coin null on
> CAGR** and its drawdown is **worse than all 100** of those random books.

It is not a liveness problem (long 52% of cells), not a lookahead problem (proved
exactly by truncation), not a bug in my harness (ROC parity is 1.1e-16 and every number
was reproduced after a full lint-and-rerun pass), and only partly a costs problem
(gross 3.29% is still below market).

### Most likely reason

**The ROC gate is not a stock-selection rule — it is a 10-day breadth filter, and its
only durable value was regime-specific market timing.** `threshold = 0.01` on a 10-day
ROC excludes barely half the universe (46% of cells pass), so it says more about "is
the market in an uptrend right now" than about "is this a good stock". On TRAIN that
timing worked spectacularly for drawdown (−35.21% → −10.71%). On TEST the
pass-rate/forward-return relationship **inverted** (+0.094 → −0.127), the drawdown
benefit disappeared (−24.50 pp → −0.97 pp), and the gate concentrated the book into the
part of the window where it then lost 13.20% against a market's −8.26%.

Underneath that, the genuinely cross-sectional part of ROC *is* real but tiny:
momentum-matched Q5−Q1 is **+0.225 pp/21d on TRAIN and +0.328 pp/21d on TEST**, both
positive, both worth roughly 1.3–1.9%/yr gross on the spread. The book turns over 4x/yr
and pays **2.02%/yr**. **The signal is smaller than the bill for harvesting it.** That
is the whole reason this fails, and it is a property of the indicator at this horizon on
this universe, not of the implementation.

This is an honest, publishable negative. Two independent established results in the
repo agree with it: `nsealgo/factors/core.py` reached on literature grounds that
Indian cash equities are a momentum market with no short-horizon mean-reversion core,
and `agent_cci` measured from the catalog side that short-horizon reversal has no
long-only NSE edge. ROC-10 turns out to be too short to be a useful momentum measure
either — it is the loser of both.

### The one thing I would try next

**Not another parameter, and not another ROC period.** Two leads, both with the same
shape:

1. **The stock-selection half is worth keeping; the gate is not.** The momentum-matched
   ROC spread is positive in both windows. Drop the binary `roc > 0` eligibility screen
   and use ROC as a *continuous, ranked* factor inside `build_composite_score` (a small
   weight, replacing part of the `momentum_12_1` weight) so it is blended rather than
   used to switch the book off. Note `V5_raw` (pure ROC ranking) scored −0.60 Sharpe on
   TEST, so this is **not** the same experiment and would need a fresh look — but the
   two differ in an important way: `V5_raw` still applied the same binary gate on top.

2. **The drawdown job the ROC gate was pretending to do already has a proper tool.**
   `src/nsealgo/factors/regime.py` exists precisely for this — its module docstring
   records that the composite alone produced a **−40.9%** drawdown over 2008–2026 and
   that `exposure_series` / `blend_with_cash` are the sanctioned overlay, backed by
   Singh & Walia (2020) time-series momentum on the market proxy, at a 126-day lookback
   rather than 10 days. The ROC gate was an accidental, unprincipled substitute for it,
   which is why it worked in one regime and inverted in the next. If a drawdown lever is
   wanted, use that one and test it on TRAIN.

Both must be entered as **pre-registered hypotheses on a fresh out-of-sample window**.
The 2024-01-01 → 2026-10-01 TEST set is now consumed and must not be reused for
selection. My honest prior on both: the composite one is worth a shot because its
underlying spread is positive in both windows; the regime one is already in the codebase
and only needs an honest OOS test.

The higher-value action is the one already taken by writing this down: **retire ROC-10
as a standalone NSE strategy**, so the next agent does not spend a budget re-deriving a
result that cost one full TRAIN/TEST cycle to establish.

---

## 7. Bugs found

Seven. None in `src/nsealgo`, `src/cryptobot`, `GOAL.md` or `reports/`; all in this
agent's own harness except **BUG-2**, which is a library-level defect that affects other
agents' scripts in this repo.

### BUG-2 — `pd.DataFrame({name: DataFrame})` is broken on pandas 3.0.5 ★ most valuable

`ValueError: If using all scalar values, you must pass an index`, raised for a perfectly
ordinary construction of two frames with identical index and columns:

```python
A = pd.DataFrame(np.arange(10.).reshape(5, 2), index=i, columns=["a", "b"])
pd.DataFrame({"x": A, "y": A})      # ValueError
pd.DataFrame({"x": A["a"]})         # OK  — Series values are fine
pd.concat([A, A], axis=1)           # OK
A.assign(x=A["a"])                  # OK
```

It is unconditional — int, float, str, Categorical and datetime column indexes all
fail; the column dtype is irrelevant. `DataFrame({str: Series})` works, so only
**DataFrame-valued** dict entries are affected.

This is a very common idiom when stacking factor panels in research scripts, and it is
already used across this repo — `research/agent_bollinger_bands/01_diagnostics.py:93`,
`research/agent_atr_trailing/stage1b_diag.py:84`,
`research/agent_flag_pattern/s2_test.py:126`,
`research/agent_correlation_gate/v06_rank_mismatch.py:31`,
`research/agent_macd/run.py:334` and more. **Any of those scripts will fail the moment
someone runs it under this venv.** `src/nsealgo` and `src/cryptobot` do **not** use the
pattern, so production is unaffected.

*Workaround applied here:* stack to `Series` first (`frame.stack()`), then build the
frame from Series.

### BUG-1 — `roc()` parity check compared different bar indices

`s0_data_check.py`. Reported a spurious `max_abs_err = 6.7e-02` — which would have cast
doubt on the signal construction. Cause: the catalog's `roc()` consumes a **contiguous**
close list, so parity must be checked on a NaN-free per-symbol series, while my vector
form lives on the union-calendar panel with 13,916 NaN cells. Comparing the two compares
different bars. Fixed before any result was produced; the true figure is **1.110e-16**.

### BUG-3 — "quintiles" that were 300 groups

`s3_posthoc.py §B`, first draft. `r10.rank(axis=1, pct=True)` produces a *continuous*
percentile, so `groupby` on it created hundreds of groups and the table labelled
"Q1…Q5" was actually a top-1-versus-bottom-1 comparison. Fixed with explicit
`np.digitize` bins.

### BUG-4 — `np.digitize` maps NaN to the **top** bucket

Same section. `np.digitize(nan, bins)` returns `len(bins)`, i.e. the strongest-ROC
bucket — so a missing price would have been counted as the best signal in the universe.
One cell, TEST, forward return −11.587%, which alone dragged the reported "raw Q5−Q1"
to a nonsensical −11.163 pp. Fixed by masking NaN to −1 before digitizing and dropping
it. *General lesson: `np.digitize` is not NaN-safe and does not raise.*

### BUG-5 — `resample().last()` is not a compounded annual return

`s3_posthoc.py §D`, first draft. `mkt.resample("YE").last().pct_change()` compares the
last *daily* return of one year with the last daily return of the next, which printed
**+565.87% for 2025** and **−220.15% for 2026**. Fixed by compounding to an equity
curve first. (A reminder that appears in at least three other agent scripts.)

A second, subtler instance of the same mistake survived into the first fixed draft: §D's
buy-and-hold column was built from the **uncosted** equal-weight series, so it showed
2024 at **+20.13%** while §5.3 (which charges the entry round trip) showed **+20.40%**.
Same comparator, two numbers, in one report. Fixed by having §D call the same
cost-charged `buy_and_hold()` used in §5.3; both now read **+20.40%**.

### BUG-6 — paired monthly t-statistic returned `NaN` and printed `+0.00`

`s2_test.py §5.5`, first draft. It intersected a `PeriodIndex` of months with a
`DatetimeIndex` of bar dates; the intersection was empty, so it reported "positive in
0/0 months, t = +0.00" and would have been read as a real (zero) result. Superseded by
`s3_posthoc.py §C`, which resamples both sides to month-ends: **+0.279%/mo, 16/34 months,
t = +0.89**.

### BUG-7 — tz-naive window bounds against a tz-aware index

`common.py`. `panel.index` is `Asia/Kolkata`, so `panel.loc[pd.Timestamp("2016-01-01"):…]`
raises `TypeError: Cannot compare tz-naive and tz-aware datetime-like objects`. Fixed by
making `TRAIN_START` / `TEST_END` etc. tz-aware.

---

## 8. Files

| file | role |
|---|---|
| `common.py` | shared harness — panels, vectorised ROC, score construction, comparators, nulls |
| `s0_data_check.py` | engine sha, cost basis, cleaning report, ROC-library parity, liveness |
| `s1_train.py` | **TRAIN selection** — the 5 declared variants, winner frozen here |
| `s1b_lookahead.py` | truncation-based no-lookahead proof + weight-hold structural check |
| `s2_test.py` | **the single TEST touch** — primary result, family, comparators, nulls, cost stress |
| `s3_posthoc.py` | post-hoc diagnostics: gate ablation, ROC quintiles, paired test, gate timing, coin null |
| `S0_OUT.txt` … `S3_OUT.txt` | captured stdout of the five scripts |
| `train_results.json`, `test_results.json`, `posthoc_results.json` | machine-readable results |
| `REPORT.md` | this file |

Reproduce:

```bash
cd research/agent_roc
../../.venv/bin/python s0_data_check.py   # ~10s
../../.venv/bin/python s1_train.py        # ~30s
../../.venv/bin/python s1b_lookahead.py   # ~10s
../../.venv/bin/python s2_test.py         # ~4m
../../.venv/bin/python s3_posthoc.py      # ~2m
```

The five are independent. Nothing outside `research/agent_roc/` is written or modified.

Lint: `.venv/bin/ruff check research/agent_roc/*.py` → clean.

**Nothing in `src/`, `tests/`, `GOAL.md` or `reports/` was modified. Nothing was
committed or pushed.**