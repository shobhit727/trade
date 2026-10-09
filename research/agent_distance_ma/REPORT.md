# `distance_moving_average` on NSE NIFTY-50 — TEST-window result

**Verdict: NO. This strategy does not make money on NSE.** It returned **+1.21% CAGR
(Sharpe −0.50)** out-of-sample against buy-and-hold's **+10.79% (Sharpe +0.38)**, was
**1.33 pp worse on drawdown**, and performed **worse than a random coin flip with the
same exposure**.

Run date 2026-10-07. Data `data/nse/*_1d.csv`, cleaned by `load_universe`. All figures
net of the full Indian delivery stack (**21.92 bps** all-in round trip: 11.92 statutory
+ 2×5 bps slippage) at ₹1,00,000/position.

---

## 1. The strategy and the long-only translation

```python
dev = (close - sma(close, period)) / sma(close, period)
dev >  +threshold  ->  -1        # short   (price stretched ABOVE its MA)
dev <  -threshold  ->  +1        # long    (price stretched BELOW its MA)
```

A pure mean-reversion rule. **The `-1` leg was discarded, not inverted** — an Indian
delivery account cannot short. So the tested rule is one half of the source strategy:

> Buy when the close is more than `threshold` below its `period`-day SMA.

The book is long-only and cross-sectional, so signalled names are ranked by how far
below the MA they sit and the engine buys the deepest. All 5 declared variants are
listed in `DECLARED_BUDGET.md`, written before any backtest ran.

## 2. Declared parameter budget (exactly 5, none exceeded)

| # | construction | period | threshold |
|---|-------------|--------|-----------|
| V1 | dev_depth | 20 | 0.03 *(source defaults)* |
| V2 | dev_depth | 20 | 0.05 |
| V3 | dev_depth | 50 | 0.05 |
| V4 | dev_depth | 100 | 0.08 |
| V5 | mom_ranked (gate + 126d momentum rank) | 20 | 0.03 |

Selection rule, fixed in advance: **highest TRAIN Sharpe net of costs**. That picked
**V3**, which was then run unchanged on TEST.

## 3. TRAIN results (2016-01-01 → 2023-12-31) — the selection window

| variant | CAGR | Sharpe | MaxDD | invested |
|---------|------|--------|-------|----------|
| V1 | 9.51% | 0.27 | −30.02% | 49.5% |
| V2 | 5.78% | 0.00 | −30.90% | 26.9% |
| **V3 ← selected** | **11.69%** | **0.44** | −30.63% | 41.4% |
| V4 | 9.75% | 0.30 | −29.52% | 32.8% |
| V5 | 8.03% | 0.18 | −32.74% | 46.8% |
| *nsealgo composite* | 21.14% | 0.96 | −32.92% | 89.1% |
| *buy-and-hold (EW 22)* | 19.28% | 0.80 | −33.68% | — |

**The warning sign was visible in-sample.** Best variant 11.69% vs market 19.28%:
already ~7.6 pp/yr behind before TEST was opened. And on TRAIN it beat a random
signal only 0.44 vs 0.38 — statistically indistinguishable from a coin flip.

## 4. TEST results (2024-01-01 → 2026-10-01) — 685 bars, 2.81 years

### Headline: V3 `dev_depth p50 t0.05`, TRAIN-selected, unchanged

| metric | strategy | buy-and-hold (EW 22) | composite |
|--------|---------:|---------------------:|----------:|
| **CAGR** | **1.21%** | **10.79%** | 1.99% |
| Sharpe | **−0.50** | +0.38 | −0.31 |
| Sortino | −0.68 | — | — |
| MaxDD | **−15.19%** | −13.86% | −14.94% |
| Calmar | 0.08 | 0.78 | 0.13 |
| Turnover/yr | 3.11x | 0.00x | 2.43x |
| Cost drag/yr | 0.71% | ~0.02% | 0.57% |
| Avg names held | 15.1 | 22 | ~22 |
| Avg invested | 48.5% | 90% | ~89% |

- Return: **−9.58 pp/yr worse** (−29.89 pp cumulative: 3.43% vs 33.32%)
- Drawdown: **worse by 1.33 pp** — no protection offered
- Calendar years: 2024 −0.37%, 2025 +11.13%, 2026 −6.58%
- Costs paid: **₹41,721** on a ₹21,00,000 book

### All 5 declared variants on TEST

| variant | CAGR | Sharpe | MaxDD | Calmar |
|---------|------|--------|-------|--------|
| V1 dev_depth p20 t0.03 | 2.48% | −0.39 | −12.77% | 0.19 |
| V2 dev_depth p20 t0.05 | 2.56% | −0.57 | −8.94% | 0.29 |
| **V3 dev_depth p50 t0.05** | **1.21%** | **−0.50** | −15.19% | 0.08 |
| V4 dev_depth p100 t0.08 | 0.28% | −0.63 | −15.29% | 0.02 |
| V5 mom_ranked p20 t0.03 | −0.05% | −0.73 | −12.77% | −0.00 |

**All five are negative-Sharpe out-of-sample.** The strategy's best TEST variant (V2,
2.56%) is still ~8 pp/yr behind buy-and-hold. There is no version of this grid that
works. Note V5 — the brief's recommended momentum-ranked construction — is the *worst*
of the five, which says the momentum overlay was not what rescued or sank the others.

## 5. Negative control — the strategy is worse than a coin flip

Random signal, same 14.87% of name-days long, identical costs, constraints and
rebalance schedule:

| control | TRAIN Sharpe | TEST Sharpe | TEST CAGR |
|---------|-------------:|------------:|----------:|
| strategy V3 | 0.44 | **−0.50** | 1.21% |
| random (mean of 3 seeds) | 0.38 | **−0.24** | 3.54% |
| verdict | barely above | **below** | — |

In-sample it scraped past a coin flip by 0.06. Out-of-sample it is 0.26 Sharpe units
*behind* one. **This fails the minimum bar in brief §6.5.**

## 6. Did it beat the nsealgo composite? No

TEST: strategy 1.21% / −0.50 vs composite 1.99% / −0.31. Worse on both. (Both are poor
on this particular TEST window — 2.81 years in which the equal-weight market managed
only ~11%/yr — but the composite is the less bad of the two.)

For calibration, the literature-cited mean-reversion negative control
(`NEGATIVE_CONTROL_WEIGHTS`, reversal_5d/20d + low-vol) got 7.14% / 0.11 on TEST —
*better than my strategy*. A textbook reversal blend beat the Bollinger-style band
rule.

## 7. Why it failed — diagnosis

**The signal's average is fine; the way the strategy trades it is not.**

Raw forward returns after a long signal (TEST, unconditional, unweighted):

| horizon | after signal | universe | excess |
|---------|-------------:|---------:|-------:|
| 5d | +0.380% | +0.192% | +0.19 pp |
| 21d | +1.191% | +0.857% | +0.33 pp |

A naive long-everything-signalled sleeve *would* have beaten the market. The strategy
captures none of that. Two compounding reasons:

**(a) The book cannot be filled — a structural mismatch, not a bad signal.**
The gate fires on only 14.9% of name-days, and the *median firing bar has 6 of 48
names signalled*. Against `PortfolioConfig`'s 12% single-name cap, 6 names can hold at
most 72%, so the book sits at **48.5% invested on average**, with 34% of TEST bars
under 25% invested. The strategy is structurally half-cash.

**(b) It buys the wrong end of its own signal.**
Splitting signalled name-days into quintiles of deviation depth (TEST, 21d forward):

| quintile | mean fwd 21d | vs universe |
|----------|-------------:|------------:|
| Q1 shallowest | +1.246% | +0.39 pp |
| Q2 | +0.797% | **−0.06 pp** |
| Q3 | +1.356% | +0.50 pp |
| Q4 | +1.344% | +0.49 pp |
| Q5 deepest | +1.213% | +0.36 pp |

**The relationship is non-monotonic and essentially flat.** The strategy ranks by
deviation depth and buys Q5; Q5 is statistically indistinguishable from Q1. The
"distance" component — the entire identity of this strategy — carries no ordering
information.

**Decomposition of the TEST return:**

| term | annualised |
|------|-----------:|
| sleeve gross return (per unit of capital at work) | +4.79% |
| market (EW 22) | +10.99% |
| **selection term** | **−6.21%** |
| **cash term** (1 − 48.5% invested) | **−2.46%** |
| implied gross CAGR | +2.32% *(actual gross 1.90% ✓)* |

So: half the loss is the sleeve picking worse names than the market, and half is the
half-empty book. Costs (−0.71%/y) are real but **not** the cause — at zero cost the
strategy still returns only 1.52%.

**Cost stress** (GOAL.md §5 Gate 4), TEST:

| model | CAGR | Sharpe | drag/yr |
|-------|-----:|-------:|--------:|
| base | 1.21% | −0.50 | 0.71% |
| 2× slippage | 0.89% | −0.53 | 1.03% |
| 3× slippage | 0.58% | −0.56 | 1.34% |
| zero cost | 1.52% | −0.46 | 0.39% |

The result does not depend on the cost assumption. **It is not a cost problem.**

## 8. Sanity checks (brief §6) — all pass, the failure is real

| check | result |
|-------|--------|
| §6.1 plausibility | 1.21% CAGR — plausible; no lookahead, no compounding bug |
| §6.2 weight count | 15.1 names, not 48 — no residual accumulation |
| §6.3 liveness | 14.87% of name-days long — above the 5% floor, not always-flat |
| §6.4 cost drag | gross 1.90% → net 1.21%; reported, and ruled out as the cause |
| §6.5 random control | **FAILS** — below a coin flip out-of-sample |

**No lookahead:** every factor on row *t* uses closes through *t* only (trailing
rolling mean); `run_backtest` holds weights decided on *t* from *t+1*.

## 9. PROTOCOL COMPLIANCE

- TRAIN (2016-01-01→2023-12-31) and TEST (2024-01-01→2026-10-01) split respected.
- **TEST was opened exactly once**, after V3 was selected on TRAIN Sharpe. All
  parameter selection used TRAIN only.
- **Parameter budget: 5 declared, 5 run. Not exceeded.** The other four variants'
  TEST numbers are shown in §4 as a disclosure of the already-declared budget; none
  was added after seeing any TEST result.
- Costs are the mandated `CostModel(segment="delivery", slippage_bps=5)`; no cost was
  reduced to rescue a result. The zero-cost row is a stress test, explicitly labelled.
- Survivorship bias is present in the panel (today's NIFTY-50 backfilled) and is
  disclosed. It applies equally to the strategy and both benchmarks, so it does not
  change the comparison.
- **Survivorship bias is a live caveat but is not the explanation here**: the strategy
  loses to buy-and-hold and to a coin flip *in the same biased panel*, so the bias
  cancels out of the comparison.
- All results are quoted to **2026-10-01**.

## 10. Most likely reason, and the one thing to try next

**Most likely reason:** mean reversion is the wrong sign in Indian equities, and
`nsealgo/factors/core.py` had already recorded the evidence before this run —
`reports/FACTOR_EVIDENCE.md` cites a multiple-testing-corrected study of Indian
technical rules in which 7 of 8 surviving configurations were trend-following, while
RSI_25_75, RSI_30_70, Bollinger_20/2.0 and Bollinger_20/2.5 all failed. This strategy
is a one-sided Bollinger-band rule. It is a documented negative control that got
promoted to a candidate. The TRAIN forward-return edge (+0.60 pp excess over 21d)
was real but small, and it did not survive — TEST excess was +0.33 pp, and the way
the strategy ranks its own signals is non-monotonic, so there was no edge left to
monetise even in principle.

**The one thing I would try next:** *not* another threshold. Retune the band width.
The two findings that actually cost money are (a) the half-empty book and (b) depth
ranking being flat. Test whether a **breadth-relative** version of the same idea
survives — on each bar, buy the most-below-MA names *within the set of names that are
below their MA*, forcing a full book rather than a sparse one — and only then keep it
if it beats the random control. If a breadth-forced band rule still loses to a coin
flip, that closes the family and mean reversion should be retired for this universe.
I would **not** spend further budget on `(period, threshold)` pairs: V1–V4 already span
a 5× range of period and 2.7× of threshold, and all four are negative-Sharpe on TEST.

---

### Reproduction

```bash
cd research/agent_distance_ma
../../.venv/bin/python step0_data.py          # data audit + cost calibration
../../.venv/bin/python step1_signal_diag.py   # liveness, before any backtest
../../.venv/bin/python step2_train.py         # 5 variants on TRAIN -> selection
../../.venv/bin/python step3_test.py          # the single TEST run + controls
../../.venv/bin/python step4_diagnose.py      # decomposition, depth quintiles
```

`TEST_RUN.txt` holds the verbatim TEST output. No file outside
`research/agent_distance_ma/` was modified. Nothing committed.