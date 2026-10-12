# AGENT REPORT — `williams_r_strategy` on NSE NIFTY-50

**Status:** COMPLETE — negative finding, validated.

## Provenance

```python
from nsealgo.provenance import provenance; provenance()
```
```
{'engine': 'd93815344bd3', 'loader': 'c1badf5f7df8', 'costs': 'ba350aef75b3', 'panel': '389b082b832f'}
```

Cost basis, verified by `.venv/bin/python -m nsealgo.cli costs` semantics and directly:
`round_trip_bps(100_000) = 11.92`, `all_in_round_trip_bps(100_000) = 21.92`.
**Every headline number below is net of 21.92 bps**, because everything goes through
`run_backtest`, which charges `all_in_round_trip_bps`. Zero-cost control = 11.92 bps.

## 1. Assignment and signal

- **Strategy:** `src/cryptobot/strategies/catalog/williams_r_strategy.py` (`WilliamsRStrategy`)
- **Signal:** Williams %R = `(HH - C) / (HH - LL) * -100` over `period` bars.
  `+1` when `%R <= lower`, `-1` when `%R >= upper`, else `0`. Defaults: `period=14, lower=-80, upper=-20`.
- **Crypto-specificity:** none. Pure price oscillator, no funding/peg/IV/basis. It has NSE meaning, so I ran it.
- **Implementation fidelity:** my vectorised %R was checked bar-for-bar against the real
  `cryptobot.strategies.indicators.williams_r` over 4 symbols x 3 periods.
  Value match to 1.4e-14 and the **flagged set is identical** (`s0_indicator_check.py`).

### Declared parameter budget (5 variants, written before any backtest ran)

| # | variant | period | lower | persistence | TRAIN Sharpe |
|---|---------|--------|-------|-------------|--------------|
| V1 | canonical-state   | 14 | -80 | none (state) | **-0.31** |
| V2 | canonical-touch21 | 14 | -80 | touch, L=21   | **0.53** |
| V3 | deep-touch21      | 14 | -90 | touch, L=21   | **0.31** |
| V4 | fast-touch21      |  5 | -80 | touch, L=21   | **0.76** |
| V5 | slow-touch21      | 28 | -80 | touch, L=21   | **0.36** |

5 declared, 5 run. No sixth. **Selection rule fixed in advance: highest TRAIN Sharpe -> V4.**
The other four variants were deliberately **not** run on TEST, so TEST cannot become a second
selection round.

### Construction
Long-only (the `-1` leg has no meaning in an Indian delivery account; it is discarded, not shorted).
Cross-sectional score per `AGENT_BRIEF.md` §5: percentile rank of 126d trailing momentum
**among signalled names only**; non-signalled names stay NaN and the engine drops them.
Monthly rebalance, `PortfolioConfig()` defaults (22 names, 12% single, 25% sector, 10% cash,
35% turnover budget) — never bypassed. No lookahead: %R on day *t* uses bars ≤ *t*; the engine
holds weights decided at *t* from *t+1*.

## 2. Protocol and disclosure

| Set | Window | Used for |
|-----|--------|----------|
| TRAIN | 2016-01-01 → 2023-12-31 | all 5 variants, all controls |
| TEST  | 2024-01-01 → 2026-10-01 | V4 only, once, unchanged |

**Full disclosure of what I saw and when** — this matters, so I am being exact:

1. V4's parameters were locked by TRAIN Sharpe in `s2_train.py`, before any TEST number existed.
2. `s3_diagnostic.py` printed **TEST** figures for buy-and-hold, the nsealgo composite and pure
   126d momentum *before* V4's TEST run, because those controls are required by `AGENT_BRIEF.md` §7.3.
   This did not influence V4's parameter choice (already locked) nor its metric code (fixed in advance).
   If anything it made me *expect* a bad V4 number and therefore less inclined to rescue it.
3. `s5_raw_edge.py` printed a TEST number for **V5's raw forward-return spread**, which happens to be
   the one positive result in the whole study. **I did not act on it.** Running V5's portfolio on
   TEST would be a second selection round on the out-of-sample window and would exceed the declared
   budget. It is reported in §7 as the next step, not as a result.

I did not tune thresholds after seeing TEST, and I did not re-select after seeing TEST.

## 3. TRAIN results (2016-01-01 → 2023-12-31, net of 21.92 bps)

```
name                         CAGR%  Sharpe  MaxDD% Calmar  Turn/y Drag%/y  Names   Rs on 21L
V1 canonical-state            3.13   -0.31  -31.68   0.10    3.60    1.81    6.7     593,344
V2 canonical-touch21         13.33    0.53  -35.32   0.38    4.02    2.90   21.4   3,678,306
V3 deep-touch21               9.81    0.31  -35.67   0.27    4.08    2.62   19.7   2,374,515
V4 fast-touch21              18.04    0.76  -35.21   0.51    3.14    2.78   22.0   5,928,552
V5 slow-touch21              10.24    0.36  -33.32   0.31    4.12    2.49   18.5   2,520,382
CONTROL buy-and-hold         17.96    0.77  -33.26   0.54    0.50    0.42   22.0   5,883,091
CONTROL nsealgo composite     20.29    0.90  -32.94   0.62    1.95    1.90   22.0   7,251,059
CONTROL random @V2 mask      11.16    0.44  -26.66   0.42    4.15    2.68   21.5   2,845,020   (10 seeds, range 10.66-12.06)
CONTROL random @V4 mask      12.51    0.55  -28.11   0.45    4.15    2.83   22.0   3,357,852   (10 seeds, range 11.49-14.23)
```

On TRAIN, V4 (18.04% CAGR) is **indistinguishable from buy-and-hold** (17.96%) and behind the
composite (20.29%) — while running 6.3x its turnover. V1–V3 and V5 all sit at or below the
random control. V2 in particular (13.33% / Sharpe 0.53) is statistically indistinguishable
from a coin flip at the same liveness (random: 11.16% / 0.44).

## 4. TEST results (2024-01-01 → 2026-10-01) — V4 only, net of 21.92 bps

```
name                         CAGR%  Sharpe  MaxDD% Calmar  Turn/y Drag%/y  Names   Rs on 21L
V4 WilliamsR (SELECTED)       2.68   -0.21  -16.21   0.17    3.41    1.75   22.0     161,619
buy-and-hold                  9.54    0.30  -13.48   0.71    0.50    0.27   22.0     611,103
nsealgo composite             7.61    0.14  -15.22   0.50    2.04    1.12   22.0     479,138
random @V4 mask (10 seeds)    3.38   -0.29  -11.54   0.31    4.24    2.08   22.0     206,028
  random range                CAGR [0.40, 5.05]   Sharpe [-0.57, -0.11]
```

Zero-cost control (11.92 bps statutory only):

```
V4 @ zero cost                3.38   -0.16  -15.04   0.22    3.41    0.96   22.0     205,265
buy-and-hold @ zero cost      9.65    0.31  -13.44   0.72    0.50    0.15   22.0     618,788
```

Calendar-year TEST returns:
```
V4 WilliamsR       2024: +19.1%   2025: +3.8%    2026: -12.9%
buy-and-hold       2024: +16.5%   2025: +16.0%   2026: -4.5%
nsealgo composite  2024: +27.0%   2025: +6.6%    2026: -9.3%
```

₹21,00,000 → **₹22,61,619** over 2.75 years. Buy-and-hold → ₹27,11,103.
(`GOAL.md` target is 3%/month net. This is 0.27%/month net — an order of magnitude short.)

## 5. Sanity checks (`AGENT_BRIEF.md` §6)

| # | check | result |
|---|-------|--------|
| 1 | **Plausibility** | PASS. 18.04% TRAIN / 2.68% TEST CAGR. No 200% bug; far below the 40-50% unlevered ceiling. |
| 2 | **Weight count** | PASS. V4 holds 22.0 names. (V1 held 6.7 — a concentrated book, flagged, and it was never selected.) |
| 3 | **Signal liveness** | PASS. Canonical `%R<=-80` fires on **16.4% TRAIN / 20.5% TEST** of symbol-days — well above the 5% always-flat line. V4's `p=5` fires 86%/94%. Not an always-flat strategy; it is a strategy that genuinely loses. |
| 4 | **Cost drag** | 1.75%/y, 6.5x buy-and-hold. Zero-cost cliff is only **0.70 pp/yr** (3.38% → 2.68%). Costs are *not* why this fails. |
| 5 | **Negative control** | **FAIL.** V4 2.68% CAGR / Sharpe -0.21 vs random 3.38% / -0.29. V4 is *below* the random mean and comfortably inside the random range [0.40, 5.05]. It does not beat a coin flip. |

## 6. Why it fails — the mechanism, measured not asserted

`V4 top-22 vs pure-126d-momentum top-22, Jaccard overlap: mean 84.5%, median 91.3%`
(`s3_diagnostic.py`).

V4 uses `period=5`, which flags ~90-94% of symbol-days. The %R filter is therefore almost always
**ON**, and the only thing shaping the book is the momentum ranking applied to whatever passes.
V4 is a **momentum book wearing a Williams %R costume**, and it inherits momentum's fate:

```
pure 126d momentum [TRAIN]   17.09%   Sharpe  0.70
pure 126d momentum [TEST]     3.14%   Sharpe -0.18     <- same collapse as V4's 2.68% / -0.21
```

### Raw signal power, portfolio wrapper removed (`s5_raw_edge.py`)

Flagged minus unflagged forward return, annualised, 21-day horizon:

| variant | TRAIN spread | TRAIN t | TEST spread | TEST t | stable? |
|---------|-------------:|--------:|------------:|-------:|---------|
| V1 p14<-80 state   | **-480 bp** | -2.28 | **-181 bp** | +0.63 | negative both — the canonical rule actively *loses* |
| V2 p14<-80 touch21 | +258 bp | +6.91 | **-307 bp** | -0.46 | **sign flip — in-sample mirage** |
| V3 p14<-90 touch21 | +311 bp | +8.12 | **-412 bp** | -1.62 | **sign flip — in-sample mirage** |
| V4 p5<-80 touch21  | -94 bp | +1.29 | **-353 bp** | -0.50 | null |
| V5 p28<-80 touch21 | +168 bp | +6.04 | +213 bp | +4.87 | positive both (see §7) |

At the 5-day horizon every single variant is negative in both windows (-778 to -1510 bp/yr).
This is the cleanest statement of the finding: **buying NIFTY-50 names on a Williams %R
oversold print has destroyed return at every horizon and every parameter setting I tested,
except the slow 28-day version at a 21-day horizon.**

This independently reproduces the prior already recorded in `src/nsealgo/factors/core.py`:
the only multiple-testing-corrected (Romano-Wolf) Indian technical-rule study found
RSI_25_75, RSI_30_70, Bollinger 20/2.0 and Bollinger 20/2.5 **all failed**, with 7 of 8
survivors trend-following. Williams %R is a bounded rescaling of stochastic-%K and sits in
exactly that rejected oscillator family. This study is an independent confirmation on NIFTY-50
daily data, not a surprise.

## 7. Verdict

**Does Williams %R make money on NSE? NO.** It lost out-of-sample to buy-and-hold by
**6.86 pp/yr on CAGR** (2.68% vs 9.54%) and had a **deeper drawdown** (-16.21% vs -13.48%);
it lost to the nsealgo composite by 4.93 pp/yr; and it **failed the negative control**, scoring
below a random signal at identical liveness.

Most likely reason: **Williams %R is a pure mean-reversion oscillator, and Indian NIFTY-50
equities exhibit short-term *continuation*, not reversal.** A signal that buys weakness in a
market that keeps falling buys the knife. The momentum overlay mandated by `AGENT_BRIEF.md` §5
made this worse, not better — it is the wrong cross-sectional construction for a reversal
signal, since ranking "oversold" names by trailing 126d momentum selects the *least-bad* of the
weak rather than the deepest-reverting names, and in V4 it simply deleted the signal (84.5%
overlap with pure momentum).

**The one thing I would try next — named, deliberately NOT run.** V5 (`period=28, lower=-80,
touch-21`) is the only variant whose raw 21-day spread is positive in *both* TRAIN (+168 bp,
t=6.04) and TEST (+213 bp, t=4.87). Its portfolio result was poor (TRAIN 10.24% / Sharpe 0.36)
because the momentum ranking throws away exactly the deep-oversold names that carry the edge.
The correct next experiment is **V5 with a reversal-consistent ranking** — rank flagged names by
short-term 21d return *ascending* (deepest decline first), or simply inverse-vol-weight all
flagged names with no momentum overlay at all. That is a 6th variant, outside my declared
budget, so I am naming it rather than running it. It must be evaluated on a **fresh forward
window**, not on the TEST window I have already looked at.

## 8. Bugs found (the most valuable output)

### B1 — my own random control was biased (found and fixed, `harness.py`)
The first `random_score` assigned every flagged name a constant score of `1.0`.
`build_rebalance_weights` breaks score ties with a **stable sort on `-score`**
(`engine.py:285`), so on every date it kept the 22 flagged names with the **lowest column
index** — an alphabetical subset, not a random one. The control reported 13.3% CAGR when the
true random mean is 11.2%. Fixed by drawing continuous random scores.

### B2 — latent footgun in `nsealgo/backtest/engine.py` (NOT fixed; src is read-only here)
`engine.py:285`, `order = np.argsort(-s_masked, kind="stable")[:k]`. Any score panel with
tied values silently becomes an **alphabetical** portfolio. A binary score (`(sig>0).astype(float)`)
or a z-scored factor with repeated values will pick the first N symbols in panel order, not the
best N. `build_rebalance_weights` should break ties on something meaningful (a secondary
factor, or `rng`-independent symbol hash) or at minimum document that ties are column-ordered.
This is a real trap for any future agent who passes a binary or coarse score.

### B3 — a missing bar poisons a 14-day rolling window entirely
`panel.rolling(period, min_periods=period)` returns NaN if *any* bar in the window is missing
(14,455 NaN high cells in the aligned H/L panels, ~6.5%). One suspension inside the window
disables the signal for up to `period` days. This is conservative — it can only *reduce*
signals, never manufacture them — so it does not invalidate the negative result. Noted so the
next agent does not mistake it for lookahead.

## 9. Reproduce

```bash
.venv/bin/python research/agent_williamsr/s0_indicator_check.py   # indicator fidelity
.venv/bin/python research/agent_williamsr/s1_liveness.py          # provenance, panel, liveness
.venv/bin/python research/agent_williamsr/s2_train.py             # 5 variants on TRAIN
.venv/bin/python research/agent_williamsr/s3_diagnostic.py         # fixed controls, overlap
.venv/bin/python research/agent_williamsr/s4_test.py              # THE TEST RUN
.venv/bin/python research/agent_williamsr/s5_raw_edge.py          # raw signal power
.venv/bin/ruff check research/agent_williamsr/                    # clean
```
Raw console output preserved in `s4_output.txt` and `s5_output.txt`.

Not committed or pushed, per `AGENT_BRIEF.md` §9.