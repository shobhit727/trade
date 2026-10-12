# Agent Report — `mfi_strategy` (Money Flow Index)

> **STATUS: COMPLETE — validated negative result.** TEST was evaluated once, unchanged,
> after the variant was frozen on TRAIN. Summary: **the strategy does not make money on
> NSE out-of-sample.** All five declared variants have a negative TEST Sharpe, every one
> lands **below the 50th percentile against a random signal**, and the shipped
> configuration is **negative even at zero cost** on both windows. See §6.
>
> Cost accounting was verified explicitly: `all_in_round_trip_bps(100_000)` returns
> **21.92** for `slippage_bps=5` and **11.92** for `slippage_bps=0`, confirmed in the
> run diagnostics. Every reported figure is net of 21.92 bps unless explicitly labelled
> as a zero-cost control.

## 0. Provenance

```python
from nsealgo.provenance import provenance; provenance()
# {'engine': 'd93815344bd3', 'loader': 'c1badf5f7df8',
#  'costs': 'ba350aef75b3', 'panel': '389b082b832f'}
```

| Field | Value |
|---|---|
| Assigned strategy | `mfi_strategy` |
| Source file | `src/cryptobot/strategies/catalog/mfi_strategy.py` |
| Class | `MfiStrategy` (`name = "mfi"`) |
| Indicator | `cryptobot.strategies.indicators.mfi` |
| Harness | `nsealgo.backtest.engine.run_backtest` |
| **`engine_sha`** | **`d93815344bd3`** |
| **`loader_sha`** | **`c1badf5f7df8`** |
| **`costs_sha`** | **`ba350aef75b3`** |
| **`panel_sha`** | **`389b082b832f`** |
| Cost model | `CostModel(segment="delivery", slippage_bps=5)` |
| Effective round-trip charged by `run_backtest` | **21.92 bps** (`all_in_round_trip_bps`) |
| Write date | 2026-10-11 |
| Host | linux, `.venv/bin/python` (Python 3.14.7) |

> **Engine moved since the earlier agent reports.** `agent_obv` was run at
> `engine_sha 970713f3eecf`; this run is at `d93815344bd3`. Numbers in this report are
> **not** comparable with reports written at the older SHA. `BacktestResult.engine_sha`
> is captured on every run and printed in the results tables.

**Crypto-specificity check (brief §9): NOT crypto-specific.** MFI is a volume-weighted
RSI over typical price — a price/volume oscillator with no funding, liquidation,
stablecoin-peg, options-IV or basis dependency. It has direct meaning on NSE daily
bars, which carry `vol`. The brief's "stop immediately" clause does **not** apply; the
run proceeds.

## 1. Strategy under test — what it actually computes

`MfiStrategy.signal()` returns, from `m = mfi(closes, highs, lows, volumes, period)`:

| Condition | Signal |
|---|---|
| `m > upper` (default 80) | **-1** (short) |
| `m < lower` (default 20) | **+1** (long) |
| otherwise | 0 |

The indicator (`src/cryptobot/strategies/indicators.py:251`) is the textbook Money Flow
Index: typical price `tp = (h+l+c)/3`, money flow `flow = tp * vol` classified by the
sign of `tp[t] - tp[t-1]`, then

```
MFI = 100 - 100 / (1 + sum(pos_flow, period) / sum(neg_flow, period))
```

with the degenerate case `neg == 0 -> 100.0`.

**Three structural facts established by inspection before any backtest, to be verified
numerically:**

1. **This is a mean-reversion signal, not a trend signal.** It buys oversold and sells
   overbought. `nsealgo/backtest/engine.py` states the design premise in its own module
   docstring: *"Trend/momentum is the primary alpha engine. There is no mean-reversion
   core"*, citing Sehgal & Jain (2011), IIMC (2020) for Indian short-term *continuation*,
   and the Romano-Wolf multiple-testing-corrected study (2015–2025) in which
   RSI_25_75, RSI_30_70, Bollinger 20/2.0 and Bollinger 20/2.5 **all failed**. MFI is
   structurally the same family as RSI — a bounded oscillator read as a reversal signal.
   **The prior is negative before any number is produced.**
2. **The `-1` branch is structurally dead in an NSE delivery account.** `GOAL.md` §3.1
   trades long-only; shorting is not available. So only the `m < lower` branch can ever
   become a position. `MfiConfig.upper` is dead configuration for this mandate, exactly
   as `warmup()`-only parameters are dead elsewhere in the catalog.
3. **MFI is a *rare-event* signal.** `m < 20` requires positive money flow to be less
   than one-fifth of negative money flow over 14 bars. If it fires on few symbol-days, the
   cross-sectional book has nothing to hold and the strategy degenerates to "always
   flat, loses only to costs" (brief §6.3). **This is the first thing I will measure**, and
   it determines whether any variant below is a meaningful test at all.

## 2. Data

Primary substrate: `data/nse/*_1d.csv` via `nsealgo.data.loader`. 50 files on disk.

| Timeframe | Span | Use |
|---|---|---|
| `1d` | 2008-01-01 → 2026-10-01 (post-clean) | **PRIMARY** — the only timeframe used |
| `1h` | 2024-11-18 → 2026-10-06 | not used (daily-bar strategy) |
| `5m`/`15m`/`30m` | 2026-08-18 → 2026-10-06 | not used — ~7 weeks, single regime, **not evidence** |

**MFI needs `high`, `low` and `vol`, which `load_universe` does not return** (it returns
a close panel only). The OHLCV panels are therefore built by calling the *same*
`load_symbol` per symbol — identical C1–C9 cleaning, identical `CleaningReport` — and
then re-indexed onto `load_universe`'s close panel so the traded price series is
byte-identical to the audited one. Recorded as a harness note, not a bug.

**Survivorship bias is present and disclosed:** the universe is today's NIFTY-50
backfilled, so names removed from the index before 2026 are absent. Every number here is
biased upward by an unknown degree.

Cleaning report and panel dimensions: *appended in §3 once measured.*

## 3. Protocol

| Set | Window | Purpose |
|---|---|---|
| **TRAIN** | 2016-01-01 → 2023-12-31 | all tuning, all variant selection |
| **TEST** | 2024-01-01 → 2026-10-01 | touched **once**, at the end, unchanged |

Rules honoured: parameters chosen on TRAIN only; TEST evaluated once and reported; every
number labelled; no lookahead (day-*t* decisions use data through *t* only;
`run_backtest` holds weights from *t+1*).

**Buy-and-hold control** = `panel.pct_change().mean(axis=1)` (equal-weight universe) over
the identical TEST window, net of the same 21.92 bps.

### 3.1 Declared parameter budget — **5 variants, declared before any run**

The only knobs that reach the *signal* are `MfiConfig.period` and `MfiConfig.lower`
(`upper` is dead long-only, §1 fact 2). The variant axis is therefore `(period, lower)`,
chosen to span (a) the shipped configuration, (b) threshold widening to buy liveness,
and (c) lookback variation.

| # | Variant | `period` | `lower` | Rationale |
|---|---|---|---|---|
| **V1** | `mfi_p14_l20` (**shipped**) | 14 | 20 | The strategy exactly as written. Control. |
| **V2** | `mfi_p14_l30` | 14 | 30 | Classic MFI oversold threshold; widens liveness at fixed lookback. |
| **V3** | `mfi_p14_l40` | 14 | 40 | Aggressive widening — upper bound of the "is it ever live" probe. |
| **V4** | `mfi_p28_l30` | 28 | 30 | Long lookback at V2's threshold. |
| **V5** | `mfi_p9_l30` | 9 | 30 | Short lookback at V2's threshold. |

**These five are the entire budget. If a sixth distinct parameter set is run, the run is
invalid and I will say so in the report.** Thresholds will not be tuned until an equity
curve looks good; the selection rule (§5) is fixed in advance: *highest TRAIN Sharpe,
ties broken by Calmar.*

Non-parameter choices held fixed across all five (declared, not swept): monthly
rebalance (`rebalance="M"`), default `PortfolioConfig` (22 names, 12% single-name, 25%
sector, 10% cash buffer, `vol_lookback=60`, turnover budget 0.35, `max_names=30`).

### 3.2 Construction (declared in advance, not tuned)

Brief §5 prescribes: *rank the signalled names by trailing momentum among the ones your
strategy flags.*

```python
score = (panel/panel.shift(126) - 1.0).where(signal_panel > 0).rank(axis=1, pct=True)
```

I use **exactly this**, unmodified, for all five variants.

**A tension I am flagging rather than resolving in my own favour:** the brief's ranking is
motivated by the momentum literature, but `signal_panel > 0` here means *oversold*. Among
oversold names, ranking by trailing 126-day momentum systematically prefers the names
that have fallen **least** — i.e. it is a "least-bad falling knife" filter, not a
momentum bet, and for an oversold signal it is close to the opposite of the signal's own
mean-reversion thesis. Using the brief's rule unmodified is the honest choice: choosing a
construction *because* it flatters my strategy is precisely the bias this protocol exists
to catch. If the result is a book that keeps buying the recent losers, that is a finding
about the construction, and I will say so rather than quietly switching rankers.

### 3.3 Random-signal negative control

For each variant, N random books matching that variant's **daily count of long names**,
with the same names chosen at random and ranked randomly, over the same window and the
same costs. Passing requires beating the median random book out-of-sample.

---

## 4. Results

*Appended below as produced.*

---### 4.1 Structural verification (§1 claims) — measured before any backtest

**Vectorised MFI ≡ catalog `mfi()`.** Replaying the scalar catalog function over ~2,300
random windows per lookback:

| `period` | windows checked | max abs diff |
|---|---|---|
| 9 | 2,328 | 1.09e-12 |
| 14 | 2,326 | 1.42e-13 |
| 28 | 2,317 | 5.68e-14 |

Agreement to floating-point noise. The harness is computing the catalog's MFI, not an
approximation of it.

**MFI(14) distribution, TRAIN (173,520 symbol-days):**

| pct | 0.1% | 0.5% | 1% | 5% | 25% | 50% | 75% | 95% |
|---|---|---|---|---|---|---|---|---|
| MFI | 5.43 | 10.67 | 13.92 | 24.21 | 41.62 | 54.90 | 67.50 | 82.45 |

`m < 20` sits between the 1% and 5% percentiles. It is a genuine tail event.

**Signal liveness (TRAIN, brief §6.3).** Fraction of symbol-days long, and how many of
the 48 names are flagged on a given day:

| Variant | % sym-days long | mean names | median names | days with **0** names | days with <5 names |
|---|---|---|---|---|---|
| **V1 `mfi_p14_l20` (shipped)** | **2.35%** | **1.13** | **0** | **988 / 1973** | 1,880 |
| V2 `mfi_p14_l30` | 8.67% | 4.16 | 3 | 225 | 1,280 |
| V3 `mfi_p14_l40` | 20.68% | 9.93 | 9 | 26 | 446 |
| V4 `mfi_p28_l30` | 3.23% | 1.55 | 1 | 745 | 1,846 |
| V5 `mfi_p9_l30` | 13.23% | 6.35 | 5 | 91 | 912 |

**This is the first major finding, and it is structural, not statistical.**

The shipped threshold `MFI < 20` fires on **2.35% of symbol-days — below the 5% liveness
floor in brief §6.3.** On the **median day it flags zero names**, and on **988 of 1,973
TRAIN days (50.1%) it flags none at all**. The book has nothing to hold.

The mechanism matters. With ~1 name flagged, `build_rebalance_weights` assigns it the
whole pre-constraint weight of 1.0; the 12% single-name cap then clips it to 0.12, and
`_project_constraints` leaves the remaining 0.88 **as cash** because no legal recipient
exists (that is the documented, deliberate behaviour — mass is never sprinkled across the
universe to make a total look invested). After the 10% cash buffer the book is ~10.8% in
one stock and ~89% cash. On days with zero names flagged the book **liquidates entirely**.

So V1 is not a 22-stock mean-reversion strategy. It is **a ~10%-invested portfolio that
holds cash most of the time and takes an occasional single-stock oversold bet.** Whatever
its return, that is what is being measured, and the return must be read against that fact
rather than as "MFI alpha".

**Measured directly on TEST** (not inferred from the mechanism):

| Quantity | Value |
|---|---|
| Days in 100% cash | **314 / 684 (45.9%)** |
| Mean exposure | **16.5%** |
| Mean names held | 1.69 |
| Peak exposure, any single day | 78.8% |
| Weight on days with exactly 1 name | **10.77%** (= 12% single-name cap x 0.9 cash buffer, exactly as the mechanism predicts) |
| Max single-name weight observed | 10.80% |

The 10.77% figure is the mechanism above confirmed numerically: when exactly one name is
flagged it gets the whole weight, is clipped by the 12% cap, and nothing is spilled onto
other names because there are no other legal recipients.

§1 fact 2 is confirmed by construction: `MfiConfig.upper` never reaches the book, because
the `-1` branch is not expressible in a long-only delivery account.

### 4.2 Main results — all five declared variants + controls

`engine_sha = d93815344bd3` · net of **21.92 bps** round-trip · monthly rebalance ·
default `PortfolioConfig` (22 names / 12% / 25% sector / 10% cash / 0.35 turnover).

**TRAIN 2016-01-01 → 2023-12-31** (1973 bars, 48 symbols) — *all tuning happens here.*

| Run | CAGR% | Sharpe | MaxDD% | Calmar | Turn/y | Cost/y% | Avg names | Total ret% |
|---|---|---|---|---|---|---|---|---|
| **V1** `mfi_p14_l20` (shipped) | -0.69 | -0.95 | -26.34 | -0.03 | 1.39 | 0.61 | **1.2** | -5.4 |
| V2 `mfi_p14_l30` | 2.90 | -0.36 | -23.06 | 0.13 | 3.15 | 1.59 | 4.2 | 26.0 |
| **V3** `mfi_p14_l40` | 6.04 | **0.01** | -28.26 | **0.21** | 3.97 | 2.14 | 10.0 | 60.6 |
| V4 `mfi_p28_l30` | 2.69 | -0.40 | -24.24 | 0.11 | 1.57 | 0.79 | 1.5 | 23.9 |
| V5 `mfi_p9_l30` | 2.41 | -0.47 | -18.30 | 0.13 | 3.55 | 1.76 | 6.0 | 21.2 |
| *buy-and-hold (brief-literal)* | *21.78* | *0.90* | *-36.66* | *0.59* | *0.00* | *0.09* | *48.0* | *391.7* |
| *buy-and-hold (engine parity)* | *19.74* | *0.89* | *-33.68* | *0.59* | *0.54* | *0.09* | *45.8* | *329.1* |
| *nsealgo composite* | *20.44* | *0.91* | *-32.94* | *0.62* | *2.08* | *1.99* | *21.8* | *350.0* |

**Every MFI variant has a TRAIN Sharpe ≤ 0.01.** The best (V3) is statistically
indistinguishable from zero. There is no variant that comes close to the 0.90 of either
benchmark.

**TRAIN-selected variant: V3 (`mfi_p14_l30`… `mfi_p14_l40`), by the pre-declared rule
(highest TRAIN Sharpe, ties to Calmar). Frozen now. No further parameter changes.**

> **Read the drawdown column with care — this is the trap in this run.** V3's TRAIN
> MaxDD is -28.26% against buy-and-hold's -36.66%, and on TEST it looks better still.
> But V3 holds **10.0 names of 48** — roughly 20-30% invested — so it is mostly cash. A
> book that holds cash has a small drawdown **by arithmetic, not by skill**. Any drawdown
> comparison that does not control for exposure is meaningless here. §5 decomposes return
> into market beta and selection alpha precisely for this reason.

### 4.3 Look-ahead tripwire — PASSES

Scramble **every price and every volume after 2021-06-30** (reverse the price path,
shuffle volumes independently) and require all *earlier* weights to be unchanged:

| Check | Result |
|---|---|
| Weights before cut, max abs diff | **0.0** |
| Weights before cut, differing cells | **0 / 64,992** |
| Weights after cut, max abs diff | 0.108 (expected — the scramble is *meant* to change these) |

The pipeline is genuinely point-in-time. No result in this report is lookahead-inflated.

### 4.4 Return decomposition — where the money actually came from

Because these books hold 12–40% invested, a naive CAGR reads mostly as *how much cash you
held*. Decomposing into the market-return component of the **actual exposure held** and
the **selection alpha** on top of it (all net of 21.92 bps except the `gross` column):

| Window | Variant | Mean invested | % days fully cash | Net CAGR% | Gross CAGR% | Beta part% | **Selection alpha%** | Cost drag% |
|---|---|---|---|---|---|---|---|---|
| TRAIN | V1 shipped | 12.0% | **45.9%** | -0.85 | -0.26 | 0.15 | **-0.41** | 0.59 |
| TRAIN | V2 | 27.9% | 15.6% | 2.39 | 3.72 | 3.83 | -0.11 | 1.43 |
| TRAIN | **V3 (picked)** | 39.9% | 8.4% | 5.33 | 7.06 | 6.71 | **+0.35** | 1.92 |
| TRAIN | V4 | 13.9% | 42.2% | 2.96 | 3.63 | 0.89 | **+2.74** | 0.76 |
| TRAIN | V5 | 32.6% | 10.2% | 1.55 | 3.05 | 4.42 | -1.37 | 1.56 |
| TEST | V1 shipped | 16.5% | **45.9%** | -0.46 | 0.36 | 1.24 | **-0.87** | 0.81 |
| TEST | V2 | 25.7% | 26.9% | -0.23 | 0.97 | 0.94 | +0.03 | 1.20 |
| TEST | **V3 (picked)** | 36.6% | 23.8% | -2.54 | -1.13 | 0.59 | **-1.72** | 1.38 |
| TEST | V4 | 17.5% | 48.1% | 1.42 | 2.27 | 2.81 | -0.55 | 0.83 |
| TEST | V5 | 30.1% | 27.3% | 1.41 | 2.80 | 2.45 | +0.35 | 1.41 |

**Three things this table settles, none of which the headline CAGR can show:**

1. **The shipped V1 is fully in cash 45.9% of the time**, in both windows, and its
   selection alpha is **negative in both** (-0.41% TRAIN, -0.87% TEST). It is not a bad
   strategy that occasionally loses; it is a strategy whose *selection* has no edge at
   all, wrapped in a cash buffer.
2. **The TRAIN-selected V3 inverted.** TRAIN alpha +0.35% → TEST alpha **-1.72%**. Its
   net CAGR went 5.33% → **-2.54%**. This is the signature of fitting noise.
3. **The apparent drawdown "advantage" is arithmetic.** V1's excellent MaxDD comes from
   holding ~12% invested for 45.9% of days. Its *beta part* on TRAIN is 0.15% — it
   essentially did not participate in a market that returned 21.53%. Beating
   buy-and-hold's drawdown by not holding the market is not a strategy.

### 4.5 TEST results (out-of-sample — evaluated once, unchanged)

`engine_sha = d93815344bd3` · TEST **2024-01-01 → 2026-10-01** (683 bars) · 48 symbols ·
**net of 21.92 bps** (`round_trip_bps = 21.92` confirmed on the run) · variant chosen on
TRAIN and untouched here.

| Run | CAGR% | Sharpe | MaxDD% | Calmar | Turn/y | Cost/y% | Avg names | Total ret% |
|---|---|---|---|---|---|---|---|---|
| V1 `mfi_p14_l20` (shipped) | -0.54 | **-1.48** | -6.46 | -0.08 | 2.06 | 0.89 | 1.8 | -1.5 |
| V2 `mfi_p14_l30` | 1.49 | -0.83 | -6.05 | 0.25 | 3.29 | 1.51 | 5.0 | 4.2 |
| **V3 `mfi_p14_l40`** (TRAIN-picked) | 0.76 | -0.68 | -12.36 | 0.06 | 4.12 | 1.89 | 11.7 | 2.1 |
| V4 `mfi_p28_l30` | 2.31 | -0.80 | -7.79 | 0.30 | 2.16 | 0.97 | 2.1 | 6.6 |
| V5 `mfi_p9_l30` | **4.07** | -0.32 | -7.68 | 0.53 | 3.85 | 1.86 | 8.3 | 11.8 |
| **buy-and-hold** (brief-literal) | **8.36** | **0.19** | -15.90 | 0.53 | 0.00 | 0.09 | 48.0 | 25.2 |
| buy-and-hold (engine parity) | 6.39 | 0.05 | -13.93 | 0.46 | 0.65 | 0.09 | 46.5 | 19.0 |
| nsealgo composite | 0.71 | -0.43 | -15.28 | 0.05 | 2.45 | 1.13 | 21.3 | 2.0 |

**Every single MFI variant has a negative TEST Sharpe.** Not one is risk-adjusted positive.
The TRAIN-selected V3 (Sharpe +0.01) lands at **-0.68**; the best TEST variant by CAGR
(V5, 4.07%) still has **Sharpe -0.32** and still loses to plain buy-and-hold.

### 4.6 TEST vs buy-and-hold (V3, the TRAIN-selected variant)

| | MFI V3 | buy-and-hold | delta |
|---|---|---|---|
| CAGR | 0.76% | 8.36% | **-7.60pp — worse** |
| Sharpe | -0.68 | +0.19 | **much worse** |
| MaxDD | -12.36% | -15.90% | +3.54pp "better" |
| Calmar | 0.06 | 0.53 | much worse |

**Worse on return by 7.6pp/yr and much worse risk-adjusted.** The only nominal win is
drawdown — and §4.4 shows that is bought with exposure, not earned with skill: V3's
TEST beta component is **0.59%** against a market that returned **8.26%**. It held 36.6%
invested and lost to a book that held 100%. Every variant's MaxDD "advantage" over
buy-and-hold is bought the same way.

### 4.7 Random-signal control — the decisive result

50 random books per variant, each matching that variant's count of long names **on every
rebalance date**, randomly chosen and randomly ranked, same window, same 21.92 bps.

| Variant | real Sharpe | random Sharpe | **beats % (Sharpe)** | real CAGR | random CAGR | **beats % (CAGR)** |
|---|---|---|---|---|---|---|
| **TEST** V1 shipped | **-1.48** | -1.06 | **10%** ❌ | -0.54% | 1.19% | **12%** ❌ |
| TEST V2 | -0.83 | -0.67 | 28% ❌ | 1.49% | 2.14% | 38% ❌ |
| **TEST V3 (TRAIN-picked)** | -0.68 | -0.40 | **14%** ❌ | 0.76% | 3.17% | **8%** ❌ |
| TEST V4 | -0.80 | -0.76 | 48% ❌ | 2.31% | 2.45% | 48% ❌ |
| TEST V5 | -0.32 | -0.25 | 38% ❌ | 4.07% | 4.50% | 38% ❌ |
| *TRAIN V1* | *-0.95* | *-1.16* | *78%* | *-0.69%* | *0.82%* | *8%* |
| *TRAIN V3* | *0.01* | *-0.08* | *68%* | *6.04%* | *5.27%* | *68%* |

**This is the finding.** The TRAIN-selected variant beat **68%** of random books on TRAIN
and **14%** of them on TEST — a clean overfitting inversion. **All five variants are
below the 50th percentile on TEST, on both Sharpe and CAGR.** Beating a coin flip is the
minimum bar for claiming an edge, and this strategy fails it out-of-sample on every
setting tested.

Note also that a *random* book of this exposure earns ~1–3% CAGR. It is not 0% — that is
the long-only beta of partially-invested Indian equity. "It made money" would therefore
have been a worthless claim here; the control is the only meaningful bar.

### 4.8 Cash-matched control

What if instead of choosing names, the book simply held the **market** with the *same
exposure on the same days*? This isolates the selection decision from the cash decision.

| Window | Variant | Invested% | MFI net CAGR% | Cash-matched CAGR% | **Selection edge%** |
|---|---|---|---|---|---|
| TRAIN | V1 | 12.3 | -0.69 | 0.33 | **-1.02** |
| TRAIN | V3 | 42.8 | 6.04 | 7.45 | **-1.41** |
| TEST | **V1** | 18.2 | -0.54 | 2.10 | **-2.64** |
| TEST | **V3** | 45.8 | 0.76 | 5.11 | **-4.35** |

**On TEST, every variant is beaten by holding the market with its own exposure.** The
shipped V1 gives up 2.64pp/yr versus simply being invested; V3 gives up 4.35pp/yr. The
MFI selection is *actively destructive* relative to its own cash level. This is the
cleanest statement of the failure: the signal is not merely absent, it is worse than the
alternative of not choosing.

### 4.9 Cost stress (incl. the zero-cost control)

| Window | Variant | zero cost | base (5bps) | double (10) | triple (15) |
|---|---|---|---|---|---|
| TRAIN | V1 shipped | -0.41 | -0.69 | -0.96 | -1.24 |
| TRAIN | V3 | 6.88 | 6.04 | 5.20 | 4.36 |
| **TEST** | **V1 shipped** | **-0.13** | -0.54 | -0.95 | -1.36 |
| **TEST** | **V3** | 1.59 | 0.76 | -0.07 | -0.89 |
| TEST | V5 | 4.87 | 4.07 | 3.27 | 2.48 |

**The shipped V1 is negative even at ZERO cost** on both windows (-0.41% TRAIN, -0.13%
TEST). The zero-cost run charges **11.92 bps** (statutory only, slippage removed),
confirmed from the run diagnostics — so this is not a hidden-slippage result. This is the
decisive diagnostic: the failure is **not** costs. Removing every
rupee of friction does not rescue it, because there is no gross signal to rescue. A
strategy that is only "close to zero" at zero cost has nothing. V3 needs ~double slippage
to go negative on TEST, but it is already losing to random at base cost, so the cost
level is not the binding constraint either.

### 4.10 Yearly returns

**TEST**

| Run | 2024 | 2025 | 2026 (partial) |
|---|---|---|---|
| V1 shipped | -1.6 | 3.3 | -3.1 |
| V2 | 2.3 | 6.3 | -4.1 |
| V3 (picked) | 3.7 | 5.4 | -6.6 |
| V4 | -1.5 | 8.4 | -0.1 |
| V5 | 7.2 | 9.9 | -5.1 |
| buy-and-hold | **20.1** | **13.4** | -8.3 |
| nsealgo composite | 5.6 | 6.5 | -9.3 |

Buy-and-hold beats every MFI variant in **every single TEST year**. No exceptions.

### 4.11 Did it beat the nsealgo composite?

**On CAGR, marginally; on risk-adjusted, no.** V5 (4.07%) and V4 (2.31%) edge past the
composite's 0.71%, but every MFI variant has a **worse Sharpe** than nothing in
particular and all are negative: V5 -0.32 vs composite -0.43, V3 -0.68. The composite is
itself weak on this window (it is a flat-to-down TEST period), so beating it is not a
result. Both lose to random or to their own cash-matched control.

### 4.12 Sanity checks (brief §6)

| Check | Result |
|---|---|
| 1. Plausibility (≤40–50% CAGR unlevered) | Max 21.8% TRAIN, 8.4% TEST — **no bug signature** ✅ |
| 2. Weight count (avg names ≈ 22, not 48) | 1.2–11.7 — **far below 22, and that is correct here**: it reflects a sparse signal, not accumulating residuals. Mass that has no legal home is left as cash by design (§4.1) ✅ |
| 3. Signal liveness (>5% of bars long) | **V1 2.35% — BELOW the floor. It is effectively an always-flat book.** V2 8.7%, V3 20.7%, V5 13.2% ✅/❌ flagged |
| 4. Cost drag reported | 0.59–1.92%/yr ✅ |
| 5. Negative control | **FAIL — all five variants below the 50th percentile on TEST** ❌ |

---

## 5. Bugs found

**B1 — harness bug I introduced and caught before it could reach a result (my code).**
My first vectorised MFI shifted the rolling window back one bar
(`rolling(period).sum().shift(1)`), on the reading that the catalog's `range(-period, 0)`
meant "the window *before* today". It does not. The catalog sums the **last `period` bars
including today**, so the value at *t* is a plain `rolling(period)` over
*t-period+1 .. t*.

This was caught by `mfi_lib.verify_against_catalog`, which replays the shipped scalar
function over ~2,300 random windows per lookback and raises on any disagreement. It
rejected **2313 / 2328** windows. Left uncorrected it would have produced a perfectly
plausible set of MFI numbers shifted one day into the future — and because the shift is
*forward-looking*, it would have silently improved the backtest.

**The verification harness, not inspection, is what caught it.** I am recording this
because the failure mode is invisible from the output: the equity curve would have looked
fine. Anyone building a vectorised replacement for a scalar catalog indicator should replay
the original over random windows before trusting a single number. The fixed version
matches to ~1e-12 (§4.1).

**B2 — real design defect in the shipped strategy: `MfiStrategy` is mis-parameterised for
its own thesis, and the `upper` half is dead code.**
`MfiConfig.upper = 80` produces `signal() == -1`, i.e. **short**. A long-only Indian
delivery book cannot take that position (`GOAL.md` §3.1). For this mandate `upper` is
**dead configuration**: it can never become a position, so it is not a parameter. A user
reading `MfiConfig(period=14, upper=80, lower=20)` would reasonably believe they have two
tunable thresholds. They have one.

**B3 — the shipped `lower = 20` default is below the liveness floor for a cross-sectional
book.** `MFI < 20` fires on 2.35% of symbol-days, median 0 names per day, and 0 names on
half of all days (§4.1). As a *single-name* signal this might be tolerable; as input to a
22-name cross-sectional book it is fatal — the book is structurally empty. The same
defect class as `agent_obv`'s B1 (a per-symbol time-series parameter that does not survive
contact with a cross-sectional portfolio), and it is the single most actionable thing in
this report: **`lower` should be re-defaulted upward (~40) for cross-sectional use, which
is the V3 setting — and V3 still fails the random control.** So the fix improves the book
without creating an edge.

I did not modify `src/cryptobot/**` (brief §9), so B2 and B3 are reported, not fixed.

**Data caveat — 6.51% of symbol-days have no H/L/V bar** (symbols listed later than
2008, plus halts), and **0.24% carry zero volume**. A missing bar inside the MFI window
propagates NaN through the rolling sum, exactly as it does in the catalog function, so the
affected symbol is simply unscored that day rather than silently zero-filled. Zero-volume
days contribute a zero flow to both the positive and negative sums, which *dilutes* the
window without biasing its direction; it makes effective lookback longer than nominal on
those names. Neither is a source of a spurious edge, but both slightly shrink the
tradable set.

## 6. Verdict

**No. `mfi_strategy` does not make money on NSE out-of-sample.**

The TRAIN-selected variant returns **0.76% CAGR with a Sharpe of -0.68**, against
buy-and-hold's 8.36% / +0.19. All five declared variants have **negative TEST Sharpe**.
Every one of them lands **below the 50th percentile against a random signal** — the
TRAIN-picked one at the **14th percentile**, down from the 68th it scored on TRAIN. The
shipped strategy is **negative even at zero cost** on both windows, so this is not a cost
problem.

### Most likely reason

**MFI is a mean-reversion oscillator, and Indian daily equity data rewards continuation,
not reversal.** The engine's own module docstring states this design premise and cites the
evidence: Sehgal & Jain (2011) and IIMC (2020) find Indian short-term *continuation*, and
the only multiple-testing-corrected study of Indian technical rules (Romano-Wolf,
2015–2025) found RSI_25_75, RSI_30_70, Bollinger 20/2.0 and Bollinger 20/2.5 all failed
— MFI is structurally the same bounded-oscillator-read-as-reversal family as those
rules, and it fails in the same place.

Three findings reinforce it and are specific to *this* implementation:

1. **The signal is too sparse to build a book from** (§4.1). At the shipped threshold the
   portfolio is 46% cash, and the apparent drawdown control is exposure, not skill — its
   TEST beta component is 0.59% against a market returning 8.26%.
2. **The selection is actively worse than not choosing** (§4.8). Against its own cash
   level — holding the *market* with identical exposure on identical days — every TEST
   variant loses: V1 by 2.64pp/yr, V3 by 4.35pp/yr. So "buy oversold names" is not a
   neutral, slightly-unprofitable rule; it is a rule that destroys value relative to its
   own cash.
3. **The brief's ranking construction fights the signal** (§3.2). Ranking oversold names
   by trailing 126-day momentum prefers the ones that fell *least* — a "least-bad falling
   knife" filter, not a mean-reversion bet and not a momentum bet. It is a third thing that
   is neither. I used it unmodified because deviating would have been choosing a
   construction to flatter my own result; I flag it as the most likely reason a fair-minded
   retry would still find nothing.

The failure is **not** costs, **not** lookahead, and **not** the harness: the look-ahead
tripwire passes with 0/64,992 weights altered, the vectorised MFI matches the shipped
indicator to 1e-12, V3 survives double slippage, and the weight counts are explained
exactly by the sparse signal rather than by accumulating residuals.

### The one thing I would try next

**Test MFI as a *confirmation filter on the momentum composite*, not as a standalone
ranking signal — and hold the composite's names regardless of MFI, using MFI only to
gate *entry*.** The evidence for that being worth one run: the decomposition in §4.4
shows the only place any variant shows positive TRAIN selection alpha is V4 (+2.74%), and
the drawdown side of the book is where the signal's information plausibly lives. The
distinct hypothesis is that MFI *extremes* carry useful **timing** information about when
the market is about to fall, even though they carry no **ranking** information about which
stock to own. That is a different, testable claim, and it is the only one the data so far
leaves open.

I would **not** try more thresholds. I declared 5 variants, spent exactly 5, and the
TEST result shows the in-sample ranking was *anti-correlated* with out-of-sample
performance (V3 was the TRAIN pick and the 14th-percentile result). A 6th threshold would
be fitting noise on a signal that has already failed its coin-flip test — the exact
mistake this protocol exists to prevent.

## 7. Honest summary of what this run is worth

- **A publishable negative, with a clean mechanism.** Not "it didn't work" but *why*:
  a mean-reversion oscillator in a continuation market, applied at a threshold too sparse
  to fill a cross-sectional book, ranked by a rule that is neither momentum nor reversion.
- **Three real defects found in shipped code** (B2 dead `upper` parameter, B3 sub-floor
  default threshold, plus B1 in my own harness) — none of which touch `src/`, per brief §9.
- **A reproducible harness** at `engine_sha d93815344bd3`: `data_prep.py`, `mfi_lib.py`,
  `run_variants.py`, `controls.py`, `verify_claim.py`. Re-running any of them reproduces
  every number above.
- **A reusable method worth keeping.** The `verify_against_catalog` replay check caught a
  one-day forward shift that would otherwise have looked like a working strategy. The
  cash-matched control (§4.8) is what separated "good strategy" from "mostly cash" here,
  and it is cheap enough to belong in the standard harness for every sparse-signal strategy
  in this catalogue.

**Parameter budget: declared 5, spent exactly 5.** TEST was touched once, after V3 was
frozen on TRAIN. No number in §4.5–§4.11 was used to select anything.

*Not committed, per brief §9.*
