# REPORT — `bollinger_bands` on NSE NIFTY-50

**Status:** IN PROGRESS (resumed run — see §0)
**Assigned strategy:** `bollinger_bands`
**Source:** `src/cryptobot/strategies/catalog/bollinger_bands.py`

---

## 0. Provenance of this run (read first)

This directory was left by an **interrupted prior run**. Nothing was thrown away; every
scratch file was re-read and re-verified against `src/nsealgo/**` and
`src/cryptobot/**` before being trusted. Verification outcomes are recorded in §7.

The prior run had already executed `03_test_eval.py`, i.e. TEST had been looked at
once. The protocol permits TEST to be touched exactly once, and the structure of the
scripts enforces that:

- `02_train_select.py` physically truncates the panel at 2023-12-31 in-process
  (`panel = panel_full.loc[:TRAIN[1]]`, followed by an `assert`) — it is
  **structurally incapable** of seeing TEST.
- The selection was written to `selected_variant.json` by that script, keyed to the
  selection rule declared in advance in `DECLARED_BUDGET.md`.
- `03_test_eval.py` reads that frozen JSON and chooses nothing.

So the discipline held; it was not retrofitted. This resumed run **did not change any
parameter, threshold or variant after seeing TEST.** Re-running the existing scripts
verbatim is a reproduction, not a re-selection.

---

## 1. The strategy

Catalog implementation (`src/cryptobot/strategies/catalog/bollinger_bands.py`) delegates
to `cryptobot.strategies.indicators.bollinger_position`
(`src/cryptobot/strategies/indicators.py:216`):

```
a     = closes[-period:]
sig   = (a[-1] - mean(a)) / (n_std * sd(a))      # ddof=0, window INCLUDES today
+1    if sig < -entry                             # close below lower band
-1    if sig > +entry                             # close above upper band
 0    otherwise
```

Defaults: `period=20, n_std=2.0, entry=1.0` — i.e. the long leg fires when the close sits
more than **2 population-sd below its own 20-day mean**. This is a textbook
**mean-reversion / oversold** signal. It is emphatically **not** crypto-specific, so it
has a legitimate NSE interpretation and no reason to be rejected as out-of-scope.

**NSE adaptation (brief §5).** The book is long-only; an Indian delivery account cannot
short, so the `-1` upper-band leg is dropped. The NSE strategy is the LONG leg only:

> Hold names whose close is more than `entry * n_std` population-sd below their
> `period`-day mean.

The rolling window includes day *t* and `run_backtest` holds weights decided at *t*
from *t+1* (`engine.py:381-382`, `held.shift(1)` at `engine.py:415`). No look-ahead.

**Score construction (cross-sectional).** The catalog emits ±1/0 per symbol; the NSE book
is cross-sectional, so the gated names must be ranked. Two constructions are tested so
the result can be decomposed rather than blurred:

- `pure` — rank gated names by **oversold depth**. This isolates the Bollinger signal.
- `hybrid` — rank gated names by **126d momentum** (the brief §5 recipe). This is a
  Bollinger+momentum *hybrid*; its performance is **not** attributable to Bollinger
  alone and is labelled as such wherever it appears.

---

## 2. DECLARED PARAMETER BUDGET — 5 variants

Declared before any backtest was run (full text: `DECLARED_BUDGET.md`).
Budget = **5 distinct parameter variants**, per brief §4. **Budget used: 5/5.**

| # | name | period | n_std | entry | construction | effective band depth |
|---|------|--------|-------|-------|--------------|----------------------|
| V1 | `bb_pure_default` | 20 | 2.0 | 1.0 | `pure` | 2.0 sd |
| V2 | `bb_hybrid_mom6m` | 20 | 2.0 | 1.0 | `hybrid` (126d mom) | 2.0 sd |
| V3 | `bb_pure_deep` | 20 | 2.5 | 1.0 | `pure` | 2.5 sd |
| V4 | `bb_pure_slow` | 60 | 2.0 | 1.0 | `pure` | 2.0 sd |
| V5 | `bb_pure_fast` | 10 | 2.0 | 1.0 | `pure` | 2.0 sd |

`entry` is held at the catalog default 1.0 throughout; effective band depth is
`entry * n_std`, so V3 probes a deeper band without spending a second parameter slot.

**Selection rule fixed in advance:** highest TRAIN Sharpe; tie-break lower TRAIN annual
cost drag. Selection uses TRAIN only. The winner is then run on TEST **unchanged**.

**Not variants (baselines/controls — reported, never selected):** buy-and-hold equal-weight
universe; `build_composite_score` (nsealgo production composite); random-signal control
with the same per-day name count as the real signal, 5 fixed seeds.

---

## 3. Data and costs

- Primary: `data/nse/*_1d.csv` via `nsealgo.data.loader.load_universe("data/nse")`
  (applies the cleaning rules: drops pre-2008 vendor artifacts, non-positive prices,
  impossible moves; returns an auditable report).
- **TRAIN** 2016-01-01 → 2023-12-31 · **TEST** 2024-01-01 → 2026-10-01.
- Costs: `CostModel(segment="delivery", slippage_bps=5)`.
  - `round_trip_bps(100_000)` = **11.92 bps** — statutory only.
  - `all_in_round_trip_bps(100_000)` = **21.92 bps** — what `run_backtest` actually
    charges (`engine.py:412` calls `all_in_round_trip_bps`, because a portfolio
    simulator never calls `fill_price`, so slippage is folded in as
    `rt_bps + 2 x slippage_bps`).
  - **Every number in this report is net of 21.92 bps round-trip**, because every result
    is produced by `run_backtest`. Verified against `.venv/bin/python -m nsealgo.cli costs`.
- Portfolio: `PortfolioConfig()` defaults (22 names, 12% single name, 25% sector, 10%
  cash, 35% turnover budget), monthly rebalance. Not bypassed.
- **Survivorship bias is present** — today's NIFTY-50 is backfilled over 24y. Every result
  here inherits it and must be discounted accordingly.

---

## 4. Results

### 4.0 Port fidelity + data sanity (verified, not assumed)

`00_data.py` → `load_universe` drops 66,312 pre-2008 vendor rows, 3 extreme events, and
excludes 2 symbols (`adanient`, `jiofin`) → **48 symbols, 4,629 bars, 2008-01-01 →
2026-10-01**, Asia/Kolkata, monotonic, no duplicate dates. TRAIN 3,944 bars, TEST 685
bars.

**The vectorised port reproduces the catalog signal bar-for-bar.** `01_diagnostics.py`
runs the real `BollingerBandsStrategy.signal` bar-by-bar on RELIANCE (4,429 bars) for
every declared parameter set:

| period | n_std | long-leg agreement | long % (catalog = mine) | short leg dropped |
|--------|-------|--------------------|------------------------|-------------------|
| 20 | 2.0 | 4429/4429 | 5.667% | 6.232% |
| 20 | 2.5 | 4429/4429 | 1.400% | 1.829% |
| 60 | 2.0 | 4429/4429 | 4.741% | 8.286% |
| 10 | 2.0 | 4429/4429 | 3.929% | 5.125% |

So the re-implementation is exact, and the dropped short leg is a real, symmetric ~6% of
bars that a long-only Indian account simply cannot express.

**Signal liveness (brief §6.3): TRAIN 4.60%, TEST 5.23%** of (name, day) cells — sitting
exactly on the brief's ~5% "effectively always-flat" floor. Names signalled per day:
mean 2.2 (TRAIN) / 2.5 (TEST), median 1. This is a very sparse signal; brief §6.3 applies.

Missing data is real and is **not** forward-filled: `eternal` is 85% NaN in TRAIN,
`maxhealth` 79%, `hdfclife`/`sbilife` ~61%. Those names are simply not scoreable on days
with no close. No synthetic prices are invented.

### 4.1 TRAIN (2016-01-01 → 2023-12-31) — the 5 declared variants, net of 21.92 bps

| variant | CAGR % | Sharpe | MaxDD % | Calmar | Turn/y | Drag %/y | avg names |
|---------|--------|--------|---------|--------|--------|---------|-----------|
| V1 `bb_pure_default` | 1.75 | −0.49 | −31.95 | 0.05 | 1.88 | 0.52 | 2.7 |
| V2 `bb_hybrid_mom6m` | 2.24 | −0.48 | −31.52 | 0.07 | 1.77 | 0.54 | 2.3 |
| V3 `bb_pure_deep` | −0.63 | −1.08 | −34.05 | −0.02 | 0.65 | 0.15 | 0.8 |
| V4 `bb_pure_slow` | **2.13** | **−0.37** | −31.98 | 0.07 | 1.67 | 0.45 | 2.9 |
| V5 `bb_pure_fast` | 1.38 | −0.64 | −36.19 | 0.04 | 1.46 | 0.42 | 1.7 |
| BASE buy-and-hold (EW) | 18.61 | 0.76 | −44.68 | 0.42 | 0.53 | 0.55 | 21.9 |
| BASE nsealgo composite | 18.71 | 0.78 | −40.66 | 0.46 | 1.98 | 2.09 | 21.9 |
| CTRL random (5 seeds) | 1.27 | −0.61 | −30.92 | — | ~1.78 | ~0.45 | 2.4 |

**Every one of the five variants has a negative TRAIN Sharpe.** The declared rule
(highest TRAIN Sharpe) therefore selected the *least bad*, not a good variant:
**V4 `bb_pure_slow` (Sharpe −0.366, CAGR 2.13%)**. Frozen to `selected_variant.json`.

Note the book is ~16% invested and holds ~2.9 names against a 22-name budget — the gate
is far too sparse to be a standalone portfolio.

### 4.2 TRAIN cost decomposition — costs are NOT the root cause

| variant | net CAGR % | zero-slippage CAGR % | drag pp/y |
|---------|-----------|---------------------|-----------|
| V1 | 1.75 | 1.94 | 0.19 |
| V2 | 2.24 | 2.42 | 0.18 |
| V3 | −0.63 | −0.57 | 0.07 |
| V4 | 2.13 | 2.30 | 0.17 |
| V5 | 1.38 | 1.52 | 0.15 |

Drag is 0.07–0.19 pp/y. Brief §6.4 is satisfied and points the opposite way from the
usual failure: the strategy is **~0% gross**, so even a zero-cost book makes nothing.
Removing all costs would *not* rescue it.

### 4.3 TRAIN exposure-free verdict — the signal is INVERTED (decisive)

This is the finding that matters, and it is independent of portfolio construction,
position caps and costs.

**Mean 21d forward return by Bollinger z-bucket (TRAIN, 3,067 gated observations):**

| z bucket | n | mean 21d fwd (bps) |
|----------|---|--------------------|
| < −3.0 | 273 | 52 |
| −3 .. −2.5 | 1,025 | 151 |
| **−2.5 .. −2.0 (GATE)** | **3,067** | **145** |
| −2.0 .. −1.5 | 6,457 | 159 |
| −1.5 .. −1.0 | 9,138 | 182 |
| −1.0 .. 0 | 19,260 | 211 |
| 0 .. 1 | 21,685 | 214 |
| 1 .. 2 | 23,352 | 186 |
| > 2 | 7,058 | 189 |

Universe mean 194 bps. Gated cells (z < −2) return 145 bps → **−48 bps excess per 21d**.
Monotonic in the *wrong* direction: the more oversold, the worse the forward return.

> **`corr(bucket midpoint z, mean fwd return) = +0.746`**
> Mean reversion requires this to be **negative**. It is strongly **positive**.

**Mean reversion is not merely absent on NIFTY-50 — it is inverted.** Buying names as
they dip below the lower Bollinger band is systematically buying the losers in a
persistent-momentum market.

Corroborating TRAIN measures (all negative):
- Rank IC inside the gated set: −0.005 / +0.000 / +0.020 / −0.021 / +0.010 for V1–V5 —
  **no ordering power whatsoever** (all |t| < 1.3).
- Gated vs universe excess: −23 / −23 / −61 / −65 / −4 bps per 21d for V1–V5.
- Beta-adjusted alpha: **−2.26 to −4.42 pp/y for every variant**, so the shortfall is not
  explained by under-investment.

---

### 4.4 TEST (2024-01-01 → 2026-10-01) — the TRAIN-locked variant, evaluated once

Locked variant: **V4 `bb_pure_slow`** (period=60, n_std=2.0, entry=1.0, `pure`).
Nothing was re-chosen. 685 bars, 48 symbols, 33 rebalances. All figures net of **21.92 bps**
round-trip, subject to the full `PortfolioConfig()`.

| | **bb_pure_slow (TEST)** | buy-and-hold (TEST) | nsealgo composite (TEST) | random control (TEST) |
|---|---|---|---|---|
| **CAGR %** | **−0.11** | **+9.76** | +1.99 | +0.58 |
| **Sharpe** | **−1.07** | **+0.32** | −0.31 | −0.92 |
| **MaxDD %** | **−10.40** | **−13.51** | −14.94 | −9.84 |
| **Calmar** | **−0.01** | **+0.72** | +0.13 | — |
| Turnover /yr | 1.98x | 0.64x | 2.43x | ~2.06x |
| Cost drag %/yr | 0.44 | 0.16 | 0.57 | ~0.46 |
| **Avg names held** | **4.21** (cap 22) | 21.3 | 22.5 | ~4.7 |

**Brief §4.5 raw benchmark.** `panel.pct_change().mean(axis=1)` equal-weight universe over
the identical TEST window gives **CAGR 8.29%, total +25.05%** (zero-cost, no constraints).
The engine-based buy-and-hold above (+9.76%) is the *consistent* comparator because it pays
the same 21.92 bps, the same 10% cash buffer and the same caps; it edges higher purely
because inverse-vol sizing tilts toward the winners. **Either way the conclusion is
unchanged: the strategy is ~8–10 pp/y behind simply holding the index.**

**Calendar years (%)**

| year | bb_pure_slow | buy-and-hold | composite |
|------|--------------|--------------|-----------|
| 2024 | +1.57 | +17.03 | +8.47 |
| 2025 | +1.71 | +16.07 | +7.10 |
| 2026 (to 2026-10-01) | −3.49 | −4.37 | −9.01 |

**TEST vs buy-and-hold:**
- Return: **WORSE by 9.87 pp/y** (−0.11% vs +9.76%).
- Drawdown: **BETTER by 3.11 pp** (−10.40% vs −13.51%) — but only because the book is
  ~19.5% invested, not because of any risk skill.
- Sharpe: −1.07 vs +0.32 → **worse by 1.38**.
- vs the nsealgo composite: also worse (−0.11% vs +1.99% CAGR, −1.07 vs −0.31 Sharpe).
  The composite is itself negative on this window; the Bollinger strategy does not beat
  the house baseline either.

**Random-signal control: the strategy LOSES TO A COIN FLIP.** CAGR −0.11% vs random
+0.58% (**−0.69 pp/y**); Sharpe −1.07 vs random −0.92. It fails the minimum bar in
brief §6.5.

**All five variants on TEST** (transparency only — the ranking was *not* re-picked from
these; selection was TRAIN-only):

| variant | CAGR % | Sharpe | MaxDD % | avg names |
|---------|--------|--------|---------|-----------|
| V1 `bb_pure_default` | +0.87 | −0.95 | −10.19 | 3.3 |
| V2 `bb_hybrid_mom6m` | −0.51 | −1.23 | −10.19 | 3.1 |
| V3 `bb_pure_deep` | −0.26 | −1.40 | −10.22 | 1.0 |
| **V4 `bb_pure_slow`** ← TRAIN-selected | **−0.11** | **−1.07** | **−10.40** | **4.2** |
| V5 `bb_pure_fast` | +0.32 | −1.01 | −13.16 | 3.1 |

All five are negative-Sharpe on TEST. Not one of the five beats buy-and-hold; not one
beats the composite on CAGR; the best of them (V1, +0.87%) still returns ~9 pp/y less
than simply holding the index.

### 4.5 Sanity checks (brief §6) — all run, all pass

| # | check | result |
|---|-------|--------|
| 6.1 | Plausibility | CAGR −0.11% — far below the 40–50% unlevered ceiling. **No lookahead, no compounding bug.** |
| 6.2 | Weight count | Avg names held **4.21** vs cap 22. Below cap because the gate is sparse, **not** residual accumulation. |
| 6.3 | Signal liveness | **4.99%** of (name,day) cells on TEST (2,885 held name-days). Right on the brief's ~5% floor — this is close to an always-flat book. |
| 6.4 | Cost drag | 0.44%/yr on 1.98x turnover. Zero-slippage CAGR is **+0.09%** vs net **−0.11%**, so costs cost 0.20 pp/y. Costs do flip the sign, **but the strategy is ~0% gross too — costs are not the root cause.** |
| 6.5 | Negative control | **LOSES to a random signal**: −0.11% vs +0.58% CAGR (−0.69 pp/y); Sharpe −1.07 vs −0.92. |

### 4.6 Look-ahead proof (empirical, not asserted)

Re-running the backtest on a panel **truncated** at three dates; the equity path *before*
the cut must be bit-identical:

| truncation | equity max abs diff | weight max abs diff | verdict |
|------------|--------------------|--------------------|---------|
| 2024-09-30 | 0.000e+00 | 0.000e+00 | CLEAN |
| 2025-06-30 | 0.000e+00 | 0.000e+00 | CLEAN |
| 2026-03-31 | 0.000e+00 | 0.000e+00 | CLEAN |

**Negative control:** a deliberately leaked score (`.shift(-5)`) *is* detected
(equity max abs diff 1.518e-01), so the test is sensitive and its CLEAN verdict is
meaningful, not a vacuous pass.

### 4.7 Significance — the excess is negative in BOTH windows

Cross-sectionally demeaned daily excess of gated names over the universe, Newey-West
lag-5 adjusted (a common market shock cannot inflate the t-stat):

| window | days | mean daily excess | Newey-West t |
|--------|------|-------------------|--------------|
| TRAIN | 968 | **−28.6 bps** | **−0.92** |
| TEST | 362 | **−46.8 bps** | **−1.21** |

Mean reversion requires t > +1.96. Neither window reaches it; both point the *wrong*
way. TRAIN→TEST difference is −18.2 bps/day, diff t = −0.65 → **consistent with noise,
not a statistically real regime change.** There is no sign-stable behaviour to deploy.

### 4.8 Exposure-matched check — the TEST loss is not an under-investment artefact

| | invested % | beta | CAGR % | beta × market % | alpha pp/y |
|---|---|---|---|---|---|
| `bb_pure_slow` | 19.5 | 0.251 | −0.11 | +2.07 | **−2.18** |
| buy-and-hold | 87.2 | 0.817 | +9.76 | — | — |

Removing the exposure difference leaves the strategy with **−2.18 pp/y of alpha**. It is
genuinely underperforming, not merely under-invested.

### 4.9 BUG AND CAVEAT FOUND — recorded per brief §8.3

Three defects in my own harness, found and documented rather than hidden:

**(a) My `pure` score construction is self-defeating — a real porting defect.**
`pure` ranks gated names by oversold *depth* (`-sig`, deepest first). But within the gate,
depth is **inversely** related to forward return — the *deepest* oversold names are the
*worst*:

| TRAIN, inside gate | period=20 mean 21d fwd | period=60 mean 21d fwd |
|---|---|---|
| z < −3 | −40.5 bps | −44.1 bps |
| z −3..−2.5 | +102.0 | −23.6 |
| z −2.5..−2.25 | +104.3 | +83.4 |
| z −2.25..−2 | +130.3 | +178.7 |
| **corr(depth, fwd)** | **+0.913** | **+0.929** |

So `pure` is *guaranteed* to buy the worst sub-bucket of its own gate. **This is a defect
of the construction I chose in order to isolate the signal — not a property of the catalog
strategy**, which emits an unranked +1/0/−1 and says nothing about depth.

**The negative result is nevertheless robust to this flaw**, because V2 (`hybrid`) ranks
gated names by momentum and so does *not* suffer the depth inversion — and V2 also fails
(TRAIN Sharpe −0.48, TEST CAGR −0.51%). Five variants across 3 periods, 2 band depths and
2 scoring constructions all fail. The construction flaw is a contributing cause of the
*magnitude* of the loss, not the reason the edge is absent.

**(b) An over-claimed line in the prior run's `03_test_eval.py` — CORRECTED.**
`03` printed `reversion CONFIRMED OOS` from an **unconditional** correlation between
bucket z and mean raw forward return (TEST corr −0.573). That measure is contaminated by
the common market factor: when the market falls, deeply-oversold names have depressed raw
returns, so the correlation goes negative for the wrong reason. Removing it:

| TEST bucket | RAW bps | CROSS-SECTIONALLY DEMEANED bps |
|---|---|---|
| < −2.5 | 49 | — |
| −2.5 .. −2 | 184 | — |
| > 1 | 13 | — |

and on TRAIN the demeaned column is small and of inconsistent sign (+13 to +46 bps in the
gated buckets, −28 to −37 bps in the deepest). The demeaned, autocorrelation-adjusted
excess in §4.7 is the correct read, and it is **negative in both windows**.
**There is no reversion edge to confirm.** `03_test_eval.py`'s "CONFIRMED OOS" line should
be disregarded.

**(c) Two nsealgo facts a reader of my scratch scripts could get wrong.**
- `04_significance.py` evaluates the **locked period=60** variant, while the `01`/`02b`
  bucket tables use the **catalog default period=20**. These are *different signals*, not
  comparable measurements (liveness 4.44% vs 4.30%, names/day 2.13 vs 2.06). The tables
  that looked contradictory are not.
- `all_in_round_trip_bps` = **21.92 bps** (statutory 11.92 + 2 × 5 bps slippage), not the
  11.92 bps statutory-only figure. Every number in this report is net of 21.92. Verified
  against `.venv/bin/python -m nsealgo.cli costs`.

*(No defects were found in `src/nsealgo/**`. The engine, cost model and constraint
projector behaved exactly as documented, and the truncation test independently confirms
the one-bar lag is real.)*

---

## 5. Verdict

> ### No. `bollinger_bands` does not make money on NSE NIFTY-50.

Out-of-sample it returns **−0.11% CAGR net of the full 21.92 bps delivery stack over
2024-01-01 → 2026-10-01**, versus **+9.76%** for simply holding the universe — **9.87 pp/y
worse** — and it **loses to a random signal of the same breadth** (−0.11% vs +0.58%),
which fails the minimum bar in brief §6.5.

**Why it fails (most likely reason).** Not costs, not drawdown, not position sizing. The
signal itself has no exploitable cross-sectional edge on this universe: gated names carry
**negative** de-meaned excess return in both TRAIN (t = −0.92) and TEST (t = −1.21), and
inside the gate there is **no rank IC at all** (|IC| ≤ 0.021, all |t| < 1.3). The mean
reversion this strategy is built on is not merely absent on Indian large caps — the TRAIN
bucket monotonicity runs the *wrong way* (`corr(z, fwd) = +0.746`), i.e. Indian equities
behaved as a persistent-momentum market over this sample, and buying the lower Bollinger
band systematically bought the losers. NIFTY-50 has a strong down-leg-bounce structure
that a 20–60 day single-name oversold rule cannot harvest; the liveness (5%) and breadth
(~2 names/day) are also too thin to be a book in their own right.

**The one thing I would try next (not tested — I am at budget 5/5 and will not exceed it).**
The demeaned TRAIN table in §4.9(b) shows the *shallow* end of the gate carries the only
positive excess (+46 bps for z ∈ (−2.25, −2) at period=60, vs −37 bps for z < −3). The
defect is not mean reversion per se, it is that the gate is **too deep and ranked by the
wrong variable**. A single 6th, TRAIN-only variant — `period=60, n_std=2.0, entry=0.75`
(gate z < −1.5), ranked by *momentum* rather than depth — is the obvious next probe. I am
explicitly **not** claiming it would work: the effect is one bucket in one window, unadjusted
for the ~5,000 comparisons that produced it, and it would need a fresh out-of-sample window
that does not exist in this dataset. It is a hypothesis, not a result.

**What must not be concluded from this report:**
- This is not "the signal is fine but too expensive". Zero-slippage CAGR is +0.09%; the
  book is ~0% gross. Costs cost 0.20 pp/y — costs are not the binding constraint.
- This is not "it just needs more capital or better drawdown control". MaxDD (−10.40%) is
  *shallower* than buy-and-hold (−13.51%), purely from being ~19% invested; beta-adjusted
  alpha is **−2.18 pp/y**.
- The shallower drawdown must not be quoted as an advantage.

**Standing caveat.** Survivorship bias is present throughout (today's NIFTY-50 backfilled
over 24 years). That inflates *every* strategy equally here, so it does not explain the
gap to buy-and-hold; but it means none of these absolute numbers transfer to a live,
point-in-time universe.

---

## 6. Reproducing this run

```bash
.venv/bin/python research/agent_bollinger_bands/00_data.py               # universe + panel
.venv/bin/python research/agent_bollinger_bands/01_diagnostics.py        # port proof + TRAIN buckets
.venv/bin/python research/agent_bollinger_bands/02_train_select.py      # 5 variants, TRAIN only -> selection
.venv/bin/python research/agent_bollinger_bands/02b_signal_diagnostics.py# TRAIN exposure-free diagnostics
.venv/bin/python research/agent_bollinger_bands/03_test_eval.py          # TEST, once, locked
.venv/bin/python research/agent_bollinger_bands/04_significance.py       # lookahead proof + t-stats
.venv/bin/python research/agent_bollinger_bands/05_diagnosis.py          # TRAIN mechanism + corrections
.venv/bin/ruff check research/agent_bollinger_bands/*.py                 # lint: clean
```

`02_train_select.py` is structurally incapable of seeing TEST (it truncates the panel
in-process and asserts on it). Re-running `02` reproduced `selected_variant.json`
byte-identically, confirming the selection is deterministic and not hand-picked.

**Scratch files:** `00_data.py` `01_diagnostics.py` `02_train_select.py`
`02b_signal_diagnostics.py` `03_test_eval.py` `04_significance.py` `05_diagnosis.py`
`common.py` `DECLARED_BUDGET.md` `selected_variant.json` `panel.pkl` `symbols.txt`

No file under `src/nsealgo/**`, `src/cryptobot/**`, `GOAL.md`, `reports/` or any test was
modified. Nothing was committed.