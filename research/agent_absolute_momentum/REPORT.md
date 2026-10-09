# `absolute_momentum` on NSE NIFTY-50 — validation report

**Strategy:** `src/cryptobot/strategies/catalog/absolute_momentum.py`
**Date of run:** 2026-10-07 · **Data:** `data/nse` via `load_universe` (48 symbols, 4,629 daily bars, 2008-01-01 → 2026-10-01)
**Costs:** full Indian delivery stack, `CostModel(segment="delivery", slippage_bps=5)` → 21.9 bps all-in round trip (11.9 statutory + 10 slippage)

---

## Verdict

**No — `absolute_momentum` does not make money on NSE as a strategy.** It returns
+8.37% CAGR out-of-sample, but that is 99% beta and +0.7 pp of total return versus
buy-and-hold over 2.75 years. More decisively: **the absolute-momentum gate itself
— the entire premise of the strategy — contributes −0.44 pp/yr out-of-sample.** The
cross-sectional momentum ranking that carries the book is not this strategy's idea;
it belongs to the nsealgo composite. Strip the gate and the book does *better*.

This is a clean, publishable negative result.

---

## 1. Signal and declared parameter budget

Catalog signal, verbatim:

```python
m = roc(closes, period)                                  # close/close.shift(period) - 1
return 1 if m > threshold else (-1 if m < -threshold else 0)
```

Shorting is unavailable in an Indian delivery account, so the `-1` branch maps to
"not held". Book construction (brief §5): among names the signal flags, rank
cross-sectionally by the same trailing return that produced the signal.

```python
score = roc_panel.rank(axis=1, pct=True)   # NaN where not flagged
```

**Declared budget — 5 variants, fixed before any run was executed:**

| # | name | period | threshold |
|---|------|--------|-----------|
| V1 | `V1_p30_t0.00` | 30 | 0.00 |
| V2 | `V2_p63_t0.00` | 63 | 0.00 |
| V3 | `V3_p126_t0.00` | 126 | 0.00 |
| V4 | `V4_p252_t0.00` | 252 | 0.00 |
| V5 | `V5_p126_t0.05` | 126 | 0.05 |

**Budget respected: exactly 5 variants tested. No threshold or period was adjusted
after seeing an equity curve.** The span covers the catalog's crypto default (30d)
through a full trading year, plus one magnitude-hurdle variant. Sections 3–4 run
*diagnostics at other lookbacks* (30/63/126/252/504) — these are ablations of the
selected variant, not selection candidates; the selected variant is unchanged in
every out-of-sample number below.

---

## 2. TRAIN selection (2016-01-01 → 2023-12-31, 1,975 bars)

| variant | CAGR | Sharpe | MaxDD | Calmar | Turnover | Cost drag | Avg names | Signal live |
|---|---|---|---|---|---|---|---|---|
| V1 p30 | 12.59% | 0.48 | −32.53% | 0.39 | 4.08x/y | 1.43%/y | 29.0 | 58.1% |
| V2 p63 | 15.25% | 0.62 | −33.77% | 0.45 | 3.60x/y | 1.43%/y | 23.9 | 60.9% |
| V3 p126 | 17.09% | 0.71 | −34.92% | 0.49 | 2.84x/y | 1.20%/y | 21.4 | 64.0% |
| **V4 p252** | **20.16%** | **0.88** | −34.57% | **0.58** | 2.03x/y | 0.96%/y | 21.3 | 67.2% |
| V5 p126 t5% | 16.81% | 0.70 | −34.86% | 0.48 | 3.03x/y | 1.26%/y | 20.4 | 53.9% |
| *composite (ref)* | *21.30%* | *0.96* | *−32.92%* | *0.65* | | | | |

**Selected: V4 (`period=252, threshold=0.00`)** on TRAIN Sharpe, tie-broken on Calmar.
Note it already *lost to the nsealgo composite in-sample* (0.88 vs 0.96) — an early
warning that the edge was not distinctive.

---

## 3. TEST result (2024-01-01 → 2026-10-01, 685 bars) — selected variant, unchanged

| metric | **absolute_momentum** | **buy-and-hold** | **nsealgo composite** |
|---|---|---|---|
| Total return | **+25.3%** | +24.6% | +19.7% |
| CAGR | **8.37%** | 8.16% | 6.55% |
| Sharpe (rf 6.5%) | **0.20** | 0.18 | 0.07 |
| Max drawdown | **−16.18%** (107d) | −15.91% | −14.84% |
| Calmar | **0.52** | 0.51 | 0.44 |
| Volatility | 13.45% | — | — |
| Turnover | 2.00x/yr | 0.36x/yr | 2.07x/yr |
| Cost drag | 0.54%/y | — | — |
| Avg names held | 21.2 | 48 | — |
| Beta vs EW market | 0.94 | 1.00 | — |
| Annual alpha | **+0.67%** | −0.08% | — |

Yearly: 2024 **+24.1%**, 2025 **+8.3%**, 2026 (to Oct 1) **−6.8%** — 67% of years positive.

### Head to head vs buy-and-hold
- **Return: +0.7 pp better** (+25.3% vs +24.6%). On a ₹21,00,000 book that is
  **~₹15,000 over 2.75 years** — inside the noise of the cost model itself.
- **Drawdown: 0.28 pp WORSE** (−16.18% vs −15.91%). It gave up return *and* took more pain.
- CAGR margin +0.22 pp/yr. Beta 0.94, annual alpha +0.67% — it is the market, less a bit.

### Cost drag
| | CAGR | Sharpe | Total return |
|---|---|---|---|
| gross (zero cost) | 8.59% | 0.21 | +26.0% |
| net (base cost) | 8.37% | 0.20 | +25.3% |

Drag 0.22 pp/yr (₹31,932 total). **Viable on costs** — it is not a cost-killed
strategy, it simply has almost nothing to pay costs on.

---

## 4. Negative control — random signal, same % bars long (60 seeds, TEST)

Random names, random rank, matched daily eligible count.

| | mean | p05 | p95 |
|---|---|---|---|
| random CAGR | 5.02% | 2.63% | 7.73% |
| random Sharpe | −0.08 | −0.29 | 0.16 |

**Strategy Sharpe 0.20 beats 98% of random draws → PASSES the coin-flip bar.**

But the control is more informative than that. An *identical gate with a random rank*
scores 4.35% ± 1.42% (40 seeds). So:

- **The ranking, not the gate, is what beats the coin flip.** Gate+real-rank 8.37%
  and rank-only 8.82% both sit above 40/40 random-rank seeds; gate+random-rank does not.

---

## 5. Ablation — where did the return actually come from?

Same period (252), same costs, TEST window:

| book | CAGR | Sharpe | MaxDD | beta | alpha/yr | corr to mkt |
|---|---|---|---|---|---|---|
| GATE + RANK (selected) | 8.37% | 0.20 | −16.18% | 0.94 | +0.67% | 0.94 |
| RANK only (no gate) | **8.82%** | **0.23** | −16.18% | 0.94 | +1.08% | 0.94 |
| GATE only (random rank) | 4.78% | −0.08 | −14.46% | 0.83 | −1.97% | 0.95 |
| BUY-AND-HOLD | 8.16% | 0.18 | −15.91% | 1.00 | −0.08% | 1.00 |

- **A. Cross-sectional 252d momentum ranking: +3.59 pp/yr.** This is real — but it is
  the composite's idea, not this strategy's.
- **B. The absolute-momentum gate: −0.44 pp/yr.** The strategy's actual thesis.
  Removing it *improves* the book.
- **C. Beta: 0.94.** The book is the market.

### The gate finding is robust, not a one-window artefact

| window | gate+rank | rank only | gate worth |
|---|---|---|---|
| 2009–2013 | 23.85% | 30.62% | **−6.77pp** |
| 2014–2018 | 18.93% | 18.83% | +0.09pp |
| 2019–2021 | 21.40% | 22.44% | −1.04pp |
| 2022–2023 | 18.34% | 18.17% | +0.16pp |
| TRAIN all | 20.16% | 20.54% | −0.38pp |
| TEST 2024–26 | 8.37% | 8.82% | −0.44pp |
| full 2008–26 | 18.00% | 19.95% | **−1.95pp** |

Negative in **5 of 7 windows**, mean −1.48 pp, median −0.44 pp.

Across lookbacks (TRAIN | TEST), the gate is negative in **9 of 10** cells:

| period | TRAIN gate worth | TEST gate worth |
|---|---|---|
| 30 | −2.22pp | −0.83pp |
| 63 | −2.44pp | −1.52pp |
| 126 | −1.29pp | +0.19pp |
| 252 | −0.38pp | −0.44pp |
| 504 | +0.05pp | −0.00pp |

Consistent story: **short lookbacks the gate is clearly harmful** (it whipsaws names
in and out of a falling market at the worst moment), **long lookbacks it is inert**.

---

## 6. Sanity checks (brief §6)

| check | result |
|---|---|
| [1] Plausibility | 8.37% CAGR — well under the 40–50% long-only ceiling. **OK** |
| [2] Weight count | avg **21.2** names held (target 22, hard cap 30), max 22. **OK** |
| [3] Signal liveness | **73.6%** of (name,bar) cells long; avg 35.3 names eligible/day. **OK — genuinely live**, not always-flat |
| [4] Cost drag | +0.22 pp/yr; gross +8.6% → net +8.4%. Not cost-killed |
| [5] Random control | beats 98% of 60 seeds — but that is the *ranking*, not the gate |

Additional: max single weight 7.24% (cap 12%), 33 rebalances, max drawdown 107 days.

---

## 7. GOAL.md §5 gates on TEST

| gate | value | result |
|---|---|---|
| 1 — CAGR ≥ 3%/month net | 8.37%/yr (need ~43%/yr) | **FAIL** |
| 2 — Sharpe ≥ 1.0 | 0.20 | **FAIL** |
| 3 — positive ≥60% of years | 67% | PASS |
| 4 — MaxDD ≤ 20% | −16.18% | PASS |
| 5–7 — cost stress, capacity, robustness | not pursued; gate 1–2 already fail | — |

**Two of the seven non-waivable gates fail. This does not ship.**

---

## 8. Why it failed, and what I would try next

**Most likely reason.** The catalog strategy was written for crypto, where
"absolute momentum" means *regime switching* — cut to cash when the asset's own
trailing return is negative, because a crypto drawdown is a 70% event that must be
avoided at any cost. In a long-only Indian delivery book that logic inverts:

1. **There is no short and no meaningful cash.** The `-1` branch, which is where the
   strategy's real risk control lives, maps to "hold a slightly different basket of
   22 large caps." Beta is 0.94. The regime switch that would have saved you in crypto
   is not available.
2. **The gate destroys the cross-section it then ranks.** Filtering to
   `roc_252 > 0` and ranking by `roc_252` is nearly a monotone function of the same
   variable. The gate mostly removes the *bottom* of the ranking, which inverse-vol
   scaling and the 22-name cap would have handled anyway — while adding the cost of
   the churn it creates (gate+random-rank turns over 3.88x/yr vs 2.00x for the real book).
3. **India is not a mean-reverting-at-the-margin market for this.** Long-horizon
   NIFTY-50 names are positive more than 73% of the time, so `roc > 0` excludes
   names in a *temporary* dip — precisely the ones about to mean-revert upward. The
   gate systematically buys weakness.

**The one thing I would try next.** Abandon the per-name gate. The one thing this
run does establish is that a plain cross-sectional 252d momentum rank (the *ablation*
book, not the selected strategy) is worth **+3.59 pp/yr over a random-rank book and
beats the nsealgo composite out-of-sample** — 8.82% CAGR / Sharpe 0.23 vs 6.55% /
0.07 — though it too fails to beat buy-and-hold by a margin worth deploying (B&H
8.16%). So even the salvageable component is a beta-plus-marginal result, not a
standalone edge. If anyone continues here, the only untested variant with a
real mechanism is applying absolute momentum **at the index level, not the name
level**: a market-wide `equal_weight_market` 252d-return gate that scales the whole
book toward cash (or to the 10% buffer) when the *market* trend is negative, using
`nsealgo.factors.regime.exposure_series`. That preserves the crypto thesis at the
only level where it can be expressed in a delivery account, without the per-name
churn. It is a new hypothesis and would need its own declared budget and a fresh
TRAIN/TEST protocol — it is not a re-run of this one.

---

## Protocol compliance

- TRAIN 2016-01-01 → 2023-12-31 used for **all** parameter selection.
- TEST 2024-01-01 → 2026-10-01 touched **once**, at step 2, with the variant carried
  over unchanged from `selected_variant.txt`.
- **No TEST data influenced any parameter choice.** Steps 3 and 4 use TEST only for
  attribution/ablation of the already-frozen selected variant, and their TRAIN-side
  counterparts are reported alongside for every comparison.
- Parameter budget: 5 declared, 5 run. Not exceeded.
- Costs are the full `CostModel` delivery stack on every fill, never reduced.
  The zero-cost figure is reported only to isolate drag (§3), labelled as gross.
- No lookahead: ROC on day *t* uses closes through *t*; `run_backtest` applies weights
  decided at *t* from *t+1*.
- No lookahead in the forward-fill: the engine holds targets between rebalances by
  forward-filling from the past.
- Nothing committed. Scratch only, under `research/agent_absolute_momentum/`.

## Files

| file | purpose |
|---|---|
| `harness.py` | shared loaders, signal, score construction, B&H, random control |
| `step1_train_sweep.py` | TRAIN-only selection → `train_sweep.csv`, `selected_variant.txt` |
| `step2_test_eval.py` | the single TEST run + all mandated comparisons → `test_summary.csv` |
| `step3_ablation.py` | gate-vs-rank attribution, beta/alpha, GOAL.md gates |
| `step4_robustness.py` | sub-window + lookback sweep, random-seed noise floor |
