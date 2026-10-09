# `hull_moving_average` on NSE NIFTY-50 — WORKING (status filled in below)

Source: `src/cryptobot/strategies/catalog/hull_moving_average.py`
Signal: `close > HMA(period)` → +1 else −1. Catalog default `period=20`.
Scratch: `research/agent_hull_ma/` (`run.py` protocol, `verify_hull.py` indicator equivalence)

**STATUS: report header written before any run. Results appended below as obtained.**

---

## 1. Declared parameter budget — DECLARED BEFORE RUNNING ANYTHING

Max 5 distinct parameter variants (brief §4). The only parameter is `period`.
Rebalance frequency is held fixed at monthly (`"M"`) for all variants — it is a
harness choice, not a strategy variant, and is not swept.

| Variant | `period` | note |
|---------|---------|------|
| V1 | 20 | catalog default |
| V2 | 10 | faster Hull |
| V3 | 15 | |
| V4 | 30 | slower Hull |
| V5 | 55 | classic slow Hull |

**Selection rule, fixed in advance: max TRAIN Calmar.** Selection happens on TRAIN
only; the winner is then evaluated unchanged on TEST.

**Variants tested: 5. Exceeded 5: no.**

---

## 2. Data

- `load_universe("data/nse")` daily close panel, cleaned. Span 2008→2026-10-01.
- TRAIN 2016-01-01 → 2023-12-31. TEST 2024-01-01 → 2026-10-01 (touched once, at the end).
- Daily bars only. 1m/5m/15m are banned/too short to validate — not used.
- **Survivorship bias is present** (today's NIFTY-50 backfilled) and is disclosed with
  every number below. Every nsealgo result must be quoted with its end date
  (2026-10-01).

---

## 3. Construction

- Signal replicated exactly from `cryptobot.strategies.indicators.hull`:
  `HMA = WMA(2*WMA(n/2) - WMA(n), sqrt(n))`, with the catalog's own lagged-blend
  loop reproduced bar-for-bar and verified against the library function.
- Long-only book (brief §5): only the +1 state is holdable.
- Cross-sectional score: 126d trailing momentum ranked **only among names the Hull
  flags long** (brief §5 recipe).
- Portfolio: `PortfolioConfig()` defaults — 22 names, 12% single, 25% sector, 10% cash,
  35% turnover budget. Enforced by `run_backtest`; not bypassed.
- Costs: `CostModel(segment="delivery", slippage_bps=5)` → **21.92 bps** all-in round
  trip on ₹1,00,000. Every number below is **net of 21.92 bps** because these results
  come from `run_backtest` (brief §3 — do not mix with the 11.92 statutory-only figure).

---

## 4. Indicator fidelity + a real bug in the catalog (found before any backtest)

`research/agent_hull_ma/verify_hull.py` compares my vectorised `hull_panel` against the
real `cryptobot.strategies.indicators.hull` bar-for-bar on a 900-bar synthetic series,
for every one of the 5 declared periods. Result:

```
period= 10  max_rel_diff=5.471e-16  first_finite_bar=11
period= 15  max_rel_diff=4.271e-16  first_finite_bar=17
period= 20  max_rel_diff=5.890e-16  first_finite_bar=22
period= 30  max_rel_diff=6.387e-16  first_finite_bar=33
period= 55  max_rel_diff=5.434e-16  first_finite_bar=60
OK: vectorised hull_panel == catalog hull (to float precision)
```

**BUG (catalog, medium severity) — Hull terms are swapped.**
`src/cryptobot/strategies/indicators.py:76-86` computes

```python
raws.append(2.0 * wf - wh)      # wf = WMA(period), wh = WMA(period//2)
```

with the docstring claiming `WMA(2*WMA(n/2) - WMA(n), sqrt(n))`. The textbook Hull MA is
`2*WMA(n/2) - WMA(n)`; the library has the two terms reversed. The correct composite
should be the *fast* MA doubled minus the *slow* MA (it is a low-lag smoother). The
library produces `2*WMA(slow) - WMA(fast)`, which is the negative of the intended line.

Consequence: this is **not** a cosmetic bug. `hull_moving_average` computes
`signal = +1 if close > hull else -1`. Negating the Hull line flips the sign of
`(close - hull)`, so the strategy's signal is roughly *inverted* versus a genuine Hull
MA strategy — it goes long precisely when a correct Hull implementation would be flat-to-
short. Any other consumer of `indicators.hull` (there are several in the catalog) is
affected the same way. I am validating **the library as written** (it is the assigned
strategy) and reporting this separately, but flag it as a fix candidate upstream.

**Secondary note:** `indicators.hull` is O(period) per call inside a Python loop and
recomputes the WMA over overlapping windows, i.e. O(n·period·sqrt(period)) for a panel.
Fine for streaming, wasteful for research. My panel version is exact and O(n·period).

---

## 5. TRAIN (2016-01-01 → 2023-12-31) — selection only

All numbers **net of 21.92 bps**. Panel 48 symbols, 4,629 bars, 2008→2026-10-01.
Cleaning: 274,541 → 208,226 rows (66,312 pre-2008 dropped, `adanient` + `jiofin`
excluded, 3 extreme moves dropped).

| variant | period | CAGR% | Sharpe | MaxDD% | Calmar | Turn x/y | Cost %/y | Names | Long% |
|---------|--------|-------|--------|--------|--------|----------|-----------|-------|-------|
| V1 | 20 | 17.02 | 0.80 | −26.52 | 0.64 | 3.96 | 1.66 | 28.2 | 54.8% |
| **V2 (selected)** | **10** | **18.73** | **0.96** | **−14.38** | **1.30** | 3.96 | 1.82 | 28.2 | 53.1% |
| V3 | 15 | 18.40 | 0.92 | −20.12 | 0.91 | 3.95 | 1.77 | 28.0 | 54.0% |
| V4 | 30 | 15.64 | 0.70 | −29.46 | 0.53 | 3.94 | 1.56 | 27.6 | 56.2% |
| V5 | 55 | 13.76 | 0.54 | −33.28 | 0.41 | 3.72 | 1.36 | 25.8 | 58.7% |
| buy & hold | — | 18.38 | 0.78 | −34.92 | 0.53 | 2.64 | 1.18 | 22.2 | — |
| nsealgo composite | — | 21.30 | 0.96 | −32.92 | 0.65 | 1.96 | 1.00 | 21.8 | — |

TRAIN looks genuinely good: V2 beats buy-and-hold on CAGR *and* carries a **less than
half** the drawdown (−14.4% vs −34.9%), for a Calmar of 1.30 vs 0.53. Signal liveness
is healthy (~53% of bars long — nowhere near the 5% always-flat failure mode).
Selection on max Calmar picks **V2, period=10**.

**TRAIN-only diagnostic of the catalog term-order bug** (not a variant, not selected on,
not counted against the budget): re-running the identical pipeline with the Hull terms
un-swapped to textbook order gives TRAIN CAGR% `{V1_20: 19.86, V2_10: 15.96, V3_15: 18.14,
V4_30: 19.60, V5_55: 15.88}`. The bug is not uniformly fatal — for the slower periods the
textbook version is *better* (V1 19.86 vs 17.02, V4 19.60 vs 15.64), and for period=10 it
is worse. So the swap is a genuine correctness defect but not a simple "the library is
backwards and everything would improve" story.

---

## 6. TEST (2024-01-01 → 2026-10-01) — touched once, after selection was locked

| variant | period | CAGR% | Sharpe | MaxDD% | Calmar | Turn x/y | Cost %/y | Names | Long% |
|---------|--------|-------|--------|--------|--------|----------|-----------|-------|-------|
| V1 | 20 | 2.86 | −0.22 | −15.19 | 0.19 | 4.02 | 1.03 | 27.6 | 53.3% |
| **V2 (selected)** | **10** | **3.85** | **−0.14** | **−13.46** | **0.29** | 4.03 | 1.02 | 28.1 | 51.9% |
| V3 | 15 | 4.56 | −0.08 | −13.79 | 0.33 | 4.01 | 1.05 | 27.6 | 52.6% |
| V4 | 30 | 1.27 | −0.34 | −19.03 | 0.07 | 4.02 | 1.02 | 26.4 | 54.6% |
| V5 | 55 | 1.98 | −0.27 | −18.80 | 0.11 | 3.74 | 0.95 | 25.3 | 56.2% |
| **buy & hold** | — | **2.60** | −0.22 | −16.86 | 0.15 | 2.76 | 0.70 | 21.3 | — |
| nsealgo composite | — | 6.55 | 0.07 | −14.84 | 0.44 | 2.07 | 0.55 | 21.3 | — |

**Selected variant V2 (period=10): CAGR 3.85%, Sharpe −0.14, MaxDD −13.46%, Calmar 0.29,
turnover 4.03×/yr, cost drag 1.02%/yr, 28.1 names, 685 sessions.**
Total return 11.2% over ~2.7 years.

### 6.1 Sanity checks (brief §6)

1. **Plausibility.** 3.85% CAGR — nowhere near the 40–50% unlevered ceiling, no bug
   signature. ✅
2. **Weight count.** avg 28.1 names vs the 22-name `n_positions` target. Investigated:
   weights sum to 0.90 max / 0.82 mean (10% cash buffer honoured), max single weight
   8.8% (under the 12% cap), max names ever held 30. The count exceeds 22 because
   `apply_turnover_budget` *blends* toward the new target and thins to `max_names=30`
   rather than snapping to it — residual names survive inside the 35% turnover budget.
   That is engine design (`engine.py:332-347`), not weight accumulation, and the same
   behaviour appears in the BH row (22.2). No bug. ⚠️ worth knowing, not a defect.
3. **Signal liveness.** 51.9% of bars long. Healthy. ✅
4. **Cost drag.** 1.02%/yr. Gross is positive and net stays positive — the strategy is
   not cost-killed, but the margin is thin.
5. **Negative control.** ❌ **FAILS.** 20 random-signal controls with the same bar-long
   frequency: TEST CAGR median **5.25%**, range 2.67–9.00%. The selected Hull variant beat
   only **2 of 20** random draws. A coin flip with identical exposure beats this
   strategy more often than not.

### 6.2 TEST vs buy-and-hold, and vs the composite

| | Hull V2 | BH | composite |
|---|---------|----|-----------|
| CAGR | 3.85% | 2.60% | 6.55% |
| Sharpe | −0.14 | −0.22 | +0.07 |
| MaxDD | −13.46% | −16.86% | −14.84% |
| Calmar | 0.29 | 0.15 | 0.44 |

- **vs buy-and-hold:** better on return by **+1.25 pp CAGR** and better on drawdown by
  **3.4 pp** (−13.46% vs −16.86%). Marginally better on both counts.
- **vs composite:** **worse**, by 2.70 pp CAGR and on Calmar (0.29 vs 0.44). The
  nsealgo composite beats it.
- **Sharpe is negative** for Hull, BH *and* the composite in this window — TEST is a
  grinding 2.7-year stretch where almost nothing made a risk-adjusted return. The 6.5%
  risk-free assumption in `compute_metrics` is doing work here: a 3.85% CAGR is a
  *negative* excess return by construction. That is an honest reading of the window, not
  a Hull-specific defect.

### 6.3 Cost stress (selected variant, TEST CAGR%)

| cost | CAGR% |
|------|-------|
| zero slippage (11.92 bps statutory only) | 4.26 |
| **base (5 bps slippage → 21.92 bps)** | **3.85** |
| 10 bps slippage (31.92 bps) | 3.43 |
| 15 bps slippage (41.92 bps) | 3.01 |

Cost drag is ~0.41 pp of CAGR per 5 bps of slippage. Even at zero cost the strategy only
reaches 4.26% — **the result is not cost-limited, it is signal-limited.** Removing costs
would not rescue it above the random control's 5.25% median.

### 6.4 TEST yearly returns (selected variant)

| year | Hull V2 | buy & hold | composite |
|------|---------|-----------|-----------|
| 2024 | +13.51% | +18.60% | +22.57% |
| 2025 | +7.71% | +3.12% | +7.16% |
| 2026 (to 10-01) | −9.07% | −12.12% | −9.01% |

Consistent with the metrics: it lagged badly in the 2024 melt-up (it is a 52%-long
trend filter, so it de-risks into exactly those rallies), did well in chop, and matched
the market's drawdown in 2026.

---

## 7. VERDICT

**No — `hull_moving_average` does not make money on NSE. Out-of-sample it returns
3.85% CAGR net of 21.92 bps with a negative Sharpe, it beats buy-and-hold by only
1.25 pp, it loses to the nsealgo composite by 2.70 pp, and a random signal with identical
bar-long frequency beats it 18 times out of 20.**

The TRAIN result (18.73% CAGR, Sharpe 0.96, Calmar 1.30, half the market's drawdown) was
**not** reproduced in TEST (3.85% CAGR, Sharpe −0.14, Calmar 0.29). This is the textbook
in-sample trap, and the random-signal control is what proves it rather than a hunch.

**Most likely reason:** the signal carries essentially no cross-sectional information.
A binary `close > MA` filter is a *market-level* trend overlay — it turns roughly half
the universe on and off together, which is close to a uniform 52% exposure bet. All the
return therefore comes from the 126-day momentum ranking layered on top, which is the
same ranking buy-and-hold and the composite already use. When the momentum ranking is
mildly negative in the TEST window (it is: BH Sharpe −0.22), the Hull filter adds churn
(4.03×/yr turnover vs BH's 2.76×) and a slightly worse exposure mix, and you end up
paying 1.02%/yr for nothing. The filter adds no information; it only re-times an exposure
decision that the momentum rank was already making.

**The one thing I would try next:** stop using the binary filter as a *mask* and instead
test whether the Hull line's **slope or distance** carries cross-sectional signal —
rank names by normalised distance-to-HMA (`(close - HMA)/ATR`) across the whole universe
instead of masking momentum. A trend filter as a soft, cross-sectional score can
differentiate names; as a binary gate it can only move the whole book together. That is
the only shape of this indicator that could plausibly beat a random mask.

**The upstream fix, independently of the above:** `indicators.hull` has its Hull terms
swapped versus the textbook definition (§4). Every catalog strategy that consumes
`hull()` inherits an approximately inverted signal. That is worth fixing in
`src/cryptobot/strategies/indicators.py` regardless of what this NSE validation finds.

---

## 8. Protocol compliance

- Parameter budget: **5 declared, 5 tested, 0 exceeded.** All 5 are the `period` values
  listed in §1. Selection was max TRAIN Calmar, fixed before running.
- TEST was touched exactly once, after `best` was locked in `run.py`.
- The only TEST-set information that entered a decision: the `results.json` bookkeeping
  and the random-control seeds (a negative control, not a selection knob). The
  cost-stress sweep and yearly-return table are *reported diagnostics* on the already-
  selected variant — no parameter was changed after seeing them.
- The textbook-Hull comparison in §5 is **TRAIN-only** and was computed before TEST was
  opened. It was never used to select.
- Costs: every reported number is net of the 21.92 bps that `run_backtest` actually
  charges. The 11.92 bps statutory-only figure appears once, in the cost-stress table,
  correctly labelled as the zero-slippage case.
- Data end date for all results: **2026-10-01**. Survivorship bias present throughout.
- No lookahead: `run_backtest` lags execution one bar (weights from close *t* held from
  *t+1*). My score panel uses only data up to *t*; `panel.shift(126)` is backward-looking.
- Files touched: `research/agent_hull_ma/{REPORT.md,run.py,verify_hull.py,run.log,results.json}`.
  Nothing under `src/`, `tests/`, `reports/` or `GOAL.md` was modified. Not committed.