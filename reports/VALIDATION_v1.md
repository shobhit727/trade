# Validation Report — v1 · ⚠️ SUPERSEDED BY THE ADDENDUM BELOW

> # ⚠️ READ THE ADDENDUM IN §0 FIRST
>
> **The result in this file is the ORIGINAL v1 measurement, taken on data ending
> 2026-08-25. It is no longer the current result and it must not be quoted.**
>
> **The current result is 9.52% annualised / Sharpe 0.32 / Sortino 0.38 / max drawdown
> −14.92% / Calmar 0.64 — Band D, four of six gate checks failing.**
>
> **The headline has been corrected four times and every correction made it worse:
> 13.40% → 10.97% → 9.89% → 9.71% → 9.52%.** One correction was a data extension plus two
> breaches of our own portfolio limits; one was a **critical** bug — an engine that charged
> **half** the real cost stack; one was a turnover budget that diluted exits so that 59% of
> a sparse book's held weight was stale residue; and the fourth is a **silent selection
> bug** — tied scores were resolved **alphabetically**, not at random. See §0.3.
>
> **Everything below the addendum is retained unchanged as the historical record of the
> original measurement.** Where it conflicts with §0, §0 wins. Nothing has been edited to
> make the old numbers look better or worse than they were.
>
> Three findings lead, per `GOAL.md` §6.7:
> - **§0.3 — the engine charged exactly half the real cost stack.** Every CAGR this project
>   had ever reported was flattered, and the Gate 4 slippage stress ran at half strength.
> - **§0.5 — a tied or discrete score panel silently produced a zero-turnover book.** A
>   binary 0/1 mask under the old engine held *the same alphabetically-first names every
>   month, forever*: 1 distinct book across 225 rebalances, 0.0% turnover. Results built
>   that way are not trustworthy and must be re-run.
> - **§0.2 — 27 trading days moved Sharpe from 0.66 to 0.44 and the band from C to D**,
>   with no code change at all. A fragility signal about the strategy, not a data defect.

---

# §0 — ADDENDUM v4 (2026-10-12): the authoritative result

**Reproduce:** `.venv/bin/python research/validate.py`
**Data:** `data/nse/*_1d.csv`, re-fetched 2026-10-06 (`tools/recover_nse_data.py`),
cleaned per `reports/DATA_AUDIT.md` §5 (rules C1–C9)
**Window:** 2008-01-01 → 2026-10-01 (19.0y), 48 symbols, **4,625 trading days**
**Provenance:** engine `29764f562cd5` · loader `c1badf5f7df8` · costs `ba350aef75b3` ·
panel `389b082b832f`
**Verdict: 🔴 BAND D. SIX GATE CHECKS RUN, FOUR FAIL. NOT 3%/month. NOT DEPLOYABLE.**

## 0.1 ⚠️ THE CHAIN OF CORRECTIONS — every number this project published was too high

**This table is the headline of the report. Every row below the first is a correction, and
every correction moved the number DOWN.**

| # | Measurement | OOS CAGR | OOS Sharpe | Band | What was fixed |
|---|-------------|----------|-----------|------|----------------|
| 1 | **v1** — data to 2026-08-25 | **13.40%** | **0.66** | **C** | The original measurement. **SUPERSEDED.** |
| 2 | **v2** — data to 2026-10-01 | **10.97%** | **0.44** | **D** | +27 sessions of data **and** two §3.2 breaches: a 25.66% single name against a 12% cap, and 48 names held against `max_positions` 30. **SUPERSEDED.** |
| 3 | **v2b** | **9.89%** | **0.35** | **D** | **Bug 1 (CRITICAL): the engine charged exactly half the real cost stack.** **SUPERSEDED.** |
| 4 | **v3** | **9.71%** | **0.34** | **D** | **Bug 2 (HIGH): residual-weight dilution in `apply_turnover_budget`.** **SUPERSEDED.** |
| 5 | **v4 — CURRENT** | **9.52%** | **0.32** | **D** | **Bug 5 (CRITICAL, silent): tied scores were resolved *alphabetically*.** Now `blake2b(date\|symbol)`. |

**13.40% → 10.97% → 9.89% → 9.71% → 9.52%.** A reader who stopped at v1 was reading a
figure **40% too high**; at v2, still **15% too high**.

> Rows 1–4 are retained **only** as the historical correction chain. They are superseded
> results and must never be quoted as current.

**The structural finding, and it is about method rather than about strategy: nothing in
the routine pipeline found any of these.** All five bugs were found by adversarial probing
of the harness while 38 catalog trials were being run on top of it — a cost-ratio
assertion, a plausibility check on realised exposure, and a run of checks whose whole
purpose was to attack the engine's own bookkeeping. The current number is the current
number **because someone went looking for it**, not because the pipeline was trustworthy.

**No step in this project ever made the strategy look better by fixing a bug.** Every fix
removed an artifact that had been *adding* return. Five for five. A correction that had
*improved* the number would have been the thing to investigate.

## 0.2 FINAL HEADLINE

| Metric | v1 | v2 | v2b | v3 | **v4 — CURRENT (authoritative)** | Target | |
|--------|----|----|-----|----|--------------------------------|--------|---|
| **OOS annualised** | 13.40% | 10.97% | 9.89% | 9.71% | **9.52%** | 42.6% | ❌ 4.5× short |
| **OOS monthly equivalent** | +1.053% | +0.871% | +0.789% | +0.775% | **+0.761%** | 3.000% | ❌ |
| **OOS Sharpe** | 0.66 | 0.44 | 0.35 | 0.34 | **0.32** | ≥ 0.7 | ❌ |
| **OOS Sortino** | — | — | — | — | **0.38** | — | — |
| **OOS Max Drawdown** | −15.41% | −12.91% | — | −14.92% | **−14.92%** | < 35% | ✅ |
| **OOS Calmar** | 0.87 | 0.85 | — | 0.65 | **0.64** | — | ✅ |
| **OOS positive years** | 12/13 (92%) | 11/13 (85%) | — | 10/13 (77%) | **10/13 (77%)** | ≥ 60% | ✅ |
| **Band (`GOAL.md` §2.3)** | **C** | D | D | D | **D** | C or better | ❌ |

**The v4 column is the only valid result in this document.** Every other column is quoted
only to size the corrections.

> **Cost drag on the final window: 6.17%/yr** at 2.00x/yr turnover (measured on the v3
> engine; not re-measured on v4 — see `reports/STRESS_v3.md`, which carries a staleness
> banner). This was previously left unmeasured at 5.93%/yr / 1.99x, and was then re-measured
> to 6.17% / 2.00x when cleaning rule **C9** (frozen-price dropping, §5 of `DATA_AUDIT.md`)
> removed 539 vendor-freeze bars from 2008–2010. **The OOS result did not move** — those
> bars fall entirely in the training half of fold 6, and every OOS test window starts
> 2014-11-26 or later. The direction of the change is *more* conservative: a higher measured
> cost drag on an unchanged OOS number. See [`reports/STRESS_v3.md`](STRESS_v3.md) for the
> full Gate 4 re-run, which **fails** two of its checks.

**Against the benchmark** (equal-weight buy & hold of the same 48 symbols, identical test
windows):

| | CAGR | Sharpe | MaxDD |
|---|---|---|---|
| **OOS strategy (v4)** | **9.52%** | **0.32** | **−14.92%** |
| **OOS benchmark (v4)** | **17.12%** | **0.68** | −37.97% |
| **Difference** | **−7.60pp** | **−0.36** | **+23.05pp** |

**−7.60pp/yr behind buy-and-hold**, for a drawdown that is 61% shallower. The return
deficit has widened at every measurement: −5.36pp (v1) → −6.00pp (v2) → −7.41pp (v3) →
**−7.60pp (v4)**.

## 0.3 ⚠️ THE FIVE ENGINE BUGS — all five inflated every earlier number

All fixed in `src/nsealgo/backtest/engine.py` (**on disk, uncommitted**) and in
`src/nsealgo/data/loader.py` (C8/C9). Found by adversarial probing while catalog trials ran
on top of the engine — **not** by the normal validation pipeline.

| # | Bug | Severity | Measured symptom | Cost of the fix |
|---|-----|----------|------------------|-----------------|
| **1** | **Cost charged at exactly half.** `all_in_round_trip_bps` is quoted per unit of **total** turnover (a full rotation is `sum\|dW\| = 2.0`), but the engine multiplied it by **one-way** turnover `sum\|dW\|/2`. Ratio proven **0.500000**, not approximately. | **CRITICAL** | **Every CAGR in the project was flattered.** The **Gate 4 slippage stress ran at half strength** — a gate certifying a robustness property the backtest never tested. | 10.97% → **9.89%** CAGR, 0.44 → **0.35** Sharpe |
| **2** | **Residual-weight dilution.** `apply_turnover_budget` blended the *whole* book toward the new target, so a name the target no longer wanted decayed instead of exiting. | HIGH | **59% of a sparse book's held weight was stale residue**; realised exposure averaged **~0.6 of the intended 0.9**. The book measured the harness, not the signal. | 9.89% → **9.71%** CAGR. Now whole-position exits, all-or-nothing adoption when the budget binds. |
| **3** | Sector cap redistributed weight **without re-capping** the receiving names, so the single-name cap was applied first and then invalidated | HIGH | **worst single weight 25.66%** against a 12% cap (§3.2 breach) | worst single weight **10.80%** |
| **4** | Dead residual weights accumulated — positions below the material threshold were never dropped | HIGH | **48 names held** against `max_positions` 30 (§3.2 breach) | max names **30**, worst sector **22.50%** |
| **5** | **Tied scores were resolved alphabetically.** `np.argsort(-score, kind="stable")` breaks ties by **column position**, and the panel's columns are alphabetical — so every tied score selected names alphabetically. `build_composite_score` fills missing factor values with the median **0.5**, manufacturing ties by construction. | **CRITICAL** (silent) | On a **binary 0/1 mask** the engine produced **1 distinct book across 225 rebalances and 0.0% turnover** — a frozen book with a fictional monthly rebalance and understated cost drag (§0.5). On the production composite it changed the delivered book on **6 of 225** rebalances and moved the headline by flipping **1 fold's train-window argmax out of 6**. | 9.71% → **9.52%** CAGR, 0.34 → **0.32** Sharpe. Engine `d93815344bd3` → `29764f562cd5` |

**Bug 1 in detail, because it is the one that matters.** A complete rotation of the book —
sell 100%, buy 100% — is `sum|dW| = 2.0`, i.e. 200% of one-way turnover. The rate
`all_in_round_trip_bps` is quoted per unit of *total* turnover. Charging
`one_way_turnover × rate` therefore under-charges by exactly **2×**. The agent that found
it proved the ratio was `0.500000` rather than approximately, which is what distinguishes
a unit-convention bug from a modelling choice. The consequence is not a slightly optimistic
number: **every performance figure this project had ever published was wrong in the
optimistic direction, and one of its robustness gates had never actually been tested.**

**This must be said plainly: part of the earlier result was not obtainable under the rules
`GOAL.md` mandates.** A backtest that pays half the real cost, or that quietly holds 25% in
a single name, is not the strategy this constitution describes, whatever it prints. Any
return produced by breaching a limit is an artifact of the harness, not a return of the
strategy, and it is recorded here as one.

**Gate 4 caveat, carried forward:** the 2× slippage stress test is not a valid piece of
evidence in either direction until it is re-run against the fixed engine.

### 0.3.1 ⚠️ Reproducibility: `engine_sha`

`BacktestResult` now carries **`engine_sha`** — a hash of the engine source, computed at
import, printed with every result and stored alongside it.

This was added because **the engine was rewritten by another process mid-experiment, twice,
uncommitted, both times changing `apply_turnover_budget`.** Dozens of concurrent agent
reports were produced against different engine revisions with no way to distinguish them. At
least one agent had to **discard an entire TRAIN table** after discovering it had been
measured on the pre-fix engine — it had shown Sharpe **+0.42** where the fixed engine gave
**−0.08**. The signal was bit-identical; only the engine differed.

**Rule adopted: if the `engine_sha` on a stored result does not match the working tree, the
result is stale and must be re-run rather than quoted.** A number without an engine
fingerprint is not reproducible, and an unreproducible number is an opinion.

**This rule has now paid for itself twice.** The second application is bug 5:

| engine | walk-forward OOS | fold-2 train pick |
|---|---|---|
| `d93815344bd3` (superseded) | CAGR 9.71% / Sharpe 0.3365 | `22\|126\|0.6` |
| `29764f562cd5` (current) | CAGR **9.52%** / Sharpe **0.3202** | **`22\|252\|0.6`** |

Two engines differing **only** in how a tied score is broken — nothing about the strategy,
the factors, the costs, the data or the folds — produce different walk-forward headlines
and select a **different parameter cell in 1 fold out of 6**. Verified by direct ablation:
emulating the old alphabetical tie-break inside the current engine reproduces 9.71% /
0.3365 exactly, and the `_thin` / `_exit_allocation` tie-break fixes alone move the number
by 0.00. **The tie-break accounts for 100% of the 9.71 → 9.52 move.**

This is the strongest evidence yet that the **selection layer is the weakest part of this
harness**, and it is direct support for `reports/SELECTION_STUDY.md` §2.5: a train-window
argmax that can be flipped by reshuffling 2.7% of its own rebalance books is reading noise.

## 0.4 ⚠️ THE FRAGILITY FINDING — 27 trading days moved the band

**Still true, and the corrections above made the picture worse rather than better.**

| | End date | Extra sessions | OOS CAGR | Sharpe | Band |
|---|---|---|---|---|---|
| v1 | 2026-08-25 | — | 13.40% | 0.66 | **C** |
| v2 | 2026-10-01 | **+27** | 10.97% | 0.44 | **D** |
| v3 | 2026-10-01 | +0 | 9.71% | 0.34 | **D** |
| **v4 (current)** | 2026-10-01 | +0 | **9.52%** | **0.32** | **D** |

Between v1 and v2 **nothing about the strategy changed**: same code, same Indian cost stack,
same parameters, same six-fold sliding-origin walk-forward design. The only variable was the
data end date. **Twenty-seven sessions — about six weeks — removed a third of the measured
risk-adjusted return and dropped the system out of the band it was previously judged
against.**

There is now a **second** fragility axis, and it is worse because it is inside the code
rather than in the data: between v3 and v4, with the **same end date** and the same data,
the headline moved **9.71% → 9.52%** because a tie-break flipped one fold's selected cell.
**A 2.7% perturbation of the delivered book is worth 0.19pp/yr of headline.**

| Over the 27-session window (2026-08-26 → 2026-10-01) | Return |
|---|---|
| Equal-weight market proxy | **−7.7%** |
| Strategy (OOS series) | **−6.9%** |

The strategy **lost money**, but it lost roughly what the market lost and marginally less —
this is not an alpha failure in the window, and the portfolio construction held up. The
damage is entirely to the *statistics*: 27 down-days are enough to pull a 19-year Sharpe
down by 0.22.

**The finding that matters is not "the last six weeks were bad". It is that the v1 band was
one noisy draw away from being wrong.** A result that changes band when the end date moves
by six weeks is not a measurement of the strategy's edge; it is a measurement of where the
end date happened to fall.

**Standing rule, strengthened:** every figure reported by this project must carry **its end
date and its `engine_sha`**. A CAGR without a window is not a measurement, and a CAGR
without an engine fingerprint is not reproducible.

## 0.5 Gate re-check (`GOAL.md` §5)

**Six gate checks. Four fail.**

| # | Gate | Requirement | v1 | v2 | v3 | **v4 (current)** | |
|---|------|-------------|----|----|-----|------------------|---|
| 1 | G3 | OOS CAGR ≥ 12% | 13.40% ✅ | 10.97% ❌ | 9.71% ❌ | **9.52%** | ❌ |
| 2 | G3 | OOS Sharpe ≥ 0.7 | 0.66 ❌ | 0.44 ❌ | 0.34 ❌ | **0.32** | ❌ |
| 3 | G3 | OOS MaxDD < 35% | −15.41% ✅ | −12.91% ✅ | −14.92% ✅ | **−14.92%** | ✅ |
| 4 | G3 | Positive years ≥ 60% | 92% ✅ | 85% ✅ | 77% ✅ | **77%** | ✅ |
| 5 | G4 | Beat benchmark CAGR | −5.36pp ❌ | −6.00pp ❌ | −7.41pp ❌ | **−7.60pp** | ❌ |
| 6 | G4 | Beat benchmark Sharpe | −0.11 ❌ | −0.23 ❌ | −0.34 ❌ | **−0.36** | ❌ |

**Three failed at v1. Four fail now**, and the band has fallen from C to D — which also
fails Gate 3's "Band C or better" line. The trend in the deficit against the benchmark has
monotonically worsened across every measurement.

**Default verdict per `GOAL.md` §5: NO DEPLOY.** The system is research-complete for v4 and
not capital-ready. **Nothing about §5 has been changed, relaxed or reinterpreted to
accommodate the result.**

## 0.6 Catalog trials — 38 of 38 strategies failed

> ## 🚨 §0.5a — THE ZERO-TURNOVER BOOK: results on tied/binary panels are not trustworthy
>
> `build_rebalance_weights` used `np.argsort(-score, kind="stable")`. A stable sort resolves
> ties by **column position**, and the panel's columns are alphabetical — so **every tied
> score was resolved alphabetically**. `build_composite_score` fills a missing factor value
> with the cross-sectional median **0.5** (`src/nsealgo/factors/core.py:219`), manufacturing
> ties by design; a **binary 0/1 mask** ties every flagged name exactly.
>
> **Verified directly** on a static 0/1 mask, 226 monthly rebalances, 22-name book:
>
> | engine | distinct books | mean monthly turnover |
> |---|---|---|
> | `d93815344bd3` (alphabetical) | **1 / 225** | **0.0%** |
> | `29764f562cd5` (`blake2b`) | 223 / 225 | 15.7% |
>
> The old engine held **the same alphabetically-first names every month, forever**. That is a
> frozen portfolio wearing a "monthly rebalance" label: it pays the cost stack once and then
> never trades, so its measured cost drag is understated and its turnover statistics are
> fictional.
>
> **Exposure of the production composite is much smaller, and the honest figures are these**
> (re-measured, 226 rebalance dates):
>
> | measurement | count |
> |---|---|
> | dates containing at least one exact duplicate score | **178 / 226** |
> | dates where a tie sits exactly on the top-22 cut | **43 / 226** |
> | dates where the old and new rules select a **different set of names** | **6 / 225** (2.7%) |
>
> So the production headline moved because a 2.7% perturbation flipped **1 fold's train
> argmax out of 6** — not because the tie-break decided most books.
>
> **Consequences, binding:**
> - **Any result produced on a binary or heavily-tied score panel under `d93815344bd3` or
>   earlier must be re-run.** Its CAGR, Sharpe and conclusions are all suspect.
> - **The 38-agent catalog sweep is affected.** Binary gates are exactly the construction
>   these agents were built from, so many of the 38 negative results are **not trustworthy
>   in either direction** and need re-validation. Listed in
>   [`reports/CATALOG_TRIALS.md`](CATALOG_TRIALS.md). **Those reports are deliberately not
>   edited here** — they are other authors' documents and a correction has to be re-derived,
>   not asserted.
> - Before trusting any run, check `diag["avg_names"]`, `diag["min_names"]` and
>   `diag["avg_invested_weight"]` (all three now emitted by `run_backtest`). **A
>   zero-turnover book is a bug in the setup, not a strategy.**

The full per-strategy table, the defect list and the methodology notes are in
**[`reports/CATALOG_TRIALS.md`](CATALOG_TRIALS.md)**. Summary:

- **38 agents, 38 negative, zero made money.** One strategy per agent, parameters declared
  up front, selected on **TRAIN 2016–2023**, evaluated once on **TEST 2024–2026**, net of
  the full Indian delivery stack (**21.92 bps all-in**).
- **Not one beat plain buy-and-hold out of sample.** Several lost to a **coin flip**, which
  `research/AGENT_BRIEF.md` §6.5 names as the minimum bar.
- **Why:** these are long/short **crypto** time-series indicators dropped into a **long-only
  cross-sectional** NSE book. In crypto `−1` means cut to cash; in a delivery account `−1`
  maps to "a slightly different basket of 22 large caps", beta ≈ 0.9. The risk-control
  mechanism they were written around **does not exist in this market**.
- **Indian equities continued; they did not reverse.** Mean reversion is not merely absent
  here — it is **inverted**. This independently confirms why the reversal factors were
  removed from `src/nsealgo/factors/core.py`.
- **Costs were never the binding constraint.** Strategies lost on selection, not fees.

### 0.6.1 Full-window in-sample sweep (secondary, for completeness)

`research/benchmark_catalog.py`: 84 discovered, 80 evaluated, 2 never signalled, 2
crypto-only skipped, 0 errors. **None beat the composite** — best catalog Sharpe 0.76 vs
composite 0.88, best Calmar 0.91 vs 0.95. The best catalog result is *below* pure 6-month
momentum (0.80) and within noise of a **random 50/50 mask** (0.77): the adapter gives each
strategy the benefit of momentum ranking, and the leading rows produce byte-identical books
(correlation 1.000). **This is a full-window in-sample comparison and is not comparable to
the 0.34 OOS figure above.**

## 0.7 The data — recovery is faithful, and three defects are now on the record

`data/nse/` was accidentally deleted locally and re-fetched on **2026-10-06** with
`tools/recover_nse_data.py`. **The recovery is faithful and provably so:** truncating the
recovered panel back to 2026-08-25 and re-running the walk-forward reproduces the original
v1 measurement — 13.37% / 0.65 / −15.38% against the recorded 13.40% / 0.66 / −15.41%, with
the same parameters selected in every fold.

| Check | Result |
|---|---|
| Symbols fetched | 50 / 50 files present, all ending 2026-10-01 |
| Verified vs `research/_audit_1d.csv` | **49 / 50** |
| Duplicate timestamps | 0 |
| Non-positive prices | **47 bars, all `adanient`, 2002-07** (excluded by rule **C3**) |
| Unadjusted split bars | **114 bars** with >20% single-bar moves (excluded by **C1**, pre-2008) |
| One-day moves > 45% in the full sample | 0 |
| **Stray weekend bars** | **4** (2010-02-06 Sat, 2019-10-27 Sun, 2020-11-14 Sat, 2025-02-01 Sat) — **now dropped by rule C8**. Each had planted an interior NaN in 42 symbols, corrupting every rolling/ewm indicator for `period` bars after the hole, silently, because the loader only validated *within* each symbol. |

**The panel is 4,625 trading days** after C8 removed those 4 dates.

**Bias is unchanged and still applies in full.** ~7.3%/yr (survivorship + dividends absent
— the panel is price-return only). Measured on the v1 window and carried forward unchanged,
because it is a property of the universe construction rather than the end date:

| Figure | Reported | Bias-corrected |
|---|---|---|
| Strategy (v1) — **SUPERSEDED** | 13.40% | ≈ 6.1% |
| Strategy (v2) — **SUPERSEDED** | 10.97% | ≈ 3.7% |
| Strategy (v3) — **SUPERSEDED** | 9.71% | 3.57% |
| **Strategy (v4 — CURRENT)** | **9.52%** | **3.38%** |
| Benchmark (v4) | 17.12% | ≈ 9.83% |

**Derivation (correct, and reconciled):** our panel is *price-return only*, so dividends
must be ADDED before the discount is applied.

```
  price return (measured OOS)      9.52%
+ dividend yield (absent data)   + 1.15%   -> total return 10.67%
- survivorship + selection bias  - 7.29%
= bias-corrected                  3.38%
```

An earlier draft wrote this as `9.71 - 7.3 = 3.6%`, which does not reconcile — it omitted
the dividend add. Applying the corrected derivation to the current headline gives
**3.38%**, and the open item remains closed. The ~7.3pp discount was measured on the v1
full window and carried forward unchanged because it is a property of the universe
construction, not of the end date.

**The claim "beats the official NSE index TRI" was never valid** — §6.1 of the original
report below already established that. At v4 it is further wrong: bias-corrected, the
strategy is **below** the index on return. A 61% shallower drawdown is the only claim that
survives.

## 0.8 What is required before any capital is deployed

Four of six gate checks fail. In order of expected value:

1. **Prove the band is stable, not window-dependent.** §0.4 is the binding problem, and it
   is a research problem, not a parameter-tuning one: the strategy needs an edge that does
   not depend on where the sample ends. Candidate directions — an exposure rule that scales
   with realised volatility rather than switching on a trend threshold, and an explicit
   evaluation of the Sharpe estimate's confidence interval at 19y. **Until a re-measurement
   over a longer window reproduces the band, no other fix counts.**
2. **Restore the return.** 9.52% is below the 12% floor and **7.60pp/yr behind** the
   benchmark, and the deficit has widened at every measurement. Note that the entire crypto
   catalog scored *below pure momentum* out of sample (§0.6), so the search space is not
   where the answer is. **And note the direction of travel: production now sits at the 29th
   percentile of the random null on gross return** (§0.5a / `GOAL.md` §0.0), so "restore the
   return" means finding an edge, not recovering one.
3. **Re-run Gate 4 against the current engine.** The 2× slippage stress ran at half strength
   under the half-cost bug, and the whole sweep is now on the superseded `d93815344bd3`.
   See the staleness banner in `reports/STRESS_v3.md`.
4. **Fix the selection layer, or stop trusting the headline.** The v4 tie-break fix moved
   the headline 0.19pp/yr by reshuffling only 6 of 225 rebalances, because it flipped one
   fold's train-window argmax. Until the selection rule is shown to be stable under that
   class of perturbation, no walk-forward number from this harness should be treated as a
   measurement of the strategy (§0.3.1, §0.4).
5. **Re-validate the catalog sweep on the current engine** (§0.5a). Binary-gated agents ran
   on an engine that turned tied scores into a frozen alphabetical book; their verdicts are
   not settled.
6. **Reconcile the bias-corrected figure** (§0.7) — now derived as 3.38%, which *does*
   reconcile: `9.52 + 1.15 − 7.29`.
5. **Make the fresh-data path automatic.** The panel was restored by a one-off recovery
   script. Gate 6 requires a repeatable Kite historical feed, and until that exists the
   measurement window will keep being set by hand — precisely the failure mode §0.4 exposed.
6. **Gate 6 — production readiness.** Live/paper parity, kill-switch tests, broker
   reconciliation. None of this is built yet.
7. **Land the §0.3 engine fixes and the `engine_sha` fingerprint.** They are on disk and
   uncommitted; **every reported number depends on them.**

**Current status: research-complete for v3. Capital NOT authorised.**

---

# §0-S — SUPERSEDED v2 MEASUREMENT (2026-10-06), retained as the historical record

> This is the intermediate measurement that was briefly the published headline — 10.97% /
> Sharpe 0.44. **It is not a result of the code as it now stands.** It is retained here
> because it is the step that quantifies the fragility finding (§0.4) and because deleting
> it would hide the size of the corrections. Its cost model was still charging half the
> real cost and its turnover budget was still diluting exits.

**v2 headline:** 10.97% OOS annualised / +0.871% monthly / Sharpe 0.44 / MaxDD −12.91% /
Calmar 0.85 / 11 of 13 calendar years positive / Sortino 0.52 / all-in cost drag 3.11%/yr /
**Band D** — six gate checks, four failing.

**v2 vs benchmark:** strategy 10.97% / 0.44 / −12.91% / 0.85 against equal-weight
buy-and-hold 16.96% / 0.67 / −37.97% / 0.45. Difference **−6.00pp/yr** of CAGR for a
drawdown 66% shallower.

### v2 OOS yearly returns

| Year | Benchmark | Strategy | Alpha |
|------|-----------|----------|-------|
| 2014 | −1.17% | 0.22% | +1.39% |
| 2015 | 4.16% | 1.45% | −2.71% |
| 2016 | 10.24% | 7.55% | −2.69% |
| 2017 | 42.06% | 32.55% | −9.50% |
| 2018 | 0.90% | **−0.20%** | −1.09% |
| 2019 | 16.33% | 11.29% | −5.04% |
| 2020 | 28.28% | 2.19% | **−26.10%** |
| 2021 | 44.50% | 21.91% | **−22.59%** |
| 2022 | 7.86% | 4.63% | −3.23% |
| 2023 | 38.58% | 30.48% | −8.11% |
| 2024 | 20.26% | 33.02% | **+12.76%** |
| 2025 | 13.34% | 5.14% | −8.20% |
| 2026 | −8.26% | **−8.94%** | −0.69% |

**11 of 13 years positive (85%)** at v2, down from 12/13 at v1 and **10/13 (77%) at v3**.
The overlay pattern from §3.1 of the v1 report holds throughout: it wins in flat and down
years and gives back heavily in sharp recoveries (2020 −26.10pp, 2021 −22.59pp).

### v2 walk-forward folds (6 folds, sliding origin, 6y train / 2y test)

| Fold | Train | Test | OOS CAGR | Sharpe | MaxDD | Selected params |
|------|-------|------|---------|--------|-------|-----------------|
| 1 | 2018-11-14 → 2024-10-18 | 2024-10-21 → 2026-10-01 | **−1.55%** | **−1.05** | −10.48% | n=22, lb=126, thr=0.00 |
| 2 | 2016-11-25 → 2022-10-25 | 2022-10-27 → 2024-10-18 | 30.23% | 1.78 | −7.53% | n=22, lb=126, thr=0.60 |
| 3 | 2014-12-01 → 2020-11-05 | 2020-11-06 → 2022-10-25 | 13.76% | 0.59 | −12.56% | n=22, lb=126, thr=0.60 |
| 4 | 2012-12-05 → 2018-11-13 | 2018-11-14 → 2020-11-05 | 6.86% | 0.08 | −9.47% | n=15, lb=126, thr=0.00 |
| 5 | 2010-12-10 → 2016-11-24 | 2016-11-25 → 2018-11-13 | 14.71% | 0.82 | −12.46% | n=15, lb=126, thr=0.60 |
| 6 | 2008-12-18 → 2014-11-28 | 2014-12-01 → 2016-11-24 | 4.44% | −0.12 | −12.91% | n=15, lb=126, thr=0.60 |
| **All** | | **2014-12 → 2026-10** | **10.97%** | **0.44** | **−12.91%** | |

The most recent fold was already negative at v2 (−1.55% CAGR, Sharpe −1.05) — it is the fold
the 27 new sessions landed in. Fold dispersion −1.55% → 30.23%. Fold-level numbers were **not
re-measured after the §0.3 fixes** and must not be quoted; only the aggregate is current.

---
---

# ORIGINAL v1 REPORT (2026-10-05) — retained unchanged as the historical record

**Reproduce:** `.venv/bin/python research/validate.py` (host venv) or
`docker compose -f docker-compose.research.yml run --rm research python research/validate.py`
**Data:** `data/nse/*_1d.csv`, cleaned per `reports/DATA_AUDIT.md` §5
**Window:** 2008-01-01 → 2026-08-25 (18.9y), 48 symbols, 4,602 trading days
**Verdict (at the time): 🟡 BAND C — real but modest. NOT 3%/month. NOT YET DEPLOYABLE.**
**Superseded by §0. The Band C verdict and the 13.40% headline no longer stand.**

---

## 1. Headline: the honest number

| Metric | Result |
|--------|--------|
| **OOS annualised (walk-forward)** | **13.40%** |
| **OOS monthly equivalent** | **+1.054%** |
| Target | 3.000%/month = 42.6% annualised |
| **Gap to target** | **~3.2× short** |
| OOS Sharpe | 0.66 |
| OOS Max Drawdown | **−15.41%** (139 trading days) |
| OOS Calmar | 0.87 |
| OOS positive years | 12/13 (92%) |
| All-in cost drag | 3.03%/yr (measured, not assumed) |

**I did not reach the target. The target is not reachable — see §5.**

---

## 2. Walk-forward out-of-sample detail

6 folds, sliding origin. Each fold selects parameters on **train only**, then is
evaluated unchanged on the test window. Test windows are contiguous 2014→2026.

| Fold | Train | Test | OOS CAGR | Sharpe | MaxDD | Selected params |
|------|-------|------|---------|--------|-------|-----------------|
| 6 | 2008-11 → 2014-10 | 2014-10 → 2016-10 | 8.94% | 0.26 | −15.41% | n=15, lb=252, thr=0.60 |
| 5 | 2010-11 → 2016-10 | 2016-10 → 2018-10 | 13.54% | 0.73 | −9.10% | n=15, lb=126, thr=0.00 |
| 4 | 2012-10 → 2018-10 | 2018-10 → 2020-09 | 6.53% | 0.05 | −9.47% | n=15, lb=126, thr=0.00 |
| 3 | 2014-10 → 2020-09 | 2020-09 → 2022-09 | 20.18% | 1.03 | −11.40% | n=22, lb=126, thr=0.35 |
| 2 | 2016-10 → 2022-09 | 2022-09 → 2024-09 | 31.05% | 1.87 | −7.53% | n=22, lb=126, thr=0.35 |
| 1 | 2018-10 → 2024-09 | 2024-09 → 2026-08 | 2.50% | −0.48 | −8.12% | n=22, lb=126, thr=0.35 |
| **All** | | **2014 → 2026** | **13.40%** | **0.66** | **−15.41%** | |

Fold dispersion is wide (2.5% → 31.1%), which is normal for 2-year windows and is
itself a reason not to trust any single number here.

---

## 3. vs Benchmark — the uncomfortable part

Benchmark is **equal-weight buy & hold of the same 48 symbols**, over identical windows.

| | CAGR | Sharpe | Sortino | MaxDD | Calmar |
|---|---|---|---|---|---|
| **OOS strategy** | **13.40%** | 0.66 | 0.77 | **−15.41%** | **0.87** |
| **OOS benchmark** | **18.77%** | 0.77 | 0.93 | −37.97% | 0.49 |
| **Difference** | **−5.36%** | −0.11 | −0.16 | **+22.56%** | **+0.38** |

**The strategy does not beat buy-and-hold on return. It beats it decisively on risk.**

- Returns **5.4pp/yr lower** than the benchmark.
- Drawdown **58% shallower** (−15.4% vs −38.0%).
- Calmar **1.8× better** (0.87 vs 0.49).

### 3.1 Where the alpha is and isn't

| Year | Benchmark | Strategy | Alpha |
|------|-----------|----------|-------|
| 2015 | 4.16% | 3.85% | −0.31% |
| 2016 | 10.24% | 14.87% | **+4.62%** |
| 2018 | 0.90% | 1.70% | **+0.80%** |
| 2020 | 28.28% | 7.36% | −20.92% |
| 2021 | 44.50% | 26.64% | −17.86% |
| 2023 | 38.58% | 31.78% | −6.80% |
| 2024 | 20.26% | 30.85% | **+10.59%** |

The overlay wins in **flat/down years** and loses badly in **sharp recoveries** (2020,
2021). This is the textbook time-series-momentum whipsaw, and it is a real cost, not a
bug. It buys the drawdown reduction with upside participation.

---

## 4. Gate checks (`GOAL.md` §5)

| Gate | Requirement | Result | |
|------|-------------|--------|---|
| G3 | OOS CAGR ≥ 12% | 13.40% | ✅ |
| G3 | OOS Sharpe ≥ 0.7 | 0.66 | ❌ |
| G3 | OOS MaxDD < 35% | −15.41% | ✅ |
| G3 | Positive years ≥ 60% | 92% | ✅ |
| G4 | Beat benchmark CAGR | −5.36% | ❌ |
| G4 | Beat benchmark Sharpe | −0.11 | ❌ |

**Band: C** (`GOAL.md` §2.3, by CAGR). Band C requires Sharpe ≥ 0.7 — **missed by 0.04**.

**Default verdict per `GOAL.md` §5: NO DEPLOY.** Three gates fail. The system is
*research-complete for v1*, not capital-ready.

---

## 5. Why 3%/month was never reachable

An evidence survey (`reports/FACTOR_EVIDENCE.md`) established this before the numbers
were produced:

| Reference | Annualised |
|-----------|-----------|
| **Our OOS result** | **13.4%** |
| NIFTY-50 TRI, 20yr to Feb 2026 (NSE official) | 12.44% |
| NIFTY-50 TRI since 1999 (NSE official) | 14.2% |
| Best documented Indian long-only multi-factor (Conservative Formula, QED) | ~12.6% *over* BSE-100 |
| Indian active fund managers, net of fees (425 funds, 2013–2024) | **≈0 alpha** |
| Best peer-reviewed Indian long-short WML | 17.3% *(long-short — not available to us)* |
| **Target** | **42.6%** |

The target is **3.0–3.4× the entire long-run return of the index** and ~2.5× the best
peer-reviewed Indian factor result even with shorting, which a delivery account cannot
do. No academic, regulator, index-vendor or credible practitioner source supports
anything above ~20% for a long-only Indian strategy.

**13.40% OOS is a good result.** It sits at the top of the honest band
(10–14% p.a. net identified by the survey), it beats the official index TRI, and it
does it with a −15% drawdown instead of −38%. It is 1.05%/month, not 3%.

---

## 6. ⚠️ Survivorship bias — the benchmark is unfairly strong

The benchmark (18.77% OOS CAGR) is **3.2× the official NIFTY-50 TRI** for a comparable
period. That gap is survivorship bias, and it cuts both ways:

- The **universe** is today's 48 NIFTY-50 members backfilled to 2008. Names that left
  the index — and went to zero (Satyam, IL&FS, DHFL, Yes Bank, Vodafone Idea) — are
  absent. Those failures stayed *listed and tradable*, so their returns should have been
  in the panel regardless of index removal.
- **Diagnostic (from the survey):** a correct 2008→2026 NIFTY-50 panel should contain
  Satyam, IL&FS, DHFL, Yes Bank and Vodafone Idea. **This panel contains none of them.**
  That is direct confirmation the panel is a survivor set.

**Consequence:** both the benchmark *and* the strategy's absolute return are optimistic.
The **relative** comparison (strategy vs benchmark over identical windows and identical
cost treatment) is the more meaningful number here, and that is the −5.36%/yr CAGR
deficit in §3.

Unquantified. Fixing it requires a point-in-time NIFTY-50 constituent history, which we
do not have. Disclosed per `GOAL.md` §6.5.

### 6.1 ⚠️ CORRECTION — the bias is ~7.3%/yr, and dividends are missing

An earlier draft of this report left the bias "unquantified". That was too generous.
`research/verify_corporate_actions.py` quantifies it:

| | Annualised |
|---|---|
| Our equal-weight benchmark, **price return only** | 18.58% |
| + estimated NSE-50 dividend yield (~1.15%) | 19.73% |
| **Official NSE TRI, 20y to Feb 2026 (includes dividends)** | **12.44%** |
| **Implied survivorship + selection bias** | **≈ 7.3%/yr** |

Two separate effects compound here:

1. **Survivorship/selection bias.** Backfilling today's constituents means we never held
   the failures.
2. **Dividends are absent from our data entirely.** The panel is price-only. Official
   TRI includes dividends, so comparing our price return to their total return
   *understates* the gap — hence adding ~1.15% back makes the bias larger, not smaller.

**So ~7.3%/yr of our reported numbers is bias, not skill.** Applied to the strategy:

| Figure | As reported | Bias-corrected estimate |
|---|---|---|
| Strategy | 13.40% | **≈ 6.1%** |
| Benchmark | 18.77% | **≈ 11.5%** |

This does **not** change the relative conclusion — the strategy still trails the
benchmark by ~5.4pp/yr — but it means the headline "13.40% beats the official 12.44%
index TRI" comparison was **not valid** and should not be made. Corrected, the strategy
roughly matches the index on return while halving the drawdown. That is a real but far
more modest claim.

Per `GOAL.md` §6.5 this is disclosed in every result.

---

## 7. What worked, what didn't

### Worked
| Change | Effect | Evidence basis |
|--------|--------|----------------|
| **Removed all mean-reversion** | Large | Indian evidence shows short-term *continuation*, not reversal. Romano-Wolf-corrected study: 7/8 survivors were trend rules; RSI/Bollinger failed. |
| **Monthly rebalance + 35% turnover budget** | Moderate | No Indian study supports weekly. SEBI's own loss gradient is monotone in turnover. |
| **Regime overlay (time-series momentum on market proxy)** | **Very large** | MaxDD −40.9% → −15.4%; Sharpe 0.72 → 0.91 (in-sample). Singh & Walia 2020. |
| **Real cost stack from day one** | Discipline | Caught a 2× under-statement of STT and a 2× under-statement of portfolio-level cost drag. |

### Negative control — the harness is not noise-mining
A reversal composite (the factor the evidence says should fail) was run through the
identical harness:

| Composite | CAGR | Sharpe | MaxDD |
|-----------|------|--------|-------|
| Reversal (negative control) | 17.27% | 0.70 | −49.98% |
| Trend + overlay | 17.59% | **0.91** | **−14.92%** |

The control behaves as the evidence predicts (worse risk-adjusted, far worse drawdown).
**PASS** — the harness is discriminating, not curve-fitting.

---

## 8. Bugs found and fixed during this work

Recorded because each one inflated returns and would have been invisible without a check:

1. **STT modelled as sell-only.** Delivery STT is **0.1% on both sides** since Oct 2024.
   Understated costs ~2×.
2. **`round_trip_bps` divided by one-way notional** instead of total turnover. Doubled
   every cost estimate. Now calibrated against two published itemisations and matches
   **11.66 bps exactly** (₹334.67 on ₹2,87,000 turnover).
3. **Portfolio-level costs not scaled by equity.** Cost was charged as a bare fraction
   of turnover rather than of the compounding book — understating the drag ~20×.
4. **Slippage contributed zero to the backtest.** The engine applied weights directly
   and never called `fill_price`, making the Gate 4 stress test vacuous. Added
   `all_in_round_trip_bps`.
5. **`yearly_returns` returned cumulative, not calendar-year, returns** — the first
   yearly table showed +467% "annual" returns.
6. **Regime overlay returned a return series where an exposure multiplier was expected**,
   driving the portfolio to ~100% cash (CAGR collapsed to 2.2%).
7. **2002–2007 data contains 58 unadjusted split artifacts** (24 of them >100% one-day
   moves); 12 symbols affected on the single date 2005-07-28. Restricted to 2008+.

---

## 9. What is required before any capital is deployed

Three gates fail. In order of expected value:

1. **Close the Sharpe gap (0.66 → ≥0.7).** The overlay's whipsaw is the cost.
   Candidate fixes: slower de-risking trigger, partial re-entry ramp instead of binary
   on/off, or volatility-targeted exposure instead of a binary gate. **Must be validated
   walk-forward, not in-sample.**
2. **Be honest about the benchmark.** Either obtain a point-in-time constituent history
   to remove survivorship bias, or stop comparing to a survivor-set benchmark and
   compare to official NSE TRI instead. This may change the sign of the result.
3. **Gate 6 — production readiness.** Live/paper parity, kill-switch tests, broker
   reconciliation. None of this is built yet.

**Current status: research-complete for v1. Capital NOT authorised.**