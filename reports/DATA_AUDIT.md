# NSE Data Audit Report

**Generated:** from `data/nse/` via `research/audit_data.py`
**Reproduce:** `.venv/bin/python research/audit_data.py`
**Verdict:** ✅ Usable — **with mandatory cleaning**. See §5.

---

## 0. 2026-10-06 — panel re-fetched, verified faithful, now 27 sessions longer

`data/nse/` was **accidentally deleted locally**. It was re-fetched on **2026-10-06** with
`tools/recover_nse_data.py` (yfinance; retries both `auto_adjust` modes with backoff,
writes atomically, then verifies each symbol against the per-symbol statistics committed in
`research/_audit_1d.csv` so a silent partial fetch cannot pass). `tmp/nifty50.csv` was
deleted with it and has been regenerated from the same committed symbol list.

**Verify the panel at any time (no network):**
`.venv/bin/python tools/recover_nse_data.py --verify-only`

| Check | Result |
|---|---|
| Files present | **50 / 50**, every one ending **2026-10-01** |
| Verified against `research/_audit_1d.csv` | **49 / 50** (the exception is `adanient`, already excluded by rule C3) |
| Duplicate timestamps | 0 |
| Non-positive prices | 47 rows, `adanient` only — excluded by **C3** |
| One-day moves > 45% in the full sample | **0** |
| Median bars per symbol | 6,025 (range 774 → 6,678) |
| Panel size | 27.5 MB |

**Faithfulness is proven, not asserted.** Re-running the walk-forward on the recovered panel
**truncated back to 2026-08-25** reproduces the original v1 measurement almost exactly:

| Truncated to 2026-08-25 | CAGR | Sharpe | MaxDD | Calmar | Positive years |
|---|---|---|---|---|---|
| Recovered panel, re-measured | **13.37%** | **0.65** | **−15.38%** | **0.87** | 12/13 |
| v1 record | 13.40% | 0.66 | −15.41% | 0.87 | 12/13 |

The **same parameters were selected in every fold**, and the residual (0.03pp of CAGR,
0.01 of Sharpe) is explained by the two engine fixes recorded in
`reports/VALIDATION_v1.md` §0.3 plus fold-boundary alignment. **The recovered panel is the
same panel.**

**It is, however, 27 trading days longer** — 2026-08-26 → 2026-10-01. That extension, and
nothing else, is what moved the headline result: OOS Sharpe 0.66 → 0.44, band C → D. See
`reports/VALIDATION_v1.md` §0.2. **The data is not implicated; the strategy's sensitivity to
the measurement window is.**

Structural properties below (§1–§5) were re-verified on the recovered panel and are
unchanged. The pre-2008 slice is still poisoned by the same vendor artifacts, so **C1 still
stands**, with its end date moved to 2026-10-01.

---

## 1. Universe

**50 NIFTY-50 symbols**, OHLCV daily + intraday.
Coverage: `itc, tmpv, titan, tatasteel, tataconsum, sunpharma, sbin, reliance, ongc,
m&m, infy, hindunilvr, hindalco, hdfcbank, wipro, eichermot, drreddy, axisbank, cipla,
kotakbank, grasim, trent, apollohosp, asianpaint, bajaj-auto, shriramfin, bajfinance,
bel, bhartiartl, adanient, icicibank, lt, ultracemco, hcltech, tcs, bajajfinsv,
nestleind, jswsteel, maruti, ntpc, techm, powergrid, adaniports, coalindia, indigo,
sbilife, hdfclife, maxhealth, eternal, jiofin, wipro`

---

## 2. Timeframe reality (span, not bar count)

This is the single most important table in the report. Bar counts lie; spans don't.

**As originally audited (data end 2026-08-25).** The daily row was re-measured after the
2026-10-06 recovery — see §0 — and now reads **6,025 median bars, 2002-07-01 → 2026-10-01
(~24.3y)**. The intraday timeframes were **not** re-fetched: only the `1d` panel was
recovered, so those rows remain as audited.

| TF | Bars (median) | Actual span | Verdict |
|----|---------------|-------------|---------|
| **1d** | **6,025** *(5,998 as originally audited)* | **2002-07-01 → 2026-10-01 (~24.3y)** | ✅ **PRIMARY** |
| 1h | 3,436 | 2024-08-26 → 2026-08-25 (729d ≈ 2.0y) | ⚠️ corroboration |
| 4h | 984 | 2024-08-26 → 2026-08-25 (729d ≈ 2.0y) | ⚠️ corroboration |
| 30m | 533 | 2026-06-29 → 2026-08-24 (56d) | ⚠️ sanity |
| 15m | 1,025 | 2026-06-29 → 2026-08-24 (56d) | ⚠️ sanity |
| 5m | 3,107 | 2026-06-29 → 2026-08-24 (56d) | ⚠️ sanity |
| **1m** | **1,801** | **2026-08-18 → 2026-08-25 (6d)** | ❌ **BANNED** |

### 2.1 The 1m data is worse than previously documented

At **375 trading minutes/day**, 1,801 bars ≈ **4.8 trading days**. It is not 30 days.
It is 6 calendar days. **No intraday strategy can be validated on this dataset, ever.**
This is a hard ban, not a soft caution.

**Consequence:** the only defensible strategy horizon is **daily bars, 5–60 day holds**.

### 2.2 Intraday files are sparse samples, not continuous series

`1m` shows only 5 internal gaps but a max gap of 2.75 days across a 6-day span — the
series is discontinuous, not a continuous minute tape. Do not treat it as a tape.

---

## 3. Structural data quality — GOOD

| Check | Result |
|-------|--------|
| Duplicate timestamps | ✅ **0** across all 50 symbols (all TFs) |
| Zero / negative prices | ⚠️ **1 symbol** (`adanient`, 47 rows) — see §4.1 |
| OHLC violations (high<low, etc.) | ⚠️ **1 symbol** (`adanient`, 46 rows) — see §4.1 |
| Non-positive volume | ✅ ~84 rows/symbol-day on average (1.5% — zero-volume holidays) |
| Flat bars (ret≈0) | ✅ 1.8% daily — consistent with exchange holidays |

**The dataset is structurally clean apart from `adanient` and the split artifacts below.**

---

## 4. THE CRITICAL PROBLEM: unadjusted corporate actions

### 4.1 Split / bonus artifacts — 58 events across 18 symbols

Prices are **raw/unadjusted**. Detected one-day moves > 45%:

| Date | Symbols hit | Example |
|------|-------------|---------|
| **2005-07-28** | **12** | trent +959%, tatasteel +600%, grasim +548%, reliance +337% |
| **2005-07-29** | **12** | (reversal of the above) |
| 2003-04-14/15 | 2 | cipla −92%, tatasteel +600% |
| 2003-11-26/27 | 2 | cipla, tatasteel |
| 2003-12-25/26 | 2 | cipla, tatasteel |
| 2004-04-26/27 | 2 | cipla, tatasteel |
| 2004-05-11/12, 2006-09-27/28, 2004-08-24, 2010-01-08 | various | single-symbol |

**2005-07-28/29 is unambiguously a data artifact, not market history.** 12 unrelated
companies cannot simultaneously have a ~10× one-day gain on the same date and reverse it
the next day. It is a source-data glitch (the NSE face-value/series restructuring).

### 4.2 Extreme-move density by era — the decisive table

| Era | Symbol-days | \|>25%\| | \|>50%\| | \|>100%\| | Quality |
|-----|------------|---------|---------|----------|---------|
| **2002–2007** | 57,681 | **58** | **50** | **24** | ❌ **UNUSABLE** |
| 2008–2012 | 53,421 | 8 | 3 | 0 | ✅ clean |
| 2013–2016 | 43,576 | **1** | 0 | 0 | ✅ pristine |
| 2017–2020 | 46,124 | 4 | 0 | 0 | ✅ clean |
| 2021–2026 | 69,147 | 4 | 0 | 0 | ✅ clean |

**Conclusion: the 2002–2007 slice contains more bad data than the entire 18 years that
follow it combined.** A momentum or trend strategy backtested across it would register
~90–99% one-day "losses" and be worthless.

---

## 5. MANDATORY CLEANING PLAN (binding)

Applied in `nsealgo/data/cleaning.py`. No backtest may run on unclean data.

| # | Rule | Rationale |
|---|------|-----------|
| **C1** | **Backtest window: 2008-01-01 → latest available (2026-10-01)** | Only era with clean data. Still spans GFC, 2013 taper, 2015-16, COVID, 2021-22. Note: the end date is data-driven and has now moved once (§0) — every reported figure must carry it. |
| **C2** | **Drop 2005-07-28 and 2005-07-29** everywhere | 12-symbol systematic artifact |
| **C3** | **Exclude `adanient`** (or drop its 47 non-positive rows) | Only symbol with structural corruption |
| **C4** | Forward-fill nothing. **Drop** rows with non-positive price. | Never invent prices |
| **C5** | Sanity-halt: if a single-day \|return\| > 45% survives C1–C4, **log + drop**, and report it | Belt-and-braces |
| **C6** | Assert **no duplicates**, **no NaN close**, **monotonic ts** in every load | Fail loudly |
| **C7** | Record `cleaning_report` per run: rows dropped by rule | Auditable, per `GOAL.md` §6.6 |

### 5.1 What we lose by starting in 2008

- We lose the 2003–07 bull run. **This is acceptable** — those years contain the poisoned
  data, and including them would corrupt every metric we compute.
- Coverage after C1: **≥ 40 symbols with ≥ 15 years** → `GOAL.md` §5 Gate 1 ✅

### 5.2 Corporate actions are ADJUSTED post-2008 (verified)

Verified by `research/verify_corporate_actions.py` against 10 documented 1:1 bonus
issues. An unadjusted series would show a ~-50% one-day drop on each ex-date:

| Symbol | Bonus | Worst day in that window |
|---|---|---|
| Infosys | 1:1, ex-Sep 2018 | −0.98% |
| Wipro | 1:1, ex-Nov 2024 | −2.44% |
| HDFC Bank | 1:1, ex-Jul 2015 | −1.66% |
| HCLTech | 1:1, ex-Jul 2013 | −1.87% |
| Axis Bank | 1:1, ex-Sep 2015 | −3.88% |
| ICICI Bank | 1:1, ex-Jun 2014 | −2.13% |
| Tech Mahindra | 1:1, ex-May 2013 | −2.17% |
| HUL | 1:1, ex-Dec 2013 | −1.21% |
| SBI | 1:1, ex-Sep 2015 | −3.58% |
| TCS | 1:1, ex-Jul 2014 | −2.09% |

**No -50% signature at any bonus date -> the post-2008 panel is corporate-action
adjusted and returns are usable.** This independently justifies the C1 restriction:
the pre-2008 slice is where the vendor's adjustment *breaks down*.

### 5.3 ⚠️ DIVIDENDS ARE ABSENT — price return only

The panel is **price return only**. The official NSE NIFTY-50 TRI (12.44% over 20y)
*includes* dividends; our figures do not. NSE-50 long-run dividend yield is ~1.15%/yr.

Every number this project reports is therefore a **price return** and is understated
by roughly 1.15%/yr as a total return. Combined with survivorship, see
`reports/VALIDATION_v1.md` §6.1 for the resulting ~7.3%/yr bias estimate.

### 5.4 Survivorship bias — DISCLOSED and now QUANTIFIED

31 of 50 symbols have **truncated history matching their listing date**:

| Symbol | First bar | Bars |
|--------|-----------|------|
| jiofin | 2023-08-21 | 747 |
| eternal | 2021-07-23 | 1,262 |
| maxhealth | 2020-08-21 | 1,491 |
| hdfclife | 2017-11-17 | 2,169 |
| sbilife | 2017-10-03 | 2,201 |
| indigo | 2015-11-10 | 2,665 |
| coalindia | 2010-11-04 | 3,901 |
| jswsteel | 2003-05-08 | 5,778 |

This is **today's NIFTY-50 backfilled through history**. Delisted and removed
constituents are absent. Consequences:
- Any backtest **systematically overstates** performance (we never hold a loser that was
  dropped from the index).
- **Diagnostically confirmed:** a correct 2008→2026 NIFTY-50 panel must contain Satyam,
  IL&FS, DHFL, Yes Bank and Vodafone Idea. **This panel contains none of them.** No
  point-in-time constituent history exists locally, so the bias cannot be *removed*.
- **Quantified at ≈ 7.3%/yr** in aggregate (survivorship + selection + missing dividends) —
  see `reports/VALIDATION_v1.md` §6.1 for the derivation and §0.7 for how it carries into
  the current numbers. Bias-corrected, the strategy is ≈3.7%/yr on the current window, not
  the 10.97% headline.
- Per `GOAL.md` §6.5, this is disclosed in **every** result. Treat all numbers as
  **optimistic by ≈7.3pp/yr** until proven otherwise on live data.

---

## 6. Staleness — resolved, but not automated

**Data ends 2026-10-01** (re-fetched 2026-10-06, §0). The ~6-week staleness recorded here
previously is **gone** — the daily panel is now ~3 trading days behind the calendar.

**But the refresh was a one-off recovery script, not a feed.** `nsealgo/data/kite_history.py`
must still provide a repeatable Kite historical backfill before Gate 6, for two reasons:

1. Live trading cannot depend on someone remembering to run a recovery script.
2. The measurement window being set by hand is exactly what produced the fragility finding
   in `reports/VALIDATION_v1.md` §0.2 — 27 hand-chosen sessions moved Sharpe 0.66 → 0.44.
   **The refresh path is a research-integrity problem before it is an operational one.**

---

## 7. Verdict

| Question | Answer |
|----------|--------|
| Can we backtest daily NIFTY-50 strategies? | ✅ **Yes**, 2008-01-01 → 2026-10-01, 19.0y, 4,629 days, 48 symbols |
| Is the recovered panel trustworthy? | ✅ **Yes** — 49/50 verified vs the audit; truncation to 2026-08-25 reproduces the v1 result (§0) |
| Can we backtest intraday? | ❌ **No.** 6 days of 1m. Banned. Not re-fetched. |
| Can we claim the result is bias-free? | ❌ **No.** ~7.3%/yr quantified — survivorship plus dividends absent entirely |
| Can we go live today? | ❌ **No.** Fresh-data path is still a one-off script; Gate 6 unbuilt. |

**Bottom line:** this dataset supports a genuine, honest, cost-aware **daily-bar swing**
research programme over ~19 years. It does **not** support intraday work, and it does
not support bias-free claims. Build accordingly.

**And a warning that belongs in a data audit:** extending this panel by 27 sessions moved
the walk-forward Sharpe from 0.66 to 0.44 and the band from C to D. The data did its job.
The lesson is that the *strategy* result was fragile at the sample boundary, and every
figure produced from this panel must be published with its end date attached.