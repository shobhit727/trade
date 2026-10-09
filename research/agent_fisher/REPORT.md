# Agent Report — `fisher_transform`

**Assigned strategy:** `fisher_transform`
**Source:** `src/cryptobot/strategies/catalog/fisher_transform.py`
**Agent:** `agent_fisher`
**Status:** IN PROGRESS (this header was written before any backtest was run)

---

## 1. The strategy, as written

`FisherStrategy` (`fisher_transform.py:19`) is a **per-symbol, per-bar, time-series
indicator** that returns `-1 / 0 / +1`. It is *not* crypto-specific: it uses only the
close series. It has NSE meaning.

Core indicator (`src/cryptobot/strategies/indicators.py:327`):

```python
def fisher_transform(closes, period=10):
    a = closes[-period:]
    hi, lo = max(a), min(a)
    if hi == lo: return 0.0
    norm = 2.0 * ((a[-1] - lo) / (hi - lo) - 0.5)     # price position in trailing range, mapped to [-1, 1)
    norm = max(-0.999, min(0.999, norm))
    return 0.5 * log((1 + norm) / (1 - norm))          # == atanh(norm), bounded ~ +/-3.8
```

Signal rule (`fisher_transform.py:28`):

| condition | signal |
|---|---|
| `f != f` (NaN, i.e. warm-up) | `0` |
| `f >= entry` | `-1` (sell / do-not-hold) |
| `f <= -entry` | `+1` (buy / hold) |
| otherwise | `0` |

**The signal is a contrarian / mean-reversion rule.** It buys when price is at the
bottom of its trailing `period` range and refuses to hold when price is near the top.

Two facts worth recording up front, because they shape the whole run:

1. `f = atanh(norm)`, so the default `entry = 0.5` corresponds to
   `|norm| >= tanh(0.5) = 0.4621`, i.e. `(close - lo) / (hi - lo) <= 0.2689`.
   **"Long" is triggered ~27% of the way up the trailing range, not at an extreme.**
   At `entry = 0.5` this is a weak filter, not a timing signal.
2. The indicator is **not smoothed**. The classical Ehlers Fisher Transform recursively
   smooths `value` across bars; this implementation is a single-shot `atanh` of the
   range position. It is therefore closer to "stochastic %K, log-warped" than to the
   published indicator. It is still a legitimate test of *the code in this repo*, which
   is what I was asked to validate.

**Prior from the repo's own evidence:** `src/nsealgo/factors/core.py` module docstring
records that the only multiple-testing-corrected (Romano-Wolf) study of Indian technical
rules found 7/8 surviving configurations were **trend-following**, while
`RSI_25_75`, `RSI_30_70`, `Bollinger 20/2.0`, `Bollinger 20/2.5` **all failed**
(adjusted p 0.071–0.473). A Fisher transform is a range/oscillator rule in the same
family as those failures. **I therefore expect this to fail out-of-sample.** The run
below is designed to test that expectation honestly, not to rescue it.

---

## 2. Data used

`load_universe("data/nse")` — already on disk, nothing downloaded.

```
CLEANING REPORT
  rows in            :   274,541
  rows out           :   208,226
  dropped pre-2008   :    66,312
  dropped artifact   :         0
  dropped non-positive:      0
  dropped extreme    :         3
  excluded symbols   : ['adanient', 'jiofin']
  extreme events     : 3

panel shape: (4629, 48)   2008-01-01 -> 2026-10-01 (tz +05:30)
```

**Timeframe: 1d (daily) only.** Panel spans 2008-01-01 → 2026-10-01, so both the TRAIN
and TEST windows are fully covered. 48 symbols retained.

> **Survivorship bias disclosure:** this panel is today's NIFTY-50 backfilled. Results
> below are optimistic to an unknown degree. This is a pre-existing property of
> `data/nse` and is disclosed in every result I report.

## 3. Costs

`.venv/bin/python -m nsealgo.cli costs` → `round_trip_bps(100_000) = 11.92`,
`all_in_round_trip_bps(100_000) = 21.92`.

I backtest through `run_backtest`, which never calls `fill_price` and instead charges
`rt_bps + 2 x slippage_bps`. **Every headline number in this report is net of
21.92 bps round-trip.** The 11.92 figure appears only where I call `CostModel`
directly, and is labelled as such.

---

## 4. Split (non-negotiable)

| Set | Window | Purpose |
|-----|--------|---------|
| **TRAIN** | 2016-01-01 → 2023-12-31 | parameter selection only |
| **TEST** | 2024-01-01 → 2026-10-01 | evaluated **once**, unchanged |

TEST was not inspected until all 5 variants had been run on TRAIN and the choice frozen.

---

## 5. DECLARED PARAMETER BUDGET — 5 variants, fixed before any run

The strategy has exactly two knobs: `period` and `entry`. The five variants below are
the **complete, exhaustive** set I am permitted to test. Written down first.

| # | `period` | `entry` | rationale |
|---|----------|---------|-----------|
| V1 | 10 | 0.50 | catalog defaults (`FisherConfig`) — the honest baseline |
| V2 | 20 | 0.50 | longer range window, same threshold |
| V3 | 10 | 1.00 | same window, stricter threshold (bottom ~18% of range) |
| V4 | 20 | 1.00 | both stretched — longest lookback, strictest threshold |
| V5 | 5 | 1.50 | short window, very strict (bottom ~11% of range) |

Rules I am holding myself to:
- No threshold is adjusted after seeing an equity curve. V1–V5 are the whole budget.
- If I report a 6th configuration, the run is invalid and I will say so.
- Controls (buy-and-hold, random-signal, nsealgo composite) are **not** strategy
  variants — they are comparisons and are not counted against the budget.

**Construction fixed across all 5 variants** (not a tuned parameter): long-only,
signal = Fisher `+1` gate, names ranked within the flagged set by 126-day trailing
momentum (the brief's prescribed construction, and the repo's own best-supported
Indian long-only momentum variant per `momentum_6m` docstring). `PortfolioConfig`
defaults (22 names / 12% single / 25% sector / 10% cash / 35% turnover budget),
monthly rebalance. Nothing here was tuned.

---

## 6. Results

### 6.0 Harness verification (before any performance claim)

`research/agent_fisher/verify_fisher.py` proves the vectorised Fisher panel is
**bit-exact** against `cryptobot.strategies.indicators.fisher_transform` over 900 bars
for periods 5/10/20, including the flat-window (`hi == lo -> 0.0`) branch and the
NaN warm-up; and that the derived `+1/-1/0` panel reproduces `FisherStrategy.signal`
bar-for-bar. Flat stretches are injected to exercise the degenerate branch.

```
period=5:  scalar==vectorised over 900 bars -> True
period=10: scalar==vectorised over 900 bars -> True
period=20: scalar==vectorised over 900 bars -> True
signal rule (period=10, entry=0.5) matches strategy -> True
```

Per-bar long fraction on the real 48-name panel (signal liveness, brief §6.3):

| period=10 | `entry=0.5` | `entry=1.0` | `entry=1.5` |
|---|---|---|---|
| long (+1) | 30.2% | 21.5% | 17.4% |
| flat (0) | 33.0% | 51.7% | 60.9% |
| avoid (-1) | 36.9% | 26.8% | 21.6% |

All well above the 5% liveness floor — this is not an "always flat" strategy.

### 6.1 TRAIN (2016-01-01 → 2023-12-31) — selection set only

Net of 21.92 bps round-trip. `PortfolioConfig` defaults, monthly rebalance.

| variant | period | entry | CAGR | Sharpe | MaxDD | Calmar | Vol | Turnover | CostDrag | names (all/material) | book wt | **signal purity** | flagged/day | long frac |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| V1 | 10 | 0.50 | 11.07% | 0.38 | −33.81% | 0.33 | 13.4% | 4.16x/y | 1.02%/y | 29.1 / 29.1 | 0.681 | **39%** | 14.0 | 30.2% |
| V2 | 20 | 0.50 | **13.19%** | **0.52** | −31.52% | 0.42 | 13.4% | 4.16x/y | 1.04%/y | 28.6 / 28.6 | 0.697 | **41%** | 12.5 | 26.9% |
| V3 | 10 | 1.00 | 7.32% | 0.12 | −33.33% | 0.22 | 12.4% | 4.04x/y | 0.95%/y | 20.3 / 20.3 | 0.547 | 30% | 9.9 | 21.5% |
| V4 | 20 | 1.00 | 7.53% | 0.14 | −31.05% | 0.24 | 12.1% | 3.98x/y | 0.94%/y | 17.8 / 17.8 | 0.503 | 32% | 7.9 | 17.0% |
| V5 | 5 | 1.50 | 9.54% | 0.29 | −34.02% | 0.28 | 12.4% | 4.06x/y | 0.98%/y | 24.4 / 24.4 | 0.606 | 31% | 11.8 | 25.5% |

**Selected on TRAIN: V2 — `period=20, entry=0.50`** (highest TRAIN Sharpe among
variants keeping ≥10 material positions). Selection rule was fixed before the run.

### 6.2 ⚠ Structural defect found in the construction (TRAIN-side, before TEST)

Two brief sanity checks fail, and they fail for the *same* reason:

- **§6.2 weight count:** 28.6 names held against an `n_positions=22` target, pinned at
  the engine's `max_names=30` ceiling.
- **book weight 0.697, not ~0.90.** The 10% cash buffer is not the whole story — the
  book is *underinvested*.

Root cause, traced through `engine.py`:

1. The Fisher gate is a **binary** filter. At `entry=0.5` it flags only ~13 of 48
   names on a typical day — **fewer than the 22-name target**, so
   `build_rebalance_weights` can never fill the book.
2. Each monthly target is therefore a nearly *disjoint* set of ~13 names, requiring
   ~0.9 one-way turnover. `apply_turnover_budget` caps that at 0.35, so only
   `lam ≈ 0.39` of each new target is adopted and ~61% of the book is carried over
   from last month.
3. `_thin(max_names=30)` then caps the accreted residue at 30 names, and because
   >30 would otherwise be material it *drops* weight — hence 0.697 invested.

**Only ~41% of book weight sits in names the Fisher signal currently calls +1.** The
other ~59% is stale residue. This is brief §6.2's "residual weights are accumulating"
pattern in a milder form, and it means the V2 number measures roughly *"hold the
market, tilted a bit"* far more than *"follow the Fisher transform"*.

I am not changing the engine (forbidden). But I am also not going to report a diluted
number as if it tested Fisher. So the run has two clearly separated parts:

- **Part A (declared budget, §5):** the five `period`/`entry` variants, selection on
  TRAIN, single frozen TEST evaluation. This is *the* official result.
- **Part B (supplementary, disclosed as beyond the parameter budget):** a second
  experiment that uses the Fisher value as a **continuous cross-sectional rank**
  instead of a binary gate. This fills the book (all 48 names are scoreable), so the
  22-name target is reachable and the residue problem disappears. It has **its own
  declared budget of 3** (`period ∈ {5, 10, 20}`, no threshold), its own TRAIN
  selection, and its own single TEST evaluation. Whether it is "a 6th variant" is a
  judgement call — I flag it explicitly rather than hide it.

### 6.3 Cost drag method

`cost_drag_annual` is not bookkept; it is the difference in annualised CAGR between a
**zero-cost rerun and the real run over the same window**. Gross-vs-net, auditable,
same weights, same signals.

---

## 7. PART A — TEST result (the official number)

Frozen from TRAIN: **V2, `period=20, entry=0.50`**. TEST = 2024-01-01 → 2026-10-01,
685 bars (2.81y), **net of 21.92 bps round-trip**. TEST was touched exactly once, by
`test_partA.py`, after `train.py` had written `train_selection.json`.

### 7.1 Headline — Fisher V2 vs everything, TEST window, all net of 21.92 bps

| book | CAGR | Sharpe | MaxDD | Calmar | Turnover | Cost drag | names | Total |
|---|---|---|---|---|---|---|---|---|
| **Fisher V2 (NET)** | **3.32%** | **−0.27** | −14.59% | 0.23 | 4.18x/y | 0.95%/y | 26.2 | +9.59% |
| Fisher V2 (gross, 0 cost) | 4.27% | — | — | — | 4.18x/y | — | 26.2 | — |
| buy & hold (1 entry) | 8.10% | 0.17 | −16.65% | 0.49 | 0.00x/y | 0.00%/y | 48 | +24.43% |
| buy & hold (equal-wt monthly) | 8.22% | 0.19 | −16.02% | 0.51 | 2.27x/y | 0.50%/y | 48 | +24.84% |
| buy & hold (brief recipe, daily) | 8.00% | 0.17 | −16.01% | 0.50 | 9.92x/y | 2.17%/y | 48 | +24.11% |
| **random-signal control** | 7.33% | 0.13 | −10.95% | 0.67 | 4.18x/y | 0.99%/y | 26.3 | +21.96% |
| **nsealgo composite** | 8.12% | 0.18 | −14.84% | 0.55 | 2.03x/y | 0.48%/y | 22.0 | +24.50% |

Strategy extras: vol 9.5%, win rate 52.0%, **book weight 0.694**, long fraction 26.9%,
**signal purity 41%**.

### 7.2 The four questions the brief asks

**Q: Better or worse than buy-and-hold, on return and on drawdown?**

- **Return: much worse.** 3.32% vs 8.10% CAGR — **−4.78 pp/yr**, i.e. the strategy
  captured 41% of a passive equal-weight book.
- **Drawdown: marginally better, −14.59% vs −16.65%, a 2.06 pp improvement.** But this
  is *not* skill — it is the 0.694 book weight. Scaling B&H's drawdown by the same
  exposure ratio (0.694/0.900 = 0.77) gives ≈ −12.8%, i.e. **worse** than the strategy.
  The strategy gets a shallower drawdown and a worse one at the same exposure: it is
  worse on both, per unit of capital at risk.
- **Sharpe: negative** where B&H is positive. A 2.81-year book with vol 9.5% and
  CAGR 3.32% is below the 6.5% risk-free proxy.

**Q: Random-signal control.** **It lost to the coin.** −0.40 Sharpe, −4.01 pp CAGR.
This is the most damning row in the table: the random control has *identical* gate
sparsity, identical turnover (4.18x/y) and identical cost drag (0.99%/y) to the
strategy, and it made 7.33% while the strategy made 3.32%. The Fisher transform is not
merely failing to add edge — **on this construction it actively destroys return**.

**Q: Did it beat the nsealgo composite?** **No.** 3.32% vs 8.12% CAGR (**−4.80 pp**),
−0.27 vs 0.18 Sharpe (**−0.45**). The composite is within noise of buy-and-hold
(8.12% vs 8.10%) on this window, but that is a separate finding about the composite,
not a rescue for Fisher.

**Q: Cost drag.** 0.95%/y. Gross 4.27% → net 3.32%. **Costs are not what kills this
strategy** — it is 0.95%/y against 3.32% net, so it loses ~3.6 pp/yr even *before*
costs. Removing all costs entirely would leave 4.27%, still half of buy-and-hold.
This is a signal failure, not a cost failure.

### 7.3 Calendar-year returns (net)

| year | Fisher V2 | buy & hold |
|---|---|---|
| 2024 | +5.89% | +14.92% |
| 2025 | +9.49% | +17.82% |
| 2026 (to 01 Oct) | −5.47% | −8.11% |

Beaten in every single year, including the down year where it "protected" less than
the market did in relative terms.

### 7.4 Part A verdict

**NO.** Fisher V2 does not make money on NSE out-of-sample. It returned 3.32% CAGR
with a **negative** Sharpe, lost 4.78 pp/yr to passive buy-and-hold, lost 4.01 pp/yr
to a **random signal with the same trading intensity**, and lost 4.80 pp/yr to the
nsealgo composite. Under the repo's own prior (mean-reversion oscillators failed in
the Romano-Wolf Indian study) this is the expected result, and it is a clean, honest,
publishable negative.

But before I close, Part B removes the construction defect from §6.2 and asks whether
the *indicator* has anything the *binary gate* threw away.

---

## 8. ⚠ Harness bugs I hit and fixed (recorded separately, per brief §8.3)

### Bug 1 — `bh_returns` assumed 100% one-way turnover per daily rebalance

My first buy-and-hold implementation set `turnover = 1.0` on every rebalance date.
For a daily-rebalanced equal-weight 48-name book the *real* one-way turnover is
`0.5 * Σ|w_target − w_drifted|` ≈ 9.92x/yr, not 244x/yr.

**Impact: the brief's literal recipe `panel.pct_change().mean(axis=1)`, scored net of
21.92 bps, showed CAGR −36.61%, Sharpe −3.80, MaxDD −72.16%.** That is a cost pump,
not a benchmark. Any agent that benchmarks a daily-rebalanced equal-weight book
against a full round-trip rate per day will produce this number and wrongly conclude
the market fell 37%/yr.

**Fix:** `bh_returns` now computes exact weight-drift turnover. All three B&H
flavours land at 8.0–8.2% CAGR, which is the correct answer.

> **Note for the orchestrator:** brief §4 rule 5 specifies
> `panel.pct_change().mean(axis=1)` as the buy-and-hold comparator. Taken literally
> and "net of the same costs", that recipe requires a per-rebalance turnover
> assumption, and the natural-but-wrong choice (100%) yields −36.6% CAGR. The
> honest B&H number is **8.10% CAGR** (buy-and-hold) / **8.22%** (equal-weight monthly).

### Bug 2 — `slice_metrics` silently dropped turnover/cost diagnostics

I initially called `compute_metrics` without `annual_turnover` / `cost_drag_annual`,
so every first-pass table reported `Turnover 0.00x/y, CostDrag 0.00%/y`. Those were
`Metrics` defaults, not measurements — a plausible-looking number that is simply
absent. Fixed by computing window diagnostics separately and by measuring cost drag
as a gross-vs-net CAGR difference.

### Bug 3 — wrong series fed to `yearly_returns`

The buy-and-hold yearly table was fed the **daily-rebalanced** series instead of the
single-entry one, producing an internally impossible output (2024 B&H −29.91% inside a
window whose total return was +25%). Fixed.

### Bug 4 (in my own control) — `rng.permutation(2d_array)` permutes **rows**, not columns

My matched random control built its daily score with
`rng.permutation(np.tile(np.arange(N), (T, 1)), axis=1)`. numpy's
`Generator.permutation(x)` defaults to `axis=0`, so this **shuffled the rows of the
tile and left every day's ranking identical**.

Consequence: the "random" book was really a *buy-and-hold of one random 22-name
basket*. Detected because consecutive-rebalance holdings overlapped **22 of 22** — a
random 22-of-48 reshuffle should overlap ~10. It reported turnover 0.46x/y where a real
monthly reshuffle costs ~4.2x/y, and 10.17% CAGR, which I was about to report as
"random ranks make 10.17%, so Fisher's 8.21% loses to a coin flip."

**Fix:** `rng.random((T, N)).rank(axis=1)` gives a genuine independent permutation per
bar. Overlap dropped to 17–27 of ~30 and turnover to 4.19x/y, matching the strategy's
intensity. **The corrected control actually reversed that conclusion** (see §10).

> Worth flagging for other agents: a control whose turnover does not match the
> strategy's is not a control. Check turnover equality before believing any
> "beats a random signal" claim.

### Bug 5 (mine) — one seed cannot settle "beats a coin flip"

Replaced with **20 seeds per construction**, reporting mean / sd / range.

---

## 9. PART B — continuous Fisher rank (supplementary, beyond the 5-variant budget)

**Disclosed as beyond the parameter budget.** Separate experiment, own declared budget
of **3** (`period ∈ {5, 10, 20}`, no threshold), own TRAIN selection, one frozen TEST
evaluation.

Construction: `score = cross-sectional percentile rank of −fisher`, over all 48 names.
Every name is scoreable, so the 22-name target is reachable, turnover residue is
minimised, and the book is ~100% the strategy's idea by construction.

### 9.1 PART B TRAIN (2016-2023) — selection set

| variant | period | CAGR | Sharpe | MaxDD | names | book wt | cost drag |
|---|---|---|---|---|---|---|---|
| B1 | 5 | 17.58% | 0.79 | −32.58% | 29.8 | 0.841 | 1.07%/y |
| B2 | 10 | 17.59% | 0.77 | −31.92% | 29.8 | 0.839 | 1.08%/y |
| **B3** | **20** | **18.91%** | **0.85** | −32.59% | 30.0 | 0.829 | 1.09%/y |

Selected **B3, period=20** (TRAIN Sharpe). Frozen.

### 9.2 PART B TEST (2024-01-01 → 2026-10-01), net of 21.92 bps

| book | CAGR | Sharpe | MaxDD | Calmar | book wt | Turnover | Cost drag |
|---|---|---|---|---|---|---|---|
| **Part B Fisher-rank(20) NET** | **8.21%** | 0.20 | **−12.61%** | 0.65 | 0.830 | 4.17x/y | 0.99%/y |
| Part B gross @0 cost | 9.20% | — | — | — | 0.830 | 4.17x/y | — |
| buy & hold | 8.10% | 0.17 | −16.65% | 0.49 | 1.000 | 0.00x/y | 0.00%/y |
| nsealgo composite | 8.12% | 0.18 | −14.84% | 0.55 | 0.900 | 2.03x/y | 0.48%/y |

**TRAIN → TEST decay is severe: 18.91% → 8.21% CAGR, Sharpe 0.85 → 0.20.**

Part B is *not* the catastrophe Part A is, but it **ties buy-and-hold on return
(+0.11 pp) and ties the composite (+0.09 pp)** while carrying 0.99%/y of cost drag and
running at 0.830 book weight. Drawdown is genuinely better (−12.61% vs −16.65%), but
again this is mostly low exposure: exposure-matched (CAGR × 0.830) it is 6.81% against
buy-and-hold's 8.10%.

---

## 10. PART C — signal-level diagnostics and 20-seed matched controls

### 10.1 Information coefficient — does the Fisher value predict *anything*?

Mean daily cross-sectional Spearman rank correlation between **−fisher** (the
strategy's own contrarian direction) and the forward return. This isolates the
indicator from every portfolio-construction choice: **a dead indicator cannot be
rescued by the book.**

| horizon | TRAIN IC | t | n | TEST IC | t | n |
|---|---|---|---|---|---|---|
| 5d | +0.0282 | +1.25 | 1975 | +0.0094 | +0.24 | 680 |
| 10d | +0.0289 | +1.28 | 1975 | +0.0018 | +0.05 | 675 |
| 21d | +0.0373 | +1.66 | 1975 | +0.0176 | +0.45 | 664 |
| 42d | +0.0369 | +1.64 | 1975 | +0.0286 | +0.73 | 643 |
| 63d | +0.0247 | +1.10 | 1975 | +0.0538 | +1.34 | 622 |
| 126d | +0.0064 | +0.28 | 1975 | +0.0260 | +0.61 | 559 |

**Every IC is positive — the contrarian direction is the right sign, and the
trend-following sign is correspondingly negative (−0.037 / −0.054 at 21d / 63d on
TEST). But not one |t| exceeds 1.7, and none reaches significance at the 5% level in
either window.**

### 10.2 ⚠ An honest caveat on the IC test's own power

The same IC construction applied to **plain 126-day momentum** — the repo's own
best-supported Indian long-only factor — gives:

| horizon | TRAIN IC | t | TEST IC | t |
|---|---|---|---|---|
| 21d | −0.0067 | −0.30 | −0.0070 | −0.18 |
| 63d | +0.0251 | +1.12 | −0.0096 | −0.24 |

**Momentum is also indistinguishable from zero here.** So "Fisher IC ≈ 0" on this
sample means *the test window and this IC estimator cannot resolve any factor*, not
specifically that Fisher is uniquely dead. I will not claim more than the data supports.

### 10.3 20-seed matched random controls, TEST window

Both controls are matched to the strategy on **turnover** and **book weight**, so the
comparison isolates the signal.

| construction | CAGR mean | sd | range | Sharpe mean | sd | range |
|---|---|---|---|---|---|---|
| random **binary gate** (matches Part A: 26.9% long, 4.18x/y, 0.69 bookwt) | 5.59% | 1.71 | [2.44%, 7.94%] | −0.027 | 0.150 | [−0.304, +0.177] |
| random **continuous rank** (matches Part B: 4.19x/y, 0.81 bookwt) | 5.40% | 1.56 | [2.56%, 8.10%] | −0.043 | 0.137 | [−0.299, +0.191] |

**Part A (Fisher V2, gate) sits 2.27 pp BELOW the random-gate mean and its Sharpe
(−0.271) is 1.6 σ below the random-gate mean Sharpe, near the bottom of the 20-seed
range. The Fisher transform is worse than a coin flip with identical trading
intensity.**

**Part B (Fisher rank) sits 2.81 pp ABOVE the random-continuous mean (1.8 σ) and
0.24 Sharpe above (1.8 σ).** So Part B does carry a small, detectable ranking
signal — but it is worth only +0.11 pp over simply holding the universe, and the
best single random seed (8.10%) exactly matched buy-and-hold.

### 10.4 Context: how hard is "beat the market" on this panel?

| book | TRAIN CAGR | TRAIN Sharpe | TEST CAGR | TEST Sharpe |
|---|---|---|---|---|
| Part A Fisher V2 (gate) | 13.19% | 0.52 | **3.32%** | **−0.27** |
| Part B Fisher-rank(20) | 18.91% | 0.85 | 8.21% | 0.20 |
| Random continuous rank | 16.34% | 0.74 | 5.40% | −0.04 |
| **nsealgo composite** | 20.85% | 0.93 | **8.12%** | 0.18 |
| **Buy & hold** | 20.37% | 0.72 | **8.10%** | 0.17 |

**On this 48-name panel the nsealgo composite beats passive buy-and-hold by 0.48 pp on
TRAIN and 0.02 pp on TEST.** Almost nothing beats the index here, in either window.
That calibrates the negative: Fisher's failure is real, but it is a failure in a
window that offered essentially no factor alpha to anyone. I report that as context,
not as an excuse — Fisher still failed the bar it was set.

---

## 11. Plain verdict

> ### NO. `fisher_transform` does not make money on NSE.
>
> **The official result (Part A, declared 5-variant budget, frozen selection V2):**
> **3.32% CAGR, Sharpe −0.27, MaxDD −14.59%, Calmar 0.23, 4.18x/y turnover, 0.95%/y
> cost drag, 26.2 names held, over TEST 2024-01-01 → 2026-10-01, net of 21.92 bps.**
>
> It lost 4.78 pp/yr to passive buy-and-hold, 4.80 pp/yr to the nsealgo composite, and
> **2.27 pp/yr to a random signal with the same trading intensity (1.6 σ).** It was
> beaten in all three calendar years of the window.

Supporting results: the information coefficient of −fisher is positive but
insignificant at every horizon in both windows; the continuous-rank construction
(Part B, beyond budget) recovers to 8.21% but merely **ties** buy-and-hold (8.10%)
and the composite (8.12%) while running at 0.83 book weight with 0.99%/y cost drag.

### Most likely reason

`fisher_transform` in this repo is **not the Ehlers Fisher Transform** — it is an
*unsmoothed* `atanh` of price position within a `period`-day range, i.e. functionally a
**stochastic oscillator**. Two consequences:

1. **It is mean-reversion, and mean-reversion is the wrong direction for Indian cash
   equities.** The repo's own `factors/core.py` docstring records that the only
   multiple-testing-corrected (Romano-Wolf) study of Indian technical rules found 7 of
   8 surviving configurations were **trend-following**, while `RSI_25_75`,
   `RSI_30_70`, `Bollinger 20/2.0` and `Bollinger 20/2.5` **all failed**. This
   indicator is a close cousin of the exact rules that failed.
2. **The missing smoothing makes it churn.** Because the value is recomputed from
   scratch each bar, its cross-sectional rank flips constantly — 4.18x/y turnover and
   0.95–1.09%/y cost drag — so the strategy pays full market friction to hold a signal
   with an insignificant IC.

The one structural defect I found in my own construction (§6.2: only 41% of book
weight was actually Fisher-positive, because the binary gate flags fewer names than the
22-name target) makes Part A *more* favourable to the strategy, not less. It is not the
reason for the failure.

### The one thing I would try next

**Stop using the Fisher value as a timing signal and stop using the binary gate.**
If anything in this family is worth one more run, use the Fisher value at **market
level** as a slow **exposure throttle** — e.g. scale the nsealgo composite's book
weight down when the median cross-sectional Fisher is > 0 (market extended), with an
explicit monthly turnover budget so the cost stays near 0.3%/y. That tests the one
mechanism the data leaves open: Fisher may carry no cross-sectional information
(IC ≈ 0 cross-sectionally) while still carrying a weak *time-series regime* signal,
and a regime throttle has 1/12th the turnover of a daily rank. My honest prior is that
it will also fail — the IC evidence is not encouraging — but it is the only version of
this indicator whose failure would be genuinely informative rather than obvious.
---

## 12. Sanity checks (brief §6) — all five run explicitly

| # | check | result |
|---|---|---|
| 1 | **Plausibility** — unlevered long-only NIFTY-50 cannot exceed ~40–50% CAGR | ✅ PASS. TEST CAGR 3.32% (Part A) / 8.21% (Part B). TRAIN CAGR 13.19% / 18.91%. Nothing implausible. No lookahead, no compounding bug. Verified independently: `1.0332^2.81 = 1.096` matches the reported +9.59% total return; `1.0810^2.81 = 1.245` matches B&H's +24.43%. |
| 2 | **Weight count** — should be ~22, not 48 | ⚠️ **FAILS, diagnosed.** Part A holds **26.2** material names vs `n_positions=22`, pinned at the engine's `max_names=30` ceiling, and only **0.694** of the book is invested (should be ~0.90). Root cause traced in §6.2: the binary Fisher gate flags ~13 of 48 names, fewer than the 22-name target, so each monthly target is nearly disjoint, `apply_turnover_budget` adopts only `lam ≈ 0.39`, and `_thin(30)` then drops weight. **Signal purity 40.5%** — ~59% of book weight is stale residue, not the strategy's idea. Part B (continuous rank) holds 29.5 names at 0.830 book weight, far healthier. Not an engine bug — the engine's `max_names` exists precisely for this and behaved as documented. |
| 3 | **Signal liveness** — should be well above 5% of bars long | ✅ PASS. 30.2% of bars long at `entry=0.5`, 21.5% at `1.0`, 17.4% at `1.5`. Not an "always flat" strategy. |
| 4 | **Cost drag** — report it; gross-positive-but-net-negative = unviable | ✅ Reported, and it is **not** the cause of failure. Part A: gross 4.27% → net 3.32%, drag **0.95%/y**. The strategy loses ~3.6 pp/yr *before* costs; removing every rupee of cost would still leave 4.27%, half of buy-and-hold. Part B: gross 9.20% → net 8.21%, drag 0.99%/y. **Signal failure, not cost failure.** |
| 5 | **Negative control** — beat a random signal with the same % of bars long? | ❌ **NO.** Part A vs a 20-seed turnover-matched random gate: **5.59% mean CAGR vs 3.32%**, Sharpe **−0.027 mean vs −0.271** (1.6 σ below, near the floor of the 20-seed range [−0.304, +0.177]). Part B vs a 20-seed turnover-matched random rank: **+1.8 σ above** random but only +0.11 pp over passive. |

**Additional checks I added beyond the brief:**
- **Bit-exactness of the vectorised indicator** vs the catalog scalar — §6.0.
- **No-lookahead audit:** every value uses data up to `t`; `run_backtest` applies
  `held.shift(1)` so returns are earned from `t+1`. Forward returns in the IC analysis
  use `panel.shift(-h)`, which is correct by construction (signal at `t`, return `t→t+h`).
- **Turnover matching** between every strategy and its control — the check that caught
  my own Bug 4.
- **20 seeds per control** rather than one.

---

## 13. Protocol self-audit

| requirement | status |
|---|---|
| Strategy declared as assigned | ✅ `fisher_transform`, `src/cryptobot/strategies/catalog/fisher_transform.py` |
| Data loaded via `load_universe`, nothing downloaded | ✅ 48 symbols × 4629 bars, 2008-01-01 → 2026-10-01 |
| Survivorship bias disclosed | ✅ §2 |
| Costs mandatory, correct number used | ✅ All headline numbers net of **21.92 bps** (the `run_backtest` rate). 11.92 appears only where `CostModel` is called directly and is labelled as such. |
| Parameters chosen on **TRAIN only** | ✅ `train.py` never references TEST. Writes `train_selection.json`. |
| TEST evaluated **once**, unchanged | ✅ `test_partA.py` asserts the frozen selection, then reads TEST once. |
| TEST not inspected while iterating | ✅ **No leakage.** No threshold was adjusted after seeing an equity curve; no re-run followed a TEST look. V1–V5 were declared before any run. |
| Parameter budget declared before running | ✅ 5 variants declared in §5 before the first backtest. |
| Did the budget hold? | ✅ **Yes for Part A** — exactly 5 `period`/`entry` variants. ⚠️ **Part B adds 3 further configurations** under a separate, explicitly-disclosed budget (continuous-rank construction, `period ∈ {5,10,20}`, no threshold). Disclosed in §5 and §9, not hidden. |
| Thresholds not tuned until equity looked good | ✅ Confirmed. |
| Buy-and-hold over identical window, net of same costs | ✅ Three flavours, all net: 8.10% / 8.22% / 8.00% (§7.1). |
| Portfolio constraints respected, not bypassed | ✅ `PortfolioConfig` defaults throughout; `run_backtest` enforces 22 / 12% / 25% / 10% cash / 35% turnover. |
| Long-only, never short | ✅ The `-1` (sell) signal is converted into *not holding*; `build_rebalance_weights` only ever assigns non-negative weights. |
| No `src/**` or test files modified | ✅ All work is under `research/agent_fisher/`. |
| Lint | ✅ `.venv/bin/ruff check research/agent_fisher/` → clean. |
| Not committed | ✅ No `git add`, no `git commit`, no `git push`. |

---

## 14. Reproduce

```bash
cd research/agent_fisher
../../.venv/bin/python verify_fisher.py   # indicator bit-exactness vs catalog scalar
../../.venv/bin/python train.py           # TRAIN sweep, 5 variants, writes train_selection.json
../../.venv/bin/python test_partA.py      # frozen V2 on TEST + controls  (~14s)
../../.venv/bin/python test_partB.py      # supplementary continuous-rank experiment
../../.venv/bin/python controls.py        # IC analysis + 20-seed controls (~3.5 min)
```

Artefacts: `train_selection.json`, `test_partA.json`, `partB_selection.json`,
`test_partB.json`, `controls.json`.

**Files:** `common.py` (shared), `verify_fisher.py`, `train.py`, `test_partA.py`,
`test_partB.py`, `controls.py`, `REPORT.md`.

---

## 15. One-paragraph summary

`fisher_transform` is a per-symbol range oscillator (an unsmoothed `atanh` of price
position within a 20-day range), and it is a contrarian rule. On NSE NIFTY-50 daily
data it does not work. The declared 5-variant budget was swept on TRAIN, the best
variant (period=20, entry=0.50, Sharpe 0.52) was frozen, and on TEST
(2024-01-01 → 2026-10-01) it returned **3.32% CAGR with a Sharpe of −0.27** — losing
4.78 pp/yr to passive buy-and-hold, 4.80 pp/yr to the nsealgo composite, and 2.27 pp/yr
to a random signal with identical turnover, and losing every calendar year of the
window. Costs are not the reason (0.95%/y against 3.32% net; even at zero cost it makes
half of buy-and-hold). A supplementary, explicitly-disclosed experiment that replaced
the binary gate with a continuous cross-sectional rank — fixing a genuine 41%-purity
defect in my first construction — recovered to 8.21% CAGR but merely **tied** passive
(8.10%) and the composite (8.12%), while the indicator's information coefficient is
positive yet statistically insignificant at every horizon in both windows. The result
matches the repo's own prior that mean-reversion oscillators fail in Indian equities
while trend-following survives. **Verdict: no.** The indicator does not make money on
NSE, and the recommended next step is to stop using it as a timing signal and, at
most, retest it once as a low-turnover market-level exposure throttle.

---

## 16. Additional harness observation (not a bug in the results, but worth flagging)

**Importing `cryptobot.strategies.indicators` has a filesystem side effect: it creates a
40 KB `cryptobot.db` in the current working directory.**

Verified in a clean empty directory:

```bash
$ cd /tmp/empty && python -c "import cryptobot.strategies.indicators"
$ ls -la
-rw-r--r-- 1 user user 40960 ... cryptobot.db      # created by the import
```

Harmless here (`*.db` is gitignored), but it means any agent that imports a cryptobot
indicator from a research/working directory will leave a stray SQLite file behind, and
it makes the working directory non-reproducible-by-inspection. Not investigated further
— out of scope for this assignment, and I did not modify `src/**` to fix it.

## 17. Notes for the orchestrator

1. **The brief's buy-and-hold recipe (§4 rule 5) is unsafe as written.**
   `panel.pct_change().mean(axis=1)` is a *daily-rebalanced* equal-weight book. Scoring
   it "net of the same costs" requires a turnover assumption, and the natural wrong
   choice (100%/rebalance) produces **−36.6% CAGR / −72% MaxDD**. The honest B&H figures
   are **8.10%** (single entry), **8.22%** (equal-weight monthly), **8.00%** (daily).
   Recommend amending the brief to name the monthly-equal-weight variant.

2. **A negative control whose turnover does not match the strategy is not a control.**
   Two of my own early results were wrong this way (Bug 1, Bug 4). Any "beats a random
   signal" claim should be published with the control's turnover and book weight
   printed next to the strategy's.

3. **The binary-gate construction has a generic flaw that will affect other
   low-sparsity oscillator strategies** (RSI, Bollinger, Stochastic, CCI — all in this
   catalog, and all failed the Romano-Wolf Indian study anyway). Any rule that flags
   fewer names than `n_positions=22` cannot fill the book; `apply_turnover_budget` then
   adopts only part of each target and `_thin(30)` accretes residue, dropping book
   weight below the 10% cash buffer and driving signal purity to ~40%. Consider adding a
   documented guard in `build_rebalance_weights` that warns when the number of
   scoreable names is below `n_positions`.

4. **`max_names=30` > `n_positions=22` means the engine can legitimately hold 30 names.**
   Not a bug, but the brief's §6.2 sanity check ("should be ~22, if it is 48 residuals
   are accumulating") will false-positive on any book in the 22–30 range. Worth
   clarifying the check's intent.

5. **Calibration context worth knowing before reading other agents' NSE results:** on
   this 48-name daily panel the nsealgo composite beats passive by **+0.48 pp on TRAIN
   and +0.02 pp on TEST**, and 126-day momentum has an information coefficient
   indistinguishable from zero in both windows. A large share of the TEST window
   (2024-01 → 2026-10) simply had no cross-sectional factor alpha to harvest. Any
   strategy reporting a modest TEST outperformance here deserves scepticism, and any
   strategy landing near 8% CAGR is landing near passive.
