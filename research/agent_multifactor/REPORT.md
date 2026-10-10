# AGENT REPORT — `multi_factor_strategy` on NSE NIFTY-50

> **Status: COMPLETE.** Written before any backtest ran (header + declared parameter
> budget committed first per `AGENT_BRIEF.md` §8), then appended as results arrived.

| Field | Value |
|---|---|
| **Assigned strategy** | `multi_factor_strategy` |
| **Source** | `src/cryptobot/strategies/catalog/multi_factor_strategy.py` |
| **Class** | `MultiFactorStrategy` (`name = "multi_factor"`), a `SignalStrategy` |
| **Data** | `data/nse/<sym>_1d.csv` via `load_universe("data/nse")` — **48** names, 2008-01-01 → 2026-10-01 |
| **Timeframe** | 1d only |
| **TRAIN** | 2016-01-01 → 2023-12-31 (all parameter selection) |
| **TEST** | 2024-01-01 → 2026-10-01 |
| **Costs** | `CostModel(segment="delivery", slippage_bps=5)`; `run_backtest` charges **21.92 bps** all-in. All results net of that. |
| **Portfolio** | `PortfolioConfig()` defaults — 22 names, 12% single, 25% sector, 10% cash, 35% turnover budget, monthly rebalance |
| **Engine revision** | `src/nsealgo/backtest/engine.py` md5 `24da076e8225a2d8b4283f888d6f2a3c` (see §6) |
| **Not crypto-specific** | Price-vs-SMA + RSI only. No funding/liquidation/peg/IV/basis content → assignment proceeds. |

---

## 1. What the strategy does

```python
def signal(self, closes, highs, lows, volumes):
    t = sma(closes, self.config.period)          # simple MA, last `period` closes
    r = rsi(closes, self.config.rsip)            # simple-average RSI (NOT Wilder)
    if t != t or r != r:
        return 0
    score = (1 if closes[-1] > t else -1) + (1 if r > 50 else -1)
    return 1 if score >= 2 else (-1 if score <= -2 else 0)
```

Two binary votes, summed. `+2` → both agree up → **+1 (long)**; `−2` → both agree down
→ **−1 (short)**; `0` → they disagree → **flat**.

It is a *confluence filter* on a ~1-month trend and a ~2-week momentum oscillator.
Despite the name it is **not** a multi-factor model: two price-derived factors, no
cross-sectional or fundamental inputs, no weighting — just unanimity. Tradable
content of a long-only Indian delivery book is exactly "hold the names above their
1-month average that also have positive 2-week momentum".

**Faithfulness check (mandatory, and it passed).** I reimplemented the signal
vectorised and compared it to the real `MultiFactorStrategy.signal()` on random
(symbol, date) pairs: **286 agree / 0 disagree**, and **0 differing cells out of
222,000** versus a from-scratch independent reimplementation for all three
parameter sets. The vectorised and independent implementations are cell-identical.

---

## 2. Declared parameter budget — 5 variants, fixed before any run

| # | Variant | `period` | `rsip` | Gate | Rank among flagged |
|---|---|---|---|---|---|
| **V1** | authored baseline | 20 | 14 | `close>SMA & RSI>50` | 126d momentum |
| **V2** | short-horizon rank | 20 | 14 | same | 21d momentum |
| **V3** | slower trend filter | 50 | 14 | same | 126d momentum |
| **V4** | authored + fill rule | 20 | 14 | same | 126d; top up from unflagged if <22 flagged |
| **V5** | slower oscillator | 20 | 21 | same | 126d momentum |

**Exactly 5 tested. No sixth.** Selection on TRAIN Sharpe; the winner went to TEST
unchanged. Buy-and-hold, the random control and the composite benchmark are
mandated controls, not variants. Fixed for every variant: `PortfolioConfig()`
defaults, `rebalance="M"`, `initial_capital=2_100_000`.

---

## 3. Results

### 3.1 Data load

```
rows in 274,541 → rows out 208,226 | dropped pre-2008 66,312 | extreme 3
excluded: ['adanient', 'jiofin']     panel (4625, 48)   2008-01-01 → 2026-10-01
```

**48 tradable names, not 50** — `adanient` is the documented corrupt exclusion, and
`jiofin` fails the 1000-bar minimum (listed 2023). Everything below is a 48-name
universe. (Harness note: the panel index is tz-aware `Asia/Kolkata`; naive window
bounds crash it.)

### 3.2 Cost sanity check

`nsealgo.cli costs` reproduces the published 11.65–11.66 bps reference
(11.92 at ₹1,00,000). Confirmed: `round_trip_bps(100k)=11.92`,
`all_in_round_trip_bps(100k)=21.92`. **Every result is net of 21.92 bps.**

### 3.3 TRAIN — all 5 variants

**Liveness:** long 43.0–49.7% of `(name, bar)` observations in TRAIN. Far above the
5% always-flat floor. The AND-gate is not sparse.

**Flagged names/day:** mean 22.1–23.9, median 22–24, but **fewer than 22 flagged on
42–49% of days** — the gate is mildly binding, which is what V4 was declared to price.

| Variant | CAGR | Sharpe | MaxDD | Calmar | Turn | Cost drag | Avg names | Total ret |
|---|---|---|---|---|---|---|---|---|
| V1 `p20 r14 rank126` (authored) | 8.85% | 0.27 | −23.62% | 0.37 | 4.07x/y | 2.45%/y | 18.8 | +98.5% |
| V2 `p20 r14 rank21` | 6.92% | 0.09 | −26.42% | 0.26 | 4.15x/y | 2.29%/y | 18.8 | +71.8% |
| V3 `p50 r14 rank126` | 8.81% | 0.26 | −24.23% | 0.36 | 4.02x/y | 2.38%/y | 17.7 | +98.0% |
| V4 `p20 r14 rank126 fill` | 9.71% | 0.29 | **−36.60%** | 0.27 | 3.97x/y | 2.43%/y | 22.0 | +111.6% |
| **V5 `p20 r21 rank126`** ← selected | **9.56%** | **0.33** | −26.22% | 0.36 | 4.09x/y | 2.62%/y | 18.2 | +109.3% |
| *[ctrl] B&H eod (48)* | 21.56% | 0.90 | −36.66% | 0.59 | — | 0.02%/y | 48.0 | +385.0% |
| *[ctrl] B&H monthly-eq* | 19.05% | 0.85 | −32.89% | 0.58 | 0.29x/y | 0.24%/y | 48.0 | +309.6% |

**Selection: V5** — best TRAIN Sharpe (0.33). Same winner under every harness state
I ran (see §5), so the selection was never contingent on a bug.

**Two TRAIN findings:**
1. **All five lose to buy-and-hold on TRAIN, by 9.4–12.0pp of CAGR.** This is not
   an overfitting signature — the strategy fails even where it is allowed to cheat.
2. **V4's fill rule made MaxDD 13pp worse** (−23.6% → −36.6%). Topping the book up
   with names the gate *rejected* imports exactly the losers the gate was filtering.
   "Not flagged" is informative; do not dilute it.

### 3.4 TEST — V5, unchanged

`2024-01-01 → 2026-10-01`, net of 21.92 bps, `PortfolioConfig()` defaults.

| Book | CAGR | Sharpe | MaxDD | Calmar | Turnover | Cost drag | Avg names | Total ret |
|---|---|---|---|---|---|---|---|---|
| **V5 NET** | **1.79%** | **−0.38** | **−18.97%** | 0.09 | 4.13x/y | 2.10%/y | 18.1 | +5.1% |
| *V5 GROSS (cost removed)* | 3.65% | −0.21 | −15.83% | 0.23 | — | — | 18.1 | +10.6% |

- Liveness 43.5%. Rebalances 34. Avg names 18.1.
- Cost drag **2.10%/y**, 4.96% of terminal wealth cumulatively; gross→net CAGR
  erosion **1.86pp**.
- Yearly: **2024 +19.80%, 2025 −1.41%, 2026 −11.02%.** Positive in **1 of 3** years
  (`GOAL.md` §5 Gate 3 wants 60%).
- Sharpe is **negative**. Gross-of-cost Sharpe is negative too (−0.21), so this is
  not a cost problem — the signal is losing before costs are charged.

### 3.5 TEST vs buy-and-hold (identical window)

| Book | CAGR | Sharpe | MaxDD | Calmar |
|---|---|---|---|---|
| V5 | 1.79% | −0.38 | −18.97% | 0.09 |
| B&H eod (`panel.pct_change().mean(axis=1)`, one round trip at inception) | 8.22% | 0.19 | −15.90% | 0.52 |
| B&H monthly equal-weight, cost-charged | 7.40% | 0.13 | −14.50% | 0.51 |

**Worse on both axes: −6.43pp CAGR and −3.07pp MaxDD vs B&H eod** (−5.61pp CAGR
vs the comparable monthly-rebalanced book). It gives up ~30% of the return *and*
takes a deeper drawdown to do it.

*(B&H holds all 48 names, so it breaches the 22-name/12%/25%-sector caps. It is a
benchmark, not a deployable book. The strategy is still beaten by a book that isn't
deployable — which is the more damning comparison.)*

### 3.6 TEST random-signal control

Same overall % long (0.4379 = V5's full-history liveness), same 126d rank, same
portfolio rules, 20 seeds.

| Window | median CAGR | median Sharpe | p90 CAGR |
|---|---|---|---|
| TRAIN null | 10.66% | 0.41 | 12.36% |
| TEST null | 3.22% | −0.33 | 4.12% |

**V5 TEST Sharpe −0.38 vs null median −0.33 → it beats only 40% of random signals
(p = 0.40). V5 CAGR 1.79% vs null median 3.22%.**

**It loses to a coin flip.** `AGENT_BRIEF.md` §6.5 calls beating a coin the minimum
bar; this does not clear it.

### 3.7 TEST vs nsealgo composite

| Book | CAGR | Sharpe | MaxDD | Calmar | Turnover | Drag | Names |
|---|---|---|---|---|---|---|---|
| V5 | 1.79% | −0.38 | −18.97% | 0.09 | 4.13x/y | 2.10%/y | 18.1 |
| `build_composite_score` | 7.61% | 0.14 | −15.22% | 0.50 | 2.04x/y | 1.12%/y | 22.0 |

**−5.82pp CAGR, −0.52 Sharpe, 3.75pp worse drawdown.** The composite dominates on
every axis and costs half the turnover.

### 3.8 Sanity checks (`AGENT_BRIEF.md` §6)

| # | Check | Result |
|---|---|---|
| 1 | Plausibility (≤40–50% CAGR) | 1.79% — **OK** |
| 2 | Weight count (~22) | 18.1 — **OK**, ≤ `max_names=30`. See note below. |
| 3 | Signal liveness (>5%) | 43.5% — **OK** |
| 4 | Cost drag; gross>0 & net<0? | gross 3.65% → net 1.79%. Not a cost failure — gross is also poor. |
| 5 | Negative control | **FAILS** — loses to a coin flip (40th percentile). |

Note on #2: `n_positions=22` is *not* the realised holdings count. The turnover
blend routinely carries 32 names before `_thin` caps at `max_names=30`, so 30 is the
real cap and 18.8/18.1 is the realised average. This is the engine defect in §5.

---

## 4. Verdict

**No. `multi_factor_strategy` does not make money on NSE NIFTY-50.** It returns
**1.79% CAGR / Sharpe −0.38** out of sample versus **8.22% / 0.19** for
buy-and-hold, it beats a random signal only 40% of the time, and it is beaten by the
project's own composite on every metric. The result is not marginal or
borderline-failing: it is negative-Sharpe, positive in 1 of 3 years, and it loses to
a coin flip.

**Most likely reason:** the strategy has **no cross-sectional information at all**.
Both votes are time-series properties of a single name; the "multi-factor" label
describes two correlated price transforms of the same series. Averaging two votes
over the same input adds no information beyond a slightly slower, noisier version of
one trend filter — and it is then asked to pick 22 names, so the ranking step has to
supply all the selection. What survives is short-horizon price momentum ranked
among names that already have short-horizon price momentum: redundant, late, and
turning over 4.1x/yr for a 2.10%/y bill. The evidence for why this is structural
rather than a tuning failure is that it loses on TRAIN too, where selection is free.

**One thing I would try next** (not done — would have exceeded the 5-variant budget):
keep the gate as a **risk/quality screen** and take the selection entirely from a
factor that is not derived from the same price path — e.g. gate on the signal, rank
by `low_volatility` (the one Indian factor with strong independent long-only
support) rather than by 126d momentum. That tests the actual hypothesis — "confluence
is a filter, not an alpha source" — instead of re-rolling the momentum dice.

---

## 5. BUG found in `src/nsealgo/backtest/engine.py` — full write-up in `ENGINE_BUG.md`

**`run_backtest` silently under-invests the book: it holds 0.595 of equity, not the
0.90 that `cash_buffer=0.10` specifies.**

Cause chain (measured, not guessed):

1. `build_rebalance_weights` targets themselves average only **0.8345**, not 0.90,
   because `_project_constraints` leaves mass it cannot legally place as cash — and
   on thin-coverage dates the target collapses to 0.216. This is the dominant term.
2. A 22-name book rotating monthly demands ~0.90 one-way turnover, but
   `turnover_budget=0.35` binds on **85.3%** of rebalances.
3. Under the pre-rewrite engine, `lam≈0.74` left old positions unsold, the blended
   book carried ~32 names, and `_thin` truncated to `max_names=30` by **zeroing**
   rather than redistributing — a further ~1.7pp of weight lost per rebalance.

Impact: **TRAIN CAGR 9.56% → 13.72% (+4.16pp) at `budget=1.0`**, ~36% of the gross
TRAIN return. The composite is **immune** (turnover demand under budget → exactly
0.900/22.0 at either budget), which is why the project's reference implementation
never exposed it. Any strategy rotating faster than the composite is silently
penalised.

**A parallel agent has since rewritten `apply_turnover_budget`** (exit-first,
adopt-with-surplus), reaching the same diagnosis of the stale-tail half. **The
under-investment survives it**: 0.5934 → 0.5954, still ~0.30 short of 0.90. The
remaining defect lives in `_project_constraints`, not in the budget.

**It does not rescue this strategy:** on TEST, `budget=1.0` gives 1.31% vs 1.79% —
marginally *worse*. The engine defect is a real distortion of TRAIN-phase results
across the project, but it is not the reason this strategy fails.

## 6. Disclosures

I am required to disclose these rather than hide them.

- **My harness had a bug.** An earlier state produced V1 TRAIN CAGR 13.27% with 28.7
  names held; the final state produces 8.85% with 18.8. I caught it because 28.7
  (TRAIN) was inconsistent with 18.1 (TEST) for the same config. I resolved it by
  writing `verify_independent.py`, a from-scratch reimplementation: it reproduces the
  final numbers and confirms 0/222000 differing signal cells. All numbers come from
  the final, lint-clean, deterministic state, verified identical across three process
  runs. `run_backtest` was separately confirmed non-mutating and order-independent.
- **The TEST window was computed more than once.** Once on the buggy harness
  (1.73%), then again after the fix (1.79%). Per `AGENT_BRIEF.md` §4 rule 4 I state
  this plainly. **No parameter was chosen using TEST.** Selection was TRAIN-Sharpe
  only and picked **V5 identically under the buggy and the corrected TRAIN tables**,
  and only V5 was ever scored on TEST. The conclusion did not depend on harness state.
- **`src/nsealgo/backtest/engine.py` was edited by another agent twice while I was
  working.** Every number here was therefore re-verified against a hash-pinned
  revision (`md5 24da076e8225a2d8b4283f888d6f2a3c`), stable before and after the run.
  **Results are byte-identical across engine revisions `b515819…` and `24da076…`** —
  this strategy's verdict is robust to that rewrite. Use `final_run.py`, which
  re-runs until the engine hash holds still.
- `ruff --fix` altered results once (it silently rewrote an import in a way that
  changed a number). Fixed and re-verified; the tree is lint-clean.

## 7. Files

| File | Purpose |
|---|---|
| `harness.py` | Vectorised signal + score construction + window metrics + controls |
| `sweep_train.py` | TRAIN sweep, all 5 declared variants |
| `eval_test.py` | TEST evaluation of V5 + all controls |
| `verify_independent.py` | From-scratch reimplementation used to arbitrate the harness bug |
| `diag_weights.py` / `diag_budget.py` / `diag_engine.py` | Engine under-investment diagnostics |
| `disclosure_budget.py` | TRAIN/TEST attribution vs `turnover_budget` |
| `final_run.py` | Hash-pinned authoritative TEST run (retries until the engine stops changing) |
| `ENGINE_BUG.md` | The engine defect, for the project |
| `train_results.json` / `test_results.json` | Machine-readable results |

Nothing under `src/` was modified by me. `.venv/bin/ruff check research/agent_multifactor/`
passes. No commits made.