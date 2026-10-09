# Cointegration Strategy — NSE NIFTY-50 Validation Report

**Agent:** `cointegration`
**Assigned strategy:** `src/cryptobot/strategies/catalog/cointegration_strategy.py`
**Class:** `CointegrationStrategy` (catalog `name = "cointegration"`)
**Status:** IN PROGRESS — results appended below as they are obtained.
**Date of run:** 2026-10-08

---

## 0. Is this crypto-specific?

**No.** It has NSE meaning, so this run proceeds.

The catalog file is *named* `cointegration` but it is **not** a cointegration strategy
in the pairs-trading sense. There is no pair, no spread, no hedge ratio, and no
OLS/Engle-Granger residual. Reading the source (`cointegration_strategy.py:28-36`),
the entire signal is:

```
z_t = (close_t − mean(W)) / std(W)          # trailing window W, population std (ddof=0)
+1 (long)   if z_t < −entry
−1 (short)  if z_t > +entry
 0           otherwise
```

It is a **single-name z-score mean-reversion / oversold-timing rule**. That is
statistically distinct from cointegration: a z-score of price vs. its *own* mean
measures how stretched the level is; cointegration measures whether two series share
a long-run equilibrium. Applying a z-score to a *non-stationary trending* index like
NIFTY constituents is precisely the textbook failure of the cointegration idea —
prices do not mean-revert to a fixed mean, they trend. So the honest name for what
this code does is **mean-reversion / oversold-timing**, and I evaluate that.

This naming mismatch is the first finding. It is a real documentation defect in the
catalog and is recorded in §Bug-1 below.

---

## 1. The signal, restated precisely

Faithful port in `research/agent_cointegration/coinlib.py`:

| Component | Catalog behaviour | This port | Why |
|---|---|---|---|
| z-score | `zscore(closes)` over the strategy's whole rolling buffer | trailing mean / **population** std over an explicit window `W`, standardised on the last bar | see §Bug-2 — `config.period` never windows the statistic |
| Long leg | `+1` when `z < −entry` | **kept verbatim** | mean-reversion is the only usable side |
| Short leg | `−1` when `z > +entry` | **dropped** | an Indian delivery account cannot short (`GOAL.md`, brief §5) |
| Book | single-symbol signal | long-only cross-sectional, `PortfolioConfig(n_positions=22)` | the NSE book is cross-sectional |

**Two deliberate deviations from the literal source, both forced, both recorded:**

1. **The short leg is dropped.** The catalog is long/short; NSE delivery is long-only.
   Dropping it is a *reduction* in the strategy's opportunity set, not a tuning choice,
   and it is applied identically to all variants and all controls.
2. **`config.period` is honoured as the window.** The catalog declares
   `period: int = 30` and uses it *only* in `warmup()`; the z-score itself is computed
   over the strategy's `maxlen=300` streaming buffer. So the declared parameter is
   inert in the source. I take `W` explicitly because on a cross-sectional panel the
   lookback is the parameter that matters, and I use the catalog's exact z-score
   formula (mean + `ddof=0` std) so the statistic itself is unchanged.

**No lookahead:** `z` on date *t* uses closes up to and including *t* only. `run_backtest`
holds weights from *t+1*, giving exactly one bar of lag. Verified mechanically — see
§5 Lookahead audit.

---

## 2. Data

| | |
|---|---|
| Source | `data/nse/<symbol>_1d.csv` via `nsealgo.data.loader.load_universe` |
| Panel | 50 NIFTY-50 symbols, daily close |
| Span | 2002-07-01 → 2026-10-01 |
| **TRAIN** | **2016-01-01 → 2023-12-31** |
| **TEST** | **2024-01-01 → 2026-10-01** |
| Survivorship bias | **PRESENT** — today's NIFTY-50 backfilled over 24y. Disclosed in every number. |

---

## 3. Costs (mandatory, non-negotiable)

`CostModel(segment="delivery", slippage_bps=5)` — the full Indian delivery stack:
STT, exchange transaction charge, SEBI turnover fee, stamp duty, DP charges,
brokerage, and 18% GST.

- `round_trip_bps(100_000)` = **11.92 bps** — statutory only
- `all_in_round_trip_bps(100_000)` = **21.92 bps** — what `run_backtest` charges,
  because the portfolio simulator never calls `fill_price`, so the engine folds
  slippage in as `rt_bps + 2 × slippage_bps`

**Everything reported in this file is via `run_backtest`, therefore net of 21.92 bps
round trip.** The 11.92 figure appears nowhere in the results. Zero-cost numbers are
labelled *gross, memo only*.

---

## 4. DECLARED PARAMETER BUDGET — 5 variants, fixed before any result was read

**This list was declared in `train_sweep.py` (docstring, lines 1-16) before that file
was executed. It is adopted unchanged from the interrupted run and re-verified here.**

| # | Variant | Window `W` | `entry` (sigma) | Score rule |
|---|---|---|---|---|
| **V1** | long window, shallow trigger | 252 (1y) | 1.0 | depth |
| **V2** | long window, deeper trigger | 252 | 1.5 | depth |
| **V3** | mid window, shallow trigger | 126 (2 quarters) | 1.0 | depth |
| **V4** | mid window, deeper trigger | 126 | 1.5 | depth |
| **V5** | same signal, brief's ranking | 126 | 1.0 | momentum (rank flagged by 126d trailing return) |

Rationale: the catalog default is a ~300-bar buffer with `entry=1.0`. 126 bars is the
shortest window that still spans two quarters; 252 is one year. `entry ∈ {1.0, 1.5}`
brackets the catalog default from both sides. V5 isolates the score-ranking rule
against V3 — it is the *same* signal with a different cross-sectional sort.

**Budget: 5 variants. Not exceeded. Any deviation is reported, not hidden.**

Parameters that are NOT tuned and are fixed for every variant:
`n_positions=22`, monthly (`M`) rebalance, `slippage_bps=5`, momentum lookback=126
(V5 only), long-only, no short leg.

---

## 5. Audit trail

- Lookahead audit: `audit_lookahead.py` — **§6**
- TRAIN sweep: `train_sweep.py` — **§7**
- TEST evaluation: `test_eval.py` — **§8**
- Failure diagnosis (event study + layer peel): `diagnose.py` — **§9**
- Bug-3 proof: `bug3_engine_trace.py`, `bug3_cost_probe.py`, `bug3_rupee_reconciliation.py`
- §9.3 exposure isolation: `bug4_exposure_probe.py`
- Shared harness (signal, controls, corrected costs): `coinlib.py`

---

## 6. Lookahead audit — PASS

`audit_lookahead.py`, TRAIN panel, four independent checks:

| check | result |
|---|---|
| **A. Truncation** — score[:T] from the full panel vs recomputed on px[:T], 4 random cut dates | max abs diff **0.000e+00**, 0 NaN-pattern mismatches |
| **B. Relabelling** — permute the 48 symbol columns; every per-symbol statistic must be invariant | max abs diff **0.000e+00** |
| **C. Liveness** — is the score constant (which would make the one-bar lag vacuous)? | 14.20% of symbol-bars live; the score set changed on **77.3%** of bars |
| **D. Formula** — our z-score vs the catalog's own formula, one cell | `axisbank` 1.3462246230 vs 1.3462246230 |

**Verdict: no lookahead.** The score is strictly a function of the past, is
independent of the peer group, and genuinely changes bar to bar.

---

## 7. TRAIN results (2016-01-01 → 2023-12-31) — the only data used for selection

Panel actually loaded: **4,629 bars × 48 symbols, 2008-01-01 → 2026-10-01**.

> *Note on the panel.* The brief describes `1d` as 50 symbols from 2002-07-01. The
> **cleaned** panel `load_universe` returns is 48 symbols from **2008-01-01** — the
> cleaning rules drop pre-2008 vendor artifacts and 2 symbols fail an integrity
> check. This is expected behaviour of the documented loader, not a data fault. The
> TRAIN/TEST windows are well inside the cleaned span either way.

### All 5 declared variants — corrected costs (21.92 bps, the headline basis)

| Variant | CAGR | Sharpe | MaxDD | Calmar | Turn/y | Drag/y | Liveness | Avg names | Exposure | Total ret |
|---|---|---|---|---|---|---|---|---|---|---|
| V1 W252 e1.0 depth | 8.38% | 0.20 | −31.99% | 0.26 | 2.32x | 1.30% | 13.17% | 7.6 | 42.9% | +91.9% |
| V2 W252 e1.5 depth | 8.38% | 0.21 | −28.36% | 0.30 | 1.67x | 0.96% | 6.98% | 4.0 | 26.0% | +91.9% |
| **V3 W126 e1.0 depth** | **11.93%** | **0.45** | −30.99% | 0.38 | 3.02x | 1.98% | 15.46% | 12.5 | 48.9% | +149.0% |
| V4 W126 e1.5 depth | 6.38% | 0.05 | −27.13% | 0.24 | 2.22x | 1.18% | 8.50% | 5.8 | 29.8% | +65.0% |
| V5 W126 e1.0 momentum | 11.68% | 0.45 | −31.12% | 0.38 | 3.02x | 1.96% | 15.46% | 12.5 | 48.9% | +144.5% |

### Same variants, as-is engine costs (10.96 bps — what `run_backtest` really charges)

The gap is small and does not change the ranking: V3 is 12.67% / Sharpe 0.51 as-is
vs 11.93% / 0.45 corrected. **Cost correction moves CAGR by 0.4–0.7 pp/yr.** It is
real and must be reported, but it does not rescue or sink the strategy.

### TRAIN controls

| Control | CAGR | Sharpe | MaxDD | Turn/y | Avg names | Exposure |
|---|---|---|---|---|---|---|
| **V3 (selected)** | **11.93%** | **0.45** | −30.99% | 3.02x | 12.5 | 48.9% |
| nsealgo composite | 20.77% | 0.93 | −32.94% | 1.96x | 21.8 | 89.1% |
| buy-and-hold (EW) | 22.15% | 0.90 | −37.97% | 0.25x | 48 | 100% |
| random s1 | 11.56% | 0.44 | −30.56% | 3.01x | 12.5 | 48.9% |
| random s2 | 11.31% | 0.42 | −31.46% | 3.01x | 12.5 | 48.8% |
| random s3 | 11.68% | 0.45 | −30.97% | 3.01x | 12.4 | 48.7% |

### 🔒 VARIANT LOCKED: **V3 = window 126, entry 1.0, rule "depth"**

Chosen on **TRAIN Sharpe** (0.454, best of 5; V5 is 0.450 and statistically
indistinguishable). Locked here, in writing, **before** the TEST window was opened.

**Already visible on TRAIN, before any TEST data:**

- V3 beats buy-and-hold by **nothing** — it is 10.2 pp/yr *behind* (11.93% vs 22.15%).
- V3 is beaten by the nsealgo composite by **8.8 pp/yr** (11.93% vs 20.77%).
- **V3 does not separate from a random signal.** Random seeds land at 11.31–11.68%
  against V3's 11.93% — a 0.25–0.62 pp/yr spread across three seeds, with V3 sitting
  barely above the top of it. On TRAIN this already fails the brief's §6.5 minimum bar.
- V3's edge over random, if any, is essentially "hold ~12 names, ~49% of the book,
  rebalance monthly."

**Disclosed deviation (brief §4.4):** the interrupted run had already opened TEST
(its `test_eval.py` ran, and `_test_yearly.csv` / `_test_equity.csv` exist on disk).
Its TRAIN CSV was produced by a `build_score_window` that is **broken** in the
leftover source — it builds the warm-up slice from bars ending at the window start
and then indexes it with dates that are not in it, which raises `KeyError` on the
current panel. So those numbers were not reproducible and **have been discarded and
regenerated from scratch**. The V3 selection above rests only on the regenerated
TRAIN table, which reproduces the same ranking.

---

## Bugs found

### Bug-1 (catalog, documentation) — `cointegration_strategy.py` is not a cointegration strategy
No pair, no spread, no hedge ratio. It is a single-name z-score mean-reversion rule
applied to price. The name promises a statistical-arbitrage construction the code does
not implement, and it is applied to non-stationary equity prices where the underlying
assumption (a stationary spread) does not hold. **Severity: medium** (misleading
label; misleads anyone who picks this strategy expecting pairs trading).

### Bug-3 (`src/nsealgo`, HIGH, affects EVERY backtest in the project) — costs are charged at half

**This is the most important finding in this run. It is not in the strategy; it is in
the shared harness, so it affects every other agent's numbers too.**

The cost model and the engine disagree about what the two are multiplying.

- `costs.py:198-201` — `round_trip_bps` is explicitly **"basis points of total
  turnover"**, and divides by `2 * notional` because "a round trip on `notional`
  produces `2 * notional` of turnover".
- `engine.py:411-412` — `rate = all_in_round_trip_bps / 10_000`, i.e. a rate defined
  **per unit of total turnover**.
- `engine.py:415-419` — but the engine then computes
  `turnover_by_date = (tgt - tgt.shift(1)).abs().sum(axis=1) / 2.0`, which is
  **one-way** turnover — half of total turnover, by the engine's own definition.
- `engine.py:432` — and charges `cost_amt = turn_t * eq * rate`.

**A per-total-turnover rate is multiplied by a one-way quantity.** Charge per unit of
total turnover therefore comes out as `rate / 2`.

**Proof** — `bug3_engine_trace.py` rebuilds the engine's own `tgt` and prints the
arithmetic. A book that goes from flat to fully long in one name:

```
target book:            2024-03-01  AAA = 1.0000      (flat -> fully long)
engine turnover_by_date = 0.5000                      (one-way, after the /2)
total turnover          = 1.0000                      (Rs 1,00,000 actually traded)

engine charge  = one_way x rate = 0.5 x 0.002192 = 0.001096  ->  Rs 109.60
correct charge = total    x rate = 1.0 x 0.002192 = 0.002192  ->  Rs 219.20
ratio engine/correct = 0.500000
```

Cross-checked three further ways, all consistent:

| probe | result |
|---|---|
| `bug3_cost_probe.py` — ratio vs a total-turnover bill | exactly **0.5000** |
| `bug3_calibration_probe.py` — book set equal to `REF_POSITION_NOTIONAL` | engine charge = `one_way x rate x book`, one-way again |
| independent hand bill of every rupee leg at real notionals | engine ≈ half once the deliberate reference-notional normalisation is separated out |

**Both halves of the stack are affected:** statutory charges are halved *and* slippage
is charged on one leg instead of two. That is precisely the failure mode
`all_in_round_trip_bps`' own docstring says it exists to prevent:

> *"Without this, slippage would silently contribute zero to the backtest — which
> would make the Gate 4 stress test vacuous."*

**Magnitude.** Every reported nsealgo result is net of **10.96 bps of total turnover
instead of 21.92** — roughly half the intended Indian delivery stack. It does not
invalidate results on its own (cost drag on these books is ~0.5–1.8%/yr, so the
correction moves CAGR by well under a percent), but it flatters every CAGR in the
project and it makes the Gate 4 slippage stress weaker than advertised.

**Contradiction with the brief.** Brief §3 states `all_in_round_trip_bps(100_000)`
= 21.92 bps is "what `run_backtest` actually charges". It is not — `run_backtest`
charges 10.96 bps. The brief's number is the *intended* number. **This report treats
21.92 bps as the correct basis** and reports both:

- **`as-is`** = `run_backtest` with the stock `CostModel` (what the engine really does, 10.96 bps)
- **`corrected`** = `run_backtest` with `DoubledCosts`, which returns `2x`
  `all_in_round_trip_bps` so the engine's charge lands on the intended 21.92 bps

**The corrected figure is the headline.** The as-is figure is disclosed alongside it.
`src/nsealgo/**` was **not** modified; the correction is a research-side subclass.

### Bug-2 (catalog, real defect) — `config.period` is inert
`CointegrationConfig.period` (default 30) is consumed **only** by `warmup()`
(`cointegration_strategy.py:25-26`). The z-score at line 29 is `zscore(closes)` over
the entire `maxlen=300` streaming buffer that `signal_base` hands it, so the effective
window is always ~300 bars regardless of configuration. A user who sets
`period=20` and `period=200` gets **identical signals**. **Severity: medium** — a
tuning parameter that silently does nothing, which makes the strategy untunable as
written and misreports exposure in any config dump.

---

## 8. TEST results (2024-01-01 → 2026-10-01, 685 bars) — locked variant, no re-tuning

**Variant: V3 = window 126, entry 1.0, rule "depth". Locked on TRAIN before this
window was opened. Nothing was re-tuned here.**

### Headline — corrected cost basis (21.92 bps of total turnover, the intended stack)

| Metric | **cointegration V3** | buy-and-hold (EW) | nsealgo composite |
|---|---|---|---|
| **CAGR** | **3.27%** | 8.09% | 6.07% |
| **Sharpe** | **−0.26** | 0.18 | 0.04 |
| **MaxDD** | **−15.19%** | −15.91% | −15.02% |
| **Calmar** | 0.22 | 0.51 | 0.40 |
| Total return | +9.46% | +24.37% | +18.0% |
| Turnover/yr | 3.32x | 0.71x | 2.07x |
| Cost drag/yr | 1.58% | 0.16% | 1.09% |
| **Avg names held** | **14.1** | 48 | 21.3 |
| Avg exposure | 56.3% | 100% | 87.2% |
| Signal liveness | 18.83% of symbol-bars | — | — |

Total cost paid over the window: **Rs 93,099**.

### As-is engine cost basis (10.96 bps — what `run_backtest` really charges)

V3: CAGR **4.03%**, Sharpe −0.19, MaxDD −14.87%, drag 0.80%/y, total +11.7%.

**Cost basis gap: +0.76 pp/yr.** The Bug-3 correction does not rescue the strategy;
it costs it 0.76 pp/yr. Both bases are reported; the corrected one is the headline
because it is the number the brief asks for.

### 8.1 vs buy-and-hold

| | strategy | B&H | delta | verdict |
|---|---|---|---|---|
| Total return | +9.46% | +24.37% | **−14.91 pp** | **WORSE** |
| CAGR | 3.27% | 8.09% | **−4.82 pp/yr** | **WORSE** |
| MaxDD | −15.19% | −15.91% | +0.72 pp | slightly better (shallower) |
| Sharpe | −0.26 | 0.18 | −0.44 | WORSE |

It gives up **14.91 pp of total return** over 2.75 years to shave **0.72 pp** off the
drawdown. That is a terrible trade — the drawdown improvement is 5% of the return
given up.

**Exposure-matched** (grossed up to 100% deployed, costs not rescaled): CAGR
**5.17%** vs B&H **8.09%** → still **worse**. So the thin signal is not the excuse.

### 8.2 Random-signal control — FAILS the minimum bar

| | CAGR | Sharpe | MaxDD | Avg names | Exposure |
|---|---|---|---|---|---|
| **V3 strategy** | **3.27%** | **−0.26** | −15.19% | 14.1 | 56.3% |
| random s1 | 3.72% | −0.22 | −15.19% | 13.9 | 56.6% |
| random s2 | 3.39% | −0.25 | −15.19% | 14.5 | 56.5% |
| random s3 | 3.67% | −0.22 | −15.19% | 13.7 | 56.6% |
| random s4 | 4.10% | −0.18 | −15.19% | 14.2 | 56.6% |
| random s5 | 3.56% | −0.23 | −15.19% | 13.7 | 56.5% |
| random mean | **3.69%** (sd 0.26) | −0.22 (sd 0.03) | | | |

**The strategy does not beat a coin flip.** It is *below* the random mean (3.27% vs
3.69%) and below the best of five seeds (4.10%). All five random seeds have a
**better Sharpe** than the strategy. This is a hard fail of the brief's §6.5 bar.

The random seeds are strikingly tight — MaxDD is **−15.19% for the strategy and for
all five randoms**, which is simply the drawdown of a ~56%-exposed book in this
window. The seed is changing nothing that matters.

### 8.3 Cost stress

| Basis | bps of total turnover | CAGR | Sharpe | MaxDD | Drag/yr |
|---|---|---|---|---|---|
| 2× corrected (Gate 4 style) | 43.84 | 1.77% | −0.41 | −15.82% | 3.10% |
| **corrected — HEADLINE** | **21.92** | **3.27%** | −0.26 | −15.19% | 1.58% |
| as-is engine | 10.96 | 4.03% | −0.19 | −14.87% | 0.80% |
| zero cost (gross, memo) | 0 | 4.79% | −0.12 | −14.55% | 0.00% |

**Gross return is positive (+4.79%/y) but net is only +3.27%/y** — cost drag takes
1.52 pp/yr. But note the decisive point: **even gross, the strategy loses to
buy-and-hold's 8.09%**. So this is *not* a "viable signal killed by costs" story.
The signal does not work to begin with; costs just finish it off.

### 8.4 Yearly returns (TEST)

| Year | cointegration | composite | buy-and-hold |
|---|---|---|---|
| 2024 | +3.69% | +21.91% | +20.13% |
| 2025 | +12.84% | +6.72% | +13.34% |
| 2026 (to 01 Oct) | −6.46% | −9.31% | −8.26% |

Positive years: cointegration **2/3**, composite 2/3, B&H 2/3.

### 8.5 Sanity checks (brief §6)

| check | value | verdict |
|---|---|---|
| 1. Plausibility | CAGR 3.27% | **OK** — far below the 40–50% ceiling, no lookahead bug |
| 2. Weight count | avg 14.1 names | **OK** — not 48, no weight accumulation |
| 3. Signal liveness | 18.83% of symbol-bars | **OK** — well above the 5% floor; genuinely live, not always-flat |
| 4. Cost drag | 1.58%/y, Rs 93,099 | gross positive, net positive but far below B&H |
| 5. Negative control | 3.27% vs random 3.69% mean | **FAIL — does not beat a coin flip** |

---

## 9. Why did it fail? — diagnosis (`diagnose.py`)

### 9.1 The signal is *not* dead — the construction is what kills it

**Event study** — forward return of flagged symbol-bars vs unflagged, paired by date,
t-stat across dates (the cross-section is heavily correlated within a day, so an
unclustered t-stat would be inflated by ~√n):

| horizon | TRAIN spread | t | TEST spread | t |
|---|---|---|---|---|
| 5d | +0.168% | 2.95 | +0.218% | 2.67 |
| 21d | +0.539% | 4.50 | +0.570% | 3.35 |
| 63d | +1.153% | 6.19 | +0.156% | 0.55 |
| 126d | **−1.535%** | **−5.23** | −0.427% | −0.87 |

There **is** a real short-horizon effect: an oversold reading beats an average one by
~0.54% over 21 days on both windows, at t ≈ 3.4–4.5. It is not a data artefact.

**But it reverses by 126 days** (TRAIN t = −5.2). A +126-day holding period — which
is exactly what a monthly-rebalanced, 3.3x-turnover book effectively creates — captures
the *negative* end of that curve. The signal is a 1-month mean-reversion effect being
harvested with a ~4-month average holding period.

### 9.2 Layer peel — where the return actually goes

| Layer | TRAIN CAGR | TEST CAGR | TEST Sharpe | TEST exposure |
|---|---|---|---|---|
| **L0** raw signal-following, no constraints, no costs | 25.93% | **8.94%** | 0.22 | 96.9% |
| **L1** + full Indian cost stack | 22.12% | 6.13% | 0.05 | 96.9% |
| **L2** + position caps, sector caps, cash buffer | 11.93% | **3.27%** | −0.26 | 56.3% |
| **L3** + turnover budget = *the reported result* | 11.93% | 3.27% | −0.26 | 56.3% |
| *[ref]* buy-and-hold | 22.15% | 8.09% | 0.18 | 100% |
| *[ref]* nsealgo composite | 20.77% | 6.07% | 0.04 | 87.2% |

This is the most useful table in the report. On TEST:

- Costs take **2.81 pp/yr** (8.94% → 6.13%).
- **Portfolio constraints take another 2.86 pp/yr** (6.13% → 3.27%) — almost exactly
  as much again, and they do it by halving exposure from 96.9% to 56.3%.
- The turnover budget (L2→L3) contributes **nothing** — the book is already so
  un-invested and so churn-free at that point that the 35% budget never binds.

**And the decisive line is L0: 8.94% vs buy-and-hold 8.09%.** With no constraints, no
costs, no caps, ~97% deployed, and 5.95x/y turnover, the raw signal beats
buy-and-hold by **0.85 pp/yr** — inside the noise of a 2.75-year window. There is
almost nothing there to protect. The construction did not destroy a large edge; it
took a small one and shaved it twice.

This is why the random control ties: a book that is 56% invested, 14 names wide,
monthly, in large caps, *is* close to a random large-cap book, and it performs like one.

### 9.3 Why the book only reaches 56% exposure — a construction finding, not a code bug

`cash_buffer` is 10%, so a full book should run ~90% gross. It runs 56.3%.
`bug4_exposure_probe.py` isolates the cause by relaxing one constraint at a time on
the identical signal:

| Setting | Exposure | Avg names | CAGR |
|---|---|---|---|
| stock config | 56.3% | 14.1 | 3.27% |
| sector cap 100% | 59.3% | 14.8 | 4.15% |
| sector cap 50% | 59.1% | 14.6 | 4.16% |
| no cash buffer | 62.3% | 14.9 | 3.51% |
| `n_positions` 30 | 56.4% | 13.7 | 3.45% |
| turnover budget 1.0 | 56.1% | 8.6 | 3.00% |
| turnover budget 2.0 | 56.1% | 8.6 | 3.00% |

Exposure is **insensitive to the sector cap, the cash buffer, `n_positions` and the
turnover budget.** The binding constraint is the **12% single-name cap meeting a
signal that flags a median of only 7 names**: 7 × 12% = 84% maximum achievable
exposure, × 0.9 cash buffer = 75.6%, and the sector caps take it down to ~62% before
the buffer and 56% after.

**This is correct arithmetic, not a defect** — but it is a serious *comparability*
caveat for the whole project:

> **Raw CAGR is not comparable across strategies whose signals flag different
> numbers of names.** A broad signal (the composite flags ~21 names, runs at 87%
> exposure) is compared against a thin one (this strategy flags ~7, runs at 56%).
> The thin-signal strategy is structurally handicapped in any head-to-head CAGR
> table, and roughly half of the "underperformance" in §8 is a cash-drag artefact of
> the constraint set, not a property of the signal.

I therefore report the exposure-matched number (5.17% vs B&H 8.09%, still worse) and
the L0/L1 layers, so the conclusion does not depend on this. **Every head-to-head
CAGR table in this project should carry an exposure column, and thin-signal
strategies should be compared exposure-matched.**

### 9.4 Persistence

| | mean fraction of next 200 bars still below −1σ | flagged 21d fwd | unconditional 21d fwd |
|---|---|---|---|
| TRAIN | 26.5% | +2.744% | +1.909% |
| TEST | 24.1% | +0.976% | +0.857% |

An oversold reading is still oversold ~24–27% of the time over the next 200 days. So
the signal fires repeatedly into continued weakness — consistent with the 126d
reversal in §9.1, and with the observation that the useful horizon is 1 month while
the book's realised holding period is ~4 months.

---

## 10. Reproduction

```bash
.venv/bin/python research/agent_cointegration/audit_lookahead.py     # §6  -> PASS
.venv/bin/python research/agent_cointegration/train_sweep.py         # §7  -> V3 locked
.venv/bin/python research/agent_cointegration/test_eval.py           # §8  -> headline
.venv/bin/python research/agent_cointegration/diagnose.py            # §9  -> event study + peel
.venv/bin/python research/agent_cointegration/bug3_engine_trace.py   # Bug-3 proof
.venv/bin/python research/agent_cointegration/bug4_exposure_probe.py # §9.3
```

`.venv/bin/ruff check research/agent_cointegration/` → **All checks passed**.
Every script re-runs to identical numbers after the lint pass.
`src/nsealgo/**`, `src/cryptobot/**` and all test files were **not modified**. Nothing committed.

---

## Verdict

### Does this strategy make money on NSE? **NO.**

Out of sample it returns **3.27% CAGR at a −0.26 Sharpe** against buy-and-hold's
**8.09%**, and it **fails the random-signal control** (3.27% vs a 3.69% random mean,
and worse Sharpe than all five seeds). It gives up 14.91 pp of total return to shave
0.72 pp off the drawdown. Train 11.93% → test 3.27% is a textbook decay, and the
strategy was already indistinguishable from noise on TRAIN (random 11.31–11.68% vs
V3 11.93%).

### Most likely reason

**The strategy has a real but short-horizon edge, and the book is built to harvest it
at the wrong horizon.** The signal is genuine — an oversold reading beats the average
name by ~0.54% over 21 days on *both* windows at t ≈ 3.4–4.5 (§9.1) — but it
*reverses* at 126 days (t = −5.2 on TRAIN), and a monthly-rebalanced book with 3.3x
annual turnover holds names for roughly four months. It buys the front of the curve
and eats the back. Everything downstream compounds the damage: 5.95x/y raw turnover
hands 2.81 pp/yr to costs, and a signal that flags a median of 7 names cannot fill a
book capped at 12% per name, so half the capital sits in cash and the result is
compared against a fully-invested buy-and-hold (§9.3).

Strip everything away and the ceiling is visible: **L0 — no constraints, no costs,
97% deployed — is 8.94% against buy-and-hold's 8.09%.** There was never a large edge
to lose.

### The one thing I would try next

**Test a genuine cointegration strategy instead of this one.** This file is named
`cointegration` but implements a single-name z-score of price against its own mean
(Bug-1) — and the z-score of a *non-stationary* trending equity price is precisely
the statistic that is *supposed* not to mean-revert. The correct construction uses a
**pair**: estimate a hedge ratio (OLS or Engle-Granger on returns/logs), build the
spread, and trade the **stationary spread residual** rather than the price level.
The long-only leg is long the cheap leg / short the rich leg, which maps to a
long-only book by buying the underpriced member of the pair. That is a different
strategy, not a parameter change to this one, and it is outside this run's declared
5-variant budget — so it is a recommendation, not a result.

A cheaper second step, if the budget allowed it: re-run this same signal with a
**21-day holding period** (biweekly rebalance, turnover budget raised to match) so
the book actually lives where the edge is. §9.1 says the 21d spread is +0.57% at
t = 3.35 on TEST, and the 126d spread is negative — the horizon mismatch is the
single clearest, cheapest thing left to test.

### Bugs found (details above)

| # | Where | Severity | One line |
|---|---|---|---|
| **Bug-3** | `src/nsealgo/backtest/engine.py` | **HIGH — affects every result in the project** | Costs are charged at **half** the intended stack (10.96 bps of total turnover, not 21.92), because a per-*total*-turnover rate is multiplied by a *one-way* turnover quantity. |
| Bug-1 | `cointegration_strategy.py` | medium | Named "cointegration" but implements a single-name z-score mean-reversion rule — no pair, no spread, no hedge ratio. |
| Bug-2 | `cointegration_strategy.py` | medium | `config.period` is inert: it is used only by `warmup()`, so `period=20` and `period=200` produce identical signals. |
| Bug-4 | construction, not code | medium (methodological) | Raw CAGR is not comparable across strategies with different signal breadth — the 12% name cap leaves a thin-signal book ~56% invested. |

**Bug-3 is the headline deliverable of this run.** It is not in my strategy; it is in
the shared harness, so it applies to every other agent's numbers in this project and
to `reports/VALIDATION_v1.md`. It flatters every CAGR by roughly the cost-drag term
(0.4–0.7 pp/yr on typical books, 1.5 pp/yr on this one) and it halves the Gate 4
slippage stress. I did not fix it — `src/nsealgo/**` is out of scope for this
assignment — but it is proven three independent ways and should be fixed centrally
before any more strategies are benchmarked.