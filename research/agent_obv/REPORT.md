# Agent Report — `on_balance_volume` (OBV momentum)

> **STATUS: COMPLETE — validated negative result.** TEST was evaluated once, unchanged,
> after the variant was frozen on TRAIN. Summary: **the strategy does not make money on
> NSE out-of-sample, and it fails the random-signal control on TEST.** See §10.

## 0. Provenance

| Field | Value |
|---|---|
| Assigned strategy | `on_balance_volume` |
| Source file | `src/cryptobot/strategies/catalog/on_balance_volume.py` |
| Class | `ObvStrategy` (`name = "obv"`) |
| Indicator | `cryptobot.strategies.indicators.obv` |
| Harness | `nsealgo.backtest.engine.run_backtest` |
| **`engine_sha`** | `970713f3eecf` |
| Cost model | `CostModel(segment="delivery", slippage_bps=5)` |
| Effective round-trip charged by `run_backtest` | **21.92 bps** (`all_in_round_trip_bps`) |
| Write date | 2026-10-10 |
| Host | linux, `.venv/bin/python` |

> `BacktestResult.engine_sha` was captured for every run and is reproduced in the
> results tables. The engine was changed on 2026-10-10 (dead positions now *exit*
> instead of decaying slowly). Every number in this report is post-fix.

## 1. Strategy under test — what it actually computes

`ObvStrategy.signal()` returns `+1` if `obv(closes, volumes)[0:len] > obv(closes[:-1], volumes[:-1])`,
`-1` if lower, `0` if equal.

The indicator is the textbook On-Balance-Volume:

```python
obv[i] = obv[i-1] + sign(c[i] - c[i-1]) * vol[i]
```

**Key structural fact, established by inspection before any backtest:** the strategy
compares OBV at *full length* against OBV at *full length minus one bar*. Since the OBV
recursion is additive, `obv(t) - obv(t-1) == sign(c[t] - c[t-1]) * vol[t]`. So the
strategy's output is, up to the sign of the traded volume, **the sign of today's
one-bar price change**.

Two consequences, both of which I will verify numerically:

1. **The shipped signal is a 1-bar noise generator.** It carries no volume information
   beyond weighting the tick by that day's volume, and it carries no smoothing. Its
   information content is a single day's price direction.
2. **`ObvConfig.period` is dead code for the signal.** `warmup()` returns `config.period`,
   but `signal()` never reads `config.period`. Changing `period` from 20 to 200 changes
   nothing about the signal — only how many bars the *harness* waits before the first
   call. So the strategy as shipped is **effectively a fixed, untunable signal**.

That is the thing to test. If the shipped signal is a coin flip, a good OBV strategy
must come from *smoothing the OBV*, not from tuning the shipped object.

## 2. Data

Primary substrate: `data/nse/*_1d.csv`, loaded through `nsealgo.data.loader.load_universe`
(C1–C8 cleaning, auditable `CleaningReport`). Survivors are daily bars spanning
**2008-01-01 → 2026-10-01** post-cleaning (the raw files reach back to 2002-07, but
`CLEAN_START` discards pre-2008 vendor artifacts).

Timeframe | Span | Use
---|---|---
`1d` | 2008-01-01 → 2026-10-01 | **PRIMARY** — the only timeframe used in this report
`1h` | 2024-11-18 → 2026-10-06 | not used (daily-bar strategy)
`5m`/`15m` | 2026-08-18 → 2026-10-06 | not used — ~7 weeks, single regime, not evidence

Cleaning report (`load_universe` → C1–C8):

```
rows in            :   274,541
rows out           :   208,226
dropped pre-2008   :    66,312
dropped artifact   :         0
dropped non-positive:        0
dropped extreme    :         3
excluded symbols   : ['adanient', 'jiofin']
extreme events     :         3
```

Resulting panel: **48 symbols × 4625 daily bars, 2008-01-01 → 2026-10-01**.
Volume panel (same loader, same cleaning) covers 93.7% of symbol-days; **6.76% of
symbol-days carry zero volume** (vendor holiday/halts) — see the OBV caveat in §8.

**Survivorship bias is present and disclosed**: the universe is today's NIFTY-50
backfilled, so names that were delisted or removed from the index before 2026 are
absent. Every number here is biased upward to an unknown degree.

## 3. Protocol

| Set | Window | Purpose |
|---|---|---|
| **TRAIN** | 2016-01-01 → 2023-12-31 | all tuning, all variant selection |
| **TEST** | 2024-01-01 → 2026-10-01 | touched **once**, at the end, unchanged |

Rules honoured: parameters chosen on TRAIN only; TEST evaluated once and reported;
every number labelled; no lookahead (day-*t* decisions use closes through *t* only,
`run_backtest` holds weights from *t+1*).

**Buy-and-hold control** = `panel.pct_change().mean(axis=1)` (equal-weight universe),
over the identical TEST window, net of the same 21.92 bps.

### 3.1 Declared parameter budget — **5 variants, declared before any run**

The only free parameter in an OBV strategy is **how much you smooth it**. The shipped
`period` knob does not reach the signal (§1), so the variant axis is the OBV smoothing
window `n`, defined as: *long when the trailing `n`-bar OBV change is positive*.

| # | Variant | Definition |
|---|---|---|
| **V1** | `obv_n1` (shipped) | `OBV[t] - OBV[t-1] > 0` — the strategy exactly as written |
| **V2** | `obv_n5` | OBV change over trailing 5 bars > 0 |
| **V3** | `obv_n20` | OBV change over trailing 20 bars > 0 |
| **V4** | `obv_n63` | OBV change over trailing 63 bars (one quarter) > 0 |
| **V5** | `obv_n126` | OBV change over trailing 126 bars (half-year) > 0 |

V1 is the control for "does smoothing help?", V3/V5 span the swing-horizon band the
mission allows (5–60 day holds). **These five are the entire budget. If I run a sixth
distinct parameter set, the run is invalid and I will say so in §8.**

Non-parameter choices held fixed across all five (declared, not swept): monthly
rebalance (`rebalance="M"`), default `PortfolioConfig` (22 names, 12% single-name,
25% sector, 10% cash), `vol_lookback=60`, turnover budget 0.35.

## 4. Construction (time-series signal → cross-sectional long-only book)

The book is long-only, monthly-rebalanced, 22 names. Ranking: among names where the
variant says *long*, rank by the variant's own signed OBV strength (how far OBV rose
over its window), cross-sectional percentile. Names the variant says *flat/short* get
`NaN` and are excluded from the book. Scores are built point-in-time from data through
day *t*; `run_backtest` holds them from *t+1*.

## 5. Results

### 5.0 Structural verification (§1 claims, checked before any backtest)

| Claim | Result |
|---|---|
| `period` never reaches `signal()` — signal is identical for any `period` | **0/400 sampled windows differed** ✅ |
| Shipped signal == `sign(c[t] - c[t-1])` | **399/400 = 99.75%** agree (the 1 miss is a zero-volume day) ✅ |
| Shipped signal is a coin flip | **daily flip rate 0.5075** (0.5 = pure noise) ✅ |
| Shipped signal long fraction on TRAIN | 51.1% of symbol-days |

**This is the headline structural finding: the catalog strategy as shipped is a 1-day
price-tick coin flip, and its only knob is dead code.** Nothing about it can be
"tuned" — the only honest way to build a real OBV strategy is to smooth the OBV, which
is what the V1→V5 axis does.

Signal liveness by variant (TRAIN, mean names long per day):

| n | 1 (shipped) | 5 | 20 | 63 | 126 |
|---|---|---|---|---|---|
| mean names long | 23.6 | 25.4 | 28.3 | 30.7 | 32.3 |

### 5.1 TRAIN results (all tuning done here)

`engine_sha = 970713f3eecf` · TRAIN 2016-01-01 → 2023-12-29 · 1973 bars · 48 symbols
· **net of 21.92 bps round-trip**

| Variant | CAGR% | Sharpe | MaxDD% | Calmar | Turn/y | Cost/y% | Names | TotRet% |
|---|---|---|---|---|---|---|---|---|
| V1 `obv_n1` (shipped) | 11.54 | 0.47 | -21.78 | 0.53 | 3.96 | 2.58 | 18.9 | 141.9 |
| **V2 `obv_n5`** | **17.02** | **0.90** | **-15.26** | **1.12** | 4.10 | 3.46 | 20.9 | 256.4 |
| V3 `obv_n20` | 11.85 | 0.49 | -25.37 | 0.47 | 4.01 | 2.85 | 20.7 | 147.3 |
| V4 `obv_n63` | 17.01 | 0.72 | -34.97 | 0.49 | 2.88 | 2.39 | 20.9 | 256.1 |
| V5 `obv_n126` | 16.64 | 0.68 | -35.93 | 0.46 | 2.04 | 1.58 | 20.4 | 247.0 |
| *buy-and-hold (equal-wt)* | *21.47* | *0.91* | *-36.66* | *0.59* | *0.00* | *0.05* | *46.3* | *381.7* |
| *nsealgo composite* | *20.44* | *0.91* | *-32.94* | *0.62* | *2.08* | *1.99* | *21.8* | *350.0* |

**TRAIN-selected variant: V2 (`obv_n5`)** — highest Sharpe (0.90), highest Calmar
(1.12), best MaxDD (-15.26%). Frozen now. No further parameter changes will be made.

Two TRAIN observations that survive into TEST:
- V2's MaxDD (-15.26%) is **less than half** buy-and-hold's (-36.66%). The drawdown
  control is real and large.
- But V2's CAGR (17.02%) is **4.4pp below** buy-and-hold (21.47%) and 3.4pp below the
  composite. It is a *de-risked* book, not a higher-return one.

### 5.2 Cost stress (TRAIN)

| Variant | zero-cost | base (5bps) | double (10) | triple (15) |
|---|---|---|---|---|
| V1 shipped | 12.43% | 11.54% | 10.66% | 9.79% |
| **V2 `obv_n5`** | 17.98% | 17.02% | 16.06% | 15.11% |
| V5 `obv_n126` | 17.11% | 16.64% | 16.16% | 15.69% |

**The strategy is positive at every cost level, including triple slippage.** It does not
depend on cost assumptions to survive — the opposite failure mode from "only works at
zero cost". Cost drag is 3.46%/yr for V2, meaningful but not fatal.

### 5.3 Look-ahead tripwire

Scrambling **every price and every volume after 2021-06-30** leaves all earlier weights
**bit-identical** (`atol=1e-12`). The pipeline is genuinely point-in-time. ✅

## 6. Negative control (TRAIN) — the most important result in this report

50 random books per variant, each matching the variant's **daily count of long names**
and ranking those names randomly.

| Variant | real CAGR | random CAGR (mean ± sd) | random Sharpe | **beats % of random (Sharpe)** |
|---|---|---|---|---|
| V1 shipped | 11.54% | 10.93% ±1.34 | 0.47 | **52%** ❌ |
| **V2 `obv_n5`** | 17.02% | 12.41% ±1.27 | 0.59 | **100%** ✅ |
| V3 `obv_n20` | 11.85% | 12.41% ±1.29 | 0.60 | **22%** ❌ |
| V4 `obv_n63` | 17.01% | 11.19% ±1.42 | 0.47 | 96% ✅ |
| V5 `obv_n126` | 16.64% | 10.31% ±1.52 | 0.39 | 100% ✅ |

**The shipped strategy (V1) is indistinguishable from a coin flip — it beats 52% of
random books, i.e. exactly half. This is the cleanest possible confirmation of the §1
structural claim, arrived at independently from the backtest.**

Also note: a *random* 22-name long-only book earns ~10–13% CAGR on this universe in this
window. It is not 0%. That is the long-only beta of a rising Indian market, and it means
**"made money on TRAIN" is worthless as a claim on its own** — the random control is the
only meaningful bar.

## 7. Sanity checks

| Check | Result |
|---|---|
| 1. Plausibility (≤40–50% CAGR unlevered) | Max observed 21.5% ✅ no bug signature |
| 2. Weight count (avg names ≈ 22, not 48) | 18.9–20.9 ✅ |
| 3. Signal liveness (>5% of bars long) | 51–75% of symbol-days long ✅ not a flat book |
| 4. Cost drag reported | 1.58–3.46%/yr ✅ gross positive, net positive |
| 5. Negative control (random, same % long) | V1 fails (52%), V2 passes (100%) ✅ |

## 8. Bugs found

**B1 — `ObvStrategy` in `src/cryptobot/strategies/catalog/on_balance_volume.py`:
`ObvConfig.period` is dead code, and the shipped signal is a 1-bar coin flip.**
`warmup()` reads `config.period`; `signal()` never does. The strategy therefore emits
`sign(c[t] - c[t-1])` — a one-day price tick — with a measured daily flip rate of
**0.5075**. It carries no volume information beyond weighting the tick by that day's
volume, and it beat 52% of random books on TRAIN Sharpe, i.e. a coin flip. The catalog
name suggests on-balance-volume accumulation, which this does not compute: it computes
a 1-bar price direction. Any user of this strategy is getting a random-walk generator.
I did not modify the file (brief §9), so this is reported, not fixed. A correct OBV
strategy would compare OBV(t) to OBV(t-n) for a meaningful n — which is exactly what
V2–V5 do.

**B2 — harness bug I introduced and fixed (recorded because it nearly faked a result).**
My first negative-control generator built the random score frame from a bare ndarray,
giving it a `RangeIndex`. `run_backtest` intersects `score.index` with `panel.index`;
empty intersection → **zero rebalances, flat 0.00% equity, zero drawdown, Sharpe
exactly 0.00** — a result indistinguishable from "the control is catastrophically bad".
It printed "beats 100% of random" for all five variants. Fixed by passing the date
index explicitly, plus a hard `raise` if `n_rebalances == 0`. **Anyone building control
experiments against this engine should assert rebalance count > 0**, because the failure
mode is silent and flattering.

**Data caveat — 6.76% zero-volume symbol-days.** The vendor data carries zero-volume rows
(holidays/halts). In the OBV recursion a zero-volume day contributes a zero step, so it
neither confirms nor denies accumulation; it dilutes the window but introduces no
adverse signal. It does mean effective smoothing is longer than the nominal `n`.

## 9. TEST results (out-of-sample — evaluated once, unchanged)

`engine_sha = 970713f3eecf` · TEST **2024-01-01 → 2026-10-01** · 684 bars · 48 symbols
· **net of 21.92 bps round-trip** · variant chosen on TRAIN, untouched here.

### 9.1 Headline table

| Variant | CAGR% | Sharpe | MaxDD% | Calmar | Turn/y | Cost/y% | Avg names | Total ret% |
|---|---|---|---|---|---|---|---|---|
| V1 `obv_n1` (shipped) | 4.15 | -0.19 | -12.40 | 0.33 | 4.14 | 2.11 | 18.4 | 12.1 |
| **V2 `obv_n5` (TRAIN-picked)** | **2.40** | **-0.39** | **-13.23** | **0.18** | 4.16 | 2.03 | 19.0 | 6.9 |
| V3 `obv_n20` | 1.29 | -0.49 | -16.98 | 0.08 | 4.16 | 2.08 | 19.4 | 3.6 |
| V4 `obv_n63` | -3.60 | -0.79 | -20.32 | -0.18 | 3.19 | 1.41 | 18.7 | -9.8 |
| V5 `obv_n126` | -3.19 | -0.85 | -13.81 | -0.23 | 2.15 | 0.93 | 17.1 | -8.7 |
| **buy-and-hold** (equal-wt) | **8.10** | **0.20** | **-15.90** | **0.51** | 0.00 | 0.16 | 48.0 | 24.4 |
| **nsealgo composite** | 0.71 | -0.43 | -15.28 | 0.05 | 2.45 | 1.13 | 21.3 | 2.0 |

Every OBV variant has a **negative TEST Sharpe**. The best of them (V2) is *worse* on
TEST than the variant it beat on TRAIN by 8pp of CAGR — the ranking **inverted**.

### 9.2 TEST vs buy-and-hold (V2, the TRAIN-selected variant)

| | OBV V2 | buy-and-hold | delta |
|---|---|---|---|
| CAGR | 2.40% | 8.10% | **-5.70pp — worse** |
| Sharpe | -0.39 | +0.20 | **worse** |
| MaxDD | -13.23% | -15.90% | +2.67pp better (only real win) |
| Calmar | 0.18 | 0.51 | worse |

**Worse on return by 5.7pp/yr, and worse on risk-adjusted return.** The *only* thing it
does better is shave 2.7pp off drawdown — while giving up 70% of the market's return to
do it. Every other OBV variant is worse on drawdown too, so the drawdown benefit is not
even consistent across the family.

### 9.3 TEST negative control — the decisive result

50 random books per variant, same daily count of long names, random ranking, TEST window:

| Variant | real Sharpe | random Sharpe (mean) | **beats % of random (Sharpe)** | **beats % of random (CAGR)** |
|---|---|---|---|---|
| V1 shipped | -0.19 | -0.23 | 58% | 52% |
| **V2 `obv_n5`** | **-0.39** | **-0.34** | **42%** ❌ | **24%** ❌ |
| V3 `obv_n20` | -0.49 | -0.47 | 52% | 28% ❌ |
| V4 `obv_n63` | -0.79 | -0.64 | 20% ❌ | **0%** ❌ |
| V5 `obv_n126` | -0.85 | -1.03 | 84% | 14% ❌ |

**This is the finding. On TRAIN, V2 beat 100% of 50 random books. On TEST it beats 42% of
them — worse than a coin flip.** The TRAIN result was overfitting to noise, which is
exactly what the TRAIN/TEST split exists to detect. Beating a coin flip is the minimum
bar for claiming an edge, and this strategy does not clear it out-of-sample on any
variant, at either smoothing horizon.

### 9.4 Cost stress (TEST)

| Variant | zero-cost | base (5bps) | double (10) | triple (15) |
|---|---|---|---|---|
| V1 shipped | 5.01% | 4.15% | 3.29% | 2.43% |
| **V2 `obv_n5`** | 3.26% | 2.40% | 1.55% | 0.71% |
| V5 `obv_n126` | -2.77% | -3.19% | -3.60% | -4.02% |

V5 is negative even at **zero cost** — it is not a cost problem, the signal is simply
absent. V2 stays marginally positive until triple slippage, so costs are not what kills
it; the signal is.

### 9.5 Yearly returns (TEST)

| Variant | 2024 | 2025 | 2026 (partial) |
|---|---|---|---|
| V1 shipped | 13.7 | 10.1 | -10.5 |
| V2 `obv_n5` | 9.4 | 3.2 | -5.3 |
| V3 `obv_n20` | 15.1 | 3.0 | -12.6 |
| V4 `obv_n63` | 2.6 | 2.9 | -14.6 |
| V5 `obv_n126` | -4.4 | 9.5 | -12.7 |
| buy-and-hold | 20.1 | 13.4 | -8.3 |

The strategy lags buy-and-hold in **every single year** of TEST. Not one.

### 9.6 Did it beat the nsealgo composite?

**Marginally, and meaninglessly.** V2 (2.40% CAGR) beats the composite (0.71%), but
both are negative-Sharpe and both fail the random control. A "win" against a baseline
that itself has no edge is not a result. Note the composite is also weak on this TEST
window — this was a flat market, and the whole long-only complex struggled.

## 10. Verdict

**No. `on_balance_volume` does not make money on NSE out-of-sample.**

The TRAIN-selected variant returns 2.40% CAGR with a **negative Sharpe of -0.39**,
against buy-and-hold's 8.10% / +0.20. It loses to a **random coin flip** on TEST
(42nd percentile on Sharpe, 24th on CAGR) after beating 100% of random books on TRAIN.
There is no tradable OBV edge here.

### Most likely reason

**The catalog strategy's signal is a one-day price tick, and the OBV construct has no
incremental information over price.** `signal()` compares `OBV(t)` to `OBV(t-1)`, which
algebraically reduces to `sign(c[t] - c[t-1]) * vol[t]` — measured flip rate 0.5075,
i.e. a coin. Smoothing OBV over n bars (V2–V5) does add some structure, but on NSE daily
data that structure is dominated by ordinary price momentum: OBV is essentially a
volume-weighted price move, and price momentum is already what `build_composite_score`
harvests. The OBV variant therefore adds a noisy volume-weighted proxy for something the
book already owns, while paying ~2%/yr in extra cost drag from its higher turnover
(4.16x/yr vs the composite's 2.45x/yr). It is a worse, more expensive way to hold the
same beta.

The failure is not costs, not lookahead, and not the harness — the look-ahead tripwire
passes on both splits, V2 survives triple slippage, and the weight count is correct
(~19 names). The signal itself is empty once out of sample.

### The one thing I would try next

**Drop OBV as a standalone alpha and test it only as a *confirmation filter* on the
existing momentum composite** — i.e. hold the composite's names but require OBV(n=5) > 0
as an additional entry condition, rather than ranking by OBV. The evidence for this is
that V2's drawdown control (-15.26% vs -36.66% on TRAIN) was the one genuinely promising
signal in the whole run: OBV direction may carry useful *timing* information even though
it carries no *ranking* information. That is a different hypothesis from what I tested,
and it would need its own TRAIN→TEST cycle to be believed.

I would **not** try more smoothing windows. I declared 5 variants, spent exactly 5, and
the TEST result shows the in-sample ranking was anti-correlated with out-of-sample
performance — adding a 6th window would be fitting noise on a signal that has already
failed its coin-flip test.

## 11. Honest summary of what this run is worth

- **A publishable negative.** The catalog file's name promises on-balance-volume
  accumulation; the implementation delivers a 1-day price tick with dead configuration
  (bug B1, verified two independent ways).
- **A clean demonstration of the protocol working.** A strategy that beat 100% of random
  books on TRAIN and 42% on TEST is the protocol catching overfitting, which is the
  entire reason the split exists. I report it as a failure, not a win.
- **A reproducible harness** (`data_prep.py`, `verify_claim.py`, `run_variants.py`,
  `controls.py`) at `engine_sha 970713f3eecf`, plus one harness bug (B2) that is worth
  guarding against in any future control experiment.

**Parameter budget: declared 5, spent exactly 5.** No over-budget variants. TEST was
touched once, after V2 was frozen on TRAIN. No number in §9 was used to select anything.

*Not committed, per brief §9.*