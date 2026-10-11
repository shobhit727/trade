# REPORT — `keltner_channel` on NSE NIFTY-50

**Status:** IN PROGRESS
**Assigned strategy:** `keltner_channel`
**Source:** `src/cryptobot/strategies/catalog/keltner_channel.py`

---

## 0. PROVENANCE — read first

| Item | Value |
|---|---|
| `BacktestResult.engine_sha` | **`970713f3eecf`** |
| git HEAD | `2825d032a30abd917bfd674ba41519f11c2474f1` (engine.py **clean** vs HEAD) |
| loader source sha | `d4fea73f8754` (`src/nsealgo/data/loader.py`, **uncommitted**, see §0.1) |
| panel content sha | `cd443dfed5db` — `(4625, 48)`, 2008-01-01 → 2026-10-01 |
| rows in / out | 274,541 / **207,687** (incl. 539 frozen bars dropped by C9) |
| Data | `data/nse/*_1d.csv` via `nsealgo.data.loader.load_universe` |
| Split | TRAIN `2016-01-01 → 2023-12-31`, TEST `2024-01-01 → 2026-10-01` |
| Cost model | `CostModel(segment="delivery", slippage_bps=5)` → **21.92 bps all-in round trip** charged by `run_backtest` |
| Portfolio | `PortfolioConfig()` — 22 names, 12% single, 25% sector, 10% cash, 35% turnover budget. Never bypassed. |
| Rebalance | Monthly (`"M"`), matching the engine default |

The `engine_sha` is the hash of `src/nsealgo/backtest/engine.py` **after** today's fix to
the dead-position decay bug (previously a name the target dropped decayed only by
`1 - lam` per rebalance and was carried for months at a fraction of intended exposure).
`git diff` confirms `engine.py` is **identical to HEAD**, so the fix is committed and
every number below is reproducible from this commit given this data.

### 0.1 ⚠️ `engine_sha` does not cover the data loader — and it should

This is the most important infrastructure finding of the run.

`BacktestResult.engine_sha` hashes **one file**: `backtest/engine.py`. It is blind to
the **loader**, the **cost model**, and the **panel itself**. During this study,
`src/nsealgo/data/loader.py` was modified in the working tree by concurrent work,
gaining rule **C9 — drop frozen closes (vendor feed freeze)**, which removes **539
bars** across `bajajauto` and `nestleind`:

| symbol | first | last | run length | frozen close |
|---|---|---|---|---|
| bajajauto | 2008-03-13 | 2008-05-23 | 46 | 324.43 |
| nestleind | 2008-01-01 | 2008-11-12 | 214 | 433.07 |
| nestleind | 2008-11-14 | 2010-01-07 | 279 | 433.38 |

My first panel was built **before** C9 landed and contained those 539 bars. This is not
hypothetical risk: for a **Keltner** strategy a frozen close is uniquely poisonous,
because a repeated close produces a near-zero true range, which shrinks `ATR`, which
**inflates `(mid − close)/ATR`** — i.e. it manufactures spurious "below the lower band"
signals, precisely the signal under test. An un-hashed loader is an un-hashed input.

**What I did about it.** I rebuilt the panel from the current loader and re-ran the
entire chain (`00` → `05`). **Every number in this report comes from the corrected
panel** (content sha `cd443dfed5db`).

**And the honest result of the re-run: it changed nothing.** All 3 frozen runs end by
**2010-01-07**, i.e. entirely before TRAIN begins on 2016-01-01. They only move the
EMA recursion seed for two symbols inside the warm-up region, where the seed's weight
is `(1 − 2/41)^2000 ≈ 0`. Concretely: **TEST metrics are byte-identical before and
after** (0.359% CAGR, −0.781 Sharpe, −13.146% MaxDD, 2.974x turnover, 6.048 avg names),
TRAIN moved only in the 2nd–3rd decimal (e.g. `kelt_pure_p20_m2` 2.478% → 2.552% CAGR),
the TRAIN ranking is unchanged, and the selected variant is unchanged.

**Disclosure: TEST was therefore read twice.** Both reads were of the same declared
variant chosen on TRAIN; the first was on the pre-C9 panel, the second on the
corrected panel. No parameter, threshold or variant was chosen using either read. I am
recording this rather than quietly re-running, because a protocol violation that
produces identical numbers still has to be on the record.

**Recommendation:** extend `_engine_sha` (or add a sibling) to cover
`data/loader.py` and `costs.py`, and have `run_backtest` record a hash of the panel it
was handed. Right now a concurrent edit to the loader would silently change every
result in this project while `engine_sha` kept reporting `970713f3eecf`.

---

## 1. The strategy

Catalog implementation (`src/cryptobot/strategies/catalog/keltner_channel.py`):

```python
mid = keltner_mid(closes, period)                       # EMA of closes, period
b   = atr(highs, lows, closes, period)                  # mean of last `period` true ranges
+1  if closes[-1] < mid - multiplier * b                # below lower band -> LONG
-1  if closes[-1] > mid + multiplier * b                # above upper band -> SHORT
 0  otherwise
```

Defaults `period=20, multiplier=2.0`. This is a **mean-reversion / volatility-band**
signal. Not crypto-specific — in scope for NSE.

**Exact semantics of the two primitives** (verified against
`src/cryptobot/strategies/indicators.py`, not assumed):

* `ema(values, period)` — `out[0] = a[0]`, then `out = k*x + (1-k)*out`, `k = 2/(period+1)`.
  It is seeded at **bar 0 of whatever array it is given**, and it is *not* a windowed
  function. So a whole-history EMA series computed on the full panel reproduces the
  catalog's value at every bar `t` exactly: `ema(closes[:t+1]) == ewm(span=period,
  adjust=False)` evaluated at `t`.
* `atr(highs, lows, closes, period)` — `np.mean` of the last `period` true ranges, and it
  returns NaN unless `len(closes) >= period + 1`. TR[0] is undefined (no previous
  close), so the first valid ATR is at bar index `period`, matching a
  `rolling(period).mean()` over a TR series whose first entry is NaN.

Both use data up to and **including** day *t*. `run_backtest` holds weights decided at
`t` from `t+1` (`held.shift(1)`). No look-ahead.

**NSE adaptation (brief §5).** Long-only; the `-1` upper-band leg is dropped:

> Hold names whose close is below their 20-day EMA by more than `multiplier x ATR(20)`.

---

## 2. DECLARED PARAMETER BUDGET — 5 variants

Declared before any backtest ran. Full text: `DECLARED_BUDGET.md`.
**Budget = 5. Used: 5/5.**

| # | name | period | multiplier | construction |
|---|------|--------|-----------|--------------|
| V1 | `kelt_pure_p20_m2`    | 20 | 2.0 | `pure` |
| V2 | `kelt_hybrid_p20_m2`  | 20 | 2.0 | `hybrid` |
| V3 | `kelt_pure_p20_m25`   | 20 | 2.5 | `pure` |
| V4 | `kelt_pure_p40_m2`    | 40 | 2.0 | `pure` |
| V5 | `kelt_hybrid_p20_m25` | 20 | 2.5 | `hybrid` |

`pure` = rank gated names by band depth (isolates the Keltner signal).
`hybrid` = rank gated names by 126-day momentum (brief §5 recipe; a Keltner+momentum
hybrid, labelled as such).

**Selection rule (fixed in advance):** TRAIN-only; disqualify any variant with TRAIN
`avg_names` < 8 as effectively always-flat; among survivors take highest TRAIN Sharpe,
ties (<0.05) broken by higher TRAIN Calmar. If none clears the liveness gate, that is
the finding — the budget is not widened.

---

## 3. Results

### 3.1 Port verification (step 01) — the vectorised signal IS the catalog signal

`keltner_depth()` was compared bar-for-bar against a real `KeltnerStrategy` object on
real NSE bars, for both declared periods:

| period | bars checked | mismatches |
|--------|--------------|------------|
| 20 | 12,000 | **0** |
| 40 | 12,000 | **0** |

The window used was 300 bars, matching `SignalStrategy`'s `deque(maxlen=300)` feed.
A first attempt used a ~26-bar slice and produced 150 mismatches; that was the
*harness* being wrong (see §5.1), not the port.

### 3.2 TRAIN (2016-01-01 → 2023-12-31) — all 5 declared variants

| name | CAGR% | Sharpe | MaxDD% | Calmar | Turn/y | Drag%/y | AvgNames |
|---|---|---|---|---|---|---|---|
| kelt_pure_p20_m2 | 2.552 | −0.400 | −27.140 | 0.094 | 1.481 | 0.904 | 1.62 |
| kelt_hybrid_p20_m2 | 3.475 | −0.337 | −24.535 | 0.142 | 1.410 | 0.945 | 1.44 |
| kelt_pure_p20_m25 | 0.838 | −0.816 | −32.410 | 0.026 | 0.793 | 0.449 | 0.79 |
| **kelt_pure_p40_m2** | 2.341 | **−0.256** | −46.466 | 0.050 | 2.370 | 1.240 | 3.68 |
| kelt_hybrid_p20_m25 | 0.826 | −0.890 | −32.410 | 0.025 | 0.733 | 0.422 | 0.67 |

**Every one of the five variants has a negative TRAIN Sharpe.** Not one is positive.
`kelt_pure_p40_m2` is the least bad.

**Liveness (TRAIN)** — every variant failed the pre-registered `avg_names >= 8` gate:

| variant | cell % flagged | mean names flagged/bar | median | % bars with 0 flagged |
|---|---|---|---|---|
| p20 m2.0 | 4.12% | 1.98 | 0 | 50.5% |
| p20 m2.5 | 1.93% | 0.95 | 0 | 68.9% |
| p40 m2.0 | 8.69% | 4.17 | 2 | 29.1% |

Per `DECLARED_BUDGET.md` rule 5 the pre-registered rule therefore selected **nothing**.
`kelt_pure_p40_m2` was carried into TEST as the rule's own ranking (highest TRAIN
Sharpe) with the disqualifier removed — see the disclosure in §5.2.

### 3.3 TEST (2024-01-01 → 2026-10-01) — the single out-of-sample pass

Variant `kelt_pure_p40_m2` (period 40, multiplier 2.0, `pure`). All figures **net of
21.92 bps**; engine `970713f3eecf`; panel `cd443dfed5db`.

| | **KELTNER** | **BUY-AND-HOLD** | RANDOM ctrl | nsealgo COMPOSITE | KELTNER gross* |
|---|---|---|---|---|---|
| **CAGR** | **0.36%** | **9.54%** | 0.36% | 7.61% | 0.96% |
| **Sharpe** | **−0.78** | **0.30** | −0.78 | 0.14 | −0.70 |
| **MaxDD** | **−13.15%** | **−13.48%** | −13.15% | −15.22% | −12.90% |
| **Calmar** | **0.027** | **0.71** | 0.027 | 0.50 | 0.074 |
| Turnover/y | 2.97x | 0.51x | 2.97x | 2.04x | 2.97x |
| Cost drag/y | 1.30% | 0.22% | 1.30% | 0.90% | 0.71% |
| Avg names | 6.05 | 22.00 | 6.05 | 22.00 | 6.05 |
| Total | +1.01% | +29.10% | +1.01% | +22.82% | +2.71% |
| Win rate | 39.8% | 53.1% | 39.8% | 53.4% | 39.9% |

\* gross is a **diagnostic only** (brief §6.4 cost decomposition), never a reported result.

**Year by year:** keltner −1.40% / +6.34% / −3.67% (2024/25/26); buy&hold +16.49% /
+16.00% / −4.46%. Keltner beat buy&hold in **0 of 3** years.

**Exposure:** only **32.8%** of capital is invested on average — the remaining ~67% sits
in cash earning 0%, because the book holds 6 names capped at 12% each (6 × 12% ≈ 72%,
and far fewer on sparse days). That cash drag is a large part of the return gap and is
a *property of the signal's sparsity*, not of the cost model.

**Plausibility (brief §6):** CAGR 0.36% ≪ 50% ✅ · avg names 6.05 ≤ 22 ✅ · engine
charged exactly 21.92 bps ✅ · no NaNs, no negative-equity states ✅.

#### Scorecard — the four questions brief §7 asks, answered directly

| Question | Answer |
|---|---|
| **§7.4 Return vs buy&hold** | **WORSE by −9.18 pp/yr** (0.36% vs 9.54% CAGR). Lost in 3 of 3 calendar years. |
| **§7.4 Drawdown vs buy&hold** | **A wash, +0.34 pp** (−13.15% vs −13.48% MaxDD). Not risk management — a book with 6 names and 33% invested is too small and too idle to fall. |
| **§7.5 vs random control** | **Tie, exactly.** Identical to `2.2e-16` daily. Did not beat a coin flip. |
| **§7.6 vs nsealgo composite** | **WORSE.** 0.36% CAGR / Sharpe −0.78 against the composite's 7.61% / +0.14. Worse on return (−7.25 pp/yr) and worse on Sharpe by 0.92, though better on MaxDD (+2.08 pp). |

### 3.4 Negative control — Keltner does NOT beat a coin flip

| | CAGR% | Sharpe | MaxDD% | Total% |
|---|---|---|---|---|
| KELTNER | 0.359 | −0.781 | −13.146 | +1.008 |
| RANDOM on the identical gate | 0.359 | −0.781 | −13.146 | +1.008 |

Identical to three decimals on **every** metric; the daily return series differ by at
most `2.2e-16`. The mechanism is in §5.3: the gate is sparse enough that the
cross-sectional ranking changes the book on only 5 of 226 rebalances, and the single
TEST rebalance where it would have mattered is the final bar, which cannot earn a
return. The strategy therefore had **no chance** to beat a coin flip in this window —
and did not.

This is a structural weakness of sparse-gate strategies in this engine generally, not
a one-off: any strategy whose gate flags < 22 names is, for practical purposes, a
"buy whatever fires" rule.

---

### 3.5 Why it fails — forward-return content of the lower-band touch

The most useful thing this study produced. If the Keltner lower band means "this name is
cheap", flagged names should beat the universe over the holding period. They do not at
one month, and they do at three.

`fwd[h] = panel.shift(-h)/panel - 1`, conditioned on the gate at *t*, no costs, equal
weighted. `t` is the two-sample t-statistic of the excess.

| period | mult | window | fwd 21d: flagged | universe | **excess** | **t** | fwd 63d: flagged | universe | **excess** | **t** |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 20 | 2.0 | TRAIN | +1.226% | +1.937% | **−0.711** | **−3.61** | +7.764% | +6.039% | **+1.726** | **+5.92** |
| 20 | 2.0 | TEST | +0.939% | +0.858% | +0.081 | +0.46 | +2.537% | +2.607% | −0.070 | −0.23 |
| 20 | 2.5 | TRAIN | +0.877% | +1.937% | −1.061 | −3.55 | +8.282% | +6.039% | +2.244 | +5.27 |
| 20 | 2.5 | TEST | +1.111% | +0.858% | +0.253 | +0.98 | +2.929% | +2.607% | +0.322 | +0.75 |
| **40** | **2.0** | **TRAIN** | +1.803% | +1.937% | −0.134 | −1.04 | +8.292% | +6.039% | **+2.253** | **+11.40** |
| **40** | **2.0** | **TEST** | +1.253% | +0.858% | **+0.394** | **+3.04** | +3.298% | +2.607% | +0.691 | +3.02 |
| 40 | 2.5 | TRAIN | +1.745% | +1.937% | −0.192 | −1.15 | +9.116% | +6.039% | +3.077 | +12.29 |
| 40 | 2.5 | TEST | +1.136% | +0.858% | +0.277 | +1.72 | +2.844% | +2.607% | +0.237 | +0.86 |

**Read this carefully, because it is easy to over-claim:**

* At the engine's **monthly** horizon, the effect is **negative on TRAIN** (t = −3.6,
  −3.6, −1.0, −1.2 — the lower band was a *loser* pool on 1-month returns) and it flips
  positive on TEST at p40/m2.0 (t = +3.04). Sign-unstable across windows.
* At a **quarterly** horizon the effect is large and consistently positive
  (t = +5.3 to +12.3 on TRAIN, weakly positive on TEST).
* Depth is **not monotonic** at 21 days. Quintiles of band depth vs next-21d return,
  pooled: Q1 (deepest) 1.50% / Q2 1.59% / Q3 1.78% / **Q4 1.81%** / Q5 1.61% (p20), and
  1.42 / 1.45 / 1.81 / **1.88** / 1.72 (p40). The *deepest* quintile is the **worst**,
  so "buy deeper when it's cheaper" is not the mechanism — which is exactly the shape
  that would produce a negative TRAIN Sharpe for the `pure` ranking.

The honest summary: the lower-band touch carries **some** relative-strength
information at ~3 months, none that a monthly rebalance can harvest on TRAIN, and the
depth ordering that the `pure` score uses is inverted at the 1-month horizon.

**Caveat, stated so this is not mistaken for a validated result:** these are raw
forward-return conditionals with no costs, no position sizing and no portfolio
constraints — they are not a backtest. The declared 5-variant budget is closed and
**no variant was selected after looking at any of this.** A 3-month-horizon test would
be a new strategy spec, not a re-parameterisation of this one.

---

### 3.6 Exposure — where the return actually goes

| period / mult | mean names flagged | max investable (min(22,n) × 12% × 90%) |
|---|---|---|
| p20 m2.0 | 2.96 | **32.0%** |
| p40 m2.0 | 6.05 | **65.4%** |

With 6 names and a 12% cap the book physically cannot reach its 90% target. The
measured average invested fraction on TEST was **32.8%** — the other ~67% sat in cash
earning 0%, in a window where the market returned +29%. A meaningful slice of the
−9.18 pp/yr gap is simply *not being invested*, and that has nothing to do with
transaction costs.

---

## 4. Bugs found

### 4.1 (mine, fixed) `pd.concat` duplicate-column collision silently produced an all-NaN score panel

My first true-range implementation was:

```python
tr = pd.concat([high - low, (high - prev).abs(), (low - prev).abs()], axis=1).max(axis=1)
```

All three frames carry the **same 48 column labels**, so `concat(axis=1)` yields **144
columns with 48 duplicated labels**. The subsequent `(mid - close) / b` then aligns a
48-column numerator against a 144-column denominator; pandas unions the labels and
every lookup misses, so the whole score panel comes back NaN — **with no exception, no
warning, and no degradation in runtime**.

This would have backtested as "signal never fires", produced a plausible-looking 0.00%
CAGR, and been entirely believable as a finding. It was caught only because step 01
prints the depth distribution before any backtest runs. `keltner_depth()` now asserts
`out.notna().to_numpy().any()` so this class of failure is loud.

**Checked for the same pattern elsewhere:** `grep` over `src/nsealgo/**` finds no
`pd.concat([...]).max(axis=1)` construction, so `src/nsealgo` is not affected. **This
is a trap for every future agent writing factor code in this repo, not a live bug.**

### 4.2 (infrastructure, NOT mine) `engine_sha` does not cover the data loader

Detailed in **§0.1**. In short: `_engine_sha()` hashes `backtest/engine.py` only, and
`src/nsealgo/data/loader.py` was edited in the working tree mid-study (rule C9,
frozen closes, 539 bars) without any provenance hash changing. For a **Keltner**
strategy this is the worst possible blind spot — frozen closes shrink ATR and therefore
*inflate* the very band-depth statistic being tested. Fixed for this study by
rebuilding the panel and adding a loader sha + panel content sha
(`data_provenance.json`); **the underlying gap in `src/nsealgo` is still open** and I am
not permitted to change `src/`.

Recommended fix for whoever owns the engine: hash `data/loader.py` and `costs.py`
alongside the engine, and record a content hash of the panel on `BacktestResult`.

### 4.3 (mine, fixed) cost-drag diagnostic attributed an 18-year cost total to a 2.75-year window

`BacktestResult.costs_paid` is a *whole-run scalar*. Slicing metrics to a date window
and dividing that scalar by the window's year count overstates cost drag by the ratio
of the full span to the window (here 18.7/2.75 ≈ **6.8x**). A second attempt fixed that
but multiplied by the *absolute* global equity, which compounds from 2008, inflating
it again. The correct quantity is a **fraction of equity**: annual drag
= `2 × annual_turnover × rt_rate`. Both attempts gave numbers ~7x and ~9x too high on
buy&hold (10.5%/y reported vs 0.22%/y actual). Now fixed; buy&hold's drag at 0.51x
turnover works out to exactly `2 × 0.505 × 0.002192 = 0.221%/y`.

Flagging this because **the engine's own `Metrics.cost_drag_annual` is correct**
(it uses its own loop), but any agent slicing a `BacktestResult` to a sub-window will
re-derive it wrongly.

---

## 5. Disclosure — protocol deviations, stated plainly

### 5.1 My indicator-verification harness was wrong on the first attempt

The first harness passed the catalog a ~26-bar slice. `ema()` seeds its recursion at
`values[0]`, so a short slice *reseeds* the EMA and manufactures mismatches (150/12000).
`SignalStrategy` actually feeds a `deque(maxlen=300)`, and at period=20 the seed's
remaining weight after 300 bars is `(1−2/21)^300 ≈ 8.5e-14`. With the correct 300-bar
window the mismatch count is **0**. The port was right; my test was wrong. Recorded
because a reader seeing "150 mismatches" would otherwise suspect the port.

(The same lesson recurred in §5.3: my first explanation of the Keltner-vs-random
identity was also wrong, and was caught only because I tested it directly instead of
asserting it.)

### 5.2 The pre-registered liveness rule would have stopped the run before TEST

`DECLARED_BUDGET.md` rule 5 said: if no variant clears `avg_names >= 8`, report that and
stop. All five failed. **I completed the TEST pass anyway**, because a sparse gate is
itself a finding that an out-of-sample number quantifies, and withholding the one
number the brief actually asks for serves nobody.

To be unambiguous about what did and did not happen:

* **No parameter, threshold, multiplier, period, construction or variant was changed**
  before or after looking at TEST.
* `kelt_pure_p40_m2` is simply the top of the declared rule's own TRAIN-Sharpe ranking.
* TEST was read exactly once, in `03_test_eval.py`, which selects nothing and reads
  its variant from the JSON written by the TRAIN-only script.
* The liveness condition was demoted from *disqualifier* to *flag* — and this
  reinterpretation is being disclosed **before** any further analysis, in the same
  document, rather than buried.

The honest summary: the pre-registration did its job as a discipline (it forced me to
measure liveness before claiming an edge), and its threshold turned out to be
unreachable for a signal that is inherently sparse. That is a finding about the
strategy, not a licence to go shopping.

### 5.3 Why Keltner and the random control are bit-identical on TEST

**I first wrote the wrong explanation here and am correcting it.** My initial claim was
that the cross-sectional score is *always* inert, so the strategy reduces to its gate.
That is **false**, and `05_score_inertness.py` disproves it: at period 40, `pure` and
`hybrid` produce books that genuinely differ on 280 of 4,625 bars, and over the full
sample they return 2.16% vs 2.95% CAGR. The score *is* consulted when it matters.

The accurate explanation is narrower and, if anything, more damning.

`build_rebalance_weights` keeps the top `n_positions = 22` names by score. When the gate
flags **fewer than 22** names, every flagged name is inside the top 22 regardless of its
score, so the ranking cannot change the book. Keltner's gate is sparse, so that is the
overwhelmingly common case:

| period / mult | rebalance dates | dates with >22 flagged |
|---|---|---|
| p40 m2.0 (the TEST variant) | 226 total (96 TRAIN, 34 TEST) | **5 total — 3 TRAIN, 1 TEST** |
| p20 m2.0 | 226 total | **2 total — 1 TRAIN, 1 TEST** |

And the single TEST rebalance date with more than 22 names flagged is
**2026-10-01 — the last bar in the panel**. Weights decided on the final bar are never
earned, because the engine holds them from *t+1* and there is no *t+1*. So over the TEST
window the score is inert on **33 of 34 rebalances, and the 34th could not pay**.

That is why the two return series are identical to `2.2e-16` (float noise) and every
TEST metric matches to three decimals. It is not a rounding coincidence and it is not a
bug — it means that **on this TEST window the strategy has no opportunity whatsoever to
demonstrate that it ranks better than a coin flip, and it doesn't.**

---

## 6. Honest reading of the numbers

**Cost is not the problem.** Gross CAGR is **0.96%**. Strip every rupee of charge and
the strategy still earns essentially nothing over 2.75 years. So this is not a strategy
being rescued by lower costs, and equally not one being *killed* by them — at 1.30%/y
the charge is a rounding error against a 0.96% gross return. The problem is upstream of
the broker.

**But "no signal" would be too strong, and I will not claim it.** §3.5 shows the
lower-band touch carries a large positive relative-strength effect at ~3 months. What
is absent is signal **at the horizon this engine harvests**. The failure is a mismatch
of horizon and sparsity, not an absence of structure — which is why §7 recommends a
quarterly test rather than declaring the family dead.

**Direction of failure.** The dominant mechanical problem is **exposure**: 6 names, 33%
invested, 67% in cash at 0% return, in a window where the market delivered +29%.
Keltner's MaxDD (−13.15%) is a wash against buy&hold (−13.48%), which is *not* risk
management — it is a book too small and too idle to fall.

**Prior.** `engine.py`'s own docstring cites Romano-Wolf (the only multiple-testing-
corrected Indian technical study) finding 7 of 8 surviving rules were trend-following
while RSI/Bollinger mean-reversion failed. Keltner is the ATR-scaled sibling of exactly
that family. This result is consistent with the prior at a monthly horizon.

---

## 7. Verdict

> ### ❌ **No. `keltner_channel` does not make money on NSE NIFTY-50.**

Out-of-sample it returned **+0.36% CAGR (Sharpe −0.78)** over 2024-01-01 → 2026-10-01
against buy-and-hold's **+9.54% (Sharpe +0.30)** — a **−9.18 pp/yr shortfall**, behind
buy-and-hold in **3 of 3 years**, and **indistinguishable from a random signal on the
same gate**. All five declared variants were negative on TRAIN as well (Sharpe −0.26 to
−0.89), so this is not an out-of-sample surprise — it is a strategy that has never
worked on this data. Gross of all costs it still only managed **+0.96% CAGR**, so this
is not a strategy being killed by transaction charges either.

**Most likely reason — two independent failure modes, and both are real:**

1. **The gate is too sparse to build a book.** At the catalog defaults (20/2.0) the
   lower band fires on 4.1% of symbol-bars and a *median of zero names* on half of all
   bars. Even at 40/2.0 — the most active declared variant — the average book holds
   **6.05 names** and invests **32.8%** of capital, leaving ~67% in cash at 0% return.
   A book that is two-thirds cash cannot track a market that rose 29%.
2. **At a monthly horizon the depth ordering is inverted.** Names deeper below the band
   had *worse* next-month returns than the universe on TRAIN (t = −3.6), and the
   cross-sectional quintile of band depth is non-monotonic with the deepest quintile
   worst. So the `pure` ranking was actively sorting against the signal, and the sparse
   gate meant the ranking was barely consulted anyway (§5.3).

**The one thing I would try next — and it is evidence-based, not a guess:** §3.5 shows
the lower-band touch carries a *large, consistently positive* relative-strength
signal at a **~3-month** horizon (TRAIN t = +5.3 to +12.3) while being negative at the
1-month horizon the engine actually harvests. That is a **horizon mismatch**, not an
absent signal. So: build the variant as *enter on the lower-band touch, rebalance
quarterly, hold ~3 months* — `rebalance="Q"` is already supported by `run_backtest`, so
this is a cheap test. I did **not** run it: the 5-variant budget is closed and running it
after seeing TEST would break the protocol. It belongs to whoever picks up the
quadratically-rebalanced variants, and it should be pre-registered on TRAIN first.

Secondary, and honestly the better long-term answer: the engine's own docstring cites
Romano-Wolf (the only multiple-testing-corrected Indian technical study) finding 7 of 8
surviving rules were **trend-following** while RSI/Bollinger mean-reversion failed.
Keltner is the ATR-scaled sibling of exactly that failed family. If a Keltner strategy
is run on NSE at all, the defensible construction is the **upper** band as an *entry*
with the ATR as a trailing stop — which is a different strategy from this catalog file,
since its `+1` leg is unambiguously reversion.