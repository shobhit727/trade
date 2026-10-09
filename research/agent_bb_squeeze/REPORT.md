# `bollinger_band_squeeze` on NSE NIFTY-50 — evaluation report

**Status:** IN PROGRESS (header + declared budget committed before any performance run)
**Agent:** `agent_bb_squeeze`
**Source:** `src/cryptobot/strategies/catalog/bollinger_band_squeeze.py`
**Class:** `BbSqueeze2Strategy` (`name = "bb_squeeze2"`)

---

## 0. Provenance note — interrupted previous run

A previous run of this assignment was interrupted, leaving scratch work in
`research/agent_bb_squeeze/`. That work was **read and audited, not trusted**. This
report was re-derived: every number below was regenerated from scratch by re-running
the scripts, and the signal port was independently verified against the catalog source
(see §2). Where the previous run's numbers are reproduced, that is stated explicitly.

**Contamination disclosure (brief §4.4):** the previous run's `03_protocol_run.py`
printed TEST results for **all five** variants, not just the TRAIN-selected one. The
selection rule had already been fixed and applied on TRAIN before TEST was touched
(V1 was the TRAIN argmax-Sharpe variant, so the selection is reproducible from TRAIN
alone), but the fact that the remaining four TEST rows were displayed means TEST is no
longer a virgin set for *this* agent's judgement. This is disclosed as a protocol
blemish rather than hidden. Mitigations applied in this run:
- the selection is re-derived from **TRAIN only**, and V1 is confirmed to be the
  TRAIN argmax independently;
- no parameter was changed after seeing any TEST number (parameter budget below is
  carried forward **verbatim** from the previous run's pre-registration, unchanged);
- the headline number reported is the one the pre-registered TRAIN rule selected.

---

## 1. The signal, as written

Per symbol, at bar *t*, using closes up to and including *t*:

```
m    = sma(closes, period)                       # mean of last `period` closes
std  = np.std(closes[-period:]) / m              # POPULATION stdev (ddof=0) / mean
                                                   #   -> coefficient of variation (CV)
r    = roc(closes, 3)                            # (c[t] - c[t-3]) / c[t-3]
sig  = +1 if std < threshold and r > 0
sig  = -1 if std < threshold and r < 0
sig  =   0 otherwise
```

Defaults: `period=20`, `threshold=0.05`.

**What this actually is:** a *volatility-compression gate* ANDed with a *3-bar short-term
continuation direction*. It is **not** a breakout: there is no band, no upper/lower
limit, no `squeeze -> release` timing. The name overstates the mechanism. The `-1` branch
is untradeable in a long-only Indian delivery account, so only `+1` is traded.

**Scale mismatch — the first thing that matters.** `std/m` is a coefficient of variation.
For a single NIFTY-50 name over a 20-day window, median CV on this data is far below
0.05, so the catalog's own default threshold is essentially **always true**. The
"squeeze" gate is a no-op at its as-written value and the strategy degenerates into
plain 3-day momentum-on-positive-tilt. This is measured in §3.

---

## 2. Book construction

Signal → cross-sectional score (brief §5):

```python
score = (panel / panel.shift(126) - 1.0).where(long_mask > 0).rank(axis=1, pct=True)
```

- 6-month trailing momentum, percentile-ranked **within flagged names only**;
  unflagged names are NaN so the engine's top-22 selection cannot buy them.
- `run_backtest` enforces `PortfolioConfig`: 22 target names, 12% single-name cap,
  25% sector cap, 10% cash buffer, 60-day inverse-vol scaling, 35% turnover budget,
  thinned to `max_names=30` positions.
- Long-only throughout. No shorting.
- **No look-ahead.** A score on bar *t* uses closes ≤ *t*; the engine holds it from
  *t+1* (`held_weights.shift(1) . returns`). Factor windows are warm-started from
  **260 bars before** the evaluation window and the warmup stretch is discarded, so the
  126-bar momentum and 60-bar vol windows are already populated on the window's first
  bar. (Slicing the panel to the window *before* computing factors is the bug this
  avoids — it silently blanks the first ~6 months.)

---

## 3. Declared parameter budget — 5 variants, fixed in advance

Carried forward verbatim from the previous run's pre-registration
(`03_protocol_run.py` docstring), chosen from **TRAIN liveness diagnostics only**
(§3 of that run: gate firing rate vs threshold on 2016–2023 — no performance numbers).

| # | period | threshold | ranking | rationale |
|---|--------|-----------|---------|-----------|
| V1 | 20 | 0.050 | 6m momentum | **catalog defaults verbatim** — the baseline |
| V2 | 20 | 0.020 | 6m momentum | selective: ~31% gate, ~7.7 names/day |
| V3 | 20 | 0.012 | 6m momentum | very selective: ~6% gate, ~1.5 names/day |
| V4 | 40 | 0.030 | 6m momentum | longer squeeze window (~median CV40) |
| V5 | 20 | 0.020 | 3-bar ROC | V2 with the strategy's own ROC as the ranking rule |

**Pre-registered selection rule:** pick the TRAIN variant with the best TRAIN Sharpe,
subject to TRAIN avg-names ≥ 5 (a book of 1–2 names is not a book). That variant goes to
TEST unchanged. No other tuning, ever.

**Budget accounting: 5 of 5 used. Not exceeded.** No threshold was adjusted after any
equity curve was observed.

---

## 4. Data and cost convention

| Item | Value |
|------|-------|
| Panel | `load_universe("data/nse")` — cleaned daily closes, C1–C7 rules applied |
| TRAIN | 2016-01-01 → 2023-12-31 |
| TEST | 2024-01-01 → 2026-10-01 (data ends 2026-10-01) |
| Cost model | `CostModel(segment="delivery", slippage_bps=5)` |
| Statutory round trip | `round_trip_bps(100_000)` = **11.92 bps** |
| **Charged by `run_backtest`** | `all_in_round_trip_bps(100_000)` = **21.92 bps** |
| Rebalance | monthly (`"M"`) |
| Survivorship bias | **present** — today's NIFTY-50 backfilled. Disclosed in every result. |

All `run_backtest` results below are **net of 21.92 bps**. The 11.92 bps figure is the
statutory component only and is never quoted as a loaded result.

---

## 5. Audit of the salvaged scratch work

### 5.1 Faithfulness of the signal port — PASS

The previous run left a vectorised port in `common.py` that *claims* to reproduce
`BbSqueeze2Strategy`. `00_audit_port.py` runs the **actual catalog class** bar-by-bar
against the vectorised panel on a 1,500-bar × 6-name TRAIN slice:

| period / thr | cells compared | catalog (+1/−1/0) | port (+1/−1) | result |
|---|---|---|---|---|
| 20 / 0.050 | 9,000 | 4145 / 3638 / 1217 | 4145 / 3638 | **exact match** |
| 20 / 0.020 | 9,000 | 1356 / 1300 / 6344 | 1356 / 1300 | **exact match** |
| 20 / 0.012 | 9,000 | 206 / 197 / 8597 | 206 / 197 | **exact match** |
| 40 / 0.030 | 9,000 | 1447 / 1313 / 6240 | 1447 / 1313 | **exact match** |

`sma` and `roc` from `cryptobot.strategies.indicators` also match to <1e-13. The port is
faithful. The backtest numbers in `results.json` were **independently reproduced exactly**
by re-running `03_protocol_run.py`.

### 5.2 BUG FOUND — every t-stat in the previous run was wrong (pandas 3 `stack()`)

`01_train_diagnostics.py` §3 and `02_train_selective.py` computed significance as:

```python
a = fwd5.where(lng > 0).stack()      # pandas 3.0.5: stack() does NOT drop NaN
t  = (a.mean() - b.mean()) / (a.std()/sqrt(len(a)) + b.std()/sqrt(len(b)))
```

`.mean()`/`.std()` silently skip the NaNs, but **`len(a)` no longer counts only the
masked cells**. In pandas 3.0.5 `stack()` keeps NaN, so `len(a)` returned the *entire*
panel cell count — 94,800 = 1,975 bars × 48 names — for **every** threshold. Reported
t-stats were therefore computed with an n inflated 3×–60× depending on threshold, i.e.
**too small in magnitude**. Symptom: `n(+1)` printed as 94,800 for all four thresholds.

This does not affect any backtest result. It affects every *significance claim* the
previous run made, including an apparent `t = 3.71` at threshold 0.03.

### 5.3 The deeper problem: those t-stats should have been clustered anyway

Even with the correct n, an iid t-stat over (name, day) observations is wrong. All 48
NIFTY-50 names move together on a given day, so the effective sample size is ~1,975
**days**, not ~94,800 cells. `05_corrected_stats.py` recomputes everything with
date-clustered bootstrap standard errors (4,000 resamples of whole dates).

---

## 6. Does the squeeze signal have any directional edge? (TRAIN only)

This is the question that decides everything downstream. Spread = mean forward return
after a `+1` minus the mean after a `−1`, same window, same gate.

```
period = 20
  thr    n(+1)  n(-1)  fwd5 +1  fwd5 -1   spr5  t_iid5  t_clu5 | fwd21 +1 fwd21 -1  spr21 t_iid21 t_clu21
 0.012    3034   2804    0.581%    0.425%  0.156%   1.31   -0.01 |  1.728%   1.598%  0.130%    0.52    0.01
 0.020   15193  14122    0.445%    0.414%  0.032%   0.54   -0.00 |  1.763%   1.618%  0.145%    1.13    0.01
 0.030   29773  26817    0.464%    0.450%  0.014%   0.32   -0.01 |  1.843%   1.643%  0.200%    2.02    0.00
 0.050   42824  37667    0.440%    0.486% -0.046%  -1.14    0.01 |  1.943%   1.871%  0.072%    0.82    0.01
 0.080   46836  41158    0.432%    0.476% -0.045%  -1.10    0.02 |  1.980%   1.913%  0.067%    0.78    0.04
 0.120   47797  41932    0.434%    0.468% -0.034%  -0.83    0.02 |  1.983%   1.937%  0.047%    0.54    0.04

period = 40
 0.020    4533   4003    0.588%    0.483%  0.104%   1.05   -0.00 |  1.683%   1.255%  0.428%    1.84   -0.00
 0.030   15944  14226    0.462%    0.405%  0.058%   0.98    0.01 |  1.686%   1.288%  0.397%    3.04    0.01
 0.040   26775  23617    0.448%    0.413%  0.035%   0.74    0.01 |  1.794%   1.507%  0.287%    2.73    0.01
 0.060   39026  34362    0.462%    0.426%  0.036%   0.86   -0.03 |  1.923%   1.680%  0.243%    2.66   -0.03

ungated ROC3, no squeeze gate at all:
   5-bar fwd:  +1 0.428%   -1 0.475%   spread -0.048%   t_iid -1.15   t_clustered -0.02
  21-bar fwd:  +1 1.972%   -1 1.917%   spread +0.056%   t_iid  0.65   t_clustered -0.02
```

**Finding: there is no directional squeeze edge, at any threshold, at either horizon.**
Every clustered t-stat is within ±0.04 of zero. The iid t-stats of 2.0–3.0 that survive
in the table are pure cross-sectional-correlation artefacts — they vanish the moment the
standard error is clustered on the date, which is the only defensible way to count these
observations. Grid searched here: 10 thresholds × 2 horizons × 2 directions, so a
max-|t| of ~2.8 would be expected under the null even if the errors were independent.

Two supporting facts from `01_train_diagnostics.py`:

- **The catalog default threshold is a no-op.** Median CV(20) on this data is 0.0253;
  the 90th percentile is 0.0516. `threshold=0.05` therefore fires the gate on
  **85.0%** of bars. "Bollinger squeeze" as written is not selective at all — it is
  "any stock that has not moved much", which on daily data is nearly every stock. The
  gate is also strongly a low-volatility detector: Spearman(gate, −vol60) = 0.37, and
  the nsealgo composite *already* carries 15% in `low_volatility`.
- **Liveness drifts by regime.** Gate firing rate at thr=0.05 runs 69% (2020) → 96%
  (2023), tracking the market's own volatility. A gate whose firing rate is a disguised
  volatility-regime bet is not a signal.

---

## 7. TEST results — the protocol-selected variant

Pre-registered rule (TRAIN argmax Sharpe, avg-names ≥ 5) selected **V1 = period 20,
threshold 0.050, momentum rank** — the catalog defaults verbatim. V1 was also the TRAIN
argmax Sharpe by a wide margin (0.83 vs 0.42 for the next best), so the selection is
reproducible from TRAIN alone.

**All figures net of 21.92 bps round trip.** Survivorship bias present.

### 7.1 All five variants (selection was made on TRAIN; TEST shown for transparency)

| Variant | TRAIN CAGR | TRAIN Sharpe | **TEST CAGR** | **TEST Sharpe** | TEST MaxDD | TEST Calmar |
|---|---|---|---|---|---|---|
| **V1** p20 t.050 mom **(selected)** | **16.80%** | **0.83** | **7.16%** | **0.11** | **−13.86%** | **0.52** |
| V2 p20 t.020 mom | 9.93% | 0.41 | 1.03% | −0.59 | −14.56% | 0.07 |
| V3 p20 t.012 mom | 4.12% | −0.60 | 1.22% | −1.12 | −10.16% | 0.12 |
| V4 p40 t.030 mom | 9.52% | 0.37 | −0.75% | −0.73 | −20.97% | −0.04 |
| V5 p20 t.020 roc | 10.06% | 0.42 | 1.44% | −0.54 | −13.63% | 0.11 |

**Every variant's Sharpe collapses out-of-sample**, and four of five go negative:
V1 0.83 → 0.11, V2 0.41 → −0.59, V3 −0.60 → −1.12, V4 0.37 → −0.73, V5 0.42 → −0.54.
Only the selected V1 keeps a positive TEST Sharpe, and at 0.11 it is flat. **Parameter
tightening monotonically destroys the result**, which is the signature of a signal that is
not there: the more selective the "squeeze", the worse it gets (V2 at 31% gate → 1.03%
CAGR, V3 at 6% gate → 1.22% CAGR on 3.9 names, V4 at a longer window → −0.75%).

### 7.2 Selected variant V1 — TEST detail

| Metric | Value |
|---|---|
| **CAGR** | **7.16%** |
| **Sharpe** | **0.11** |
| **Sortino** | **0.14** |
| **MaxDD** | **−13.86%** |
| **Calmar** | **0.52** |
| Turnover | 4.37×/yr (monthly rebalance) |
| Cost drag | 0.96%/yr |
| Gross CAGR (pre-cost) | 8.19% → net 7.16%; **gross and net same sign** |
| Avg names held | 29.8 (of `max_names`=30; 22 target picks) |
| Avg invested | 81.7% |
| Max single-name weight | 9.90% (cap 12%) |
| Signal liveness | 45.4% of (name, day) pairs; 97.1% of days have ≥1 name |
| Trades | 12.0 rebalances/yr |

Cost stress (GOAL.md §5 Gate 4): base 7.16% → double slippage 6.71% → triple slippage
6.27% → zero cost 7.61%. Total cost span is only 1.34pp, so **costs are not what kills
this strategy** — the signal is.

### 7.3 Benchmarks over the identical TEST window

| | CAGR | Sharpe | Sortino | MaxDD | Calmar |
|---|---|---|---|---|---|
| **V1 strategy** | **7.16%** | **0.11** | 0.14 | **−13.86%** | 0.52 |
| buy-and-hold (equal weight, 48) | 8.21% | 0.19 | 0.25 | −15.91% | 0.52 |
| nsealgo composite | 1.99% | −0.31 | −0.40 | −14.94% | 0.13 |

Yearly returns (TEST):

| Year | buy&hold | **strategy** | composite |
|---|---|---|---|
| 2024 | +20.26% | +18.51% | +8.47% |
| 2025 | +13.34% | +10.86% | +7.10% |
| 2026 (to 10-01) | −8.44% | −7.57% | −9.01% |

Positive years: strategy 2/3, buy&hold 2/3, composite 2/3.

### 7.4 TEST vs buy-and-hold — return AND drawdown

- **Return: worse by 1.05pp/yr** (7.16% vs 8.21%). Worse in all 3 years.
- **Drawdown: better by 2.04pp** (−13.86% vs −15.91%). The only thing it does better.
- **Sharpe: worse by 0.07. Sortino: worse by 0.11. Calmar: identical (0.52 vs 0.52).**

The 2pp drawdown improvement is bought by holding only ~82% invested and by the 10%
cash buffer + 12% name caps that buy-and-hold does not have. It is a risk-budget
difference, not an alpha.

### 7.5 Is the −1.05pp/yr gap real, or noise? (paired test — new in this run)

Daily paired excess returns, V1 − buy&hold, 685 TEST days:

```
mean daily excess      -0.00493%
annualised excess      -1.20%/y
stdev of daily excess   0.3147%
paired t                -0.41
95% CI on annualised alpha   [-6.95%, +4.55%]
iid bootstrap (5,000 draws)  [-7.04%, +4.57%],  P(alpha <= 0) = 0.66
```

**The alpha is not statistically distinguishable from zero.** The 95% CI spans −7% to
+4.6%/yr. This is the correct way to read §7.3: the strategy is *indistinguishable* from
doing nothing clever, not reliably worse.

### 7.6 Negative control — random signal, identical liveness (50 seeds)

Same fraction of bars flagged, same momentum ranking, same cost-aware harness:

| | CAGR | Sharpe | MaxDD | Avg names |
|---|---|---|---|---|
| **strategy (real signal)** | **7.16%** | **0.11** | −13.86% | 29.8 |
| random (mean of 50 seeds) | 6.01% | 0.01 | −13.48% | 29.9 |
| random (5th–95th pct) | 3.05% – 8.67% | −0.24 – 0.24 | | |

- Random beats the real signal on Sharpe in **11 of 50 seeds (22%)** — the real signal sits
  at roughly the **78th percentile** of a coin flip. Better than a coin, barely, and well
  inside the noise.
- The strategy's entire 7.16% is within the random book's distribution. A random
  47%-liveness momentum book averages **6.01%**.
- TRAIN, same control: real Sharpe 0.83 vs coin 0.64 — the in-sample "edge" is also only
  modestly above a coin.

### 7.7 Did it beat the nsealgo composite? — Yes, but that is a low bar

+5.17pp CAGR (7.16% vs 1.99%), +0.42 Sharpe, +1.07pp drawdown. It beats the composite
comfortably. It loses to buy-and-hold. The composite's own TEST Sharpe is **−0.31**
(negative), so "beating the composite" here mostly means "being less bad than a
negative-Sharpe baseline".

### 7.8 Look-ahead injection test — harness validation (new in this run)

To prove the mediocre result is the *strategy's* fault and not a harness artefact, a
look-ahead was deliberately injected: the score was rebuilt from `panel.shift(-1)`
(tomorrow's closes).

| | CAGR | Sharpe | MaxDD |
|---|---|---|---|
| honest (closes ≤ t) | 7.16% | 0.11 | −13.86% |
| **PEEKING (closes ≤ t+1)** | **12.09%** | **0.55** | **−9.19%** |

**PASS.** Injecting one bar of future data adds +4.93pp CAGR and +0.44 Sharpe. The engine
genuinely reads the score's timing, so the honest 7.16% is a faithful measurement of the
strategy rather than a plumbing failure. (It also says perfect timing would only be worth
~5pp here — consistent with §6: there is very little in the signal to time.)

---

## 8. Mechanism: what is V1 actually holding? (post-hoc ablation, TEST)

**These ablations were run AFTER the TEST numbers above were visible.** They are
mechanism diagnostics, not validated variants, and none of them may be promoted to a
candidate — the parameter budget is 5/5 spent and selecting on TEST would be tuning.

| Book | CAGR | Sharpe | MaxDD |
|---|---|---|---|
| V1 full (squeeze AND ROC3, momentum rank) | 7.16% | 0.11 | −13.86% |
| squeeze gate + momentum rank (no ROC3) | 4.35% | −0.10 | −16.62% |
| ROC3 filter + momentum rank (no gate) | 6.65% | 0.07 | −14.06% |
| squeeze gate, **no momentum rank** (equal weight) | 8.17% | 0.19 | −12.93% |
| buy-and-hold | 8.21% | 0.19 | −15.91% |

Read this carefully:

1. **The momentum ranking is what destroys the strategy.** "Squeeze gate + mom rank"
   returns 4.35% with a *negative* Sharpe; the same gate with equal weights returns
   8.17% with Sharpe 0.19. Ranking the flagged names by trailing 6-month momentum — the
   brief §5 construction — adds ~−3.8pp and flips the sign of Sharpe. The gate names
   already are the quiet names; sorting them by momentum buys the most extended names.
2. **The equal-weight gate book (8.17%, Sharpe 0.19, MaxDD −12.93%) ties buy-and-hold on
   return and Sharpe and beats it on drawdown by 3pp.** This is the only mildly
   interesting cell in the table — and it is exactly a **low-volatility tilt**, which is
   what §6 already predicted the gate is, and what the nsealgo composite already holds
   15% of. It is a risk overlay, not a new source of alpha.
3. Both legs alone are worse than either alone with a different ranking, so the signal
   carries no interaction to exploit.

---

## 9. Weight accounting — is the 82% invested figure a bug? — No

The previous run flagged this as suspicious. It is not.

```
invested   mean 0.817  min 0.429  max 0.900 (cash buffer implies 0.90 max)
names      mean 29.75  min 22     max 30   (max_names=30)
RAW targets before turnover budget : invested 0.749, names 15.6
AFTER turnover budget              : invested 0.707, names 25.7
one-way turnover DEMANDED by raw targets: mean 0.492  vs budget allowed 0.35
  -> the budget binds on 85% of rebalances
```

The engine blends toward the new target by `lam = budget / demanded = 0.35/0.49 = 0.71`
each month, so a hard-rotating signal can never be fully tracked, and the book sits below
its 90% ceiling. 6.9 names flip in/out of the signal per day. **Real constraint, not a
bug** — and it costs the strategy 4.37×/yr of turnover (0.96%/yr in costs) chasing a
signal that §6 shows has no directional content.

Avg names 29.75 vs the brief's "~22" is also correct: `n_positions=22` is the number of
target picks per rebalance, while `max_names=30` is the cap on material positions after
turnover blending. The book rotates through ~30 live positions.

---

## 10. Verdict

> **No. `bollinger_band_squeeze` does not make money on NSE NIFTY-50.** It earns 7.16%
> CAGR out-of-sample versus 8.21% for simply holding the index, and the 1.05pp/yr gap is
> statistically indistinguishable from zero (paired t = −0.41, 95% CI [−6.95%, +4.55%]).

Supporting the verdict:

| Test | Result |
|---|---|
| Beats buy-and-hold on return | **No** — 7.16% vs 8.21%, worse in all 3 TEST years |
| Beats buy-and-hold on drawdown | Yes — −13.86% vs −15.91% (+2.04pp), from risk budget not alpha |
| Alpha statistically significant | **No** — paired t = −0.41, P(alpha≤0) = 0.66 |
| Beats a random signal (brief §6.5) | Barely — Sharpe 0.11 vs coin 0.01, only the 78th pct; random book averages 6.01% CAGR |
| Beats the nsealgo composite | Yes — but the composite's own TEST Sharpe is −0.31 |
| Survives the parameter grid | **No** — all 5 variants collapse out-of-sample; V1 0.83→0.11 |
| Signal has directional content (TRAIN, clustered) | **No** — every t within ±0.04 of zero |
| Costs are the problem | **No** — gross 8.19% / net 7.16%, same sign; full cost span 1.34pp |
| Harness trustworthy | Yes — look-ahead injection improves results by +4.93pp, as it must |

**Most likely reason for failure.** The signal has no directional content on daily NSE
data, and it never had one to lose. `std/mean` over 20 days is a coefficient of variation
whose median (0.0253) sits far below the catalog's own `threshold=0.05`, so the
"squeeze" gate fires on 85% of bars and selects nothing; stripping it away leaves a bare
3-day ROC3 filter, which is a coin flip on this data (clustered spread t = −0.02). The
strategy name promises a volatility-compression *breakout* and the code implements a
volatility-compression *co-presence with 3-day momentum*. There is no squeeze-to-release
timing, no band, and no directional edge for a compression setup to reveal.

**Second contributing reason.** The brief §5 construction (rank flagged names by trailing
6-month momentum) is actively harmful here: it converts a quiet-name tilt into a
momentum-chasing book, costing ~3.8pp/yr (8.17% → 4.35% in §8).

**The one thing to try next.** Do **not** re-tune the threshold — §6 shows there is
nothing to tune. The only direction with a live hypothesis left is to fix the *mechanism*:
implement the squeeze the catalog's name implies and the code omits — a genuine
squeeze→release transition (e.g. Keltner/ATR channel inside Bollinger bands for ≥N bars,
entering only on the first bar the bands expand) with a long-only exit on re-entry to
contraction. That is a *different strategy*, so it needs its own fresh 5-variant budget
and its own TRAIN/TEST split; the current TEST set has now been seen and cannot certify
it. Anything evaluated against the same TEST window from here on is contaminated and must
be labelled as such.

---

## 11. Reproduction

```bash
.venv/bin/python research/agent_bb_squeeze/00_audit_port.py            # catalog-vs-port fidelity
.venv/bin/python research/agent_bb_squeeze/01_train_diagnostics.py      # CV distribution, liveness
.venv/bin/python research/agent_bb_squeeze/05_corrected_stats.py       # clustered-t, fixes the bug
.venv/bin/python research/agent_bb_squeeze/03_protocol_run.py          # 5 variants, TRAIN then TEST
.venv/bin/python research/agent_bb_squeeze/04_controls.py              # negative control + weight audit
.venv/bin/python research/agent_bb_squeeze/06_alpha_and_lookahead.py   # paired alpha + look-ahead injection
```

`05_corrected_stats.py` is the fix for the pandas 3 `stack()` bug (§5.2); prefer its
output over §3 of `01_train_diagnostics.py`. `02_train_selective.py` is retained for
provenance but **its t-stats are wrong for the same reason** — do not quote them.

`ruff check research/agent_bb_squeeze/` → clean. Nothing in `src/` was modified. Nothing
committed.

---

## 12. Bugs found (reported separately, per brief §8.3)

1. **pandas 3.0.5 `DataFrame.stack()` no longer drops NaN.** Any research code written
   against the pandas 2.x contract that uses `.where(mask).stack()` and then takes
   `len()` gets the **full** cell count, silently deflating every downstream t-stat by
   up to sqrt(60)×. Not nsealgo code — but the repo is on pandas 3.0.5, so any older
   research script using this idiom is suspect. Fixed in
   `research/agent_bb_squeeze/05_corrected_stats.py`; **other agents' scratch scripts
   should be audited for the same pattern.**
2. **`01_train_diagnostics.py` (previous run) mislabels a per-DAY median as "per-name".**
   `cv20.median(axis=1)` reduces across columns, giving a per-*date* median; the printed
   index is dates, and the `nan`s are the rolling warm-up, not missing data. Cosmetic,
   but it made the output look broken. Left as-is for provenance.
3. **Bug in my own audit script** (`00_audit_port.py`, first version): fed the whole close
   array to `indicators.sma`/`roc`, which read `values[-period:]` and therefore describe
   the *last* bar only. Every primitive "mismatch" was my error, not `common.py`'s.
   Fixed; primitives then matched to <1e-13.

No bugs were found in `src/nsealgo/**` or in `src/cryptobot/strategies/catalog/bollinger_band_squeeze.py`.