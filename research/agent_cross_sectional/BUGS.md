# BUG / OBSERVATION LOG — `cross_sectional` agent run

Bugs are the most valuable output of this exercise. Nothing in `src/**` was modified;
these are findings only.

---

## B1 — `run_backtest` treats an all-NaN score row as "sell the whole book", bypassing
## the turnover budget. Severity: LOW for results, **HIGH as a live-trading hazard**.

**Where:** `src/nsealgo/backtest/engine.py`
* `build_rebalance_weights` — `if not valid.any(): continue` (line ~261) leaves the whole
  target row at zero.
* `apply_turnover_budget` — `changed = one_way_turnover(tgt, cur)` (line ~334).

**Mechanism.** When the score panel has no finite value in any name on a rebalance date,
`build_rebalance_weights` emits an **all-zero target**. `apply_turnover_budget` then sees
`prev` (the previous *target*) summing to e.g. 0.39, computes
`changed = 0.5 × 0.39 = 0.19`, which is *below* the 0.35 budget, so `lam = 1.0` and the
book is liquidated in a single step. The 35% turnover budget is measured **target-to-target**,
so a target of zero always looks "cheap" — it can never be throttled.

Observed on the full history with V1 (catalog defaults, 20d / ±1.5%):
```
2008-09-01  25 eligible names -> invested 90.00%
2008-10-01   2 eligible names -> invested 38.81%   (Oct-08 crash)
2008-11-03   0 eligible names -> invested  0.00%   <-- instant full liquidation
2008-12-01   9 eligible names -> invested 70.00%
```
Under a correct turnover budget the November step should have been `38.81% × (1−0.35/0.19)… `
— i.e. a small reduction, not a jump to zero. In effect the book gets one free, unbudgeted,
un-costed-in-spirit round of selling into the worst tape of the sample.

**Why it matters.** An all-NaN score row has two very different causes that the engine
cannot distinguish:
1. *genuine* — a long-only "buy winners" strategy in a crash has no winners, and going to
   cash is arguably correct behaviour; or
2. *accidental* — a data outage / vendor gap / universe change makes every column NaN for
   one month, and the engine silently liquidates the live book with no warning.

Cause (2) is a real money-losing failure mode and the engine gives no signal.

**Scope of impact on the reported result: NONE.** V1 has exactly 3 such dates —
2008-01-01, 2008-07-01, 2008-11-03 — all before the TRAIN window starts. Enumerated for all
five declared variants: TRAIN occurrences = V1 0, V2 0, V3 0, V4 0, V5 4; **TEST occurrences =
0 for every variant.** So the reported TEST number is unaffected either way. (V5's TRAIN
Sharpe — which did not win the selection — is mildly affected.)

**Suggested fix (not applied).** Distinguish "no valid names" from "target is zero":
either (a) skip the rebalance and carry `prev` forward when `not valid.any()`, or
(b) route the degenerate all-zero target through a *held-book*-relative turnover check so
the 35% budget actually binds. Option (b) alone is not enough, because a genuine all-cash
target should still be reachable eventually. Also worth a warning log line.

---

## B2 (minor, harness-only, already fixed here) — buy-and-hold benchmark was
## double-charged and its turnover was reported 2× too high.

`buy_and_hold()` in `research/agent_cross_sectional/common.py` charged the **full**
`all_in_round_trip_bps` (21.92 bps) for a **one-way** deployment and reported
`annual_turnover = 2.0/years` where the engine's own definition is one-way turnover
per year (= `1.0/years`).

Effect: buy-and-hold's benchmark was made ~0.11% too poor in total and its turnover 2× too
high. Fixed before the reported run (now `one_way = rate/2`, `annual_turnover = 1.0/years`).
This made the benchmark *stronger* by +0.05 pp/yr CAGR (8.16% → 8.21%) — i.e. it works
against my own strategy, so fixing it is the conservative direction. No other number moved.

---

## B3 (documentation, not a code bug) — the declared tie-break rule was worded backwards.

`20_train_select.py`'s docstring declared "ties broken by lower TRAIN MaxDD". `max_drawdown`
is stored **negative**, so "lower" means *deeper* drawdown, while the code
(`sort_values(["sharpe","maxdd"], ascending=[False, False])`) actually selects the
**shallowest**. The code was right and the prose was wrong. Reworded to "shallowest" and a
comment added at the sort site. Outcome unchanged — V1's TRAIN Sharpe 0.573 is the unique
maximum, so the tie-break was never exercised.

---

## B4 (observation about the assigned strategy, not a harness bug) — the catalog strategy
## is not cross-sectional, and on NIFTY-50 its long leg is *negatively* predictive.

`cross_sectional_strategy.py` computes only `roc(closes, period)` per symbol. Nothing in it
compares symbols, so "cross-sectional" is a misnomer — it is a per-symbol time-series
momentum gate. Worse, on this panel its long-minus-short spread at the natural 21-bar
horizon is **negative on both windows**:

| window | long ann. fwd21d | short ann. fwd21d | long − short |
|--------|------------------|-------------------|--------------|
| TRAIN 2016–2023 | +21.67% | +23.93% | **−2.26 pp/yr** |
| TEST 2024–2026 | +7.57% | +14.38% | **−6.82 pp/yr** |

and the cross-sectional rank IC of ROC20 vs forward 21-bar return is negative on both
(−0.0331, t = −8.16 TRAIN; −0.0193, t = −2.17 TEST). On Indian large caps at a ~1-month
horizon, 20-day ROC is a **reversal** signal, not a momentum signal — so a long-only book
built on it is structurally long the losing side. See `REPORT.md` §8.