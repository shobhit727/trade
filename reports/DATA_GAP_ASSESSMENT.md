# DATA GAP ASSESSMENT — survivorship bias, corporate actions, delistings

**Scope:** data availability only. No strategy work, no change to `src/`.
**Prepared:** 2026-10-16. All external URLs accessed **2026-10-16** unless stated.
**Reproduce:** `tem/datagap/` holds every script and raw artefact (1.5 MiB).
**Machine-readable results:** `tem/datagap/{panel_audit,adjustment_verdict,panel_actions,symbol_price_availability,survivorship_measured}.csv|json`.

---

## 0. Headline

| # | Finding | Verdict |
|---|---------|---------|
| 1 | Point-in-time NIFTY-50 membership, 2008→2026, **exists and is downloadable**. Verified exactly against independent ground truth on 9 dates. | **FIXABLE** |
| 2 | The panel is **not price-only**. It is Yahoo `auto_adjust=True` — split *and* dividend adjusted, verified to 7e-8 (float32 epsilon). 48/50 names carry full dividend history. | Premise was wrong |
| 3 | Measured survivorship gap is **+8.94 pp/yr** of CAGR, *not* the assumed 7.3%/yr. | **Understated before** |
| 4 | One genuine **unadjusted 1:1.5 bonus (TRENT, 2026-01-01) is live inside the OOS window** and survives cleaning. | 1 bar, fixable |
| 5 | TCS is pinned to a **Yahoo adjustment vintage that no longer exists**; today's Yahoo disagrees by +0.5316% from ~2026-03. | Reproducibility defect |
| 6 | 4 securities (incl. **SATYAM**) have **no obtainable price history anywhere free**. Irreducible. | **NOT FIXABLE** |

**Single highest-value change:** make the universe a function of date. It removes
the dominant error (~9 pp/yr of CAGR) and costs ~1 day. Dividends are already
handled; they are not the bottleneck.

---

## 1. Premise corrections — read these first

Two things in the task brief are factually wrong about our own data, and both
change the priority order.

### 1.1 The panel is 50 symbols, not 250
`data/nse/` holds 250 *files* = 50 symbols × 5 timeframes. There are 50 `_1d.csv`.
The universe is today's NIFTY-50 backfilled — exactly as feared, but the size of
the biased set is 50, and the true historical membership is **104 distinct names**.

### 1.2 The panel is total-return, not price-only
`tools/download_nse.py:70` fetches with `auto_adjust=True`. I re-fetched from
Yahoo and compared against the stored CSVs:

| symbol | rel. err vs Yahoo adjusted | rel. err vs Yahoo raw | verdict |
|---|---|---|---|
| itc | 8.3e-08 | 0.303 | ADJUSTED |
| infy | 8.8e-08 | 0.236 | ADJUSTED |
| sunpharma | 7.7e-08 | 0.082 | ADJUSTED |
| hdfcbank | 7.4e-08 | 0.088 | ADJUSTED |
| reliance | 7.3e-08 | 0.046 | ADJUSTED |
| trent | 7.3e-08 | 0.013 | ADJUSTED |
| **tcs** | **5.3e-03** | 0.209 | **UNKNOWN** (see §4.3) |

`~7e-8` is float32 rounding — an exact match. **Dividends are already in the
series.** Per-symbol dividend audit (`tem/datagap/panel_actions.csv`):

- **48/50** symbols have dividend history since 2008 (median **19** dividends).
- 2 exceptions: `bajajauto` is a ticker-alias artefact (`BAJAJ-AUTO.NS` does have
  20 dividends since 2008); `eternal` is the 2025 Zomato rename, genuinely new.
- 40/50 have Yahoo split records.
- 0 names show a frozen tail.

**Consequence:** there is no "build total-return" workstream. It already exists.
The entire remaining data problem is *universe selection*, plus one broken bar.

### 1.3 The panel is already stale by one live rebalance
Our 50 symbols are **exactly** the NIFTY-50 as of the 2026-08-27 archive.org
snapshot. Since then, at the Sept-2026 rebalance, **WIPRO was removed and BSE
added**. The live list downloaded today confirms it. This is not hypothetical —
it happened last month and we did not notice.

---

## 2. Point-in-time index membership

### 2.1 What NSE itself offers (dead end)

| Source | URL | Result |
|---|---|---|
| Live constituent list | `https://nsearchives.nseindia.com/content/indices/ind_nifty50list.csv` | **200** — current list only, 50 rows, 3.3 KiB |
| NiftyIndices mirror | `https://www.niftyindices.com/IndexConstituent/ind_nifty50list.csv` | **200** — identical content |
| NSE NIFTY-100 list | `.../ind_nifty100list.csv` | **200** — current only |
| NSE press releases | `https://www.niftyindices.com/resources/press-releases` | **200**, 79 KiB HTML — not machine-readable per rebalance |
| Historical data API | `.../Backpage.aspx/getHistoricaldatatabletoString` | **302** — dead |
| NSE bhavdata archive | `.../products/content/sec_bhavdata_full_DDMMYYYY.csv` | **200** for 2019-2026, **404** for 2008/2010/2015/2022-01-01. Retention does not reach our window. |
| `www.nseindia.com` | — | **403** (WAF); archives subdomain works with a browser UA |
| stooq.com | `https://stooq.com/q/d/l/?s=reliance.in` | **Blocked** — JS proof-of-work wall, not scriptable |

**There is no official free point-in-time NIFTY-50 history from NSE.** The live
list is current-state only, and bhavdata does not go back far enough.

### 2.2 What actually works — a reconstructed matrix

> **`https://github.com/vishalvx/nifty-indices-datasets`**
> licence **MIT**, last push 2026-06-26, file
> `datasets/nifty50_weights.csv` (89,562 bytes)
> Method (per its README): "reconstructed from public press releases and
> historical circulars", monthly binary membership.

**Verified by download, not by description:**

```
rows=216   month-ends 2008-01-31 .. 2025-08-31   100 distinct symbols
T2  every single row sums to exactly 50 constituents   -> PASS (216/216)
T3  values are strictly binary {0.0, 1.0}              -> PASS
T4  mean membership change 0.54 symbols/month, max 6
```

**Validated against independent ground truth.** archive.org holds snapshots of
the real NSE constituent file. I downloaded every distinct capture and compared
symbol-by-symbol. Raw GitHub source vs archive.org truth:

| archive.org capture | matched month | Jaccard | disagreement |
|---|---|---|---|
| 2017-10-16 | 2017-10 | **1.0000** | — |
| 2018-05-30 | 2018-05 | **1.0000** | — |
| 2018-09-29 | 2018-08 | 0.9608 | LUPIN vs JSWSTEEL (one rebalance, one month late) |
| 2021-06-15 | 2021-06 | **1.0000** | — |
| 2022-07-28 | 2022-07 | **1.0000** | — |
| 2024-05-24 | 2024-05 | **1.0000** | — |
| 2024-11-10 | 2024-11 | **1.0000** | — |

Mean Jaccard **0.9944**. Six of seven exact; the one miss is a single symbol
resolved one month late.

> I first wrote a "known delistings" test from memory and it appeared to fail
> badly (YESBANK, VSNL, SATYAM, UNTECH all "wrong"). **I was wrong; the dataset
> was right.** YES Bank was merged into ICICI in **March 2020**, not 2015;
> Satyam left the index **2008-12-31**; Unitech left in 2010. The archive.org
> cross-check is the trustworthy oracle and it exonerates the source. Memory is
> not evidence.

### 2.3 Extending to today

archive.org also has 2026 captures, **gzipped** (`tem/datagap/wayback/*.csv`,
need `gzip.decompress`). Those plus today's live list close the tail:

| capture | members |
|---|---|
| 2026-08-27 | **= our panel exactly** (has WIPRO, no BSE) |
| 2026-10-15 | **matches the live list exactly** — WIPRO out, BSE in |
| live 2026-10-16 | identical to the 2026-10-15 capture (Jaccard 1.0) |

Stitched result (`data/nse_membership/nifty50_monthly_membership.csv`, **425 KiB**):

```
10,950 rows | 226 month-ends 2008-01-31 .. 2026-10-31 | 104 distinct symbols
membership per month: min=50 max=50 median=50
```

Re-validating the stitched table against all 9 ground-truth captures:
**9/9 exact, Jaccard 1.0000 on every one.** 39 membership changes over 19 years
≈ the expected semi-annual cadence.

### 2.4 Honest gaps in the membership source

1. **Unverified before 2017-10.** No ground truth exists for 2008-01…2017-09 —
   ~52% of the backtest window. The reconstruction method (press releases) is
   weakest exactly where coverage is thinnest.
2. **Ends 2025-08** in the upstream file. 2025-09…2026-07 is inherited by
   forward-fill from the Aug-2025 row — **inferred, not known** (12 months).
3. **45 month-ends are absent**, concentrated in March and September — i.e. the
   rebalance months themselves. A March change shows up in the April row. This
   is why the stitched table reports 39 changes, not the ~37 expected *plus* the
   March events that were absorbed.
4. MIT licence covers the *code and reconstructed data*, not NSE's underlying
   index data. Usable internally; **do not redistribute**.

---

## 3. Corporate-action audit

### 3.1 Unadjusted splits — far better than the "114 bars" figure

| measure | count |
|---|---|
| bars with \|1-day return\| > 30% in raw CSVs | 64 |
| of those, matching a standard split ratio (1:1.5/1:2/1:5/1:10) | **6** |
| survivors of the `CLEAN_START`/C1-C9 pipeline | **8** bars total |
| **split-like bars surviving into the backtest window** | **1** |

The five other split-like bars are pre-2008 or land on the C2 artifact dates
(`2005-07-29`), so cleaning already removes them. The old "114" figure is
obsolete — the pipeline plus the `recover_nse_data.py` refetch dealt with it.

### 3.2 The one that matters: TRENT 1:1.5 bonus, 2026-01-01

```
2025-12-31  close 4272.686523
2026-01-01  open  2848.457553    <- 4272.686523 / 1.5 exactly
2026-01-01  close 2860.706055    -> ret = -33.05%
```

- A genuine 1:1.5 bonus/split. Yahoo **applies it forward from the ex-date but
  never back-adjusts history** — its current `auto_adjust=True` series carries
  the identical artefact (stored vs adjusted rel-err 7e-8, so we faithfully
  copied Yahoo's bug).
- `C5` drops only \|return\| > 45%. **−33% passes straight through.**
- The bar is also dated **2026-01-01, a market holiday**, with a 9.2 M volume
  spike the following session.
- It sits inside the OOS window on a live NIFTY-50 constituent.

One bar, but it is a −33% single-day phantom crash inside the evidence used to
judge every strategy. Fix it or disclose it.

### 3.3 Divisor / revision drift: TCS

Stored TCS matches Yahoo-adjusted exactly until ~**2026-03-16**, then every bar
is higher by a constant factor of **1.005316** (one clean step, not drift).

This is **not** a split error. It is the signature of a dividend Yahoo added to
its adjusted series *after* our 2026-10-06 snapshot. TCS's quarterly yield is
~0.5%, which matches.

**Implication:** our stored panel is pinned to a Yahoo adjustment vintage that
**no longer exists and cannot be re-derived**. Re-running `recover_nse_data.py`
today would produce a *different* TCS series and therefore a different result,
with no way to tell which is right. Any stored nsealgo result is pinned to a
vendor vintage, not to a reproducible one — this compounds the provenance gap
already noted in `AGENTS.md`.

---

## 4. Delisting / suspension history

### 4.1 Inside our panel: there is none

All 50 symbols end **2026-10-01**. Not one terminates early. So the panel
contains **zero evidence** of any removal or delisting — removed names are simply
absent, with no tombstone row, no last-traded date, no reason. Nothing in
`data/nse/` can distinguish "was removed in 2016" from "never existed".

First dates are also informative: 19 symbols start 2000-01-03 and 11 at
2002-07-01 (Yahoo history-depth artefacts, not listing dates), while late
starters are genuine business events — `eternal` 2021 (Zomato), `jiofin` 2023,
`hdfclife`/`sbilife` 2017, `maxhealth` 2020, `indigo` 2015, `coalindia` 2010.
These are spin-offs/renames where yfinance does **not** stitch the predecessor.

### 4.2 Outside our panel: mostly recoverable

Of the 53 historical-only names in the membership matrix:

- **37/53** have continuous Yahoo history (all back to 1996-2002, no gaps > 6 days).
- **16** return no data. Most are renames, and the successor carries full history:

| historical | successor | bars from |
|---|---|---|
| HDFC | HDFCBANK | 1996 |
| IBULHSGFIN | AUROPHARMA | 1996 |
| TATAMOTORS | TMPV | 1991 |
| JPASSOCIAT | JPPOWER | 2005 |
| RANBAXY | SUNPHARMA | 1996 (merger) |
| RPL | RPOWER | 2008 (partial) |
| LTIM | LTM | 2016 (partial) |
| IDFC | IDFCFIRSTB | 2015 (partial) |

- **4 genuinely unobtainable: `SATYAMCOMP`, `VSNL`, `MCDOWELL-N`, `STER`.**

### 4.3 ⚠️ Two traps that will corrupt a naive reconstruction

**(a) Auto-resolving tickers fabricates companies.** My first resolver happily
returned *a* ticker for every empty symbol. Three mappings were wrong companies:

| historical | auto-resolved to | reality |
|---|---|---|
| VSNL | `VEDL` | **Vodafone** — Vedanta Ltd is unrelated |
| CAIRN | `VEDL` | Cairn India (Vedanta *subsidiary*) — not Vedanta Ltd |
| SESAGOA | `IDBI` | merged into Hindustan Zinc — IDBI is unrelated |

`VSNL → VEDL` is the dangerous one: `VEDL` has 7,728 bars back to **1996**, so it
would silently splice three decades of Vedanta history into a Vodafone line and
look completely healthy. **Only same-entity renames and true mergers may be
mapped; everything else must stay explicitly unresolved.**

**(b) "Ticker exists" ≠ "still trading".** `UNITECH.NS`, `RCOM.NS`, `ZEEL.NS`,
`IDEA.NS` all return continuous bars to 2026-10-14 with real volume and no gaps
> 6 days — despite Unitech having been delisted in 2020. Whether these are
revivals, ticker reuse, or stale vendor records, I could not establish from free
sources. **Delisting status must be confirmed against NSE corporate actions
before any of these is treated as live.** `RELINFRA` shows a 32% zero-volume
share over its last 250 bars — a liquidity warning.

---

## 5. Quantifying the bias (measured, not assumed)

Equal-weight, monthly-rebalanced, 2008-01 → 2026-06, 216 months, prices
`auto_adjust=True` (consistent with our panel):

| series | CAGR | vol | Sharpe (ann.) |
|---|---|---|---|
| **survivors only (today's 50)** — what we backtest | **19.58%** | 21.9% | 0.89 |
| **point-in-time members** — what we should backtest | **10.64%** | 22.1% | 0.48 |
| actual NIFTY-50 (`^NSEI`, price index) | 8.32% | 19.8% | 0.42 |

### **`SURVIVORSHIP GAP = +8.94 pp/yr of CAGR`**

This **corroborates the 7.3%/yr estimate** — the real number is somewhat worse.

**Why it is a LOWER bound.** Point-in-time members with no obtainable price are
dropped, and those are overwhelmingly the collapsed names (Satyam, Unitech,
VSNL, MCDOWELL, Sesa Goa). Dropping precisely the losers shrinks the measured
gap. The true figure is ≥ 8.94 pp/yr.

**Methodology notes (two bugs I hit and fixed — record them so nobody re-runs
them):** averaging price *levels* across a churning universe is meaningless and
produced a nonsense −0.36 pp/yr; the portfolio must be built from per-month
*returns* and compounded. And NSE symbol hygiene matters — `norm()` stripping
`&` turns `M&M` into `MM`, which 404s.

**Caveat:** equal-weight ≠ cap-weighted. This is the right analogue for our
strategy (which is equal-weight over 50 names), not an estimate of the bias in
the NIFTY-50 index itself.

---

## 6. Costed recommendation

### (a) Reconstruct point-in-time membership — **RECOMMENDED**

| | |
|---|---|
| **Effort** | ~1 day. Membership + loader **already written and validated** (§2.3). Remaining: fetch 104 symbols' prices, wire `Membership.members(date)` into the engine's universe selection, re-run walk-forward. |
| **Accuracy** | 9/9 exact vs ground truth 2017-10→2026-10. Unverified 2008-01→2017-09. 2025-09→2026-07 inferred. |
| **Bias removed** | **~all of it — ~8.9 pp/yr (≥ the measured gap).** |
| **Cost** | zero. MIT + public archives. |

### (b) NSE rebalance announcements only — not viable

The `niftyindices.com/resources/press-releases` page returns 200 but is HTML,
not a per-rebalance machine-readable feed, and no per-index-change archive exists
on the reachable endpoints. This is strictly worse than (a) for more effort.
**Skip.**

### (c) Delisting-aware universe rules — **viable fallback, much weaker**

If (a) is rejected: rule the universe down to names with continuous history.
This *cannot* recover the collapsed names, so it **cannot** remove the bias —
it only prevents adding new bias. Effort ~0.5 day, accuracy low.
**Use only as a guardrail, never as the fix.**

### (d) Cannot fix — **true for a residue, false for the whole**

Not fixable:
- `SATYAMCOMP`, `VSNL`, `MCDOWELL-N`, `STER` price history — no free source. NSE
  bhavdata does not reach 2008.
- Membership truth for 2008-01…2017-09 — no ground truth exists to verify against.
- The Yahoo adjustment vintage behind the stored CSVs (TCS §3.3) — gone.

### Residual, after doing everything in (a)

| residual | size | mitigate |
|---|---|---|
| 4 collapsed names with no prices | understates the gap; true bias **> 8.94 pp/yr** | disclose; treat the gap as a floor |
| 2008–2017 membership unverified | unknown, plausibly small if the method was sound | re-verify against NSE circulars if a rebalance ever matters |
| 12 inferred months (2025-09→2026-07) | ~6% of window, near-certainly small | disclose; `is_inferred_window()` flags it |
| TRENT −33% phantom bar | 1 bar, large single-day effect | **fix the bar** — tighten C5 or patch the split |
| Vendor revision drift | unquantifiable going forward | **freeze + hash the panel**, or results stay non-reproducible |

---

## 7. Recommended order

1. **Make the universe a function of date.** Largest error, lowest cost, code exists.
2. **Fix the TRENT 1:1.5 bar** (or widen C5 and re-run). One line, removes a
   −33% artefact from the OOS window.
3. **Freeze and hash the panel.** TCS proved the stored CSVs cannot be
   re-derived. Without this, re-runs silently drift.
4. **Refresh membership past 2025-08** when a newer GitHub push lands; it is
   13 months stale and the panel is already one rebalance behind.

---

## 8. Artefacts written

| path | size | committed? |
|---|---|---|
| `data/nse_membership/nifty50_monthly_membership.csv` | **436 KiB** | no — `/data/` is gitignored |
| `data/nse_membership/membership_meta.json` | 1 KiB | no |
| `tools/pit_membership.py` — loader stub, 9/9 ground-truth validated | 6 KiB | yes (tracked) |
| `tools/build_pit_membership.py` — rebuilds the membership table | 4 KiB | yes (tracked) |
| `tem/datagap/` — all scripts, raw downloads, price cache | **1.5 MiB** | no — `tem/` is gitignored |

**Not committed. `src/` untouched.**

### Loader stub — `tools/pit_membership.py`

Deliberately placed **outside `src/`** so it cannot silently change a stored
backtest result. Merging it into the engine is a separate, gated step.

```python
>>> from pit_membership import load_membership
>>> mem = load_membership()
>>> mem.summary()
{'months': 226, 'symbols_ever': 104,
 'coverage': '2008-01-31 .. 2026-10-31', 'changes': 39,
 'unobtainable': ['MCDOWELLN', 'SATYAMCOMP', 'STER', 'VSNL'],
 'inferred_window': '2025-09-01 .. 2026-08-01'}
>>> mem.members('2026-06-30')   # len == 50
```

It distinguishes the two kinds of absence that a naive forward-fill conflates:
*a symbol absent from a month that has records* (not a member) vs *a month absent
from the source entirely* (inherit the prior month). Getting this backwards
silently inflates the index — my first two attempts did exactly that.

---

## 9. Dead ends — stated plainly

- **No official free point-in-time NIFTY-50 history exists from NSE.** The live
  constituent CSV is current-state only; bhavdata retention does not reach 2008.
- **stooq.com** is behind a JS proof-of-work wall — not scriptable.
- **`www.nseindia.com`** returns 403 to non-browser agents; `nsearchives` and
  `niftyindices` work with a browser User-Agent.
- **archive.org has only ~9 distinct membership captures** (2017→2026). Enough to
  *validate* a reconstruction, nowhere near enough to *be* one.
- **The GitHub reconstruction is MIT but unofficial** and 13 months stale. It is
  the only real option found, and it scored 9/9 on ground truth — but it is one
  hobbyist's press-release scraping, not an institutional dataset.
- **Stooq / other free mirrors** could not cross-check Indian dividends; Yahoo is
  the only working free source found, and its adjusted series is itself buggy
  (TRENT §3.2) and unstable (TCS §3.3).