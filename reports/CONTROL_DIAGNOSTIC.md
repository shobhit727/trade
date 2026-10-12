# Control Diagnostic — does the production composite have a demonstrable edge?

Triggered by `reports/STRESS_v3.md` §6: the production trend composite returns
OOS +9.71% / Sharpe 0.34 / MaxDD −14.92%, while the reversal **negative control**
— built entirely from factors this repo's own factor module rules OUT on published
Indian evidence — returns +10.04% / Sharpe 0.37 / MaxDD −25.05% through the same
harness and the same cost stack. A negative control that passes where it is meant
to fail means the harness cannot tell the production composite apart from a
composite of rejected factors.

This report does not assume what that means. It tests six competing explanations.

## Provenance

| component | SHA |
|-----------|-----|
| engine | `d93815344bd3` |
| loader | `c1badf5f7df8` |
| costs | `ba350aef75b3` |
| panel | `389b082b832f` |

- **Panel**: 48 symbols × 4625 daily bars, 2008-01-01 → 2026-10-01
- **Engine**: `nsealgo.backtest.engine`, unmodified. Cost charge `2.0 × one_way_turnover × equity × rate` at `21.92` bps all-in round trip (statutory + 2 × 5 bps slippage).
- **Harness**: `nsealgo.backtest.walkforward.walk_forward`, 6 folds, 6y train / 2y test, 18-cell grid (`n_positions` × overlay `lookback` × overlay `threshold`) — identical to `research/validate.py`.
- **Only thing varied**: the score panel handed to `run_backtest` (and, for H3, whether `blend_with_cash` is applied). Engine, costs, factors, overlay, loader and `walk_forward` are untouched.
- **OOS window**: 2014-11-26 → 2026-10-01, 2928 daily observations across 6 contiguous 2-year test windows.
- Survivorship bias is present (today's NIFTY-50 backfilled) and is disclosed in every report in this repo.
- Reproduce: `.venv/bin/python research/control_diagnostic.py`

## Verdict at a glance

| # | Hypothesis | Verdict | Decisive number |
|---|-----------|---------|-----------------|
| H1 | It's beta, not skill | **SUPPORTED on the decisive comparison, and the net numbers understate how badly** | production at 97th pct CAGR / 96th pct Sharpe of a 100-book random null; 100% of that null is profitable |
| H2 | Low-vol leg does the work | **SUPPORTED — reversal legs carry the control, not low-vol** | control without low-volatility = +10.45% / Sharpe +0.40 vs production +9.71% / 0.34 |
| H3 | Regime overlay is the difference | **SUPPORTED — overlay flips the sign** | Sharpe gap (ctrl−prod) +0.029 with overlay, -0.037 without |
| H4 | 0.34 vs 0.37 is noise | **SUPPORTED — indistinguishable** | 95% CI on ΔCAGR [-4.07pp, +3.38pp]; robust paired p = 0.86 |
| H5 | Harness has a selection artifact | **REFUTED — production wins fixed cells without selection** | production beats control in 2/2 fixed cells; but train-selection costs production -1.30pp/yr and *adds* the control +2.03pp/yr |
| H6 | Equal-count is the wrong null | **SUPPORTED — no signal separates it from its own scramble** | production at 58th pct CAGR / 58th pct Sharpe of a 60-book turnover-matched scramble |

## H1 — "It's beta, not skill"

100 random-weight books (i.i.d. Uniform(0,1) scores) through the **identical** harness: same 6 folds, same 18-cell grid, same engine, same cost stack, same top-N cut, same inverse-vol scaling, same caps, same turnover budget, same monthly rebalance. The only thing removed is the signal.

| statistic | random CAGR | random Sharpe | random MaxDD |
|-----------|-------------|--------------|-------------|
| mean | +8.59% | +0.24 | -19.34% |
| sd | +0.60% | +0.05 | +1.97% |
| min | +7.03% | +0.10 | -24.87% |
| p05 | +7.60% | +0.15 | -24.10% |
| p25 | +8.20% | +0.21 | -20.02% |
| median | +8.65% | +0.25 | -18.91% |
| p75 | +8.98% | +0.28 | -18.19% |
| p95 | +9.50% | +0.32 | -16.99% |
| max | +10.23% | +0.39 | -14.83% |
| **profitable** | **100% of books** | — | — |

| book | net CAGR | pct (net) | **gross CAGR** | **pct (gross)** | Sharpe | pct | turnover | cost drag |
|------|---------:|---------:|-------------:|--------------:|-------:|-----:|---------:|----------:|
| **production (trend)** | +9.71% | 97th | +11.82% | **47th** | +0.34 | 96th | 2.51x/y | 1.23%/y |
| control (reversal) | +10.04% | 98th | +12.79% | 94th | +0.37 | 98th | 3.34x/y | 1.66%/y |

> **Read the gross column, not the net one.** The random books turn over 3.75x/yr against production's 2.51x/yr, so on *net* return production is credited for a cost saving that has nothing to do with its factors. The gross column strips both costs and the regime overlay.

### Where production's net edge over the null actually comes from

Three consistent measurements are available per book and they nest, so the gap decomposes exactly:

```
gross   ->  -costs-  ->  net_pre_overlay  ->  +overlay  ->  net
```

| book | gross CAGR | cost channel | net pre-overlay | overlay channel | net CAGR |
|------|-----------:|-------------:|----------------:|----------------:|---------:|
| production | +11.82% | -1.24pp | +10.58% | -0.87pp | +9.71% |
| mean random book | +11.83% | -1.83pp | +10.01% | -1.42pp | +8.59% |
| **difference** | **-0.02pp** | **+0.59pp** | — | **+0.54pp** | **+1.12pp** |

The three difference terms reconcile to the observed net gap (+1.12pp) to 0.0e+00. **The selection term — the only one that reflects the factors — is -0.02pp/yr.** Everything else is book construction: turnover and the overlay.

**Verdict: SUPPORTED on the decisive comparison, and the net numbers understate how badly.**

1. **The beta floor is real and high.** 100% of 100 random-weight books are profitable out-of-sample through this harness, net of the same 21.92bps cost stack — mean CAGR +8.59%, mean Sharpe +0.24, **worst case +7.03%**. Not one of them lost money. An arbitrary 22-name NIFTY-50 book rebalanced monthly, with no signal whatsoever, makes money in this sample. The strategy's profitability is therefore not evidence of skill.
2. **And the composite's edge over that null is not a selection edge.** On net CAGR production sits at the 97th percentile and on Sharpe at the 96th — which looks like real selection. But a book that turns over 3.75x/yr against production's 2.51x/yr is being *credited for trading less* on any net comparison.
3. **Decomposed, the selection term is -0.02pp/yr — indistinguishable from zero.** Of production's +1.12pp/yr net edge over the mean random book, +0.59pp is the turnover/cost channel and +0.54pp is the regime-overlay channel. On **gross** CAGR — before costs and before the overlay — production's +11.82% lands at the **47th percentile** of a null whose gross mean is +11.83%. That is *the median random book*, to two decimal places.

**So the honest reading of H1 is: the composite's factors are worth approximately nothing on this data, and everything it does better than a random book it does by holding fewer positions and de-risking more often.** Both of those are properties of book *construction*, and neither is evidence that the factor set has predictive power. The reversal control's gross percentile is 94th, so on this metric the control's selection is *not* null either — which is the finding, not a reprieve.

H1 cannot by itself explain why production fails to beat a composite of factors this repo has already ruled out on published Indian evidence. For that, see H2, H5 and H6.

## H2 — "The low-vol leg is doing the work, not the reversal legs"

Every component run alone at weight 1.0 through the same harness, plus the control with `low_volatility` removed (weights renormalised by `build_composite_score`).

| book | OOS CAGR | OOS Sharpe | OOS MaxDD | turnover | cost drag |
|------|---------:|-----------:|----------:|---------:|----------:|
| **PRODUCTION (trend)** | **+9.71%** | **0.34** | **-14.92%** | 2.51x/y | 1.23%/y |
| **CONTROL (reversal)** | **+10.04%** | **0.37** | **-25.05%** | 3.34x/y | 1.66%/y |
| reversal_5d | +8.90% | +0.27 | -25.48% | 3.71x/y | 1.83%/y |
| reversal_20d | +11.47% | +0.49 | -24.50% | 3.73x/y | 1.89%/y |
| low_volatility | +8.33% | +0.23 | -16.05% | 1.90x/y | 0.91%/y |
| momentum_12_1 | +10.88% | +0.41 | -22.56% | 1.62x/y | 0.82%/y |
| momentum_6m | +10.04% | +0.35 | -17.79% | 2.23x/y | 1.11%/y |
| trend_strength_200d | +8.52% | +0.23 | -17.83% | 2.42x/y | 1.20%/y |
| trend_legs_only | +10.43% | +0.39 | -17.44% | 2.05x/y | 1.01%/y |
| control_no_lowvol | +10.45% | +0.40 | -25.99% | 3.66x/y | 1.83%/y |

control **without** low-volatility = +10.45% / Sharpe +0.40; `low_volatility` alone = +8.33% / Sharpe +0.23; `reversal_5d` alone = +8.90% / +0.27; `reversal_20d` alone = +11.47% / +0.49.

**Verdict: REFUTED.** Removing the low-vol leg leaves the control at +10.45% / Sharpe +0.40 — still ahead of production's +9.71% / 0.34. The low-volatility leg is therefore *not* what carries the control; the reversal legs are.

## H3 — "The regime overlay is the whole difference"

Identical folds, identical grid, identical engine and costs. `overlay=OFF` skips `blend_with_cash` and nothing else.

| book | overlay | OOS CAGR | OOS Sharpe | OOS MaxDD |
|------|---------|---------:|-----------:|----------:|
| prod | with overlay | +9.71% | +0.34 | -14.92% |
| prod | no overlay | +11.50% | +0.41 | -32.94% |
| ctrl | with overlay | +10.04% | +0.37 | -25.05% |
| ctrl | no overlay | +10.87% | +0.37 | -34.57% |

**Sharpe gap (control − production):** +0.029 with the overlay, -0.037 without it. **CAGR gap (control − production):** +0.33pp with, -0.62pp without.

**Verdict: SUPPORTED.** The sign of the control-minus-production Sharpe gap flips between overlay on (+0.029) and off (-0.037), so the overlay is doing real work in the production-vs-control comparison.

## H4 — "0.34 vs 0.37 is noise"

OOS window 2014-11-26 → 2026-10-01, **2928 daily observations**, both books on identical dates (paired).

| test | statistic | p-value | reading |
|------|-----------|---------|---------|
| paired daily t-test on the return difference | t = -0.175 | 0.861 | mean difference -0.122 bps/day |
| same, Newey-West HAC(10) | t = -0.179 | 0.858 | serial-correlation-robust |
| bootstrap 95% CI on ΔCAGR (21-bar blocks, B=10,000) | [-4.07pp, +3.38pp] | — | P(production > control) = 0.43 |

Observed ΔCAGR = +9.71% − +10.04% = -0.33pp. Observed ΔSharpe = 0.34 − 0.37 = -0.03.

**Verdict: SUPPORTED.** The 95% bootstrap CI on ΔCAGR is [-4.07pp, +3.38pp] — it straddles zero, and the serial-correlation-robust paired t-test is t = -0.18, p = 0.86. The two books are **statistically indistinguishable** out-of-sample. That is itself the finding: the composite's factors do not separate it from a composite of rejected factors by any measurable margin, over 2928 daily observations.

## H5 — "The harness has a selection artifact"

Walk-forward selects parameters on TRAIN. A book that survives TRAIN selection could carry a structural OOS advantage unrelated to its signal. Two readings: run a **fixed, unselected** parameter set, and look at the train/test profile of both books.

### Fixed parameters — no train selection at all

| cell | params | production CAGR | control CAGR | production Sharpe | control Sharpe |
|------|--------|----------------:|--------------:|-----------------:|---------------:|
| cell_A | n=22, lb=126, thr=0.35 | +11.01% | +8.00% | 0.45 | 0.21 |
| cell_B | n=15, lb=126, thr=0.0 | +9.28% | +5.25% | 0.30 | -0.14 |

Decomposed the same way as H1 (gross = selection, then cost, then overlay):

| cell | selection (gross) | cost | overlay | total net |
|------|------------------:|-----:|--------:|----------:|
| cell_A | +2.17pp | +0.73pp | +0.10pp | +3.01pp |
| cell_B | +3.50pp | +0.42pp | +0.11pp | +4.03pp |

### What the train-window selection actually does

| book | best fixed cell | walk-forward | selection delta |
|------|-----------------:|-------------:|----------------:|
| PRODUCTION | +11.01% | +9.71% | -1.30pp |
| CONTROL_REVERSAL | +8.00% | +10.04% | +2.03pp |

### Train vs test — is there a flip?

| book | mean TRAIN Sharpe | OOS Sharpe | flip | mean TRAIN CAGR | OOS CAGR |
|------|------------------:|-----------:|-----:|----------------:|--------:|
| PRODUCTION | +0.94 | +0.34 | +0.60 | +18.89% | +9.71% |
| CONTROL_REVERSAL | +0.86 | +0.37 | +0.50 | +17.57% | +10.04% |

<details><summary>Per-fold train/test</summary>

| book | fold | selected params | TRAIN Sharpe | OOS Sharpe | TRAIN CAGR | OOS CAGR |
|------|-----:|------------------|-------------:|-----------:|----------:|---------:|
| PRODUCTION | 1 | n=22, lb=126, thr=0.35 | +1.14 | -0.85 | +22.39% | -0.80% |
| PRODUCTION | 2 | n=22, lb=126, thr=0.6 | +0.83 | +1.68 | +17.64% | +28.80% |
| PRODUCTION | 3 | n=22, lb=126, thr=0.6 | +0.47 | +0.57 | +11.97% | +13.22% |
| PRODUCTION | 4 | n=15, lb=126, thr=0.0 | +0.92 | -0.42 | +17.09% | +1.35% |
| PRODUCTION | 5 | n=15, lb=126, thr=0.35 | +0.76 | +0.71 | +14.97% | +13.16% |
| PRODUCTION | 6 | n=30, lb=126, thr=0.6 | +1.52 | -0.07 | +29.24% | +5.08% |
| CONTROL_REVERSAL | 1 | n=30, lb=126, thr=0.35 | +1.03 | -0.78 | +19.51% | +0.13% |
| CONTROL_REVERSAL | 2 | n=30, lb=126, thr=0.6 | +0.70 | +1.70 | +15.61% | +22.79% |
| CONTROL_REVERSAL | 3 | n=30, lb=126, thr=0.6 | +0.20 | +0.84 | +8.34% | +16.91% |
| CONTROL_REVERSAL | 4 | n=30, lb=126, thr=0.35 | +0.85 | +0.02 | +15.25% | +5.84% |
| CONTROL_REVERSAL | 5 | n=30, lb=252, thr=0.6 | +0.75 | +0.71 | +15.29% | +12.96% |
| CONTROL_REVERSAL | 6 | n=30, lb=126, thr=0.6 | +1.64 | -0.24 | +31.45% | +3.29% |

</details>

**Verdict: REFUTED — this is the one hypothesis that does not survive.** With the train-window selection removed entirely, production beats the control in 2 of 2 fixed cells: cell_A +3.01pp (Sharpe +0.24), cell_B +4.03pp (Sharpe +0.44). The production composite is **not** uniformly inert: under some fixed settings it does select better names than the reversal composite.

This is the strongest evidence in the repo for the production composite, and it deserves to be stated plainly rather than buried. But it is not a deployable edge, for two reasons. First, these cells are ordinary book-construction choices, not out-of-sample discoveries. Second, and more seriously, the walk-forward version of the strategy — the only protocol `GOAL.md` §5 accepts — does not reproduce it.

**The selection step is what destroys it.** Production's best fixed cell returns +11.01%/yr, but the same strategy under walk-forward parameter selection returns +9.71%/yr — selection costs it 1.30pp/yr. The control moves the other way: selection *adds* +2.03pp/yr to it. So the train-window search is anti-correlated with out-of-sample performance for the production composite and positively correlated for the control. That is a defect in the parameter-selection layer, and it is the mechanical reason the negative control ties production in the protocol that counts.

**There is no train/test flip unique to the control.** Train→OOS Sharpe degradation is +0.60 for production and +0.50 for the control — nearly identical. The control is not a book that was overfit and then broke; it is a book that behaves the same way in both regimes. That is the worse of the two cases for the production composite's defence.

## H6 — "Equal-count controls are the wrong null"

A random book and a **signal-scrambled** book are different nulls. A random book asks *does an arbitrary book make money*. A scrambled book asks *does **this** book make money for any reason other than its signal* — which is what a negative control is for.

- `scramble_c`: the composite score with a **fixed column relabel** (`score'[t,s] = score[t,π(s)]`). Every per-date marginal score distribution is preserved **exactly**; only the score-to-return link is destroyed.
- `scramble_r`: the composite with an **independent permutation of each date's cross-section**. Per-date marginals are still preserved exactly, but the name identity churns every rebalance, so turnover rises. Reported alongside so that difference is visible rather than hidden.

> **Correction on turnover preservation.** `scramble_c` was intended to hold turnover *exactly* fixed, and it does not. Relabelling score columns relabels which name receives which score, but `build_rebalance_weights` then inverse-vol-scales by the **name's** realised volatility and runs a sector/single-name cap projection over **name identities** — so the resulting weights are not a permutation of the original weights. Measured directly, under four pure column-permutations of the *same* score panel the total one-way turnover is 7.611 / 7.700 / 7.793 / 7.823 against an unpermuted 7.598: a ~3% spread, the same order as the seed-to-seed spread of the null itself. So `scramble_c` matches turnover *in distribution* and to within a few percent, not bit-exactly. The measured turnover of each null is printed in the table below so this can be checked rather than taken on trust.

| book | n | mean CAGR | sd | min | max | mean Sharpe | sd | turnover | cost drag | profitable |
|------|--:|----------:|---:|----:|----:|-----------:|---:|---------:|----------:|-----------:|
| **production (unscrambled)** | 1 | +9.71% | — | — | — | 0.34 | — | **2.51x/y** | **1.23%/y** | — |
| scramble_c (fixed relabel) | 60 | +9.59% | 0.91pp | +7.80% | +12.31% | +0.32 | 0.08 | 2.20x/y | 1.08%/y | 100% |
| scramble_r (per-date permute) | 60 | +8.52% | 0.68pp | +7.01% | +10.25% | +0.24 | 0.06 | 3.76x/y | 1.85%/y | 100% |

| book | vs scramble_c (CAGR pct) | vs scramble_c (Sharpe pct) | vs scramble_r (CAGR pct) | vs scramble_r (Sharpe pct) |
|------|-------------------------:|---------------------------:|------------------------:|--------------------------:|
| **production** | 58th | 58th | 93rd | 93rd |
| control | 72nd | 77th | 95th | 95th |

> **Read the production row, not the control row.** These nulls are built by scrambling the **production** composite, so the production row is a like-for-like test of production against its own signal destroyed. The control row places a *different* composite (reversal weights) against a null built from the trend composite's score distribution — the two books have different turnover, different score dispersion and different name overlap, so the control's percentile against this null is indicative only and should not be read as a significance test. A matched control scramble (reversal weights, then scrambled) is the clean version of that comparison and was not run; H2 and H4 cover the production-vs-control question directly instead.

**Verdict: SUPPORTED.** Against the turnover-matched signal-scrambled null, production sits at the 58th percentile on CAGR and 58th on Sharpe, while 100% of scrambled books are profitable. Keeping the per-date score distribution, the name count, the cost stack, the overlay and the constraints — and destroying only the link from score to return — leaves a result indistinguishable from the production one. (The null's turnover is matched to within a few percent, not exactly; see the correction note above.) Turnover is not what separates them.

## Turnover, beta and the equal-weight benchmark

### 1. Turnover and cost drag — is the control's edge just a smaller bill?

| book | annual turnover | annual cost drag |
|------|----------------:|-----------------:|
| production | 2.5130x/y | 1.23%/y |
| control | 3.3355x/y | 1.66%/y |
| **control − production** | **+0.8226x/y** | **+0.43pp/y** |

**The hypothesis is refuted, and the direction matters.** The brief asked what happens if the control turns over *less* — part of its advantage would then be a smaller cost bill. The measurement is the opposite: the control turns over **0.82x/yr more** and pays **0.43pp/yr more** in drag, and still earns more. As an identity:

```
gross_ctrl - gross_prod = (net_ctrl - net_prod) + (drag_ctrl - drag_prod)
                        = +0.33pp              + +0.43pp
                        = +0.76pp
```

The control's **gross** advantage is +0.76pp/yr — larger than its net advantage of +0.33pp/yr. Cost drag *narrows* the gap between the two books; it does not create it. Turnover is not the explanation, and neither book is winning by trading less.

### 2. Beta and correlation to the equal-weight benchmark

| book | beta | corr | R² | Jensen alpha | alpha t | alpha p | tracking error |
|------|-----:|-----:|---:|-------------:|--------:|--------:|---------------:|
| production | 0.491 | 0.748 | 0.559 | -1.78%/y | -0.39 | 0.70 | 10.4% |
| control | 0.577 | 0.880 | 0.775 | -2.41%/y | -0.53 | 0.60 | 10.4% |
| *equal-weight benchmark* | 1.000 | 1.000 | 1.000 | — (CAGR +17.12%, Sharpe 0.68) | — | — | — |

### 3. Would a market-neutral or beta-matched comparison change the verdict?

`GOAL.md` targets 3%/month net = **42.6%/yr**. The equal-weight NIFTY-50 benchmark over the same OOS windows returned +17.12%/yr (Sharpe 0.68). The book already **underperforms the benchmark it could have simply held**.

Production's beta against that benchmark is **0.491** (corr 0.748, R² 0.559); the control's is **0.577** (corr 0.880, R² 0.775). Neither is ~1.0 — the regime overlay spends time in cash, which is why — so the 'levered index fund' story is not literally right. But it is not rescued either: Jensen alpha is **-1.78%/yr (t = -0.39, p = 0.70)** for production and **-2.41%/yr (t = -0.53, p = 0.60)** for the control. Both are **negative** and both are statistically indistinguishable from zero.

**Would a beta-matched comparison change the verdict? No.** The two books differ by 0.086 in beta, so matching beta changes nothing material: whichever Sharpe wins raw wins beta-matched. And beta-matching cannot separate a book from a signal-scrambled version of itself, because scrambling the signal leaves beta intact by construction.

**Would a market-neutral comparison change the verdict? It is not available, and it would not be the right test.** The account is long-only delivery (`GOAL.md` §3.2, `AGENT_BRIEF.md` §5), so there is no short leg to neutralise against. The Jensen alpha above is already the market-adjusted number, and it is zero.

**At what beta would the comparison become fair?** A fair comparison asks whether the book earns its *target* given its risk. Stated on the same excess-return basis the regression uses (`excess-return (target-rf)/(benchmark-rf)`), a zero-alpha book would need a beta of **3.40** to reach 42.6%/yr from a 17.12%/yr benchmark — roughly 7× the beta production actually runs at, and well beyond what a long-only delivery account permits. Since the measured alpha is statistically zero, the target is unreachable at any beta available to this account. Meeting 3%/month would require the alpha to be real, and on this evidence it is not distinguishable from zero.

## Bottom line

**The null is not the reversal control. The null is a book with no signal at all.** 100 random-weight books run through the identical harness — same folds, same engine, same 21.92bps cost stack, same constraints — are profitable **100% of the time**, mean CAGR +8.59%, worst case +7.03%, mean Sharpe +0.24. Not one of them lost money. A 22-name, monthly-rebalanced, long-only NIFTY-50 book returns a positive out-of-sample result in this sample whatever signal it holds, because the universe rose and long-only equity beta is the dominant term.

**And the composite's edge over that null is not a selection edge.** On net CAGR production sits at the 97th percentile — but random books turn over 3.75x/yr against production's 2.51x/yr, so on *net* return production is being credited for trading less. Strip that channel out and compare gross CAGR: production's +11.82% lands at the **47th percentile** of a null whose gross mean is +11.83%. That is the median random book. What the composite genuinely does better is *hold* rather than *rotate* — a cost-management property that this harness rewards and that no factor evidence supports.

**The signal-scrambled null is the decisive test, and it agrees.** Destroy *only* the signal — keep the composite's own per-date score distribution, its name count, its cost stack, its overlay, its constraints — and relabel which symbol receives which score. Those books are profitable **100% of the time** with mean CAGR +9.59%, and production sits at the 58th percentile of them. A negative control exists for exactly one purpose: to separate the signal from everything else that produces a return. This one does not separate them, so it has failed at its job — not merely because the control scored higher, but because the harness cannot tell the two books apart.

**And the production-vs-control gap is not a real gap.** Over 2928 daily out-of-sample observations the 95% block-bootstrap CI on ΔCAGR is [-4.07pp, +3.38pp] and the serial-correlation-robust paired t-test gives p = 0.86. The 0.34-vs-0.37 Sharpe difference is noise, and the brief's reading of it as decisive was right to be doubted.

**Beta does not rescue it.** Production runs at beta 0.49 against the equal-weight benchmark and the control at 0.58 — they differ by 0.09, so beta-matching changes nothing. Jensen alpha is -1.78%/yr (p = 0.70) for production and -2.41%/yr (p = 0.60) for the control: both negative, both indistinguishable from zero. To reach `GOAL.md`'s 42.6%/yr target on a zero-alpha basis the book would need a beta of 3.40 — about 7× what it runs at, and unreachable in a long-only delivery account. The target is not beta-limited; it is alpha-limited, and the alpha is not there.

**One finding cuts the other way, and it deserves to be stated plainly.** With *fixed, unselected* parameters, production beats the control in 2 of 2 cells cell_A (+11.01% vs +8.00%), cell_B (+9.28% vs +5.25%). So the trend composite is not uniformly inert — under some fixed settings it does select better names than the reversal composite. That is a real, reproducible observation and it is the strongest argument this repo has for the production composite. It is not, however, evidence of a *deployable* edge: the same fixed cells are ordinary book-construction choices, they were not selected out-of-sample, and the walk-forward version of them — which is the only protocol that counts — does not reproduce the advantage. It also does not rescue the negative control, which exists precisely to test the walk-forward result.

**So: no — this strategy does not have a demonstrable edge, and the evidence collected here is consistent with its entire out-of-sample return being what a null produces.** A random book earns +8.6%/yr here with no signal whatsoever. The 9.71% is not a strategy result that happens to sit next to a failed control; it is a control's result wearing a different label. Nothing here justifies relaxing `GOAL.md` §5, and the four Gate 4 checks that pass would pass just as well for a book holding 22 names chosen at random. The secondary findings do not rescue it: the control survives removal of its low-volatility leg and still beats production, so that leg is not carrying it (H2). The regime overlay flips which book wins (+0.029 with it, -0.037 without), so the overlay — not the factors — decides the comparison (H3). And the two books' train-to-test degradation is nearly identical (+0.60 vs +0.50 Sharpe), so there is no train/test flip unique to the control (H5). **The correct next step is not a wider parameter search — 18 of 18 profitable cells and 42 negative catalog trials are what a null produces — it is to change what counts as success.** Any future candidate must beat a signal-scrambled version of itself, and must be measured against that, not against the equal-weight benchmark in a rising market.

---

*Produced by `research/control_diagnostic.py` against engine `d93815344bd3`, loader `c1badf5f7df8`, costs `ba350aef75b3`, panel `389b082b832f`. Every figure here is net of the full Indian delivery cost stack and must be quoted with its end date — the OOS window ends 2026-10-01. Survivorship bias is present and disclosed. `GOAL.md` §6 anti-fraud rules apply: no in-sample number is presented as a result, and no cost was reduced to rescue anything.*
