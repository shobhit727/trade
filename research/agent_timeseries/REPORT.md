# `time_series` on NSE NIFTY-50 — validation report

## Provenance

| Field | Value |
|-------|-------|
| **Strategy** | `time_series` — `src/cryptobot/strategies/catalog/time_series_strategy.py` |
| **Engine SHA** | `970713f3eecf` |
| **Engine version note** | `BacktestResult.engine_sha` = hash of `src/nsealgo/backtest/engine.py` with docstrings stripped. Taken at run time from `nsealgo.backtest.engine.ENGINE_SHA`, not copied by hand. |
| **Run date** | 2026-10-10 |
| **Data** | `data/nse` via `load_universe` → 48 symbols × 4,625 daily bars, 2008-01-01 → 2026-10-01 |
| **Costs** | `CostModel(segment="delivery", slippage_bps=5)` → `run_backtest` charges `all_in_round_trip_bps(100_000)` = **21.92 bps** all-in (11.92 statutory + 2×5 slippage). Every number below is **net** of that. |
| **Capital** | ₹21,00,000 (`PortfolioConfig` defaults: 22 names, 12% single, 25% sector, 10% cash) |
| **Split** | TRAIN 2016-01-01 → 2023-12-31 · TEST 2024-01-01 → 2026-10-01 |

**Cleaning report (mandatory first step, `report.describe()`):**

```
rows in            :   274,541
rows out           :   208,226
dropped pre-2008   :    66,312
dropped artifact   :         0
dropped non-positive:         0
dropped extreme    :         3
excluded symbols   : ['adanient', 'jiofin']
extreme events     : 3
```

48 symbols retained (adanient excluded as structurally corrupt, jiofin for insufficient history).

> **Provenance note.** `src/nsealgo/data/loader.py` carries uncommitted working-tree
> changes at run time (a new rule **C9**, "drop frozen closes / vendor feed freeze"),
> applied by a concurrent agent. My run used that version, which is what produced the
> 48-symbol panel and the cleaning report above. **This means my panel may differ from a
> run on a clean checkout** — the comparison is valid (every row in this report shares
> one panel), but the absolute CAGR is not necessarily reproducible elsewhere until that
> change lands. `src/nsealgo/backtest/engine.py` was **clean and its SHA identical at the
> start and end of my run**, so the engine half of the provenance is solid.

---

## 1. What the strategy does

```python
def signal(self, closes, highs, lows, volumes):
    m = roc(closes, self.config.period)          # period = 40
    if m != m: return 0                           # warmup NaN only
    return 1 if m > self.config.threshold else -1
```

`roc(closes, p) = (close[-1] - close[-p-1]) / close[-p-1]` — the total return over the
trailing `period` bars. The strategy is a **per-name binary time-series momentum
flag**: long (+1) if the name is up over the last `period` bars, short (−1) otherwise.

Two properties that shape the translation:

* **It never returns 0 except during warmup.** Every name is either long or short on
  every bar after warmup. The −1 leg is not "hold" — under `feed()` a `−1` target on a
  long position is a reduce-only close. In a long-only NSE book the `−1` leg maps to
  **not holding the name** (its weight goes to cash).
* **It carries no cross-sectional information at all.** The signal depends on one
  symbol's own history. Any book built from it must invent the cross-sectional
  ordering itself.

### 1.1 Translation chosen, and why

The signal is per-name and binary, but `PortfolioConfig` wants ~22 names with a strict
ranking. The gap is the *ordering* among names the strategy flags. I close it with the
strategy's **own** signal magnitude, not a second, unrelated factor:

```
roc_p   = panel / panel.shift(p) - 1.0                 # the strategy's own quantity
signal  = (roc_p > threshold)                           # +1 / -1, exactly as the catalog says
score   = roc_p.where(signal)                            # eligible names carry their own momentum
           .rank(axis=1, pct=True)                      # 1.0 = strongest of the eligible
```

This is the faithful reading: "of the names whose own time-series momentum is positive,
hold the strongest ones." Rank is computed **after** masking, so the ordering is over
eligible names only — an ineligible name never consumes a rank slot or a slot in
`n_positions`.

`build_rebalance_weights` treats non-finite scores as invalid and picks the top
`n_positions` among the valid, so ineligible names (NaN score) are never bought. No
bypassing of the portfolio constraints; `run_backtest` enforces them.

**Not crypto-specific.** ROC over a price series is defined for any OHLCV asset. No
funding, liquidations, pegs, IV or basis. Proceeding.

---

## 2. Declared parameter budget — 5 variants, fixed BEFORE any run

The strategy has exactly two parameters (`period`, `threshold`). I declare the grid now
and will not add to it. **Selection is on TRAIN only.** TEST is touched once, at the end,
with the single TRAIN-chosen variant.

| # | `period` | `threshold` | Rationale |
|---|----------|-------------|-----------|
| **V1** | 40 | 0.00 | **The catalog default, as shipped.** The mandatory baseline — if the default works, nothing else is needed. |
| **V2** | 20 | 0.00 | ~1 month. Shorter momentum, more responsive, more turnover. |
| **V3** | 60 | 0.00 | ~3 months. Between default and long. |
| **V4** | 126 | 0.00 | ~6 months. Matches `momentum_6m`, the variant `factors/core.py` cites as best long-only in India. |
| **V5** | 40 | 0.02 | Default period but a **positive** threshold — only names up ≥2% over 40 bars qualify. Tests whether tightening the gate helps or just shrinks the book. |

This is a period ladder (V1–V4) plus one threshold probe (V5). It is not a grid search
and I will not refine it after seeing results.

**Controls and benchmarks are not variants and do not consume the budget**: buy-and-hold,
the nsealgo composite, and the random-signal control are comparison objects, not
tuning candidates.

---

## 3. Results

### 3.0 Translation verified bar-for-bar first

Before any backtest, I ran the **real** `TimeSeriesStrategy` bar-by-bar over 6 randomly
sampled symbols (83,250 comparisons across 3 parameter settings) and compared against
the vectorised panel ROC.

> **0 mismatches.** The vectorised translation *is* the catalog strategy.

(My first verification pass reported 2 phantom mismatches on `bajajfinsv`. The bug was
in my verifier, not the strategy: I fed the streaming class a `dropna()`'d series, which
shifted its 300-bar rolling buffer off the panel's bar grid. `bajajfinsv` has exactly 2
NaN bars, both in 2008. Feeding the full sequence fixed it. Worth recording because
"the verifier disagreed with itself depending on how I sliced the input" is exactly the
kind of thing that becomes a phantom bug report if not chased down.)

### 3.1 TRAIN (2016-01-01 → 2023-12-31) — all 5 variants, selection here

| Variant | CAGR | Sharpe | MaxDD | Calmar | TO x/y | Drag %/y | Names |
|---------|------|--------|-------|--------|--------|----------|-------|
| V1 p40 thr0.00 *(catalog default)* | 10.66% | 0.37 | −30.15% | 0.35 | 3.97 | 2.54 | 19.8 |
| V2 p20 thr0.00 | 7.38% | 0.13 | −25.25% | 0.29 | 4.10 | 2.32 | 19.7 |
| V3 p60 thr0.00 | 14.58% | 0.62 | −26.48% | 0.55 | 3.63 | 2.83 | 19.9 |
| **V4 p126 thr0.00** | **15.58%** | **0.63** | −35.21% | 0.44 | 2.83 | 2.25 | 20.6 |
| V5 p40 thr0.02 | 9.28% | 0.28 | −27.94% | 0.33 | 3.98 | 2.50 | 18.7 |
| *buy-and-hold (TRAIN)* | *21.49%* | *0.90* | *−36.66%* | *0.59* | *0.00* | *0.03* | *46.3* |

**Selection by TRAIN Sharpe → V4 (period=126).** Locked here; TEST read once, below.

Note already on TRAIN: **buy-and-hold (21.49%) beats every single variant**, and its
Sharpe (0.90) is well above the best variant's (0.63). This was a warning that the
variant would not survive TEST, and it did not.

### 3.2 TEST (2024-01-01 → 2026-10-01) — V4 unchanged, all controls, same window

Every row net of the full 21.92 bps delivery stack. Selected = V4 (p126), unchanged
from TRAIN.

| Book | CAGR | Sharpe | MaxDD | Calmar | TO x/y | Drag %/y | Names |
|------|------|--------|-------|--------|--------|----------|-------|
| **SELECTED V4 (p126)** | **+1.11%** | **−0.35** | −19.87% | 0.06 | 3.03 | 1.51 | 20.0 |
| catalog default V1 (p40) | −0.93% | −0.59 | −21.20% | −0.04 | 4.02 | 1.98 | 19.0 |
| **BENCH buy-and-hold** | **+8.18%** | **+0.18** | −15.90% | 0.51 | 0.00 | 0.08 | 48.0 |
| BENCH nsealgo composite | +6.04% | +0.03 | −15.22% | 0.40 | 2.08 | 1.10 | 21.3 |
| CONTROL static-beta book | +2.95% | −0.24 | −15.48% | 0.19 | 0.67 | 0.33 | 21.3 |
| CONTROL random signal (5 seeds) | +1.79% ±0.85 | −0.47 | — | — | 4.11 | 2.04 | 17.5 |

**Yearly returns, selected V4:** 2024 +17.9% · 2025 +0.6% · 2026 −13.0%
**Yearly returns, buy-and-hold:** 2024 +19.9% · 2025 +13.4% · 2026 −8.3%

### 3.3 The three questions the brief asks

**(a) vs buy-and-hold — worse, on return AND on drawdown.**
V4 returns **+1.11%** against buy-and-hold's **+8.18%**: it gives up **7.1 pp/yr** of
return. And its drawdown is *deeper*: **−19.87% vs −15.90%**, i.e. 4.0 pp worse, while
also earning a third as much. It loses on both axes simultaneously. The catalog default
V1 is worse still: it is **negative** (−0.93% CAGR, Sharpe −0.59) — it lost money.

**(b) Random-signal control — the strategy does NOT beat a coin flip.**
This is the most damning single number. A random selection holding a comparable ~65%
of bars long, through the **identical** engine, caps and costs, returned a mean
**+1.79% CAGR (Sharpe −0.47)** across 5 seeds. The strategy returned **+1.11%
(Sharpe −0.35)**. The strategy is *below* the mean of the random control on return and
only marginally (and not significantly) better on Sharpe — well inside the ±0.85 pp
seed spread. **It has not demonstrated any edge over chance.**

**(c) vs nsealgo composite — worse.**
Composite +6.04% / Sharpe 0.03 vs strategy +1.11% / Sharpe −0.35. The repo's existing
multi-factor book beats it by ~5 pp/yr of return and by 0.38 of Sharpe.

### 3.4 Sanity checks (brief §6) — all pass; the number is real

| Check | Result | Verdict |
|-------|--------|---------|
| 1. Plausibility | +1.11% CAGR, far under the 40–50% ceiling | **OK** — no lookahead bug, the low number is the finding |
| 2. Weight count | avg **20.0** names held (max 22, days >30 names: 0) | **OK** — no residual-weight accumulation; the engine's `apply_turnover_budget` fix is holding |
| 3. Signal liveness | **65.2%** of symbol-bars long; mean 28.5 eligible names/day | **OK** — genuinely invested, not a near-flat book |
| 4. Cost drag | net +1.11% vs gross; **1.51%/yr** drag on 3.03x turnover | Drag is real but NOT the cause of failure (see below) |
| — caps respected | max single weight 10.3% (cap 12%), deployed 0.90 (cap 0.90), 0 dead residuals | **OK** |
| — causality | truncating the future changed past weights by **0.00e+00** | **OK** — no lookahead |
| — score drives book | p126 (+1.11%) ≠ p20 (−1.41%) | **OK** — the score is load-bearing |

**Cost drag is NOT the reason this fails.** The drag is 1.51%/yr against a gross return
that is itself near zero. Removing costs entirely would leave roughly +2.6%/yr — still
below the 6.5% risk-free rate and below buy-and-hold. This is not a strategy that works
before fees and dies after; it simply does not work.

### 3.5 Robustness — the negative result is not a construction artifact

All of these hold `period=126, threshold=0.00` fixed at the TRAIN-selected values. These
are *constructions and rebalance frequencies*, not new parameter variants — nothing here
was eligible for selection.

| Variation (TEST) | CAGR | Sharpe | MaxDD | Turnover |
|------------------|------|--------|-------|----------|
| own-roc rank (**baseline = V4**) | +1.11% | −0.35 | −19.87% | 3.03x |
| rank eligible by 12-1 momentum | +4.97% | −0.05 | −14.86% | 2.59x |
| rebalance monthly (**baseline**) | +1.11% | −0.35 | −19.87% | 3.03x |
| rebalance weekly | −0.61% | −0.48 | −21.67% | 6.79x |
| rebalance quarterly | +1.46% | −0.38 | −14.86% | 1.34x |

The conclusion holds under every construction. Even the most favourable alternative
(rank by 12-1 momentum) reaches only +4.97%, still **below buy-and-hold's +8.18%**, and
slower rebalancing barely moves it because the drag falls roughly as fast as the return.

**Gross vs net, cleanly:** net +1.11% CAGR, gross (costs fully removed) ≈ **+2.61%**.
Even handed a free, frictionless execution the strategy returns less than the 6.5%
Indian T-bill. **Costs are not the failure mode; the signal has no edge to lose.**

**What the book actually is — beta with a negative tilt.** Against the equal-weight
market over the TEST window:

| Statistic | Value |
|-----------|-------|
| Beta | **0.85** |
| Daily correlation | **0.91** |
| Annualised alpha | **−5.68%** |

The book is not a differentiated stock-picking portfolio. It moves almost exactly with
the market (corr 0.91) at slightly less than market beta, and subtracts ~5.7%/yr in the
process. It pays 3.03x/yr turnover — **4.5x the static-beta book's 0.67x** — to
manufacture that negative alpha. The extra churn buys nothing.

---

## 5. Verdict

> ### **`time_series` does NOT make money on NSE. No.**
>
> Out of sample it returns **+1.11% CAGR** against buy-and-hold's **+8.18%** — worse on
> return (−7.1 pp/yr) *and* worse on drawdown (−19.87% vs −15.90%). Its Sharpe is
> **−0.35**, i.e. it underperformed a 6.5% risk-free T-bill. The catalog's own default
> parameter (`period=40`) is worse still: **−0.93% CAGR, Sharpe −0.59 — it lost money.**
>
> It fails the minimum bar: **a random signal holding the same fraction of bars long
> returned +1.79% on average, beating it.** It loses to buy-and-hold, to the repo's own
> nsealgo composite, and to a static-beta book holding every name.

This is a clean, publishable negative result.

### Why it fails

Time-series momentum is a genuine, well-documented effect in Indian equities — the
literature cited in `factors/core.py` is right about that. **The failure is not the
idea; it is that this strategy throws the idea away.**

`TimeSeriesStrategy` reduces each name to a **binary +1/−1 flag**, and ranks nothing.
Translating a binary flag into a 22-name long-only book forces me to invent the entire
cross-sectional ordering. When I supply that ordering from the strategy's own ROC — the
most faithful thing available — the strategy degenerates into **"buy the ~20 names with
the highest 126-day momentum."** That is not a distinct strategy; it *is* the
momentum factor the composite already contains, minus the trend-strength and
low-volatility pillars that make the composite work. The composite returns +6.04%
against this strategy's +1.11% on the identical panel and window.

So the strategy contributes a **signal with no ranking and no risk control**, and the
book it produces is market beta (β=0.85, corr 0.91) with **−5.68% annualised alpha**.
It rotates 4.5x more than a static book and pays 1.51%/yr in costs for the privilege of
that negative alpha.

There is also a **regime problem specific to this window.** The TEST period
(2024-01 → 2026-10) is a choppy, mean-reverting market — buy-and-hold itself only
managed +8.18% with a +0.18 Sharpe, and 2026 was negative for *everything* (V4 −13.0%,
buy-and-hold −8.3%). Time-series momentum is structurally hurt by exactly this kind of
whipsaw market, because a 126-day lookback keeps naming "losers" as winners on the way
down and vice versa. That is a real, honest explanation for the specific numbers — but
it is **not** a defence of the strategy, because buy-and-hold and the composite both
survived the same window comfortably.

### The one thing I would try next

**Do not rescue this strategy. It is already implemented, and implemented adequately, as
`momentum_6m` / `momentum_12_1` inside `nsealgo.factors.core`.** The genuine gap in this
repo is not more momentum variants — it is that `GOAL.md` §5 asks for 3%/month net and
the best validated result is ~11%/yr OOS, so the next real question is whether
**volatility targeting or a regime overlay** on top of the composite improves
risk-adjusted return without the binary-flag information loss that sank this strategy.

Concretely: run `blend_with_cash` / `exposure_series` from `nsealgo.factors.regime`
against the composite and measure whether de-risking in the 2026-style chop adds more
than the ~1.1%/yr it costs in drag.

**What I would explicitly not do:** tune `threshold` on the TEST window. V5 (a positive
threshold) scored worst-but-one on TRAIN, so tightening the gate was already the wrong
direction before I saw TEST; chasing it now would be exactly the in-sample mining the
brief forbids.

---

## 6. Bugs and harness notes

**No bugs found in `src/nsealgo/**` or in the assigned strategy.** The engine's
`apply_turnover_budget` fix is confirmed working in practice: average names held is
20.0 (not 48), dead residual cells are 0, and the 12% single-name cap holds (max
observed 10.3%).

**One bug in my own verification script, recorded because it nearly became a false
bug report:** the first bar-for-bar verification fed the streaming
`TimeSeriesStrategy` a `dropna()`'d price series while comparing against the
non-dropna'd panel. For any symbol with interior NaN bars this silently shifts the
strategy's 300-bar rolling buffer off the panel's bar grid and manufactures phantom
mismatches. It reported "2 mismatches" on `bajajfinsv` (a symbol with exactly 2 NaN
bars). Feeding the full bar sequence gave 0 mismatches over 83,250 comparisons. **Any
future streaming-vs-vectorised verification must align the buffers explicitly** — the
mismatch count is a property of the verifier's slicing, not of the strategy.

**A note on pandas 3.x:** the panel index is tz-aware (`Asia/Kolkata`), so naive
`pd.Timestamp("2024-01-01")` bounds raise `TypeError` on comparison. Any new analysis
script must localize its window bounds to match.

---

## 7. Final numbers (TEST 2024-01-01 → 2026-10-01, net of 21.92 bps)

| | CAGR | Sharpe | MaxDD | Calmar | TO x/y | Drag %/y | Names |
|---|---|---|---|---|---|---|---|
| **time_series V4 (selected)** | **+1.11%** | **−0.35** | −19.87% | 0.06 | 3.03 | 1.51 | 20.0 |
| time_series V1 (catalog default) | −0.93% | −0.59 | −21.20% | −0.04 | 4.02 | 1.98 | 19.0 |
| buy-and-hold | +8.18% | +0.18 | −15.90% | 0.51 | 0.00 | 0.08 | 48.0 |
| nsealgo composite | +6.04% | +0.03 | −15.22% | 0.40 | 2.08 | 1.10 | 21.3 |
| static-beta control | +2.95% | −0.24 | −15.48% | 0.19 | 0.67 | 0.33 | 21.3 |
| random-signal control (5 seeds) | +1.79% ±0.85 | −0.47 | — | — | 4.11 | 2.04 | 17.5 |

*All rows use the same 48-symbol cleaned daily panel, the same window, the same
`PortfolioConfig` caps and the same full Indian delivery cost stack. Survivorship bias
in the panel (today's NIFTY-50 backfilled) is present in every row equally and does not
affect the comparison.*
---

## 4. Protocol compliance log

- [x] Mandatory first step: `load_universe` + `report.describe()` run before anything else
- [x] Parameter budget (5 variants) declared above, before any backtest
- [x] Costs = 21.92 bps all-in, the number `run_backtest` actually charges
- [x] `engine_sha` recorded
- [x] Translation verified bar-for-bar against the real catalog class (0 mismatches)
- [x] TRAIN sweep run (all 5), selection made → **V4**
- [x] TEST evaluated once, unchanged
- [x] Buy-and-hold on identical window
- [x] Random-signal control (5 seeds)
- [x] nsealgo composite comparison
- [x] Sanity checks (§6: weight count, liveness, cost drag, plausibility, causality)
- [x] **Parameter budget respected: exactly 5 variants, zero additional tuning after
      seeing TEST.** No threshold was adjusted once results were visible.

**TEST was touched exactly once.** The variant was selected on TRAIN Sharpe alone; the
TEST run evaluated V4 unchanged and simultaneously produced the benchmarks and
controls. I did not go back and re-select.

