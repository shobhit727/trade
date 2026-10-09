# REPORT — `atr_trailing_stop` on NSE NIFTY-50

**Status: IN PROGRESS (written early, per brief §8, before any run in this session)**
**Agent:** assigned strategy `atr_trailing_stop`
**Source:** `src/cryptobot/strategies/catalog/atr_trailing_stop.py`
**Date of this session:** 2026-10-08 (resuming an interrupted prior run — see §Provenance)

---

## 1. The strategy under test

Verbatim logic from the catalog source:

```python
b = atr(highs, lows, closes, period)            # mean of last `period` true ranges
m = sma(closes, period)
signal = +1  if close > m + multiplier*b
         -1  if close < m - multiplier*b
         else 0
```

Default config: `period=14`, `multiplier=2.0`.

**Naming note (honesty):** the file is called `atr_trailing_stop`, but the
implementation is *not* a trailing stop. It holds no peak, never trails, and has no
stop-loss. It is a **volatility-normalised breakout band around an SMA**. The code is
the contract, so the code is what is being ported. Anyone reading the filename will
mis-attribute the result — flagging that up front.

**Long-only:** a `-1` short is not available in an Indian delivery account, so `-1`
means "not eligible today". No shorting anywhere in this report.

## 2. Data

| Item | Value |
|------|-------|
| Source | `data/nse/<symbol>_1d.csv` via `nsealgo.data.loader.load_universe("data/nse")` |
| Timeframe | **1d only** (brief §2: primary substrate, ~6,000 bars, 24y) |
| Bars per symbol | >= 1000 (`min_bars`), post C1-C7 cleaning |
| Price panels used | `close` (from `load_universe`), `high`/`low` (same `load_symbol` cleaning path, restricted to the same symbol set) — ATR needs H/L |
| Panel end date | **2026-10-01** (see AGENTS.md: re-fetched 2026-10-06) |

**Mandatory disclosure — survivorship bias is present.** The universe is *today's*
NIFTY-50 backfilled to 2008. Delisted names are absent. Every number in this report is
therefore optimistic by an unknown margin. This is a property of the data on disk, not
of the strategy, and it cannot be fixed here.

**No intraday data is used.** 5m/15m cover only ~7 weeks and cannot validate anything.

## 3. Split (brief §4)

| Set | Window | Bars | Use |
|-----|--------|------|-----|
| **TRAIN** | 2016-01-01 → 2023-12-31 | ~1,975 | everything tuned on |
| **TEST** | 2024-01-01 → 2026-10-01 | ~685 | touched once, reported last |

## 4. DECLARED PARAMETER BUDGET — max 5 variants (declared before any run)

Only `(period, multiplier)` varies. Score construction, portfolio config, rebalance
frequency and cost model are **fixed** across all five so the comparison is clean.

| # | Label | period | multiplier | Rationale |
|---|-------|--------|-----------|-----------|
| V1 | `V1_period14_mult2.0` | 14 | 2.0 | catalog default — must be measured |
| V2 | `V2_period14_mult1.5` | 14 | 1.5 | tighter band, period held at default |
| V3 | `V3_period20_mult2.5` | 20 | 2.5 | looser band, longer period |
| V4 | `V4_period55_mult2.0` | 55 | 2.0 | ~quarter-year: band around a slow SMA |
| V5 | `V5_period10_mult3.0` | 10 | 3.0 | very tight window, very wide band — the "almost never fires" corner |

**Total distinct parameter variants tested: 5. Budget respected. Not exceeded.**
No threshold was tuned until an equity curve looked good. V5 is included precisely
because it is the corner where a volatility band goes dead — that is a pre-registered
prediction to check, not a rescue attempt.

## 5. Fixed construction (identical for all variants)

- **Score:** cross-sectional percentile rank of 126-day momentum, restricted to names
  flagged `+1` on that bar. Non-flagged names are NaN → excluded from the book.
  This is the brief §5 construction.
- **Portfolio:** `PortfolioConfig(n_positions=22)` — defaults otherwise (12% single
  name, 25% sector, 10% cash buffer, 35% turnover budget, `max_names=30`).
  Enforced by `run_backtest`; not bypassed.
- **Rebalance:** monthly (`"M"`), the engine's evidence-supported default.
- **Costs:** `CostModel(segment="delivery", slippage_bps=5)`.
  `run_backtest` charges `all_in_round_trip_bps(100000)` = **21.92 bps**
  (11.92 statutory + 2x5 slippage). **All headline numbers below are net of 21.92 bps.**
  The 11.92 figure is never quoted as if it were the backtest's charge.
- **No lookahead:** ATR and SMA use strictly trailing windows; the engine earns
  `held.shift(1) * rets`, so a decision made on the close of *t* cannot see *t+1*.

## 6. Provenance of the prior (interrupted) run

This session resumed partial scratch work in `research/agent_atr_trailing/`. Files
present at start: `common.py`, `stage1_train.{py,json}`, `stage1b_diag.{py,json}`,
`stage2_test.{py,json}`, `stage3_robustness.{py,json}`, `_ohlc.pkl`.

**Nothing is trusted without re-derivation.** mtimes show `common.py` was modified
(09:12) *after* `stage1_train.py` ran (08:55) but *before* `stage2_test.py` (09:10/15)
— so `stage1_train.json` was produced by a different version of the harness than the
one on disk. That is a reproducibility defect and it must be resolved by re-running
everything from scratch, not by reading the JSON.

**TEST-contamination disclosure:** the prior run already executed `stage2_test.py`, so
the TEST window has been opened once before this session. I have read those numbers
during triage. To keep the run honest I will: (a) re-run the whole pipeline from a
deleted cache and verify the TEST numbers reproduce bit-for-bit; (b) make **no**
further parameter or construction change of any kind — the frozen TRAIN selection
(`V4_period55_mult2.0`) is carried forward unchanged and was chosen on TRAIN Sharpe
alone; (c) report this as a single-touch run whose TEST numbers were reproduced twice
rather than freshly discovered.

---

## 7. Pre-flight verification (everything below is re-derived, not inherited)

| # | Check | Result |
|---|-------|--------|
| V1 | Cache `_ohlc.pkl` vs a fresh `load_universe` | **IDENTICAL**, max abs diff 0.0 on all three panels (`verify_cache.py`) |
| V2 | Vectorised port vs the real `AtrTrailingStrategy` class | **100% agreement, 32,298 bars, 0 mismatches**; ATR diff 2.8e-14, SMA diff 4.5e-13 (`verify_port.py`) |
| V3 | OHLC invariants `high>=close>=low` | 7 cells out of ~222,000 violate, all float-rounding (max 0.000%), **0 in TEST**, 4 in TRAIN all pre-2015 (`verify_ohlc.py`) — immaterial |
| V4 | `stage1_train` re-run | all 5 rows **bit-identical**; selection = `V4_period55_mult2.0` again |
| V5 | `stage2_test` re-run | **bit-identical** on every field incl. random control and yearly table |
| V6 | Look-ahead perturbation test | corrupting **316 future bars by ×1.50–×2.50** moved **0 of 17,712** weight cells at/before the cut. Control: a 1-day score shift moves weights by up to 10pp, so the test is not vacuous. **No look-ahead.** |
| V7 | `.venv/bin/ruff check` on all scratch files | All checks passed |

**Conclusion on provenance: the prior run's numbers are real and reproduce exactly.**
The mtime discrepancy I flagged (common.py edited after stage1) turned out to be
cosmetic — stage1 re-ran bit-identically.

### Bug found in the inherited harness (fixed in my scratch copy, not in `src/`)

`common.buy_and_hold` reported a **gross CAGR below its own net CAGR** — old value
gross 18.11% vs net 21.50%, which is arithmetically impossible. The gross-up step was
wrong. Corrected to `(1+rate) * (1+total_return)`; it now reports gross 21.50% > net
21.46%, consistent with a single 21.92 bp charge spread over 8.1 years. This is a
**benchmark-reporting** defect only — it never touched a strategy row (all 5 strategy
TRAIN rows and all TEST rows are bit-identical before and after). Not filed upstream
because `research/` scratch is not part of the shipped package.

---

## 8. TEST results — 2024-01-01 → 2026-10-01

Frozen TRAIN selection: **`V4_period55_mult2.0`** (period=55, multiplier=2.0), chosen
by TRAIN Sharpe 0.372 before TEST was opened. **685 bars. 33 monthly rebalances.**
Net of the full Indian delivery stack at **21.92 bps round trip**.

| Metric | **atr_trailing_stop** | buy & hold (equal wt) | nsealgo composite |
|--------|----------------------:|-----------------------:|------------------:|
| Total return | **−4.32%** | +24.63% | +19.50% |
| **CAGR** | **−1.56%** | **+8.16%** | **+6.55%** |
| **Sharpe** | **−0.63** | **+0.18** | **+0.07** |
| **Max drawdown** | **−23.29%** | **−15.91%** | **−14.84%** |
| **Calmar** | **−0.07** | **+0.51** | **+0.44** |
| Turnover / yr | 4.11x | 2.00x | 2.07x |
| Cost drag / yr | 1.00% | 0.08% | 0.55% |
| Avg names held | 25.1 | 48.0 | 21.3 |
| Avg invested | 74.7% | 100% | 87.2% |
| **Gross CAGR (pre-cost)** | **−0.67%** | +8.24% | +7.04% |
| Positive years | 2/3 | 2/3 | 3/3 |

Year by year (net of costs):

| Year | strategy | equal-weight | composite | alpha vs EW |
|------|---------:|-------------:|----------:|------------:|
| 2024 | +14.24% | +19.87% | +22.57% | **−5.63%** |
| 2025 | +0.52% | +13.34% | +7.16% | **−12.82%** |
| 2026* | −16.68% | −8.27% | −9.01% | **−8.41%** |

\* 2026 is a 9-month partial year (data ends 2026-10-01).

### 8.1 Brief §6 sanity checks

| # | Check | Verdict |
|---|-------|---------|
| 1 | Plausibility | CAGR −1.56%. No 200%+ bug. **OK** |
| 2 | Weight count | mean 25.1 vs 22 target — **investigated, not a bug**. 70% of bars sit at the engine's `max_names=30` ceiling, but 100% of the rank-23+ positions are **<2% of the book** (median 0.44%). Effective book = **18.2 names ≥1% of capital**. Cause is the documented turnover-budget blend between `n_positions=22` and `max_names=30`, not residual accretion (`weight_count.py`) |
| 3 | Signal liveness | 28.8% of symbol-bars flagged +1. Well above the 5% "always-flat" floor. **Not** a flat book |
| 4 | Cost drag | gross −0.67% → net −1.56%. **Loses before costs too.** Cost stress: zero-slippage −1.16%, double −1.96%, triple −2.37%. The strategy is not rescued by cheaper trading |
| 5 | Random control | strategy Sharpe −0.63; 30-seed random mean −0.23 (sd 0.13); **P(random beats strategy) = 100%**. It lost to a coin flip on every seed |

### 8.2 vs buy-and-hold, and vs the nsealgo composite

- vs buy & hold: **worse by 9.72 pp/yr** in CAGR, **deeper drawdown by 7.39 pp**
  (−23.29% vs −15.91%), Sharpe −0.81 worse, Calmar −0.58 worse. Worse on **both** axes.
- vs nsealgo composite: **worse** on every metric — CAGR −1.56% vs +6.55%, Sharpe
  −0.63 vs +0.07, MaxDD −23.29% vs −14.84%.

---

## 9. Robustness — all 5 declared variants on TEST

Reported to show the negative result is not an artefact of one parameter pair.
**Selection stays frozen at V4. No re-selection was performed.**

| Variant | period | mult | CAGR | Sharpe | MaxDD | Turn | Names |
|---------|-------:|-----:|-----:|-------:|------:|-----:|------:|
| V1 | 14 | 2.0 | −0.95% | −0.83 | −13.25% | 3.01x | 8.0 |
| V2 | 14 | 1.5 | **+1.17%** | −0.49 | −17.28% | 3.74x | 16.8 |
| V3 | 20 | 2.5 | +0.07% | −0.75 | −11.40% | 2.84x | 7.0 |
| **V4 (frozen)** | 55 | 2.0 | −1.56% | −0.63 | −23.29% | 4.11x | 25.1 |
| V5 | 10 | 3.0 | −0.68% | −3.63 | −2.95% | 0.15x | 0.1 |

**Every variant has a negative Sharpe on TEST. Not one of the five is viable.**
Even the pre-registered V5 prediction held: period=10/multiplier=3.0 fires on only
0.3% of bars and is permanently near-flat.

---

## 10. Why it fails — three independent pieces of evidence

### 10.1 The signal's own information coefficient is *negative* (TRAIN only)

Spearman IC between the strategy's continuous output — distance of close above its
SMA **measured in ATR units** — and the realised next-21-day cross-sectional return:

| Signal | mean IC | sd | t | months IC>0 |
|--------|--------:|---:|---:|------------:|
| **breakout distance / ATR(55)** | **−0.0402** | 0.2476 | **−2.22** | 85 / 187 |
| 126-day momentum (the overlay) | +0.0049 | 0.2678 | +0.25 | 100 / 185 |

The strategy's native signal is **significantly contrarian** at a monthly horizon
(t = −2.22, rejects zero at 5%). The momentum overlay layered on top is
indistinguishable from noise (t = +0.25). So the book is a random draw of names paying
4.11x annual turnover — which is exactly the observed outcome.

This is consistent with `src/nsealgo/factors/core.py`, which documents that
multiple-testing-corrected Indian technical evidence found trend-following rules
survive while Bollinger-style band rules failed; a symmetric ±ATR band around an SMA
is the same family of object.

### 10.2 The TRAIN "selection" was really just cash drag (this is the key insight)

Regressing CAGR on how much of the book was invested, across all 5 declared variants:

| Window | corr(avg_invested, CAGR) | R² |
|--------|------------------------:|---:|
| **TRAIN** | **+0.9833** | **0.9669** |
| TEST | −0.1175 | 0.0138 |

On TRAIN, **96.7% of the variance in variant performance is explained by how much cash
the variant happened to hold.** The ordering of the five variants is monotone in
`avg_invested`:

| Variant | invested | TRAIN CAGR |
|---------|---------:|-----------:|
| V5 (10, 3.0) | 2.0% | −0.34% |
| V3 (20, 2.5) | 32.1% | +3.31% |
| V1 (14, 2.0) | 33.7% | +5.15% |
| V2 (14, 1.5) | 54.9% | +8.88% |
| **V4 (55, 2.0)** | **75.8%** | **+10.70%** |

**V4 did not win the TRAIN selection because the ATR band carries information. It won
because a 55-day SMA with a 2×ATR band is the loosest gate in the set — it holds the
most names, so it sits closest to a passive long index and suffers the least cash
drag.** The "signal" is a dial on market exposure. Had the market gone down, the
ranking would have inverted.

### 10.3 On TRAIN the strategy already lost to a coin flip

| TRAIN, 2016–2023 | CAGR | Sharpe |
|------------------|-----:|-------:|
| **V4 strategy** | +10.70% | **+0.37** |
| random control (30 seeds, same #names long) | +12.59% | **+0.54** |
| buy & hold | +21.46% | +0.90 |
| nsealgo composite | +21.30% | +0.96 |

**P(random Sharpe > strategy Sharpe) = 93%** — even *in-sample*. A random draw of the
same number of names beat the strategy on **28 of 30 seeds**, putting it in the **7th
percentile** of random selection. There was never a TRAIN edge to decay; the positive
in-sample CAGR was entirely long-only beta net of a cash buffer.

### 10.4 Directional check — the band is symmetric and informationless

Diagnostic control using V4's frozen parameters (this is a *diagnostic*, not a 6th
variant — it introduces no new parameter):

| Construction | TRAIN CAGR | TRAIN Sharpe | **TEST CAGR** | TEST Sharpe |
|-------------|-----------:|-------------:|--------------:|------------:|
| band +1 → momentum rank (as reported) | +10.70% | +0.37 | −1.56% | −0.63 |
| band +1 → equal weight, no momentum | +9.56% | +0.29 | −2.00% | −0.68 |
| **INVERSE: band −1 (the "sell" side)** | +8.49% | +0.21 | **+3.23%** | **−0.28** |

Buying the names the strategy flags as *extended below* their SMA — the mirror image of
the strategy — **beats the strategy by 4.79 pp/yr on TEST**. Same gates, same costs,
same portfolio constraints, opposite sign. That is the IC result of §10.1 expressed in
P&L, and it is the most useful single fact in this report.

> **This was NOT adopted as the result.** TEST was already open when I computed it, so
> flipping the sign on the strength of it would be exactly the contamination the brief
> forbids. It is reported as a hypothesis for a future, pre-registered run — see §12.

---

## 11. Bugs / issues found

| # | Where | Severity | Finding |
|---|-------|----------|---------|
| B1 | `research/agent_atr_trailing/common.py` (inherited scratch) | Medium | `buy_and_hold` reported **gross CAGR < net CAGR** (18.11% vs 21.50%) — impossible. Gross-up formula wrong. Fixed in my scratch copy; benchmark reporting only, never affected a strategy row |
| B2 | `src/nsealgo/backtest/engine.py` — observation, not a bug | Low | `n_positions=22` with `max_names=30` plus turnover-budget blending parks the book at the 30-name ceiling on 70% of TEST bars, with ~98% of the excess names holding <2% each. Correct per design, but the nominal name count overstates the real book (18.2 names ≥1%) and the dust costs turnover. Worth knowing when reading `avg_names` in any nsealgo report |
| B3 | `src/cryptobot/strategies/catalog/atr_trailing_stop.py` — **naming defect** | Medium | The file is named `atr_trailing_stop` but implements a **volatility-normalised breakout band around an SMA**. It holds no peak, never trails, has no stop. Anyone triaging the catalog by filename will mis-attribute this result. A trailing stop is a genuinely different object and should be evaluated separately |
| B4 | data | Info | 7 of ~222,000 `high/low` cells violate `high>=close>=low`, all sub-0.001% rounding artifacts; **zero** occur in TEST. No impact |

No bug was found in `src/nsealgo`'s signal, cost, or metrics code. Costs were verified
against the brief's published figures (`11.92` statutory, `21.92` all-in) and match.

---

## 12. Verdict

**Does `atr_trailing_stop` make money on NSE? NO.** Out-of-sample it returned
**−1.56% CAGR / −0.63 Sharpe / −23.29% MaxDD** over 2024-01-01 → 2026-10-01, versus
+8.16% for buy-and-hold and +6.55% for the nsealgo composite — worse on return *and*
deeper in drawdown, and it lost to a matched random signal on **30 of 30** seeds.

**Most likely reason:** the signal carries no useful cross-sectional information and
its monthly-horizon IC is in fact *significantly negative* (−0.040, t = −2.22), so the
strategy systematically buys the names that were most extended above their SMA — the
cohort that mean-reverts. What looked like in-sample skill was market beta net of a
cash buffer (R² = 0.97 against `avg_invested`), and it beat neither buy-and-hold,
nor the composite, nor a coin flip, even in-sample.

**One thing I would try next (pre-registered, on data this strategy has never seen):**
re-run the band with the **sign inverted** — buy only names where
`close < SMA − mult×ATR`, rank by the same 126-day momentum — as a **fresh,
separately-declared variant on a TRAIN window that ends before 2024**, then evaluate
once on TEST. §10.4 says the mirrored book returned **+3.23% CAGR on TEST** against the
strategy's −1.56%, and §10.1 says the IC says to expect that in advance rather than in
hindsight. It must be pre-registered and tested on data disjoint from this run,
otherwise the +3.23% is already contaminated and worthless.

Second-order, if that also fails: the honest conclusion is that **symmetric volatility
bands have no place in this catalog's NSE book at all** — they are cash-drag dials.
That is worth knowing before another agent spends a budget on the next band-shaped
strategy.

---

## 13. Reproduce

```bash
cd research/agent_atr_trailing
VENV=/home/ph03n1x/trade/.venv/bin/python
$VENV verify_cache.py       # mandatory load_universe + cache integrity
$VENV verify_ohlc.py        # OHLC invariant audit
$VENV verify_port.py        # port == catalog class, 32k bars
$VENV stage1_train.py       # TRAIN only, 5 declared variants -> selection
$VENV stage1b_diag.py       # TRAIN random control + composite
$VENV stage2_test.py        # TEST, single touch
$VENV stage3_robustness.py  # TEST robustness + TRAIN-only IC
$VENV final_diag.py         # cash-drag regression, direction check, look-ahead proof
$VENV weight_count.py       # brief §6.2 weight-count audit
```

Parameter budget: **5 variants declared and 5 variants run. Not exceeded.** No
threshold was tuned against an equity curve. TEST was opened once by the interrupted
prior run and its numbers were reproduced bit-identically here without any intervening
tuning — see §6.

> Note: importing `cryptobot.strategies` (needed by `verify_port.py`) instantiates a
> SQLite file in the CWD. A stray `research/agent_atr_trailing/cryptobot.db` was
> created by that import and has been deleted; it is not part of the deliverable.

*Not committed, per brief §9. `src/nsealgo/**`, `src/cryptobot/**`, `GOAL.md` and
`reports/` were not modified (verified with `git status`).*
