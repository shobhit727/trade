# Validation Report — v1

**Reproduce:** `.venv/bin/python research/validate.py` (host venv) or
`docker compose -f docker-compose.research.yml run --rm research python research/validate.py`
**Data:** `data/nse/*_1d.csv`, cleaned per `reports/DATA_AUDIT.md` §5
**Window:** 2008-01-01 → 2026-08-25 (18.9y), 48 symbols, 4,602 trading days
**Verdict: 🟡 BAND C — real but modest. NOT 3%/month. NOT YET DEPLOYABLE.**

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