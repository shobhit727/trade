# NSE Daily OHLCV Data-Quality Audit

**Date:** 2026-10-09 · **Scope:** `data/nse/*_1d.csv` (50 files, 281,342 bars) · **Scratch:** this directory

## Verdict (one paragraph)

The audit claim is **half right and half wrong, and the wrong half is the dangerous half.**
`high == open` **is** real and **is** elevated — **10.06%** pooled, not 6.68% — and it **does** get
worse on violent days (7.16% → 11.56%). But it is **not** a corruption of `high`, and it does **not**
break breakout strategies. The `high` column tracks the true intraday high; the defect is in the
**`open` column**, which is wrong on **90.81%** of days and on **20.12%** of days sits *outside the
entire true trading range* — a price that never traded. Because the vendor conservatively brackets
`high = max(open, close, true_high)`, a too-high phantom open manufactures the `high == open`
artifact. **Fixing `high` is the wrong repair**; `high` is the field to leave alone.

---

## 1. Quantification (all 50 `*_1d.csv`, 281,342 bars)

| Statistic | Rate | Expected, genuine market |
|---|---|---|
| `high == open` | **10.06%** | ~0.0–0.1% |
| `high == close` | 1.69% | ~0.0–0.1% |
| `low == open` | 8.41% | ~0.0–0.1% |
| `low == close` | 1.70% | ~0.0–0.1% |
| `high == low` (flat) | 1.52% | ~0.0% |

Per-symbol spread (`research/data_quality/per_file_rates.csv`): min 5.33% (`hdfclife`), median
**9.40%**, max 35.78% (`nestleind`). The outlier is **not** a distinct defect — `nestleind` carries
1,723 zero-volume dead bars (2003–2009, ~250/yr); excluding them its rate is **9.89%**, in line with
the panel.

**Two distinct populations:**

- **Dead bars (1.52%).** `vol == 0` and `high == low == open == close`. 98.6% of these are also
  `high == open`. These are non-trading sessions (holidays/halts), not corrupt bars.
- **Live bars (`vol > 0`, 277,079 bars): `high == open` = 8.70%.** This is the population that
  matters, and it is the one under investigation.

**Why the baseline is not zero.** Two real effects inflate the rate above zero, and both are
legitimate:

- **Tick grid.** NSE prices are quantised (₹0.05). Monte Carlo on a grid vs. continuous prices at
  22% annual vol: `P(high==open)` is **15.98%** at ₹12, **2.58%** at ₹50, **0.54%** at ₹200,
  **0.07%** at ₹1400, **0.04%** at ₹3000. A ₹0.05 tick is 0.4% of a ₹12 stock and 0.004% of a ₹1400
  one.
- **Down-day drift.** The open is the day's extreme exactly when the day never retraces past it.
  Conditional rates confirm this is directional, not random: `P(high==open | close<open) = 16.19%`
  vs. `P(high==open | close>open) = 0.02%`. A symmetric artefact could not produce that split.

Observed rates fall monotonically with price level — **17.08%** below ₹10 → **12.32%** (₹10–25) →
**8.39%** (₹100–250) → **6.23%** above ₹5000 — exactly the tick-grid gradient. The pre-2010 era runs
15–20% (prices were low then); 2013–2025 runs 6–7%. This is a **price-scale artifact plus a real
`open` defect**, not a `high` defect.

## 2. Vendor-specific or systematic? — **Systematic, and worse intraday**

| Timeframe | Bars | `h==o` | `h==c` | `l==o` | `l==c` | `h==l` |
|---|---|---|---|---|---|---|
| **1d** | 281,342 | **10.06%** | 1.69% | 8.41% | 1.70% | 1.52% |
| 1h | 159,131 | 5.40% | 2.91% | 4.01% | 2.62% | 0.09% |
| 5m | 123,720 | **13.12%** | 8.59% | 9.38% | 9.39% | 0.06% |
| 15m | 42,120 | **9.63%** | 6.13% | 6.79% | 6.46% | 0.18% |
| 30m | 22,100 | 6.89% | 5.01% | 4.20% | 5.19% | 0.00% |

The daily series is **not** the worst offender — 5m is worse (13.12%), and 5m has a near-zero flat-bar
rate (0.06% vs 1.52%). The rate is a property of the `open` field and is present at every timeframe.

**Important caveat: 15m is not independent evidence.** Re-bucketing the 5m file into 15-minute bars
reproduces the 15m file with **100.00% exact OHLC match** on all four price columns (846/846
buckets). The 15m file is a resample of 5m. Only 5m and 1d carry independent information.

## 3. Clustering on volatile days — **claim confirmed**

| `|close-to-close return|` quintile | Bars | `h==o` | `l==o` |
|---|---|---|---|
| Q1 calm | 55,397 | **7.16%** | 4.54% |
| Q2 | 55,396 | 7.20% | 5.10% |
| Q3 | 55,397 | 8.10% | 6.20% |
| Q4 | 55,396 | 9.43% | 7.94% |
| **Q5 violent** | 55,397 | **11.56%** | **11.29%** |

By range `(high-low)/close` quintile: **7.41%** (tightest) → **11.70%** (widest).

By absolute range threshold:

| Range | Bars | `h==o` | `l==o` |
|---|---|---|---|
| 0–1% | 6,651 | 9.52% | 6.78% |
| 1–2% | 79,389 | 7.09% | 5.45% |
| 2–4% | 128,126 | 8.26% | 6.83% |
| 4–7% | 47,030 | 10.73% | 8.73% |
| **≥7%** | 15,883 | **13.83%** | **11.48%** |

**Magnitude: +4.40pp from calm to violent quintile (1.6×); +6.74pp for ranges ≥7% (1.9×).** The
mechanism is the phantom-open error scaling with volatility — median error 0.134% of close, p95
0.596%, max 2.006%.

## 4. Corrupt, or legitimate-but-unhelpful? — **`high`/`low` are sound; `open` is corrupt**

Integrity checks on all 281,342 daily bars:

| Check | Result | Verdict |
|---|---|---|
| `high < low` | 46 (0.0164%) | ✅ essentially clean |
| `high < open` | 26 (0.0092%) | ✅ essentially clean |
| `low > open` | 41 (0.0146%) | ✅ essentially clean |
| `high >= max(open,close)` | 99.977% | ✅ |
| `low <= min(open,close)` | 99.977% | ✅ |
| Close series sane | ✅ | see below |

**The vendor does NOT populate `high = max(open, close)`.** Only 10.23% of bars satisfy that; on
~90% of bars `high` strictly exceeds both. And `high > max(open,close)` on **0.000%** of the
`high==open` bars — i.e. on those bars the open genuinely *is* the recorded extreme.

**The vendor *does* track true intraday high/low.** Aggregating 5m → daily and comparing
(`research/data_quality/daily_vs_5m.csv`, 1,600 overlapping days):

- daily `high` == intraday max: **32.12%** exact; median gap **0.15 rupees**
- daily `low` == intraday min: **36.31%** exact; median gap **0.10 rupees**
- daily `low` > intraday min: **0.00%** — the daily low is never above the true low
- daily `high` == `max(daily_open, intraday_high)`: **40.00%** — the vendor brackets against the
  reported open

**The close series is clean:** daily close == intraday last close on **97.12%** of days, and
close-to-close returns have median 1.05%, p99 7.84%, with only 0.0405% of bars exceeding the NSE 20%
circuit limit. No impossible gaps.

### The real defect: `open`

| Check over 1,600 overlapping days | Result |
|---|---|
| daily `open` differs from true first print | **90.81%** |
| daily `open` **above the entire intraday range** | **13.06%** |
| daily `open` **below the entire intraday range** | **7.06%** |
| daily `open` outside range (either side) | **20.12%** (322 days) |
| median error | 1.400 rupees (0.134% of close) |
| p95 error | 19.525 rupees (0.596% of close) |
| max error | 93.000 rupees (2.006% of close) |

Worked example — `reliance`, 2026-09-25: 5m trades the whole day between **1215.0 and 1227.3**; the
daily file reports `open = 1210.5`, a price that **never traded**, and then stretches `low` down to
1210.5 to accommodate it.

**Causal chain (confirmed):** of 208 days where `open > true_high`, **60.58%** show the `high==open`
artifact; of 113 days where `open < true_low`, **52.21%** show `low==open`. Conversely only **8** of
134 `high==open` bars lack the phantom-open explanation. **The `high==open` artifact is a downstream
symptom of the corrupt `open`, not a defect in `high`.**

## 5. Damage to breakout strategies — **negligible**

20-day Donchian (`close > max(high[-p-1:-1])`) across the full 1d history, all 50 symbols:

| | Breakout events |
|---|---|
| Supplied `high` | 18,495 |
| Reconstructed `high = max(open, close, high)` | 18,480 |
| **Delta** | **−15 (−0.08%)** |

Only **1 of 50 symbols** changes at all (`adanient`, −15). The phantom open inflates the daily high
on 65.56% of days but by a median of **0.15 rupees (0.043% of close)**, max 1.648% — a 20-day rolling
maximum absorbs it almost entirely.

**Donchian, atr_breakout, squeeze, nr4, price_channel, triangle, rectangle, flag are all keyed to a
20-day `rolling max` of `high`. A sub-0.05% median per-bar perturbation is invisible to a 20-day
maximum.** These strategies are *not* meaningfully impaired.

**`open_range_breakout` is the genuine exposure** — it is the one strategy that reads `open` directly.
Its trigger is `price > open + k·(high−open)`. With the open wrong on 90.81% of days (p95 0.596% of
close) and the ORB range inflated on 56.75% / deflated on 36.00% of days, **ORB trigger levels are
unreliable**. Note the supplied `open→high` range has median 0.605% vs. a true 0.572%.

## 6. Decisive test: intraday vs daily — **`close` agrees, `open` disagrees**

Aggregating 5m/15m/1h to daily and joining against the 1d files over the shared window
(`research/data_quality/agg_vs_daily.csv`):

| Column | 5m vs 1d exact match | Median abs diff | Median rel |
|---|---|---|---|
| **close** | **97.13%** | **0.0000** | **0.0000%** |
| high | 31.56% | 0.4766 | 0.0235% |
| low | 35.56% | 0.2459 | 0.0158% |
| **open** | **9.06%** | **3.5084** | **0.1432%** |

`close` matches to the tick. `open` matches on **9%** of days — essentially never. This is the
clearest single statement of the defect: **the daily `close` is trustworthy, the daily `open` is not,
and the daily `high`/`low` are accurate to within a tick or two.**

The 1h file is unusable for this test — it shows a ~58-rupee median offset vs. daily, an entirely
different price basis.

## 7. Two additional defects found (orthogonal, worth flagging)

1. **Unadjusted splits — 114 bars (0.0405%) with >20% single-bar moves.** `bajfinance` 2005-07-27
   jumps 2.31 → 252.95 (**+469.6%**) and *reverses* the next day (252.95 → 2.31), the signature of an
   un-applied demerger factor. Same pattern in `bel`, `bajajfinsv`, `cipla`. These are spurious
   returns in the **close** series and would wreck any backtest spanning them.
2. **Negative prices — 47 bars, all `adanient`, 2002-07.** Values around **−0.0122** with real
   volume. Broken back-adjustment. Any log-return or percentage calculation on this window returns
   `NaN`/`inf`.

Both are independent of the `open` defect and both are more dangerous to backtests than it is.

---

## Recommendation

**Q: Is the daily OHLC trustworthy for returns?**
**A: Yes, for `close`, with two carve-outs.** `close` matches intraday to the tick on 97.12% of days
and its return distribution respects circuit limits. But **exclude the 114 split-artifact bars** and
**exclude/drop `adanient` before 2003**. Do not trade or backtest across those without adjustment.

**Q: Is `high`/`low` trustworthy for intraday-range strategies?**
**A: Yes.** They agree with intraday aggregation to within ~0.15 rupees median, `low` is never above
the true low, and the Donchian impact is −0.08%. **The premise that these strategies are broken is
incorrect.** No exclusion is warranted.

**Q: What should the project do?**

1. **Do NOT exclude the breakout strategies.** The audit's stated rationale — "`high == open` breaks
   strategies that read `high`" — is false. The measured Donchian impact is 15 events out of 18,495.
   Excluding 8 strategies would discard ~0.1% of signal over a defect that does not touch them.
2. **Do NOT "reconstruct" `high = max(open, close)`.** That repair is backwards: `high` is the good
   column. It would *discard* the true intraday high on 90% of bars and manufacture the very artifact
   it aims to fix. It also changes nothing measurable (−15 events).
3. **Fix `open`, not `high`.** Any downstream fix should correct the open from a Kite/session feed,
   or derive it as the first intraday print. Until then, **gate `open_range_breakout` and any
   open-keyed logic** (gap filters, ORB, overnight fills) behind a data-quality assertion. Expected
   trigger: a sanity check rejecting bars where `open` is outside `[low, high]` will fire on ~20% of
   days — that assertion alone would have caught this at ingest.
4. **Add three cheap ingest assertions** (all currently able to pass silently):
   `open ∈ [low, high]`; `|return| < 20%` (catches the 114 split bars); `open > 0` (catches the 47
   adanient bars).
5. **Stop treating 15m as independent corroboration.** It is a bit-exact resample of 5m (100.00%
   match). Any validation that uses 15m to "confirm" 5m is validating one source against itself.

**Correcting the record:** the reported 6.68% is understated — the true pooled rate is **10.06%**, and
8.70% on live bars. But the *conclusion* drawn from it was wrong. The elevated rate is a symptom of a
corrupt `open` column, not a corrupt `high`; it does not impair the eight strategies listed, and the
genuinely broken thing (`open_range_breakout`) was not on the audit's list.

---

## Artifacts in this directory

| File | Contents |
|---|---|
| `per_file_rates.csv` | Per-symbol `h==o`/`h==c`/`l==o`/`l==c` rates, bar counts, zero-vol counts |
| `daily_vs_5m.csv` | 1,600 overlapping days: daily OHLC vs 5m-aggregated OHLC (the decisive test) |
| `agg_vs_daily.csv` | 5m/15m/1h → daily aggregation vs 1d files, per symbol and column |

## Reproducing

```python
import pandas as pd, numpy as np, glob
for f in sorted(glob.glob('data/nse/*_1d.csv')):
    d = pd.read_csv(f); o,h,l,c,v = d.open,d.high,d.low,d.close,d.vol
    print(f, "h==o", round(100*(h==o).mean(),2), "| live-bar rate",
          round(100*(h[v>0]==o[v>0]).mean(),2))
```