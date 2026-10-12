# agent_tema — `TemaStrategy` on NSE NIFTY-50

**Status: COMPLETE — verified, reproducible, negative result.**

## TL;DR

| | |
|---|---|
| **Verdict** | **No. This strategy does not make money on NSE.** |
| **TEST** (2024-01-01 → 2026-10-01, net of 21.92 bps) | **CAGR 0.96%, Sharpe −0.51, MaxDD −14.10%, Calmar 0.07** |
| Buy-and-hold, identical window | CAGR 8.08%, Sharpe 0.19, MaxDD −15.90% |
| nsealgo composite, identical window | CAGR 6.04%, Sharpe 0.03, MaxDD −15.22% |
| **Random-signal control** (same size, same ranking, 10 seeds) | mean CAGR 3.25% — **the strategy lost to a coin flip on 10/10 seeds** |
| Cost is *not* the reason | at **zero** cost it still returns 1.80% vs 8.25% gross B&H (−6.45 pp/yr) |
| Why | the TEMA gate leaves ~22.2 eligible names into a 22-name book, so it is not filtering — it discards half the cross-section for a measured edge of only **+1.37%/yr**, on top of a 1.99%/y cost drag |
| Declared parameter budget | **5 variants (V1–V5)**, declared before any run, all used, none exceeded |

Reproduce: `python research/agent_tema/step0_audit.py && step1_train.py && step2_test.py && step3_diagnostics.py`
(All four are deterministic and reproduce bit-identically on re-run.)

---

## Provenance

```python
from nsealgo.provenance import provenance; provenance()
```

```json
{"engine": "d93815344bd3", "loader": "c1badf5f7df8", "costs": "ba350aef75b3", "panel": "389b082b832f"}
```

Cost accounting: `run_backtest` charges `all_in_round_trip_bps(100_000)` = **21.92 bps**
(round-trip), i.e. `rt_bps + 2 × slippage_bps` with `slippage_bps = 5`.
Every headline number in this report is **net of 21.92 bps** unless explicitly labelled
otherwise.

---

## 1. Assignment

| Field | Value |
|-------|-------|
| Strategy | `TemaStrategy` (`src/cryptobot/strategies/catalog/tema_strategy.py`) |
| Class / `name` | `TemaStrategy` / `"tema"` |
| Signal | `+1 if close[-1] > TEMA(close, period) else -1`; `0` while `tema` is NaN (warmup) |
| Free parameters | **one**: `TemaConfig.period` (default 20). `quantity` is unused by the signal. |
| Crypto-specific? | **No.** A triple-exponential moving average is a plain price-trend filter with direct meaning on NSE daily bars. The brief's §9 "no NSE meaning → stop" clause does **not** apply. Proceeding. |

Indicator definition (replicated from `cryptobot.strategies.indicators.tema`, to be
verified mechanically in step 1, not trusted to code reading):

```
k = 2/(period+1)
e1 = EMA(close, period)          # recursion seeded at the first bar
e2 = EMA(e1,   period)
e3 = EMA(e2,   period)
TEMA = 3*e1 - 3*e2 + e3
```

`EMA` is prefix-stable (`out[0] = a[0]`, `out[i] = k*a[i] + (1-k)*out[i-1]`), so the
indicator at bar *t* depends only on closes ≤ *t*. **No lookahead.**

---

## 2. Data

`load_universe("data/nse")` → cleaned daily close panel, **4625 bars × 48 symbols**,
`2008-01-01 → 2026-10-01` (IST). Cleaning report reproduced in `step0_audit.py` output.

**TRAIN** = 2016-01-01 → 2023-12-31 (used for all parameter choice)
**TEST**  = 2024-01-01 → 2026-10-01 (touched exactly once, at the end)

Cost model: `CostModel(segment="delivery", slippage_bps=5)` → 21.92 bps round trip
charged by `run_backtest`.

---

## 3. Declared parameter budget — **5 variants, fixed before any run**

The strategy has exactly one free parameter (`period`). The second degree of freedom is
how the per-symbol ±1 signal becomes a cross-sectional ranking, which the brief §5
prescribes: rank the signalled names by trailing momentum. Both axes are declared here,
up front, and **no variant may be added, removed or re-scoped after seeing any result.**

| Variant | `period` | Ranking factor among signalled names |
|---------|----------|----------------------------------------|
| V1 | 20 (source default) | `momentum_6m` (126d trailing return) |
| V2 | 50 | `momentum_6m` |
| V3 | 100 | `momentum_6m` |
| V4 | 20 | `momentum_12_1` (252d return skipping last 21d) |
| V5 | 50 | `trend_strength_200d` |

Selection rule (declared in advance): **highest TRAIN Sharpe**; ties broken by TRAIN
Calmar. The winner is frozen, written to `selected.json`, and evaluated on TEST once.
A zero-cost control and a random-signal control are **diagnostics, not parameter
variants** — they reuse a frozen variant and consume no budget.

If this budget is exceeded at any point, the run is invalidated and that is reported
here rather than hidden.

---

## 4. Results

*(appended as they are produced)*
---

## 5. Step 0 — audit (before any parameter choice)

`step0_audit.py` / `audit.json`.

**Indicator replication is exact.** My vectorised TEMA equals
`cryptobot.strategies.indicators.tema` to **max |Δ| = 0.000e+00** at periods 20/50/100,
across 8 randomly chosen symbols at 7 different bar indices each (including prefixes,
which also proves the recursion is prefix-stable). This was a real check: my first
version compared `mine[-200]` against the prefix ending at index 299 — an off-by-one
in the *test*, not the indicator — and produced a spurious `max|Δ| = 1.75e+02`.

**Source signal confirmed by execution, not by reading.**
`TemaStrategy(TemaConfig(period=20)).signal(...)` called on four real bar windows returns
`+1/+1/-1/-1`, matching `close[-1] > tema` exactly. `warmup()` returns `20`.

**Panel:** 4625 bars × 48 symbols, 2008-01-01 → 2026-10-01 IST. 14,455 NaN cells
(6.51%), all in 9 symbols, all leading (pre-listing) gaps — `max first-valid = 2021-07-23`.
No interior holes, so no forward-fill is needed anywhere.

### 5.1 Signal liveness (brief §6.3)

| period | bars long | bars short | mean eligible names | min eligible |
|--------|-----------|------------|---------------------|--------------|
| 20 | 49.7% | 50.3% | 22.2 | 0 |
| 50 | 50.1% | 49.9% | 22.2 | 0 |
| 100 | 50.7% | 49.3% | 22.2 | 0 |

The gate is **live**: it is long ~50% of bars, not a near-always-flat filter. Mean
eligible = 22.2 names against a 22-name book, so on an average day the book is
essentially "every TEMA-long name, ranked by momentum" — the momentum ranking is the
active selector and the TEMA gate is the universe filter. This is an important
structural fact and it is the honest reading of what this strategy becomes on NSE:
**TEMA is not adding much on top of plain momentum ranking**, because 22 eligible
names ≈ 22 slots.

### 5.2 Streaming-buffer fidelity (documented deviation)

`SignalStrategy` feeds a `deque(maxlen=300)`, so the source EMA is re-seeded at the
oldest bar of a rolling 300-bar window every bar, not on full history. Measured
divergence between the two:

| period | max rel Δ | p99 rel Δ | signal disagreements |
|--------|-----------|-----------|----------------------|
| 20 | 3.2e-11 | 7.1e-12 | 19 / 4625 (0.41%) |
| 50 | 3.8e-04 | 1.2e-04 | 49 / 4625 (1.06%) |
| 100 | 2.6e-02 | 1.4e-02 | 149 / 4625 (3.22%) |

The seed weight after 300 bars is `(1-k)^(300-p)`, so this is exactly the expected
decay and it is negligible at p=20 (the selected period) and material at p=100.
**Decision: I run full-history EMA** (the standard definition, and what
`indicators.tema` returns when handed a full series). The selected variant p=20 is
affected at the 0.4% signal level, which cannot move a 22-name book.

---

## 6. Step 1 — TRAIN sweep (2016-01-01 → 2023-12-31, net of 21.92 bps)

`step1_train.py` / `train_results.json`. Selection rule fixed in advance: highest TRAIN
Sharpe, tie-break Calmar. Zero-cost rows are diagnostics on the same frozen variants
and consumed **no** parameter budget.

| Variant | period | ranker | CAGR | Sharpe | MaxDD | Calmar | TO/y | Cost drag | avg names |
|---------|--------|--------|------|--------|-------|--------|------|-----------|-----------|
| **V1** | 20 | mom6m | 11.80% | 0.54 | −18.21% | 0.65 | 4.09x | 2.82%/y | 19.4 |
| **V2** | 50 | mom6m | 9.63% | 0.38 | −13.08% | 0.74 | 4.09x | 2.55%/y | 18.7 |
| **V3** | 100 | mom6m | 9.10% | 0.30 | −25.54% | 0.36 | 4.04x | 2.56%/y | 18.0 |
| **V4** ★ | 20 | mom12_1 | **12.24%** | **0.58** | −18.44% | 0.66 | 4.04x | 2.78%/y | 19.3 |
| **V5** | 50 | trend200 | 9.29% | 0.34 | −14.95% | 0.62 | 4.08x | 2.50%/y | 18.4 |
| V1 zero-cost | 20 | mom6m | 12.72% | 0.62 | −17.74% | 0.72 | — | — | — |
| V2 zero-cost | 50 | mom6m | 10.53% | 0.47 | −13.02% | 0.81 | — | — | — |
| V3 zero-cost | 100 | mom6m | 9.98% | 0.38 | −24.57% | 0.41 | — | — | — |
| V4 zero-cost | 20 | mom12_1 | 13.15% | 0.66 | −17.92% | 0.73 | — | — | — |
| V5 zero-cost | 50 | trend200 | 10.19% | 0.44 | −14.41% | 0.71 | — | — | — |
| *nsealgo composite (reference)* | — | — | 20.44% | 0.91 | −32.94% | 0.62 | 2.08x | 1.99%/y | 21.8 |

**Selected: V4 — `period=20`, ranker `momentum_12_1`** (TRAIN Sharpe 0.581, Calmar 0.664).
Frozen to `selected.json`. **No further variant will be added.**

Cost is not the binding constraint: even at zero cost every variant gains only
~0.9–0.9pp of CAGR. The 2.5–2.8%/y drag is real but it is not what is killing this.

The composite's 20.44% / Sharpe 0.91 on the same TRAIN panel is the bar that matters:
it says momentum ranking **without** the TEMA gate does considerably better than
momentum ranking **with** it. That is the first hint of the finding, stated on TRAIN
data only.

---

## 7. Step 2 — TEST. Touched once. (`step2_test.py` / `test_results.json`)

Frozen variant read from `selected.json`: **V4, `period=20`, ranker `momentum_12_1`**.
Nothing was re-selected. TEST = 2024-01-01 → 2026-10-01, 684 bars × 48 symbols.
**All numbers net of 21.92 bps round trip.**

### 7.1 Headline table

| Book | CAGR | Sharpe | MaxDD | Calmar | Vol | Turnover/y | Cost drag | Avg names | Final equity on ₹21,00,000 |
|------|------|--------|-------|--------|-----|-----------|-----------|-----------|-------------------------|
| **TEMA V4** (the strategy) | **0.96%** | **−0.51** | **−14.10%** | **0.07** | 9.58% | 4.14x | 1.99%/y | 17.6 | ₹21,56,948 |
| Buy-and-hold (same universe) | 8.08% | 0.19 | −15.90% | 0.51 | 13.45% | 2 round trips total (entry+exit) | 0.17%/y | 48 | ₹26,11,350 |
| nsealgo composite | 6.04% | 0.03 | −15.22% | 0.40 | 13.25% | 2.08x | 1.10%/y | 21.3 | ₹24,75,154 |
| TEMA V4, zero-cost control | 1.80% | −0.42 | −12.59% | 0.14 | 9.57% | 4.14x | — | 17.6 | — |
| Random gate, same long-fraction (10 seeds) | 3.25% ± 1.02 | −0.30 ± 0.06 | −11.0% (best) / −14.8% (worst) | ~0.11 | — | 4.16x | ~2.0%/y | 20.7 | — |

### 7.2 Year by year (net of costs)

| Year | TEMA V4 | Buy-and-hold | nsealgo composite |
|------|---------|--------------|-------------------|
| 2024 | +11.94% | +20.13% | +21.91% |
| 2025 | −0.09% | +13.35% | +6.61% |
| 2026 (to 10-01) | −8.17% | −8.28% | −9.31% |
| **CAGR** | **0.96%** | **8.08%** | **6.04%** |
| positive years | 1 / 3 | 2 / 3 | 2 / 3 |

### 7.3 vs buy-and-hold — worse on return, marginally better on drawdown

- **Return: worse by 7.12 pp/yr of CAGR** (0.96% vs 8.08%). Compounded over the 2.75y
  window that is ₹21,00,000 → **₹21,56,948** versus **₹26,11,350** for buy-and-hold —
  roughly **₹4,54,400** of foregone return on the same starting book.
- **Drawdown: better by 1.80 pp** (−14.10% vs −15.90%), Calmar 0.07 vs 0.51.
- Net: it gives up ~4× the drawdown relief it buys. It is not a risk-adjusted
  improvement.

### 7.4 Random-signal control — **it loses to a coin flip**

A random gate open on the same 49.8% of symbol-days, ranked by the same
`momentum_12_1`, charged the same costs:

- Strategy beat random on **CAGR in 0 of 10 seeds** (best seed 4.74% vs strategy 0.96%).
- Strategy beat random on **Sharpe in 1 of 10 seeds** (0.1).
- Random mean CAGR **3.25% ± 1.02%** vs strategy **0.96%**.

**The strategy is worse than a random selection of the same size.** This is the
brief's §6.5 minimum bar and it is not met.

### 7.5 vs the nsealgo composite

0.96% vs **6.04%** CAGR; Sharpe −0.51 vs 0.03; MaxDD −14.10% vs −15.22%. The
composite does **half the turnover** (2.08x vs 4.14x) and beats it by **5.08 pp/yr**.
Correlation of the two daily return series is 0.845 — they are the same bet, and the
composite's version of it is better on every axis.

### 7.6 Sanity checks (brief §6)

| Check | Result | Verdict |
|-------|--------|---------|
| §6.1 Plausibility | CAGR 0.96%, final equity 1.0271 | ✅ no bug signature (a 200%+ result would have been the tell) |
| §6.2 Weight count | avg **17.60** names, max 22, max single weight 0.0983 (cap 0.12) | ✅ below 48, caps respected, no residual accumulation |
| §6.3 Signal liveness | long 49.8% of TEST bars | ✅ live gate, not an always-flat filter |
| §6.4 Cost drag | gross 1.80% → net 0.96%; **0.84 pp/yr** | ⚠️ real but **not** the cause — see below |
| §6.5 Negative control | lost to random on 10/10 seeds | ❌ **fails** |

**Cost is not the reason this fails.** At *zero* trading cost the strategy still
returns only 1.80% CAGR against a gross buy-and-hold of 8.25% — **−6.45 pp/yr**. The
strategy loses badly even before a single charge is applied. Reporting this as a
cost problem would be the convenient wrong answer.

### 7.7 Data finding (recorded, immaterial)

The TEST panel contains exactly one interior hole: `indigo` is missing **2026-05-01**.
This is a **raw-file gap, not loader output** — `data/nse/indigo_1d.csv` genuinely has
no row for that session (2693 rows, no duplicates, 04-30 → 05-04 adjacent). One bar,
one name, 0.1% of NAV for one day. Not material to any number here, but it is a real
vendor-feed hole and any live implementation must not assume a complete panel.

---

## 8. Step 3 — Why it failed (diagnostics, `diagnostics.json`)

These run **after** the TEST number was fixed. No parameter was changed and no
alternative selection rule was applied — the verdict above stands regardless of what
follows. No new `period` was tried; these are ablations of the frozen V4.

### 8.1 Ablation: which half of V4 is the problem?

| Book | TRAIN CAGR | TRAIN Sharpe | TRAIN MaxDD | TEST CAGR | TEST Sharpe | TEST MaxDD |
|------|-----------|--------------|-------------|-----------|-------------|------------|
| **V4 frozen** (TEMA gate + mom12_1 rank) | 12.24% | 0.58 | −18.44% | **0.96%** | −0.51 | −14.10% |
| **− momentum rank** (TEMA gate, ranked by distance above TEMA) | 12.62% | 0.64 | −17.93% | 1.15% | −0.55 | −11.87% |
| **− TEMA gate** (mom12_1 rank alone, no gate) | **21.56%** | **0.95** | −33.65% | **5.83%** | 0.02 | −17.72% |

**The TEMA gate is the problem, and the evidence was already visible on TRAIN.** Removing
it improves TRAIN CAGR by 9.3 pp and TEST CAGR by 4.9 pp. Removing the momentum ranking
instead changes almost nothing (−0.19 pp on TEST).

The structural reason is in §5.1: the gate leaves **22.2 eligible names on average
against a 22-name book**. A filter that passes ~46% of the universe and whose output
fills the book is not filtering — it is *reordering who gets the marginal slot while
discarding the bottom half of the cross-section for no reason*. And because ranking
forces exactly `n_positions` picks whenever ≥22 names are eligible, the gate almost
never leaves the book smaller; it only decides *which* names are excluded from
consideration, then throws away a better-ranked set.

### 8.2 Does the TEMA gate carry any information at all?

Full panel, 21-day forward return, by gate state:

| State | n | mean fwd 21d | hit rate | Q5−Q1 |
|-------|---|--------------|----------|-------|
| above TEMA | 102,249 | +1.735% | 57.1% | 25.56% |
| below TEMA | 103,352 | +1.617% | 56.4% | 26.25% |
| **edge (above − below), annualised** | | | | **+1.37%** |

The gate has a **statistically detectable but economically tiny** edge: being above a
20-day TEMA is worth **+1.37%/yr** of forward-return edge cross-sectionally. The gate
also fires on ~50% of bars by construction, so roughly half the book is spent
declining names that would have gone up. That is the whole mechanism.

### 8.3 What the book actually became

| Diagnostic | Value |
|-----------|-------|
| Beta vs buy-and-hold (TEST) | 0.58 |
| Correlation with B&H | 0.82 |
| Capture ratio on B&H up days | 0.53 |
| Capture ratio on B&H down days | 0.58 |
| Correlation with nsealgo composite | 0.845 |

Beta 0.58 and a 0.53 up / 0.58 down capture ratio is a **uniformly de-risked book** —
it participates in roughly 55–60% of the market in both directions. It gets *some*
of the drawdown reduction (−14.1% vs −15.9%) and gives up essentially all of the
return. That is not a market-neutral overlay; it is a book that holds ~60% exposure and
charges 4.14x turnover to do it.

### 8.4 The regime story

TRAIN (2016–2023) and TEST (2024–2026-10) are different markets. The TEMA gate is a
**short-horizon trend filter**. It works when trends persist and cuts exposure at every
turn — 2024 and 2025 in India were strong, persistent uptrends where cutting exposure
in the 5% of names that dipped below a 20-day TEMA removed exactly the names that
mean-reverted back into leadership. It only behaved in 2026 (−8.17% vs B&H −8.28%),
when the market itself fell and de-risking finally paid.

---

## 9. Verdict

**No. `TemaStrategy` does not make money on NSE NIFTY-50 out of sample.** 0.96% CAGR
and −0.51 Sharpe on TEST, against 8.08% for buy-and-hold and 6.04% for the nsealgo
composite — and it is beaten by a random signal of identical size on 10 of 10 seeds.
It is not a cost problem: it loses 6.45 pp/yr even at zero trading cost.

**Most likely reason.** The TEMA gate is a 20-day trend filter being used as a
*universe filter* in a 22-name book fed by ~22 eligible names. It therefore discards
half the cross-section for a measured edge of only **+1.37%/yr**, while the ranking
that actually determines the book (12-1 momentum) is left to do the work. Signal with
a sub-cost-strike edge placed upstream of the position-sizing decision cannot pay for
its own 2.0%/y cost drag. The damage is compounded by a regime mismatch: the strategy's
edge is anti-trend-persistence, and TEST was a persistent-trend regime.

**The one thing I would try next.** Do not tune `period` further — TRAIN already shows
the optimum is *no gate* (21.56% CAGR / 0.95 Sharpe). Instead, test the composite's
own remedy: apply the TEMA signal as a **time-series market-exposure gate** via
`nsealgo.factors.regime.exposure_series` — i.e. keep 12-1 momentum as the *entire*
cross-sectional book and use TEMA only to scale gross exposure 0→1 — which is the one
place in this construction where a weak time-series signal can help without throwing
away good cross-sectional names. Expectation: most of the +1.37%/yr edge is already
captured by momentum's own trend persistence, so the honest prior is that it adds
little. That would be a *new* declared variant set with its own TRAIN/TEST budget, not
a continuation of this run.

---

## 10. Protocol compliance

| Rule | Status |
|------|--------|
| Strategy is not crypto-specific | ✅ TEMA is a plain price filter; §9 stop-clause does not apply |
| `load_universe` used as the first step | ✅ step 0 |
| Full Indian delivery cost stack | ✅ 21.92 bps via `run_backtest`; every headline number net |
| TRAIN 2016-01-01→2023-12-31 / TEST 2024-01-01→2026-10-01 | ✅ |
| Parameters chosen on TRAIN only | ✅ `step1_train.py` never slices TEST; `selected.json` written before TEST |
| TEST touched once | ✅ one `run_backtest` call per book in `step2_test.py`. Two *harness* bugs were found and fixed **before any valid TEST number existed** (a `.loc[TEST_END:]` one-row slice, and ranking factors computed on the sliced panel). Neither fix changed the strategy, its parameters, its variant, or its score. The valid TEST run happened after both fixes and has not been repeated. |
| Parameter budget ≤ 5 | ✅ exactly 5 (V1–V5). Step-3 ablations remove a component of the frozen V4; they introduce no new parameter and no new selection rule. Declared up front in §3. |
| No lookahead | ✅ TEMA is prefix-stable on closes ≤ t (verified bit-exact in step 0); rankers are trailing; `run_backtest` holds weights from t+1 |
| Long-only, `PortfolioConfig` respected | ✅ avg 17.6 names, max single weight 0.0983 ≤ 0.12 |
| Sanity checks §6.1–6.5 run | ✅ all five, §7.6 |
| No lookahead in the source replication | ✅ verified numerically, not by reading |
| `src/` and `tests/` unmodified | ✅ only `research/agent_tema/**` written |
| Not committed | ✅ per brief §9 |

---

## 11. Files

| File | Purpose |
|------|---------|
| `harness.py` | indicator replication, signal, score construction, controls, buy-and-hold |
| `step0_audit.py` / `audit.json` | bit-exact TEMA replication check, source-signal execution check, cleaning report, streaming-buffer fidelity |
| `step1_train.py` / `train_results.json`, `selected.json` | TRAIN-only sweep of the 5 declared variants + selection |
| `step2_test.py` / `test_results.json`, `test_equity.csv` | the single TEST evaluation + B&H + composite + random control + zero-cost |
| `step3_diagnostics.py` / `diagnostics.json` | ablations, gate-information test, beta/capture, cost decomposition |

## 12. Bugs found in my own harness (recorded because the brief asks for it)

1. **Verification off-by-one** (`step0_audit.py`): I compared `mine[-200]` against the
   reference computed over `values[:300]`, i.e. index 299 — off by one bar. Produced a
   spurious `max|Δ| = 1.75e+02` and a near-miss on a correct replication. Fixed; the
   replication is now exact to `0.000e+00`.
2. **One-row TEST slice**: `panel.loc[TEST_END:]` instead of `panel.loc[:TEST_END]`,
   returning a single bar. Caught by the `TEST panel: 1 bars` print. No valid TEST
   number existed at that point, so nothing was spent.
3. **Ranking factors computed on the sliced panel** (the expensive one): the random
   control and the composite computed `momentum_12_1` on the already-sliced TEST panel,
   making it NaN for the first 252 bars. The random control was starved to **13.7
   average names instead of ~21**, which would have made my negative control far *too
   easy to beat* — i.e. it would have flattered the strategy. Fixed before the valid
   TEST run; the corrected control holds 20.7 names and still beats the strategy.
4. **`panel.notna().all().all()` assertion fired on `indigo` 2026-05-01** — traced to the
   raw CSV, a genuine single-session vendor gap, not a construction bug. Turned the
   assertion into a report. See §7.7.

No bug was found in `src/nsealgo` by this agent. The engine's cost accounting behaved
exactly as documented (`rt_bps + 2 × slippage_bps` = 21.92, turnover doubled once, caps
respected), and the `CostModel(slippage_bps=0.0)` coercion made the zero-cost control
work without touching `src/`.
