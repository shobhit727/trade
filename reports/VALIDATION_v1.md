# Validation Report — v1 · ⚠️ SUPERSEDED BY THE ADDENDUM BELOW

> # ⚠️ READ THE ADDENDUM IN §0 FIRST
>
> **The result in this file is the ORIGINAL v1 measurement, taken on data ending
> 2026-08-25. It is no longer the current result and it must not be quoted.**
>
> Re-measured on 2026-10-06 with the panel 27 trading days longer and two engine bugs
> fixed, the walk-forward result is **10.97% annualised / Sharpe 0.44 / max drawdown
> −12.91% — Band D, four gates failing** (was 13.40% / 0.66 / −15.41% / Band C / three
> gates failing).
>
> **Everything below the addendum is retained unchanged as the historical record of the
> original measurement.** Where it conflicts with §0, §0 wins. Nothing has been edited to
> make the old numbers look better or worse than they were.
>
> The single most important finding is in §0.2: **27 trading days moved Sharpe from 0.66
> to 0.44 and the band from C to D.** Same code, same costs, same parameters. That is a
> fragility signal about the strategy, not a data defect.

---

# §0 — ADDENDUM v2 (2026-10-06): the current result

**Reproduce:** `.venv/bin/python research/validate.py`
**Data:** `data/nse/*_1d.csv`, re-fetched 2026-10-06 (`tools/recover_nse_data.py`),
cleaned per `reports/DATA_AUDIT.md` §5
**Window:** 2008-01-01 → 2026-10-01 (19.0y), 48 symbols, 4,629 trading days
**Verdict: 🔴 BAND D. FOUR GATES FAIL. NOT 3%/month. NOT DEPLOYABLE.**

## 0.1 Revised headline

| Metric | v1 (to 2026-08-25) | +27 days, pre-fix engine | **v2 — CURRENT (authoritative)** | Target | |
|--------|-------------------|------------------------|----------------------------------|--------|---|
| OOS annualised | 13.40% | 11.05% | **10.97%** | 42.6% | ❌ 3.9× short |
| **OOS monthly equivalent** | **+1.054%** | +0.877% | **+0.871%** | 3.000% | ❌ |
| OOS Sharpe | 0.66 | 0.45 | **0.44** | ≥ 0.7 | ❌ |
| OOS Max Drawdown | −15.41% | −12.90% | **−12.91%** | < 35% | ✅ |
| OOS Calmar | 0.87 | 0.86 | **0.85** | — | ✅ |
| OOS positive years | 12/13 (92%) | 11/13 (85%) | **11/13 (85%)** | ≥ 60% | ✅ |
| OOS Sortino | 0.77 | — | **0.52** | — | |
| All-in cost drag | 3.03%/yr | — | **3.11%/yr** | — | measured |
| **Band (`GOAL.md` §2.3)** | **C** | D | **D** | C or better | ❌ |

The **v2 column is the only valid result.** The middle column isolates the effect of the
data extension on the then-current code; it is quoted because the gap between the middle and
v2 columns is the engine fix, and because it was briefly the published headline before those
bugs were found. It is not a result of the code as it now stands.

**The 0.08pp of CAGR and 0.01 of Sharpe that the engine fix cost is immaterial. The 2.43pp
of CAGR and 0.22 of Sharpe that the 27 days cost is not.**

## 0.2 ⚠️ THE FRAGILITY FINDING — 27 trading days moved the band

**This is the headline of this addendum and it is about the strategy, not the data.**

| | End date | Extra sessions | OOS CAGR | Sharpe | Band |
|---|---|---|---|---|---|
| v1 | 2026-08-25 | — | 13.40% | 0.66 | **C** |
| v2 | 2026-10-01 | **+27** | 10.97% | 0.44 | **D** |

Between those two measurements **nothing about the strategy changed**: same code, same
Indian cost stack, same parameters, same six-fold sliding-origin walk-forward design. The
only variable was the data end date.

**Twenty-seven sessions — about six weeks — removed a third of the measured risk-adjusted
return and dropped the system out of the band it was previously judged against.**

What happened in those 27 sessions (2026-08-26 → 2026-10-01), measured:

| Over the 27-session window | Return |
|---|---|
| Equal-weight market proxy | **−7.7%** |
| Strategy (OOS series) | **−6.9%** |

The strategy **lost money**, but it lost roughly what the market lost and marginally less —
this is not an alpha failure in the window, and the portfolio construction held up. The
damage is entirely to the *statistics*: the window is a sustained drawdown for both, and
27 down-days are enough to pull a 19-year Sharpe down by 0.22.

**The finding that matters is not "the last six weeks were bad". It is that the v1 band was
one noisy draw away from being wrong.** A result that changes band when the end date moves
by six weeks is not a measurement of the strategy's edge; it is a measurement of where the
end date happened to fall. Until this system demonstrates that its band is *stable* as the
window is extended, no number from it is a forward expectation, and §4's Band C reading
must be treated as withdrawn rather than merely missed.

**Standing rule adopted from this:** every figure reported by this project must carry its
end date. A CAGR without a window is not a measurement.

## 0.3 ⚠️ Two engine bugs — the earlier numbers were partly earned by breaching our own limits

Found by the sanity checks in `research/benchmark_catalog.py` (§0.4), fixed in
`src/nsealgo/backtest/engine.py` (**on disk, uncommitted**):

| # | Bug | Measured symptom | §3.2 limit |
|---|---|---|---|
| 1 | The sector cap redistributed weight **without re-capping** the names it spilled onto, so the single-name cap was applied first and then invalidated | **worst single weight 25.66%** | 12% |
| 2 | **Dead residual weights accumulated** — positions that fell below the material threshold were never dropped | **48 names held** | `max_positions` 30 |

After the fix, measured over the full window:

| Constraint | Worst observed | Limit | |
|---|---|---|---|
| Single-name weight | **10.80%** | 12% | ✅ |
| Sector weight | **22.50%** | 25% | ✅ |
| Names held | **30** | 30 | ✅ |
| Gross exposure | 90.00% | 90% (10% cash buffer) | ✅ |

Cost of the fix: OOS **11.05% → 10.97%** CAGR, Sharpe **0.45 → 0.44**.

**This must be said plainly: part of the v1 result was not obtainable under the portfolio
rules `GOAL.md` §3.2 mandates.** A backtest holding 25% in a single name is not the
strategy this constitution describes, whatever it prints. Any return produced by breaching a
limit is an artifact of the harness, not a return of the strategy, and it is recorded here
as one. The post-fix figures are the ones to trust.

## 0.4 Catalog benchmark — nothing already in this repo beats the composite

`research/benchmark_catalog.py`. The ~85 existing crypto strategies in
`src/cryptobot/strategies/catalog/` were ported to NSE daily bars through a
`SignalStrategy` adapter and run through **the same engine, the same Indian cost stack,
the same constraints and the same metrics** as the composite, on 226 monthly rebalance
dates.

| | Count | CAGR | Sharpe | MaxDD | Calmar |
|---|---|---|---|---|---|
| **nsealgo composite** (with regime overlay) | — | **17.57%** | **0.88** | −18.51% | **0.95** |
| Best catalog strategy (`cumulative_delta_strategy`) | **80 evaluated** | 15.92% | 0.76 | −17.43% | 0.91 |
| Pure 6-month momentum, same harness | — | 16.73% | 0.80 | −20.17% | 0.83 |
| **Random 50/50 mask**, same harness | — | 15.22% | **0.77** | −17.70% | 0.86 |

Coverage: 84 discovered, 80 evaluated, 2 never signalled (`nse_intraday_trading`,
`support_strategy`), 2 crypto-only skipped (funding basis, liquidation hunt), 0 errors.
**No catalog strategy beats the composite** on Sharpe or Calmar. (The same sweep run before
the §0.3 engine fix read best-catalog Sharpe 0.81 and Calmar 0.89 — same verdict.)

**Two caveats that change what this comparison means:**

1. **This is a full-window in-sample comparison, not walk-forward.** The composite baseline
   here carries the regime overlay (Sharpe 0.88). It is **not** comparable to the 0.44 OOS
   figure in §0.1 and is not meant to be.
2. **The comparison mostly measures momentum, not strategy skill.** The adapter
   deliberately gives each catalog strategy the benefit of momentum ranking (rank the
   signalled names by trailing 126-day return). Under that construction the top of the sweep
   is not a set of distinct strategies: the leading rows produce **byte-identical books**
   (return correlation 1.000) — e.g. `on_balance_volume`, `adx_trend`, `gap_strategy`,
   `liquidation_hunt_strategy`, `supertrend_strategy` and `volatility_scaling` all print
   15.16% / 0.73 / −18.06% / 0.84.

**The honest finding: no existing catalog strategy adds anything over momentum, and none
beats the composite.** The best catalog result (Sharpe 0.76) is *below* pure 6-month
momentum (0.80) and within noise of a **random 50/50 mask** (0.77) given the same momentum
ranking. The composite's entire margin over the whole existing catalog is **0.12 Sharpe** —
of the same order as the 0.22 that 27 days of new data destroyed.

## 0.5 Gate re-check (`GOAL.md` §5)

| Gate | Requirement | v1 | **v2** | |
|------|-------------|----|--------|---|
| G3 | OOS CAGR ≥ 12% | 13.40% ✅ | **10.97%** | ❌ |
| G3 | OOS Sharpe ≥ 0.7 | 0.66 ❌ | **0.44** | ❌ |
| G3 | OOS MaxDD < 35% | −15.41% ✅ | **−12.91%** | ✅ |
| G3 | Positive years ≥ 60% | 92% ✅ | **85%** | ✅ |
| G4 | Beat benchmark CAGR | −5.36% ❌ | **10.97% vs 16.96%** | ❌ |
| G4 | Beat benchmark Sharpe | −0.11 ❌ | **0.44 vs 0.67** | ❌ |

**Three gates failed at v1. Four fail now**, and the band has fallen from C to D — which
also fails Gate 3's "Band C or better" line.

**Default verdict per `GOAL.md` §5: NO DEPLOY.** The system is research-complete for v2 and
not capital-ready. Nothing about §5 has been changed to accommodate the result.

### 0.5.1 vs benchmark, current windows

Benchmark is **equal-weight buy & hold of the same 48 symbols**, over identical test windows.

| | CAGR | Sharpe | Sortino | MaxDD | Calmar |
|---|---|---|---|---|---|
| **OOS strategy (v2)** | **10.97%** | 0.44 | 0.52 | **−12.91%** | **0.85** |
| **OOS benchmark (v2)** | **16.96%** | 0.67 | 0.81 | −37.97% | 0.45 |
| **Difference** | **−6.00pp** | −0.23 | −0.29 | **+25.06pp** | **+0.40** |

Still the same shape as v1 and now worse in degree: **6.00pp/yr behind** buy-and-hold (was
5.36pp), in exchange for a drawdown **66% shallower** (−12.9% vs −38.0%).

### 0.5.2 OOS yearly returns (v2)

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

**11 of 13 calendar years positive (85%)**, down from 12/13. The overlay pattern from §3.1
of the original report holds: it wins in flat and down years and gives back heavily in
sharp recoveries (2020 −26.10pp, 2021 −22.59pp). 2018 has flipped negative and **2026 is
negative — the partial year that produced the fragility finding.**

## 0.6 Walk-forward folds (v2)

6 folds, sliding origin, 6y train / 2y test, parameters selected on **train only**.

| Fold | Train | Test | OOS CAGR | Sharpe | MaxDD | Selected params |
|------|-------|------|---------|--------|-------|-----------------|
| 1 | 2018-11-14 → 2024-10-18 | 2024-10-21 → 2026-10-01 | **−1.55%** | **−1.05** | −10.48% | n=22, lb=126, thr=0.00 |
| 2 | 2016-11-25 → 2022-10-25 | 2022-10-27 → 2024-10-18 | 30.23% | 1.78 | −7.53% | n=22, lb=126, thr=0.60 |
| 3 | 2014-12-01 → 2020-11-05 | 2020-11-06 → 2022-10-25 | 13.76% | 0.59 | −12.56% | n=22, lb=126, thr=0.60 |
| 4 | 2012-12-05 → 2018-11-13 | 2018-11-14 → 2020-11-05 | 6.86% | 0.08 | −9.47% | n=15, lb=126, thr=0.00 |
| 5 | 2010-12-10 → 2016-11-24 | 2016-11-25 → 2018-11-13 | 14.71% | 0.82 | −12.46% | n=15, lb=126, thr=0.60 |
| 6 | 2008-12-18 → 2014-11-28 | 2014-12-01 → 2016-11-24 | 4.44% | −0.12 | −12.91% | n=15, lb=126, thr=0.60 |
| **All** | | **2014-12 → 2026-10** | **10.97%** | **0.44** | **−12.91%** | |

**The most recent fold is the first negative one this system has produced: −1.55% CAGR,
Sharpe −1.05.** It is also the fold the 27 new sessions landed in, and it is the reason the
OOS aggregate fell. One fold is not a trend — but it is the fold that is still in progress,
and it is the fold the strategy must now be judged on.

Fold dispersion is now −1.55% → 30.23%. That was always wide (§2 of the original report);
it is wider now, and it is another reason to hold the headline number loosely.

## 0.7 The data, and proof the recovery is faithful

`data/nse/` was accidentally deleted locally and re-fetched on **2026-10-06** with
`tools/recover_nse_data.py` (yfinance, retries both `auto_adjust` modes with backoff,
atomic writes, verification against the committed audit summary).

| Check | Result |
|---|---|
| Symbols fetched | 50 / 50 files present, all ending 2026-10-01 |
| Verified vs `research/_audit_1d.csv` | **49 / 50** |
| Duplicate timestamps | 0 |
| Non-positive prices | 47 rows, `adanient` only (excluded by rule C3) |
| One-day moves > 45% in the full sample | 0 |
| **Truncation test: re-run to 2026-08-25** | **13.37% CAGR / Sharpe 0.65 / −15.38% / Calmar 0.87 / 12 of 13 years positive** |
| …vs the v1 record | 13.40% / 0.66 / −15.41% / 0.87 / 12 of 13 |

**The truncation test is the proof.** The same parameters were selected in every fold as in
the v1 table below, the result lands within 0.03pp of CAGR and 0.01 of Sharpe, and the
residual is explained by the §0.3 engine fix plus fold-boundary alignment. **The recovered
panel is the same panel; it is simply 27 sessions longer.** Nothing about the data recovery
improved or damaged the result — it only extended the measurement window, and that extension
is what cost 0.22 of Sharpe.

**Bias is unchanged and still applies in full.** ~7.3%/yr (survivorship + dividends
absent — the panel is price-return only). Measured on the v1 window and carried forward
unchanged, because it is a property of the universe construction rather than the end date:

| Figure | Reported | Bias-corrected |
|---|---|---|
| Strategy (v1) | 13.40% | ≈ 6.1% |
| **Strategy (v2)** | **10.97%** | **≈ 3.7%** *(same ~7.3pp bias discount carried forward)* |
| Benchmark (v2) | 16.96% | ≈ 9.7% |

**The claim "beats the official NSE index TRI" was never valid** — §6.1 of the original
report below already established that, and reduced it to "roughly matches the index while
halving the drawdown". At v2 that has degraded further: bias-corrected, the strategy is
**below** the index on return. Halving the drawdown (−12.9% vs −38.0%) is the only claim
that survives.

## 0.8 What is required before any capital is deployed

Four gates fail, and one of them is new. In order of expected value:

1. **Prove the band is stable, not window-dependent.** §0.2 is now the binding problem, and
   it is a research problem, not a parameter-tuning one: the strategy needs an edge that does
   not depend on where the sample ends. Candidate directions — an exposure rule that scales
   with realised volatility rather than switching on a trend threshold, and an explicit
   evaluation of the Sharpe estimate's confidence interval at 19y. **Until a re-measurement
   over a longer window reproduces the band, no other fix counts.**
2. **Restore the return.** 10.97% is below the 12% floor and 6.00pp/yr behind the
   benchmark. Note that the best existing catalog strategy scored *below pure momentum*, so
   the search space is not where the answer is.
3. **Make the fresh-data path automatic.** The panel was restored by a one-off recovery
   script. Gate 6 requires a repeatable Kite historical feed, and until that exists the
   measurement window will keep being set by hand — which is precisely the failure mode §0.2
   exposed.
4. **Gate 6 — production readiness.** Live/paper parity, kill-switch tests, broker
   reconciliation. None of this is built yet.
5. **Land the §0.3 engine fix.** It is on disk and uncommitted; the reported numbers depend
   on it.

**Current status: research-complete for v2. Capital NOT authorised.**

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