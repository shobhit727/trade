# CCI Strategy on NSE NIFTY-50 — Validation Report

**Strategy file:** `src/cryptobot/strategies/catalog/cci_strategy.py`
**Class:** `CciStrategy` / `CciConfig(period=20, entry=100.0)`
**Assigned agent:** `agent_cci`
**Protocol:** `research/AGENT_BRIEF.md` (read in full; TRAIN 2016-01-01→2023-12-31,
TEST 2024-01-01→2026-10-01)
**Verdict: NO. This strategy does not make money on NSE.** Details in §6.

> **Run continuity / disclosure.** A previous run of this same assignment was
> interrupted and left scratch scripts + `*.txt` output in this directory. Those files
> (`TRAIN_RESULTS.txt`, `PRIMARY_TEST_RESULT.txt`, `POSTHOC.txt`) were treated as
> *untrusted claims*. Every number in this report has been independently reproduced by
> the scripts named beside it. Two defects in the prior scratch are written up in §7.
>
> **TEST-window disclosure, stated plainly:** the prior run had already read TEST and
> written `PRIMARY_TEST_RESULT.txt` before it was interrupted. This session therefore
> **re-verified** an already-consumed TEST window; it did not produce a first-touch
> TEST result. What was preserved is the harder property: no *new* parameter was chosen
> after seeing TEST. The 5-variant budget below was declared before the interrupted run
> executed, the winner was frozen on TRAIN alone, and this session re-confirmed the same
> winner (V5_deep) from a corrected TRAIN. **No 6th variant was tested, and no variant
> was promoted on the basis of its TEST number.**

---

## 1. What the strategy actually is

```python
c = cci(highs, lows, closes, period)      # period = 20
if c >  entry: return -1                   # entry = 100  -> SHORT (overbought)
if c < -entry: return  1                   #           -> LONG  (oversold)
return 0
```

* CCI(20) on typical price `(H+L+C)/3` with a mean-absolute-deviation denominator.
  Verified **numerically identical** to `cryptobot.strategies.indicators.cci`:
  `max_abs_error = 0.000e+00` over 120 random (symbol, bar) probes at periods 10/14/20.
* A **short-horizon mean-reversion** rule: buy deeply oversold, short deeply overbought.
* Not crypto-specific — CCI is price-only, no funding/basis/IV/pin. **It has NSE meaning.**

**Long-only adaptation (brief §5).** An Indian delivery account cannot short, so the
`-1` (overbought) branch is not tradable and collapses into "not long". The book's entire
opportunity set is therefore names with `CCI < -100`. Note the book sign convention is
`higher score = more attractive`, so ranking by *lowest* CCI = most oversold.

**Liveness.** CCI(20) < −100 fires on **16.66%** of TRAIN bar/symbol cells and
**18.64%** of TEST cells — well above the brief's 5% "effectively always flat" floor.
Median flagged names per monthly rebalance is 5 (mean 7.35), so the book is usually
short of the 22-name cap; avg names actually held is 18.7.

---

## 2. Declared parameter budget — 5 variants, fixed BEFORE any run

Declared in `s2_train.py`'s module docstring (which predates the interrupted run) and
re-declared here before re-executing. **Not exceeded.**

| # | name | period | entry | rebalance | rank_by | rationale |
|---|------|--------|-------|-----------|---------|-----------|
| V1 | `V1_base` | 20 | 100 | M | `mom126` | catalog defaults + the brief's §5 construction |
| V2 | `V2_tight` | 20 | 150 | M | `mom126` | stricter oversold filter |
| V3 | `V3_week` | 20 | 100 | W | `mom126` | rebalance matched to signal horizon |
| V4 | `V4_fast` | 10 | 100 | M | `mom126` | shorter CCI window |
| V5 | `V5_deep` | 20 | 100 | M | `deepest` | buy the *most* oversold (no momentum rank) |

**Selection rule, fixed in advance:** highest TRAIN Sharpe, ties broken by TRAIN Calmar.
**Not variants** (comparators/diagnostics, may not be selected on): buy-and-hold,
constant-score book, `build_composite_score`, the momentum book with the CCI gate
removed, random-signal nulls, cost stress models.

---

## 3. Data and cost basis

`data/nse/<sym>_1d.csv` via `nsealgo.data.loader.load_symbol` (identical C1–C6 cleaning
path as `load_universe`, which returns closes only and cannot supply the H/L that CCI's
typical price needs). `MIN_BARS=1000`, exclude `adanient` — same exclusions as
`load_universe`.

```
CLEANING REPORT      rows in 274,541 → rows out 208,226
  dropped pre-2008 66,312   dropped artifact 0   non-positive 0   extreme 3
  excluded symbols ['adanient', 'jiofin']
symbols 48   panel rows 4,629   span 2008-01-01 → 2026-10-01
TRAIN bars 1,975   TEST bars 685
```

**Cost model:** `CostModel(segment="delivery", slippage_bps=5)`. `run_backtest` charges
`all_in_round_trip_bps(100_000)` = **21.92 bps** (11.92 statutory + 2 × 5 bps slippage).
**Every strategy number in this report is net of 21.92 bps**, confirmed at runtime via
`diag['round_trip_bps']`. The 11.92 figure appears only in the cost-stress table, where
it is explicitly labelled as statutory-only.

**No lookahead — proven, not asserted.** `s1_lookahead_check.py` truncates the panel at 12
random cut points and recomputes the CCI from scratch: `max |full − truncated| =
0.000e+00` over 1,507,015 bar/symbol values. If the CCI at bar *t* had touched any data
after *t*, truncation would have changed it. `run_backtest` independently holds weights
decided at the close of *t* from *t+1* (`gross = held.shift(1) * rets`).

---

## 4. TRAIN (selection window) — 2016-01-01 → 2023-12-31

`v1_verify.py §1`. Warm-up corrected (see BUG-1 in §7).

| variant | p | entry | reb | rank | CAGR | Sharpe | MaxDD | Calmar | Turn | Cost/yr | Names |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **V5_deep** | 20 | 100 | M | deepest | **7.16%** | **0.11** | −32.36% | **0.22** | 3.82x | 1.08% | 16.9 |
| V1_base | 20 | 100 | M | mom126 | 6.38% | 0.05 | −35.15% | 0.18 | 3.81x | 1.05% | 16.8 |
| V4_fast | 10 | 100 | M | mom126 | 4.67% | −0.09 | −34.28% | 0.14 | 3.64x | 1.01% | 14.4 |
| V3_week | 20 | 100 | W | mom126 | 4.17% | −0.11 | −36.69% | 0.11 | 14.58x | 3.72% | 14.7 |
| V2_tight | 20 | 150 | M | mom126 | −1.03% | −0.72 | −34.33% | −0.03 | 2.53x | 0.53% | 4.6 |

**Winner, frozen on TRAIN: `V5_deep`** (period 20, entry 100, monthly, rank by deepest
CCI). Frozen TRAIN bar-long fraction for the null tests: **16.66%**.

Every TRAIN Sharpe in the family is ≤ 0.11. That is the whole problem, and it was
visible before TEST was touched.

---

## 5. TEST (out-of-sample) — 2024-01-01 → 2026-10-01

685 bars, 48 symbols. Produced by `v1_verify.py §2–§7`.

### 5.1 PRIMARY RESULT — frozen TRAIN winner `V5_deep`, net of 21.92 bps

| metric | value |
|---|---|
| **CAGR** | **4.56%** |
| **Sharpe** | **−0.18** |
| **MaxDD** | **−13.23%** (61 days) |
| **Calmar** | 0.34 |
| **Turnover** | 3.77x / yr |
| **Cost drag** | 0.91% / yr |
| **Trades** | 11.8 / yr |
| **Avg names held** | 18.7 |
| **Bar long fraction** | 18.64% (TRAIN 16.66%) |
| Positive years | 2 / 3 — 2024 +6.49%, 2025 +13.97%, 2026 −6.61% |

### 5.2 The whole declared family on TEST (family diagnostic — *not* a selection)

| variant | CAGR | Sharpe | MaxDD | Calmar | Turn | Cost/yr | Names | TRAIN Sharpe | did TEST beat its own TRAIN? |
|---|---|---|---|---|---|---|---|---|---|
| V1_base | 4.43% | −0.20 | −13.23% | 0.33 | 3.76x | 0.91% | 18.8 | 0.05 | no |
| V2_tight | 4.04% | −0.33 | −11.75% | 0.34 | 2.69x | 0.66% | 6.5 | −0.72 | yes |
| V3_week | 1.72% | −0.43 | −12.68% | 0.14 | 14.90x | 3.63% | 16.2 | −0.11 | no |
| V4_fast | **8.07%** | **0.21** | −15.03% | 0.54 | 3.82x | 1.01% | 18.4 | −0.09 | yes |
| V5_deep | 4.56% | −0.18 | −13.23% | 0.34 | 3.77x | 0.91% | 18.7 | 0.11 | no |

> **Read this row carefully and do not promote it.** `V4_fast` (CCI period 10) is the only
> variant whose TEST Sharpe is positive, and it is the only one that roughly matches
> buy-and-hold. But its **TRAIN Sharpe was −0.09** — it ranked 3rd of 5 on the selection
> window and was rejected there. Promoting it now because it looks good on TEST would be
> exactly the trap brief §4 rule 4 exists to prevent. The arithmetic says it is noise:
> against the 100-seed random-22 null (§5.6) with Sharpe mean −0.04 and sd 0.12, a
> Sharpe of 0.21 is a **2.08σ** single draw (p = 1.9%), and taking the **best of 5**
> variants raises that to **p ≈ 9%** — a one-in-eleven event that happens by chance under
> the null roughly once per eleven such runs. **V4_fast is reported as a curiosity, not
> as a result.** It is also the right place to look next — see §6.

### 5.3 Buy-and-hold over the identical TEST window (brief §4 rule 5)

`panel.pct_change().mean(axis=1)`, with one entry round trip (21.92 bps) charged on day 1.

| book | CAGR | Sharpe | MaxDD | Calmar | Turn | Names |
|---|---|---|---|---|---|---|
| **buy-and-hold (all 48, unconstrained)** | **8.16%** | **0.19** | **−15.91%** | 0.51 | — | 48 |
| constant-score 22-name book (see BUG-3) | 9.76% | 0.32 | −13.51% | 0.72 | 0.64x | 21.3 |
| random 22-name book, 100 seeds (true null) | 5.41% ± 1.39 | −0.04 ± 0.12 | — | — | — | 21.3 |

### 5.4 TEST vs buy-and-hold

| | CCI `V5_deep` | buy-and-hold | verdict |
|---|---|---|---|
| CAGR | 4.56% | 8.16% | **−3.60 pp — worse** |
| Sharpe | −0.18 | 0.19 | **−0.37 — worse** |
| MaxDD | −13.23% | −15.91% | **+2.68 pp — better** (shallower) |
| Calmar | 0.34 | 0.51 | −0.17 — worse |

The strategy loses to doing nothing on return and on risk-adjusted return, and wins only
on absolute drawdown depth — and that drawdown win is small and comes from holding a
~19-name book through a 10% cash buffer, not from the CCI signal.

### 5.5 vs the nsealgo composite

| book | CAGR | Sharpe | MaxDD | Names |
|---|---|---|---|---|
| `build_composite_score`, same panel, monthly | 6.55% | 0.07 | −14.84% | 21.3 |
| CCI `V5_deep` | 4.56% | −0.18 | −13.23% | 18.7 |

**The CCI strategy loses to the house composite on return (−1.99 pp) and on Sharpe
(−0.25)**, winning only on MaxDD by 1.61 pp. It adds nothing over what the project
already has, and it dilutes the book (18.7 vs 21.3 names) while doing so.

### 5.6 Negative controls — did it beat a coin?

**100-seed null (`v3_null.py`), random 22-name book through the identical engine,
costs, caps and cash buffer:**

```
random book  CAGR  mean 5.41%  sd 1.39  p05 3.25%  p50 5.38%  p95 7.74%   95% band [2.91%, 7.96%]
random book Sharpe mean -0.04  sd 0.12  p05 -0.23  p95 0.16
CCI V5_deep   CAGR 4.56%   Sharpe -0.18
CCI percentile inside the random null : CAGR 24th   Sharpe 12th
z-score vs null : CAGR -0.61   Sharpe -1.11
```

**Paired test against the median random book** (`v3_null.py §C`): monthly excess over 34
months is **−0.087%/mo**, positive in 16/34 months, **t = −0.27**. Zero detectable
advantage.

Two further controls at matched long fraction (`v1_verify.py §5`, 20 seeds):
random-eligibility-with-momentum-rank 3.90% CAGR / −0.19 Sharpe; true coin 4.84% / −0.09.
CCI's 4.56% / −0.18 sits *below* the true coin on both.

> **Answer to brief §6.5: NO. The strategy does not beat a random signal. It sits at the
> 24th percentile of a 100-seed random null on CAGR and the 12th on Sharpe — i.e. slightly
> worse than picking names at random.**

### 5.7 Cost drag (brief §6.4)

Same signal, cost model varied (`v1_verify.py §6`):

| cost model | rt bps | CAGR | Sharpe |
|---|---|---|---|
| statutory only (`zero_cost`) | 11.92 | 4.95% | −0.14 |
| **base 5 bps/side (reported)** | **21.92** | **4.56%** | **−0.18** |
| `double_slippage` | 31.92 | 4.17% | −0.23 |
| `triple_slippage` | 41.92 | 3.77% | −0.27 |

Gross-of-slippage CAGR is 4.95%, still below buy-and-hold's 8.16% and still Sharpe −0.14.
**Costs are not the reason this fails.** The signal is simply absent; even at the statutory
floor there is nothing to pay for. So the "unviable because of costs" finding does not
apply here — this is the worse and more useful conclusion: **it is unviable because it has
no edge to begin with.**

### 5.8 Brief §6 bug checks

| check | result |
|---|---|
| 1 plausibility (CAGR < 40–50%) | 4.6% — **OK** |
| 2 weight count (not ~48) | 18.7 avg, cap 22 — **OK**, no residual accumulation |
| 3 signal liveness (> 5% of bars) | 18.64% — **OK**, genuinely long |
| 4 cost drag | 0.91%/yr vs 4.56% CAGR — drag is not the binding constraint |
| 5 random control | **FAIL** — 24th/12th percentile of the random null |

---

## 6. Verdict

> **No. `cci_strategy` does not make money on NSE NIFTY-50.** Out-of-sample it returns
> **4.56% CAGR with a Sharpe of −0.18**, against buy-and-hold's **8.16% / +0.19** on the
> identical window, it loses to the `nsealgo` composite (6.55% / 0.07), and it is
> statistically indistinguishable from — in fact slightly below — a randomly selected
> 22-name book (t = −0.27 on 34 months of paired excess).

It is not a costs story (gross-of-slippage is 4.95%, still below market), not a
liveness story (long 18.6% of bars), not a lookahead story (proved by truncation), and
not an overfitting story in the usual sense — TRAIN Sharpes were all ≤ 0.11, so the
in-sample signal was already absent. **This is an honest negative: the whole CCI(20)±100
mean-reversion family has no long-only NSE edge.**

### Most likely reason

The gate is *anti*-momentum, and in Indian cash equities the working cross-sectional
signal at this horizon is momentum, not 20-day reversal. This is directly measurable
(`v2_diagnose.py §B`) — identical book, identical ranking, identical costs, only the gate
toggled:

| window | ranking | no CCI gate | CCI gate on | delta |
|---|---|---|---|---|
| TRAIN | mom126 | 18.38% / Sharpe 0.78 | 6.38% / 0.05 | **−12.00 pp, −0.73** |
| TEST | mom126 | 2.60% / Sharpe −0.22 | 4.43% / −0.20 | +1.83 pp, +0.02 |
| TRAIN | deepest CCI | 18.62% / Sharpe 0.83 | 7.16% / 0.11 | **−11.46 pp** |
| TEST | deepest CCI | 6.60% / Sharpe 0.06 | 4.56% / −0.18 | −2.04 pp |

On TRAIN the gate destroys ~12 pp of CAGR. `nsealgo/factors/core.py` reaches the same
conclusion from the literature in its own module docstring and **removed the reversal
factors entirely**, keeping them only as negative controls — this run is an independent
reproduction of that decision, from the catalog side.

The bucket-level check (`v2_diagnose.py §C`) shows why the apparent TEST edge is not one.
Mean 21-day forward return of oversold names:

| window | oversold (gate buys) | overbought (gate excludes) | raw edge | momentum-matched edge |
|---|---|---|---|---|
| TRAIN | 1.63% (n=15,211) | 1.87% (n=23,548) | **−0.24 pp** | −0.14 pp |
| TEST | 1.13% (n=5,652) | 0.52% (n=7,356) | +0.61 pp | +0.52 pp |

The reversion edge is **negative in TRAIN and positive in TEST** — it flips sign across
windows. Mean 126-day momentum in each bucket is 0.02 / 0.18 (TRAIN) and 0.01 / 0.16
(TEST), so the TEST "edge" is a single regime in which oversold names happened to rebound,
not a stable property. And it is not merely unstable, it is *small relative to noise*: the
momentum-matched TEST edge is +0.52 pp on a 21-day horizon, whereas the 100-seed random
22-name null in §5.6 has a CAGR standard deviation of 1.39 pp. A ~0.5 pp signal that
changes sign between windows and sits well inside the null's dispersion is not tradable at
any rebalance frequency this data supports.

### The one thing I would try next

Not another parameter. **`V4_fast` (CCI period 10) is the one lead** — the only variant
with a positive TEST Sharpe, and the only case where the family comes near buy-and-hold.
The problem is that the one piece of evidence available *before* TEST was consulted said no:
its TRAIN Sharpe was −0.09 and it ranked 3rd of 5. So the honest statement is not "V4_fast
looks good" but "V4_fast is the only hypothesis in this family that the data has not yet
refuted in both windows." Testing it further requires a *fresh* out-of-sample window —
the 2024-01-01 → 2026-10-01 TEST set is now consumed — and it must be entered as a
pre-registered hypothesis in `research/`, not as another sweep. My honest prior, given it
sits at the 2σ/5-draw boundary of the random null (§5.2), is that it will also land inside
that null.

The higher-value action is the opposite one: **retire short-horizon reversal from the
catalog-for-NSE candidate list and record CCI as a validated negative**, so the next agent
does not spend its budget re-deriving it.

---

## 7. BUGS FOUND (harness defects in the interrupted run's scratch)

Three, none in `src/` — all in the agent's own harness. BUG-1 and BUG-2 live in
`s2_train.py` / `s3_test.py` / `s4_posthoc.py`; BUG-3 lives in `common.py`, which every
one of those scripts imports.

### BUG-1 — TRAIN selection window was starved of ~6 months by a warm-up error
**File:** `s2_train.py` (lines 45–47). **Severity: medium — did not change the outcome,
but would have on a closer call.**

```python
close = p.close.loc[TRAIN_START:TRAIN_END]        # slice FIRST
tp    = typical_price(p).loc[TRAIN_START:TRAIN_END]
cci   = cci_panel(tp, period)                     # CCI warm-up inside the window
score = build_score(close, cci, entry, ...)       # mom126 warm-up inside the window
```

Both trailing indicators were built from the TRAIN slice, so their warm-up NaNs fell
*inside* the selection window: `mom126` had **9,457** NaN cells inside TRAIN (vs 4,005
when built on the full panel) and CCI had 4,321 (vs 3,485). The book therefore sat in
**100% cash for roughly the first 126 sessions (~6 months) of an 8-year window**, which
is why `s2_train.py` reported V1_base TRAIN CAGR 5.48% while `s4_posthoc.py` — which
built on the full panel and sliced afterwards — reported 6.38%.

**Fix (applied in `v1_verify.py`):** build every trailing indicator on the **full panel**
and slice afterwards. Trailing indicators are unaffected by slicing after the fact, and
the slice-then-compute order is the one that injects artificial dead time.

*Outcome:* with the warm-up corrected, the TRAIN ranking is **unchanged** — V5_deep still
wins (Sharpe 0.11), and all five TRAIN CAGRs rise by 0.4–0.9 pp. The frozen choice is
therefore unaffected, which is why §5 stands.

### BUG-2 — the reported "TEST negative control" was actually an 18-year number
**Files:** `s3_test.py:125`, `s4_posthoc.py:143`, via `common.random_control`.
**Severity: high — it materially misstates the control.**

`random_control()` runs the backtest on whatever `panel` it is handed, and both callers
passed `close_all` (the **full 2008-01-01 → 2026-10-01 panel**, 4,629 bars) while printing
the result under a "TEST negative control" heading. The prior run's headline claim

> `(i) random eligibility + mom126 rank : CAGR mean 12.53%  Sharpe mean 0.50`

is therefore an **~18-year** statistic compared against a **2.75-year** strategy result —
an apples-to-oranges comparison. The direction of the error matters: it made the random
book look ~8.6 pp *stronger* than it really is, so the prior report concluded "CCI is worse
than random selection" on the strength of a control that was not comparable. Corrected on
TEST, control (i) returns **3.90% CAGR / −0.19 Sharpe**, i.e. CCI (4.56% / −0.18) actually
edges it by 0.66 pp rather than trailing it by 7.97 pp.

**The conclusion nonetheless survives, on a different control.** `s4_posthoc.py §D(ii)`'s
"true coin" (random scores, no ranking) *was* correctly windowed to TEST and returned
4.84% / −0.09 — and §5.6's 100-seed null reproduces and extends it. CCI sits below the
true coin on both CAGR and Sharpe. So the verdict is unchanged; only the reasoning needed
replacing.

**Fix (applied in `v1_verify.py §5`, `v2_diagnose.py §A2`, `v3_null.py`):** every control
is run on the TEST slice only, with the seed set expanded to 100.

Also in `common.random_control`: a dead `dates = [...]` list comprehension over the whole
index was computed and never used; it is now an `assert` that the strategy is long at all.

### BUG-3 — `equal_weight_score` is not an equal-weight book
**File:** `common.py:equal_weight_score`. **Severity: medium — invalidates a comparator
the prior report leaned on.**

A constant score panel ties all 48 names. `build_rebalance_weights` breaks ties with
`np.argsort(-s, kind="stable")`, which preserves column order, and the columns are sorted
alphabetically — so the "equal weight" book is **always the same 22 alphabetically-first
names** (adaniports…bajajfinsv), permanently. Verified in `v3_null.py §A`: 22 names ever
given weight, all 22 in the alphabetical head, zero names outside it.

On TEST that fixed basket returned **9.76% CAGR / Sharpe 0.32**, which is *outside the
upper p95 of a 100-seed random-22 null (7.74%)*. The prior `POSTHOC.txt` used it as the
decisive line — *"still loses to the equal-weight book through the identical engine
(0.32)"* — but 0.32 is the return of one lucky basket, not of an untilted book. The
honest untilted reference points are buy-and-hold (**8.16% / 0.19**) and the random-22
null (**5.41% / −0.04**). **This does not change the verdict** — CCI loses to both — but
it removes a comparator that flattered the conclusion for the wrong reason.

*(Note: my own first pass at this check, `v2_diagnose.py` §A, printed "48 names ever
held" because it counted `weights.sum()` rather than a boolean mask, and concluded the
book was untilted. `v3_null.py` §A does it correctly and supersedes it.)*

### Non-bug, recorded for honesty
`s0_data_check.py` prints `warmup-window flagged count (must be 0)` and gets 333. That is
not a leak: the check builds CCI on the full panel, so CCI is valid from the first bar of
TRAIN. The assertion text is wrong; the numbers are fine.

---

## 8. Files in this directory

| file | role |
|---|---|
| `common.py` | shared harness — panels, vectorised CCI, score construction, comparators |
| `s0_data_check.py` … `s4_posthoc.py` | interrupted run's scratch, retained as-is (BUG-1, BUG-2) |
| `v1_verify.py` | **primary reproduction** — warm-up fix, TRAIN selection, TEST, comparators, controls, cost stress |
| `v2_diagnose.py` | comparator audit, CCI-gate ablation, forward-return bucket analysis |
| `v3_null.py` | constant-score book composition, 100-seed null, paired monthly t-stat |
| `VERIFY_OUT.txt`, `DIAG_OUT.txt`, `NULL_OUT.txt` | captured stdout of the three scripts above |
| `REPORT.md` | this file |

Reproduce: `cd research/agent_cci && ../../.venv/bin/python v1_verify.py && … v2_diagnose.py && … v3_null.py`
(the three are independent and can be run separately; nothing outside this directory is
written or modified).

Lint: `.venv/bin/ruff check research/agent_cci/{common,v1_verify,v2_diagnose,v3_null}.py` → clean.

**Nothing in `src/`, `tests/`, `GOAL.md` or `reports/` was modified. Nothing was committed.**
