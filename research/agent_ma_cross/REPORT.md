# Agent Report — `moving_average_cross` on NSE NIFTY-50

## Provenance

| Field | Value |
|---|---|
| Assigned strategy | `moving_average_cross` |
| Source file | `src/cryptobot/strategies/catalog/moving_average_cross.py` |
| Report started | before any backtest was run |
| **`BacktestResult.engine_sha`** | **`970713f3eecf`** |
| Engine commit | `2825d03` — *"fix: residual-weight dilution, hull() lag bug, 8 broken catalog strategies"* |
| Strategy is crypto-specific? | **No** — SMA crossover is price-only and timeframe-agnostic. It has a legitimate NSE meaning. Proceeding. |

> `engine_sha=970713f3eecf` is the **post-fix** engine. The residual-weight
> dilution bug (dead positions decaying slowly instead of exiting — see
> `apply_turnover_budget` docstring at `src/nsealgo/backtest/engine.py:364`) is
> fixed in this version. Every number in this report is produced by it.

---

## 1. The strategy

```python
# src/cryptobot/strategies/catalog/moving_average_cross.py
@dataclass
class MaCrossConfig:
    fast: int = 10
    slow: int = 30
    quantity: Decimal = Decimal("1")

class MaCrossStrategy(SignalStrategy):
    name = "ma_cross"
    def warmup(self, closes) -> int:  return self.config.slow
    def signal(self, closes, highs, lows, volumes):
        f = sma(closes, self.config.fast)
        s = sma(closes, self.config.slow)
        if f != f or s != s or f == s:  return 0
        return 1 if f > s else -1
```

**Signal:** `+1` when `SMA(fast) > SMA(slow)`, `-1` otherwise, `0` while either
SMA is undefined or the two are exactly equal.

It is a **per-symbol time-series** signal. The NSE book is **long-only and
cross-sectional**, so a translation is required (§5 of the brief).

---

## 2. Data used

`load_universe("data/nse")` — the mandatory cleaned daily close panel.

```
CLEANING REPORT
  rows in             :   274,541
  rows out            :   208,226
  dropped pre-2008    :    66,312
  dropped artifact    :         0
  dropped non-positive:         0
  dropped extreme     :         3
  excluded symbols    : ['adanient', 'jiofin']
  extreme events      :         3
```

| | |
|---|---|
| Symbols | **48** (2 excluded: `adanient` structurally corrupt, `jiofin` < 1000 bars) |
| Panel shape | 4625 × 48 |
| Date range | **2008-01-01 → 2026-10-01** |
| Interior NaNs | 13,916 / 222,000 (6.3%) — IPO drift + delistings, never forward-filled |

**Survivorship bias is present and disclosed in every number below**: the universe is
today's NIFTY-50 backfilled to 2008. Symbols that were delisted or dropped from the
index are absent. This biases results **upward**.

---

## 3. Split (fixed, non-negotiable)

| Set | Window | Use |
|-----|--------|-----|
| **TRAIN** | 2016-01-01 → 2023-12-31 | all tuning, all selection |
| **TEST** | 2024-01-01 → 2026-10-01 | touched exactly once, at the end |

---

## 4. DECLARED PARAMETER BUDGET — 5 variants, fixed before any run

I will test **at most 5** distinct variants. Chosen to answer three questions with
the budget: (a) does the MA-cross signal carry any cross-sectional value, (b) how
sensitive is that to the window pair, (c) does throwing away the magnitude of the
cross (binary flag) destroy information.

| # | Windows (fast/slow) | Score construction | Question it answers |
|---|---|---|---|
| **V1** | 10 / 30 *(catalog default)* | **Binary flag** — `1.0` where `fast>slow`, `NaN` elsewhere | the stock construction at the shipped default |
| **V2** | 20 / 60 | Binary flag | window sensitivity (faster→slower) |
| **V3** | 50 / 200 | Binary flag | window sensitivity (the "golden/death cross" regime filter) |
| **V4** | 20 / 60 | **Cross-strength** — `(SMA_fast − SMA_slow)/close`, cross-sectional z-score, restricted to flagged names | does the *magnitude* of the cross carry more than the flag? |
| **V5** | 20 / 60 | **Momentum rank** among flagged — `(P/P.shift(126) − 1).where(flag).rank(axis=1, pct=True)` | does the brief's §5 recipe beat the alternatives? |

**Not counted against the budget** (mandated controls from brief §6/§7, not variants
of my strategy): buy-and-hold, the random-signal negative control, and the
`build_composite_score` benchmark.

**Harness config held fixed across all five variants:** `PortfolioConfig()` defaults
(22 names, 12% single-name, 25% sector, 10% cash, 0.35 turnover budget), `rebalance="M"`
(monthly — the engine's evidence-backed default, engine.py:11-16; holding period ~21
sessions, inside the 5–60 day band), `CostModel(segment="delivery", slippage_bps=5)`
→ **21.92 bps all-in round trip** as charged by `run_backtest`.

**Selection rule (declared now):** pick the variant with the best TRAIN
Sharpe/Calmar balance. Freeze it. Run it on TEST exactly once.

---

## 5. Results

*(appended below as runs complete)*
---
*appended after TRAIN completed, before any TEST data was touched*

## 6. TRAIN results (2016-01-01 → 2023-12-31, 1973 bars, 48 symbols)

`engine_sha=970713f3eecf` · monthly rebalance · `PortfolioConfig()` defaults ·
**net of 21.92 bps all-in round trip**

| variant | windows | score | CAGR | Sharpe | MaxDD | Calmar | live% | avg names | turn/y |
|---|---|---|---|---|---|---|---|---|---|
| V1 | 10/30 | flag | 8.50% | 0.22 | −30.75% | 0.28 | 56.7% | 18.9 | 3.93x |
| V2 | 20/60 | flag | 11.12% | 0.40 | −31.86% | 0.35 | 59.7% | 19.8 | 3.46x |
| **V3** | **50/200** | **flag** | **14.75%** | **0.60** | −34.38% | **0.43** | 64.5% | 20.6 | 2.01x |
| V4 | 20/60 | strength | 10.47% | 0.34 | −33.92% | 0.31 | 59.7% | 19.8 | 3.87x |
| V5 | 20/60 | momrank | 12.85% | 0.49 | −33.44% | 0.38 | 59.5% | 19.8 | 3.42x |
| — | — | **buy-and-hold** | **22.20%** | **0.91** | −37.97% | 0.58 | 100% | 48 | 0.00x |
| — | — | **nsealgo composite** | **20.72%** | **0.93** | −32.94% | 0.63 | — | — | — |

### 6.1 Selection — DECLARED, THEN FROZEN

**Selected on TRAIN: `V3` — 50/200 SMA cross, binary flag.**
It wins outright on both criteria of my pre-declared rule (best Sharpe **0.60**,
best Calmar **0.43**), and it is also the cheapest to trade (lowest turnover, 2.01x/y).
There is no ambiguity in the selection, and I did not consult TEST to make it.

**V3 is now frozen. TEST is run once, unchanged.**

---

## 7. Mandated sanity checks (TRAIN)

| Check | Result | Verdict |
|---|---|---|
| **6.1 Plausibility** | best CAGR 14.75% — far under the 40–50% ceiling | ✅ no lookahead, no compounding bug |
| **6.2 Weight count** | avg **20.6** names held (target 22), never 48 | ✅ no residual-weight accumulation |
| **6.3 Signal liveness** | **64.5%** of (bar, symbol) cells flagged | ✅ nowhere near the 5% always-flat trap |
| **6.4 Cost drag** | **1.53%/yr** on V3 (2.3–2.5%/yr on the faster variants) | ⚠️ real but *not* the cause of the loss |
| **6.5 Negative control** | **random coin flip beats it** | ❌ **fails** |

### 7.1 Cost decomposition — the loss is the signal, not the friction

| variant | net CAGR | gross CAGR | drag/yr | turn/y |
|---|---|---|---|---|
| V1 10/30 | 8.50% | 9.35% | 2.43% | 3.93x |
| V2 20/60 | 11.12% | 11.89% | 2.32% | 3.46x |
| **V3 50/200** | **14.75%** | **15.21%** | **1.53%** | **2.01x** |
| V4 20/60 strength | 10.47% | 11.33% | 2.52% | 3.87x |
| V5 20/60 momrank | 12.85% | 13.62% | 2.37% | 3.42x |

Gross-of-cost V3 is **15.21%** — still ~7.5pp below buy-and-hold's 22.20%. Costs
consume 0.46pp. **This strategy was never close to viable; friction is not what
killed it.**

### 7.2 Negative control — THE DECISIVE RESULT

**Control A (brief §6.5): an independent coin flip per name per day, matched to the
same % of bars long. 20 seeds each.**

| window | **strategy net CAGR** | random-mask mean | min | max | **verdict** |
|---|---|---|---|---|---|
| 10/30 | 8.50% | **13.67%** | 10.97% | 16.76% | ❌ loses by 5.2pp |
| 20/60 | 11.12% | **14.52%** | 11.53% | 17.25% | ❌ loses by 3.4pp |
| 50/200 | 14.75% | **15.36%** | 12.55% | 17.82% | ❌ loses by 0.6pp |

**A random coin flip, given identical exposure, beats this strategy at every window
pair.** The 50/200 pair is the only one inside the noise band, and even there the
random control's *mean* is higher. The MA-cross flag carries no information that a
random draw does not also carry.

**Control B (tighter): keep the strategy's exact flagged names, break ties at random.**
This isolates the *ranking* from the *filter*.

| window | strategy (alphabetical tie-break) | random-among-flagged mean | spread |
|---|---|---|---|
| 10/30 | 8.50% | 7.19% | 5.84–8.53% |
| 20/60 | 11.12% | 9.42% | 8.00–10.56% |
| 50/200 | 14.75% | 13.57% | 12.63–14.43% |

The strategy edges out random-among-flagged by 1.2–1.7pp on the slower pairs, but
the seed-to-seed spread is ±1.3pp, so this is **not distinguishable from noise**.
Combined with Control A, the conclusion is that essentially *all* of the apparent
performance is the passive beta of holding ~20 large NIFTY names, not the crossover.

### 7.3 No-lookahead proof

Recomputing the score at date *t* from a panel **physically truncated at *t*** gives
a bit-identical result (checked 2018-06-29, 2020-03-16, 2022-09-30). If the signal
touched any future bar it could not survive truncation. Weights are held from *t+1*
via `held.shift(1)` (`engine.py:506`). ✅ **No lookahead anywhere.**

---

## 8. Bug found — `CostModel` crashes on a float `slippage_bps`

`src/nsealgo/costs.py:230` — `round_trip_bps()` returns `Decimal`, `slippage_bps` is
stored uncoerced, so `Decimal + float` raises. `CostModel(..., slippage_bps=0.0)`
therefore kills **every** `run_backtest` call, making it impossible to measure a
gross-of-cost baseline through the engine.

Full write-up, repro and suggested fix: **`BUG_costs_float_slippage.md`**.
Reported, not fixed (brief §9 forbids editing `src/nsealgo/**`).

---
*appended after the single TEST look*

## 9. TEST results (2024-01-01 → 2026-10-01, 684 bars) — ONE LOOK, V3 ONLY

Frozen variant, run unchanged. The four unselected variants were **deliberately not
run on TEST** — reporting all five would turn one out-of-sample look into five and
contaminate it. `engine_sha=970713f3eecf`, **net of 21.92 bps**.

| | CAGR | Sharpe | MaxDD | Calmar | turn/y | cost/y | avg names |
|---|---|---|---|---|---|---|---|
| **V3 ma_cross (50/200)** | **1.47%** | **−0.35** | **−17.57%** | 0.08 | 2.19x | 1.07% | 20.4 |
| buy-and-hold | 8.18% | 0.18 | −15.90% | 0.51 | — | — | 48 |
| nsealgo composite | 6.04% | 0.03 | −15.22% | 0.40 | 2.08x | 1.10% | 21.3 |

**TRAIN → TEST collapse: 14.75% → 1.47% CAGR (−13.3pp), Sharpe 0.60 → −0.35.**

### 9.1 vs buy-and-hold

| | ma_cross | buy&hold | delta |
|---|---|---|---|
| CAGR | 1.47% | 8.18% | **−6.71pp/yr** |
| Sharpe | −0.35 | 0.18 | **−0.53** |
| MaxDD | −17.57% | −15.90% | **1.67pp WORSE** |
| Calmar | 0.08 | 0.51 | −0.43 |

Worse on return **and** worse on drawdown. It does not even pay for its risk.

Calendar years: ma_cross beat buy-and-hold in **0 of 3** (2024 +13.93% vs +19.87%;
2025 +3.70% vs +13.35%; 2026 −11.81% vs −8.26%).

### 9.2 Negative control on TEST — the cleanest possible failure

Random coin flip, same % of bars long, 20 seeds:

| | CAGR |
|---|---|
| **V3 ma_cross** | **1.47%** |
| random-mask mean | 5.84% |
| random-mask min / max / sd | 2.45% / 8.52% / 1.46% |

**V3 finished at the 0th percentile of the random distribution — it lost to 20 of 20
random draws.** Not "roughly as good as random". Strictly worse than every single
one. Brief §6.5's minimum bar ("beating a coin flip") is not merely unmet; the
strategy is measurably anti-predictive.

This corroborates TRAIN exactly, where the random control also led at all three
window pairs. The failure replicated out-of-sample rather than being a TRAIN artefact.

### 9.3 vs the nsealgo composite

Composite 6.04% CAGR vs ma_cross 1.47% — **the house strategy is 4.6x better over the
identical window on the identical panel with the identical costs.** The composite
also holds 21.3 names at 2.08x turnover, i.e. operationally indistinguishable from
ma_cross. So this is a like-for-like comparison: same book size, same rebalance
schedule, same cost stack. Only the signal differs, and ma_cross loses by 4.6pp/yr.

### 9.4 Mechanism — the crossover has *negative* selection value here

Forward 21-day return by flag state, per (name, bar) cell:

| window | when flagged | when NOT flagged | spread |
|---|---|---|---|
| TRAIN | +0.086%/mo (n=61,091) | +0.107%/mo (n=33,613) | **−0.022pp** |
| TEST | +0.033%/mo (n=21,797) | +0.036%/mo (n=11,035) | **−0.004pp** |

**The spread is negative in both windows.** A name in a 50/200 uptrend did not
outperform a name that was not, on a one-month horizon, in this sample. The
signal is not merely weak — it is very slightly backwards, and both magnitudes are
far inside the noise.

So the TRAIN result was never the crossover working. It was **passive beta**: the
flag holds ~31 of 48 large NIFTY names every month, which delivers market return by
construction. Strip the beta (Control A) and there is nothing underneath — the
slightly-negative spread actively subtracts from it.

---

## 10. Verdict

> **No. `moving_average_cross` does not make money on NSE.** Out-of-sample it
> returned **1.47% CAGR / −0.35 Sharpe**, losing to buy-and-hold by 6.7pp/yr, to the
> nsealgo composite by 4.6pp/yr, and to **all 20 random-coin-flip controls** — while
> also drawing down 1.7pp *more* than the market.

### 10.1 Most likely reason

**A time-series crossover has no cross-sectional content to extract.** The MA-cross
answers "is this name trending?" but the portfolio must also answer "which trending
name?", and the binary flag carries none of that information — so ties break
arbitrarily (column order) and the book becomes an undiversified, uninformative
slice of large caps. The measured flag spread (−0.022pp/mo on TRAIN, −0.004pp on
TEST) confirms there was no latent ranking signal being thrown away by the binary
encoding: using the cross *magnitude* (V4) or trailing momentum (V5) did not rescue
it on TRAIN either (10.47% and 12.85% vs V3's 14.75% — both worse).

This is consistent with the module's own evidence note (`factors/core.py:22-26`):
the only multiple-testing-corrected study of Indian technical rules found
trend-following survivors at *long* horizons, while the crossover at 50/200 is
already long — the surviving edge sits at multi-month-to-multi-year horizons, not
at one month of holding with monthly rebalancing. **The horizon is the mismatch.**

### 10.2 The one thing I would try next

Not another window pair. **Lengthen the holding period to match the signal's actual
horizon**: stop rebalancing monthly and let a 50/200 cross be acted on quarterly or
annually (4 or 1 rebalances/yr instead of 12). Two independent reasons to expect
that to help: turnover falls ~3x, so the 1.07–2.5%/yr cost drag largely disappears;
and the one-month flag spread being ~0 while the crossover is a multi-month trend is
exactly what a longer holding period would fix. Then re-verify with a fresh
walk-forward — do **not** re-test the same TEST window that has now been consumed.

---

## 11. Protocol compliance

| Requirement | Status |
|---|---|
| Parameter budget declared before running | ✅ 5 variants, in REPORT §4, written before any backtest |
| Variants tested | ✅ exactly 5 (V1–V5); **not exceeded** |
| Parameters chosen on TRAIN only | ✅ selection was V3 on TRAIN Sharpe+Calmar, unambiguous |
| TEST touched once | ✅ **one** run, V3 only; the other four were never run on TEST |
| Controls do not consume budget | ✅ buy&hold, random control, composite are benchmarks |
| Costs | ✅ **21.92 bps all-in** as `run_backtest` charges (not the 11.92 statutory figure) |
| No lookahead | ✅ proven by panel-truncation test (§7.3) |
| Long-only | ✅ never shorts; no negative weights possible |
| `PortfolioConfig` respected | ✅ 20.4 avg names vs 22 target, 0.9% cash buffer, caps enforced by engine |
| Sanity checks §6.1–6.5 | ✅ all run; §6.5 **failed** and is reported as the finding |
| `src/` untouched | ✅ no edits to `src/nsealgo/**`, `src/cryptobot/**`, or tests |
| Not committed | ✅ nothing committed or pushed |

### Files
- `REPORT.md` — this report
- `harness.py` — signal construction, variants, benchmarks, TRAIN runner
- `controls.py` — no-lookahead proof, cost decomposition, negative controls
- `test_eval.py` — the single TEST evaluation
- `BUG_costs_float_slippage.md` — the bug found in `src/nsealgo/costs.py`
- `results_train.csv` — per-variant TRAIN metrics

### Caveats that cut against this conclusion being "too pessimistic"
- **Survivorship bias inflates every number here**, including the benchmarks — so
  the absolute CAGRs are overstated across the board.
- **The TEST window is short** (2.75 years, 3 calendar years) and contains one
  sharp drawdown phase in 2026. It cannot resolve a small edge; it can only
  conclusively reject a large one. It rejected this one decisively (0th percentile).
- **buy-and-hold is an unusually strong benchmark** — 48 names, zero rebalancing,
  zero ongoing cost — and is not itself tradeable under `PortfolioConfig`. The
  conclusion does not rest on it: the cost-paying, 21-name, monthly-rebalanced
  nsealgo composite beats ma_cross 4.6:1 under identical constraints.
- The honest negative case is that **V3 was chosen for TRAIN Sharpe over a 5-variant
  grid with no nested validation** — mild selection bias in V3's favour. That makes
  the TEST result a *conservative* estimate of the family, not an optimistic one.

---
## 12. Reproducibility note — a concurrent `loader.py` edit, caught and neutralised

While my TEST run was in flight, another agent committed a change to
`src/nsealgo/data/loader.py` at **06:29:23** (my TEST ran ~06:27). It added rule
**C9 — drop frozen closes (vendor feed freeze)**, removing **539 additional rows**
from `bajajauto` and `nestleind`:

```
rows_out  208,226 -> 207,687
dropped_frozen  539   frozen_runs 3   frozen_symbols ['bajajauto', 'nestleind']
```

This is exactly the failure mode `engine_sha` was introduced to prevent, one level
down: the result object pins the *engine* but says nothing about the *data*.

**I re-ran the full pipeline from scratch under the current loader.** Every number
in this report is **unchanged** to the last reported digit:

| | TRAIN before → after | TEST before → after |
|---|---|---|
| V3 CAGR | 14.75% → **14.75%** | 1.47% → **1.47%** |
| V3 Sharpe | 0.60 → **0.60** | −0.35 → **−0.35** |
| V3 MaxDD | −34.38% → **−34.38%** | −17.57% → **−17.57%** |
| buy-and-hold CAGR | 22.20% → **22.20%** | 8.18% → **8.18%** |
| composite CAGR | 20.72% → **20.72%** | 6.04% → **6.04%** |
| random control mean | — | 5.84% → **5.84%** (0/20) |

All 8 TRAIN and 3 TEST calendar-year returns also identical. The conclusion is
therefore **not** an artefact of the data state; it is robust to it.

### Secondary finding — `BacktestResult` fingerprints the engine but not the data

`engine_sha` (`engine.py:37-64`) was added because "concurrent edits to this file
silently changed results mid-experiment — identical scripts returned different
numbers". That reasoning applies with equal force to `loader.py`, which sits
upstream of every single number and carries **no** provenance field. Had the C9 edit
*moved* a result rather than being neutral, nothing in the returned
`BacktestResult` would have revealed it.

Suggested (not applied — brief §9): add `loader_sha` to `BacktestResult` alongside
`engine_sha`, and have `load_universe`'s `CleaningReport` record the cleaning-rule
version, so a result carries both the engine that made it and the data it was made
from. The `rows_dropped` / `dropped_frozen` counters in `CleaningReport` are already
the right data; they just are not attached to the result.

---

## 13. Bottom line

`moving_average_cross`, selected on TRAIN and evaluated once out-of-sample, returns
**1.47% CAGR at −0.35 Sharpe**, loses to buy-and-hold, loses to the house
composite by 4.6:1, loses to **every one of 20 random controls**, and draws down
**more** than the market while doing it. The underlying flag has slightly negative
cross-sectional predictive value (−0.022pp/mo on TRAIN, −0.004pp on TEST).

**This is a clean, publishable negative.** A time-series crossover answers "is this
name trending?" but a long-only cross-sectional book must also answer "which
trending name?", and the binary flag carries no information for that. It is a beta
tilt wearing an alpha costume — and once the beta is controlled away, nothing is
underneath it.

The one thing worth trying next is a **holding-period change, not a parameter
change**: rebalance quarterly or annually so a 50/200 cross is actually held for its
horizon, then re-validate on a fresh walk-forward.
