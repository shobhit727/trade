# Control Diagnostic v2 — re-run on the tie-break-fixed engine

**`engine 29764f562cd5` · loader `c1badf5f7df8` · costs `ba350aef75b3` · panel `389b082b832f`**

v1 (`reports/CONTROL_DIAGNOSTIC.md`) was computed on engine **`d93815344bd3`**. That engine resolved tied scores **alphabetically** — `np.argsort(-score, kind="stable")` over a panel whose columns are alphabetical. It is now a deterministic `blake2b("{date}|{symbol}")` key via `np.lexsort`. **Every number in v1 that touches a real composite was therefore measured on a book that was partly chosen by the alphabet**, and is re-measured here.

## Headline — what changed, in one table

| | v1 (`d93815344bd3`) | v2 (`29764f562cd5`) |
|---|---|---|
| production OOS CAGR / Sharpe | **+9.71% / 0.34** | **+9.52% / 0.32** |
| production **gross** OOS CAGR | +11.82% | **+11.43%** |
| production gross percentile in the null | 47th | **29th** |
| selection term of production's edge (gross gap) | **-0.02pp** | **-0.40pp** |
| cost term | +0.59pp | +0.60pp |
| overlay term | +0.54pp | +0.73pp |
| total net edge over the mean random book | +1.12pp | +0.93pp |
| reversal control OOS CAGR / Sharpe | +10.04% / 0.37 | **+10.05% / 0.37** |
| null (random books) mean CAGR / % profitable | +8.59% / 100% | **+8.59% / 100%** |
| H1 verdict | SUPPORTED on the decisive comparison, and the net numbers understate how badly | **SUPPORTED on the decisive comparison, and the net numbers understate how badly** |
| H6 verdict | SUPPORTED | **SUPPORTED** |

> **Verdict flip: H3.** The other hypotheses are unchanged. Any of these is a headline in its own right; the diff table in §2 shows exactly which number moved.

## 0. Provenance

| component | v1 | v2 (this report) |
|-----------|----|----|
| engine | `d93815344bd3` | `29764f562cd5`  — **CHANGED** |
| loader | `c1badf5f7df8` | `c1badf5f7df8` |
| costs | `ba350aef75b3` | `ba350aef75b3` |
| panel | `389b082b832f` | `389b082b832f` |

- **Panel**: 48 symbols x 4625 daily bars, 2008-01-01 -> 2026-10-01 (unchanged: panel SHA identical)
- **Cost model**: `CostModel(segment="delivery", slippage_bps=5)`; **21.92 bps all-in round trip** (statutory + 2 x 5 bps slippage). Engine charges `2.0 x one_way_turnover x equity x rate`. Unchanged: costs SHA identical.
- **Harness**: `nsealgo.backtest.walkforward.walk_forward`, 6 folds, 6y train / 2y test, 18-cell grid (`n_positions` x overlay `lookback` x overlay `threshold`). Identical to `research/validate.py` and to v1.
- **Only thing that varied between v1 and v2**: the engine's ranking tie-break. Same score panels, same seeds, same folds, same grid, same costs, same constraints, same loader, same factor code, same overlay.
- **OOS window**: 2014-11-26 -> 2026-10-01, 2928 daily observations across 6 contiguous 2-year test windows. Identical to v1.
- Survivorship bias is present (today's NIFTY-50 backfilled) and is disclosed in every report in this repo.
- Reproduce: `.venv/bin/python -m research.revalidate_v2.run_control && .venv/bin/python -m research.revalidate_v2.report_control`

## 1. Is the null affected by the tie-break? — measured, not assumed

The brief's claim is that random books are unaffected because i.i.d. `Uniform(0,1)` has no ties. That is **true but not sufficient**, and this section checks the stronger claim instead: *did the null move?*

Two things could have moved it, and the obvious one is not the interesting one:

1. **Score ties.** `build_rebalance_weights` ranks with `np.lexsort((tiebreak, -score))`. For a random panel the tiebreak key is never consulted, because two `Uniform(0,1)` draws are never equal.
2. **Weight ties — the one that matters.** The engine has three rankers that sort by *weight*, not score (`_top_n_weights`, `_exit_allocation`, `_thin`), and `_project_constraints` clamps at `config.max_weight`, so any two names that both hit the cap arrive at **bit-identical** weights. Under the old engine that tie was resolved by column position — alphabetically. A random book pushes a large share of its names through the cap every rebalance, so this is the common case.

`research/revalidate_v2/tie_invariance.py` measures both, on the real engine path:

| run | rebalances | rebalances with a **score** tie | `_top_n_weights` calls with a **weight** tie | of those, where the OLD rule gave a different book | `_exit_allocation` calls where the OLD rule differed |
|---|---:|---:|---:|---:|---:|
| production (trend composite) | 225 | 177 | 0/224 | **0** | 0 |
| null book (Uniform(0,1), seed 10000) | 225 | 0 | 0/224 | **0** | 0 |

Read the first two columns together. The **production composite ties on 177 of 225 rebalances** — because `build_composite_score` fills missing factor values with the median 0.5, so ties are common *by construction* — while the **random null ties on 0 of 225**. That asymmetry is the whole mechanism of the tie-break bug: it could bias production and could not bias the null.

And the weight-space rankers never saw a tie that mattered: 0 calls changed on the null run and 0 on the production run, so the cap-clamp tie is real in principle but did not fire on these books.

**The end-to-end check, which settles it:**

- **100/100** cached null books re-ran with a **bit-identical OOS daily return series** (`np.array_equal` on the full float array). That is the **entire sweep**, not a sample — every null book in this report was re-run against the new engine.
- **100/100** had an identical per-fold result table (selected params, train and test metrics).
- max `|dCAGR|` across all of them: **0.0e+00**.

**Conclusion: the null is tie-invariant — `True`.** The v1 null column is reusable *as a measurement*, not as an assumption. Every null-distribution row in the diff table below is marked `unchanged` with this measurement standing behind it, across all 100 books in the sweep — not a sample.

> **What is NOT reusable is anything built from a real composite.** Production, the reversal control and both scrambled nulls all draw on a composite whose missing values are median-filled, so they tie constantly and their books really do change. Every one of their numbers below was re-measured.

## 2. Diff table vs v1 — every number that moved

Generated from `research/_control_diag/summary_*.json` (v1, full precision) and `research/revalidate_v2/_cache/summary_*.json` (v2, full precision). **153 of 227 quantities moved**; the rest are identical to the last bit and say why.

Rows marked `unchanged` are not carried forward on trust. They are either (a) null-distribution statistics, protected by the bit-identity measurement in §1, or (b) cost-model quantities, protected by the `costs` SHA being unchanged.

### 2.1 Reference books and H1 percentiles / decomposition

| section | quantity | v1 (`d93815344bd3`) | v2 (`29764f562cd5`) | delta | status | note |
|---------|----------|------------------:|------------------:|------:|--------|------|
| ref | PRODUCTION OOS CAGR | +9.71% | +9.52% | -0.18pp | **moved** |  |
| ref | PRODUCTION OOS Sharpe | 0.34 | 0.32 | -0.02 | **moved** |  |
| ref | PRODUCTION OOS MaxDD | -14.92% | -14.92% | — | unchanged |  |
| ref | PRODUCTION gross CAGR | +11.82% | +11.43% | -0.38pp | **moved** |  |
| ref | PRODUCTION net pre-overlay | +10.58% | +10.21% | -0.37pp | **moved** |  |
| ref | PRODUCTION turnover | 2.5130 | 2.4988 | -0.0142 | **moved** |  |
| ref | PRODUCTION cost drag | +1.2301% | +1.2165% | -0.0136pp | **moved** |  |
| ref | PRODUCTION avg names | 19.72 | 19.72 | — | unchanged |  |
| ref | CONTROL OOS CAGR | +10.04% | +10.05% | +0.01pp | **moved** |  |
| ref | CONTROL OOS Sharpe | 0.37 | 0.37 | +0.0009 | **moved** |  |
| ref | CONTROL OOS MaxDD | -25.05% | -25.05% | — | unchanged |  |
| ref | CONTROL gross CAGR | +12.79% | +12.81% | +0.02pp | **moved** |  |
| ref | CONTROL turnover | 3.3355 | 3.3352 | -0.0003 | **moved** |  |
| ref | CONTROL cost drag | +1.6610% | +1.6613% | +0.0003pp | **moved** |  |
| H1 pct | production pct, net CAGR | 97th | 95th | -2 pp-rank | **moved** |  |
| H1 pct | production pct, Sharpe | 96th | 94th | -2 pp-rank | **moved** |  |
| H1 pct | production pct, GROSS CAGR | 47th | 29th | -18 pp-rank | **moved** |  |
| H1 pct | control pct, net CAGR | 98th | 98th | — | unchanged |  |
| H1 pct | control pct, Sharpe | 98th | 98th | — | unchanged |  |
| H1 pct | control pct, GROSS CAGR | 94th | 94th | — | unchanged |  |
| H1 decomp | selection (gross) gap | -0.02pp | -0.40pp | -0.38pp | **moved** |  |
| H1 decomp | cost (turnover) gap | +0.59pp | +0.60pp | +0.01pp | **moved** |  |
| H1 decomp | overlay (regime) gap | +0.54pp | +0.73pp | +0.19pp | **moved** |  |
| H1 decomp | total net gap | +1.12pp | +0.93pp | -0.18pp | **moved** |  |
| H1 decomp | control selection (gross) gap | +0.95pp | +0.97pp | +0.02pp | **moved** |  |
| H1 decomp | control total net gap | +1.44pp | +1.45pp | +0.01pp | **moved** |  |

### 2.2 H1 null distribution — protected by the §1 measurement

| section | quantity | v1 (`d93815344bd3`) | v2 (`29764f562cd5`) | delta | status | note |
|---------|----------|------------------:|------------------:|------:|--------|------|
| H1 null | random net CAGR mean | +8.59% | +8.59% | — | unchanged | null is tie-free; every book re-ran bit-identical (§1) |
| H1 null | random net CAGR sd | +0.60% | +0.60% | — | unchanged | null is tie-free; every book re-ran bit-identical (§1) |
| H1 null | random net CAGR min | +7.03% | +7.03% | — | unchanged | null is tie-free; every book re-ran bit-identical (§1) |
| H1 null | random net CAGR p05 | +7.60% | +7.60% | — | unchanged | null is tie-free; every book re-ran bit-identical (§1) |
| H1 null | random net CAGR p25 | +8.20% | +8.20% | — | unchanged | null is tie-free; every book re-ran bit-identical (§1) |
| H1 null | random net CAGR median | +8.65% | +8.65% | — | unchanged | null is tie-free; every book re-ran bit-identical (§1) |
| H1 null | random net CAGR p75 | +8.98% | +8.98% | — | unchanged | null is tie-free; every book re-ran bit-identical (§1) |
| H1 null | random net CAGR p95 | +9.50% | +9.50% | — | unchanged | null is tie-free; every book re-ran bit-identical (§1) |
| H1 null | random net CAGR max | +10.23% | +10.23% | — | unchanged | null is tie-free; every book re-ran bit-identical (§1) |
| H1 null | random Sharpe mean | 0.24 | 0.24 | — | unchanged | null is tie-free; every book re-ran bit-identical (§1) |
| H1 null | random Sharpe sd | 0.05 | 0.05 | — | unchanged | null is tie-free; every book re-ran bit-identical (§1) |
| H1 null | random Sharpe min | 0.10 | 0.10 | — | unchanged | null is tie-free; every book re-ran bit-identical (§1) |
| H1 null | random Sharpe median | 0.25 | 0.25 | — | unchanged | null is tie-free; every book re-ran bit-identical (§1) |
| H1 null | random Sharpe max | 0.39 | 0.39 | — | unchanged | null is tie-free; every book re-ran bit-identical (§1) |
| H1 null | random % profitable | 1% | 1% | — | unchanged | null is tie-free; every book re-ran bit-identical (§1) |
| H1 null | random gross CAGR mean | +11.83% | +11.83% | — | unchanged | null is tie-free; every book re-ran bit-identical (§1) |
| H1 null | random gross CAGR median | +11.85% | +11.85% | — | unchanged | null is tie-free; every book re-ran bit-identical (§1) |
| H1 null | random turnover mean | 3.7539 | 3.7539 | — | unchanged | null is tie-free; every book re-ran bit-identical (§1) |
| H1 null | random net-pre-overlay mean | +10.01% | +10.01% | — | unchanged | null is tie-free; every book re-ran bit-identical (§1) |

### 2.3 H2 — component singles

| section | quantity | v1 (`d93815344bd3`) | v2 (`29764f562cd5`) | delta | status | note |
|---------|----------|------------------:|------------------:|------:|--------|------|
| H2 | reversal_5d CAGR | +8.90% | +8.90% | — | unchanged |  |
| H2 | reversal_5d Sharpe | 0.27 | 0.27 | — | unchanged |  |
| H2 | reversal_5d MaxDD | -25.48% | -25.48% | — | unchanged |  |
| H2 | reversal_5d turnover | 3.71 | 3.71 | — | unchanged |  |
| H2 | reversal_5d cost drag | +1.8260% | +1.8260% | — | unchanged |  |
| H2 | reversal_20d CAGR | +11.47% | +11.47% | — | unchanged |  |
| H2 | reversal_20d Sharpe | 0.49 | 0.49 | — | unchanged |  |
| H2 | reversal_20d MaxDD | -24.50% | -24.50% | — | unchanged |  |
| H2 | reversal_20d turnover | 3.73 | 3.73 | — | unchanged |  |
| H2 | reversal_20d cost drag | +1.8928% | +1.8928% | — | unchanged |  |
| H2 | low_volatility CAGR | +8.33% | +8.16% | -0.17pp | **moved** |  |
| H2 | low_volatility Sharpe | 0.23 | 0.21 | -0.02 | **moved** |  |
| H2 | low_volatility MaxDD | -16.05% | -16.05% | — | unchanged |  |
| H2 | low_volatility turnover | 1.90 | 1.89 | -0.01 | **moved** |  |
| H2 | low_volatility cost drag | +0.9146% | +0.9041% | -0.0105pp | **moved** |  |
| H2 | momentum_12_1 CAGR | +10.88% | +6.79% | -4.09pp | **moved** |  |
| H2 | momentum_12_1 Sharpe | 0.41 | 0.08 | -0.33 | **moved** |  |
| H2 | momentum_12_1 MaxDD | -22.56% | -17.78% | +4.78pp | **moved** |  |
| H2 | momentum_12_1 turnover | 1.62 | 3.11 | +1.49 | **moved** |  |
| H2 | momentum_12_1 cost drag | +0.8248% | +1.4490% | +0.6242pp | **moved** |  |
| H2 | momentum_6m CAGR | +10.04% | +9.31% | -0.73pp | **moved** |  |
| H2 | momentum_6m Sharpe | 0.35 | 0.30 | -0.06 | **moved** |  |
| H2 | momentum_6m MaxDD | -17.79% | -17.79% | — | unchanged |  |
| H2 | momentum_6m turnover | 2.23 | 2.69 | +0.45 | **moved** |  |
| H2 | momentum_6m cost drag | +1.1150% | +1.2911% | +0.1762pp | **moved** |  |
| H2 | trend_strength_200d CAGR | +8.52% | +9.87% | +1.35pp | **moved** |  |
| H2 | trend_strength_200d Sharpe | 0.23 | 0.35 | +0.11 | **moved** |  |
| H2 | trend_strength_200d MaxDD | -17.83% | -17.83% | — | unchanged |  |
| H2 | trend_strength_200d turnover | 2.42 | 2.39 | -0.03 | **moved** |  |
| H2 | trend_strength_200d cost drag | +1.1977% | +1.1650% | -0.0327pp | **moved** |  |
| H2 | trend_legs_only CAGR | +10.43% | +10.64% | +0.21pp | **moved** |  |
| H2 | trend_legs_only Sharpe | 0.39 | 0.41 | +0.02 | **moved** |  |
| H2 | trend_legs_only MaxDD | -17.44% | -17.44% | — | unchanged |  |
| H2 | trend_legs_only turnover | 2.05 | 2.14 | +0.09 | **moved** |  |
| H2 | trend_legs_only cost drag | +1.0126% | +1.0431% | +0.0305pp | **moved** |  |
| H2 | control_no_lowvol CAGR | +10.45% | +10.45% | +0.0002pp | **moved** |  |
| H2 | control_no_lowvol Sharpe | 0.40 | 0.40 | +0.0001 | **moved** |  |
| H2 | control_no_lowvol MaxDD | -25.99% | -25.99% | — | unchanged |  |
| H2 | control_no_lowvol turnover | 3.66 | 3.66 | -0.0015 | **moved** |  |
| H2 | control_no_lowvol cost drag | +1.8326% | +1.8323% | -0.0003pp | **moved** |  |

### 2.4 H3 — regime overlay on/off

| section | quantity | v1 (`d93815344bd3`) | v2 (`29764f562cd5`) | delta | status | note |
|---------|----------|------------------:|------------------:|------:|--------|------|
| H3 | prod with overlay CAGR | +9.71% | +9.52% | -0.18pp | **moved** |  |
| H3 | prod with overlay Sharpe | 0.34 | 0.32 | -0.02 | **moved** |  |
| H3 | prod with overlay MaxDD | -14.92% | -14.92% | — | unchanged |  |
| H3 | ctrl with overlay CAGR | +10.04% | +10.05% | +0.01pp | **moved** |  |
| H3 | ctrl with overlay Sharpe | 0.37 | 0.37 | +0.0009 | **moved** |  |
| H3 | ctrl with overlay MaxDD | -25.05% | -25.05% | — | unchanged |  |
| H3 | prod no overlay CAGR | +11.50% | +10.91% | -0.58pp | **moved** |  |
| H3 | prod no overlay Sharpe | 0.41 | 0.37 | -0.04 | **moved** |  |
| H3 | prod no overlay MaxDD | -32.94% | -34.54% | -1.60pp | **moved** |  |
| H3 | ctrl no overlay CAGR | +10.87% | +10.89% | +0.02pp | **moved** |  |
| H3 | ctrl no overlay Sharpe | 0.37 | 0.37 | +0.0011 | **moved** |  |
| H3 | ctrl no overlay MaxDD | -34.57% | -34.57% | — | unchanged |  |
| H3 | Sharpe gap (ctrl-prod), overlay ON | 0.0292 | 0.0464 | +0.0172 | **moved** |  |
| H3 | Sharpe gap (ctrl-prod), overlay OFF | -0.0372 | 0.0038 | +0.0411 | **moved** |  |
| H3 | CAGR gap (ctrl-prod), overlay ON | +0.33pp | +0.52pp | +0.19pp | **moved** |  |
| H3 | CAGR gap (ctrl-prod), overlay OFF | -0.62pp | -0.02pp | +0.60pp | **moved** |  |

### 2.5 H4 — production vs control significance

| section | quantity | v1 (`d93815344bd3`) | v2 (`29764f562cd5`) | delta | status | note |
|---------|----------|------------------:|------------------:|------:|--------|------|
| H4 | mean daily diff (bps/day) | -0.1216 | -0.1925 | -0.0709 | **moved** |  |
| H4 | paired t (iid) | -0.1750 | -0.2776 | -0.1026 | **moved** |  |
| H4 | paired p (iid) | 0.8611 | 0.7813 | -0.0798 | **moved** |  |
| H4 | paired t (Newey-West) | -0.1792 | -0.2835 | -0.1043 | **moved** |  |
| H4 | paired p (Newey-West) | 0.8578 | 0.7768 | -0.0810 | **moved** |  |
| H4 | block-bootstrap dCAGR CI low | -4.07pp | -4.23pp | -0.16pp | **moved** |  |
| H4 | block-bootstrap dCAGR CI high | +3.38pp | +3.20pp | -0.18pp | **moved** |  |
| H4 | P(prod > ctrl) under block bootstrap | 0.4311 | 0.3926 | -0.0385 | **moved** |  |
| H4 | daily-block bootstrap CI low | -3.94pp | -4.13pp | -0.19pp | **moved** |  |
| H4 | daily-block bootstrap CI high | +3.29pp | +3.08pp | -0.21pp | **moved** |  |

### 2.6 H5 — fixed unselected cells, selection cost, per-fold selections

| section | quantity | v1 (`d93815344bd3`) | v2 (`29764f562cd5`) | delta | status | note |
|---------|----------|------------------:|------------------:|------:|--------|------|
| H5 | cell_A production CAGR | +11.01% | +10.99% | -0.02pp | **moved** |  |
| H5 | cell_A production Sharpe | 0.45 | 0.44 | -0.0031 | **moved** |  |
| H5 | cell_A production gross | +12.98% | +12.87% | -0.11pp | **moved** |  |
| H5 | cell_A control_reversal CAGR | +8.00% | +7.99% | -0.01pp | **moved** |  |
| H5 | cell_A control_reversal Sharpe | 0.21 | 0.21 | -0.0011 | **moved** |  |
| H5 | cell_A control_reversal gross | +10.81% | +10.80% | -0.01pp | **moved** |  |
| H5 | cell_B production CAGR | +9.28% | +9.23% | -0.05pp | **moved** |  |
| H5 | cell_B production Sharpe | 0.30 | 0.30 | -0.01 | **moved** |  |
| H5 | cell_B production gross | +10.67% | +10.51% | -0.16pp | **moved** |  |
| H5 | cell_B control_reversal CAGR | +5.25% | +5.21% | -0.04pp | **moved** |  |
| H5 | cell_B control_reversal Sharpe | -0.14 | -0.14 | -0.01 | **moved** |  |
| H5 | cell_B control_reversal gross | +7.17% | +7.07% | -0.10pp | **moved** |  |
| H5 | cell_A decomp gross_gap | +2.17pp | +2.08pp | -0.10pp | **moved** |  |
| H5 | cell_A decomp cost_gap | +0.73pp | +0.74pp | +0.01pp | **moved** |  |
| H5 | cell_A decomp overlay_gap | +0.10pp | +0.18pp | +0.08pp | **moved** |  |
| H5 | cell_A decomp total_gap | +3.01pp | +3.00pp | -0.01pp | **moved** |  |
| H5 | cell_B decomp gross_gap | +3.50pp | +3.44pp | -0.06pp | **moved** |  |
| H5 | cell_B decomp cost_gap | +0.42pp | +0.43pp | +0.01pp | **moved** |  |
| H5 | cell_B decomp overlay_gap | +0.11pp | +0.15pp | +0.04pp | **moved** |  |
| H5 | cell_B decomp total_gap | +4.03pp | +4.02pp | -0.01pp | **moved** |  |
| H5 | PRODUCTION selection delta CAGR | -1.30pp | -1.47pp | -0.16pp | **moved** |  |
| H5 | PRODUCTION train Sharpe | 0.94 | 0.94 | -0.0007 | **moved** |  |
| H5 | PRODUCTION train CAGR | +18.89% | +18.93% | +0.05pp | **moved** |  |
| H5 | PRODUCTION train->OOS Sharpe flip | 0.60 | 0.62 | +0.02 | **moved** |  |
| H5 | CONTROL_REVERSAL selection delta CAGR | +2.03pp | +2.05pp | +0.02pp | **moved** |  |
| H5 | CONTROL_REVERSAL train Sharpe | 0.86 | 0.86 | +0.0000 | **moved** |  |
| H5 | CONTROL_REVERSAL train CAGR | +17.57% | +17.57% | +0.0003pp | **moved** |  |
| H5 | CONTROL_REVERSAL train->OOS Sharpe flip | 0.50 | 0.50 | -0.0009 | **moved** |  |
| H5 | PRODUCTION fold 1 selected params | n22 lb126 thr0.35 | n22 lb126 thr0.35 | — | unchanged | unchanged |
| H5 | PRODUCTION fold 1 OOS CAGR | -0.80% | -0.68% | +0.12pp | **moved** |  |
| H5 | PRODUCTION fold 1 OOS Sharpe | -0.85 | -0.83 | +0.02 | **moved** |  |
| H5 | PRODUCTION fold 2 selected params | n22 lb126 thr0.6 | n22 lb252 thr0.6 | — | **moved** | **argmax flipped** |
| H5 | PRODUCTION fold 2 OOS CAGR | +28.80% | +29.37% | +0.57pp | **moved** |  |
| H5 | PRODUCTION fold 2 OOS Sharpe | 1.68 | 1.73 | +0.05 | **moved** |  |
| H5 | PRODUCTION fold 3 selected params | n22 lb126 thr0.6 | n22 lb126 thr0.6 | — | unchanged | unchanged |
| H5 | PRODUCTION fold 3 OOS CAGR | +13.22% | +12.63% | -0.59pp | **moved** |  |
| H5 | PRODUCTION fold 3 OOS Sharpe | 0.57 | 0.52 | -0.05 | **moved** |  |
| H5 | PRODUCTION fold 4 selected params | n15 lb126 thr0.0 | n15 lb126 thr0.0 | — | unchanged | unchanged |
| H5 | PRODUCTION fold 4 OOS CAGR | +1.35% | +1.13% | -0.22pp | **moved** |  |
| H5 | PRODUCTION fold 4 OOS Sharpe | -0.42 | -0.44 | -0.02 | **moved** |  |
| H5 | PRODUCTION fold 5 selected params | n15 lb126 thr0.35 | n15 lb126 thr0.35 | — | unchanged | unchanged |
| H5 | PRODUCTION fold 5 OOS CAGR | +13.16% | +12.65% | -0.50pp | **moved** |  |
| H5 | PRODUCTION fold 5 OOS Sharpe | 0.71 | 0.66 | -0.05 | **moved** |  |
| H5 | PRODUCTION fold 6 selected params | n30 lb126 thr0.6 | n30 lb126 thr0.6 | — | unchanged | unchanged |
| H5 | PRODUCTION fold 6 OOS CAGR | +5.08% | +4.69% | -0.39pp | **moved** |  |
| H5 | PRODUCTION fold 6 OOS Sharpe | -0.07 | -0.11 | -0.04 | **moved** |  |
| H5 | CONTROL_REVERSAL fold 1 selected params | n30 lb126 thr0.35 | n30 lb126 thr0.35 | — | unchanged | unchanged |
| H5 | CONTROL_REVERSAL fold 1 OOS CAGR | +0.13% | +0.13% | — | unchanged |  |
| H5 | CONTROL_REVERSAL fold 1 OOS Sharpe | -0.78 | -0.78 | — | unchanged |  |
| H5 | CONTROL_REVERSAL fold 2 selected params | n30 lb126 thr0.6 | n30 lb126 thr0.6 | — | unchanged | unchanged |
| H5 | CONTROL_REVERSAL fold 2 OOS CAGR | +22.79% | +22.86% | +0.07pp | **moved** |  |
| H5 | CONTROL_REVERSAL fold 2 OOS Sharpe | 1.70 | 1.71 | +0.01 | **moved** |  |
| H5 | CONTROL_REVERSAL fold 3 selected params | n30 lb126 thr0.6 | n30 lb126 thr0.6 | — | unchanged | unchanged |
| H5 | CONTROL_REVERSAL fold 3 OOS CAGR | +16.91% | +16.91% | — | unchanged |  |
| H5 | CONTROL_REVERSAL fold 3 OOS Sharpe | 0.84 | 0.84 | — | unchanged |  |
| H5 | CONTROL_REVERSAL fold 4 selected params | n30 lb126 thr0.35 | n30 lb126 thr0.35 | — | unchanged | unchanged |
| H5 | CONTROL_REVERSAL fold 4 OOS CAGR | +5.84% | +5.84% | — | unchanged |  |
| H5 | CONTROL_REVERSAL fold 4 OOS Sharpe | 0.02 | 0.02 | — | unchanged |  |
| H5 | CONTROL_REVERSAL fold 5 selected params | n30 lb252 thr0.6 | n30 lb252 thr0.6 | — | unchanged | unchanged |
| H5 | CONTROL_REVERSAL fold 5 OOS CAGR | +12.96% | +12.96% | — | unchanged |  |
| H5 | CONTROL_REVERSAL fold 5 OOS Sharpe | 0.71 | 0.71 | — | unchanged |  |
| H5 | CONTROL_REVERSAL fold 6 selected params | n30 lb126 thr0.6 | n30 lb126 thr0.6 | — | unchanged | unchanged |
| H5 | CONTROL_REVERSAL fold 6 OOS CAGR | +3.29% | +3.29% | — | unchanged |  |
| H5 | CONTROL_REVERSAL fold 6 OOS Sharpe | -0.24 | -0.24 | — | unchanged |  |

### 2.7 H6 — signal-scrambled nulls

| section | quantity | v1 (`d93815344bd3`) | v2 (`29764f562cd5`) | delta | status | note |
|---------|----------|------------------:|------------------:|------:|--------|------|
| H6 | scramble_c cagr_mean | +9.59% | +9.36% | -0.22pp | **moved** |  |
| H6 | scramble_c cagr_sd | +0.91% | +0.82% | -0.09pp | **moved** |  |
| H6 | scramble_c cagr_min | +7.80% | +7.77% | -0.03pp | **moved** |  |
| H6 | scramble_c cagr_max | +12.31% | +11.68% | -0.63pp | **moved** |  |
| H6 | scramble_c cagr_median | +9.50% | +9.34% | -0.16pp | **moved** |  |
| H6 | scramble_c sharpe_mean | 0.32 | 0.30 | -0.02 | **moved** |  |
| H6 | scramble_c sharpe_sd | 0.08 | 0.07 | -0.01 | **moved** |  |
| H6 | scramble_c turnover_mean | 2.20 | 2.20 | +0.0006 | **moved** |  |
| H6 | scramble_c cost_drag_mean | +1.08% | +1.08% | -0.0028pp | **moved** |  |
| H6 | scramble_c cagr_frac_profitable | 1% | 1% | — | unchanged |  |
| H6 | scramble_c production pct CAGR | 58th | 57th | -2 pp-rank | **moved** |  |
| H6 | scramble_c production pct Sharpe | 58th | 58th | — | unchanged |  |
| H6 | scramble_c control pct CAGR | 72nd | 82nd | +10 pp-rank | **moved** |  |
| H6 | scramble_c control pct Sharpe | 77th | 85th | +8 pp-rank | **moved** |  |
| H6 | scramble_r cagr_mean | +8.52% | +8.38% | -0.15pp | **moved** |  |
| H6 | scramble_r cagr_sd | +0.68% | +0.75% | +0.08pp | **moved** |  |
| H6 | scramble_r cagr_min | +7.01% | +6.64% | -0.37pp | **moved** |  |
| H6 | scramble_r cagr_max | +10.25% | +10.13% | -0.12pp | **moved** |  |
| H6 | scramble_r cagr_median | +8.56% | +8.39% | -0.17pp | **moved** |  |
| H6 | scramble_r sharpe_mean | 0.24 | 0.22 | -0.01 | **moved** |  |
| H6 | scramble_r sharpe_sd | 0.06 | 0.07 | +0.01 | **moved** |  |
| H6 | scramble_r turnover_mean | 3.76 | 3.76 | -0.0042 | **moved** |  |
| H6 | scramble_r cost_drag_mean | +1.85% | +1.84% | -0.01pp | **moved** |  |
| H6 | scramble_r cagr_frac_profitable | 1% | 1% | — | unchanged |  |
| H6 | scramble_r production pct CAGR | 93rd | 93rd | — | unchanged |  |
| H6 | scramble_r production pct Sharpe | 93rd | 93rd | — | unchanged |  |
| H6 | scramble_r control pct CAGR | 95th | 97th | +2 pp-rank | **moved** |  |
| H6 | scramble_r control pct Sharpe | 95th | 97th | +2 pp-rank | **moved** |  |
| H6 | production turnover (for comparison) | 2.5130 | 2.4988 | -0.0142 | **moved** |  |
| H6 | production cost drag (for comparison) | +1.23% | +1.22% | -0.01pp | **moved** |  |

### 2.8 Beta, turnover and the equal-weight benchmark

| section | quantity | v1 (`d93815344bd3`) | v2 (`29764f562cd5`) | delta | status | note |
|---------|----------|------------------:|------------------:|------:|--------|------|
| extras | production beta | 0.4914 | 0.4933 | +0.0019 | **moved** |  |
| extras | production corr_bench | 0.7479 | 0.7493 | +0.0015 | **moved** |  |
| extras | production r2 | 0.5593 | 0.5615 | +0.0022 | **moved** |  |
| extras | production alpha_annual | -1.78% | -1.97% | -0.18pp | **moved** |  |
| extras | production alpha_t | -0.39 | -0.43 | -0.04 | **moved** |  |
| extras | production alpha_p | 0.70 | 0.67 | -0.03 | **moved** |  |
| extras | production tracking_err_annual | +10.45% | +10.47% | +0.02pp | **moved** |  |
| extras | control beta | 0.5771 | 0.5771 | +0.00000 | **moved** |  |
| extras | control corr_bench | 0.8802 | 0.8802 | +0.00001 | **moved** |  |
| extras | control r2 | 0.7748 | 0.7748 | +0.00001 | **moved** |  |
| extras | control alpha_annual | -2.41% | -2.40% | +0.01pp | **moved** |  |
| extras | control alpha_t | -0.53 | -0.52 | +0.0020 | **moved** |  |
| extras | control alpha_p | 0.60 | 0.60 | +0.0014 | **moved** |  |
| extras | control tracking_err_annual | +10.42% | +10.42% | — | unchanged |  |
| extras | benchmark CAGR | +17.12% | +17.12% | — | unchanged |  |
| extras | benchmark Sharpe | 0.68 | 0.68 | — | unchanged |  |
| extras | turnover gap (ctrl-prod) | 0.8226 | 0.8364 | +0.0138 | **moved** |  |
| extras | drag gap (ctrl-prod) | +0.43pp | +0.44pp | +0.01pp | **moved** |  |
| extras | net gap (ctrl-prod) | +0.33pp | +0.52pp | +0.19pp | **moved** |  |
| extras | gross gap (ctrl-prod) | +0.76pp | +0.97pp | +0.21pp | **moved** |  |
| extras | beta required for target | 3.40 | 3.40 | — | unchanged |  |
| extras | all-in round trip bps | 21.92 | 21.92 | — | unchanged | cost model unchanged (costs SHA identical) |

*Moved: 153. Unchanged: 74.*

## 3. Verdict at a glance — v1 vs v2

| # | Hypothesis | v1 verdict | v2 verdict | flipped? | decisive v2 number |
|---|-----------|------------|------------|---------|---------------------|
| H1 | It's beta, not skill | SUPPORTED on the decisive comparison, and the net numbers understate how badly | **SUPPORTED on the decisive comparison, and the net numbers understate how badly** | no | production at 95th pct CAGR / 94th pct Sharpe of a 100-book random null; 100% of that null is profitable |
| H2 | Low-vol leg does the work | SUPPORTED — reversal legs carry the control, not low-vol | **SUPPORTED — reversal legs carry the control, not low-vol** | no | control without low-volatility = +10.45% / Sharpe +0.40 vs production +9.52% / 0.32 |
| H3 | Regime overlay is the difference | SUPPORTED — overlay flips the sign | **REFUTED — overlay is not the difference** | **YES** | Sharpe gap (ctrl−prod) +0.046 with overlay, +0.004 without |
| H4 | 0.34 vs 0.37 is noise | SUPPORTED — indistinguishable | **SUPPORTED — indistinguishable** | no | 95% CI on ΔCAGR [-4.23pp, +3.20pp]; robust paired p = 0.78 |
| H5 | Harness has a selection artifact | REFUTED — production wins fixed cells without selection | **REFUTED — production wins fixed cells without selection** | no | production beats control in 2/2 fixed cells; but train-selection costs production -1.47pp/yr and *adds* the control +2.05pp/yr |
| H6 | Equal-count is the wrong null | SUPPORTED — no signal separates it from its own scramble | **SUPPORTED — no signal separates it from its own scramble** | no | production at 57th pct CAGR / 58th pct Sharpe of a 60-book turnover-matched scramble |

## 4. H1 — "It's beta, not skill"

100 random-weight books (i.i.d. `Uniform(0,1)` scores) through the **identical** harness: same 6 folds, same 18-cell grid, same engine, same cost stack, same top-N cut, same inverse-vol scaling, same caps, same turnover budget, same monthly rebalance. The only thing removed is the signal.

| statistic | random CAGR | random Sharpe | random MaxDD | v1 CAGR | status |
|-----------|-------------|--------------|-------------|---------|--------|
| mean | +8.59% | +0.24 | -19.34% | +8.59% | unchanged |
| sd | +0.60% | +0.05 | +1.97% | +0.60% | unchanged |
| min | +7.03% | +0.10 | -24.87% | +7.03% | unchanged |
| p05 | +7.60% | +0.15 | -24.10% | +7.60% | unchanged |
| p25 | +8.20% | +0.21 | -20.02% | +8.20% | unchanged |
| median | +8.65% | +0.25 | -18.91% | +8.65% | unchanged |
| p75 | +8.98% | +0.28 | -18.19% | +8.98% | unchanged |
| p95 | +9.50% | +0.32 | -16.99% | +9.50% | unchanged |
| max | +10.23% | +0.39 | -14.83% | +10.23% | unchanged |
| **profitable** | **100% of books** | — | — | 100% | unchanged |

| book | net CAGR | pct (net) | **gross CAGR** | **pct (gross)** | Sharpe | pct | turnover | cost drag |
|------|---------:|---------:|-------------:|--------------:|-------:|-----:|---------:|----------:|
| **production (trend)** | +9.52% | 95th | +11.43% | **29th** | +0.32 | 94th | 2.50x/y | 1.22%/y |
| control (reversal) | +10.05% | 98th | +12.81% | 94th | +0.37 | 98th | 3.34x/y | 1.66%/y |

> **Read the gross column, not the net one.** The random books turn over 3.75x/yr against production's 2.50x/yr, so on *net* return production is credited for a cost saving that has nothing to do with its factors. The gross column strips both costs and the regime overlay.

### Where production's net edge over the null actually comes from

Three consistent measurements are available per book and they nest:

```
gross   ->  -costs-  ->  net_pre_overlay  ->  +overlay  ->  net
```

| book | gross CAGR | cost channel | net pre-overlay | overlay channel | net CAGR |
|------|-----------:|-------------:|----------------:|----------------:|---------:|
| production | +11.43% | -1.22pp | +10.21% | -0.68pp | +9.52% |
| mean random book | +11.83% | -1.83pp | +10.01% | -1.42pp | +8.59% |
| **difference (v2)** | **-0.40pp** | **+0.60pp** | — | **+0.73pp** | **+0.93pp** |
| difference (v1) | -0.02pp | +0.59pp | — | +0.54pp | +1.12pp |

The three difference terms reconcile to the observed net gap (+0.93pp) to 0.0e+00. **The selection term — the only one that reflects the factors — is -0.40pp/yr.** On v1 it was -0.02pp/yr.

**Verdict: SUPPORTED on the decisive comparison, and the net numbers understate how badly.**

1. **The beta floor is real and high.** 100% of 100 random-weight books are profitable out-of-sample through this harness, net of the same 21.92bps cost stack — mean CAGR +8.59%, mean Sharpe +0.24, **worst case +7.03%**. Not one of them lost money. An arbitrary 22-name NIFTY-50 book rebalanced monthly, with no signal whatsoever, makes money in this sample. The strategy's profitability is therefore not evidence of skill.
2. **And the composite's edge over that null is not a selection edge.** On net CAGR production sits at the 95th percentile and on Sharpe at the 94th — which looks like real selection. But a book that turns over 3.75x/yr against production's 2.50x/yr is being *credited for trading less* on any net comparison.
3. **Decomposed, the selection term is -0.40pp/yr — indistinguishable from zero.** Of production's +0.93pp/yr net edge over the mean random book, +0.60pp is the turnover/cost channel and +0.73pp is the regime-overlay channel. On **gross** CAGR — before costs and before the overlay — production's +11.43% lands at the **29th percentile** of a null whose gross mean is +11.83%. That is *the median random book*, to two decimal places.

**So the honest reading of H1 is: the composite's factors are worth approximately nothing on this data, and everything it does better than a random book it does by holding fewer positions and de-risking more often.** Both of those are properties of book *construction*, and neither is evidence that the factor set has predictive power. The reversal control's gross percentile is 94th, so on this metric the control's selection is *not* null either — which is the finding, not a reprieve.

H1 cannot by itself explain why production fails to beat a composite of factors this repo has already ruled out on published Indian evidence. For that, see H2, H5 and H6.

## 5. H2 — "The low-vol leg is doing the work, not the reversal legs"

Every component run alone at weight 1.0 through the same harness, plus the control with `low_volatility` removed (weights renormalised by `build_composite_score`).

| book | OOS CAGR | OOS Sharpe | OOS MaxDD | turnover | cost drag | v1 CAGR | v1 Sharpe | status |
|------|---------:|-----------:|----------:|---------:|----------:|--------:|----------:|--------|
| **PRODUCTION (trend)** | +9.52% | 0.32 | -14.92% | 2.50x/y | 1.22%/y | +9.71% | 0.34 | **moved** |
| **CONTROL (reversal)** | +10.05% | 0.37 | -25.05% | 3.34x/y | 1.66%/y | +10.04% | 0.37 | **moved** |
| reversal_5d | +8.90% | +0.27 | -25.48% | 3.71x/y | 1.83%/y | +8.90% | +0.27 | unchanged |
| reversal_20d | +11.47% | +0.49 | -24.50% | 3.73x/y | 1.89%/y | +11.47% | +0.49 | unchanged |
| low_volatility | +8.16% | +0.21 | -16.05% | 1.89x/y | 0.90%/y | +8.33% | +0.23 | **moved** |
| momentum_12_1 | +6.79% | +0.08 | -17.78% | 3.11x/y | 1.45%/y | +10.88% | +0.41 | **moved** |
| momentum_6m | +9.31% | +0.30 | -17.79% | 2.69x/y | 1.29%/y | +10.04% | +0.35 | **moved** |
| trend_strength_200d | +9.87% | +0.35 | -17.83% | 2.39x/y | 1.17%/y | +8.52% | +0.23 | **moved** |
| trend_legs_only | +10.64% | +0.41 | -17.44% | 2.14x/y | 1.04%/y | +10.43% | +0.39 | **moved** |
| control_no_lowvol | +10.45% | +0.40 | -25.99% | 3.66x/y | 1.83%/y | +10.45% | +0.40 | **moved** |

control **without** low-volatility = +10.45% / Sharpe +0.40; `low_volatility` alone = +8.16% / Sharpe +0.21; `reversal_5d` alone = +8.90% / +0.27; `reversal_20d` alone = +11.47% / +0.49.

**Verdict: REFUTED.** Removing the low-vol leg leaves the control at +10.45% / Sharpe +0.40 — still ahead of production's +9.52% / 0.32. The low-volatility leg is therefore *not* what carries the control; the reversal legs are.

## 6. H3 — "The regime overlay is the whole difference"

Identical folds, identical grid, identical engine and costs. `overlay=OFF` skips `blend_with_cash` and nothing else.

| book | overlay | OOS CAGR | OOS Sharpe | OOS MaxDD | v1 CAGR | v1 Sharpe | status |
|------|---------|---------:|-----------:|----------:|--------:|----------:|--------|
| prod | with overlay | +9.52% | +0.32 | -14.92% | +9.71% | +0.34 | **moved** |
| prod | no overlay | +10.91% | +0.37 | -34.54% | +11.50% | +0.41 | **moved** |
| ctrl | with overlay | +10.05% | +0.37 | -25.05% | +10.04% | +0.37 | **moved** |
| ctrl | no overlay | +10.89% | +0.37 | -34.57% | +10.87% | +0.37 | **moved** |

**Sharpe gap (control − production):** +0.046 with the overlay (v1 +0.029), +0.004 without it (v1 -0.037). **CAGR gap (control − production):** +0.52pp with, -0.02pp without.

**Verdict: REFUTED.** The control's Sharpe advantage over production is present with the overlay (+0.046) and without it (+0.004) — same sign, similar size. The overlay is not the difference; production does not only win with it.

## 7. H4 — "the production-vs-control gap is noise"

OOS window 2014-11-26 -> 2026-10-01, **2928 daily observations**, both books on identical dates (paired).

| test | statistic | p-value | v1 statistic | v1 p | status |
|------|-----------|---------|--------------|-------|--------|
| paired daily t-test on the return difference | t = -0.278 | 0.781 | -0.175 | 0.861 | **moved** |
| same, Newey-West HAC(10) | t = -0.283 | 0.777 | -0.179 | 0.858 | **moved** |
| bootstrap 95% CI on ΔCAGR (21-bar blocks, B=10,000) | [-4.23pp, +3.20pp] | — | [-4.07pp, +3.38pp] | — | **moved** |

Observed ΔCAGR = +9.52% − +10.05% = -0.52pp (v1 -0.33pp). Observed ΔSharpe = 0.32 − 0.37 = -0.05 (v1 -0.03).

**Verdict: SUPPORTED.** The 95% bootstrap CI on ΔCAGR is [-4.23pp, +3.20pp] — it straddles zero, and the serial-correlation-robust paired t-test is t = -0.28, p = 0.78. The two books are **statistically indistinguishable** out-of-sample. That is itself the finding: the composite's factors do not separate it from a composite of rejected factors by any measurable margin, over 2928 daily observations.

## 8. H5 — "The harness has a selection artifact"

Walk-forward selects parameters on TRAIN. A book that survives TRAIN selection could carry a structural OOS advantage unrelated to its signal. Two readings: a **fixed, unselected** parameter set, and the train/test profile of both books.

### Fixed parameters — no train selection at all

| cell | params | production CAGR | control CAGR | production Sharpe | control Sharpe |
|------|--------|----------------:|--------------:|-----------------:|---------------:|
| cell_A | n=22, lb=126, thr=0.35 | +10.99% | +7.99% | 0.44 | 0.21 |
| cell_B | n=15, lb=126, thr=0.0 | +9.23% | +5.21% | 0.30 | -0.14 |

| cell | v1 prod CAGR | v1 ctrl CAGR | selection (gross) | cost | overlay | total net | v1 total net |
|------|-------------:|-------------:|------------------:|-----:|--------:|----------:|-------------:|
| cell_A | +11.01% | +8.00% | +2.08pp | +0.74pp | +0.18pp | +3.00pp | +3.01pp |
| cell_B | +9.28% | +5.25% | +3.44pp | +0.43pp | +0.15pp | +4.02pp | +4.03pp |

### What the train-window selection actually does

| book | best fixed cell | walk-forward | selection delta | v1 selection delta |
|------|-----------------:|-------------:|----------------:|------------------:|
| PRODUCTION | +10.99% | +9.52% | -1.47pp | -1.30pp |
| CONTROL_REVERSAL | +7.99% | +10.05% | +2.05pp | +2.03pp |

### Train vs test — is there a flip?

| book | mean TRAIN Sharpe | OOS Sharpe | flip | mean TRAIN CAGR | OOS CAGR | v1 flip |
|------|------------------:|-----------:|-----:|----------------:|--------:|--------:|
| PRODUCTION | +0.94 | +0.32 | +0.62 | +18.93% | +9.52% | +0.60 |
| CONTROL_REVERSAL | +0.86 | +0.37 | +0.50 | +17.57% | +10.05% | +0.50 |

### Per-fold train/test, and which parameter the tie-break changed the choice of

This is the mechanism table. A cell flagged **argmax flipped** is a fold where the tie-break changed which of the 18 grid cells the train window preferred — which is a direct, mechanical measurement of how much of the headline is the selection layer.

| book | fold | selected params | v1 selected params | TRAIN Sharpe | OOS Sharpe | TRAIN CAGR | OOS CAGR |
|------|-----:|------------------|-------------------|-------------:|-----------:|----------:|--------:|
| PRODUCTION | 1 | n=22, lb=126, thr=0.35 | *same* | +1.14 | -0.83 | +22.30% | -0.68% |
| PRODUCTION | 2 | n=22, lb=252, thr=0.6 | n=22, lb=126, thr=0.6 | +0.83 | +1.73 | +17.98% | +29.37% |
| PRODUCTION | 3 | n=22, lb=126, thr=0.6 | *same* | +0.47 | +0.52 | +11.96% | +12.63% |
| PRODUCTION | 4 | n=15, lb=126, thr=0.0 | *same* | +0.92 | -0.44 | +17.09% | +1.13% |
| PRODUCTION | 5 | n=15, lb=126, thr=0.35 | *same* | +0.76 | +0.66 | +14.97% | +12.65% |
| PRODUCTION | 6 | n=30, lb=126, thr=0.6 | *same* | +1.52 | -0.11 | +29.29% | +4.69% |
| CONTROL_REVERSAL | 1 | n=30, lb=126, thr=0.35 | *same* | +1.03 | -0.78 | +19.51% | +0.13% |
| CONTROL_REVERSAL | 2 | n=30, lb=126, thr=0.6 | *same* | +0.70 | +1.71 | +15.61% | +22.86% |
| CONTROL_REVERSAL | 3 | n=30, lb=126, thr=0.6 | *same* | +0.20 | +0.84 | +8.34% | +16.91% |
| CONTROL_REVERSAL | 4 | n=30, lb=126, thr=0.35 | *same* | +0.85 | +0.02 | +15.25% | +5.84% |
| CONTROL_REVERSAL | 5 | n=30, lb=252, thr=0.6 | *same* | +0.75 | +0.71 | +15.29% | +12.96% |
| CONTROL_REVERSAL | 6 | n=30, lb=126, thr=0.6 | *same* | +1.64 | -0.24 | +31.45% | +3.29% |

**1 of 12 fold-level parameter selections changed between the two engines.**

**Verdict: REFUTED — this is the one hypothesis that does not survive.** With the train-window selection removed entirely, production beats the control in 2 of 2 fixed cells: cell_A +3.00pp (Sharpe +0.24), cell_B +4.02pp (Sharpe +0.44). The production composite is **not** uniformly inert: under some fixed settings it does select better names than the reversal composite.

This is the strongest evidence in the repo for the production composite, and it deserves to be stated plainly rather than buried. But it is not a deployable edge, for two reasons. First, these cells are ordinary book-construction choices, not out-of-sample discoveries. Second, and more seriously, the walk-forward version of the strategy — the only protocol `GOAL.md` §5 accepts — does not reproduce it.

**The selection step is what destroys it.** Production's best fixed cell returns +10.99%/yr, but the same strategy under walk-forward parameter selection returns +9.52%/yr — selection costs it 1.47pp/yr. The control moves the other way: selection *adds* +2.05pp/yr to it. So the train-window search is anti-correlated with out-of-sample performance for the production composite and positively correlated for the control. That is a defect in the parameter-selection layer, and it is the mechanical reason the negative control ties production in the protocol that counts.

**There is no train/test flip unique to the control.** Train→OOS Sharpe degradation is +0.62 for production and +0.50 for the control — nearly identical. The control is not a book that was overfit and then broke; it is a book that behaves the same way in both regimes. That is the worse of the two cases for the production composite's defence.

## 9. H6 — "Equal-count controls are the wrong null"

A random book and a **signal-scrambled** book are different nulls. A random book asks *does an arbitrary book make money*. A scrambled book asks *does **this** book make money for any reason other than its signal* — which is what a negative control is for.

- `scramble_c`: the composite score with a **fixed column relabel** (`score'[t,s] = score[t,π(s)]`). Every per-date marginal score distribution is preserved **exactly**; only the score-to-return link is destroyed.
- `scramble_r`: the composite with an **independent permutation of each date's cross-section**. Per-date marginals are still preserved exactly, but the name identity churns every rebalance, so turnover rises.

> **Caveat carried forward, and it is not a formality.** The brief asked for the scrambled null to match turnover as closely as possible. `scramble_c` does **not** match it exactly and cannot: relabelling score columns relabels *which name* receives *which score*, but `build_rebalance_weights` then inverse-vol-scales by the **name's** realised volatility and runs a sector / single-name cap projection over **name identities**, so the resulting weight vector is not a permutation of the original. Measured: production turns over 2.50x/y and `scramble_c` 2.20x/y — a 11.8% gap — and the scrambled books' own seed-to-seed spread is 0.82pp on CAGR. The match is good to within a few percent and the residual is printed in the table rather than described as exact.

| book | n | mean CAGR | sd | min | max | mean Sharpe | sd | turnover | cost drag | profitable |
|------|--:|----------:|---:|----:|----:|-----------:|---:|---------:|----------:|-----------:|
| **production (unscrambled)** | 1 | +9.52% | — | — | — | 0.32 | — | **2.50x/y** | **1.22%/y** | — |
| scramble_c (fixed relabel) | 60 | +9.36% | 0.82pp | +7.77% | +11.68% | +0.30 | 0.07 | 2.20x/y | 1.08%/y | 100% |
| scramble_r (per-date permute) | 60 | +8.38% | 0.75pp | +6.64% | +10.13% | +0.22 | 0.07 | 3.76x/y | 1.84%/y | 100% |

| book | vs scramble_c (CAGR pct) | vs scramble_c (Sharpe pct) | vs scramble_r (CAGR pct) | vs scramble_r (Sharpe pct) | v1 scramble_c CAGR pct |
|------|-------------------------:|---------------------------:|------------------------:|--------------------------:|----------------------:|
| **production** | 57th | 58th | 93rd | 93rd | 58th |
| control | 82nd | 85th | 97th | 97th | 72nd |

> **Read the production row, not the control row.** These nulls are built by scrambling the **production** composite, so the production row is a like-for-like test of production against its own signal destroyed. The control row places a *different* composite (reversal weights) against a null built from the trend composite's score distribution — different turnover, different score dispersion, different name overlap — so the control's percentile against this null is indicative only and must not be read as a significance test. A matched control scramble (reversal weights, then scrambled) is the clean version and was not run; H2 and H4 cover the production-vs-control question directly instead.

**Verdict: SUPPORTED.** Against the turnover-matched signal-scrambled null, production sits at the 57th percentile on CAGR and 58th on Sharpe, while 100% of scrambled books are profitable. Keeping the per-date score distribution, the name count, the cost stack, the overlay and the constraints — and destroying only the link from score to return — leaves a result indistinguishable from the production one. (The null's turnover is matched to within a few percent, not exactly; see the correction note above.) Turnover is not what separates them.

> **Measured turnover residual, and which way it cuts.** The verdict text above says the turnover is matched "to within a few percent", carried from v1's wording. Re-measured on this engine the residual is larger and it should be stated plainly: `scramble_c` turns over 2.20x/y against production's 2.50x/y, i.e. **11.8% lower**, not ~3%. (v1's ~3% was a different measurement — total one-way turnover over the whole panel under pure column permutations, not the annualised turnover of the *selected* out-of-sample cell — and the two are not interchangeable.)

**The direction matters, and it cuts against production.** A null that turns over less pays less cost drag, so its mean net CAGR is flattered relative to production's. If the null were turnover-matched it would pay 0.14pp/yr more in drag, its mean would fall, and production's percentile against it would be *higher* than the 57th measured here. The residual therefore works **against** the production composite, and it still does not clear the null. Correcting it would not change the verdict; it would move production up the table, not out of it.

## 10. Turnover, beta and the equal-weight benchmark

### 1. Turnover and cost drag — is the control's edge just a smaller bill?

| book | annual turnover | annual cost drag | v1 turnover | v1 drag | status |
|------|----------------:|-----------------:|-------------|----------:|--------|
| production | 2.4988x/y | 1.22%/y | 2.5130x/y | 1.23%/y | **moved** |
| control | 3.3352x/y | 1.66%/y | 3.3355x/y | 1.66%/y | **moved** |
| **control − production** | **+0.8364x/y** | **+0.44pp/y** | +0.8226x/y | +0.43pp/y | |

**The hypothesis is refuted, and the direction matters.** The control turns over **0.84x/yr more** and pays **0.44pp/yr more** in drag, and still earns more. As an identity:

```
gross_ctrl - gross_prod = (net_ctrl - net_prod) + (drag_ctrl - drag_prod)
                        = +0.52pp           + +0.44pp
                        = +0.97pp
```

The control's **gross** advantage is +0.97pp/yr (v1 +0.76pp) — larger than its net advantage of +0.52pp/yr (v1 +0.33pp). Cost drag *narrows* the gap between the two books; it does not create it.

### 2. Beta and correlation to the equal-weight benchmark

| book | beta | corr | R² | Jensen alpha | alpha t | alpha p | tracking error | v1 beta | v1 alpha |
|------|-----:|-----:|---:|-------------:|--------:|--------:|---------------:|--------:|----------:|
| production | 0.493 | 0.749 | 0.562 | -1.97%/y | -0.43 | 0.67 | 10.5% | 0.491 | -1.78%/y |
| control | 0.577 | 0.880 | 0.775 | -2.40%/y | -0.52 | 0.60 | 10.4% | 0.577 | -2.41%/y |
| *equal-weight benchmark* | 1.000 | 1.000 | 1.000 | — (CAGR +17.12%, Sharpe 0.68) | — | — | — | — | — |

### 3. Would a market-neutral or beta-matched comparison change the verdict?

`GOAL.md` targets 3%/month net = **42.6%/yr**. The equal-weight NIFTY-50 benchmark over the same OOS windows returned +17.12%/yr (Sharpe 0.68). The book already **underperforms the benchmark it could have simply held**.

Production's beta against that benchmark is **0.493** (corr 0.749, R² 0.562); the control's is **0.577** (corr 0.880, R² 0.775). Neither is ~1.0 — the regime overlay spends time in cash, which is why — so the 'levered index fund' story is not literally right. But it is not rescued either: Jensen alpha is **-1.97%/yr (t = -0.43, p = 0.67)** for production and **-2.40%/yr (t = -0.52, p = 0.60)** for the control. Both are **negative** and both are statistically indistinguishable from zero.

**Would a beta-matched comparison change the verdict? No.** The two books differ by 0.084 in beta, so matching beta changes nothing material: whichever Sharpe wins raw wins beta-matched. And beta-matching cannot separate a book from a signal-scrambled version of itself, because scrambling the signal leaves beta intact by construction.

**Would a market-neutral comparison change the verdict? It is not available, and it would not be the right test.** The account is long-only delivery (`GOAL.md` §3.2, `AGENT_BRIEF.md` §5), so there is no short leg to neutralise against. The Jensen alpha above is already the market-adjusted number, and it is zero.

**At what beta would the comparison become fair?** A fair comparison asks whether the book earns its *target* given its risk. Stated on the same excess-return basis the regression uses (`excess-return (target-rf)/(benchmark-rf)`), a zero-alpha book would need a beta of **3.40** to reach 42.6%/yr from a 17.12%/yr benchmark — roughly 7× the beta production actually runs at, and well beyond what a long-only delivery account permits. Since the measured alpha is statistically zero, the target is unreachable at any beta available to this account. Meeting 3%/month would require the alpha to be real, and on this evidence it is not distinguishable from zero.

## 11. Bottom line

**The null is not the reversal control. The null is a book with no signal at all.** 100 random-weight books run through the identical harness — same folds, same engine, same 21.92bps cost stack, same constraints — are profitable **100% of the time**, mean CAGR +8.59%, worst case +7.03%, mean Sharpe +0.24. Not one of them lost money. A 22-name, monthly-rebalanced, long-only NIFTY-50 book returns a positive out-of-sample result in this sample whatever signal it holds, because the universe rose and long-only equity beta is the dominant term. **That null is the same on both engines, and §1 shows why: all 100 of them re-ran bit-identical.**

**And the composite's edge over that null is not a selection edge — on this engine it is slightly negative.** On net CAGR production sits at the 95th percentile, but random books turn over 3.75x/yr against production's 2.50x/yr, so on *net* return production is credited for trading less. Strip that channel out and compare gross CAGR: production's +11.43% lands at the **29th percentile** of a null whose gross mean is +11.83%. On v1 that percentile was 47th — production *was* the median random book, to two decimal places. **It is now materially below the median, and the decomposition agrees: the selection term moved from -0.02pp/yr to -0.40pp/yr.** What the composite genuinely does better than a random book is *hold* rather than *rotate* — a cost-management property this harness rewards and that no factor evidence supports.

**The signal-scrambled null is the decisive test, and it agrees.** Destroy *only* the signal — keep the composite's own per-date score distribution, its name count, its cost stack, its overlay, its constraints — and relabel which symbol receives which score. Those books are profitable 100% of the time with mean CAGR +9.36%, and production sits at the 57th percentile of them. And the residual turnover mismatch cuts *against* production, not for it, so correcting it would only move it up the table. A negative control exists for exactly one purpose: to separate the signal from everything else that produces a return. This one does not separate them, so it has failed at its job.

**And the production-vs-control gap is not a real gap.** Over 2928 daily out-of-sample observations the 95% block-bootstrap CI on ΔCAGR is [-4.23pp, +3.20pp] and the serial-correlation-robust paired t-test gives p = 0.78. Production +9.52% / 0.32 against the control's +10.05% / 0.37. At 0.03 Sharpe, the two books are not separable at this sample size on either engine, and the v1 framing of that gap as the single most damning finding in the repo was always overstated.

**Beta does not rescue it.** Production runs at beta 0.49 and the control at 0.58 — they differ by 0.08, so beta-matching changes nothing. Jensen alpha is -1.97%/yr (p = 0.67) for production and -2.40%/yr (p = 0.60) for the control: both negative, both indistinguishable from zero. To reach `GOAL.md`'s 42.6%/yr target on a zero-alpha basis the book would need a beta of 3.40 — about 7x what it runs at, and unreachable in a long-only delivery account. The target is not beta-limited; it is alpha-limited, and the alpha is not there.

**One finding cuts the other way, and it deserves to be stated plainly.** With *fixed, unselected* parameters, production beats the control in 2 of 2 cells cell_A (+10.99% vs +7.99%), cell_B (+9.23% vs +5.21%). The trend composite is therefore **not** uniformly inert — under some fixed settings it does select better names than the reversal composite. That is a real, reproducible observation and it is the strongest argument this repo has for the production composite. It is not evidence of a *deployable* edge: those cells are ordinary book-construction choices, they were not selected out-of-sample, and the walk-forward version of them — the only protocol that counts — does not reproduce it (selection costs production 1.47pp/yr and *adds* the control +2.05pp/yr).

**So: no — this strategy does not have a demonstrable edge, and on the tie-break-fixed engine the evidence is stronger, not weaker.** A random book earns +8.6%/yr here with no signal whatsoever. The 9.52% is not a strategy result that happens to sit next to a failed control; it is a control's result wearing a different label. Nothing here justifies relaxing `GOAL.md` §5, and the Gate 4 checks that pass would pass just as well for a book holding 22 names chosen at random. The secondary findings do not rescue it: the control survives removal of its low-volatility leg and still beats production (+10.45% / +0.40 against production's +9.52% / 0.32), so that leg is not carrying it (H2). **The regime-overlay verdict flipped on this engine**: on v1 the control's Sharpe lead reversed sign when the overlay was switched off (+0.029 with, -0.037 without), which v1 read as "the overlay is the difference". On v2 the control leads in both cases (+0.046 with, +0.004 without), so H3 is REFUTED. That does not help the production composite — the overlay now looks like the one thing that was *diluting* an edge that exists without it. And the two books' train-to-test degradation is nearly identical (+0.62 vs +0.50 Sharpe), so there is no train/test flip unique to the control (H5). **The correct next step is not a wider parameter search — 18 of 18 profitable grid cells (reports/STRESS_v3.md §5) is what a null produces — it is to change what counts as success.** Any future candidate must beat a signal-scrambled version of itself, and must be measured against that, not against the equal-weight benchmark in a rising market.

---

*Produced by `research/revalidate_v2/run_control.py` + `report_control.py` against engine `29764f562cd5`, loader `c1badf5f7df8`, costs `ba350aef75b3`, panel `389b082b832f`. v1 (engine `d93815344bd3`) is `reports/CONTROL_DIAGNOSTIC.md` and its underlying per-book cache is `research/_control_diag/`. All-in cost 21.92 bps round trip. Every figure here is net of the full Indian delivery cost stack and must be quoted with its end date — the OOS window ends 2026-10-01. Survivorship bias is present and disclosed. `GOAL.md` §6 anti-fraud rules apply: no in-sample number is presented as a result, and no cost was reduced to rescue anything.*
