# CMF Strategy — NSE NIFTY-50 Validation Report

**Agent:** `agent_cmf`
**Strategy:** `cmf_strategy` — `src/cryptobot/strategies/catalog/cmf_strategy.py`
**Status:** IN PROGRESS — this file is written incrementally; numbers appear as they are produced.

---

## 0. PROVENANCE / INTERRUPTION NOTICE (read first)

An earlier run of this agent was **interrupted** and left partial scratch work in this
directory. This report is a *continuation*, not a clean run. Full disclosure follows.

**What exists on disk from the interrupted run:**

| File | What it is |
|---|---|
| `BUDGET.md` | Parameter budget, declared **before** any TEST touch |
| `01_ohlcv.py` | builds OHLCV panels, saves 4 pickles |
| `02_diag_train.py` | TRAIN-only liveness + IC diagnostics |
| `03_train.py` | TRAIN-only run of the 5 declared variants |
| `04_sanity.py` | weight-count / lookahead / cost-drag checks |
| `05_test.py` | **the TEST touch** |
| `train_results.json` | TRAIN results + selected winner |
| `test_results.json` | **TEST results already exist** |

### 0.1 The material disclosure: TEST has already been touched once

`05_test.py` was executed by the interrupted run and `test_results.json` is present.
**I have therefore seen TEST numbers before finishing my own work.** Per
`AGENT_BRIEF.md` §4 rule 4, this must be declared rather than hidden.

What this does and does not invalidate:

- **Still intact:** the *parameter selection*. `BUDGET.md` fixes 5 variants and a
  selection rule (max TRAIN Sharpe) **before** TEST was opened. Selection used TRAIN
  only. That chain is auditable and I re-verify it from scratch in §3.
- **Intact but no longer "pristine":** the TEST evaluation. It is a *re-evaluation of
  an already-seen number*, not a first look. To keep it honest I commit in advance
  (§0.2) that the variant evaluated on TEST is **fixed now** and will not be changed
  on the basis of anything I see.
- **What would have invalidated it:** changing the winner, adding a 6th variant, or
  re-tuning after seeing TEST. I do none of those. Parameter budget stays at 5.

### 0.2 Pre-commitment, made before I re-run anything

1. I will **adopt the 5 variants and the selection rule from `BUDGET.md` unchanged.**
   I do not add, drop, or re-spec a variant.
2. The variant that goes to TEST is **whatever TRAIN selects by the pre-declared rule**
   (max TRAIN Sharpe, tie-break Calmar then MaxDD). I re-derive that on TRAIN.
3. Whatever the TEST outcome is — including if it differs from
   `test_results.json` — **I report it as-is and do not re-select.** If my re-run
   disagrees with the stored `test_results.json`, that is a harness bug to be
   investigated and reported, not a licence to pick the better number.
4. `test_results.json` from the interrupted run is treated as **unverified** until my
   independent re-run reproduces it. Where I differ, both numbers appear.

---

## 1. The strategy

```python
@dataclass
class CmfConfig:
    period: int = 20
    upper: float = 0.1
    lower: float = -0.1
    quantity: Decimal = Decimal("1")
```

`CmfStrategy.signal()` computes Chaikin Money Flow over `period` bars:

```
MFM_t   = ((C_t - L_t) - (H_t - C_t)) / (H_t - L_t)
MFV_t   = MFM_t * V_t
CMF_t   = sum(MFV over last `period`) / sum(V over last `period`)
```

and returns a ternary signal:

| Condition | Signal | Meaning |
|---|---|---|
| `CMF > +0.10` | `+1` | long |
| `CMF < -0.10` | `-1` | short |
| otherwise | `0` | flat |

`warmup()` = `period` bars. Purely **per-symbol, time-series, price+volume**. No
lookahead in the definition: CMF at bar *t* uses only bars ≤ *t*.

**Crypto-specific?** No. CMF is a textbook price/volume oscillator from the 1970s
(Chaikin) with no funding rate, liquidation, peg, options-IV or basis dependency.
It has a well-defined NSE meaning. This is a **valid** assignment — I proceed.

**Long-only constraint:** the `-1` leg cannot be taken in an Indian delivery account.
So the short leg must be expressed either by *inverting* (long the LOW-CMF names) or
ignored. That choice is the first thing the variant budget tests.

---

## 2. Declared parameter budget — 5 variants, fixed in `BUDGET.md`

*(Adopted verbatim from `BUDGET.md`, which was written before TEST was opened.
The budget is **not** expanded here — expanding it would invalidate the run.)*

| # | period | threshold | direction | construction | purpose |
|---|--------|-----------|-----------|--------------|---------|
| **V1** | 20 | +0.10 | literal (long HIGH CMF) | momentum-126d rank among flagged | catalog strategy exactly as written |
| **V2** | 20 | +0.10 | FLIPPED (long LOW CMF) | momentum-126d rank among flagged | sign-flip motivated by negative TRAIN IC |
| **V3** | 10 | +0.10 | FLIPPED | momentum-126d rank among flagged | faster window |
| **V4** | 60 | +0.10 | FLIPPED | momentum-126d rank among flagged | slower, smoothest CMF |
| **V5** | 20 | none | FLIPPED (continuous) | cross-sectional rank of −CMF | isolates CMF alone, always fills 22 names |

**Selection rule (pre-declared):** highest TRAIN Sharpe among V1–V5. Tie-break TRAIN
Calmar, then TRAIN MaxDD (least negative). The single winner goes to TEST once,
unchanged.

**Fixed across all variants:** `PortfolioConfig()` defaults (22 names, 12% single name,
25% sector, 10% cash, 0.35 turnover budget, max 30 material names), monthly rebalance,
`CostModel(segment="delivery", slippage_bps=5)`, momentum lookback 126d. No variant
changes costs, constraints, rebalance frequency, or lookback.

**Why sign-flip variants are in the budget at all** (TRAIN-only IC, from
`02_diag_train.py`, run before any TEST touch):

| CMF period | IC vs 21d fwd return (TRAIN) | t | hit rate |
|---|---|---|---|
| 10 | −0.01509 | −3.65 | 46.7% |
| 20 | −0.02019 | −5.04 | 45.2% |
| 60 | −0.00303 | −0.72 | 48.7% |

The information coefficient is **negative and statistically significant** at 10d and
20d. The catalog's long leg (high CMF) is *anti*-predictive on TRAIN; its short leg
(low CMF) is the predictive one. A budget that explored only the literal long leg
would have tested nothing. Sign is a first-class parameter, not a detail.

*(These IC numbers are reproduced/verified in §2.1 below.)*

---

### 2.1 Budget justification — independently reproduced (TRAIN only)

`research/agent_cmf/11_train_diag.py`. Every number below is reproduced exactly from a
fresh rebuild; nothing here reads TEST.

**Information coefficient — Spearman, all names, TRAIN 2016-01-01→2023-12-31
(1,975 bars).** Negative = *low* CMF predicts *higher* forward return.

| period | 5d fwd | 21d fwd | 63d fwd |
|---|---|---|---|
| 10 | −0.01812 (t −4.62) | **−0.01509 (t −3.65)** | −0.01202 (t −2.99) |
| 20 | −0.01221 (t −3.04) | **−0.02019 (t −5.04)** | −0.01470 (t −3.58) |
| 60 | −0.00436 (t −1.06) | −0.00303 (t −0.72) | −0.01774 (t −5.04) |

The IC is **negative at all nine period/horizon combinations**. The catalog's long leg
(high CMF) is anti-predictive; its short leg (low CMF) is the predictive one. Sign is
therefore a first-class parameter and the budget is justified. Caveat stated up front:
|IC| ≈ 0.02 is small in magnitude — statistically real, economically thin.

**Liveness — fraction of TRAIN bars signalled** (coverage 95.9–96.3%):

| period | thr | long | short | either |
|---|---|---|---|---|
| 10 | +0.10 | 28.93% | 33.47% | 62.40% |
| 20 | +0.10 | 23.21% | 27.42% | 50.64% |
| 20 | +0.05 | 34.65% | 39.38% | 74.03% |
| 60 | +0.10 | 11.86% | 16.22% | 28.08% |

**Capacity:** at the catalog's +0.10 threshold the flagged set is smaller than the
22-name book on 94% (period 20) / 89% (10) / 100% (60) of monthly rebalance dates —
median 10 / 12 / 5 flagged names. Thresholded variants therefore hold materially fewer
names than permitted. That is a real property of the signal, not an artefact, and it is
reported rather than hidden.

---

---

## 3. TRAIN results

### 3.1 TRAIN results — all 5 declared variants + benchmark

`research/agent_cmf/12_train_run.py`. TRAIN 2016-01-01→2023-12-31, 1,975 bars,
48 symbols, monthly rebalance, **net of 21.92 bps** round trip
(`all_in_round_trip_bps(100_000)` = 11.92 statutory + 2 × 5 bps slippage — the figure
`run_backtest` actually charges; the 11.92 number is *not* used here).

| variant | CAGR % | Sharpe | MaxDD % | Calmar | Vol % | Turnover ×/y | Cost drag %/y | Avg names | Win % |
|---|---|---|---|---|---|---|---|---|---|
| V1_p20_t10_literal | 10.52 | 0.381 | −27.89 | 0.377 | 11.57 | 4.63 | 1.50 | 27.3 | 54.9 |
| V2_p20_t10_flipped | 15.46 | 0.654 | −32.12 | 0.481 | 13.89 | 4.67 | 1.72 | 29.6 | 57.2 |
| V3_p10_t10_flipped | 15.19 | 0.628 | −33.27 | 0.457 | 14.14 | 4.67 | 1.72 | 29.5 | 57.1 |
| V4_p60_t10_flipped | 12.03 | 0.426 | −36.63 | 0.329 | 14.43 | 4.12 | 1.25 | 13.2 | 54.4 |
| **V5_p20_continuous_flip** | **17.31** | **0.763** | −30.88 | 0.561 | 13.98 | 4.65 | 1.83 | 29.4 | 57.0 |
| *BENCH_nsealgo_composite* | *20.80* | *0.935* | *−32.92* | *0.632* | *14.70* | *2.22* | *1.05* | *21.8* | *57.7* |

**Pre-declared selection: winner = `V5_p20_continuous_flip`**, Sharpe 0.763.
Runner-up V2 at 0.654 — margin +0.109. Same winner as the interrupted run's
`train_results.json`, so the selection is robust to harness detail (I added a
400-day pre-window so the 60-day vol estimate is fully seeded, and re-annualise cost
drag over the measured window; both move levels slightly, neither moves the ranking).

**Two things already visible on TRAIN, before any TEST data:**

1. **The literal catalog strategy (V1) is the WORST of the five.** Sharpe 0.381 vs the
   composite's 0.935. As written, CMF does not work on Indian equities.
2. **Every CMF variant loses to the project's own composite** on Sharpe, Calmar *and*
   CAGR. Even the best one is −0.172 Sharpe behind.

---

### 3.2 Sanity checks (all TRAIN, `13_sanity.py`)

| # | Check | Result |
|---|---|---|
| 1 | **Look-ahead.** Scramble all prices after a cut date ×1.0→×2.5 | weights **bit-identical** (max\|Δw\| = 0.000e+00), equity bit-identical |
| 1b | Negative control: +30% on a *past* block inside the window | weights **do** move → the harness genuinely reads price history |
| 1c | CMF(20) itself invariant to the future scramble | max\|Δ\| = 0.000e+00 |
| 2 | **Weight count** | mean 29.4, median 30, **max 30** (hard ceiling `max_names=30`). Not the 48-name residual-tail failure mode |
| 2b | **Single-name cap** | max observed 0.0698 vs cap 0.12 ✓ |
| 2c | **Sector cap** | max sector 0.2250 (`it`) vs cap 0.25 ✓ |
| 2d | Invested weight | Σw mean 0.8349 = 1 − 0.10 cash buffer ✓ |
| 3 | **Signal liveness** | V1 22.3%, V2 26.4%, V3 32.2%, V4 15.6%, V5 96.2% |
| 4 | **Cost drag, gross vs net** | gross of all cost CAGR 18.37% → net 17.31%; drag 1.83%/y on 4.65× turnover. **Both gross and net positive** — the TRAIN result is not a cost artefact |
| 4b | Cost ladder | 11.92 → 17.79%, 21.92 → 17.31%, 31.92 → 16.83%, 41.92 → 16.35%. Monotone, no cliff |
| 5 | **Plausibility** | best variant 17.31% vs unlevered long-only ceiling 40–50%. No bug |
| 6 | Is V5 really CMF? | see §3.3 |
| 7 | Decomposition | see §3.3 |

**On the 29.4 average names (brief check #2).** The book drifts from the 22 target to
~29 because the 0.35 turnover budget *blends* toward each new target rather than
replacing it, and `_thin` then admits up to `max_names=30` material names. That is
`engine.apply_turnover_budget` / `engine._thin` behaving as designed, **not** an
indexing bug and **not** a bypass of `PortfolioConfig`. The failure mode the brief
warns about — an accumulating residual tail reaching 48 — does not occur, and the
30-name limit is asserted, not assumed.

### 3.3 The most important diagnostic: "CMF" here is really 20-day reversal

Daily cross-sectional Spearman correlation on TRAIN:

| | V5 (−CMF rank) | mom 12-1 | mom 6m | trend 200d | reversal 20d | composite |
|---|---|---|---|---|---|---|
| **V5 (−CMF rank)** | — | −0.010 | −0.223 | −0.349 | **+0.647** | −0.173 |

And running the project-side factors through the *same* engine on TRAIN:

| factor (diagnostic, not a budget variant) | CAGR % | Sharpe | MaxDD % |
|---|---|---|---|
| V5 (−CMF rank) | 17.31 | 0.763 | −30.88 |
| **reversal_20d alone** | **18.80** | **0.843** | −31.97 |
| reversal_5d alone | 17.21 | 0.771 | −30.46 |
| momentum_6m alone | 17.89 | 0.747 | −34.92 |

**Plain 20-day reversal beats V5 on TRAIN** (Sharpe 0.843 vs 0.763), and V5 correlates
+0.647 with it. So V5's TRAIN "edge" is a **short-term reversal effect wearing a
Chaikin money-flow costume**, not a money-flow effect.

This matters because `src/nsealgo/factors/core.py` already documents, from
methodologically disjoint sources, that reversal does **not** work in Indian cash
equities: Sehgal & Jain (2011) and IIMC (2020) find short-term *continuation*; the
only multiple-testing-corrected Indian technical study (Romano-Wolf, 2015–2025) found
7 of 8 surviving rules were trend-following while RSI/Bollinger mean-reversion all
failed (adjusted p 0.071–0.473). The project's own module keeps `reversal_20d` only as
a labelled **negative control**.

I therefore predict, before looking at TEST, that V5 will not survive out-of-sample.
That prediction is recorded here, before the TEST touch, so the TEST result cannot be
rationalised after the fact.

---

## 4. TEST results — 2024-01-01 → 2026-10-01 (685 bars, 2.81 years)

`research/agent_cmf/14_test.py`. Warmup from 2023-07-01 (TRAIN data) so the book is
invested on the first TEST bar. **Net of 21.92 bps** round trip throughout.
The variant evaluated is `V5_p20_continuous_flip`, fixed by the TRAIN-only rule in
§0.2 before this file was written, and run **unchanged**.

| | **CMF V5 (strategy)** | buy-and-hold | nsealgo composite | reversal_20d *(diag)* |
|---|---|---|---|---|
| CAGR | **5.40%** | 8.15% | 8.10% | 8.01% |
| Sharpe | **−0.055** | 0.184 | 0.180 | 0.189 |
| MaxDD | **−12.26%** (110d) | −15.87% | −14.84% | −11.62% |
| Calmar | **0.441** | 0.513 | 0.546 | 0.690 |
| Vol | 9.34% | 13.42% | 13.41% | 10.94% |
| Turnover | 3.96 ×/y | — | 2.03 ×/y | 4.19 ×/y |
| Cost drag | 1.04%/y | — | 0.56%/y | 1.12%/y |
| Avg names | 27.4 | — | 21.4 | 28.7 |
| Win rate | 49.2% | 54.0% | 53.6% | 53.0% |
| Total return | 15.92% | 24.59% | 24.44% | 24.16% |

Calendar years: **2024 +17.9%, 2025 +10.1%, 2026 −10.5%** (67% positive).

### 4.1 TEST vs buy-and-hold

- **Return: worse by 2.74 pp/yr** (5.40% vs 8.15%). Total return 15.9% vs 24.6%.
- **Sharpe: worse by 0.24** (−0.055 vs 0.184). The strategy's Sharpe is **negative**,
  i.e. it underperformed the 6.5% Indian T-bill proxy that `compute_metrics` subtracts.
  Its 5.40% CAGR is **below the risk-free rate**.
- **Drawdown: better by 3.62 pp** (−12.26% vs −15.87%). This is the one axis it wins,
  and it is an accident of being under-invested and diversified (27 names, 9.3% vol vs
  buy-and-hold's 13.4% vol), not a source of return.
- Net verdict on the pair: **worse**. It gave up 2.74 pp/yr of return and
  24 Sharpe basis points to buy 3.62 pp of drawdown protection — a bad trade at any
  reasonable risk aversion, and Calmar confirms it (0.441 vs 0.513).

### 4.2 Random-signal control (negative control)

300 seeds of a random cross-sectional rank, same book occupancy, same caps, same
turnover budget, same costs, zero information:

| | random | CMF V5 |
|---|---|---|
| CAGR mean | 5.44% (sd 1.48, p05 2.81%, p95 7.66%) | **5.40%** |
| Sharpe mean | −0.04 (sd 0.13, p95 0.16) | **−0.055** |
| MaxDD mean | −13.37% | −12.26% |

CMF beats 49.0% of seeds on CAGR (p = 0.490) and 43.0% on Sharpe (p = 0.430).

**It does not beat a coin flip.** A random ranking earns 5.44% CAGR; CMF earns 5.40%.
The observed TEST edge is indistinguishable from zero, and the Sharpe comparison
actually favours the random book.

### 4.3 Did it beat the nsealgo composite?

**No, on every axis except drawdown.** CAGR 5.40% vs 8.10% (−2.70 pp), Sharpe −0.055 vs
0.180 (−0.235), Calmar 0.441 vs 0.546. The composite is also *cheaper to hold*
(0.56%/y drag vs 1.04%/y) because it turns over at 2.03 ×/y against CMF's 3.96 ×/y.
The composite's own TEST Sharpe (0.180) is close to buy-and-hold's (0.184) — worth
noting separately, but outside this agent's scope.

### 4.4 The reversal hypothesis, confirmed out-of-sample

The §3.3 TRAIN diagnostic predicted failure because V5 is 20-day reversal in disguise.
TEST confirms it: `reversal_20d` alone scores Sharpe **0.189** on TEST versus V5's
**−0.055**, and beats it on CAGR (8.01% vs 5.40%). The factor CMF was tracking is a
documented non-edge in Indian equities, and the strategy inherits that.

### 4.5 Reconciliation with the interrupted run

My independent re-run reproduces the interrupted run's `test_results.json` to three
decimals on every metric that matters:

| | mine | interrupted | diff |
|---|---|---|---|
| CAGR % | 5.404 | 5.403 | +0.001 |
| Sharpe | −0.055 | −0.055 | 0.000 |
| MaxDD % | −12.257 | −12.257 | −0.000 |
| Calmar | 0.441 | 0.441 | 0.000 |
| avg names | 27.449 | 27.124 | +0.325 |
| turnover ×/y | 3.957 | 3.914 | +0.044 |
| cost drag %/y | 1.035 | 1.127 | −0.092 |
| buy-and-hold CAGR % | 8.146 | 8.163 | −0.016 |
| composite CAGR % | 8.100 | 8.100 | 0.000 |

The residual differences are harness details, not disagreements: I seed the 60-day
vol window with 400 days of pre-window history (the interrupted run used ~6 months),
and I measure turnover and cost drag **strictly inside** the TEST window rather than
over the engine's whole warmup span. Signs and conclusions are identical.

---

## 5. VERDICT

**Does the Chaikin Money Flow strategy make money on NSE NIFTY-50? No.**

Out-of-sample it earns 5.40% CAGR at a **negative** Sharpe of −0.055, against
buy-and-hold's 8.15% / +0.184. It is statistically indistinguishable from a random
signal (p = 0.49 on CAGR, p = 0.43 on Sharpe), and its 5.40% CAGR is below the 6.5%
risk-free proxy. Worse, it **loses to the project's own composite by 2.70 pp/yr of
CAGR** while costing twice as much to hold.

Three things make this unambiguous rather than merely disappointing:

1. **The catalog strategy as written (V1, long high CMF) is the worst of the five
   TRAIN variants** — Sharpe 0.381 vs the composite's 0.935. It was never going to
   work. The TRAIN information coefficient was negative at all nine period/horizon
   combinations, so the sign was wrong from the start.
2. **Inverting the sign does not rescue it.** The best TRAIN variant (V5) is the
   inverted one, and it still loses out-of-sample. There is no direction in which
   "CMF ranks cross-sectionally" beats noise here.
3. **The TRAIN edge was borrowed, not earned.** V5 correlates +0.647 with 20-day
   reversal, and plain `reversal_20d` *beats* V5 on both TRAIN (0.843 vs 0.763) and
   TEST (0.189 vs −0.055). CMF added no information beyond a reversal bet that the
   project has already documented as non-working in India.

### 5.1 Most likely reason

**CMF is not an alpha factor; on Indian daily equity bars it is a noisy proxy for
short-term reversal.** Chaikin money flow measures where the close sits within the
bar's range, weighted by volume — structurally close to a 1-bar reversal signal. The
TRAIN IC was negative and significant, so the "money flow predicts" intuition inverts
into "recently-sold names bounce", which is exactly the reversal premium that Sehgal &
Jain (2011), IIMC (2020) and the Romano-Wolf multiple-testing study all fail to find in
Indian equities. A +0.02 TRAIN IC is far too small to survive a regime change, and
2026 (−10.5%) shows exactly that.

### 5.2 The one thing I would try next

**Stop treating CMF as a standalone long-only tilt, and test it as a *sizing overlay*
on the momentum composite** — i.e. use CMF only to scale position size *within* names
the composite already selects, rather than to pick names itself. The evidence
supporting that specific next step: the composite and CMF are nearly orthogonal
(Spearman −0.173) yet V5 lost to the composite by 0.235 Sharpe while costing 2× the
turnover, which says CMF's rank is adding noise and cost without adding information.
If it carries any signal at all, conditioning should extract it; as a standalone
selector it demonstrably cannot.

I have **not** run that experiment — it would be a 6th variant and would invalidate
this run. It is named as the next step only.

---

## 6. Honest caveats

- **TEST was touched once by the interrupted run before I got here**, and I have seen
  its numbers. Disclosed in §0.1. The *selection* remains clean (TRAIN-only,
  pre-declared rule, same winner reproduced); the TEST *evaluation* is a re-evaluation
  of a seen number rather than a first look. §0.2 lists what I committed to in advance
  and I did not change the variant, add a variant, or re-tune.
- **Parameter budget respected: 5 variants, exactly as pre-declared.** No sixth was
  run. The reversal rows in §3.3 and the `reversal_20d` column in §4 are labelled
  **diagnostics** and cannot change selection, which was fixed at §0.2.
- **Survivorship bias is present** — the universe is today's NIFTY-50 backfilled to
  2008. Disclosed per the brief. It inflates all four rows in §4 equally and so does
  not rescue the strategy.
- **Data ends 2026-10-01**; the TEST window is 2.81 years and contains one full
  regime cycle plus a partial one. 685 bars is a thin basis for a 0.05 Sharpe
  difference — but it is enough to reject a strategy that loses to both buy-and-hold
  and a random ranking, which is what happened here.
- **The averaging in TEST is favourable to the strategy**, not the reverse: 6-month
  trend-following was strong in 2024–25 and the strategy is long-only and always fully
  invested. It still lost. The result is not rescued by "wrong regime".
- `CostModel` charges `all_in_round_trip_bps` against **one-way** turnover
  (`engine.py:412-431`), which is conservative — it double-counts relative to a real
  buy+sell cycle. I have not adjusted for it, because `AGENT_BRIEF.md` §3 forbids
  reducing costs to rescue a result. Every number here is therefore a slight
  *under*statement of CMF's viability, in the wrong direction to help it.

## 7. Bugs and defects found along the way

Per `AGENT_BRIEF.md` §8.3. Two in `src/`, the rest in my own scratch work.

| # | Where | What |
|---|---|---|
| B1 | `src/nsealgo/costs.py:127` | `CostModel._enabled` is declared as a dataclass field but **never read anywhere** in the repo. It reads as a cost kill-switch that does nothing. Dead field, misleading intent. (Not fixed — `src/nsealgo/**` is out of bounds for this brief.) |
| B2 | my scratch work, `13_sanity.py` | `w.groupby(grouper_series)` where `w` has a `DatetimeIndex` and the grouper has a **symbol** index: pandas aligns the grouper to `w.index`, yields **zero groups**, and the sector-cap assertion passes **vacuously** with `max sector weight = 0.0000`. Fixed by grouping `w.T` and asserting the group count. Worth flagging because "cap check passes" is exactly the kind of check that hides a bug. |
| B3 | my scratch work, `13_sanity.py` | Look-ahead negative control perturbed `past.iloc[:1000]`, which lies **outside** the `warm:cut` slice the backtest actually reads — so a real harness would also have "passed". The control was meaningless. Fixed to perturb a block inside the used window. |
| B4 | my scratch work, `13_sanity.py` | `pd.concat([a, b]).corr(method="spearman").iloc[0,1]` on two panels sharing column labels returns garbage (duplicate labels). Produced a table of implausible constant values before I caught it. Fixed with an explicit numpy rank correlation. |
| B5 | my scratch work, `cmflib.py` | `metrics_on` derived window turnover by rescaling `res.metrics.annual_turnover` by a year ratio. That is **wrong**: the engine's annual turnover divides by a span starting ~400 days before the window, so its numerator includes out-of-window turnover. It inflated TEST turnover to 5.44 ×/y and cost drag to 1.68%/y. Correct window-exact values are **3.96 ×/y** and **1.035%/y**. Also, the first version fed `res.returns` (post-cost) into a gross-return replay. Both fixed and cross-validated against an independent panel-based replay (1.032 vs 1.035 %/y). |
| B6 | my scratch work, `11_train_diag.py` | `DataFrame.stack(dropna=...)` is removed/behaviour-changed in pandas 3 — the project's venv is on 3.14. Any new research code using it will break. |

## 8. Reproduction

```bash
cd /home/ph03n1x/trade
.venv/bin/python research/agent_cmf/10_verify_panels.py   # rebuild + verify panels, CMF parity
.venv/bin/python research/agent_cmf/11_train_diag.py      # TRAIN liveness + IC
.venv/bin/python research/agent_cmf/12_train_run.py       # TRAIN, 5 variants, selection
.venv/bin/python research/agent_cmf/13_sanity.py          # lookahead / caps / costs / decomposition
.venv/bin/python research/agent_cmf/14_test.py            # THE TEST TOUCH + controls
.venv/bin/ruff check research/agent_cmf/cmflib.py research/agent_cmf/1[0-4]_*.py
```

No commits made. `src/nsealgo/**`, `src/cryptobot/**`, `GOAL.md` and `reports/` untouched.

---

## 9. Files

| File | Role |
|---|---|
| `BUDGET.md` | pre-declared 5-variant budget + selection rule (from the interrupted run) |
| `REPORT.md` | this report |
| `cmflib.py` | shared verified harness (signal, window-exact turnover/drag, metrics) |
| `10_verify_panels.py` … `14_test.py` | the pipeline above |
| `v_*.pkl` | OHLCV panels rebuilt and verified from `data/nse` |
| `v_train_results.json`, `v_test_results.json` | my results |
| `01_*.py` … `05_test.py`, `_*.pkl`, `train_results.json`, `test_results.json` | artefacts of the interrupted run, left in place; superseded by `v_*` but retained for the §4.5 reconciliation |
