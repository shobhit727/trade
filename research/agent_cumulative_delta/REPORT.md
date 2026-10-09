# `cumulative_delta` on NSE NIFTY-50 — agent report

**Status: IN PROGRESS.** Header + declared budget committed before any run (brief §8.1).

---

## 1. Assignment

| | |
|---|---|
| Strategy | `cumulative_delta` |
| Source | `src/cryptobot/strategies/catalog/cumulative_delta_strategy.py` |
| Indicator | `cumulative_delta` — `src/cryptobot/strategies/indicators.py:375` |
| Crypto-specific? | **No.** Uses only close + volume. No funding, liquidations, peg, IV, basis. Daily-bar cousin of Chaikin Money Flow / OBV slope. Legitimate for NSE. |

### What the signal actually is

```python
# indicators.py:375 — verbatim
def cumulative_delta(closes, volumes, window: int = 30) -> float:
    delta = 0.0
    for i in range(-window, 0):
        if closes[i] > closes[i - 1]:   delta += volumes[i]
        elif closes[i] < closes[i - 1]: delta -= volumes[i]
    return float(delta)
```

Net buy pressure = Σ signed volume over the trailing `window` bars, where the sign is the
tick rule (up bar → +vol, down bar → −vol, flat bar → 0). It is a raw share-count sum, not
normalised by window length or turnover, so high-volume days dominate it.

Strategy mapping (`CumulativeDeltaStrategy.signal`): `+1` if `delta > 0`, `-1` if `delta < 0`,
`0` if flat or NaN (warmup).

**Long-only constraint.** Shorting does not exist in an Indian delivery account, so the `-1`
branch maps to **not held**. This is disclosed, not worked around.

## 2. Data

`data/nse/*_1d.csv` via the mandatory loader — no downloads.

| | |
|---|---|
| Loader | `nsealgo.data.loader.load_universe` (close panel, rules C1–C7) + `load_symbol` per symbol for the **volume** panel, so both share one cleaning history |
| TRAIN | 2016-01-01 → 2023-12-31 |
| TEST | 2024-01-01 → 2026-10-01 |
| Rebalance | monthly (`run_backtest(..., rebalance="M")`) |
| Cost stack | `CostModel(segment="delivery", slippage_bps=5)` |

**All backtest numbers below are net of `all_in_round_trip_bps(100_000)` = 21.92 bps**
(statutory 11.92 + 2×5 slippage), because `run_backtest` charges that and never calls
`fill_price`. The 11.92 figure appears only where `CostModel` is called directly
(the zero-cost gross leg). The two are never mixed.

## 3. DECLARED PARAMETER BUDGET — 5 variants, fixed before any run

At most 5 distinct parameter variants (brief §4). Declared here, before execution:

| # | Name | `window` | Cross-sectional construction |
|---|---|---|---|
| 1 | `V1_w20_delta_rank` | 20 | rank signalled names by delta itself |
| 2 | `V2_w30_delta_rank` | 30 (catalog default) | rank signalled names by delta itself |
| 3 | `V3_w60_delta_rank` | 60 | rank signalled names by delta itself |
| 4 | `V4_w30_mom_rank` | 30 | flag by delta, rank by 126d momentum (brief §5 recipe) |
| 5 | `V5_w30_blend` | 30 | mean of the delta rank and the momentum rank |

Portfolio construction fixed at `PortfolioConfig()` defaults (22 names, 12% single, 25%
sector, 10% cash, 35% turnover budget). Not a tuned parameter.

Variants 1–3 vary the window on the faithful translation; 4–5 vary the construction at the
catalog default so "is it the window or the construction?" is answerable on TRAIN.

## 4. PROTOCOL INTEGRITY DISCLOSURE — read this before the numbers

This run **inherits an interrupted previous run** in this same directory. Auditing it:

- `01_verify.py`, `02_train.py`, `03_test.py`, `04_sanity.py`, `common.py`, `panel.pkl` exist.
- No captured stdout from the previous run, so nothing can be trusted on faith.

**Contamination found.** `04_sanity.py:92` hard-codes an observation *about the TEST window*:

```
#     (from 03_test.py: 1/20 on Sharpe, 0/20 on CAGR -> NO)
```

So before I ran anything, the following was already known: **for the previous run's
TEST-selected variant, the negative control beat the strategy — 1/20 seeds on Sharpe,
0/20 on CAGR — i.e. the strategy did not beat a coin flip out-of-sample.** That is a
TEST-window observation and it was inherited, not chosen by me.

What is **not** contaminated:
- The actual TEST numbers (CAGR / Sharpe / MaxDD / B&H comparison) are **not** in any file.
  I have not seen them.
- The variant selection was documented as TRAIN-derived, and I **re-derive the TRAIN
  selection independently from scratch** before touching TEST.

**Mitigation, declared up front:**
1. Selection is re-made on TRAIN only. The frozen choice is recorded before TEST runs and is
   **not** changed afterwards, whatever TEST shows.
2. TEST is read exactly once for the frozen variant.
3. The remaining 4 variants are additionally run on TEST **purely as post-hoc disclosure**,
   clearly labelled as not-a-selection. This is more information for the reader, and it
   cannot launder the frozen choice because the choice is already fixed and written down.
4. The coin-flip control result is reported as **pre-confirmed by inheritance**, not as an
   out-of-sample surprise. I do not claim it as a clean test.

This is a **partially contaminated run**, declared rather than hidden. Per brief §4.4 the
requirement is disclosure, which this is.

---

## 5. Harness audit (done before running, on inherited scratch code)

Salvaged from the previous run rather than rewritten. Every claim below was checked against
the actual source, not assumed:

| Inherited piece | Verdict | Evidence |
|---|---|---|
| `run_backtest(panel, score, cm, cfg, "M")` signature | **correct** | `engine.py:371` |
| No lookahead | **correct** | `engine.py:415` — `held.shift(1) * rets`; targets from close of *t*, earned from *t+1* |
| `.returns/.equity/.weights/.metrics` on result | **correct** | `engine.py:108` `BacktestResult` |
| Cost = `all_in_round_trip_bps` (21.92) | **correct** | `engine.py:412`, `costs.py:219` |
| `_rebalance_dates` importable | **correct** | `engine.py:357` |
| `compute_metrics(..., annual_turnover=, cost_drag_annual=)` | **correct** | `metrics.py:86` |
| `build_composite_score(panel)` | **correct** | `factors/core.py:189` |
| Per-symbol delta rolling | **correct and necessary** | panel index is the *union* of all symbols' dates (`loader.py:250`); a symbol missing a bar would otherwise lose `window` bars of history per gap. The catalog loop walks one symbol's own sequence. Verified equal, not assumed. |
| Sharpe annualised √244, ddof=1, equity-curve DD, rf 6.5% | **correct** | `metrics.py:119-141` |
| `panel.pkl` cache | **to be re-verified** against a fresh load before use |

**Note on `04_sanity.py:88-89`** — it asserts costs are only ~0.3pp/yr and prints a
pre-baked conclusion ("gross is ALSO ~x%"). That is a comment left by the previous run, not
a computed result in this run. It will be re-derived, not trusted.

---

*Sections 6+ appended as results land.*

---

## 6. Step 1 — equivalence + data audit (`01_verify.py`)

`panel.pkl` cache was **re-verified bit-identical** to a fresh `load_universe` /
`load_symbol` load (`.equals()` True on both panels and on the symbol list). Trusted.

### Cleaning report (mandatory loader)

```
rows in 274,541 -> rows out 208,226
dropped pre-2008  66,312      dropped non-positive 0
dropped artifact        0      dropped extreme      3
excluded symbols: ['adanient', 'jiofin']   (C3 corrupt / <1000 bars)
panel (4629 dates x 48 symbols)  2008-01-01 -> 2026-10-01
```

48 tradable names (not 50: `adanient` is corrupt per C3, `jiofin` has <1000 bars).
13,966 NaN name-days in each panel — a symbol not trading on a given date, never forward-filled.

### Vectorised delta == catalog loop

Exact-sign match on **every bar of all 48 symbols** at every declared window, plus exact
raw-delta match on 20 synthetic paths (with flat days and zero-volume days seeded in):

| window | name-bars matched | synthetic paths |
|---|---|---|
| 20 | 207,266 / 207,266 | 20/20 |
| 30 | 206,786 / 206,786 | 20/20 |
| 60 | 205,346 / 205,346 | 20/20 |

The signal used downstream is the catalog's signal, not a lookalike.

### Signal liveness (TRAIN) — brief §6.3

| variant | long_frac | avg names flagged/day | days with <22 eligible |
|---|---|---|---|
| V1_w20 | 59.3% | 28.5 | 18.4% |
| V2_w30 | 61.4% | 29.5 | 15.2% |
| V3_w60 | 64.9% | 31.1 | 10.9% |

Comfortably live — nowhere near the always-flat failure mode. Mean run length of a long
state: 13.4 / 17.4 / 27.8 sessions for w=20/30/60 (median 5/5/4). Longer windows flip state
less often, which is why they cost less.

### What the delta is actually measuring (TRAIN, cross-sectional correlation)

Mean per-day correlation across names, `delta30` and `mom126` against the **forward**
21-day return, at several horizons:

| horizon | corr(delta30, fwd21d) | corr(mom126, fwd21d) |
|---|---|---|
| +1d | **+0.3681** | +0.3707 |
| +2d | +0.3517 | +0.3510 |
| +6d | +0.2814 | +0.2740 |
| +22d | +0.0075 | −0.0092 |

```
corr(delta30, mom126) = +0.2439   (TRAIN cross-sectional)
```

**This is the single most important diagnostic in the report.** Net buy pressure over 30
days predicts the next month about as well as 6-month momentum does (+0.368 vs +0.371), and
the two are correlated +0.244 with each other. So `cumulative_delta` is *mostly a
re-expression of momentum*, not an orthogonal money-flow edge. Any residual edge it has is
the part that is **not** momentum — and since the engine already ranks with a turnover
budget and the composite benchmark contains momentum, that residual is exactly what will be
charged ~0.3–2pp/yr of costs.

Prediction recorded **before** seeing any backtest: this should land near the momentum
benchmark, not beat it, and should lose to the nsealgo composite (which has momentum in it).

---

## 7. Step 2 — TRAIN results (`02_train.py`), all net of 21.92 bps round trip

TRAIN = 2016-01-01 → 2023-12-31, 1975 sessions, monthly rebalance.

| variant | CAGR | Sharpe | MaxDD | Calmar | Turn/y | Cost/y | names | long% | gross CAGR | drag |
|---|---|---|---|---|---|---|---|---|---|---|
| **BUY-AND-HOLD** | **21.46%** | **0.90** | −36.66% | 0.59 | 0.12x | 0.08% | 48 | 100% | — | — |
| **nsealgo composite** | **21.30%** | **0.96** | −32.92% | 0.65 | 1.96x | 1.00% | 21.8 | 100% | — | — |
| V1_w20_delta_rank | 16.46% | 0.71 | −33.17% | 0.50 | 4.05x | 1.66% | 28.7 | 59.3% | 16.93% | 0.47pp |
| V2_w30_delta_rank | 16.73% | 0.71 | −30.40% | 0.55 | 3.94x | 1.58% | 27.4 | 61.4% | 17.19% | 0.46pp |
| **V3_w60_delta_rank** | **18.94%** | **0.81** | −34.33% | 0.55 | 2.98x | 1.34% | 22.6 | 64.9% | 19.29% | 0.36pp |
| V4_w30_mom_rank | 16.82% | 0.73 | −30.28% | 0.56 | 3.72x | 1.56% | 25.7 | 61.4% | 17.26% | 0.44pp |
| V5_w30_blend | 15.58% | 0.65 | −30.50% | 0.51 | 3.83x | 1.50% | 26.2 | 61.4% | 16.03% | 0.44pp |

### The headline TRAIN fact: all five variants LOSE to both benchmarks

| | best variant | gap vs B&H | gap vs composite |
|---|---|---|---|
| CAGR | 18.94% (V3) | **−2.52 pp** | −2.36 pp |
| Sharpe | 0.81 (V3) | **−0.09** | −0.15 |
| MaxDD | −30.28% (V4) | **shallower by 6.4pp** | worse |

So the strategy buys a ~6pp shallower drawdown than buy-and-hold by giving up ~2.5pp of CAGR
— that is a risk profile, not an edge. This is exactly what §6 predicted from the correlation
diagnostic.

### Cost is NOT the problem — gross is also bad

V3 gross (zero-cost) CAGR is 19.29% vs 21.46% for buy-and-hold. Drag is only **0.36pp/yr**.
The strategy is unprofitable *before* costs. Per brief §6.4 there is no cost-rescue to report.

### TRAIN negative control (V2 vs 20 random seeds, eligible count matched per day)

```
random    CAGR 16.90% (sd 1.19)   Sharpe 0.76 (sd 0.08)   MaxDD -32.40%
strategy  CAGR 16.73%              Sharpe 0.71              MaxDD -30.40%
beats  5/20 seeds on Sharpe,  10/20 on CAGR
```

**5/20 on Sharpe is a coin flip.** On TRAIN the delta signal is indistinguishable from
randomly picking the same number of names.

### Yearly returns (net, TRAIN) — no single-year blowup

V3: 2016 +13.69 / 2017 +35.02 / 2018 +6.42 / 2019 +7.48 / 2020 +17.76 / 2021 +41.92 /
2022 +8.42 / 2023 +27.93. Positive in 8/8 years, but every year is below buy-and-hold's
equivalent except 2021–2023, which tracks the 2021 melt-up. Not concentrated in one name
or one year — the return stream is simply *too small*.

---

## 8. ❄️ SELECTION FROZEN — written before TEST is read

**SELECTED = `V3_w60_delta_rank`** (`window=60`, construction `delta_rank`).

Reason, stated entirely in TRAIN terms: best Sharpe (0.81) **and** best CAGR (18.94%) of the
5 declared variants. It is the only variant that reaches the 22-name target cleanly
(22.6 names) with the lowest turnover (2.98x/y) and lowest cost (1.34%/y).

This independently reproduces the selection documented in the inherited `03_test.py`
(18.94% / 0.81 / −34.33%) — the previous run's TRAIN-derived choice is confirmed, not
assumed.

**This selection is now fixed and will not be changed, whatever TEST shows.** The remaining
4 variants will additionally be run on TEST as post-hoc disclosure only (see §1.4).

---

## 9. Step 3 — TEST results, net of the full Indian delivery cost stack

**TEST = 2024-01-01 → 2026-10-01, 685 sessions, data end 2026-10-01.**
Variant `V3_w60_delta_rank`, frozen on TRAIN in §8, carried **unchanged**.

### Headline table

| | CAGR | Sharpe | MaxDD | Calmar | Turn/y | Cost drag/y | Avg names |
|---|---|---|---|---|---|---|---|
| **`cumulative_delta` (frozen)** | **0.34%** | **−0.40** | **−19.25%** | 0.02 | 3.47x | 0.85% | 23.1 |
| buy-and-hold | 8.16% | 0.18 | −15.91% | 0.51 | 0.36x | 0.09% | 48 |
| nsealgo composite | 6.55% | 0.07 | −14.84% | 0.44 | 2.07x | 0.55% | 21.3 |
| random control (20 seeds, mean) | 5.32% (sd 1.67) | −0.05 (sd 0.15) | −13.70% | — | — | — | — |

Cost basis: `all_in_round_trip_bps(100_000)` = **21.92 bps** (11.92 statutory + 2×5 slippage),
which is what `run_backtest` charges. `nsealgo.cli costs` independently confirms 11.92 bps at
Rs 1,00,000/side against the 11.65–11.66 published reference.

### TEST vs buy-and-hold — worse on BOTH axes

| axis | strategy | B&H | gap | |
|---|---|---|---|---|
| CAGR | 0.34% | 8.16% | **−7.82 pp** | WORSE |
| Sharpe | −0.40 | 0.18 | −0.58 | WORSE |
| MaxDD | −19.25% | −15.91% | **−3.34 pp** | WORSE (deeper) |

Not a risk/return trade — dominated on return *and* drawdown simultaneously.

### Yearly (net)

| | 2024 | 2025 | 2026 (9m) |
|---|---|---|---|
| `cumulative_delta` | 13.46% | 3.91% | −14.37% |
| buy-and-hold | 20.00% | 13.34% | −8.37% |
| nsealgo composite | 22.57% | 7.16% | −9.01% |

Worse than buy-and-hold in **every single year**, including the down year — the signature of
a high-turnover signal being chopped up rather than a defensive one.

### Negative control — did not beat a coin flip

```
random    CAGR 5.32% (sd 1.67)   Sharpe -0.05 (sd 0.15)   MaxDD -13.70%
strategy  CAGR 0.34%              Sharpe -0.40              MaxDD -19.25%
beats  1/20 seeds on Sharpe,  0/20 on CAGR
```

**This reproduces the inherited contamination note exactly** (`04_sanity.py:92`: 1/20 Sharpe,
0/20 CAGR). The previous run's TEST observation was accurate, and it was a negative one.

Per §1.4 this control is reported as **pre-confirmed by inheritance, not as a clean
out-of-sample surprise**. It is the weakest link in the run's integrity and is disclosed as such.

### Cost diagnostic — no cost-rescue available

```
gross CAGR (zero cost)  0.69%
net   CAGR              0.34%
drag                   0.35 pp/yr   (turnover 3.47x/y)
```

Gross is **also** ~0.7%. The strategy is unprofitable before costs. Brief §6.4 case: there is
no version of this result that is "really" profitable with cheaper execution.

### Sanity checks (brief §6) — all pass, so the negative is real

| check | result | verdict |
|---|---|---|
| 6.1 Plausibility | CAGR 0.34% << 50% cap | **OK** — no lookahead/compounding bug |
| 6.2 Weight count | avg 23.1, median 22, max 30, 0/685 days >30 names | **OK** — no residual accretion |
| 6.3 Weight caps | gross ≤ 0.9000 (= 1 − cash buffer), max single 0.0913 ≤ 0.12 | **OK** — caps never breached |
| 6.3b Metrics reconcile | recomputed CAGR 0.34% / MaxDD −19.25%, exact match | **OK** |
| 6.4 Signal liveness | 60.8% of name-days long, 29.2 flagged/day | **OK** — not always-flat |
| 6.5 Cost drag | gross 0.69% > net 0.34% | **OK** — drag real but tiny |
| 6.6 Coin flip | 1/20 Sharpe, 0/20 CAGR | **FAILS** — this is the finding |

### Harness cross-validation — the negative is not a harness artifact

`nsealgo.cli validate --walk-forward` reproduces the project's authoritative published
result **exactly**: 10.97% OOS CAGR, Sharpe 0.44, MaxDD −12.91% (48d), 11/13 positive years.
Same engine, same `CostModel`, same metrics module. The harness is sound.

Note also that the reference strategy's own most recent fold
(`test 2024-10-21→2026-10-01 | OOS CAGR −1.55% Sharpe −1.05`) is *also* deeply negative, and
buy-and-hold over my TEST window is only 8.16% CAGR / Sharpe 0.18. **The TEST window is
genuinely hard.** That is context, not an excuse: `cumulative_delta` is still dominated by
buy-and-hold on return *and* drawdown inside that hard window.

---

## 10. Post-hoc disclosure — all 5 variants on TEST (not a selection)

Disclosed per §1.4 so the reader can see whether the TRAIN pick was lucky or unlucky. **V3
stands as frozen; nothing below changes the choice.**

| variant | TRAIN Sharpe | TRAIN CAGR | TEST Sharpe | TEST CAGR | TEST MaxDD | names | vs B&H | vs composite |
|---|---|---|---|---|---|---|---|---|
| V1_w20_delta_rank | 0.71 | 16.46% | −0.35 | 1.60% | −18.83% | 28.8 | −6.55pp | −4.95pp |
| V2_w30_delta_rank | 0.71 | 16.73% | −0.35 | 1.23% | −19.22% | 27.4 | −6.93pp | −5.32pp |
| **V3_w60 (frozen)** | **0.81** | **18.94%** | **−0.40** | **0.34%** | **−19.25%** | 23.1 | **−7.82pp** | **−6.21pp** |
| V4_w30_mom_rank | 0.73 | 16.82% | −0.18 | 3.14% | −17.07% | 26.6 | −5.02pp | −3.41pp |
| V5_w30_blend | 0.65 | 15.58% | −0.28 | 1.95% | −17.79% | 26.4 | −6.20pp | −4.60pp |

Three facts that matter more than any single number:

1. **All 5 variants lose to buy-and-hold and to the composite.** Range −5.02 to −7.82pp.
   This is not a bad pick inside a good family; the whole family is negative.
2. **All 5 variants have NEGATIVE out-of-sample Sharpe** (−0.18 to −0.40). Even the best.
3. **TRAIN rank does not generalise — rank correlation TRAIN vs TEST Sharpe = −0.400.** The
   TRAIN-best (V3) is the **TEST-worst of 5**. Every variant's TEST Sharpe is below its TRAIN
   Sharpe. The variant that looked best in-sample was the worst out-of-sample: a textbook
   demonstration of why the split exists.

Every variant also has a **deeper** MaxDD than buy-and-hold (−15.91%) and the composite
(−14.84%). Dominated on both axes, five times out of five.

---

## 11. Why it failed — attribution

`V4_w30_mom_rank` is "gate on delta, rank by momentum", so it differs from plain momentum
*only* by the gate. Running momentum with no delta gate isolates what the gate contributes:

| | TRAIN | TEST |
|---|---|---|
| momentum, **gated** on delta>0 | 16.82% / Sharpe 0.73 / 25.7 names | 3.14% / Sharpe −0.18 / 26.6 names |
| momentum, **ungated** | 18.38% / Sharpe 0.78 / 22.2 names | 2.60% / Sharpe −0.22 / 21.3 names |
| **gate's contribution** | **−1.56pp CAGR, −0.05 Sharpe** | **+0.54pp CAGR, +0.04 Sharpe** |
| buy-and-hold | 21.46% / 0.90 | 8.16% / 0.18 |

**The gate's sign flips between windows** (−1.56pp TRAIN, +0.54pp TEST). That is the
signature of noise, not signal. And on TEST, ranking by delta itself (V3, 0.34%) is *worse*
than ranking by momentum (V4, 3.14%) — so the delta's own ranking content is worse than the
thing it correlates with.

The mechanism is also visible in the position counts. The delta gate removes ~35–39% of names
on any given day (60.8% long), shrinking the investable set **below the 22-name target**, so
the engine holds 26.6 names instead of 21.3 and must re-rank them all monthly:

| | names held | turnover/y | cost/y |
|---|---|---|---|
| gated | 26.6 | 3.87x | 1.00% |
| ungated | 21.3 | 2.76x | 0.70% |

**The gate adds 41% more turnover and adds nothing to the return.** That is the whole failure
mechanism: `cumulative_delta` selects *fewer* names on the strength of a signal that is +0.244
correlated with 6-month momentum and predicts the next month at +0.368 — statistically
indistinguishable from momentum itself (+0.371). It re-expresses momentum, then pays extra
turnover for the privilege, and momentum alone is already beaten by buy-and-hold in this
sample.

---

## 12. VERDICT

### Does `cumulative_delta` make money on NSE?

**NO.** Out-of-sample on 2024-01-01 → 2026-10-01 (data end 2026-10-01) the TRAIN-selected
variant returned **0.34% CAGR with a Sharpe of −0.40** — negative risk-adjusted return over
2.8 years. It lost to buy-and-hold by 7.82pp of CAGR, lost to the nsealgo composite by 6.21pp,
had a **deeper** drawdown than both, and failed to beat a matched random signal on 19 of 20
seeds. All 5 declared variants were negative out-of-sample. All sanity checks pass, so the
negative is a property of the strategy, not a bug.

This is a **useful, publishable negative result**, not a failure of the work. `cumulative_delta`
is a legitimate daily-bar signal — it is simply not an *edge* on NIFTY-50 once the Indian
delivery cost stack is charged.

### Most likely reason

The delta is a **redundant re-expression of momentum** (corr +0.244 with 126d momentum;
both predict the next 21d return at ~+0.37), so it has no orthogonal information to add. Used
as a ranker it is worse than momentum; used as a gate it shrinks the investable set below the
22-name target, forcing 3.9x/yr turnover instead of 2.8x/yr, and pays ~0.3pp/yr more in costs
for a gate whose sign flips between windows. Net: strictly dominated.

### The one thing I would try next

**Stop treating delta level as the signal; treat it as a *divergence* signal.** The raw
`sum(sign(Δclose) × volume)` conflates two things — genuine institutional accumulation, and
simply "a name that went up a lot". Divided by traded value (Chaikin Money Flow) and taken as
the **difference between a short and a long window** (e.g. CMF(5) − CMF(60)), the momentum
component largely cancels and what remains is the buy/sell-pressure divergence that the
current formulation throws away. That is the one genuinely untested idea the catalog's
indicator leaves on the table, and it is orthogonal to the momentum the current version
merely restates. It would need a fresh TRAIN-only budget; I would not test it here because
this run's 5-variant budget is spent and TEST is no longer clean for me.

---

## 13. Run integrity footer

- **Nothing committed or pushed.** `HEAD` unchanged at `6a7ce6e`. All work is untracked under
  `research/agent_cumulative_delta/`.
- **No file modified outside my scratch directory.** `src/nsealgo/**`, `src/cryptobot/**`,
  `tests/**`, `GOAL.md`, `reports/**` all untouched by this run.
- **Parameter budget: 5 declared, 5 tested, 0 exceeded.** Variants V1–V5 declared in §3 before
  any run; V3 selected on TRAIN in §8 before TEST was read. The two extra scripts
  (`05_disclosure.py` all-variants-on-TEST, `06_attribution.py` ungated momentum) are
  **diagnostics and benchmarks, not strategy variants**, and are labelled as such in their own
  docstrings. No threshold was tuned against an equity curve.
- **TEST contamination, disclosed not concealed** (§1.4). I inherited a prior observation of the
  TEST coin-flip control (1/20 Sharpe, 0/20 CAGR) from `04_sanity.py:92` *before* running
  anything. My independent TEST run reproduced it exactly. This is the reason the coin-flip
  result is presented as pre-confirmed rather than as a clean surprise, and it is the single
  caveat on this run's integrity. Mitigation: the TRAIN selection was re-derived from scratch
  and independently reproduced the inherited choice (18.94% / 0.81 / −34.33%), then frozen in
  writing before TEST was read.
- **Inherited scratch work audited, not trusted.** `panel.pkl` re-verified bit-identical to a
  fresh loader run; every `run_backtest` / `CostModel` / `compute_metrics` call site checked
  against source; per-symbol rolling justified from `loader.py:250`; the vectorised delta proved
  equal to the catalog loop on 619,398 name-bars plus 60 synthetic paths.
- **Lint:** `.venv/bin/ruff check research/agent_cumulative_delta/*.py` → all checks passed.
- **Costs never used to rescue a result.** Base case is the full 21.92 bps; the zero-cost leg
  appears only to isolate viability, and it made the result *worse*, not better.
- **Every nsealgo number is quoted with its end date: 2026-10-01.**

### Files

| file | purpose |
|---|---|
| `common.py` | shared harness — panels, vectorised delta, variants, benchmarks, controls |
| `01_verify.py` | data audit + vectorised-vs-catalog equivalence + liveness + correlation diagnostic |
| `02_train.py` | TRAIN only, all 5 variants, B&H, composite, 20-seed control |
| `03_test.py` | TEST, frozen variant, read once |
| `04_sanity.py` | brief §6 sanity checks + independent metric reconciliation |
| `05_disclosure.py` | post-hoc: all 5 variants on TEST (not a selection) |
| `06_attribution.py` | diagnostic: what the delta gate contributes vs no gate |
| `panel.pkl` | panel cache, re-verified against a fresh load |

### Reproduce

```bash
.venv/bin/python research/agent_cumulative_delta/01_verify.py
.venv/bin/python research/agent_cumulative_delta/02_train.py
.venv/bin/python research/agent_cumulative_delta/03_test.py
.venv/bin/python research/agent_cumulative_delta/04_sanity.py
.venv/bin/python research/agent_cumulative_delta/05_disclosure.py
.venv/bin/python research/agent_cumulative_delta/06_attribution.py
```

---

## TL;DR

`cumulative_delta` on NSE NIFTY-50, TRAIN 2016-01-01→2023-12-31, TEST 2024-01-01→2026-10-01
(data end 2026-10-01), monthly rebalance, net of the full Indian delivery stack (21.92 bps
round trip), 22 names, long-only.

**TEST: 0.34% CAGR, Sharpe −0.40, MaxDD −19.25%, Calmar 0.02, turnover 3.47x/yr, cost drag
0.85%/y, 23.1 names held.**
B&H over the identical window: 8.16% / 0.18 / −15.91%. nsealgo composite: 6.55% / 0.07 / −14.84%.

**Verdict: NO.** Worse than buy-and-hold on return (−7.82pp) *and* on drawdown (−3.34pp),
worse than the composite (−6.21pp), and it failed to beat a matched random signal on 19 of 20
seeds. All 5 declared variants were negative out-of-sample, all with Sharpe < 0 and drawdowns
deeper than both benchmarks. The TRAIN-best variant ranked **last** of 5 on TEST (rank
correlation −0.400). Cause: the delta is a redundant re-expression of momentum (corr +0.244
with 126d momentum; both predict fwd-21d at ~+0.37), so it adds no orthogonal information while
its gate shrinks the investable set below the 22-name target and raises turnover 41%.
Gross CAGR is also only 0.69% — there is no cost-rescue. Next idea: normalise to traded value
and take the **short-minus-long window spread** (e.g. CMF(5) − CMF(60)) so the momentum
component cancels and only the pressure *divergence* remains — untested here, because this
run's 5-variant budget is spent and TEST is no longer clean for me.
