# `correlation_gate` on NSE NIFTY-50 — validation report

**Status: IN PROGRESS** (this file is appended to as work proceeds)

---

## 1. Assignment

| Item | Value |
|------|-------|
| Assigned strategy | `correlation_gate` |
| Source | `src/cryptobot/strategies/catalog/correlation_gate.py` |
| Data used | `data/nse/*_1d.csv` (daily), via `nsealgo.data.loader.load_universe` |
| TRAIN | 2016-01-01 → 2023-12-31 |
| TEST | 2024-01-01 → 2026-10-01 |

### 1.1 What the strategy actually computes (naming caveat)

The catalog name is **misleading**. Despite being called `correlation_gate`, the file
contains **no correlation statistic of any kind** — no rolling correlation, no
covariance, no dispersion or eigenvalue measure. The full logic is 12 lines:

```python
m = sma(closes, period)          # period-SMA
r = roc(closes, period)          # rate of change over `period`
if r >  threshold and close > m:  return +1
if r < -threshold and close < m:  return -1
return 0
```

So the real strategy is a **dual-confirmation trend-following crossover**: price above
its own SMA *and* positive ROC over the same window. The "gate" is the ROC deadband
`threshold`, not a correlation filter. I report it under its assigned name but every
result below describes the SMA+ROC crossover, because that is what the code does.
This naming mismatch is itself a finding worth recording (see §7).

---

## 2. DECLARED PARAMETER BUDGET (written before any run)

**Hard cap: 5 distinct parameter variants. This is the complete list. No sixth.**

### 2.1 The 5 variants (all that will ever be run)

| ID | `period` | `threshold` | Note |
|----|----------|-------------|------|
| V1 | 20 | 0.010 | catalog default |
| V2 | 10 | 0.010 | shorter ROC window |
| V3 | 40 | 0.010 | longer ROC window |
| V4 | 20 | 0.000 | ROC gate effectively disabled |
| V5 | 20 | 0.030 | wide ROC deadband |

These 5 were declared by the interrupted run in
`02_train_sweep.py` *before* its first backtest. I am honouring the same
declaration rather than re-cutting a fresh budget, so the budget is not being
quietly enlarged to cover a second search.

### 2.2 Fixed across all 5 (not swept, not tuned)

| Choice | Value | Rationale |
|--------|-------|-----------|
| Signal mapping | cross-sectional pct-rank of the strategy's **own** ROC(period), taken only over names flagged +1 | keeps alpha attributable to `correlation_gate` instead of smuggling in nsealgo's momentum factor |
| Names flagged 0/−1 | excluded (NaN), never shorted | Indian delivery account is long-only; the strategy says "flat", so the book is flat |
| Rebalance | monthly | engine default, matches the evidence note in `engine.py` |
| Portfolio | `PortfolioConfig()` defaults | n_positions=22, max_weight=12%, max_sector=25%, cash_buffer=10%, max_names=30 |
| Costs | `CostModel(segment="delivery", slippage_bps=5)` | mandatory full Indian stack |

### 2.3 Selection rule (declared up front)

**Highest TRAIN Sharpe; tie-break on lower TRAIN MaxDD.** The champion is then run
on TEST exactly once, unchanged.

### 2.4 Cost figure convention

Backtests go through `run_backtest`, which never calls `fill_price`, so it folds
slippage in as `rt_bps + 2 × slippage_bps`. **Every number in this report is net of
the full 21.92 bps all-in round trip.** The 11.92 bps statutory-only figure is never
quoted on its own, to avoid the double-count/under-count confusion the brief warns about.

---

## 3. Protocol compliance statement

- Parameters were chosen on **TRAIN only** (`02_train_sweep.py` does not load the TEST
  window at all).
- TEST was then evaluated once, unchanged, with the champion.
- Any deviation discovered during verification is recorded explicitly in §6.

*(results appended below)*
---

## 4. Verification of the inherited harness (done BEFORE trusting any number)

The interrupted run left 13 scratch files. I re-verified rather than reused on faith.
Three of my own verification scripts failed at first and were **my** bugs, not the
harness's — all three are recorded in §6.2 because they are the kind of mistake that
manufactures a fake leak or a fake pass.

### 4.1 Vectorised signal == the real catalog class — PASS

I drove the actual `CorrGateStrategy.signal()` bar-by-bar over real OHLC arrays for 6
symbols × 4,629 bars and compared against the vectorised panel.

| Vectorised ROC offset | Mismatching (symbol,bar) cells | of |
|---|---|---|
| `shift(period)` | **125** | 27,774 |
| `shift(period+1)` | 2,283 | 27,774 |

The residual 125 are **not** a real disagreement. They are all bars where the panel has
a genuine NaN (IPO/suspension gap) so the rolling SMA is undefined and the vectorised
signal is correctly forced to 0, while my *verification harness* had compacted the
series with `.dropna()` and so handed the class a well-defined SMA. That is an artefact
of the checker, and the vectorised panel is right.

Settled independently by calling the real indicator (`v02_roc_offset.py`):

```
roc(px, 20)                        = -0.0861088672
close[t]/close[t-20] - 1           = -0.0861088672   match=True
close[t]/close[t-21] - 1           = -0.0639484477   match=False
```

So `roc()` is a `period`-bar shift, and the inherited `common.py` was **correct**.
I initially suspected an off-by-one from reading `closes[-period-1]` naively; that
hypothesis was wrong and I withdrew it. The prior harness did not need fixing.

### 4.2 No lookahead — PASS (4 independent tests, `v05_lookahead.py`)

The strongest test: rebuild the book from a panel **truncated** at various dates and
check that every past weight is bit-identical to the full run. Any leak of a future bar
into a past decision would show up as a non-zero delta.

| Test | Result |
|---|---|
| 1. Truncation test, 5 cuts on TEST (120→555 overlapping bars) | max abs Δweight = **0.000e+00**, max abs Δreturn = **0.000e+00** |
| 2. Extra lag must hurt | shift(1) −1.36 pp CAGR, shift(2) −2.19 pp — monotone degradation |
| 3. Same truncation test on **TRAIN** (where selection happened) | max abs Δweight = **0.000e+00** |
| 4. Score rank rebuilt from an independent recompute | **0** mismatches |

### 4.3 Portfolio constraints — all PASS (`v04_weight_drift.py`)

`single weight ≤ 12%` · `cash ≥ 10%` (max gross observed exactly 90.00%) ·
`names ≤ 30` · `weights ≥ 0` · `no NaN`.

**One honest deviation to disclose:** average names held is **28.84**, not the
`n_positions=22` target. Cause: the engine selects 22 target names
(`k = min(n_positions, n)`, `engine.py:255`) but the turnover-budget blend plus
`_thin(w, max_names=30)` (`engine.py:292`) keeps up to 30 material positions. The book
is **saturated at the `max_names=30` hard cap on 2,619 of 2,660 bars** and does not
grow without bound, so this is engine design, not residual-weight accumulation.
Held-but-dust positions (<0.1% of book) total **0.013%** of book — dust, not drift.
The book is *more* diversified than the brief's "22 names" idealisation, which if
anything costs the strategy alpha rather than flattering it.

---

## 5. RESULTS

### 5.1 TRAIN (2016-01-01 → 2023-12-31) — the only place selection happened

| Variant | period | thr | CAGR | Sharpe | MaxDD | Calmar | live% | names |
|---|---|---|---|---|---|---|---|---|
| **V2 → CHAMPION** | 10 | 0.01 | **16.12%** | **0.83** | −13.93% | 1.16 | 40.4 | 29.6 |
| V1 (catalog default) | 20 | 0.01 | 12.81% | 0.55 | −28.30% | 0.45 | 44.8 | 29.0 |
| V4 | 20 | 0.00 | 12.82% | 0.54 | −28.64% | 0.45 | 47.6 | 29.0 |
| V3 | 40 | 0.01 | 12.97% | 0.51 | −30.66% | 0.42 | 48.6 | 27.8 |
| V5 | 20 | 0.03 | 11.92% | 0.48 | −26.50% | 0.45 | 37.7 | 28.8 |

Champion = **V2 (period=10, threshold=0.01)**, selected on TRAIN Sharpe, unchanged.
Parameter budget respected: **5 variants tested, 5 declared, 0 exceeded.**

### 5.2 TEST (2024-01-01 → 2026-10-01) — out-of-sample, champion unchanged

All figures **net of the full 21.92 bps all-in round trip.**

| Metric | correlation_gate (V2) |
|---|---|
| **CAGR** | **3.53%** |
| **Sharpe** | **−0.20** |
| **MaxDD** | **−13.72%** |
| **Calmar** | 0.26 |
| Turnover | 4.13×/yr |
| Cost drag | 1.06%/yr |
| Avg names held | 28.84 |
| Avg gross exposure | 76.2% (23.8% cash) |
| Max single weight | 10.01% |
| Signal liveness | long 38.2%, short 33.6%, flat 28.1% of symbol-days |

Calendar-year net returns: **2024 +14.47% · 2025 +7.22% · 2026 −10.20%**

**TRAIN → TEST decay: Sharpe 0.83 → −0.20; CAGR 16.12% → 3.53%.** The entire TRAIN
edge did not survive the out-of-sample window.

### 5.3 Benchmarks over the identical TEST window

| | CAGR | Sharpe | MaxDD | Calmar | Turn | Drag |
|---|---|---|---|---|---|---|
| **correlation_gate (V2)** | **3.53%** | **−0.20** | −13.72% | 0.26 | 4.13× | 1.06% |
| B&H equal-weight (gross, brief formula) | 8.25% | 0.19 | −15.91% | 0.52 | 2.00× | 0.00% |
| B&H 22-name constrained (net) | **9.76%** | **0.32** | −13.51% | 0.72 | 0.64× | 0.16% |
| nsealgo composite (net) | 6.55% | 0.07 | −14.84% | 0.44 | 2.07× | 0.55% |
| random control (mean of 5) | 5.14% | −0.07 | −13.06% | 0.40 | 4.14× | 1.07% |

- vs **buy-and-hold (net, fair)**: **−6.24 pp CAGR** and **−0.21 pp worse MaxDD**.
  Worse on return *and* no better on drawdown — it fails on both axes.
- vs **nsealgo composite**: **−3.02 pp CAGR**, Sharpe −0.27 worse. Loses to the
  generic composite too.
- Turnover is the quiet killer: **4.13×/yr vs 0.64×/yr** for B&H, costing 1.06%/yr
  against 0.16%/yr. The strategy churns ~6.5× as hard to earn less.

### 5.4 Sanity checks (brief §6)

| # | Check | Result |
|---|---|---|
| 1 | Plausibility (≤40–50% CAGR) | 3.53% — **OK**, no bug |
| 2 | Weight count | 28.84, saturated at the engine's `max_names=30` cap, no accumulation — **OK** |
| 3 | Signal liveness | 38.2% long — **OK**, not a flat strategy |
| 4 | Cost drag | net 3.53% vs 3.96% zero-cost = **0.43 pp/yr**. Costs do **not** flip the sign; the strategy is underwater on merit, not on costs |
| 5 | Negative control | **FAILS — beats 0/5** |

### 5.5 Negative control — the decisive result

Two controls, both matched on the strategy's 38.2% live fraction, 5 draws each:

| Control flavour | Control CAGR | Control Sharpe | Strategy beats on CAGR | on Sharpe |
|---|---|---|---|---|
| random mask, flagged names equal-weighted | 5.14% | −0.07 | **0/5** | 1/5 |
| random mask, strategy's **real** ROC ranking retained | 5.00% | −0.08 | **0/5** | **0/5** |

A coin flip with the same number of positions long and the same turnover pressure
**beats this strategy on return in 10 of 10 draws**. The second control is the stricter
one — it keeps the strategy's momentum ranking and randomises only *which* names get
flagged, so it isolates "is the flag informative" from "does concentration help". The
strategy fails even that.

---

## 6. Findings

### 6.1 `correlation_gate` has no correlation logic (naming bug)

The catalog file is named `correlation_gate` and its docstring is "Correlation gate",
but it computes **no correlation, covariance, dispersion or eigenvalue statistic** —
only `sma`, `roc` and a comparison. The "gate" is a ROC deadband. Anyone reading the
catalog name would assume a diversification/correlation filter and misread every result
attached to it. Suggest either implementing the intended correlation filter or renaming
to `sma_roc_crossover`.

### 6.2 Bugs I introduced and caught (recorded because they nearly faked a result)

1. **`shift(period)` vs `shift(period+1)`.** I read `closes[-period-1]` as a period+1
   shift and nearly "corrected" a correct harness. The bar-by-bar class comparison
   (125 vs 2,283 mismatches) and a direct call to `roc()` both disproved my reading.
   *Had I "fixed" it, I'd have invalidated the run over a non-bug.*
2. **Slice-then-shift.** TEST 4 reported 165 false rank mismatches because I computed
   `s.shift(PERIOD)` on a 4-month slice, NaN-ing the first 10 rows. Shifting must be
   done on the full panel.
3. **NaN-aware equality.** `Series.ne()` returns `True` for `NaN != NaN`, so every
   name the strategy called flat looked like a mismatch. Real mismatch count: **0**.

Also fixed locally: a `ValueError` from pandas `zip(strict=)` and a tz-naive date
slice (`Both dates must have the same UTC offset` — these panels are tz-aware
`Asia/Kolkata`).

### 6.3 Minor: `warmup()` understates by one bar

`CorrGateStrategy.warmup()` returns `self.config.period`, but `roc()` returns NaN while
`len(closes) <= period`, so the first usable signal needs **`period + 1`** bars
(verified: `roc(ones(20), 20) = nan`, `roc(ones(21), 20) = 0.0`). Off by one. Harmless
here — the vectorised panel forces 0 on undefined bars anyway — but it would let a
live caller act on one bar too early.

### 6.4 Protocol disclosure (brief §4.4)

The prior interrupted run had already executed TEST and left `test_output.txt`. I
re-ran TEST **to verify reproducibility, not to choose anything** — my independent
re-run reproduced its numbers exactly (3.53% / −0.20 / −13.72%), and the champion was
selected on TRAIN Sharpe *before* TEST existed in this directory. No parameter was
changed after seeing TEST. I am disclosing it because the honest statement is "TEST
was observed twice", not "once". It does not rescue the result — the result is a loss
either way.

---

## 7. VERDICT

**No — `correlation_gate` does not make money on NSE.** Out-of-sample it returns
**+3.53% CAGR at −0.20 Sharpe**, losing **6.24 pp** to net buy-and-hold, losing
**3.02 pp** to the plain nsealgo composite, and losing to a **random coin flip in
10 of 10 matched draws**. It is a textbook in-sample trap: Sharpe 0.83 on TRAIN
collapses to −0.20 on TEST.

**Most likely reason.** The strategy is not really a strategy — it is a *restatement of
trailing momentum*. Its ROC(period) filter fires almost exactly when a name's own
6-month return is positive, so on a cross-sectional book it selects "recent winners",
which is precisely the crowding trade that mean-reverts at monthly rebalance. Ranking
by its own ROC then concentrates the book in the most extended names, paying 4.13×/yr
turnover for negative selection. The edge was never there; TRAIN was 8 years of a
single NSE bull trend where the filter's cost was under-estimated by luck.

**The one thing I would try next.** Stop ranking by ROC — it is the concentration that
converts a flat signal into a costly one. Instead hold the flagged names **equal-weight
and let the constraint engine cap at `n_positions`** rather than letting a momentum
sort push the book to 30 names at `max_names`. If that still cannot beat a random mask
on net return, the correct conclusion is that a 20-day ROC deadband adds nothing to a
momentum baseline on NSE and the catalog entry should be retired rather than tuned.
