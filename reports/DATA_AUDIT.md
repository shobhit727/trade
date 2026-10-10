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

## 0.1 2026-10-09/10 — data-quality re-audit: the `open` column is corrupt, and 3 more defects

**Reproduce:** `research/data_quality/FINDINGS.md` (full write-up, 281,342 bars across all
50 `*_1d.csv` files, with per-symbol and intraday cross-checks).
**What changed:** four defects were found. Three are now fixed in the loader. One was
**mis-attributed in this report and is corrected below.**

### 0.1.1 ⚠️ CORRECTION — `high` and `low` are sound. The defect is in `open`.

§3 of this report previously carried the claim:

> `high == open` on **6.68%** of bars — every breakout-level strategy reads a column that
> is wrong precisely on the moves it exists to catch.

**That conclusion was wrong, and the wrong half was the dangerous half.** Corrected:

| | Then (§3) | **Now (measured)** |
|---|---|---|
| Pooled `high == open` rate | 6.68% | **10.06%** (8.70% on live, non-dead bars) |
| Which column is corrupt | implied `high` | **`open`** |
| Effect on breakout strategies | claimed impaired | **−0.08% of Donchian events — not impaired** |

**Why `high` is exonerated.** Aggregating the 5m file to daily and comparing against the 1d
files over 1,600 overlapping days:

| Check | Result | Verdict |
|---|---|---|
| daily `low` **above** the true intraday low | **0.00%** | `low` is sound |
| daily `low` == intraday min | 36.31% exact, median gap **0.10 rupees** | `low` is sound |
| daily `high` == intraday max | 32.12% exact, median gap **0.15 rupees** | `high` is sound |
| daily `high >= max(open, close)` | 99.977% | no integrity violation |
| 20-day Donchian events, supplied vs reconstructed `high` | 18,495 vs 18,480 | **delta −15 (−0.08%)**, 1 symbol of 50 |

**Why `open` is convicted.**

| Check over 1,600 overlapping days | Result |
|---|---|
| daily `open` differs from the true first 5m print | **90.81% of days** |
| daily `open` **above the entire intraday range** | **13.06%** |
| daily `open` **below the entire intraday range** | **7.06%** |
| **daily `open` outside the true range, either side** | **20.12%** (322 days) |
| median error | ₹1.400 (0.134% of close) |
| p95 / max error | ₹19.525 (0.596%) / ₹93.00 (2.006%) |

Worked example — `reliance`, 2026-09-25: 5m trades the whole day between **1215.0 and
1227.3**; the daily file reports `open = 1210.5`, **a price that never traded**, then
stretches `low` down to 1210.5 to accommodate it.

**Causal chain, confirmed:** of 208 days where `open > true_high`, **60.58%** show the
`high == open` artifact; of 113 days where `open < true_low`, **52.21%** show
`low == open`. Conversely only **8 of 134** `high == open` bars lack the phantom-open
explanation. **The `high == open` artifact is a downstream symptom of the corrupt `open`,
not a defect in `high`.**

**`close` is clean:** daily close == intraday last close on **97.12%** of days, with
median close-to-close return 1.05%, p99 7.84%, and only 0.0405% of bars exceeding the NSE
20% circuit limit. **The return series — the thing every result here is built on — is
trustworthy.**

**Consequences, stated plainly:**

- **Do NOT exclude the eight breakout strategies** (donchian, atr_breakout, squeeze, nr4,
  price_channel, triangle, rectangle, flag). A sub-0.05% median per-bar perturbation is
  invisible to a 20-day rolling maximum. Excluding them would discard ~0.1% of signal over a
  defect that does not touch them.
- **Do NOT "reconstruct" `high = max(open, close)`.** That repair is backwards — it would
  discard the true intraday high on 90% of bars and manufacture the very artifact it aims
  to fix, while changing nothing measurable (−15 events).
- **`open_range_breakout` is the genuine exposure** and was *not* on the original list. It
  reads `open` directly; its trigger levels are unreliable. Gate it, or any other
  `open`-keyed logic (gap filters, overnight fills), behind a data-quality assertion.
- **Three ingest assertions are now mandatory and none existed:** `open ∈ [low, high]`
  (fires on ~20% of days and would have caught this at ingest), `|return| < 20%`,
  `open > 0`.
- **Do not treat 15m as independent corroboration of 5m.** The 15m file is a bit-exact
  resample of the 5m file — **100.00% exact OHLC match on all four price columns**
  (846/846 buckets). Validating 5m against 15m is validating one source against itself.

### 0.1.2 ✅ FIXED — 4 stray weekend bars (interior data hole)

Four bogus Saturday/Sunday dates sat inside the panel: **2010-02-06 (Sat), 2019-10-27
(Sun), 2020-11-14 (Sat), 2025-02-01 (Sat)**. The NSE does not trade Saturday or Sunday, so
these are vendor artefacts.

**The damage was not the four bars — it was the hole they punched.** The panel is a union
index across symbols, so each weekend date became an **interior NaN in 42 symbols**. Every
rolling and `ewm` indicator is then wrong for `period` bars after the hole. Because the
loader's C6 check only validated *within* each symbol, nothing raised: the NaNs were
between symbols, not inside one.

**Fixed as new cleaning rule C8** — drop any index entry with `dayofweek >= 5`, plus a
belt-and-braces coverage filter. Panel is now **4,625 trading days** (was 4,629).

> **This class of bug is now on the standing checklist:** an *interior* hole in an aligned
> panel is invisible to per-symbol validation. Any new cleaning rule must be checked against
> **panel-level** coverage, not just per-symbol integrity.

### 0.1.3 ⚠️ 114 unadjusted-split bars (surviving cleaning)

**114 bars (0.0405%) show >20% single-bar moves** that are un-applied split/demerger factors
in the **close** series. Example: `bajfinance` 2005-07-27 jumps **2.31 → 252.95 (+469.6%)**
and **reverses the next day** (252.95 → 2.31). Same pattern in `bel`, `bajajfinsv`, `cipla`.

These are spurious *returns* — worse than a price defect, because they enter the return
series directly rather than through a level.

**Covered by C1** (the 2008+ window restriction), since every instance is pre-2008. **Not
additionally excluded by C5**, which fires at >45%; an 114-bar population that includes
moves in the 20–45% band passes C5 and still corrupts momentum features. The `|return| <
20%` assertion recommended in §0.1.1 is what closes that gap.

### 0.1.4 ⚠️ 47 negative-price bars (all `adanient`)

**47 bars, all in `adanient`, all in 2002-07**, with values around **−0.0122 and real
volume**. This is broken back-adjustment. Any log-return or percentage calculation on that
window returns `NaN`/`inf`.

**Covered by C3** (exclude `adanient`). Already counted in §3 and §0 above; recorded here
because a dedicated re-audit found it independently and confirmed the count.

### 0.1.5 Summary — what the re-audit changed

| # | Finding | Status | Rule |
|---|---|---|---|
| 1 | `open` corrupt (90.81% of days wrong; 20.12% outside the true range) | **Open** — no repair possible from OHLCV alone; needs a Kite/session feed | `open`-keyed logic must be gated |
| 2 | `high == open` rate understated (6.68% → 10.06%) | Corrected above | — |
| 3 | 8 breakout strategies wrongly implicated | **Retracted** | — |
| 4 | 4 stray weekend bars → interior NaN in 42 symbols | ✅ **Fixed** | **C8** |
| 5 | 114 unadjusted-split bars | Covered (pre-2008); `\|return\| < 20%` assertion recommended | C1 |
| 6 | 47 negative-price bars (`adanient`) | Covered | C3 |
| 7 | 15m is a resample of 5m, not independent | **Disclosure added** | — |

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

> ⚠️ **This verdict was later partly overturned. Read §0.1 before relying on it.**
> A dedicated re-audit on 2026-10-09 found that **structural consistency is not the same as
> correctness**: the daily `open` column is corrupt on **90.81%** of days and sits outside
> the true intraday range on **20.12%** of them, while passing every check in this table —
> because a file can be internally consistent and still be wrong. The `close` and
> `high`/`low` columns **survive** cross-checks against intraday data; `open` does not.

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
| **C8** | **Drop every index entry with `dayofweek >= 5`, plus any date with panel coverage < 5%** | Added 2026-10-10 after §0.1.2. Four stray weekend dates each punched an **interior NaN into 42 symbols**, corrupting every rolling/ewm indicator for `period` bars — invisibly, because C6 validated *within* each symbol. **Validate the panel, not just the symbols.** |
| **C9** | *Recommended, not yet implemented:* assert `open ∈ [low, high]`, `\|return\| < 20%`, `open > 0` at ingest | §0.1.1 / §0.1.3. The first would have caught the corrupt `open` (fires ~20% of days); the second closes the 20–45% gap C5 misses; the third catches the `adanient` rows. **All three currently pass silently.** |

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
  the current numbers. Bias-corrected, the strategy is **≈3.6%/yr (provisional — the
  derivation does not currently reconcile, see `reports/VALIDATION_v1.md` §0.7) on the
  current window, not the 9.71% headline.**
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
| Can we backtest daily NIFTY-50 strategies? | ✅ **Yes**, 2008-01-01 → 2026-10-01, 19.0y, **4,625** days, 48 symbols |
| Is the daily `close` series trustworthy? | ✅ **Yes** — 97.12% exact match against intraday aggregation; return distribution respects the NSE circuit limit |
| Is `high`/`low` trustworthy for breakout strategies? | ✅ **Yes** — Donchian impact is −0.08%. **The earlier claim that they were broken is retracted** (§0.1.1) |
| Is the daily `open` column trustworthy? | ❌ **No** — wrong on 90.81% of days, outside the true range on 20.12%. `open`-keyed logic must be gated (§0.1.1) |
| Is the recovered panel trustworthy? | ✅ **Yes** — 49/50 verified vs the audit; truncation to 2026-08-25 reproduces the v1 result (§0) |
| Can we backtest intraday? | ❌ **No.** 6 days of 1m. Banned. Not re-fetched. |
| Can we claim the result is bias-free? | ❌ **No.** ~7.3%/yr quantified — survivorship plus dividends absent entirely |
| Can we go live today? | ❌ **No.** Fresh-data path is still a one-off script; Gate 6 unbuilt. |

**Bottom line:** this dataset supports a genuine, honest, cost-aware **daily-bar swing**
research programme over ~19 years, built on a **`close` series that is trustworthy** and a
**`high`/`low` pair that survives cross-checks against intraday data**. It does **not**
support intraday work, it does **not** support bias-free claims, and it does **not** support
any logic keyed to the `open` column. Build accordingly.

**Two warnings that belong in a data audit:**

1. **Extending this panel by 27 sessions moved the walk-forward Sharpe from 0.66 to 0.44 and
   the band from C to D.** The data did its job. The lesson is that the *strategy* result was
   fragile at the sample boundary, and every figure produced from this panel must be
   published with its end date attached.

2. **The most important defect this audit ever found was invisible to the audit that was
   supposed to find it.** Four weekend bars, each punching an interior NaN into 42 symbols,
   corrupted every rolling indicator downstream and passed every existing check, because
   the existing checks looked *within* each symbol and the hole was *between* them. The
   `open`-column defect was likewise found by cross-checking against an **independent
   source** (intraday bars), not by inspecting the daily file for internal consistency.
   **Corollary for any future data work: a dataset validated only against itself will
   happily confirm its own defects.** The same corollary explains why the backtest engine's
   bugs survived the validation pipeline — see `reports/VALIDATION_v1.md` §0.3.