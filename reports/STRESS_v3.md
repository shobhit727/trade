# Gate 4 Robustness Stress Tests — v3 (re-run against the cost-fixed engine)

- **`engine_sha`: `970713f3eecf`** (`nsealgo.backtest.engine`)
- Cost charge now in force: `cost = 2.0 * one_way_turnover * eq * rate` (`src/nsealgo/backtest/engine.py:526`) — the half-cost bug is fixed
- Data: 48 symbols x 4625 daily bars, 2008-01-01 -> 2026-10-01
- Harness: `nsealgo.backtest.walkforward`, 6 folds, 6y train / 2y test, 18-cell grid (`n_positions` x overlay `lookback` x overlay `threshold`) — identical to `research/validate.py`. The engine, cost model, factors, overlay and loader are untouched by this script.
- All-in round trip: **21.92 bps** of total turnover (statutory + 2 x 5 bps slippage), measured on a Rs 1,00,000 per-position notional
- Reproduce: `.venv/bin/python research/stress_tests.py`

## Verdict

**Gate 4 DOES NOT PASS: 5 of 7 checks pass, 2 fail.**

| # | Gate 4 requirement | Result | Evidence |
|---|--------------------|--------|----------|
| 1 | G4.1 survives 2x/3x slippage stress without collapsing | **PASS** | 2x +9.25% / Sharpe 0.30; 3x +8.79% / Sharpe 0.26; alpha -7.41% -> -7.87% |
| 2 | G4.2 survives +/-20% parameter perturbation | **PASS** | 14/14 profitable, CAGR +8.49%..+10.19%, Sharpe 0.23..0.38, 0 sign flip(s) |
| 3 | G4.3 no single year > 35% of total P&L | **FAIL** | max 35.80% (2024) |
| 4 | G4.4 no single stock > 20% of total P&L | **PASS** | max 8.01% (trent) |
| 5 | G4.5 >= 4 of 6 neighbouring settings profitable | **PASS** | 6 of 6, CAGR +8.49%..+9.80% |
| 6 | X   turnover / cost-drag sanity (no engine regression) | **PASS** | 1.9964x/y, 6.1692%/y (targets 1.99x/5.93% moved by loader rule C9, OOS unchanged) |
| 7 | X   negative control (reversal) underperforms | **FAIL** | reversal Sharpe 0.37 vs trend 0.34 |

## 0. Baseline reproduction, turnover and cost-drag sanity check

| Metric | Measured | v3 baseline |
|--------|----------|-------------|
| OOS CAGR | **+9.71%** | 9.71% |
| OOS Sharpe | **0.34** | 0.34 |
| OOS MaxDD | **-14.92%** | -14.92% |
| OOS Calmar | **0.65** | 0.65 |
| Benchmark CAGR / Sharpe / MaxDD | +17.12% / 0.68 / -37.97% | 17.12% / 0.68 / -37.97% |
| Annual turnover | **1.9964x/yr** | ~1.99x |
| Cost drag | **6.1692%/yr** | ~5.93% |
| Average names held | 21.9 | — |

The walk-forward baseline reproduces the v3 measurement **exactly** (same CAGR, Sharpe, MaxDD, Calmar and the same parameters selected in all six folds), so the 2x/3x slippage rows below are genuinely at full strength for the first time.

### The turnover / cost-drag numbers moved, and here is exactly why

The ~1.99x and ~5.93% sanity targets quoted in the brief were measured before loader rule **C9** existed. A concurrent agent added C9 (*drop frozen closes* — a vendor-feed-freeze rule) to `nsealgo/data/loader.py` while this sweep was being written. It removes 539 frozen bars in 3 runs, all inside 2008-01 to 2010-01, in `bajajauto` and `nestleind`. `engine_sha` does **not** cover `loader.py`, so this change is invisible to the engine hash. It was measured both ways rather than assumed away:

| Panel | annual turnover | cost drag | full-panel in-sample CAGR | walk-forward OOS CAGR | OOS Sharpe |
|-------|----------------:|----------:|-------------------------:|-------------------:|-----------:|
| pre-C9 (C9 disabled) | 1.9913x | 5.9297%/yr | +16.63% | +9.71% | 0.3365 |
| current (C9 active) | 1.9964x | 6.1692%/yr | +16.87% | +9.71% | 0.3365 |

- Turning C9 off reproduces the stated sanity targets **exactly** (1.9913x, 5.9297%/yr), which confirms C9 is the sole cause.
- C9 moves the full-panel cost drag by **+0.2395pp/yr** and the full-panel in-sample CAGR by **+0.2410pp**.
- It moves the walk-forward OOS CAGR by **+0.0000pp** — i.e. not at all. The frozen bars sit inside the earliest *training* windows, never in a test window, so nothing reported below depends on whether C9 is in.
- So: **no engine regression.** The direction is *upward* on cost drag, i.e. more conservative, and the headline out-of-sample result is unmoved.

<details><summary>Walk-forward folds (out-of-sample)</summary>

| Fold | Test window | Selected params | CAGR | Sharpe | MaxDD |
|------|-------------|-----------------|------|--------|-------|
| 1 | 2024-10-18 -> 2026-10-01 | n=22, lb=126, thr=0.35 | -0.80% | -0.85 | -10.59% |
| 2 | 2022-10-25 -> 2024-10-17 | n=22, lb=126, thr=0.6 | +28.80% | 1.68 | -7.53% |
| 3 | 2020-11-04 -> 2022-10-24 | n=22, lb=126, thr=0.6 | +13.22% | 0.57 | -11.77% |
| 4 | 2018-11-09 -> 2020-11-03 | n=15, lb=126, thr=0.0 | +1.35% | -0.42 | -14.92% |
| 5 | 2016-11-22 -> 2018-11-07 | n=15, lb=126, thr=0.35 | +13.16% | 0.71 | -11.62% |
| 6 | 2014-11-26 -> 2016-11-21 | n=30, lb=126, thr=0.6 | +5.08% | -0.07 | -11.24% |

</details>

## 1. Gate 4.1 — slippage stress (2x and 3x)

The **entire** walk-forward was re-run — including train-window parameter re-selection — with `CostModel(slippage_bps=...)` at 5 (base), 10 (2x) and 15 (3x). The benchmark is the harness's equal-weight buy-and-hold series; it is numerically identical at every setting because `walk_forward` builds it from the price panel with no cost model. That is the right comparison here and the point is stated below.

| Setting | slippage | OOS CAGR | OOS Sharpe | OOS MaxDD | bench CAGR | bench Sharpe | alpha CAGR | alpha Sharpe |
|---------|---------:|---------:|-----------:|----------:|-----------:|------------:|----------:|------------:|
| 1x (base) | 5 bps | +9.71% | 0.34 | -14.92% | +17.12% | 0.68 | -7.41% | -0.34 |
| 2x | 10 bps | +9.25% | 0.30 | -14.96% | +17.12% | 0.68 | -7.87% | -0.38 |
| 3x | 15 bps | +8.79% | 0.26 | -14.99% | +17.12% | 0.68 | -8.33% | -0.42 |

- Alpha against the benchmark: **-7.41%** at 1x -> **-7.87%** at 2x -> **-8.33%** at 3x
- Gross CAGR falls +0.46pp at 2x and +0.91pp at 3x
- "Without collapsing" is read as: **CAGR and Sharpe both stay positive** at 2x and 3x. The book is never made to lose money by assuming worse fills.
- A buy-and-hold book pays one round trip in 19 years, so raising slippage moves the benchmark by well under 0.1%/yr; the relative (alpha) columns are the meaningful ones and they are **negative at every setting**.

## 2. Gate 4.2 — +/-20% parameter perturbation

One parameter moved at a time, everything else held, full walk-forward re-run so re-selection still happens. Factor lookbacks are exposed through a parameterised rebuild of `build_composite_score` from the same exported primitives; that rebuild is asserted **bit-identical** to the stock composite at the base values, so the base row is the production composite. The overlay's `lookback` and `threshold` are *selected from* the grid rather than fixed, so a +/-20% perturbation of them scales that axis of the grid.

| Perturbation | OOS CAGR | OOS Sharpe | OOS MaxDD | vs base CAGR |
|--------------|---------:|-----------:|----------:|-------------:|
| mom_long 244->195 (-20%) | +10.14% | 0.38 | -14.92% | +0.43% |
| mom_long 244->293 (+20%) | +9.31% | 0.30 | -17.41% | -0.40% |
| mom_skip 21->17 (-20%) | +10.19% | 0.37 | -17.85% | +0.48% |
| mom_skip 21->25 (+20%) | +9.64% | 0.33 | -15.84% | -0.07% |
| mom_6m 126->101 (-20%) | +9.80% | 0.34 | -17.51% | +0.10% |
| mom_6m 126->151 (+20%) | +9.75% | 0.34 | -16.05% | +0.04% |
| trend_lb 200->160 (-20%) | +8.67% | 0.25 | -15.82% | -1.03% |
| trend_lb 200->240 (+20%) | +9.76% | 0.34 | -14.92% | +0.05% |
| vol_lb 60->48 (-20%) | +8.90% | 0.26 | -14.92% | -0.81% |
| vol_lb 60->72 (+20%) | +9.38% | 0.31 | -14.92% | -0.33% |
| overlay lookback x0.80 (-20%) | +8.49% | 0.23 | -21.94% | -1.22% |
| overlay lookback x1.20 (+20%) | +9.11% | 0.28 | -18.20% | -0.60% |
| overlay threshold x0.80 (-20%) | +9.82% | 0.35 | -14.92% | +0.11% |
| overlay threshold x1.20 (+20%) | +9.71% | 0.33 | -14.92% | -0.00% |

- CAGR spread: **+8.49% .. +10.19%** (range +1.70%)
- Sharpe spread: **0.23 .. 0.38** (range 0.15)
- Baseline is +9.71% / 0.34; **0 of 14** perturbations flip the sign of CAGR; **14 of 14** are profitable at all.

> **Source observation, not a change made here:** the docstring of `momentum_12_1` says *"252d return"* but the code uses `core.TRADING_DAYS = 244`. This run perturbs from the **code** value (244) so the base row is bit-identical to production. Worth reconciling in a later change; it is not fixed here because this run owns no source file.

## 3. Gate 4.3 — no single year contributes > 35% of total P&L

Measured on the compounding OOS equity curve: `contribution_y = (E_y - E_{y-1}) / (E_final - 1)`. These sum exactly to 100%, and a losing year correctly shows a negative share. The log-return share is a cross-check.

| Year | P&L (equity units) | share of total P&L | calendar return | log share |
|------|-------------------:|-------------------:|---------------:|----------:|
| 2014 | +0.0025 | +0.12% | +0.25% | +0.22% |
| 2015 | +0.0300 | +1.47% | +2.99% | +2.65% |
| 2016 | +0.0769 | +3.77% | +7.45% | +6.46% |
| 2017 | +0.3245 | +15.91% | +29.25% | +23.08% |
| 2018 | -0.0076 | -0.37% | -0.53% | -0.48% |
| 2019 | +0.1505 | +7.38% | +10.55% | +9.02% |
| 2020 | -0.1187 | -5.82% | -7.53% | -7.04% |
| 2021 | +0.3094 | +15.17% | +21.22% | +17.31% |
| 2022 | +0.0738 | +3.62% | +4.17% | +3.68% |
| 2023 | +0.5267 | +25.83% | +28.61% | +22.63% |
| 2024 | +0.7301 | +35.80% | +30.83% | +24.17% |
| 2025 | +0.2466 | +12.09% | +7.96% | +6.89% |
| 2026 | -0.3052 | -14.97% | -9.13% | -8.61% |

**Max single-year share: 35.80% (2024)** against a gate of 35.00%.

## 4. Gate 4.4 — no single stock contributes > 20% of total P&L

Out-of-sample only. For each fold the backtest is re-run on the **test** window with that fold's train-selected parameters. Each day's gross book return is attributed by held weight and each day's cost charge is split across stocks by that stock's share of the day's `|dW|`. The engine's own compounding equity loop is replayed to recover the per-date charge and is **asserted against `BacktestResult.costs_paid`**; the resulting per-stock daily series reconcile to the engine's daily returns to within **3.1e-16**. The regime overlay is then applied to every leg, and the cash leg is reported separately, so the parts sum back to the OOS P&L.

Total net stock P&L **+1.0357** normalised equity units; cash leg (overlay idle time in T-bills) **+0.1420**.

**Top 5 contributors**

| # | symbol | net P&L | share of net | share of gross | cost charged |
|--:|--------|--------:|-------------:|---------------:|-------------:|
| 1 | trent | +0.0830 | 8.01% | 7.39% | 0.0017 |
| 2 | powergrid | +0.0558 | 5.39% | 5.07% | 0.0022 |
| 3 | bel | +0.0558 | 5.38% | 5.05% | 0.0020 |
| 4 | hdfcbank | +0.0474 | 4.58% | 4.32% | 0.0021 |
| 5 | titan | +0.0473 | 4.57% | 4.39% | 0.0030 |

- Top 5 combined share of net P&L: **27.93%**
- **Max single-stock share: 8.01% (trent)** against a gate of 20.00%
- 40 of 48 names contributed positive net P&L; the rest lost money

Bottom 3 by net P&L:

| symbol | net P&L | share of net |
|--------|--------:|-------------:|
| wipro | -0.0161 | -1.56% |
| cipla | -0.0173 | -1.67% |
| icicibank | -0.0190 | -1.84% |

## 5. Gate 4.5 — at least 4 of 6 neighbouring settings profitable

**Definition of "neighbouring"** (stated because the gate requires it): a single-axis **+/-20%** shift of one of the three lookback knobs that define the operating point, every other parameter held at its value, with the standard walk-forward re-selection left switched **on** — so every neighbour is an honest end-to-end out-of-sample number, not a fixed-fit one. The six are the two factor lookbacks the composite is most sensitive to (`momentum_6m`, `trend_strength_200d`) plus the overlay lookback, each at +/-20%. Profitability is **net of the full cost stack**.

| # | neighbour | OOS CAGR (net) | OOS Sharpe | OOS MaxDD |
|--:|-----------|----------------:|-----------:|----------:|
| 1 | mom_6m 126->101 (-20%) | +9.80% | 0.34 | -17.51% |
| 2 | mom_6m 126->151 (+20%) | +9.75% | 0.34 | -16.05% |
| 3 | trend_lb 200->160 (-20%) | +8.67% | 0.25 | -15.82% |
| 4 | trend_lb 200->240 (+20%) | +9.76% | 0.34 | -14.92% |
| 5 | overlay lookback x0.80 (-20%) | +8.49% | 0.23 | -21.94% |
| 6 | overlay lookback x1.20 (+20%) | +9.11% | 0.28 | -18.20% |

**Profitable: 6 of 6** against a gate of >= 4 of 6. CAGR range across neighbours: +8.49% .. +9.80%.

### Supplementary — the full grid, FIXED parameters, no train selection

The same 18 cells `walk_forward` chooses between, each evaluated on the fold test windows with **no per-fold re-fitting**. This is the cleanest available read on whether the result is a property of the signal or of the search, and it is reported whether or not it flatters the strategy.

| n_positions | overlay lookback | threshold | OOS CAGR | OOS Sharpe | OOS MaxDD |
|------------:|-----------------:|----------:|---------:|-----------:|----------:|
| 15 | 126 | 0.00 | +9.28% | 0.30 | -14.92% |
| 15 | 126 | 0.35 | +9.36% | 0.30 | -21.47% |
| 15 | 126 | 0.60 | +9.35% | 0.29 | -26.11% |
| 15 | 252 | 0.00 | +8.02% | 0.19 | -17.80% |
| 15 | 252 | 0.35 | +8.53% | 0.23 | -21.57% |
| 15 | 252 | 0.60 | +8.83% | 0.24 | -26.11% |
| 22 | 126 | 0.00 | +10.43% | 0.41 | -16.15% |
| 22 | 126 | 0.35 | +11.01% | 0.45 | -22.11% |
| 22 | 126 | 0.60 | +11.36% | 0.45 | -26.35% |
| 22 | 252 | 0.00 | +9.47% | 0.31 | -17.01% |
| 22 | 252 | 0.35 | +10.37% | 0.38 | -22.11% |
| 22 | 252 | 0.60 | +10.96% | 0.41 | -26.35% |
| 30 | 126 | 0.00 | +10.09% | 0.38 | -17.87% |
| 30 | 126 | 0.35 | +10.70% | 0.42 | -23.80% |
| 30 | 126 | 0.60 | +11.08% | 0.43 | -28.01% |
| 30 | 252 | 0.00 | +8.84% | 0.26 | -17.87% |
| 30 | 252 | 0.35 | +9.88% | 0.35 | -23.80% |
| 30 | 252 | 0.60 | +10.56% | 0.39 | -28.01% |

- Profitable cells: **18 of 18**
- CAGR range **+8.02% .. +11.36%**, Sharpe range **0.19 .. 0.45**
- The train-selected baseline is **+9.71% / 0.34**. Where it lands inside that unselected spread is the tell: a search that only works when it is allowed to re-fit shows a selected number far above its own neighbourhood.

## 6. Negative control

`NEGATIVE_CONTROL_WEIGHTS` (45% `reversal_5d`, 30% `reversal_20d`, 25% `low_volatility`) through the **same** walk-forward harness and the same cost stack. It must underperform the trend composite; if it does not, the harness is mining noise, and that would be the single most important finding on this page.

| composite | OOS CAGR | OOS Sharpe | OOS MaxDD |
|-----------|---------:|-----------:|----------:|
| trend (production) | +9.71% | 0.34 | -14.92% |
| reversal (control) | +10.04% | 0.37 | -25.05% |

**Control underperforms on both CAGR and Sharpe: FAIL.**

### This is the most important line in this report

`reversal_5d` and `reversal_20d` are short-term reversal factors. The factor module's own literature review (`src/nsealgo/factors/core.py`) concludes, from two methodologically disjoint Indian studies plus the only multiple-testing-corrected one, that **reversal does not work in Indian cash equities and trend does** — the exact opposite of what the backtest produced. A composite built *entirely* from those two rejected factors returned a higher out-of-sample CAGR (+10.04% vs +9.71%) and a higher Sharpe (0.37 vs 0.34) than the production trend composite, net of the full cost stack.

Read together with the supplementary grid in §5 — where **all 18 of 18** parameter cells are profitable with a CAGR range of +8.02% to +11.36% — the picture is that almost anything built from this factor set on this universe returns a positive out-of-sample result. That is the signature of a long-only, equity-beta-tilted book in a market that rose, plus the low-volatility weight common to *both* composites, not of a validated signal. The Sharpe differences being tested here (0.34 vs 0.37) are well inside the noise of a Sharpe estimated from ~2,900 daily observations.

Per `GOAL.md` §6, this is the finding that invalidates the others: a strategy whose negative control does not fail cannot be certified by robustness tests that it passes. The four Gate 4 checks it *does* pass (slippage, parameter perturbation, per-stock concentration, neighbouring settings) are consistent with a book that holds 22 NIFTY-50 names with a mild quality tilt and keeps turning over monthly — and such a book would pass all four of them whatever the signal was worth.

## 7. Plain-English verdict

1. **G4.1 survives 2x/3x slippage stress without collapsing** — PASS. 2x +9.25% / Sharpe 0.30; 3x +8.79% / Sharpe 0.26; alpha -7.41% -> -7.87%.
2. **G4.2 survives +/-20% parameter perturbation** — PASS. 14/14 profitable, CAGR +8.49%..+10.19%, Sharpe 0.23..0.38, 0 sign flip(s).
3. **G4.3 no single year > 35% of total P&L** — **FAIL**. max 35.80% (2024).
4. **G4.4 no single stock > 20% of total P&L** — PASS. max 8.01% (trent).
5. **G4.5 >= 4 of 6 neighbouring settings profitable** — PASS. 6 of 6, CAGR +8.49%..+9.80%.
6. **X   turnover / cost-drag sanity (no engine regression)** — PASS. 1.9964x/y, 6.1692%/y (targets 1.99x/5.93% moved by loader rule C9, OOS unchanged).
7. **X   negative control (reversal) underperforms** — **FAIL**. reversal Sharpe 0.37 vs trend 0.34.

**Overall: Gate 4 DOES NOT PASS (2 of 7 checks fail).**

The failures, stated plainly:

- **G4.3 no single year > 35% of total P&L** — max 35.80% (2024).
- **X   negative control (reversal) underperforms** — reversal Sharpe 0.37 vs trend 0.34.

> **Read the failures together, not separately.** The two failures are not independent. The negative control failing means the harness cannot distinguish the trend composite from a composite of factors the project has already ruled out on published Indian evidence. In that light, the yearly-concentration failure (2024 alone carries 35.80% of total P&L) is what a result driven by market beta rather than signal looks like: one strong calendar year does most of the work. The four passes are not evidence against this reading — a 22-name, monthly-rebalanced, mildly quality-tilted book passes slippage, parameter, per-stock and neighbour stress regardless of whether it has an edge.
>
> **This does not say the strategy has no edge.** It says the evidence collected here cannot demonstrate one. `GOAL.md` §5's default verdict applies: keep researching, do not loosen the gate, do not deploy.

---

*Produced by `research/stress_tests.py` against engine `engine_sha 970713f3eecf`. Any result from this system must be quoted with its end date; the OOS window here ends 2026-10-01. Survivorship bias is present (today's NIFTY-50 backfilled) and is disclosed in every report in this repo. `GOAL.md` §6 anti-fraud rules apply: no in-sample number is presented as a result, and no cost was reduced to rescue anything.*
