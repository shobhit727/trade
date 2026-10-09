# `dual_momentum` on NSE NIFTY-50 — validated negative finding

**Verdict: NO. This strategy does not make money on NSE. It lost to buy-and-hold, to
the nsealgo composite, and — decisively — to a coin flip with the same % of bars long.**

---

## 1. What the strategy is

`src/cryptobot/strategies/catalog/dual_momentum_strategy.py` → `DualMomentumStrategy`,
`name = "dual_momentum"`.

Per-symbol time-series signal, +1/0/−1:

```python
f = ema(closes, fast)      # default 10
s = ema(closes, slow)      # default 30
return 1 if f > s else -1
```

`warmup = slow`; `ema()` returns NaN on a short window, so no signal exists for the
first `slow` bars and those name-days are untradeable rather than falsely flat.

**Not crypto-specific** — no funding, no liquidations, no pegs, no IV, no basis. It has a
perfectly good NSE meaning, so this is a real result and not an early exit.

### Translation into the book
Long-only, so `-1` (short) maps to *flat*, not to a short position. The AGENT_BRIEF §5
recipe is used **verbatim**:

```python
score = (panel / panel.shift(126) - 1.0).where(signal_panel > 0).rank(axis=1, pct=True)
```

i.e. 6-month trailing momentum, percentile-ranked **inside the flagged subset only**,
fed to the unmodified `run_backtest` (monthly rebalance, 22 positions, 12% single name,
25% sector, 10% cash, 35% turnover budget, `CostModel(delivery, slippage_bps=5)` →
**21.92 bps charged per complete rotation**).

My vectorised EMA was verified **bit-identical** to the catalog's `ema()` (`|diff| = 0.000e+00`
at both periods), so this really is the shipped strategy and not a lookalike.

### Declared parameter budget (written before any backtest — `00_DECLARED_BUDGET.md`)

The strategy has exactly two knobs. Score construction fixed, not tuned.

| # | fast | slow |
|---|------|------|
| V1 | 10 | 30 (catalog default, verbatim) |
| V2 | 20 | 60 |
| V3 | 50 | 200 |
| V4 | 10 | 100 |
| V5 | 30 | 120 |

**5 tested. 5 is the budget. Not exceeded.** Selection rule fixed in advance: highest
TRAIN Calmar, TRAIN CAGR as tie-break. Winner: **V3 = EMA 50/200**.

**TRAIN = 2016-01-01 → 2023-12-31.** TEST = 2024-01-01 → 2026-10-01 was not touched
until `02_test_eval.py` ran, and then **only the selected variant**. The other four were
deliberately *not* evaluated on TEST, so "TEST touched once" is literally true.

---

## 2. TRAIN results (all 5 variants + references)

48 names, 2016-01-01 → 2023-12-31, net of 21.92 bps/rotation.

| name | CAGR | Sharpe | Sortino | MaxDD | Calmar | Turn/x-y | Cost drag/y | Names |
|------|------|--------|---------|-------|--------|-----------|-------------|-------|
| V1 ema10/30 | 13.78% | 0.54 | 0.64 | −33.75% | 0.41 | 3.71 | 1.37% | 25.9 |
| V2 ema20/60 | 16.00% | 0.66 | 0.77 | −33.94% | 0.47 | 3.22 | 1.26% | 22.6 |
| **V3 ema50/200** | **18.00%** | **0.77** | **0.90** | **−34.71%** | **0.52** | 2.60 | 1.16% | 21.3 |
| V4 ema10/100 | 16.49% | 0.69 | 0.80 | −33.86% | 0.49 | 3.14 | 1.24% | 22.2 |
| V5 ema30/120 | 16.56% | 0.68 | 0.78 | −35.78% | 0.46 | 2.90 | 1.17% | 21.1 |
| *composite baseline* | *21.30%* | *0.96* | *1.14* | *−32.92%* | *0.65* | 1.96 | 1.00% | 21.8 |
| *buy-and-hold* | *21.46%* | *0.90* | *1.06* | *−36.66%* | *0.59* | — | — | — |

Two things were already visible on TRAIN and I did not talk myself out of either:
the whole family **loses to buy-and-hold and to the composite**, and every variant
carries a −33% to −36% drawdown, well outside GOAL.md Band C (<35%) for all but V2.

Longer EMA ⇒ better result, monotonically. That was the first hint that the signal was
carrying almost nothing and the 6-month momentum rank underneath was doing all the work.

---

## 3. TEST results (2024-01-01 → 2026-10-01, net of the full Indian delivery stack)

| name | CAGR | Sharpe | Sortino | MaxDD | Calmar | Turn/x-y | Cost drag/y | Names |
|------|------|--------|---------|-------|--------|-----------|-------------|-------|
| **dual_momentum V3** | **3.46%** | **−0.16** | **−0.19** | **−16.55%** | **0.21** | 2.55 | 0.65% | 21.2 |
| composite baseline | 6.55% | 0.07 | 0.09 | −14.84% | 0.44 | 2.07 | 0.55% | 21.3 |
| buy-and-hold (equal-weight) | 8.16% | 0.18 | 0.25 | −15.91% | 0.51 | — | — | — |

Detail on the selected variant:

- total return **+10.03%**, vol 13.04%, win rate 50.2%, best day +3.82%, worst day −7.39%
- max drawdown **−16.55%, 131 trading days underwater**
- **33 rebalances, 11.8 trades/yr**, avg top weight 6.11% (cap 12%)
- **costs paid ₹38,198 on ₹21,00,000** — 1.82% of capital across the whole window
- yearly: **2024 +18.60% · 2025 +2.86% · 2026 (to 01-Oct) −9.81%**

Signal liveness: long on **66.5%** of symbol-bars, 30.5 names flagged per day on
average. Well above the 5% floor, so this is not an always-flat strategy — it genuinely
holds a book and genuinely loses.

### 3a. vs buy-and-hold — worse on return, worse on drawdown

| | CAGR | Sharpe | MaxDD |
|---|---|---|---|
| dual_momentum V3 | 3.46% | −0.16 | −16.55% |
| buy-and-hold | 8.16% | 0.18 | −15.91% |
| **delta** | **−4.70pp** | **−0.34** | **−0.64pp (worse)** |

Worse on *both* axes. It paid 2.55x/yr of turnover and 0.65%/y of cost to underperform
a do-nothing index on return *and* to take more drawdown doing it.

### 3b. Cost drag — costs are not the problem (`GOAL.md` Gate 4)

| model | slippage/side | CAGR | Sharpe | MaxDD | drag/y |
|---|---|---|---|---|---|
| zero cost | 0 bps | 3.73% | −0.14 | −16.43% | 0.35% |
| base | 5 bps | 3.46% | −0.16 | −16.55% | 0.65% |
| double | 10 bps | 3.20% | −0.18 | −16.67% | 0.94% |
| triple | 15 bps | 2.94% | −0.20 | −16.79% | 1.23% |

Costs cost ~0.27pp of CAGR at the base setting and ~0.8pp at triple slippage. **Even at
literally zero cost the strategy returns 3.73%** — less than half of buy-and-hold's
8.16%. This is not a strategy being killed by fees; it is a worse portfolio than plain
6-month momentum, before fees.

### 3c. Random-signal control — this is where it fails outright

20 seeds each, matched to the strategy's 66.5% of bars long, identical engine:

| control | CAGR mean | CAGR range | Sharpe mean | Sharpe range | MaxDD mean |
|---|---|---|---|---|---|
| random **gate** on the same 6m score | 4.98% | 1.91 – 7.69 | **−0.06** | −0.32 – +0.15 | −13.95% |
| fully **random** score | 4.68% | 2.37 – 9.07 | **−0.11** | −0.32 – +0.28 | −13.35% |
| **dual_momentum V3** | **3.46%** | — | **−0.16** | — | −16.55% |

**The EMA crossover is beaten by a random gate 17 times out of 20.** It beats only
**3/20** random-gate seeds and **9/20** random-score seeds (20 seeds each, identical
engine, matched 66.5% bar-liveness). It also has a *deeper* average drawdown than the
random books.

Beating a coin flip is the minimum bar. This is below the floor.

### 3d. vs the nsealgo composite

| | CAGR | Sharpe | MaxDD |
|---|---|---|---|
| dual_momentum V3 | 3.46% | −0.16 | −16.55% |
| `build_composite_score` | 6.55% | 0.07 | −14.84% |
| **delta** | **−3.09pp** | **−0.23** | **−1.71pp (worse)** |

It did not beat the composite on anything.

---

## 4. Why — TRAIN-only ablation (`03_ablation_train.py`, never saw TEST)

The holdout was already spent on the selected variant, so all diagnosis stayed on TRAIN.

**(a) The gate is significantly ANTI-predictive.** Forward 6-month return of symbol-bars,
TRAIN 2016–2023:

| set | n | mean fwd-6m | % positive |
|---|---|---|---|
| flagged (EMA50 > EMA200) | 65,224 | **11.84%** | 69.7% |
| unflagged (EMA50 ≤ EMA200) | 26,167 | **13.50%** | 67.7% |

Spread **−1.66pp per 6 months, t = −8.42**. The names the "trend filter" keeps have
*worse* forward returns than the ones it throws away. It is not a weak signal, it is an
inverted one — and it is measured at 8 sigma.

**(b) The gate barely changes the book.** It excludes 31.2% of the universe, leaving
33.0 scorable names per day against 22 slots. Those 22 slots are filled **100%** of
rebalance months either way. So the gate never starves the book and never improves the
selection — it just *substitutes* names, and the substitutes are worse.

**(c) Removing the gate entirely changes nothing on TRAIN:**

| | CAGR | Sharpe | Calmar |
|---|---|---|---|
| dual_momentum V3 (with gate) | 18.00% | 0.77 | 0.52 |
| ablation: 6m momentum, no gate | 18.38% | 0.78 | 0.53 |
| **gate effect** | **−0.38pp** | **−0.01** | **−0.01** |

The strategy *is* plain 6-month momentum, slightly damaged by its own filter. And plain
6-month momentum (18.38% TRAIN) already loses to buy-and-hold (21.46%) and the composite
(21.30%). The failure is layered: the filter subtracts, and what remains was never good
enough.

---

## 5. Integrity checks (`04_verify.py` — all PASS)

| check | result |
|---|---|
| EMA == catalog `ema()` | `\|diff\| = 0.000e+00` at period 50 and 200; signal agrees |
| **No look-ahead** — shock every price after the TRAIN cut by ±5% and ±30% | TRAIN equity end **3.8184930939 in all three runs**, bit-identical |
| Avg names held | **21.3** (not 48 → no residual-weight accretion) |
| Plausibility / compounding bug | TRAIN CAGR 18.00%, TEST 3.46% — nowhere near the 200% tell |
| Max single weight | 6.57% (cap 12%) |
| Cost model charged | 21.92 bps round-trip (11.92 statutory + 10 slippage) |

Signals are built on the full panel and then **sliced** to the window, so EMA/rolling
warm-up is satisfied by pre-window history — which a live system would also have —
rather than by eating into the evaluation window. A signal at date *t* uses closes up to
and including *t*; `run_backtest` holds `shift(1)` weights, so execution is from *t+1*.

## 6. Disclosures

- **Survivorship bias is present** — today's NIFTY-50 backfilled to 2008. Affects all
  strategies in this study equally, including the baselines.
- **The TEST window was intrinsically hard for everything**: the nsealgo composite itself
  managed only 6.55% CAGR / Sharpe 0.07 there. That is context, not an excuse — the
  strategy still underperformed both references, and a strategy that only works in good
  windows is not deployable against a 3%/month target.
- The composite figure above is a **like-for-like control in the same engine and
  window**, not the headline walk-forward validation number in `reports/`.
- Roughly 6.3% of panel cells are NaN (newer listings); `run_backtest` treats a missing
  bar as a 0% return for that symbol, identically for every strategy tested.

---

## 7. Plain verdict

**No — `dual_momentum` does not make money on NSE.** Out-of-sample it returned 3.46%
CAGR with a **negative Sharpe of −0.16**, underperforming buy-and-hold by 4.70pp of
annual return *and* taking 0.64pp more drawdown, while losing to a random coin flip
17 times out of 20.

**Most likely reason:** the EMA crossover is a weak, lagging trend filter that adds no
information to a cross-sectional momentum rank — its flagged names have *significantly
worse* forward returns than the names it excludes (t = −8.42) — so it only churns the
book (−0.38pp CAGR on TRAIN) without improving selection. The strategy's return is
entirely the 6-month momentum rank underneath it, and that rank alone is dominated by
buy-and-hold and by the nsealgo composite.

**The one thing I would try next:** stop trying to filter *within* the universe and use
the EMA where it is actually useful — as a **market-wide de-risking switch** rather than
a name filter. `nsealgo.factors.regime.exposure_series` already implements exactly that
(exposure in `[threshold, 1.0]`, decided from prior data only), and it attacks the
binding constraint here, which is drawdown, not return. Concretely: drop the EMA gate
entirely, keep `build_composite_score` as the score (it beat this strategy by 3.09pp
CAGR and 1.71pp of drawdown on TEST), and layer the time-series gate on top as exposure.
That is a strategy-composition change, not a parameter tweak, so it needs its own
declared budget — I did not run it here, because doing so would have turned TEST into a
second training set.

---

## Reproduce

```bash
cd research/agent_dual_momentum
../../.venv/bin/python 01_train_sweep.py     # 5 declared variants, TRAIN only
../../.venv/bin/python 02_test_eval.py      # the single TEST evaluation
../../.venv/bin/python 03_ablation_train.py # diagnosis, TRAIN only
../../.venv/bin/python 04_verify.py         # EMA fidelity, no-lookahead, sanity
```

Nothing under `src/nsealgo/**`, `src/cryptobot/**`, `tests/`, `GOAL.md` or `reports/`
was modified. Nothing was committed.
