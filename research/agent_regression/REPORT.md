# Agent report — `regression_strategy`

**Assigned strategy:** `src/cryptobot/strategies/catalog/regression_strategy.py`
(`RegressionStrategy`, `name = "regression"`)

**Status:** IN PROGRESS — header written before any backtest was run, per brief §8.

---

## 0. Provenance

```python
from nsealgo.provenance import provenance; provenance()
```

| key | sha (first 12) |
|-----|----------------|
| `costs` | `ba350aef75b3` |
| `engine` | `d93815344bd3` |
| `loader` | `c1badf5f7df8` |
| `panel` | `389b082b832f` |

Cost calibration measured in this session (not copied from the brief):

| quantity | value |
|---|---|
| `round_trip_bps(100_000)` | **11.92 bps** (statutory only) |
| `all_in_round_trip_bps(100_000)`, `slippage_bps=5` | **21.92 bps** ← what `run_backtest` charges |
| `all_in_round_trip_bps(100_000)`, `slippage_bps=0.0` (float) | **11.92 bps** ← zero-slippage control |

`CostModel(slippage_bps=0.0)` constructs cleanly (the `__post_init__` coercion works),
so a genuine zero-cost control run is possible.

---

## 1. What the signal actually is — read the code, not the name

The module docstring says **"Linear regression"**. The body does not compute a
regression. It is:

```python
def signal(self, closes, highs, lows, volumes):
    m = sma(closes, self.config.period)      # simple moving average, period=20
    if m != m:
        return 0                             # warm-up -> flat
    return 1 if closes[-1] > m else -1       # price vs SMA
```

There is **no slope, no least-squares fit, no residual, no r-squared**. The only
parameter is `period` (default 20); `quantity` is unused by the signal.

**Finding F1 (code/label mismatch).** `regression_strategy` is an **SMA-distance
trend filter**, not a regression. It is the same family as `ma_cross`,
`distance_ma` and `triple_ma`, and the results should be read alongside theirs. Any
report calling this "linear regression" would be wrong. I test **what the code does**.

**What a genuine linear regression would mean here** (slope of price on time over the
lookback window) is *not* implemented, so it cannot be tested without editing `src/`,
which the brief forbids. It is the obvious "one thing to try next" if this fails.

Note the catalog signal is **±1, never 0 after warm-up**. On a long-only book a −1
signal has no expression; the only actionable content is "is this name above its own
`period`-day mean".

---

## 2. Data used

```
load_universe("data/nse") -> panel  shape (4625, 48)
index  2008-01-01 → 2026-10-01  tz=Asia/Kolkata
cleaning: rows in 274,541 → out 207,687
  dropped pre-2008 66,312 · artifact 0 · non-positive 0 · extreme 3 · frozen 539
  excluded symbols: adanient, jiofin
```

Daily (`1d`) bars only, as the brief mandates. `1h`/`5m`/`15m` are not used: this is a
daily-bar trend filter and the intraday windows are far too short to validate anything.
**No intraday evidence is claimed.**

---

## 3. Protocol

| Set | Window |
|-----|--------|
| TRAIN | 2016-01-01 → 2023-12-31 |
| TEST  | 2024-01-01 → 2026-10-01 |

TRAIN used for selection. TEST touched once, at the end.

---

## 4. DECLARED PARAMETER BUDGET — 5 variants, fixed before any run

The strategy has exactly one free parameter (`period`). The other degree of freedom is
how a per-symbol ±1 flag becomes a cross-sectional score for a long-only book.

| # | Variant | period | score construction |
|---|---------|--------|--------------------|
| V1 | `p20_flag` | 20 | binary flag, neutral tie-break — the catalog rule as written |
| V2 | `p50_flag` | 50 | binary flag — tests a medium window |
| V3 | `p200_flag` | 200 | binary flag — the classic slow-trend window |
| V4 | `p50_momrank` | 50 | 126d trailing return, percentile-ranked **among flagged names only** |
| V5 | `p20_strength` | 20 | (close−SMA20)/close, cross-sectional z, kept only where flagged |

Selection rule on TRAIN: highest Sharpe; ties broken by Calmar. Fixed in advance.

Controls (not variants — they are not candidates and cannot be selected):
* buy-and-hold equal-weight universe, net of one all-in round trip (21.92 bps)
* `nsealgo` composite score
* **random signal** matched on fraction of bars long, seeds 1..10
* **zero-cost control** — same variant re-run with `slippage_bps=0.0` (11.92 bps)

Variants tested: **5/5**. Selection made on TRAIN only.

---

## 5. Results

### 5.1 TRAIN (2016-01-01 → 2023-12-31) — 1973 bars, 48 symbols

All five declared variants, net of 21.92 bps all-in, monthly rebalance.

| variant | period | score | CAGR | Sharpe | MaxDD | Calmar | live % | avg names | turn/y |
|---|---|---|---|---|---|---|---|---|---|
| V1_p20_flag | 20 | flag | 11.13% | 0.46 | −26.18% | 0.43 | 54.9% | 19.6 | 4.01x |
| V2_p50_flag | 50 | flag | 11.37% | 0.46 | −23.29% | 0.49 | 58.5% | 19.8 | 3.68x |
| V3_p200_flag | 200 | flag | 14.54% | 0.59 | −35.62% | 0.41 | 65.1% | 20.8 | 2.43x |
| **V4_p50_momrank** | **50** | **momrank** | **13.48%** | **0.60** | **−18.36%** | **0.73** | 58.2% | 19.7 | 3.74x |
| V5_p20_strength | 20 | strength | 7.01% | 0.10 | −24.49% | 0.29 | 54.9% | 19.7 | 4.12x |
| *buy-and-hold* | — | — | **22.20%** | **0.91** | −37.97% | 0.58 | — | 48 | — |
| *nsealgo composite* | — | — | 20.72% | 0.93 | −32.94% | 0.63 | — | 21.8 | — |

**Selected: `V4_p50_momrank`** — highest TRAIN Sharpe (0.60), and also the best Calmar
(0.73) and shallowest drawdown (−18.36%). The pre-declared rule selects it
unambiguously; no tie-break was needed.

**The headline TRAIN fact: every variant loses to buy-and-hold by a wide margin.**
The best variant trails the equal-weight universe by **8.72 pp/yr** of CAGR. The
strategy is a *concentration* play (22 names out of 48) with no sector or
single-name alpha strong enough to pay for the concentration.

Note the only variant with a higher CAGR than V4, V3 (p200, 14.54%), gets there with
a −35.6% drawdown and the worst Calmar of the five. V4 is better on risk-adjusted
return, which is what the declared rule measures.

### 5.2 Sanity checks (brief §6)

| check | result | verdict |
|---|---|---|
| Plausibility (≤40–50% CAGR) | 7.0–14.5% | ✅ no bug signature |
| Avg names held | 19.6–20.8 (target 22, `max_names` 30) | ✅ no residual accumulation |
| Signal liveness (>5%) | 54.9–65.1% of cells | ✅ genuinely long most of the time |
| Cost drag | +0.85 pp/yr of CAGR (see §5.4) | ⚠️ material but not fatal |
| Negative control | beat 10/10 random seeds | ✅ see below |

### 5.3 Negative control — random signal, 10 seeds, TRAIN

Matched on fraction of bars long (58.2%), 21.92 bps.

| | CAGR | Sharpe | MaxDD | Calmar |
|---|---|---|---|---|
| V4_p50_momrank | **13.48%** | **0.60** | **−18.36%** | **0.73** |
| random mean (10 seeds) | 11.89% | 0.50 | −27.07% | 0.44 |
| random range | 10.46–12.85% | 0.38–0.57 | −20.4 to −34.4% | 0.33–0.56 |

**Strategy beat 10/10 random seeds on CAGR** (mean edge **+1.59 pp/yr**), and 10/10 on
Sharpe. So the SMA filter *does* carry some information — it is not a coin flip.

**Harness note (methodology fix I had to make):** my first random control drew a 0/1
mask only. Every "live" name then tied at 1.0, and `run_backtest` breaks ties with a
stable argsort — i.e. column order — so the "random" book was the alphabetically-first
live names. That is not a random book. Fixed by drawing a *second* independent uniform
for the score, masked to the live cells, so coverage matches *and* the choice of which
22 names to hold is genuinely random. The corrected numbers are the ones reported here.
The uncorrected version flattered random to 13.92% and would have inverted the verdict.

### 5.4 Cost drag and the zero-cost control — TRAIN, V4

| | all-in bps | CAGR | Sharpe | MaxDD | Calmar |
|---|---|---|---|---|---|
| V4 at `slippage_bps=5` | 21.92 | 13.48% | 0.60 | −18.36% | 0.73 |
| V4 at `slippage_bps=0.0` | 11.92 | 14.33% | 0.67 | −18.30% | 0.78 |
| **difference** | −10.00 | **+0.85 pp/yr** | +0.07 | ~0 | +0.05 |

**Cost drag = 0.85 pp/yr of CAGR** on 3.74x annual turnover.

The engine reports `cost_drag_annual = 2.78%/y`, which is larger than the 0.85 pp CAGR
gap. That is not a contradiction: the engine's figure is in **linear** normalised-equity
units, and on a 13.5% CAGR book a 2.78% linear charge compounds down to ~0.85 pp of
geometric CAGR. The two are consistent; only the CAGR difference is comparable across
strategies.

`CostModel(slippage_bps=0.0)` accepted the float cleanly — the `__post_init__`
`Decimal(str(x))` coercion works, so the zero-cost control was runnable. Had it not
been, this control would have been impossible to measure through the engine (the
documented failure mode: a `TypeError` deferred to `Decimal + float` deep inside
`all_in_round_trip_bps`).

**The zero-cost control does not rescue the result.** Removing 10 bps of slippage buys
back 0.85 pp; the gap to buy-and-hold is 8.72 pp. Costs are not why this strategy
fails. **The failure is structural, not a fee problem.**

### 5.5 Signal diagnostic — does the filter itself work? (TRAIN only)

Before any portfolio construction: for every symbol-day, is the name above its own
SMA50? Compare forward 21-day returns of flagged vs unflagged cells.

| period | flag rate | mean raw fwd | t | median raw fwd | rank spread | t |
|---|---|---|---|---|---|---|
| SMA20 | 54.7% | +1.973% vs +1.832% (**+0.141pp**) | **+2.27** | +1.642% vs +1.743% | −1.515pp | −7.84 |
| SMA50 | 57.7% | +1.790% vs +2.090% (**−0.300pp**) | **−4.72** | +1.466% vs +2.012% | −2.011pp | −10.31 |
| SMA200 | 59.5% | +1.714% vs +2.223% (**−0.509pp**) | **−7.92** | +1.374% vs +2.219% | −0.578pp | −2.93 |

**This is the most important result in the report, and it contradicts the backtest.**

The SMA filter has **no usable forward-return information**. On TRAIN:
* **SMA50 and SMA200 are significantly NEGATIVE** (t = −4.72 and −7.92). Names below
  their own 50/200-day mean outperformed names above it over the next month.
* SMA20 is marginally positive on the mean (+0.14pp, t = 2.27) but its *median* is
  negative, so even that is a right-tail artefact.
* The **rank spread is negative for all three** (t = −2.9 to −10.3). Under the null
  (a flag drawn at random at the same rate) this is ~0 at any flag rate, because a
  random subset of a uniform distribution still has mean 0.5. A significantly
  negative rank spread means the average flagged name sits *below* the average
  unflagged name in the cross-section.

So V4's +1.59 pp edge over random is **not** coming from the filter being a good
predictor. It is coming from the **momentum ranking** that V4 layers on top
(126d trailing return, ranked among flagged names). The filter is acting as a
*restrictor* that trims the momentum universe; the alpha is the momentum, which is not
this strategy's contribution.

That also explains V5 (`strength`, 7.01%) being the worst variant: `strength` ranks by
how far above the SMA a name is — i.e. it ranks by *pure* filter strength, with no
momentum term — and it duly performs like the filter measures, badly.

### 5.6 Honest disclosure — a protocol slip

My **first** run of the signal diagnostic (the one that errored partway, and a later
line that printed pooled 2008–2026 figures) computed over the **whole** panel, so it
included TEST-window bars. Those pooled numbers were aggregate forward-return
statistics, not TEST portfolio performance, and they are **superseded** by §5.5 which
is TRAIN-only. No TEST *portfolio result* was viewed before selection was locked, and
`selected_variant.json` was written before the diagnostic existed. But the brief says
"never look at TEST while iterating", and a pooled statistic is a look. Flagging it
rather than hiding it. The discrepancy is itself informative: pooled over
2008–2026 the raw mean favours flagged names (+1.75% vs +1.49%), while TRAIN-only it
does not — the filter's sign flips between the two windows.

### 5.7 **TEST — out-of-sample (2024-01-01 → 2026-10-01), 684 bars, 48 symbols**

The locked variant `V4_p50_momrank`, unchanged from selection. Net of 21.92 bps.

| | CAGR | Sharpe | MaxDD | Calmar | turn/y | cost drag | avg names |
|---|---|---|---|---|---|---|---|
| **`regression` V4_p50_momrank** | **0.35%** | **−0.43** | **−22.27%** | **0.02** | 3.75x | 1.88%/y | 19.1 |
| buy-and-hold | **8.18%** | 0.18 | **−15.90%** | 0.51 | — | — | 48 |
| nsealgo composite | 6.04% | 0.03 | −15.22% | 0.40 | — | — | 21.3 |

**TEST vs buy-and-hold: worse on every axis.**
* **Return: −7.83 pp/yr of CAGR.** Total return +0.98% over 2.75 years vs +24.7% for
  the equal-weight universe.
* **Drawdown: worse.** −22.27% vs −15.90%, i.e. 40% deeper. The strategy was supposed
  to reduce risk by concentrating in names in an uptrend; it did the opposite.
* **Sharpe: −0.43 vs +0.18.** Negative Sharpe net of the 6.5% T-bill proxy means it
  lost to holding cash.

Calendar years (strategy): 2024 **+18.5%**, 2025 **+1.0%**, 2026-to-Oct **−15.6%**.

All five variants were also run on TEST for completeness (selection was already
locked; these are not selectable):

| variant | TRAIN Sharpe | TRAIN CAGR | **TEST CAGR** | **TEST Sharpe** | **TEST MaxDD** |
|---|---|---|---|---|---|
| V1_p20_flag | 0.46 | 11.13% | 0.60% | −0.53 | −19.09% |
| V2_p50_flag | 0.46 | 11.37% | 0.91% | −0.44 | −19.84% |
| V3_p200_flag | 0.59 | 14.54% | 1.63% | −0.33 | −19.23% |
| **V4_p50_momrank** (selected) | 0.60 | 13.48% | **0.35%** | **−0.43** | **−22.27%** |
| V5_p20_strength | 0.10 | 7.01% | −1.33% | −0.80 | −18.43% |

**Every single variant collapsed out-of-sample.** TRAIN 7–14.5% → TEST −1.3 to +1.6%.
Sharpe went negative for all five. This is not one unlucky parameter choice; the whole
family fails the same way. Note V3 had the second-best TRAIN Sharpe and the best TEST
CAGR — switching to it now would be exactly the cherry-pick this protocol exists to
prevent, and it is still −6.55 pp/yr against buy-and-hold.

### 5.8 TEST negative control — random signal, 10 seeds

| | CAGR | Sharpe | MaxDD | Calmar |
|---|---|---|---|---|
| V4_p50_momrank | **0.35%** | **−0.43** | −22.27% | 0.02 |
| random mean (10 seeds) | **3.00%** | −0.33 | −12.01% | 0.27 |
| random range | 1.46–5.77% | −0.52 to −0.04 | −8.4 to −14.2% | 0.12–0.69 |

**The strategy lost to 10/10 random seeds on TEST** (mean edge **−2.65 pp/yr**).

This is the cleanest negative result in the report, and it directly reverses TRAIN:
* TRAIN: beat random **10/10**, edge **+1.59 pp/yr**
* TEST: lost to random **10/10**, edge **−2.65 pp/yr**

The TRAIN "edge" was not an edge. A signal that beats a coin flip on TRAIN and loses to
it 10-for-10 on TEST is textbook overfitting — and my parameter budget (5 variants) did
not prevent it, because a single parameter (`period`) cannot create 10/10 by accident.
The overfit was in the *choice of V4 among five*, on a TRAIN Sharpe that separated the
five by only 0.14 (0.46–0.60). That is not a selection margin worth trusting.

Note the random book also has negative Sharpe on TEST (−0.33) and 3.00% CAGR vs
buy-and-hold 8.18%. **The whole 22-name concentrated structure is losing to the
equal-weight universe in this window, regardless of signal.** The strategy is not
special in failing; it is ordinary, and the market was the thing to beat.

### 5.9 TEST zero-cost control

| | all-in bps | CAGR | Sharpe | MaxDD | Calmar |
|---|---|---|---|---|---|
| V4 at `slippage_bps=5` | 21.92 | 0.35% | −0.43 | −22.27% | 0.02 |
| V4 at `slippage_bps=0.0` | 11.92 | **1.11%** | −0.37 | −20.98% | 0.05 |
| difference | −10.00 | **+0.76 pp/yr** | +0.06 | +1.29pp | +0.03 |

**Cost drag on TEST = 0.76 pp/yr of CAGR** on 3.75x turnover (engine linear figure
1.88%/y; the CAGR gap is smaller because a ~0.4% book barely compounds).

**The zero-cost control settles the question.** Removing all slippage turns 0.35% into
1.11% — the strategy is still 7.07 pp/yr behind buy-and-hold, still negative-Sharpe,
still loses to random. **A result that only exists at zero cost is not a result**; here
even the zero-cost version does not exist. The strategy is unviable, and **not because
of fees.**

### 5.10 TEST signal diagnostic — the filter is actively harmful

| period | flag rate | mean raw fwd (flag vs unflag) | diff | t | rank spread | t |
|---|---|---|---|---|---|---|
| SMA20 | 51.6% | +0.443% vs +1.321% | **−0.879pp** | **−10.72** | −1.210pp | −3.74 |
| SMA50 | 50.5% | +0.404% vs +1.342% | **−0.938pp** | **−11.46** | −2.152pp | −6.66 |
| SMA200 | 38.8% | −0.079% vs +1.456% | **−1.535pp** | **−18.81** | −0.902pp | −2.72 |

On TEST the signal is **significantly negative for every window**, and much more
strongly so than on TRAIN. The median forward return tells the same story and is not an
outlier artefact: median flagged 0.40% vs median unflagged 1.01% for SMA50.

**Buying names that are above their own moving average made money *less* likely over
the next month, with t-statistics of −11 to −19, in the most recent 2.75 years of
NIFTY-50 data.** The effect is large and precise, not marginal. This is the root cause,
and it is visible without any portfolio construction at all — no costs, no 22-name book,
no ranking.

The TRAIN and TEST diagnostics agree in direction (both negative for SMA50/SMA200),
which is why this is a trustworthy negative rather than a noise artifact: the TRAIN
window that selected the variant already said the filter did not work, and I did not
believe it.

---

## 6. Verdict

**No. `regression_strategy` does not make money on NSE NIFTY-50.** Out-of-sample it
returned **0.35%/yr with a Sharpe of −0.43 and a 22.3% drawdown**, against buy-and-hold
at **8.18%/yr** and a random-signal control at **3.00%/yr**. It lost to a coin flip
10/10 out of sample.

| question (brief §7) | answer |
|---|---|
| beat buy-and-hold on return? | **No** — −7.83 pp/yr |
| beat buy-and-hold on drawdown? | **No** — −22.27% vs −15.90% |
| beat a random signal? | **No** — lost 10/10 on TEST (was 10/10 on TRAIN) |
| beat the nsealgo composite? | **No** — 0.35% vs 6.04% |
| positive in ≥60% of years? | **No** — 2/3 TEST calendar years positive, but 2026 −15.6% |

---

## 7. Why it failed, and the one thing to try next

**Most likely reason (evidence-backed, in order of confidence):**

1. **The signal is the wrong sign for this market and this period.** Names above their
   own 50/200-day mean had significantly *worse* forward 21-day returns than names below
   it, on both windows, at t = −5 to −19. Buying the in-an-uptrend name is a
   buy-high rule. This accounts for the whole failure independently of construction.

2. **The strategy concentrates; the market rewarded breadth.** It holds ~19 of 48 names
   with a 12% single-name cap, while buy-and-hold holds all 48. In TEST the equal-weight
   universe made 8.18% and *every* concentrated 22-name book — including the random
   control at 3.00% — made less. The concentration, not the signal, is the dominant
   loss channel.

3. **The signal itself contains no alpha.** All the TRAIN outperformance came from the
   126d momentum ranking V4 layered on top, which is `nsealgo`'s composite signal, not
   this strategy's contribution. The catalog strategy added nothing on top of it.

4. **Costs are a minor contributor.** 0.76 pp/yr on TEST. Removing slippage entirely
   does not make the strategy viable (§5.9). Not the reason.

**Not the reason** (checked and ruled out): a lookahead bug, a weight-accumulation bug
(avg names 18.5–20.8, consistent with `n_positions=22` under the turnover budget), a
signal-liveness failure (51–65% of bars long), or an implausible-return bug (all
results within a 0–15% band).

**The one thing I would try next — and it is a code change, not a parameter change:**

The strategy is **named "Linear regression" and contains no regression.** That is
finding F1, and it is the most likely explanation for why this slot was assigned: the
intended signal was almost certainly the **OLS slope of price on time over the
lookback window** — `sign(β)` from regressing `log(close)` on `1..period` — which is a
*different animal* from the price-vs-SMA filter that got implemented. A fitted slope
normalises the move by its dispersion and reacts to the *shape* of the trend, whereas
`close > SMA` is a single level comparison that ignores how the move was achieved. I
expect slope-based signals to behave differently, and the evidence above says any
future version of this slot must be judged on its own diagnostics (§5.10-style forward
return by flag), because the current implementation's flag has none.

I did not test it: it would require editing `src/`, which this brief forbids.

**Secondary recommendation: retire this slot.** A price-vs-SMA filter is not a distinct
hypothesis on NSE — it is a strict subset of the composite's trend factor, and the
composite already does 6.04%/yr on TEST where this does 0.35%. If the slot is kept, it
should be re-specified as a regression slope and re-run from scratch; if it is not
re-specified, it should be dropped rather than re-parameterised. Tuning `period` across
more values would produce exactly the TRAIN-looks-good / TEST-fails pattern documented
above, and would be a misuse of the parameter budget rather than an honest attempt.

---

## 8. Reproduction

```bash
.venv/bin/python research/agent_regression/harness.py train    # selection
.venv/bin/python research/agent_regression/harness.py test     # TEST, once
PYTHONPATH=research/agent_regression .venv/bin/python research/agent_regression/controls.py train
PYTHONPATH=research/agent_regression .venv/bin/python research/agent_regression/controls.py test
```

`selected_variant.json` is written **before** the TEST run and is what the TEST
evaluation used. Provenance for every run above:

```
engine  d93815344bd3   loader c1badf5f7df8   costs ba350aef75b3   panel 389b082b832f
```

Parameters tested: **5 of 5 declared**, none added, none removed. Selection was made on
TRAIN Sharpe only, once, before TEST was run.

## 9. Findings worth propagating

| # | finding | where |
|---|---------|-------|
| F1 | `regression_strategy` computes an SMA filter, **not** a linear regression. Docstring and code disagree. | `src/cryptobot/strategies/catalog/regression_strategy.py:1,27-31` |
| F2 | A random-signal control built from a bare 0/1 mask is **not random**: `run_backtest` breaks score ties with a stable argsort, so the "random" book becomes the alphabetically-first live names. Needs a second independent uniform for the score. | `src/nsealgo/backtest/engine.py` (`build_rebalance_weights`, stable sort) |
| F3 | The engine's `cost_drag_annual` is in linear equity units and is **not** comparable across strategies; only the CAGR difference is. On a 13.5% book, 2.78%/y linear = 0.85 pp CAGR. | `src/nsealgo/backtest/engine.py` |
| F4 | `price > SMA(n)` is a **significantly negative** 21-day forward-return predictor on NIFTY-50 2016–2026 (t = −5 to −19 on both sub-windows). Any catalog strategy built on it should be expected to lose. | this report §5.5, §5.10 |
| F5 | A sibling `controls.py` style harness that hardcodes `lo, hi = TRAIN if stage == "train" else TRAIN` silently re-runs TRAIN for the TEST stage. I hit exactly this and caught it only by noticing the TEST random seeds produced byte-identical numbers to TRAIN. Worth grepping for in the other agent dirs. | `research/agent_regression/controls.py` |

---

*Agent: `regression_strategy`. Parameters used: 5/5 declared. TEST touched once, after
`selected_variant.json` was written. No `src/` or `tests/` file was modified.*

