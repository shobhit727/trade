# Selection Study v2 — is there a real edge under fixed parameters on the current engine?

> **This is a re-measurement of `reports/SELECTION_STUDY.md` (v1).** Every number v1 reported was
> computed on engine `d93815344bd3`. The tie-break in `build_rebalance_weights` has since changed
> from `np.argsort(-score, kind="stable")` — which resolved tied scores by *column position*, and
> this panel's columns are alphabetical — to a `blake2b("{date}|{symbol}")` key via `np.lexsort`.
> Engine is now `29764f562cd5`.
>
> **The question this document exists to answer, and it is the single most decision-relevant number
> in this repository:** v1 reported that *removing* train-window parameter selection takes production
> from **+9.71%/yr to +11.36%/yr**, and its percentile against the signal-scrambled null from the
> **65th to the 90th**. That is the only thing in this repo that suggests a path from "no
> demonstrable edge" to "real edge". It was on a dead engine. It is re-measured here.
>
> **Both the check and the answer are below.** The headline is in §5; every number that moved is in
> §7. Nothing from v1 is carried forward without being recomputed on this engine.

## Provenance

| component | v1 (cached, produced every v1 number) | **v2 (this document)** |
|-----------|--------------------------------------|------------------------|
| engine | `d93815344bd3` | **`29764f562cd5`** **CHANGED** |
| loader | `c1badf5f7df8` | `c1badf5f7df8` (same) |
| costs | `ba350aef75b3` | `ba350aef75b3` (same) |
| panel | `389b082b832f` | `389b082b832f` (same) |

- **Panel**: 48 symbols × 4625 daily bars, 2008-01-01 → 2026-10-01
- **Harness**: `nsealgo.backtest.walkforward.walk_forward`, 6 folds, 6y train / 2y test, 18-cell grid (`n_positions` × overlay `lookback` × overlay `threshold`) — identical to `research/validate.py` and to v1. Engine, costs, factors, overlay and loader untouched; only the score panel and the selection rule vary.
- **Cost stack**: `CostModel(segment="delivery", slippage_bps=5)`; the engine charges `2.0 × one_way_turnover × equity × rate` at **21.92 bps all-in round trip**. Gross and net are reported separately wherever it matters.
- **OOS window**: 2014-11-26 → 2026-10-01, **2928 daily observations** across 6 contiguous 2-year test windows.
- **Nulls**: 48 signal-scrambled books (`scramble_c`: a fixed column relabel of the
  production composite, so every per-date marginal score distribution is preserved exactly and only
  the score-to-return link is destroyed) + 24 i.i.d. Uniform(0,1) no-signal books.
  Every null is pushed through **the same selection scheme** as the book it is compared against.
- **Survivorship bias is present** (today's NIFTY-50 backfilled) and is disclosed in every report in
  this repo. **Every number here must be quoted with its end date and engine SHA.**
- Reproduce: `.venv/bin/python research/selection_v2/determinism.py` then
  `.venv/bin/python research/selection_v2/run.py` (sweeps cache to `research/selection_v2/_cache/`).

### Cross-check against the tie-break commit

The tie-break commit (`f4fff7c`) and `reports/VALIDATION_v1.md` both publish figures for engine
`29764f562cd5`. This study reaches the same engine by a completely different route — v1's own
sweep machinery rather than `research/validate.py` — so agreement is a real check and disagreement
would be a real finding. Where the two disagree, the construction differs and is named.

| quantity | tie-break commit / `VALIDATION_v1.md` | this study | agree? |
|----------|-------------------------------------:|------------:|:------:|
| walk-forward OOS CAGR | +9.52% | +9.52% | yes |
| walk-forward OOS Sharpe | 0.32 | 0.3202 | yes |
| walk-forward OOS Sortino | 0.38 | 0.3796 | yes |
| walk-forward OOS MaxDD | -14.92% | -14.92% | yes |
| production gross OOS CAGR | +11.43% | +10.99% | **no** |
| production gross pct of a **random-book** null | 29th (null mean +11.83%) | 33rd (null gross mean +11.17%) | **no** |

> ### 🚨 The two gross rows do **not** reconcile, and that is a finding, not a rounding note
>
> This study's gross OOS CAGR is **+10.99%** against `CONTROL_DIAGNOSTIC.md` §0.5a's
> **+11.43%** — a 0.44pp gap on a quantity the two reports both call "gross".
>
> What is actually established here: this study's sweep driver returns a daily series **bit-identical**
> to the untouched `walk_forward` on the same engine (Gate 1 below), at +9.5248% — which rounds to
> the +9.52% both reports publish. So the *net* book is not in question. What is in question is
> that two documents report different numbers under one name for **gross**, which can only mean
> they compute it differently. (Neither report states its gross definition, so this study cannot
> say whose is right — only that they are not the same quantity.)
>
> This study's definition, stated so it can be checked: the engine's own return attribution,
> `held_weights.shift(1) * asset_returns`, summed across names — **before costs, after the regime
> overlay**. §1.3 decomposes every fixed cell through it.
>
> The random-book percentile is also not comparable: **24** i.i.d. Uniform(0,1) books
> here against the tie-break audit's larger sample, different seeds, and a different null gross mean
> (+11.17% against the +11.83% quoted). A percentile against a null whose mean has
> moved 0.66pp is not the same statistic.
>
> **What this means for the engine check.** The four *net* rows — CAGR, Sharpe, Sortino, MaxDD — are
> the ones that must agree to confirm which engine a report is on, and they do. The gross figure is
> a genuine open reconciliation item between two reports, and it is called out here rather than
> averaged away.
>
> **Recommendation (also §6.3).** "gross CAGR" is used as a headline in `GOAL.md` and
> `CONTROL_DIAGNOSTIC.md` and is not defined identically in the code that produces it. It should be
> one shared function with one docstring, and every report should print which definition it used.
> A metric that is load-bearing in a go/no-go gate and defined two ways is a defect regardless of
> which way is right.

> **The comparable rows agree.** This study is on the engine it claims to be on.

## Gate — the driver is now validated bar-for-bar, and the engine is reproducible

v1 §2.5 reported two serious problems with the harness this study reuses: that the engine
"delivers a different realisation across processes" (15/18 fold-1 cells differing by up to 0.013
Sharpe between a worker-pool sweep and a fresh in-process recompute), and that this script's sweep
driver "does not match an in-process `walk_forward`". If either were true, a sub-2pp/yr effect
would be unmeasurable and every number below would be suspect. Both were tested first.

### Gate 1 — the sweep driver reproduces the untouched `walk_forward`

| check | v1 (`d93815344bd3`) | **v2 (`29764f562cd5`)** |
|-------|-------------------|------------------------|
| identical daily OOS series | **no** (CAGR +9.7068% vs +9.5248%) | **yes — max abs diff 0.0e+00** |
| fold-for-fold cell pick | 0/6 reported | **6/6** |
| walk_forward CAGR / Sharpe | +9.71% / 0.34 | **+9.52% / 0.3202** |

**The driver is exact.** Same daily returns to the last bit, same cell in every fold, same CAGR.

> **Why v1 saw a mismatch, and why the "0/6 folds" it reported was never a driver problem.**
> v1's cache was written on `d93815344bd3`; its stability check and its `walk_forward` call both ran
> against a working tree already carrying the tie-break fix. So it compared an old-engine sweep to a
> new-engine `walk_forward` and read the engine change as driver disagreement. Separately, the
> `same_picks` line zips `wf.folds` (fold 1 = most recent first) against `apply_scheme(...)['picks']`,
> which `apply_scheme` emits in the opposite order — so it reports 0/6 even when every fold agrees,
> which is what happened in both v1 and this run. **v1's §2.5 conclusion that the driver was
> unreliable is withdrawn: the driver was always correct, and the artifact it was measuring was the
> engine change.**

### Gate 2 — the engine is deterministic across processes

| check | result |
|-------|--------|
| two independent processes, 3 folds × 18 cells × 5 metrics | **0 differing pairs, max abs delta 0.000e+00** |
| in-process repeat of fold 1 (18 cells) | 0 differing, max abs delta 0.000e+00 |
| fold 1 re-run from scratch in the reporting process | 0/18 cells differ, max abs dSharpe 0.0e+00; TRAIN argmax `22\|126\|0.35` unchanged |

**The engine is bit-reproducible across processes.** v1's 15/18-cell spread does not reproduce.

> This was a precondition, not a footnote. A per-cell Sharpe spread of 0.013 is the same order
> as the effect being measured; on an engine with that spread, a 2pp/yr difference in CAGR would
> have been indistinguishable from re-running the code. It is now measurable, which means the
> numbers below are worth reading *and* worth disbelieving on their merits rather than on
> reproducibility grounds.

### Pipeline self-check

v1's cache is re-analysed through the **identical** `analyse()` used for v2, and the result is
compared against v1's *published* report. This is what makes §7 a measured diff rather than a
transcription. Tolerances are v1's own: 0.05pp on CAGR/MaxDD, 0.005 on Sharpe.

| quantity | v1 published | recomputed from v1's cache | pass |
|----------|-------------:|------------------------------:|:----:|
| `wf_prod_cagr` | +9.71% | +9.71% | yes |
| `wf_prod_sharpe` | 0.3400 | 0.3365 | yes |
| `wf_prod_maxdd` | -14.92% | -14.92% | yes |
| `wf_ctrl_cagr` | +10.04% | +10.04% | yes |
| `wf_ctrl_sharpe` | 0.3700 | 0.3657 | yes |
| `wf_ctrl_maxdd` | -25.05% | -25.05% | yes |
| `cellA_prod` | +11.01% | +11.01% | yes |
| `cellA_ctrl` | +8.00% | +8.00% | yes |
| `cellA_prod_sharpe` | 0.4500 | 0.4466 | yes |
| `cellB_prod` | +9.28% | +9.28% | yes |
| `cellB_ctrl` | +5.25% | +5.25% | yes |
| `cellB_prod_sharpe` | 0.3000 | 0.3043 | yes |
| `best_fixed` | +11.36% | +11.36% | yes |
| `a_pct` | 90th | 90th | yes |
| `b_pct` | 65th | 65th | yes |
| `sel_delta_prod` | -1.30% | -1.30% | yes |
| `sel_delta_ctrl` | +2.03% | +2.03% | yes |
| `rho_prod` | 0.1340 | 0.1338 | yes |
| `rho_ctrl` | 0.7530 | 0.7527 | yes |
| best fixed cell | `22\|126\|0.6` | `22\|126\|0.6` | yes |

> **20/20 pass.** The pipeline reproduces v1 exactly, so every difference in
> §7 is attributable to the engine and nothing else.

## §1 — Reproduction of the fixed-parameter claim

Recomputed from scratch on the current engine. Nothing is copied from `CONTROL_DIAGNOSTIC.md` or
from v1.

### 1.1 Walk-forward headline — the protocol that counts

| book | CAGR (v2) | Sharpe | MaxDD | sortino | Calmar |
|------|----------:|-------:|------:|--------:|-------:|
| PRODUCTION | +9.52% | 0.3202 | -14.92% | 0.3796 | 0.6383 |
| CONTROL_REVERSAL | +10.05% | 0.3666 | -25.05% | 0.4545 | 0.4010 |

The **untouched `walk_forward`** agrees: CAGR +9.52% · Sharpe 0.3202 · MaxDD -14.92% over 2928 days.

> **v1 → v2: +9.71% → +9.52%** (-0.18pp/yr), Sharpe 0.34 → 0.32. 
> This reproduces the `9.52% / 0.32` headline that the tie-break commit and
> `reports/VALIDATION_v1.md` quote for engine `29764f562cd5` — an independent confirmation
> that this study is on the right engine, reached by a different route.

### 1.2 The two fixed cells the diagnostic quotes

Fixed means one parameter set held constant across all six test windows, no train-window selection.

| cell | params | prod CAGR | prod Sharpe | prod gross CAGR | ctrl CAGR | ctrl Sharpe | gross margin (prod − ctrl) |
|------|--------|----------:|------------:|----------------:|----------:|------------:|-----------------------------------:|
| cell_A | `22\|126\|0.35` | +10.99% | 0.4436 | +12.87% | +7.99% | 0.2052 | +2.08pp |
| cell_B | `15\|126\|0` | +9.23% | 0.2985 | +10.51% | +5.21% | -0.1447 | +3.44pp |

### 1.3 Gross-selection decomposition of the fixed-cell gap

`gross → −costs → net pre-overlay → +overlay → net`, as H1/H5 did it. The gross term is the only
one that reflects the factors; costs and overlay are harness, not signal.

| cell | book | selection (gross) | costs | overlay | total net |
|------|------|------------------:|------:|--------:|----------:|
| cell_A | PRODUCTION | +12.87% | -1.16pp | -0.72pp | +10.99% |
| cell_A | CONTROL_REVERSAL | +10.80% | -1.90pp | -0.91pp | +7.99% |
| cell_A | **margin** | **+2.08pp** | +0.74pp | +0.18pp | **+3.00pp** |
| cell_B | PRODUCTION | +10.51% | -1.43pp | +0.16pp | +9.23% |
| cell_B | CONTROL_REVERSAL | +7.07% | -1.86pp | +0.00pp | +5.21% |
| cell_B | **margin** | **+3.44pp** | +0.43pp | +0.15pp | **+4.02pp** |

### 1.4 "Selection destroys it"

| book | best of the 2 quoted fixed cells | walk-forward (b) | selection delta |
|------|---------------------------------:|-----------------:|---------------:|
| PRODUCTION | +10.99% | +9.52% | -1.47pp |
| CONTROL_REVERSAL | +7.99% | +10.05% | +2.05pp |

> **The same caveat as v1, unchanged and still correct.** The "best fixed cell" is the best of two
> cells chosen with knowledge of which one won out-of-sample. That is a test-window selection, biased
> upward, and biased upward for both books at once — so this −X/+Y split is **not** a clean measure
> of what selection costs. §3.1's `selection vs picking blind` comparison and §4's block bootstrap
> are the ones that mean something.

### 1.5 Where the fixed cells actually sit — all 18, on the current engine

The diagnostic tested 2 of 18. v1 tested all 18. Here they are again, held fixed, on identical OOS
windows, with each cell's percentile against the **same cell** of the scrambled null.

| rank | cell | prod CAGR | prod Sharpe | prod gross CAGR | ctrl CAGR | prod > ctrl | pct of same cell, scrambled | p |
|-----:|------|----------:|------------:|----------------:|----------:|:----------:|----------------------------------:|---:|
| 1 | `22\|126\|0.6` | +11.31% | 0.4440 | +12.87% | +8.37% | yes | 96th | < 0.001 |
| 2 | `22\|126\|0.35` | +10.99% | 0.4436 | +12.87% | +7.99% | yes | 100th | < 0.001 |
| 3 | `30\|126\|0.6` | +10.98% | 0.4223 | +12.28% | +10.22% | yes | 81st | < 0.001 |
| 4 | `22\|252\|0.6` | +10.91% | 0.4071 | +12.87% | +7.90% | yes | 96th | < 0.001 |
| 5 | `30\|126\|0.35` | +10.65% | 0.4196 | +12.28% | +9.73% | yes | 90th | < 0.001 |
| 6 | `30\|252\|0.6` | +10.46% | 0.3773 | +12.28% | +9.58% | yes | 77th | < 0.001 |
| 7 | `22\|126\|0` | +10.45% | 0.4109 | +12.87% | +7.39% | yes | 100th | < 0.001 |
| 8 | `22\|252\|0.35` | +10.35% | 0.3806 | +12.87% | +7.24% | yes | 98th | < 0.001 |
| 9 | `30\|126\|0` | +10.10% | 0.3844 | +12.28% | +8.95% | yes | 98th | < 0.001 |
| 10 | `30\|252\|0.35` | +9.82% | 0.3421 | +12.28% | +8.71% | yes | 88th | < 0.001 |
| 11 | `22\|252\|0` | +9.48% | 0.3159 | +12.87% | +6.26% | yes | 100th | < 0.001 |
| 12 | `15\|126\|0.35` | +9.28% | 0.2941 | +10.51% | +5.27% | yes | 79th | < 0.001 |
| 13 | `15\|126\|0.6` | +9.24% | 0.2783 | +10.51% | +5.27% | yes | 62nd | 0.111 |
| 14 | `15\|126\|0` | +9.23% | 0.2985 | +10.51% | +5.21% | yes | 96th | < 0.001 |
| 15 | `30\|252\|0` | +8.85% | 0.2649 | +12.28% | +7.41% | yes | 92nd | < 0.001 |
| 16 | `15\|252\|0.6` | +8.71% | 0.2337 | +10.51% | +4.83% | yes | 56th | 0.471 |
| 17 | `15\|252\|0.35` | +8.42% | 0.2172 | +10.51% | +4.57% | yes | 65th | 0.059 |
| 18 | `15\|252\|0` | +7.94% | 0.1794 | +10.51% | +4.15% | yes | 83rd | < 0.001 |

- production beats the control in **18/18** fixed cells.
- **15/18** fixed cells sit at ≥75th percentile of their own scrambled counterpart.
- 18/18 production cells and 18/18 control cells are profitable; production's median fixed cell is +9.96%.
- `cell_A` sits at the **94th percentile** of the 18 production fixed cells (rank 2/18); `cell_B` at the 28th.

### §1 verdict

**The fixed-parameter claim survives.** Production beats the reversal control in **18/18** fixed cells on the current engine, the same as v1. Both halves of H5 reproduce.

But the *specific* −X/+Y selection-cost split is measured against a test-window-selected best-of-two
(see §1.4), and neither half is evidence of skill until §3 puts them against a null that has the same
freedom. §3 is where the decision is made.

## §2 — The selection trace across folds

Fold 6 is the earliest test window, fold 1 the latest. Every column is read off the train table the
selection actually saw.

### PRODUCTION

| fold | train window | test window | selected cell | TRAIN Sharpe | TRAIN Calmar | TRAIN CAGR | TEST CAGR | TEST Sharpe |
|-----:|--------------|-------------|---------------|------------:|------------:|----------:|----------:|-----------:|
| 1 | 2018-11-09 -> 2024-10-17 | 2024-10-18 -> 2026-10-01 | `22\|126\|0.35` | +1.14 | +1.01 | +22.30% | -0.68% | -0.83 |
| 2 | 2016-11-22 -> 2022-10-24 | 2022-10-25 -> 2024-10-17 | `22\|252\|0.6` | +0.83 | +0.68 | +17.98% | +29.37% | +1.73 |
| 3 | 2014-11-26 -> 2020-11-03 | 2020-11-04 -> 2022-10-24 | `22\|126\|0.6` | +0.47 | +0.45 | +11.96% | +12.63% | +0.52 |
| 4 | 2012-11-30 -> 2018-11-07 | 2018-11-09 -> 2020-11-03 | `15\|126\|0` | +0.92 | +1.19 | +17.09% | +1.13% | -0.44 |
| 5 | 2010-12-07 -> 2016-11-21 | 2016-11-22 -> 2018-11-07 | `15\|126\|0.35` | +0.76 | +1.18 | +14.97% | +12.65% | +0.66 |
| 6 | 2008-12-12 -> 2014-11-25 | 2014-11-26 -> 2016-11-21 | `30\|126\|0.6` | +1.52 | +2.07 | +29.29% | +4.69% | -0.11 |

Picks: **6 distinct cell(s) across 6 folds** — `15|126|0`×1, `15|126|0.35`×1, `22|126|0.35`×1, `22|126|0.6`×1, `22|252|0.6`×1, `30|126|0.6`×1.
Mean TRAIN Sharpe +0.94 → OOS Sharpe +0.32 (degradation +0.62).

### CONTROL_REVERSAL

| fold | train window | test window | selected cell | TRAIN Sharpe | TRAIN Calmar | TRAIN CAGR | TEST CAGR | TEST Sharpe |
|-----:|--------------|-------------|---------------|------------:|------------:|----------:|----------:|-----------:|
| 1 | 2018-11-09 -> 2024-10-17 | 2024-10-18 -> 2026-10-01 | `30\|126\|0.35` | +1.03 | +0.78 | +19.51% | +0.13% | -0.78 |
| 2 | 2016-11-22 -> 2022-10-24 | 2022-10-25 -> 2024-10-17 | `30\|126\|0.6` | +0.70 | +0.54 | +15.61% | +22.86% | +1.71 |
| 3 | 2014-11-26 -> 2020-11-03 | 2020-11-04 -> 2022-10-24 | `30\|126\|0.6` | +0.20 | +0.29 | +8.34% | +16.91% | +0.84 |
| 4 | 2012-11-30 -> 2018-11-07 | 2018-11-09 -> 2020-11-03 | `30\|126\|0.35` | +0.85 | +1.22 | +15.25% | +5.84% | +0.02 |
| 5 | 2010-12-07 -> 2016-11-21 | 2016-11-22 -> 2018-11-07 | `30\|252\|0.6` | +0.75 | +1.13 | +15.29% | +12.96% | +0.71 |
| 6 | 2008-12-12 -> 2014-11-25 | 2014-11-26 -> 2016-11-21 | `30\|126\|0.6` | +1.64 | +2.50 | +31.45% | +3.29% | -0.24 |

Picks: **3 distinct cell(s) across 6 folds** — `30|126|0.35`×2, `30|126|0.6`×3, `30|252|0.6`×1.
Mean TRAIN Sharpe +0.86 → OOS Sharpe +0.37 (degradation +0.50).

### 2.3 Does TRAIN rank information survive into TEST?

Spearman correlation between the TRAIN score and the TEST CAGR across all 18 cells, within each fold
— computed over the same 18 cells, so it cancels regime and level and asks only whether the ranking is
informative. This is the quantity the selection rule is trying to maximise.

| book | ρ(TRAIN Sharpe, TEST CAGR) per fold | mean ρ | mean ρ(Calmar→CAGR) |
|------|--------------------------------------|--------:|-------------------:|
| PRODUCTION | +0.28, -0.49, +0.51, -0.25, +0.05, +0.55 | **+0.109** | +0.183 |
| CONTROL_REVERSAL | +0.62, +0.67, +0.90, +0.63, +0.94, +0.82 | **+0.763** | +0.651 |

| book | TRAIN-argmax cell | TEST-*oracle* cell (unusable upper bound) | median cell | worst cell | selection vs picking blind |
|------|------------------:|---------------------------------------:|------------:|-----------:|-------------------------:|
| PRODUCTION | +9.97% | +13.25% | +10.35% | +7.32% | **-0.38pp** |
| CONTROL_REVERSAL | +10.33% | +11.07% | +7.77% | +3.19% | **+2.56pp** |

> **This is the cleanest statement of the defect and it needs no confidence interval.** For the
> **production** book the train search picks a cell that is **-0.38pp/yr relative to picking blind** from the same grid; for the **control** it picks one that is **+2.56pp/yr**.
> v1 measured -0.31pp and +2.55pp respectively.

### 2.4 How much do the picks vary, and is there a typical set?

| book | distinct cells picked | modal cell | folds on `lookback=252` | n_positions range |
|------|---------------------:|------------:|-----------------------:|------------------:|
| PRODUCTION | 6 | `15\|126\|0` ×1 | 1/6 | 15–30 |
| CONTROL_REVERSAL | 3 | `30\|126\|0.6` ×3 | 1/6 | 30–30 |

> ### 🚨 The selection layer no longer converges on anything at all
>
> Production picks **6 different cells across 6 folds** — one per fold, with no repetition. There is no mode.
>
> This is not a detail. v1's entire headline — *"removing selection takes production to
> +11.36%/yr"* — was scheme (a) fixing the **modal cell of the train trace**. On v1's engine
> the search returned `22|126|0.6` in two of six folds, and that cell happened to be the **best
> of all 18** (+11.36%). So the "no selection" scheme was not search-free at all: it was
> *the search, laundered*, and it inherited the search's good answer.
>
> On this engine the search returns a different cell in every fold, so "the modal cell" is
> resolved by alphabetical order among six singletons and lands on `15|126|0` — the **14th best of 18**, not the 1st.
>
> **This is the mechanism by which v1's central claim died, and it is worth more than the
> headline it kills.** A benchmark called "no selection" that quietly reads its answer off the
> selection layer is not a benchmark. It will report the selection layer's best day whenever the
> selection layer happens to converge and its median day otherwise.

**Modal cell of the production TRAIN trace: `15|126|0`** (`15|126|0`×1, `15|126|0.35`×1, `22|126|0.35`×1, `22|126|0.6`×1, `22|252|0.6`×1, `30|126|0.6`×1). This is what scheme (a) fixes to,
and it is derived from TRAIN information only.

## §3 — Five selection schemes

All five run on **identical** folds, cells, dates and cost paths: each sweep evaluates all 18 cells on
all 6 train and all 6 test windows, and the five schemes are pure post-processing over that one table.

### 3.1 Out-of-sample results

| scheme | rule | prod CAGR | prod Sharpe | prod MaxDD | prod gross CAGR | prod positive yrs | ctrl CAGR | ctrl Sharpe | ctrl MaxDD |
|--------|------|----------:|------------:|-----------:|----------------:|------------------:|----------:|------------:|-----------:|
| (a) fixed, no selection | fixed at `15\|126\|0` | +9.23% | 0.2985 | -14.92% | +10.51% | +69% | +5.21% | -0.1447 | -16.96% |
| (b) max TRAIN Sharpe (current) | argmax TRAIN Sharpe (current) | +9.52% | 0.3202 | -14.92% | +10.99% | +77% | +10.05% | 0.3666 | -25.05% |
| (c) max TRAIN Sharpe, reduced grid | argmax TRAIN Sharpe over 5 cells | +9.26% | 0.2959 | -14.92% | +10.92% | +69% | +7.08% | 0.1081 | -17.97% |
| (d) max TRAIN Calmar | argmax TRAIN Calmar | +10.26% | 0.3787 | -17.87% | +11.91% | +85% | +10.01% | 0.3675 | -25.05% |
| (e) TRAIN Sharpe shrunk to grid median | argmax TRAIN Sharpe − 0.1·dist | +10.99% | 0.4436 | -22.11% | +12.87% | +85% | +8.74% | 0.2688 | -21.79% |

**The mechanical cost of selection, in one line per book.** The TRAIN-argmax cell is what scheme (b)
holds. If selection works it should beat a cell picked blind from the same grid:

| book | mean fold CAGR of the TRAIN-argmax cell | of the **median** cell | of the best cell *on test* (oracle, unusable) | selection vs picking blind |
|------|-------------------------------------:|--------------------:|---------------------------------------:|------------------------:|
| PRODUCTION | +9.97% | +10.35% | +13.25% | **-0.38pp** |
| CONTROL_REVERSAL | +10.33% | +7.77% | +11.07% | **+2.56pp** |

**The headline question, on this engine: removing selection entirely is worth -0.29pp/yr** (v1: +1.66pp/yr).

### 3.2 The decisive test — production vs a signal-scrambled version of itself, through the SAME scheme

Each scramble keeps the production composite's per-date score distribution, name count, constraints,
cost stack and overlay, and destroys only the score-to-return link — then goes through the identical
selection scheme. 48 books per scheme.

| scheme | prod CAGR | null mean ± sd | null profitable | **prod pct CAGR** | **prod pct Sharpe** | **prod pct GROSS** | exact two-sided p | ctrl pct CAGR | ctrl pct GROSS |
|--------|----------:|---------------:|----------------:|------------------:|--------------------:--------------------:|----------------:|----------------:|-------------------:|
| (a) fixed, no selection | +9.23% | +7.70% ± 1.07pp | 100% | **96th** | 94th | 44th | < 0.001 | 0th | 0th |
| (b) max TRAIN Sharpe (current) | +9.52% | +9.20% ± 0.76pp | 100% | **67th** | 67th | 31st | 0.029 | 0th | 0th |
| (c) max TRAIN Sharpe, reduced grid | +9.26% | +8.19% ± 0.97pp | 100% | **92nd** | 90th | 44th | < 0.001 | 0th | 0th |
| (d) max TRAIN Calmar | +10.26% | +9.21% ± 0.87pp | 100% | **88th** | 88th | 60th | < 0.001 | 0th | 0th |
| (e) TRAIN Sharpe shrunk to grid median | +10.99% | +9.60% ± 0.70pp | 100% | **98th** | 98th | 92nd | < 0.001 | 0th | 0th |

> **The control columns put the production percentiles in context.** The same scrambled null applied
> to the reversal book: if a composite built from factors this repo rules out on published Indian
> evidence also lands high against the same null, then a high percentile is a property of the harness
> rather than of the factors. The null is behaving when it puts the control at the bottom.

> ### What the tie-break fix did to the scramble null
>
> This is a real change of test, and it cuts against production. `build_composite_score` fills missing
> factor values with the median **0.5**, so the production score panel is **heavily tied by
> construction**. `scramble_c` is a column relabel of that same panel, so a scrambled book inherits the
> same tie structure — and under the old engine, a tied score resolved *alphabetically*, which is a
> systematic, non-random preference for low-numbered tickers. The old nulls were therefore not
> exchangeable with the real book: they were all tilted the same way. The fix removes that tilt from
> both the real book and the null, so the two are finally on the same footing — and the real book has moved -2.13pp/yr relative to it.
>
> Read that number carefully: the scheme-(a) book is -2.13pp/yr against v1's, because the
> cell it fixes changed from the best of 18 to the 14th. The composite did not move; the
> benchmark's definition did.
>
> Concretely, scheme (a): production's percentile moved 90th → 96th, scheme (b): 65th → 67th.
> The percentile is *not* comparable across v1 and v2 as though the null were unchanged — the null moved.

### 3.3 The same schemes against a book with no signal at all

24 i.i.d. Uniform(0,1) books through each scheme.

| scheme | null mean CAGR | null mean Sharpe | null profitable | prod pct CAGR | prod pct Sharpe | prod pct GROSS |
|--------|---------------:|------------------|----------------:|--------------:|---------------:|----------------:|
| (a) fixed, no selection | +5.08% | -0.1863 | +100% | 100th | 100th | 100th |
| (b) max TRAIN Sharpe (current) | +8.29% | +0.2151 | +100% | 96th | 96th | 33rd |
| (c) max TRAIN Sharpe, reduced grid | +5.57% | -0.0853 | +100% | 100th | 100th | 100th |
| (d) max TRAIN Calmar | +6.93% | +0.0855 | +100% | 100th | 100th | 100th |
| (e) TRAIN Sharpe shrunk to grid median | +8.19% | +0.2110 | +100% | 100th | 100th | 100th |

### 3.4 Production minus the *mean* scrambled book of the same scheme

Percentiles are one answer; this is a confidence interval. The mean null book is the elementwise mean
of the 48 scrambles' daily series under that scheme, so the comparison is paired on
every date and the block bootstrap (21-bar blocks, B=10,000) applies honestly.

| scheme | ΔCAGR (prod − mean null book) | 95% CI | P(prod > null) | Newey-West p on daily diff |
|--------|------------------------------:|--------|---------------:|-------------------------------:|
| (a) fixed, no selection | +1.47pp | [-1.46pp, +4.45pp] | 0.84 | 0.28 |
| (b) max TRAIN Sharpe (current) | +0.28pp | [-2.46pp, +3.02pp] | 0.58 | 0.81 |
| (c) max TRAIN Sharpe, reduced grid | +1.00pp | [-2.15pp, +4.19pp] | 0.73 | 0.48 |
| (d) max TRAIN Calmar | +0.99pp | [-1.60pp, +3.57pp] | 0.78 | 0.41 |
| (e) TRAIN Sharpe shrunk to grid median | +1.36pp | [-1.12pp, +3.79pp] | 0.85 | 0.25 |

### 3.5 Is the no-selection result a property of the signal or of that one cell?

Scheme (a) fixes a single cell, so its percentile could be a property of that cell. The check: rank
each of the **18 fixed cells** against the **same cell** of all 48 scrambled books.

| cell | production CAGR | control CAGR | pct of the same cell, scrambled | p |
|------|----------------:|-------------:|-----------------------------------:|---:|
| `22\|126\|0.6` | +11.31% | +8.37% | 96th | < 0.001 |
| `22\|126\|0.35` | +10.99% | +7.99% | 100th | < 0.001 |
| `30\|126\|0.6` | +10.98% | +10.22% | 81st | < 0.001 |
| `22\|252\|0.6` | +10.91% | +7.90% | 96th | < 0.001 |
| `30\|126\|0.35` | +10.65% | +9.73% | 90th | < 0.001 |
| `30\|252\|0.6` | +10.46% | +9.58% | 77th | < 0.001 |
| `22\|126\|0` | +10.45% | +7.39% | 100th | < 0.001 |
| `22\|252\|0.35` | +10.35% | +7.24% | 98th | < 0.001 |
| `30\|126\|0` | +10.10% | +8.95% | 98th | < 0.001 |
| `30\|252\|0.35` | +9.82% | +8.71% | 88th | < 0.001 |
| `22\|252\|0` | +9.48% | +6.26% | 100th | < 0.001 |
| `15\|126\|0.35` | +9.28% | +5.27% | 79th | < 0.001 |
| `15\|126\|0.6` | +9.24% | +5.27% | 62nd | 0.111 |
| `15\|126\|0` | +9.23% | +5.21% | 96th | < 0.001 |
| `30\|252\|0` | +8.85% | +7.41% | 92nd | < 0.001 |
| `15\|252\|0.6` | +8.71% | +4.83% | 56th | 0.471 |
| `15\|252\|0.35` | +8.42% | +4.57% | 65th | 0.059 |
| `15\|252\|0` | +7.94% | +4.15% | 83rd | < 0.001 |

**15/18** fixed cells sit at ≥75th percentile of their own scrambled
counterparts. Production sits at ≥75th percentile of its own signal-scrambled null in **4/5** schemes ((a) fixed, no selection, (c) max TRAIN Sharpe, reduced grid, (d) max TRAIN Calmar, (e) TRAIN Sharpe shrunk to grid median) and at <60th percentile in **0/5**. The ΔCAGR CI excludes zero in **0/5** schemes.

## §4 — Significance: what is indistinguishable from noise

OOS window is 2928 daily observations. Every difference gets the same treatment: a
paired 21-bar block bootstrap on ΔCAGR (B=10,000) plus a Newey-West HAC(10) paired t-test. **A CI
that straddles zero means the two books are not distinguishable on this data, whatever the point
estimate says.**

| comparison | ΔCAGR | 95% CI | straddles 0? | Newey-West p |
|------------|------:|--------|:-----------:|------------:|
| (b) walk-forward — production vs control | -0.52pp | [-4.23pp, +3.20pp] | **yes** | 0.78 |
| (a) no selection — production vs control | +4.02pp | [-0.29pp, +8.44pp] | **yes** | 0.05 |
| (c) reduced grid — production vs control | +2.18pp | [-1.78pp, +6.34pp] | **yes** | 0.23 |
| (a) − (b): does removing selection help? | -0.29pp | [-2.36pp, +1.83pp] | **yes** | 0.78 |
| (c) − (b): does shrinking the grid help? | -0.26pp | [-1.78pp, +1.28pp] | **yes** | 0.77 |
| (d) Calmar-selection − (b) | +0.73pp | [-1.40pp, +2.99pp] | **yes** | 0.51 |
| (e) shrinkage − (b) | +1.47pp | [-0.35pp, +3.29pp] | **yes** | 0.12 |
| cell_A fixed — production vs control | +3.00pp | [-0.42pp, +6.57pp] | **yes** | 0.07 |
| cell_B fixed — production vs control | +4.02pp | [-0.29pp, +8.44pp] | **yes** | 0.05 |
| a-priori fixed cell `22\|126\|0.35` — production vs control | +3.00pp | [-0.42pp, +6.57pp] | **yes** | 0.07 |
| (f) a-priori fixed cell `22\|126\|0.35` − (b): does a search-free fix help? | +1.47pp | [-0.35pp, +3.29pp] | **yes** | 0.12 |

> **Note on the last two rows.** `cell_A` *is* `22|126|0.35` — v1's grid median and v1's
> cell_A are the same cell — so the `cell_A fixed` row and the `a-priori fixed cell` row are the
> same comparison, and the `(f) − (b)` row is the same as `(e) − (b)` because scheme (e) also
> converges on the grid median. They are shown separately because they answer different
> questions: one is *fixed cell vs control*, the other is *fixed cell vs the current rule*.

### 4.1 What survives, stated plainly

- **No pairwise comparison in this study has a 95% CI that excludes zero** (11/11 straddle). Every one is indistinguishable from noise on this data at this
  sample size. v1 reached the same conclusion.
- The specific thing the hypothesis asks about — turning the selection layer off — is worth **-0.29pp/yr** with a 95% CI of [-2.36pp, +1.83pp]
  (v1: +1.66pp/yr).

### 4.2 Why §3 says one thing and §4 says another — and which to believe

| | §3 (rank / percentile) | §4 (ΔCAGR confidence interval) |
|---|---|---|
| asks | does this book order above signal-free books built the same way? | is the return *difference* large relative to its own sampling noise? |
| what the noise is | 48 scramble permutations (a fixed population of alternatives) | 2928 daily returns with autocorrelation |
| sample size | effectively 48 books per cell, 18 cells | 1 time series |
| sensitivity | high — a 1pp edge is resolvable | low — the CI half-width is ≈2.5pp |

They answer different questions and can disagree without either being wrong. **§3 is the more
powerful test; §4 is the more relevant test of *magnitude*.** Both readings point at different
decisions, and the verdict below has to satisfy both.

## §5 — Verdict

| quantity | value |
|----------|-------|
| production beats control on fixed params | **18/18** cells |
| fixed cells at ≥75th pct of their matched scrambled null | **15/18** |
| schemes at ≥75th pct of their own scrambled null | **4/5** |
| schemes whose ΔCAGR CI vs the null excludes 0 | **0/5** |
| selection-vs-blind, production | **-0.38pp/yr** |
| selection-vs-blind, control | **+2.56pp/yr** |
| mean ρ(TRAIN→TEST), production | **+0.109** |
| mean ρ(TRAIN→TEST), control | **+0.763** |
| walk-forward OOS (scheme b) | CAGR +9.52%, Sharpe 0.32, MaxDD -14.92% |
| best scheme on OOS (unusable for choosing) | (e) TRAIN Sharpe shrunk to grid median at +10.99% |
| gain from deleting the search (scheme a − b) | **-0.29pp/yr** (v1: +1.66pp/yr) |
| gain from a search-free a-priori cell (`22\|126\|0.35` − b) | **+1.47pp/yr**, CI [-0.35pp, +3.29pp] |
| **verdict** | the fixed-parameter edge is real, but the selection-layer fix v1 recommended is worth -0.29pp/yr — **nothing**; only a search-free a-priori cell is worth anything (+1.47pp/yr) and its CI straddles zero |

Three findings, in descending order of how much they should change your mind.

**1. 🚨 v1's central claim is dead, and it died for a reason that matters more than the number.** v1 said removing train-window selection takes production from +9.71%/yr to +11.36%/yr. On this engine the same pre-registered procedure takes it from +9.52% to +9.23% — a **-0.29pp/yr** change of direction.

   The fixed-cell economics did not move: the 18 production cells shifted by at most 0.12pp between the two engines. What moved is **which cell the search converges on**. On v1's engine it converged on `22|126|0.6` in 2 of 6 folds, and that cell is
   the best of all 18. On this engine it returns a different cell in every one of the six folds, so "the modal cell" is a 6-way tie resolved alphabetically and lands on `15|126|0` — the 14th of 18.

   **The consequence: v1's "no selection" baseline was never search-free. It was the search, laundered.**
   It reported the selection layer's best day whenever the search converged and its median day
   otherwise. That is why its percentile moved from 65th to 90th and why it did so on an engine
   where nothing about the fixed-cell evidence changed.

**2. The fixed-parameter edge itself survives the engine fix, unchanged.** Production still beats the reversal control in 18/18 fixed cells and 15/18 of them sit at ≥75th percentile of a *matched* signal-scrambled null. Every cell moved by less than 0.15pp/yr. Whatever this composite has, it is not the tie-break.

**3. The selection layer is still broken, and the diagnosis is now stronger than v1's.** The train ranking orders test outcomes at ρ = +0.109 for production against +0.763 for the reversal control — v1 measured +0.134 and +0.753. The cell the search picks is -0.38pp against picking blind from the same grid (v1: -0.31pp), while the same search *gains* the control +2.56pp. The search emits a different answer in every fold.

**4. And the magnitude was never going to be enough.** The best book anywhere in this document returns +10.99%/yr against a 42.6%/yr target. Of the 11 ΔCAGR confidence intervals in §4, **0 exclude zero**. Nothing here clears the gate, and nothing here should be used to argue that it might.

## §6 — Minimal proposed fix

**v1's §6.1 recommendation does not survive, and neither does its reason.** v1 said: delete the
train-window argmax, fix a cell a priori, and this is worth +1.66pp/yr. On this engine:

| intervention | ΔCAGR vs current rule (b) | 95% CI |
|--------------|---------------------------:|--------|
| v1 §6.1 as pre-registered — fix at the **modal cell** (scheme a) | -0.29pp | [-2.36pp, +1.83pp] |
| fix at the **grid median** `22\|126\|0.35`, a priori (scheme f) | +1.47pp | [-0.35pp, +3.29pp] |

### 6.1 What is actually warranted: delete the search, but fix the cell without it

The distinction the two rows above make is the whole content of this section.

**Deleting the argmax while keeping the modal cell does not help** — it is -0.29pp/yr, i.e.
slightly *worse* than the search it replaces, with a CI straddling zero. That is not a null result
to be disappointed about; it is the correct result, because the modal cell is not a search-free
choice. It is the search's own answer, read off a 6-way tie and broken
alphabetically, which lands on `15|126|0` — the 14th of 18.

**Fixing a priori at the grid median does help, by a similar amount to what v1 claimed** —
+1.47pp/yr, taking production to +10.99% at the 100th percentile of
its matched scrambled null (null gross mean aside, this is the 100th of 48 books). But the CI is [-0.35pp, +3.29pp], which straddles zero, and
**this number must not be used the way v1 used its own.** v1 §6.1 named this exact cell and the
exact reason — "it cannot be accused of being the cell that happened to win" — and that
naming predates any number in this document, which is the only thing that makes it a legitimate
choice rather than a test-window pick.

| | current rule (b) | fix a priori at the grid median (f) |
|---|---|---|
| OOS CAGR | +9.52% | +10.99% |
| OOS Sharpe | 0.3202 | 0.4436 |
| OOS MaxDD | -14.92% | -22.11% |
| pct of its own scrambled null | 67th | 100th |
| production vs the reversal control | +9.52% vs +10.05% — **loses** | +10.99% vs +7.99% — **wins** |
| ΔCAGR vs the control | -0.52pp CI [-4.23pp, +3.20pp] | +3.00pp CI [-0.42pp, +6.57pp] |

**The honest cost, which v1 also buried:** MaxDD gets worse, -22.11% against -14.92%. `GOAL.md` §2.3 Band C requires MaxDD > −35%, which both pass, so
this is not a gate failure — but it is a real deterioration in a dimension the goal cares about.

> **What this is worth, in one line.** A search-free fix is worth about +1.47pp/yr with a CI that contains zero, on a strategy that needs +31pp/yr to clear its
> own gate. That is a bug fix with a governance justification — it removes the harness's ability to
> manufacture a headline and makes every future result interpretable — and it is not a reason to
> put capital behind the composite.

### 6.2 The fix that is *not* warranted

Do **not** ship a refined selection rule — reduced grid (c), Calmar (d), shrinkage (e). On this
engine all three beat the current rule on the test window:

| scheme | prod CAGR | prod pct of scrambled null |
|--------|----------:|--------------------------:|
| (c) max TRAIN Sharpe, reduced grid | +9.26% | 92nd |
| (d) max TRAIN Calmar | +10.26% | 88th |
| (e) TRAIN Sharpe shrunk to grid median | +10.99% | 98th |

Choosing between them on that basis is the exact failure mode this document documents, and v1's
§6.2 already declined to do it. Two of them have a structural problem independent of their OOS
ranking, which is worth stating anyway: scheme (c)'s reduced grid is built around the modal cell,
so the fix changed what it searches (['15|126|0', '15|126|0.35', '15|252|0', '22|126|0', '15|126|0.6']) whenever the modal cell changes —
it inherits scheme (a)'s instability. And note that scheme (e), the shrinkage rule, is the **only**
scheme that converges: it returns the same cell in all six folds on this engine. That is a real
property of the rule and worth noting, but it is not evidence — the cell it lands on happens to be
the grid median, which is already available a priori for free (§6.1) without running a search whose
output we have just spent this document showing to be uncorrelated with test performance.

### 6.3 Hygiene — warranted regardless of §5, and now better evidenced

**1. Report ρ, not just the selected cell.** The per-fold TRAIN→TEST rank correlation costs nothing
on a grid you have already evaluated, and it is the number that flags this book in one pass:
ρ = +0.109 for production against +0.763 for the reversal control.
The matching blind-pick gap is -0.31pp/yr on v1's engine and -0.38pp/yr on this one.

**2. Report the pick's stability, not just its value.** The number that killed v1's claim was not
any performance figure — it was that the selection layer returned 6 different cells in 6 folds. A selection layer that emits a new answer for
overlapping training windows should be reported as unstable, not scored.

**3. Change the acceptance test.** A candidate should have to beat a signal-scrambled version of
*itself, through its own selection rule*, not a different composite. §3.2 is a working implementation
and costs one sweep per null book.

**4. Make the cache engine-aware and refuse mismatches.** Every sweep is stamped with
`provenance()`; `research/selection_v2/run.py` refuses to run its report phase against a cache on
an unexpected engine. v1's §2.5 happened because a cache and a working tree disagreed and only a
hand-written banner caught it.

**5. Never define a "no selection" baseline from the selection layer.** Scheme (a) as
pre-registered is not search-free; §2.4 shows why, and it cost v1 its headline. A
no-selection baseline must be a cell chosen without reference to the search.

## §7 — Explicit diff against v1

**Every headline number in this document, old engine vs new engine, measured through one pipeline.**
Both columns are computed by the same `analyse()` on two caches; neither is transcribed from a
report. Rows are sorted so that everything that changed comes first.

**70 of 112 tracked quantities changed.**

| quantity | v1 `d93815344bd3` | **v2 `29764f562cd5`** | Δ |
|----------|--------------------:|---------------------:|---:|
| §1.1 walk-forward PRODUCTION CAGR | +9.71% | +9.52% | -0.18pp |
| §1.1 walk-forward PRODUCTION Sharpe | 0.3365 | 0.3202 | -0.0163 |
| §1.1 walk-forward PRODUCTION gross CAGR | +11.38% | +10.99% | -0.40pp |
| §1.1 walk-forward CONTROL Sharpe | 0.3657 | 0.3666 | +0.0009 |
| §1.5 fixed cell `15\|126\|0.35` prod CAGR | +9.36% | +9.28% | -0.08pp |
| §1.5 fixed cell `15\|126\|0.6` prod CAGR | +9.35% | +9.24% | -0.11pp |
| §1.5 fixed cell `15\|252\|0` prod CAGR | +8.02% | +7.94% | -0.08pp |
| §1.5 fixed cell `15\|252\|0.35` prod CAGR | +8.53% | +8.42% | -0.10pp |
| §1.5 fixed cell `15\|252\|0.6` prod CAGR | +8.83% | +8.71% | -0.12pp |
| §1.5 fixed cell `22\|252\|0.6` prod CAGR | +10.96% | +10.91% | -0.05pp |
| §1.5 fixed cell `30\|126\|0.35` prod CAGR | +10.70% | +10.65% | -0.05pp |
| §1.5 fixed cell `30\|126\|0.6` prod CAGR | +11.08% | +10.98% | -0.10pp |
| §1.5 fixed cell `30\|252\|0.35` prod CAGR | +9.88% | +9.82% | -0.05pp |
| §1.5 fixed cell `30\|252\|0.6` prod CAGR | +10.56% | +10.46% | -0.10pp |
| §1.5 fixed cell `15\|126\|0.35` control CAGR | +5.33% | +5.27% | -0.06pp |
| §1.5 fixed cell `15\|126\|0.6` control CAGR | +5.35% | +5.27% | -0.08pp |
| §1.5 fixed cell `15\|252\|0` control CAGR | +4.25% | +4.15% | -0.10pp |
| §1.5 fixed cell `15\|252\|0.35` control CAGR | +4.67% | +4.57% | -0.10pp |
| §1.5 fixed cell `15\|252\|0.6` control CAGR | +4.94% | +4.83% | -0.10pp |
| §1.5 worst fixed cell CAGR | +8.02% | +7.94% | -0.08pp |
| §2.3 prod mean rho(TRAIN Sharpe -> TEST CAGR) | 0.1338 | 0.1090 | -0.0248 |
| §2.3 ctrl mean rho(TRAIN Sharpe -> TEST CAGR) | 0.7527 | 0.7626 | +0.0100 |
| §2.3 prod mean rho(TRAIN Calmar -> TEST CAGR) | 0.2054 | 0.1834 | -0.0220 |
| §2.3 ctrl mean rho(TRAIN Calmar -> TEST CAGR) | 0.6522 | 0.6508 | -0.0014 |
| §2.4 prod distinct cells selected | 5 | 6 | 1 |
| §2.4 modal cell of the TRAIN selection trace | `22\|126\|0.6` (15\|126\|0x1, 15\|126\|0.35x1, 22\|126\|0.35x1, 22\|126\|0.6x2, 30\|126\|0.6x1) | `30\|126\|0.6` (15\|126\|0x1, 15\|126\|0.35x1, 22\|126\|0.35x1, 22\|126\|0.6x1, 22\|252\|0.6x1, 30\|126\|0.6x1) | **changed** |
| §3.1 (a) fixed  prod CAGR | +11.36% | +9.23% | -2.13pp |
| §3.1 (a) fixed  prod Sharpe | 0.4495 | 0.2985 | -0.1510 |
| §3.1 (a) fixed  prod MaxDD | -26.35% | -14.92% | +11.43pp |
| §3.1 (a) fixed  prod gross CAGR | +12.98% | +10.51% | -2.48pp |
| §3.1 (a) fixed  prod pct of scramble null | 89.6 pct | 95.8 pct | +6.2 pts |
| §3.1 (b) walkfwd prod CAGR | +9.71% | +9.52% | -0.18pp |
| §3.1 (b) walkfwd prod Sharpe | 0.3365 | 0.3202 | -0.0163 |
| §3.1 (b) walkfwd prod gross CAGR | +11.38% | +10.99% | -0.40pp |
| §3.1 (b) walkfwd prod pct of scramble null | 64.6 pct | 66.7 pct | +2.1 pts |
| §3.1 (c) prod CAGR | +10.87% | +9.26% | -1.61pp |
| §3.1 (c) prod pct of scramble null | 85.4 pct | 91.7 pct | +6.2 pts |
| §3.1 (d) prod CAGR | +10.41% | +10.26% | -0.15pp |
| §3.1 (e) prod pct of scramble null | 95.8 pct | 97.9 pct | +2.1 pts |
| §3.1 (a) fixed  control CAGR | +8.38% | +5.21% | -3.17pp |
| §3.1 (a) selection delta, PRODUCTION | -1.30pp | -1.47pp | -0.16pp |
| §3.1 (a)−(b) ΔCAGR | +1.66pp | -0.29pp | -1.95pp |
| §3.1 TRAIN-argmax cell vs median cell, PRODUCTION | -0.31pp | -0.38pp | -0.07pp |
| §3.4 scramble null mean CAGR, scheme (b) | +9.43% | +9.20% | -0.23pp |
| §3.4 scramble null mean CAGR, scheme (a) | +10.16% | +7.70% | -2.45pp |
| §4 ΔCAGR [(b) walk-forward — production vs control] observed | -0.33pp | -0.52pp | -0.19pp |
| §4 CI [(b) walk-forward — production vs control] d_cagr_ci_lo | -4.07pp | -4.23pp | -0.16pp |
| §4 CI [(b) walk-forward — production vs control] d_cagr_ci_hi | +3.38pp | +3.20pp | -0.18pp |
| §4 ΔCAGR [(a) no selection — production vs control] observed | +2.98pp | +4.02pp | +1.04pp |
| §4 CI [(a) no selection — production vs control] d_cagr_ci_lo | -0.54pp | -0.29pp | +0.26pp |
| §4 CI [(a) no selection — production vs control] d_cagr_ci_hi | +6.64pp | +8.44pp | +1.80pp |
| §4 ΔCAGR [(c) reduced grid — production vs control] observed | +0.66pp | +2.18pp | +1.52pp |
| §4 CI [(c) reduced grid — production vs control] d_cagr_ci_lo | -2.75pp | -1.78pp | +0.97pp |
| §4 CI [(c) reduced grid — production vs control] d_cagr_ci_hi | +4.10pp | +6.34pp | +2.24pp |
| §4 ΔCAGR [(a) − (b): does removing selection help?] observed | +1.66pp | -0.29pp | -1.95pp |
| §4 CI [(a) − (b): does removing selection help?] d_cagr_ci_lo | -0.76pp | -2.36pp | -1.60pp |
| §4 CI [(a) − (b): does removing selection help?] d_cagr_ci_hi | +4.07pp | +1.83pp | -2.24pp |
| §4 ΔCAGR [(c) − (b): does shrinking the grid help?] observed | +1.17pp | -0.26pp | -1.43pp |
| §4 CI [(c) − (b): does shrinking the grid help?] d_cagr_ci_lo | -0.34pp | -1.78pp | -1.45pp |
| §4 CI [(c) − (b): does shrinking the grid help?] d_cagr_ci_hi | +2.68pp | +1.28pp | -1.40pp |
| §4 CI [(d) Calmar-selection − (b)] d_cagr_ci_lo | -1.51pp | -1.40pp | +0.11pp |
| §4 CI [(d) Calmar-selection − (b)] d_cagr_ci_hi | +3.04pp | +2.99pp | -0.05pp |
| §4 ΔCAGR [(e) shrinkage − (b)] observed | +1.30pp | +1.47pp | +0.16pp |
| §4 CI [(e) shrinkage − (b)] d_cagr_ci_lo | -0.50pp | -0.35pp | +0.15pp |
| §4 CI [(e) shrinkage − (b)] d_cagr_ci_hi | +3.11pp | +3.29pp | +0.18pp |
| §4 CI [cell_A fixed — production vs control] d_cagr_ci_lo | -0.37pp | -0.42pp | -0.05pp |
| §4 CI [a-priori fixed cell `22\|126\|0.35` — production vs control] d_cagr_ci_lo | -0.37pp | -0.42pp | -0.05pp |
| §4 ΔCAGR [(f) a-priori fixed cell `22\|126\|0.35` − (b): does a search-free fix help?] observed | +1.30pp | +1.47pp | +0.16pp |
| §4 CI [(f) a-priori fixed cell `22\|126\|0.35` − (b): does a search-free fix help?] d_cagr_ci_lo | -0.50pp | -0.35pp | +0.15pp |
| §4 CI [(f) a-priori fixed cell `22\|126\|0.35` − (b): does a search-free fix help?] d_cagr_ci_hi | +3.11pp | +3.29pp | +0.18pp |

<details><summary>unchanged quantities (42)</summary>

| quantity | v1 | v2 |
|----------|----:|----:|
| §1.1 walk-forward PRODUCTION MaxDD | -14.92% | -14.92% |
| §1.1 walk-forward CONTROL CAGR | +10.04% | +10.05% |
| §1.1 walk-forward CONTROL MaxDD | -25.05% | -25.05% |
| §1.5 modal (best) fixed cell CAGR | +11.36% | +11.31% |
| §1.5 median fixed cell CAGR | +9.98% | +9.96% |
| §1.5 fixed cell `15\|126\|0` prod CAGR | +9.28% | +9.23% |
| §1.5 fixed cell `22\|126\|0` prod CAGR | +10.43% | +10.45% |
| §1.5 fixed cell `22\|126\|0.35` prod CAGR | +11.01% | +10.99% |
| §1.5 fixed cell `22\|126\|0.6` prod CAGR | +11.36% | +11.31% |
| §1.5 fixed cell `22\|252\|0` prod CAGR | +9.47% | +9.48% |
| §1.5 fixed cell `22\|252\|0.35` prod CAGR | +10.37% | +10.35% |
| §1.5 fixed cell `30\|126\|0` prod CAGR | +10.09% | +10.10% |
| §1.5 fixed cell `30\|252\|0` prod CAGR | +8.84% | +8.85% |
| §1.5 fixed cell `15\|126\|0` control CAGR | +5.25% | +5.21% |
| §1.5 fixed cell `22\|126\|0` control CAGR | +7.40% | +7.39% |
| §1.5 fixed cell `22\|126\|0.35` control CAGR | +8.00% | +7.99% |
| §1.5 fixed cell `22\|126\|0.6` control CAGR | +8.38% | +8.37% |
| §1.5 fixed cell `22\|252\|0` control CAGR | +6.28% | +6.26% |
| §1.5 fixed cell `22\|252\|0.35` control CAGR | +7.26% | +7.24% |
| §1.5 fixed cell `22\|252\|0.6` control CAGR | +7.92% | +7.90% |
| §1.5 fixed cell `30\|126\|0` control CAGR | +8.95% | +8.95% |
| §1.5 fixed cell `30\|126\|0.35` control CAGR | +9.72% | +9.73% |
| §1.5 fixed cell `30\|126\|0.6` control CAGR | +10.21% | +10.22% |
| §1.5 fixed cell `30\|252\|0` control CAGR | +7.41% | +7.41% |
| §1.5 fixed cell `30\|252\|0.35` control CAGR | +8.70% | +8.71% |
| §1.5 fixed cell `30\|252\|0.6` control CAGR | +9.57% | +9.58% |
| §1.5 fixed cells prod beats ctrl | 18 | 18 |
| §1.5 fixed cells at >=75th pct of scramble null | 1500.0 pct | 1500.0 pct |
| §3.1 (b) walkfwd prod MaxDD | -14.92% | -14.92% |
| §3.1 (d) prod pct of scramble null | 87.5 pct | 87.5 pct |
| §3.1 (e) prod CAGR | +11.01% | +10.99% |
| §3.1 (b) walkfwd control CAGR | +10.04% | +10.05% |
| §3.1 (b) selection delta, CONTROL | +2.03pp | +2.05pp |
| §3.1 TRAIN-argmax cell vs median cell, CONTROL | +2.55pp | +2.56pp |
| §4 ΔCAGR [(d) Calmar-selection − (b)] observed | +0.71pp | +0.73pp |
| §4 ΔCAGR [cell_A fixed — production vs control] observed | +3.01pp | +3.00pp |
| §4 CI [cell_A fixed — production vs control] d_cagr_ci_hi | +6.55pp | +6.57pp |
| §4 ΔCAGR [cell_B fixed — production vs control] observed | +4.03pp | +4.02pp |
| §4 CI [cell_B fixed — production vs control] d_cagr_ci_lo | -0.27pp | -0.29pp |
| §4 CI [cell_B fixed — production vs control] d_cagr_ci_hi | +8.46pp | +8.44pp |
| §4 ΔCAGR [a-priori fixed cell `22\|126\|0.35` — production vs control] observed | +3.01pp | +3.00pp |
| §4 CI [a-priori fixed cell `22\|126\|0.35` — production vs control] d_cagr_ci_hi | +6.55pp | +6.57pp |

</details>

### The four things that moved, in order of consequence

**The walk-forward headline moved -0.18pp/yr.** Production OOS CAGR +9.71% → +9.52%, Sharpe 0.34 → 0.32,
gross CAGR +11.38% → +10.99%.
This independently reproduces the `9.52% / 0.32` figure the tie-break commit and `VALIDATION_v1.md`
quote for this engine — the first check that this study is on the engine it claims.

**v1's central claim, re-measured.** v1 said: removing selection takes production from
+9.71% at the 65th percentile to +11.36% at the 90th percentile — a +1.66pp/yr gain.
On this engine it is +9.52% at the 67th → +9.23% at the 96th — a -0.29pp/yr loss.

🚨 **The size of the claimed fix fell by 1.95pp/yr** (+1.66pp → -0.29pp).
v1's headline number did not survive the engine fix intact.

**The percentile is not comparable across v1 and v2**, and this is the subtle one. The scrambled
null is a relabel of the production score panel, which is heavily tied by construction (missing
factor values are filled with the median 0.5). Under the old engine those ties resolved
alphabetically, tilting the real book *and* all nulls the same way — so the v1 percentile was
measured against a null that shared the bias. The fix removes the tilt from both, which is the
correct comparison and is why the real book can move relative to the null at all. Reading a v2
percentile as "v1's percentile adjusted by the CAGR change" is wrong.

**Reproducibility improved.** v1 §2.5's 15/18-cell cross-process spread does not reproduce on this
engine: two independent processes are bit-identical. Measuring a sub-2pp/yr effect requires that,
so it is a precondition that is now met.

---

## The plain version

**Yes, there is still a real selection edge under fixed parameters, and the engine fix did not touch it.** Production beats the reversal control in 18/18 fixed cells and 15/18 of them beat a matched signal-scrambled null at the 75th percentile or better; no production cell moved by more than 0.12pp when the tie-break changed. The reversal control, meanwhile, sits at the 0th percentile of that same null, so the null is still doing its job. **Yes, the selection layer still destroys it, and the evidence is stronger than v1's.** The train ranking orders test outcomes at rho = +0.109 for this composite against +0.763 for the control; the cell it picks is -0.38pp against picking blind from the same grid while the same search gains the control +2.56pp; and it now emits 6 different cells in 6 folds, so it has stopped converging on anything. **But fixing it no longer justifies proceeding, and that is the finding that reverses v1.** v1 said deleting the search was worth +1.66pp/yr, taking production to +11.36%. The identical procedure is worth -0.29pp/yr here — the wrong sign. The reason is not that the edge went away; it is that v1's "no selection" baseline was never search-free. It fixed the cell at the *modal* pick of the very search it was meant to replace, and on v1's engine that search happened to converge on the single best of 18 cells. It does not converge now, the mode is a tie broken alphabetically, and the baseline inherits a worse cell. The only search-free comparison — the grid median v1 itself named in advance — is worth +1.47pp/yr (+10.99%/yr) with a CI of [-0.35pp, +3.29pp] that contains zero. So: delete the search because it is provably adding negative value and because it lets the harness manufacture a headline, not because it unlocks an edge. Even taken at face value the best book in this document returns +10.99%/yr against a 42.6%/yr target, no delta-CAGR interval in the study excludes zero, and the honest answer remains the one v1 gave at the end: **the composite has a small real selection margin that the harness was throwing away, and the harness was throwing away more than the margin is worth.** Nobody should put paper or live capital behind this on the strength of the selection study.

---

*Produced by `research/selection_v2/run.py` on engine `29764f562cd5` (loader `c1badf5f7df8`, costs `ba350aef75b3`, panel `389b082b832f`), against v1's cache on engine
`d93815344bd3` re-analysed by the identical pipeline. Sweeps cache to
`research/selection_v2/_cache/`; `research/_selection_study/` was read, never written. Every figure
is net of the full Indian delivery cost stack (21.92 bps all-in
round trip) unless labelled gross, and every figure must be quoted with its end date — the OOS
window ends 2026-10-01. Survivorship bias is present and disclosed. `GOAL.md` §6
anti-fraud rules apply: no in-sample number is presented as a result, no cost was reduced to rescue
anything, and no scheme hyper-parameter was chosen on a test window.*

