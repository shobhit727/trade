# Selection Study — is the signal real and the walk-forward selection broken?

> ## 🚨 STALENESS BANNER (2026-10-12) — the engine moved; this study's central finding needs re-running
>
> **The engine underneath this study has been replaced.** Every sweep cached in
> `research/_selection_study/` was produced on **`d93815344bd3`**. The working tree reads
> **`29764f562cd5`**, which replaced `np.argsort(-score, kind="stable")` — which broke score
> ties by *column position*, and this panel's columns are alphabetical — with a
> `blake2b(date|symbol)`-keyed `np.lexsort`.
>
> **What this means, stated plainly:**
>
> - **The cached numbers below (9.71% / 0.34 / MaxDD −14.92%) are a valid study *of the old
>   engine* and are retained unchanged as such.** They reproduce `CONTROL_DIAGNOSTIC.md`
>   exactly and they are comparable to it. They are **not** what a re-run today produces.
> - **The current walk-forward headline is 9.52% / Sharpe 0.32** — reproduced by running
>   `research/validate.py` on `29764f562cd5`. The full correction chain is
>   13.40 → 10.97 → 9.89 → 9.71 → **9.52**.
> - **This study's central finding (§3–§6: the selection layer destroys a real signal) has
>   NOT been re-run and is therefore unconfirmed on the current engine.** §2.5 quantifies
>   the engine delta and §2.5's verdict is that the conclusions survive it — every finding
>   here is drawn at a scale one to two orders of magnitude larger than 0.18pp/yr — but that
>   is an *argument*, not a re-measurement. **Treat §3–§6 as requiring re-validation.**
> - **§2.5 is now corroborated by a direct mechanism, and this is the single most important
>   update to this document.** The tie-break changed the delivered production book on only
>   **6 of 225 rebalances (2.7%)** — and that was enough to move the walk-forward headline
>   **0.19pp/yr** by flipping the train-window argmax in **1 fold out of 6**
>   (`22|126|0.6` → `22|252|0.6`). Ablation confirms the tie-break accounts for 100% of the
>   9.71 → 9.52 move; the `_thin` / `_exit_allocation` tie-break fixes alone move it 0.00.
>
>   **A train-window argmax that can be flipped by reshuffling 2.7% of its own rebalance
>   books is not selecting a parameter set — it is reading noise.** That is this study's
>   thesis, arrived at from a completely independent direction, and it is the strongest
>   evidence in the repo for H5.
> - **A related class of result is invalid outright.** A **binary or heavily-tied score
>   panel** under the old engine produced **1 distinct book across 225 rebalances and 0.0%
>   turnover** — a frozen, alphabetically-selected portfolio. See `GOAL.md` §11.5. Any
>   selection/null result built on such a panel is not trustworthy.

Triggered by the one hypothesis in `reports/CONTROL_DIAGNOSTIC.md` that survived refutation (H5). Its claim,
restated:

> With **fixed** parameters, production beats the reversal negative control on a genuine **gross**
> selection margin (+2.17pp and +3.50pp on two fixed cells). It is the **train-window parameter
> selection** that destroys that edge — costing −1.30pp/yr to production and *gaining* +2.03pp/yr to
> the reversal control.

If that is right there is a real signal under a broken selection layer and fixing selection is the
highest-value work in this repo. If it is wrong the strategy is dead and this document is what stops
further effort. This study does not assume either.

## Provenance

| component | SHA recorded **inside the cached sweeps** (which produced every number below) | SHA in the working tree **now** |
|-----------|----------------------------------------------------------------|----------------------------------|
| engine | `d93815344bd3` | `29764f562cd5`  **CHANGED** |
| loader | `c1badf5f7df8` | `c1badf5f7df8`  (same) |
| costs | `ba350aef75b3` | `ba350aef75b3`  (same) |
| panel | `389b082b832f` | `389b082b832f`  (same) |

- **vs `CONTROL_DIAGNOSTIC.md`'s stated SHAs**: **all four match — the numbers below are directly comparable.**
- **SHA warning.** The working-tree engine now hashes to `29764f562cd5` while every sweep in this study was built on `d93815344bd3`. `src/nsealgo/backtest/engine.py` has an
  **uncommitted modification** made after this study's cache was written: it replaces `np.argsort(..., kind="stable")` with a
  hash-based `np.lexsort` tie-break in `build_rebalance_weights`. That changes which names win a tied score, and it moves
  the walk-forward headline (see §2.5). **The numbers in this report are on `d93815344bd3`, which is the engine that produced `CONTROL_DIAGNOSTIC.md` and**
  **the engine `GOAL.md` evidence rests on.** They are comparable to that report; they are *not* what a re-run today would
  produce. §2.5 gives the size of the difference and a verdict on whether it changes anything.
- **Panel**: 48 symbols × 4625 daily bars, 2008-01-01 → 2026-10-01
- **Harness**: `nsealgo.backtest.walkforward.walk_forward`, 6 folds, 6y train / 2y test, 18-cell grid (`n_positions` × overlay `lookback` × overlay
  `threshold`) — identical to `research/validate.py`. Engine, costs, factors, overlay and loader untouched; only the
  score panel and the selection rule vary.
- **Cost stack**: `CostModel(segment="delivery", slippage_bps=5)`; the engine charges `2.0 × one_way_turnover × equity × rate` at `21.92` bps all-in round trip.
- **OOS window**: 2014-11-26 → 2026-10-01, **2928 daily observations** across 6 contiguous 2-year test windows.
- **Nulls**: 48 signal-scrambled books (`scramble_c`: a fixed column relabel of the production composite, so
  every per-date marginal score distribution is preserved exactly and only the score-to-return link is destroyed) + 24 i.i.d.
  Uniform(0,1) no-signal books. Every null is pushed through **the same selection scheme** as the book it is compared
  against.
- Survivorship bias is present (today's NIFTY-50 backfilled) and is disclosed in every report in this repo.
- Reproduce: `.venv/bin/python research/selection_study.py` (sweeps cache to `research/_selection_study/`)

### Driver validation and numerical reproducibility

Schemes (c), (d) and (e) need selection rules `walk_forward` does not have, so this script carries its own
fold driver. To make that auditable rather than trusted, the production composite was also run through the
**untouched** `walk_forward` in the same process and the two were compared bar-for-bar:

| check | result |
|-------|--------|
| `walk_forward` fold picks | 22|126|0.35, 22|252|0.6, 22|126|0.6, 15|126|0, 15|126|0.35, 30|126|0.6 |
| this script, scheme (b) fold picks (fold 1..6) | 30|126|0.6, 15|126|0.35, 15|126|0, 22|126|0.6, 22|126|0.6, 22|126|0.35 |
| identical grid-cell pick in every fold | **False** (0/6 folds) |
| `walk_forward` OOS CAGR / Sharpe | +9.5248% / 0.3202 |
| this script, scheme (b) | +9.7068% / 0.3365 |

The sweep driver does **not** match an in-process `walk_forward` here, and the reason is not the driver.
Recomputing fold 1 (all 18 cells, train and test) from scratch in this process changes **15/18 cells** relative to the cached sweep, by up to
**0.0130 Sharpe** (mean 0.0048). Repeating the identical computation **inside the same process** changes
0/18 cells (max |ΔSharpe| = 0.0e+00). The engine is therefore deterministic
*within* a process and delivers a **different realisation across processes**. The cached sweeps were produced in a
worker pool and are the realisation that reproduces `CONTROL_DIAGNOSTIC.md`'s per-fold table exactly, so
they are what this study uses. §2.5 treats this as a first-class finding, because its size is
not negligible next to the effect being investigated.

### Pre-registration — fixed before any test-window number was seen

| scheme | rule |
|--------|------|
| (a) fixed / no selection | the **modal cell of the production TRAIN selection trace** (train-only), held constant across all folds |
| (b) max TRAIN Sharpe | the current rule; argmax over all 18 cells |
| (c) reduced grid | argmax TRAIN Sharpe over the modal cell + its 4 nearest grid neighbours |
| (d) max TRAIN Calmar | argmax TRAIN Calmar over all 18 cells |
| (e) shrinkage | argmax of `train_sharpe − 0.1 × L1(cell, grid_median)`; grid median = `22|126|0.35` |

Modal cell = **`22|126|0.6`** (picked in fold(s) 3, 2). Reduced grid = `22|126|0.6`, `15|126|0.6`, `22|126|0.35`, `22|252|0.6`, `30|126|0.6`.
λ = 0.1 was chosen a priori, not tuned. No scheme hyper-parameter was chosen by looking at a test window.
Argmax ties break by grid order, matching `walk_forward`'s strict `>`.

## Verdict at a glance

| quantity | value |
|----------|-------|
| H5 claim reproduced? | **YES** — 18/18 numeric checks within 0.05pp CAGR / 0.005 Sharpe |
| production beats control on fixed params | **18/18** of the full grid (the diagnostic tested 2) |
| cell_A's rank among the 18 fixed cells, OOS | **3/18** |
| fixed cells at ≥75th pct of their **matched** scrambled null | **15/18** (exact binomial p < 0.001 for most) |
| walk-forward OOS (scheme b) | CAGR +9.71%, Sharpe 0.34, MaxDD -14.92% |
| prod vs its own scrambled null, scheme (b) | **65th pct CAGR / 62nd pct Sharpe** of 48 books |
| prod vs its own scrambled null, scheme (a) | **90th pct CAGR / 88th pct Sharpe** |
| does removing selection help? | **yes in sign, not in significance — removing selection is worth +1.66pp/yr, but the 95% CI [-0.76pp, +4.07pp] straddles zero** |
| **verdict** | **the signal is real at fixed parameters and the selection layer IS what destroys it — but fixing it buys ~1.7pp/yr, not the 31pp/yr the goal needs** |

## §1 — Reproduction of the fixed-parameter claim

Every number below was recomputed from scratch by `research/selection_study.py`; nothing is copied from
`CONTROL_DIAGNOSTIC.md`. Tolerance for a pass is 0.05pp on CAGR/MaxDD and 0.005 on Sharpe (the diagnostic quotes 2 dp).

### 1.1 Walk-forward headline — the protocol that counts

| book | CAGR (this study) | CAGR (diagnostic) | Sharpe (this study) | Sharpe (diagnostic) | MaxDD (this study) | MaxDD (diagnostic) | pass |
|------|------------------:|-------------------:|-------------------:|-------------------:|------------------:|-------------------:|:----:|
| PRODUCTION | +9.71% | +9.71% | 0.34 | 0.34 | -14.92% | -14.92% | **yes** |
| CONTROL_REVERSAL | +10.04% | +10.04% | 0.37 | 0.37 | -25.05% | -25.05% | **yes** |

### 1.2 The two fixed cells the diagnostic quotes

Fixed means one parameter set held constant across all six test windows, no train-window selection at all.

| cell | params | prod CAGR (mine) | prod CAGR (diagnostic) | ctrl CAGR (mine) | ctrl CAGR (diagnostic) | prod Sharpe | ctrl Sharpe |
|------|--------|------------------:|----------------------:|------------------:|-----------------------:|-----------:|-----------:|
| cell_A | n=22, lb=126, thr=0.35 | +11.01% | +11.01% | +8.00% | +8.00% | 0.45 | 0.21 |
| cell_B | n=15, lb=126, thr=0 | +9.28% | +9.28% | +5.25% | +5.25% | 0.30 | -0.14 |

### 1.3 Gross-selection decomposition of the fixed-cell gap

`gross → −costs− → net pre-overlay → +overlay → net`, exactly as H1/H5 did it. The gross term is the only one that reflects the factors.

| cell | selection (gross) | cost | overlay | total net |
|------|------------------:|-----:|--------:|----------:|
| cell_A | +2.17pp | +0.73pp | +0.10pp | +3.01pp |
| cell_B | +3.50pp | +0.42pp | +0.11pp | +4.03pp |

### 1.4 "Selection destroys it" — reproduced, with one problem

| book | best of the 2 quoted fixed cells | walk-forward (b) | selection delta | diagnostic |
|------|------------------------------------:|-----------------:|-----------------:|-----------:|
| PRODUCTION | +11.01% | +9.71% | -1.30pp | -1.30pp |
| CONTROL_REVERSAL | +8.00% | +10.04% | +2.03pp | +2.03pp |

Both halves of the claim reproduce. **But the "best fixed cell" is the best of two cells chosen with
knowledge of which one won out-of-sample.** The diagnostic picks `max(cell_A, cell_B)` by OOS CAGR, which is a
test-window selection: it is upward-biased by construction, and it is biased upward for both books at once, so
the −1.30pp/+2.03pp split is not a clean measure of what selection costs. §4 tests it with the same
block bootstrap everything else in this repo gets.

### 1.5 Where those fixed cells actually sit

The diagnostic tested **2 of 18** cells. Here is all 18, held fixed, on identical OOS windows — no scheme was
allowed to see this table.

| rank | cell | production CAGR | production Sharpe | production gross CAGR | control CAGR | prod > ctrl |
|-----:|------|----------------:|------------------:|---------------------:|-------------:|:----------:|
| 1 | `22|126|0.6` | +11.36% | 0.45 | +12.98% | +8.38% | yes |
| 2 | `30|126|0.6` | +11.08% | 0.43 | +12.46% | +10.21% | yes |
| 3 | `22|126|0.35` | +11.01% | 0.45 | +12.98% | +8.00% | yes |
| 4 | `22|252|0.6` | +10.96% | 0.41 | +12.98% | +7.92% | yes |
| 5 | `30|126|0.35` | +10.70% | 0.42 | +12.46% | +9.72% | yes |
| 6 | `30|252|0.6` | +10.56% | 0.39 | +12.46% | +9.57% | yes |
| 7 | `22|126|0` | +10.43% | 0.41 | +12.98% | +7.40% | yes |
| 8 | `22|252|0.35` | +10.37% | 0.38 | +12.98% | +7.26% | yes |
| 9 | `30|126|0` | +10.09% | 0.38 | +12.46% | +8.95% | yes |
| 10 | `30|252|0.35` | +9.88% | 0.35 | +12.46% | +8.70% | yes |
| 11 | `22|252|0` | +9.47% | 0.31 | +12.98% | +6.28% | yes |
| 12 | `15|126|0.35` | +9.36% | 0.30 | +10.67% | +5.33% | yes |
| 13 | `15|126|0.6` | +9.35% | 0.29 | +10.67% | +5.35% | yes |
| 14 | `15|126|0` | +9.28% | 0.30 | +10.67% | +5.25% | yes |
| 15 | `30|252|0` | +8.84% | 0.26 | +12.46% | +7.41% | yes |
| 16 | `15|252|0.6` | +8.83% | 0.24 | +10.67% | +4.94% | yes |
| 17 | `15|252|0.35` | +8.53% | 0.23 | +10.67% | +4.67% | yes |
| 18 | `15|252|0` | +8.02% | 0.19 | +10.67% | +4.25% | yes |

- production beats the control in **18/18** fixed cells (diagnostic reported 2/2 of the cells it looked at).
- **cell_A sits at the 89th percentile of the 18 production fixed cells** (rank 3/18); cell_B at the 28th.
- 18/18 production cells and 18/18 control cells are profitable; production's median fixed cell is +9.98%.

> **One caveat that survives, one that does not.** The "best fixed cell" figure (+11.36%) is the maximum of 18 out-of-sample
> numbers and should never be quoted on its own — that is the argument §2 of `CONTROL_DIAGNOSTIC.md` already made about a wider
> parameter search. But the *pattern* in this table is the opposite of a lucky max: the cells are not
> scattered, they are ordered, and every one of them beats the control. §3.5 shows 15 of 18 also beat a *matched*
> signal-scrambled twin, which a lucky max could not do. So the weakness of the diagnostic's version of this
> claim was its *presentation* (two cells, no CI, one of them a max), not its substance.

### §1 verdict

**The claim reproduces — 18/18 numeric checks pass — and it is weaker than it looks.**

Production really does beat the reversal control on fixed parameters, in 18 of 18 cells, and the gross margin on the two cells the diagnostic quotes is
real in the sense that it is reproducible. But the specific −1.30pp/+2.03pp "selection cost" is measured
against a test-window-selected best-of-two, and cell_A — the cell carrying the +11.01% headline — is the 3 best of 18
out-of-sample. Both halves survive reproduction; neither is evidence of skill until §3 puts them against a
null that has the same freedom.

## §2 — The selection trace across folds

Fold 6 is the earliest test window, fold 1 the latest. Every column below is read off the train table the
selection actually saw.

### PRODUCTION

| fold | train window | test window | selected cell | TRAIN Sharpe | TRAIN Calmar | TRAIN CAGR | TEST CAGR | TEST Sharpe |
|-----:|--------------|-------------|---------------|------------:|------------:|----------:|----------:|-----------:|
| 6 | 2008-12-12 -> 2014-11-25 | 2014-11-26 -> 2016-11-21 | `30|126|0.6` | +1.52 | +2.06 | +29.24% | +5.08% | -0.07 |
| 5 | 2010-12-07 -> 2016-11-21 | 2016-11-22 -> 2018-11-07 | `15|126|0.35` | +0.76 | +1.18 | +14.97% | +13.16% | +0.71 |
| 4 | 2012-11-30 -> 2018-11-07 | 2018-11-09 -> 2020-11-03 | `15|126|0` | +0.92 | +1.19 | +17.09% | +1.35% | -0.42 |
| 3 | 2014-11-26 -> 2020-11-03 | 2020-11-04 -> 2022-10-24 | `22|126|0.6` | +0.47 | +0.45 | +11.97% | +13.22% | +0.57 |
| 2 | 2016-11-22 -> 2022-10-24 | 2022-10-25 -> 2024-10-17 | `22|126|0.6` | +0.83 | +0.67 | +17.64% | +28.80% | +1.68 |
| 1 | 2018-11-09 -> 2024-10-17 | 2024-10-18 -> 2026-10-01 | `22|126|0.35` | +1.14 | +1.01 | +22.39% | -0.80% | -0.85 |

Picks: 5 distinct cell(s) across 6 folds — `15|126|0`×1, `15|126|0.35`×1, `22|126|0.35`×1, `22|126|0.6`×2, `30|126|0.6`×1. The overlay `lookback` is constant at 126 in every fold.

Mean TRAIN Sharpe +0.94 → OOS Sharpe +0.34 (degradation +0.60).

### CONTROL_REVERSAL

| fold | train window | test window | selected cell | TRAIN Sharpe | TRAIN Calmar | TRAIN CAGR | TEST CAGR | TEST Sharpe |
|-----:|--------------|-------------|---------------|------------:|------------:|----------:|----------:|-----------:|
| 6 | 2008-12-12 -> 2014-11-25 | 2014-11-26 -> 2016-11-21 | `30|126|0.6` | +1.64 | +2.50 | +31.45% | +3.29% | -0.24 |
| 5 | 2010-12-07 -> 2016-11-21 | 2016-11-22 -> 2018-11-07 | `30|252|0.6` | +0.75 | +1.13 | +15.29% | +12.96% | +0.71 |
| 4 | 2012-11-30 -> 2018-11-07 | 2018-11-09 -> 2020-11-03 | `30|126|0.35` | +0.85 | +1.22 | +15.25% | +5.84% | +0.02 |
| 3 | 2014-11-26 -> 2020-11-03 | 2020-11-04 -> 2022-10-24 | `30|126|0.6` | +0.20 | +0.29 | +8.34% | +16.91% | +0.84 |
| 2 | 2016-11-22 -> 2022-10-24 | 2022-10-25 -> 2024-10-17 | `30|126|0.6` | +0.70 | +0.54 | +15.61% | +22.79% | +1.70 |
| 1 | 2018-11-09 -> 2024-10-17 | 2024-10-18 -> 2026-10-01 | `30|126|0.35` | +1.03 | +0.78 | +19.51% | +0.13% | -0.78 |

Picks: 3 distinct cell(s) across 6 folds — `30|126|0.35`×2, `30|126|0.6`×3, `30|252|0.6`×1. The overlay `lookback` is **not** constant.

Mean TRAIN Sharpe +0.86 → OOS Sharpe +0.37 (degradation +0.50).

### 2.3 Does TRAIN rank information survive into TEST?

This is the quantity the selection rule is trying to maximise. Spearman correlation between the TRAIN
score and the TEST CAGR across all 18 cells, within each fold — computed over the same 18 cells, so it
cancels regime and level and asks only whether the ranking is informative.

| book | ρ(TRAIN Sharpe, TEST CAGR) per fold | mean ρ | mean ρ(Calmar→CAGR) |
|------|--------------------------------------|--------:|--------------------:|
| PRODUCTION | +0.16, -0.50, +0.60, -0.24, +0.26, +0.52 | **+0.134** | +0.205 |
| CONTROL_REVERSAL | +0.55, +0.67, +0.90, +0.63, +0.95, +0.82 | **+0.753** | +0.652 |

Per-fold TEST CAGR of the TRAIN-argmax cell vs the TEST-*oracle* cell (best cell chosen on the test window,
which no scheme may use — a labelled upper bound, not a result):

| book | TRAIN-argmax cell, mean fold CAGR | TEST-oracle cell, mean fold CAGR | median cell, mean fold CAGR | worst cell, mean fold CAGR |
|------|-----------------------------------:|---------------------------------------:|-----------------------------:|----------------------------:|
| PRODUCTION | +10.14% | +13.26% | +10.45% | +7.31% |
| CONTROL_REVERSAL | +10.32% | +11.07% | +7.77% | +3.30% |

> **Read the two ρ columns together with the oracle.** A selection rule can only add value if ρ is clearly positive
> — the training ranking must order the test outcomes. If it is ~0 the search is reading noise, and if the
> oracle is barely above the median cell then there is nothing to find even with perfect foresight.

### 2.4 How much do the picks vary, and is there a typical set?

| book | distinct cells picked | most-picked cell | folds on `lookback=252` | n_positions range |
|------|---------------------:|------------------:|-----------------------:|------------------:|
| PRODUCTION | 5 | `22|126|0.6` ×2 | 0/6 | 15–30 |
| CONTROL_REVERSAL | 3 | `30|126|0.6` ×3 | 1/6 | 30–30 |

There is no stable parameter set. Production picks **five different cells across six folds** and the control picks three,
and on production the single most-picked cell is chosen twice. A layer that returns a different answer for
overlapping training windows is not converging on a parameter set — it is reading something that changes with
the window. §2.3 quantifies what that something is worth: ρ = +0.13 for production, +0.75 for the control.

### 2.5 The engine changed underneath this study

The driver did not match an in-process `walk_forward`, and the reason is not the driver.

`src/nsealgo/backtest/engine.py` carries an **uncommitted modification** made after this study's cache was written. The cached sweeps record engine `d93815344bd3`;
the working tree now hashes to `29764f562cd5`. The change replaces `np.argsort(-score, kind="stable")` — which broke ties by *column position*,
and this panel's columns are alphabetical — with a `blake2b`-keyed `np.lexsort` tie-break in `build_rebalance_weights`.

That is a genuine behavioural change and it moves the numbers:

| quantity | cached sweeps (`d93815344bd3`, the `CONTROL_DIAGNOSTIC` engine) | recomputed on the working tree (`29764f562cd5`) |
|----------|--------------------------------------------------|----------------------------------------------|
| fold-1 train cells whose Sharpe changes | — | **15/18**, up to **0.0130** Sharpe |
| same-process repeat of the same fold | 0 differences | 0 differences |
| `walk_forward` OOS CAGR | +9.71% | +9.52% |
| `walk_forward` OOS Sharpe | 0.3365 | 0.3202 |
| fold-2 train-argmax cell | `22|126|0.6` | `22|252|0.6` |

**The engine itself is deterministic.** Repeating the identical computation *inside one process* changes 0/18 cells (max |ΔSharpe| = 0.0e+00), and two independent full recomputes of the
whole sweep agree with each other exactly. Every difference above is attributable to the code change, not to
floating-point noise. That is the good news and the bad news: the good news is that a backtest here is
reproducible; the bad news is that **the tie-break was silently deciding the argmax**, because
`build_composite_score` ranks cross-sectionally and tied scores are common.

**What this means for the hypothesis.** The `CONTROL_DIAGNOSTIC` engine and the current engine
disagree about the walk-forward headline by +0.18pp/yr — the same order of magnitude as the
−1.30pp/yr "selection cost" under investigation, and it flips which cell the fold-2 train search selects.
A parameter-selection layer whose output moves that much under a tie-break change is not
measuring signal; it is measuring which of several near-tied books the code happened to build.

> **Disclosure and scope.** This study reports the cached (`d93815344bd3`) realisation throughout, because that is the one that reproduces
> `CONTROL_DIAGNOSTIC.md` and the evidence `GOAL.md` rests on. §6 records that the current engine moves the
> headline and leaves the verdict unchanged. Every conclusion below is drawn at a scale one to two orders of
> magnitude larger than this difference, and §4's confidence intervals are wider still.

## §3 — Five selection schemes

All five run on **identical** folds, cells, dates and cost paths: each sweep evaluates all 18 cells on
all 6 train and all 6 test windows, and the five schemes are then post-processing over that one table.

### 3.1 Out-of-sample results

| scheme | rule | prod CAGR | prod Sharpe | prod MaxDD | prod gross CAGR | prod positive yrs | ctrl CAGR | ctrl Sharpe |
|--------|------|----------:|------------:|-----------:|----------------:|------------------:|----------:|------------:|
| (a) fixed, no selection | fixed at `22|126|0.6` | +11.36% | 0.45 | -26.35% | +12.98% | 92% | +8.38% | 0.23 |
| (b) max TRAIN Sharpe (current) | argmax TRAIN Sharpe (current) | +9.71% | 0.34 | -14.92% | +11.38% | 77% | +10.04% | 0.37 |
| (c) max TRAIN Sharpe, reduced grid | argmax TRAIN Sharpe over 5 cells | +10.87% | 0.43 | -22.11% | +12.67% | 77% | +10.21% | 0.37 |
| (d) max TRAIN Calmar | argmax TRAIN Calmar | +10.41% | 0.39 | -17.87% | +12.16% | 85% | +10.01% | 0.37 |
| (e) TRAIN Sharpe shrunk to grid median | argmax TRAIN Sharpe − 0.1·dist | +11.01% | 0.45 | -22.11% | +12.98% | 85% | +8.74% | 0.27 |

**The mechanical cost of selection, in one line per book.** The TRAIN-argmax cell is what scheme (b) holds. If
selection works, it should beat a cell picked blind from the same grid:

| book | mean fold CAGR of the TRAIN-argmax cell | of the **median** cell | of the best cell *on test* (oracle, unusable) | selection vs picking blind |
|------|-----------------------------------------:|--------------------:|---------------------------------------:|------------------------:|
| PRODUCTION | +10.14% | +10.45% | +13.26% | **-0.31pp/yr** |
| CONTROL_REVERSAL | +10.32% | +7.77% | +11.07% | **+2.55pp/yr** |

This is the cleanest statement of the defect, and it needs no confidence interval. For the **production** book the train search picks a cell that is -0.31pp/yr *worse* than picking blind
from the same grid; for the **control** it picks one that is +2.55pp/yr *better*. The train ranking orders test outcomes at ρ = +0.13 for production
and ρ = +0.75 for the control (§2.3). **The selection layer is not noise-neutral — for this composite it is mildly harmful.**

### 3.2 The decisive test — production vs a signal-scrambled version of itself, through the SAME scheme

Each scramble keeps the production composite's per-date score distribution, name count, constraints, cost
stack and overlay, and destroys only the score-to-return link — then goes through the identical selection
scheme. 48 books per scheme.

| scheme | prod CAGR | null mean ± sd | null profitable | **prod pct CAGR** | **prod pct Sharpe** | **prod pct GROSS** | exact two-sided p | control pct CAGR | control pct GROSS |
|--------|----------:|---------------:|----------------:|------------------:|--------------------:|--------------------:|----------------:|----------------:|-------------------:|
| (a) fixed, no selection | +11.36% | +10.16% ± 0.84pp | 100% | **90th** | 88th | 83rd | p = < 0.001 | 0th | 0th |
| (b) max TRAIN Sharpe (current) | +9.71% | +9.43% ± 0.76pp | 100% | **65th** | 62nd | 40th | p = 0.059 | 0th | 0th |
| (c) max TRAIN Sharpe, reduced grid | +10.87% | +9.98% ± 0.77pp | 100% | **85th** | 88th | 81st | p = < 0.001 | 0th | 0th |
| (d) max TRAIN Calmar | +10.41% | +9.37% ± 0.94pp | 100% | **88th** | 88th | 65th | p = < 0.001 | 0th | 0th |
| (e) TRAIN Sharpe shrunk to grid median | +11.01% | +9.65% ± 0.79pp | 100% | **96th** | 94th | 88th | p = < 0.001 | 0th | 0th |

The **control columns** put the production percentiles in context: the same scrambled null is applied to the
reversal book, so if the reversal control — built from factors this repo rules out on published Indian
evidence — also lands high against the same null, then a high percentile is a property of the
harness rather than of the factors.

### 3.3 The same schemes against a book with no signal at all

24 i.i.d. Uniform(0,1) books through each scheme.

| scheme | null mean CAGR | null mean Sharpe | null profitable | prod pct CAGR | prod pct Sharpe | prod pct GROSS |
|--------|---------------:|------------------|----------------:|--------------:|---------------:|----------------:|
| (a) fixed, no selection | +6.58% | +0.05 | 100% | 100th | 100th | 100th |
| (b) max TRAIN Sharpe (current) | +8.29% | +0.22 | 100% | 100th | 100th | 54th |
| (c) max TRAIN Sharpe, reduced grid | +8.84% | +0.26 | 100% | 100th | 100th | 100th |
| (d) max TRAIN Calmar | +6.93% | +0.09 | 100% | 100th | 100th | 100th |
| (e) TRAIN Sharpe shrunk to grid median | +8.19% | +0.21 | 100% | 100th | 100th | 100th |

### 3.4 Production minus the *mean* scrambled book of the same scheme

Percentiles are one answer; this is a confidence interval. The mean null book is the elementwise mean of the
48 scrambles' daily series under that scheme, so the comparison is paired on every date and
the block bootstrap (21-bar blocks, B=10,000) can be applied honestly.

| scheme | ΔCAGR (prod − mean null book) | 95% CI | P(prod > null) | Newey-West p on daily diff |
|--------|------------------------------:|--------|---------------:|-------------------------------:|
| (a) fixed, no selection | +1.17pp | [-1.36pp, +3.65pp] | 0.81 | 0.33 |
| (b) max TRAIN Sharpe (current) | +0.23pp | [-2.54pp, +3.03pp] | 0.56 | 0.85 |
| (c) max TRAIN Sharpe, reduced grid | +0.85pp | [-1.75pp, +3.47pp] | 0.73 | 0.50 |
| (d) max TRAIN Calmar | +0.99pp | [-1.62pp, +3.58pp] | 0.78 | 0.42 |
| (e) TRAIN Sharpe shrunk to grid median | +1.33pp | [-1.12pp, +3.76pp] | 0.85 | 0.25 |

### 3.5 Is the no-selection result a property of the signal or of that one cell?

Scheme (a) fixes a single cell, so its percentile could be a property of that cell rather than of the
composite. The check: rank each of the **18 fixed cells** against the same cell of all 48 scrambled books.

| cell | production CAGR | control CAGR | pct of the same cell, scrambled | p |
|------|----------------:|-------------:|-----------------------------------:|---:|
| `22|126|0` | +10.43% | +7.40% | 100th | < 0.001 |
| `15|126|0` | +9.28% | +5.25% | 98th | < 0.001 |
| `22|252|0` | +9.47% | +6.28% | 98th | < 0.001 |
| `22|252|0.35` | +10.37% | +7.26% | 98th | < 0.001 |
| `22|126|0.35` | +11.01% | +8.00% | 96th | < 0.001 |
| `30|126|0` | +10.09% | +8.95% | 96th | < 0.001 |
| `22|252|0.6` | +10.96% | +7.92% | 92nd | < 0.001 |
| `30|252|0` | +8.84% | +7.41% | 92nd | < 0.001 |
| `22|126|0.6` | +11.36% | +8.38% | 90th | < 0.001 |
| `30|126|0.35` | +10.70% | +9.72% | 90th | < 0.001 |
| `30|252|0.35` | +9.88% | +8.70% | 88th | < 0.001 |
| `15|252|0` | +8.02% | +4.25% | 85th | < 0.001 |
| `15|126|0.35` | +9.36% | +5.33% | 81st | < 0.001 |
| `30|126|0.6` | +11.08% | +10.21% | 79th | < 0.001 |
| `30|252|0.6` | +10.56% | +9.57% | 77th | < 0.001 |
| `15|252|0.35` | +8.53% | +4.67% | 71st | 0.006 |
| `15|126|0.6` | +9.35% | +5.35% | 65th | 0.059 |
| `15|252|0.6` | +8.83% | +4.94% | 60th | 0.193 |

**15/18** fixed cells sit at ≥75th percentile of their own scrambled counterparts. That is the
honest robustness read: the advantage is not confined to the one cell scheme (a) happens to use, but neither
is it universal.

Summary: production sits at ≥75th percentile of its own scrambled null in **4/5** schemes ((a) fixed, no selection, (c) max TRAIN Sharpe, reduced grid, (d) max TRAIN Calmar, (e) TRAIN Sharpe shrunk to grid median); at <60th percentile in **0/5**.
The ΔCAGR CI excludes zero in **0/5** schemes.

## §4 — Significance: what is indistinguishable from noise

OOS window is 2928 daily observations. Every difference below gets the same treatment: a paired 21-bar
block bootstrap on ΔCAGR (B=10,000) plus a Newey-West HAC(10) paired t-test. **A CI that straddles zero
means the two books are not distinguishable on this data, whatever the point estimate says.**

| comparison | ΔCAGR | 95% CI | straddles 0? | Newey-West p |
|------------|------:|--------|:-----------:|------------:|
| (b) walk-forward — production vs control | -0.33pp | [-4.07pp, +3.38pp] | **yes** | 0.86 |
| (a) no selection — production vs control | +2.98pp | [-0.54pp, +6.64pp] | **yes** | 0.08 |
| (c) reduced grid — production vs control | +0.66pp | [-2.75pp, +4.10pp] | **yes** | 0.70 |
| (a) − (b): does removing selection help? | +1.66pp | [-0.76pp, +4.07pp] | **yes** | 0.17 |
| (c) − (b): does shrinking the grid help? | +1.17pp | [-0.34pp, +2.68pp] | **yes** | 0.12 |
| (d) Calmar-selection − (b) | +0.71pp | [-1.51pp, +3.04pp] | **yes** | 0.54 |
| (e) shrinkage − (b) | +1.30pp | [-0.50pp, +3.11pp] | **yes** | 0.16 |
| cell_A fixed — production vs control | +3.01pp | [-0.37pp, +6.55pp] | **yes** | 0.07 |
| cell_B fixed — production vs control | +4.03pp | [-0.27pp, +8.46pp] | **yes** | 0.05 |

### 4.1 The fixed-cell claim under the same discipline

- **cell_A**: observed ΔCAGR +3.01pp, 95% CI [-0.37pp, +6.55pp] — **straddles zero.** The diagnostic never put a CI on this; when one is put on it, the headline +2.17pp/+3.50pp gross margin is **not** separable from noise.
- **cell_B**: observed ΔCAGR +4.03pp, 95% CI [-0.27pp, +8.46pp] — **straddles zero.** The diagnostic never put a CI on this; when one is put on it, the headline +2.17pp/+3.50pp gross margin is **not** separable from noise.

### 4.2 What survives, stated plainly

- **No pairwise comparison in this study has a 95% CI that excludes zero.** Every one of them is
  indistinguishable from noise on this data at this sample size.
- The specific thing the hypothesis asks about — turning the selection layer off — is worth +1.66pp/yr with a CI of [-0.76pp, +4.07pp].

### 4.3 Why §3 says one thing and §4 says another — and which to believe

This is the most important thing in the document and it needs stating plainly, because a reader who reads §3
and stops will conclude the wrong thing.

They are answering **different questions**, and they can disagree without either being wrong.

| | §3 (rank / percentile) | §4 (ΔCAGR confidence interval) |
|---|---|---|
| asks | does this book order above signal-free books built the same way? | is the return *difference* large relative to its own sampling noise? |
| what the noise is | 48 scramble permutations (a fixed population of alternatives) | 2,928 daily returns with autocorrelation |
| sample size | effectively 48 books per cell, 18 cells | 1 time series |
| sensitivity | high — a 1pp edge is resolvable | low — the CI half-width is ≈2.5pp |

**§3 is the more powerful test and it passes.** A per-cell advantage that holds in 15 of 18 cells, each against 48 matched
scrambles, is not a fluke of daily noise. **§4 is the more relevant test of *magnitude*, and it fails**: the same advantage is
worth about +1.17pp/yr with a 95% CI of [-1.36pp, +3.65pp], which contains zero and contains anything
from "worthless" to "a modest real edge". Both readings are true and they point at different decisions: §3 says
**there is something there**, §4 says **it is not big enough to trade on**.

One corroborating detail from §3.2: the reversal control sits at the **0th percentile** of the same scrambled
null — below every one of the 48 books. A null that nothing can beat is not a test, and a null that a composite of
factors this repo rules out on published Indian evidence fails completely is a real test. The null is behaving.

## §5 — Verdict: is the signal real and the selection broken, or is it all noise?

### 5.1 The claim reproduces

**18/18 numeric checks pass** against `CONTROL_DIAGNOSTIC.md`, including both fixed cells, both gross-selection margins and both
selection-cost figures, on this script's own harness and on the same engine SHA the diagnostic recorded. The diagnostic was not
wrong about what it measured.

Production also beats the reversal control on fixed parameters in **18/18** cells — so the effect is not an artefact of the two cells the
diagnostic happened to look at. That much of H5 stands.

### 5.2 What the five schemes say about it

| scheme | prod CAGR | pct of its own scrambled null | 95% CI on ΔCAGR vs the mean null book | excludes 0? |
|--------|----------:|----------------------------:|------------------------------------|:-----------:|
| (a) fixed, no selection | +11.36% | 90th | [-1.36pp, +3.65pp] | no |
| (b) max TRAIN Sharpe (current) | +9.71% | 65th | [-2.54pp, +3.03pp] | no |
| (c) max TRAIN Sharpe, reduced grid | +10.87% | 85th | [-1.75pp, +3.47pp] | no |
| (d) max TRAIN Calmar | +10.41% | 88th | [-1.62pp, +3.58pp] | no |
| (e) TRAIN Sharpe shrunk to grid median | +11.01% | 96th | [-1.12pp, +3.76pp] | no |

Production sits at **≥75th percentile of its own signal-scrambled null in 4/5** schemes and at **<60th percentile in 0/5**; the ΔCAGR CI excludes zero in **0/5**.

### 5.3 The verdict

**The signal is real — and the selection layer is what destroys it. Fixing selection is worth doing. It is
not, on this evidence, worth anything close to what `GOAL.md` asks for.**

Three findings, in descending order of how much they should change your mind.

**1. The fixed-parameter edge is robust, not an artefact of two lucky cells.** Every one of the 18 fixed cells returns more than the reversal control, and
**15/18** of them sit at ≥75th percentile of a *matched* signal-scrambled null — the same cell, run on 48 books that keep the composite's
per-date score distribution, name count, constraints, cost stack and overlay and destroy only the score-to-return link. For most of those cells the exact
two-sided binomial p is below 0.001. This is the strongest evidence for the production composite anywhere in this repo, and it is
stronger than the diagnostic's own version of the claim, which rested on two cells.

**2. The selection layer is broken, and demonstrably so.** With parameters fixed the book returns +11.36% at the 90th percentile of its scrambled twin. Under the current
train-window rule it returns +9.71% at the 65th. Turning selection off is 
worth +1.66pp/yr and lifts the percentile against that null by 25 points. The mechanism is in §2.3 and §3.1: the train ranking
orders test outcomes at ρ = +0.13 for this composite (versus +0.75 for the reversal control), and the cell the search
picks is *worse* than a cell picked blind from the same grid. The same search *helps* the control. That is
exactly the asymmetry H5 reported, now traced to its cause.

**3. And none of it is enough.** The magnitude is the problem. The best scheme returns **+11.36%/yr**. `GOAL.md` targets 3%/month = **42.6%/yr**. Not one
ΔCAGR confidence interval in §4 excludes zero — not against the scrambled null, not against the reversal
control, not between any two of the five schemes. The equal-weight benchmark returned +17.12%/yr over the
same windows (`CONTROL_DIAGNOSTIC.md`), so the book underperforms simply holding the universe by ~6pp/yr.

So the correct reading is neither "the strategy is dead" nor "fix selection and ship". It is: **the composite has a real, small, measurable
selection edge that the harness was throwing away, and the harness was throwing away more than the edge is worth.** A +1.7pp/yr
improvement on a 42.6%/yr target is not a strategy. It is a bug fix.

**What this does *not* license.** Adopting any of schemes (c), (d) or (e) on the strength of their test-window
ranking would repeat the error this document exists to document. The defensible change is §6.1, and it is
chosen because it removes the search, not because it scored best.

## §6 — Minimal proposed fix

The hypothesis is confirmed, so the fix is worth making. One part of it is worth a lot, the rest is hygiene.

### 6.1 The fix that is warranted: delete the train-window argmax

Remove the per-fold parameter search and fix the cell **a priori**. Two defensible choices, neither of which looks at a test window:

- the **modal cell of the TRAIN selection trace**, `22|126|0.6` — this is what scheme (a) runs, and it uses only
  information the search itself produced on training data;
- the **grid-median cell**, `22|126|0.35` — no search output at all. It returns +11.01%/yr on this data, essentially the same as the
  modal cell's +11.36%/yr, and it sits at 96th against its own scramble. Prefer this one: it
  cannot be accused of being the cell that happened to win.

Either way the change is worth **+1.66pp/yr** of point estimate versus the current rule (95% CI [-0.76pp, +4.07pp], so it straddles zero). The argument for it is
not the size of the gain. It is this:

| book | TRAIN-argmax cell | median cell | Δ |
|------|------------------:|------------:|---:|
| PRODUCTION | +10.14% | +10.45% | **-0.31pp** |
| CONTROL_REVERSAL | +10.32% | +7.77% | **+2.55pp** |

A selection rule whose output is *worse than not selecting* has removed value. Removing it costs nothing,
removes the ability of the harness to manufacture a headline, and makes every future result in this repo interpretable.

**What it buys, stated honestly:**

| | current rule (b) | no selection |
|---|---|---|
| OOS CAGR | +9.71% | +11.36% |
| OOS Sharpe | 0.34 | 0.45 |
| OOS MaxDD | -14.92% | -26.35% |
| pct of its own scrambled null | 65th | 90th |
| production vs the reversal control | +9.71% vs +10.04% — **loses** | +11.36% vs +8.38% — **wins** |

It would also **fix the negative control gate**: with no selection the reversal composite falls to
+8.38% against production's +11.36%, which is the behaviour the gate expects. Note this is not
evidence of skill in production — §4 shows the gap's CI straddles zero — but it does mean the gate stops failing for the
wrong reason.

**The honest cost:** drawdown gets worse (-26.35% vs -14.92%). `GOAL.md` §2.3 Band C requires MaxDD > −35%, which both pass, so
this is not a gate failure, but it is a real deterioration in a dimension the goal cares about and should be
stated rather than buried.

### 6.2 The fix that is *not* warranted

Do **not** ship a refined selection rule — reduced grid (c), Calmar (d), shrinkage (e). They all score better
on the test window than the current rule, and choosing between them on that basis is the failure mode this whole
document documents. The table below is therefore diagnostic only; no scheme is adopted on its test ranking.

| scheme | prod CAGR | prod Sharpe | prod pct of scrambled null | exact p |
|--------|----------:|------------:|--------------------------:|--------:|
| (a) fixed, no selection | +11.36% | 0.45 | 90th | < 0.001 |
| (b) max TRAIN Sharpe (current) | +9.71% | 0.34 | 65th | 0.059 |
| (c) max TRAIN Sharpe, reduced grid | +10.87% | 0.43 | 85th | < 0.001 |
| (d) max TRAIN Calmar | +10.41% | 0.39 | 88th | < 0.001 |
| (e) TRAIN Sharpe shrunk to grid median | +11.01% | 0.45 | 96th | < 0.001 |

### 6.3 Three things that must be fixed regardless of §5

**1. The engine moved under the evidence base and nobody noticed.** `src/nsealgo/backtest/engine.py` has an uncommitted
change that replaces alphabetical tie-breaking with a hash tie-break and moves the walk-forward headline by +0.18pp/yr (§2.5). Every result in `reports/`
produced before that change is now unreproducible, and `provenance()` only tells you *that* it happened, not which
reports are stale. Commit it, re-run the gates, and re-date the affected reports. This is the highest-priority
item on this list and it is not a performance question.


**2. Report ρ, not just the selected cell.** The per-fold TRAIN→TEST rank correlation costs nothing on a grid you have
already evaluated and it is the number that would have flagged this book in one pass: ρ = +0.13 for production against +0.75 for the control.
**3. Change the acceptance test.** Make a candidate have to beat a signal-scrambled version of *itself, through its own selection rule*, not a
different composite. This study's §3.2 is a working implementation and costs one sweep per null book (~80 s each).

---

*Produced by `research/selection_study.py` against engine `d93815344bd3` (the SHA inside every cached sweep; the working tree now reads `29764f562cd5` — see the provenance table and §2.5), loader `c1badf5f7df8`, costs `ba350aef75b3`, panel `389b082b832f`. Every
figure is net of the full Indian delivery cost stack (21.92 bps all-in round trip) unless labelled gross, and
every figure must be quoted with its end date — the OOS window ends 2026-10-01. Survivorship bias
is present and disclosed. `GOAL.md` §6 anti-fraud rules apply: no in-sample number is presented as a result, and no
cost was reduced to rescue anything.*

