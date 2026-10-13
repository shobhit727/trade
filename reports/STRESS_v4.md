# Gate 4 Robustness Stress Tests — v4 (re-run on the tie-break-fixed engine)

- **`engine_sha`: `29764f562cd5`** (`nsealgo.backtest.engine`)
- **loader `c1badf5f7df8` · costs `ba350aef75b3` · panel `389b082b832f`**
- Cost charge: `cost = 2.0 * one_way_turnover * eq * rate` — the half-cost bug fixed in v3 is still fixed, unchanged here
- All-in round trip: **21.92 bps** of total turnover (statutory + 2 x 5 bps slippage), measured on a Rs 1,00,000 per-position notional
- Data: 48 symbols x 4625 daily bars, 2008-01-01 -> 2026-10-01
- Harness: `nsealgo.backtest.walkforward`, 6 folds, 6y train / 2y test, 18-cell grid — identical to `research/validate.py` and to v3. The engine, cost model, factors, overlay and loader are untouched *by this script*; the engine itself changed once, between v3 and v4, and that change is the subject of this report.
- Reproduce: `.venv/bin/python -m research.revalidate_v2.run_stress && .venv/bin/python -m research.revalidate_v2.report_stress`

## Verdict

**Gate 4 DOES NOT PASS: 5 of 7 checks pass, 2 fail.**

| # | Gate 4 requirement | v3 | v4 | Evidence |
|---|--------------------|----|----|----------|
| 1 | G4.1 survives 2x/3x slippage stress without collapsing | **PASS** | **PASS** | 2x +9.07% / 0.28; 3x +8.62% / 0.24; alpha -7.60% -> -8.50% |
| 2 | G4.2 survives +/-20% parameter perturbation | **PASS** | **PASS** | 14/14 profitable, CAGR +8.40%..+10.32%, Sharpe 0.22..0.39, 0 sign flip(s) |
| 3 | G4.3 no single year > 35% of total P&L | **FAIL** | **FAIL** | max 36.03% (2024) |
| 4 | G4.4 no single stock > 20% of total P&L | **PASS** | **PASS** | max 8.20% (trent) |
| 5 | G4.5 >= 4 of 6 neighbouring settings profitable | **PASS** | **PASS** | 6 of 6, CAGR +8.40%..+10.32% |
| 6 | X   turnover / cost-drag sanity (no engine regression) | **PASS** | **PASS** | 1.9910x/y, 6.0137%/y; loader C9's own contribution +0.2395pp (v3) -> +0.2335pp (v4), 21.92 bps unchanged |
| 7 | X   negative control (reversal) underperforms | **FAIL** | **FAIL** | reversal Sharpe 0.37 vs trend 0.32; CAGR +10.05% vs +9.52% |

> **The gate table did not change: same 5 pass, same 2 fail.** A tie-break fix that flipped a gate verdict would be a finding; one that does not is the expected result and is stated rather than implied.

## Diff table vs v3 — every number that moved

**127 of 194 quantities moved.** Rows marked `unchanged` are equal to v3 at the precision v3 was printed at (2dp on rates, 1dp on name counts) — `research/stress_tests.py` keeps no result cache, so the v3 column is transcribed from `reports/STRESS_v3.md` and a finer comparison is not a measurement. The `loader`, `costs` and `panel` SHAs are all identical, so nothing that does not route through `build_rebalance_weights` could move.

| section | quantity | v3 (`d93815344bd3`) | v4 (`29764f562cd5`) | delta | status | note |
|---------|----------|------------------:|------------------:|------:|--------|------|
| baseline | baseline cagr | +9.71% | +9.52% | -0.19pp | **moved** |  |
| baseline | baseline sharpe | 0.34 | 0.32 | -0.0198 | **moved** |  |
| baseline | baseline maxdd | -14.92% | -14.92% | — | unchanged |  |
| baseline | baseline calmar | 0.65 | 0.64 | -0.0117 | **moved** |  |
| baseline | baseline bm_cagr | +17.12% | +17.12% | — | unchanged | benchmark unchanged: panel SHA identical |
| baseline | baseline bm_sharpe | 0.68 | 0.68 | — | unchanged | benchmark unchanged: panel SHA identical |
| baseline | baseline bm_maxdd | -37.97% | -37.97% | — | unchanged | benchmark unchanged: panel SHA identical |
| sanity | annual turnover (x/yr) | 1.9964x | 1.9910x | -0.0054x | **moved** |  |
| sanity | cost drag (%/yr) | +6.1692% | +6.0137% | -0.1555pp | **moved** |  |
| sanity | avg names held | 21.9 | 21.9 | — | unchanged | tie-break changes *which* names, not how many |
| sanity | all-in round trip (bps) | 21.92 | 21.92 | — | unchanged | costs SHA unchanged |
| folds | fold 1 selected params | n22 lb126 thr0.35 | n22 lb126 thr0.35 | — | unchanged |  |
| folds | fold 1 OOS CAGR | -0.80% | -0.68% | +0.12pp | **moved** |  |
| folds | fold 1 OOS Sharpe | -0.85 | -0.83 | +0.0219 | **moved** |  |
| folds | fold 1 OOS MaxDD | -10.59% | -10.46% | +0.13pp | **moved** |  |
| folds | fold 2 selected params | n22 lb126 thr0.6 | n22 lb252 thr0.6 | — | **moved** | **argmax flipped** |
| folds | fold 2 OOS CAGR | +28.80% | +29.37% | +0.57pp | **moved** |  |
| folds | fold 2 OOS Sharpe | 1.68 | 1.73 | +0.0508 | **moved** |  |
| folds | fold 2 OOS MaxDD | -7.53% | -7.53% | — | unchanged |  |
| folds | fold 3 selected params | n22 lb126 thr0.6 | n22 lb126 thr0.6 | — | unchanged |  |
| folds | fold 3 OOS CAGR | +13.22% | +12.63% | -0.59pp | **moved** |  |
| folds | fold 3 OOS Sharpe | 0.57 | 0.52 | -0.0507 | **moved** |  |
| folds | fold 3 OOS MaxDD | -11.77% | -11.77% | — | unchanged |  |
| folds | fold 4 selected params | n15 lb126 thr0.0 | n15 lb126 thr0.0 | — | unchanged |  |
| folds | fold 4 OOS CAGR | +1.35% | +1.13% | -0.22pp | **moved** |  |
| folds | fold 4 OOS Sharpe | -0.42 | -0.44 | -0.0234 | **moved** |  |
| folds | fold 4 OOS MaxDD | -14.92% | -14.92% | — | unchanged |  |
| folds | fold 5 selected params | n15 lb126 thr0.35 | n15 lb126 thr0.35 | — | unchanged |  |
| folds | fold 5 OOS CAGR | +13.16% | +12.65% | -0.51pp | **moved** |  |
| folds | fold 5 OOS Sharpe | 0.71 | 0.66 | -0.0506 | **moved** |  |
| folds | fold 5 OOS MaxDD | -11.62% | -11.62% | — | unchanged |  |
| folds | fold 6 selected params | n30 lb126 thr0.6 | n30 lb126 thr0.6 | — | unchanged |  |
| folds | fold 6 OOS CAGR | +5.08% | +4.69% | -0.39pp | **moved** |  |
| folds | fold 6 OOS Sharpe | -0.07 | -0.11 | -0.0372 | **moved** |  |
| folds | fold 6 OOS MaxDD | -11.24% | -11.24% | — | unchanged |  |

### G4.1 — 2x / 3x slippage

| G4.1 slippage | 1x (5bps) CAGR | +9.71% | +9.52% | -0.19pp | **moved** |  |
| G4.1 slippage | 1x (5bps) Sharpe | 0.34 | 0.32 | -0.0198 | **moved** |  |
| G4.1 slippage | 1x (5bps) MaxDD | -14.92% | -14.92% | — | unchanged |  |
| G4.1 slippage | 2x (10bps) CAGR | +9.25% | +9.07% | -0.18pp | **moved** |  |
| G4.1 slippage | 2x (10bps) Sharpe | 0.30 | 0.28 | -0.0195 | **moved** |  |
| G4.1 slippage | 2x (10bps) MaxDD | -14.96% | -14.96% | — | unchanged |  |
| G4.1 slippage | 3x (15bps) CAGR | +8.79% | +8.62% | -0.17pp | **moved** |  |
| G4.1 slippage | 3x (15bps) Sharpe | 0.26 | 0.24 | -0.0193 | **moved** |  |
| G4.1 slippage | 3x (15bps) MaxDD | -14.99% | -14.99% | — | unchanged |  |
| G4.1 slippage | 1x alpha CAGR vs benchmark | -7.41% | -7.60% | -0.19pp | **moved** |  |
| G4.1 slippage | 2x alpha CAGR vs benchmark | -7.87% | -8.05% | -0.18pp | **moved** |  |
| G4.1 slippage | 3x alpha CAGR vs benchmark | -8.33% | -8.50% | -0.17pp | **moved** |  |

### G4.2 — +/-20% parameter perturbation

| G4.2 perturbation | mom_long 244->195 (-20%) CAGR | +10.14% | +9.87% | -0.27pp | **moved** |  |
| G4.2 perturbation | mom_long 244->195 (-20%) Sharpe | 0.38 | 0.36 | -0.0248 | **moved** |  |
| G4.2 perturbation | mom_long 244->195 (-20%) MaxDD | -14.92% | -14.92% | — | unchanged |  |
| G4.2 perturbation | mom_long 244->293 (+20%) CAGR | +9.31% | +9.30% | -0.01pp | **moved** |  |
| G4.2 perturbation | mom_long 244->293 (+20%) Sharpe | 0.30 | 0.30 | — | unchanged |  |
| G4.2 perturbation | mom_long 244->293 (+20%) MaxDD | -17.41% | -17.41% | — | unchanged |  |
| G4.2 perturbation | mom_skip 21->17 (-20%) CAGR | +10.19% | +10.08% | -0.11pp | **moved** |  |
| G4.2 perturbation | mom_skip 21->17 (-20%) Sharpe | 0.37 | 0.36 | -0.0054 | **moved** |  |
| G4.2 perturbation | mom_skip 21->17 (-20%) MaxDD | -17.85% | -17.85% | — | unchanged |  |
| G4.2 perturbation | mom_skip 21->25 (+20%) CAGR | +9.64% | +9.42% | -0.22pp | **moved** |  |
| G4.2 perturbation | mom_skip 21->25 (+20%) Sharpe | 0.33 | 0.31 | -0.0177 | **moved** |  |
| G4.2 perturbation | mom_skip 21->25 (+20%) MaxDD | -15.84% | -15.84% | — | unchanged |  |
| G4.2 perturbation | mom_6m 126->101 (-20%) CAGR | +9.80% | +9.90% | +0.10pp | **moved** |  |
| G4.2 perturbation | mom_6m 126->101 (-20%) Sharpe | 0.34 | 0.35 | +0.0127 | **moved** |  |
| G4.2 perturbation | mom_6m 126->101 (-20%) MaxDD | -17.51% | -17.51% | — | unchanged |  |
| G4.2 perturbation | mom_6m 126->151 (+20%) CAGR | +9.75% | +10.32% | +0.57pp | **moved** |  |
| G4.2 perturbation | mom_6m 126->151 (+20%) Sharpe | 0.34 | 0.39 | +0.0464 | **moved** |  |
| G4.2 perturbation | mom_6m 126->151 (+20%) MaxDD | -16.05% | -16.05% | — | unchanged |  |
| G4.2 perturbation | trend_lb 200->160 (-20%) CAGR | +8.67% | +8.40% | -0.27pp | **moved** |  |
| G4.2 perturbation | trend_lb 200->160 (-20%) Sharpe | 0.25 | 0.22 | -0.0273 | **moved** |  |
| G4.2 perturbation | trend_lb 200->160 (-20%) MaxDD | -15.82% | -15.82% | — | unchanged |  |
| G4.2 perturbation | trend_lb 200->240 (+20%) CAGR | +9.76% | +9.48% | -0.28pp | **moved** |  |
| G4.2 perturbation | trend_lb 200->240 (+20%) Sharpe | 0.34 | 0.32 | -0.0241 | **moved** |  |
| G4.2 perturbation | trend_lb 200->240 (+20%) MaxDD | -14.92% | -14.92% | — | unchanged |  |
| G4.2 perturbation | vol_lb 60->48 (-20%) CAGR | +8.90% | +8.84% | -0.06pp | **moved** |  |
| G4.2 perturbation | vol_lb 60->48 (-20%) Sharpe | 0.26 | 0.26 | — | unchanged |  |
| G4.2 perturbation | vol_lb 60->48 (-20%) MaxDD | -14.92% | -14.92% | — | unchanged |  |
| G4.2 perturbation | vol_lb 60->72 (+20%) CAGR | +9.38% | +9.28% | -0.10pp | **moved** |  |
| G4.2 perturbation | vol_lb 60->72 (+20%) Sharpe | 0.31 | 0.30 | -0.0104 | **moved** |  |
| G4.2 perturbation | vol_lb 60->72 (+20%) MaxDD | -14.92% | -14.92% | — | unchanged |  |
| G4.2 perturbation | overlay lookback x0.80 (-20%) CAGR | +8.49% | +9.12% | +0.63pp | **moved** |  |
| G4.2 perturbation | overlay lookback x0.80 (-20%) Sharpe | 0.23 | 0.28 | +0.0525 | **moved** |  |
| G4.2 perturbation | overlay lookback x0.80 (-20%) MaxDD | -21.94% | -17.02% | +4.92pp | **moved** |  |
| G4.2 perturbation | overlay lookback x1.20 (+20%) CAGR | +9.11% | +9.01% | -0.10pp | **moved** |  |
| G4.2 perturbation | overlay lookback x1.20 (+20%) Sharpe | 0.28 | 0.28 | — | unchanged |  |
| G4.2 perturbation | overlay lookback x1.20 (+20%) MaxDD | -18.20% | -14.46% | +3.74pp | **moved** |  |
| G4.2 perturbation | overlay threshold x0.80 (-20%) CAGR | +9.82% | +9.68% | -0.14pp | **moved** |  |
| G4.2 perturbation | overlay threshold x0.80 (-20%) Sharpe | 0.35 | 0.34 | -0.0133 | **moved** |  |
| G4.2 perturbation | overlay threshold x0.80 (-20%) MaxDD | -14.92% | -14.92% | — | unchanged |  |
| G4.2 perturbation | overlay threshold x1.20 (+20%) CAGR | +9.71% | +9.44% | -0.27pp | **moved** |  |
| G4.2 perturbation | overlay threshold x1.20 (+20%) Sharpe | 0.33 | 0.31 | -0.0209 | **moved** |  |
| G4.2 perturbation | overlay threshold x1.20 (+20%) MaxDD | -14.92% | -14.92% | — | unchanged |  |

### G4.3 — yearly P&L concentration

| G4.3 yearly | 2014 share of total P&L | +0.12% | +0.13% | +0.01pp | **moved** |  |
| G4.3 yearly | 2015 share of total P&L | +1.47% | +1.13% | -0.34pp | **moved** |  |
| G4.3 yearly | 2016 share of total P&L | +3.77% | +3.86% | +0.09pp | **moved** |  |
| G4.3 yearly | 2017 share of total P&L | +15.91% | +15.63% | -0.28pp | **moved** |  |
| G4.3 yearly | 2018 share of total P&L | -0.37% | -0.38% | -0.01pp | **moved** |  |
| G4.3 yearly | 2019 share of total P&L | +7.38% | +7.13% | -0.25pp | **moved** |  |
| G4.3 yearly | 2020 share of total P&L | -5.82% | -5.87% | -0.05pp | **moved** |  |
| G4.3 yearly | 2021 share of total P&L | +15.17% | +14.41% | -0.76pp | **moved** |  |
| G4.3 yearly | 2022 share of total P&L | +3.62% | +3.78% | +0.16pp | **moved** |  |
| G4.3 yearly | 2023 share of total P&L | +25.83% | +26.65% | +0.82pp | **moved** |  |
| G4.3 yearly | 2024 share of total P&L | +35.80% | +36.03% | +0.23pp | **moved** |  |
| G4.3 yearly | 2025 share of total P&L | +12.09% | +12.39% | +0.30pp | **moved** |  |
| G4.3 yearly | 2026 share of total P&L | -14.97% | -14.88% | +0.09pp | **moved** |  |
| G4.3 yearly | max single-year share | +35.80% | +36.03% | +0.23pp | **moved** |  |
| G4.3 yearly | year carrying the most P&L | 2024 | 2024 | — | unchanged |  |

### G4.4 — per-stock P&L concentration

| G4.4 per-stock | max single-stock share | +8.01% | +8.20% | +0.19pp | **moved** |  |
| G4.4 per-stock | name carrying the most P&L | trent | trent | — | unchanged |  |
| G4.4 per-stock | top-5 share of net P&L | +27.93% | +27.51% | -0.42pp | **moved** |  |
| G4.4 per-stock | total net stock P&L | 1.04 | 1.01 | -0.0224 | **moved** |  |
| G4.4 per-stock | cash leg (overlay idle time) | 0.14 | 0.14 | — | unchanged |  |
| G4.4 per-stock | v3-top5 trent share of net | +8.01% | +8.20% | +0.19pp | **moved** | v3 names its own top-5; this row compares the same symbol |
| G4.4 per-stock | v3-top5 powergrid share of net | +5.39% | +5.29% | -0.10pp | **moved** | v3 names its own top-5; this row compares the same symbol |
| G4.4 per-stock | v3-top5 bel share of net | +5.38% | +5.26% | -0.12pp | **moved** | v3 names its own top-5; this row compares the same symbol |
| G4.4 per-stock | v3-top5 titan share of net | +4.57% | +4.44% | -0.13pp | **moved** | v3 names its own top-5; this row compares the same symbol |
| G4.4 per-stock | v3-top5 hdfcbank share of net | +4.58% | +4.31% | -0.27pp | **moved** | v3 names its own top-5; this row compares the same symbol |

### G4.5 — neighbouring settings

| G4.5 neighbours | mom_6m 126->101 (-20%) CAGR | +9.80% | +9.90% | +0.10pp | **moved** |  |
| G4.5 neighbours | mom_6m 126->101 (-20%) Sharpe | 0.34 | 0.35 | +0.0127 | **moved** |  |
| G4.5 neighbours | mom_6m 126->101 (-20%) MaxDD | -17.51% | -17.51% | — | unchanged |  |
| G4.5 neighbours | mom_6m 126->151 (+20%) CAGR | +9.75% | +10.32% | +0.57pp | **moved** |  |
| G4.5 neighbours | mom_6m 126->151 (+20%) Sharpe | 0.34 | 0.39 | +0.0464 | **moved** |  |
| G4.5 neighbours | mom_6m 126->151 (+20%) MaxDD | -16.05% | -16.05% | — | unchanged |  |
| G4.5 neighbours | trend_lb 200->160 (-20%) CAGR | +8.67% | +8.40% | -0.27pp | **moved** |  |
| G4.5 neighbours | trend_lb 200->160 (-20%) Sharpe | 0.25 | 0.22 | -0.0273 | **moved** |  |
| G4.5 neighbours | trend_lb 200->160 (-20%) MaxDD | -15.82% | -15.82% | — | unchanged |  |
| G4.5 neighbours | trend_lb 200->240 (+20%) CAGR | +9.76% | +9.48% | -0.28pp | **moved** |  |
| G4.5 neighbours | trend_lb 200->240 (+20%) Sharpe | 0.34 | 0.32 | -0.0241 | **moved** |  |
| G4.5 neighbours | trend_lb 200->240 (+20%) MaxDD | -14.92% | -14.92% | — | unchanged |  |
| G4.5 neighbours | overlay lookback x0.80 (-20%) CAGR | +8.49% | +9.12% | +0.63pp | **moved** |  |
| G4.5 neighbours | overlay lookback x0.80 (-20%) Sharpe | 0.23 | 0.28 | +0.0525 | **moved** |  |
| G4.5 neighbours | overlay lookback x0.80 (-20%) MaxDD | -21.94% | -17.02% | +4.92pp | **moved** |  |
| G4.5 neighbours | overlay lookback x1.20 (+20%) CAGR | +9.11% | +9.01% | -0.10pp | **moved** |  |
| G4.5 neighbours | overlay lookback x1.20 (+20%) Sharpe | 0.28 | 0.28 | — | unchanged |  |
| G4.5 neighbours | overlay lookback x1.20 (+20%) MaxDD | -18.20% | -14.46% | +3.74pp | **moved** |  |

### Supplementary fixed-parameter grid (18 cells, no train selection)

| fixed grid | cell n15 lb126 thr0.00 CAGR | +9.28% | +9.23% | -0.05pp | **moved** |  |
| fixed grid | cell n15 lb126 thr0.00 Sharpe | 0.30 | 0.30 | — | unchanged |  |
| fixed grid | cell n15 lb126 thr0.00 MaxDD | -14.92% | -14.92% | — | unchanged |  |
| fixed grid | cell n15 lb126 thr0.35 CAGR | +9.36% | +9.28% | -0.08pp | **moved** |  |
| fixed grid | cell n15 lb126 thr0.35 Sharpe | 0.30 | 0.29 | -0.0059 | **moved** |  |
| fixed grid | cell n15 lb126 thr0.35 MaxDD | -21.47% | -21.47% | — | unchanged |  |
| fixed grid | cell n15 lb126 thr0.60 CAGR | +9.35% | +9.24% | -0.11pp | **moved** |  |
| fixed grid | cell n15 lb126 thr0.60 Sharpe | 0.29 | 0.28 | -0.0117 | **moved** |  |
| fixed grid | cell n15 lb126 thr0.60 MaxDD | -26.11% | -26.11% | — | unchanged |  |
| fixed grid | cell n15 lb252 thr0.00 CAGR | +8.02% | +7.94% | -0.08pp | **moved** |  |
| fixed grid | cell n15 lb252 thr0.00 Sharpe | 0.19 | 0.18 | -0.0106 | **moved** |  |
| fixed grid | cell n15 lb252 thr0.00 MaxDD | -17.80% | -17.80% | — | unchanged |  |
| fixed grid | cell n15 lb252 thr0.35 CAGR | +8.53% | +8.42% | -0.11pp | **moved** |  |
| fixed grid | cell n15 lb252 thr0.35 Sharpe | 0.23 | 0.22 | -0.0128 | **moved** |  |
| fixed grid | cell n15 lb252 thr0.35 MaxDD | -21.57% | -21.97% | -0.40pp | **moved** |  |
| fixed grid | cell n15 lb252 thr0.60 CAGR | +8.83% | +8.71% | -0.12pp | **moved** |  |
| fixed grid | cell n15 lb252 thr0.60 Sharpe | 0.24 | 0.23 | -0.0063 | **moved** |  |
| fixed grid | cell n15 lb252 thr0.60 MaxDD | -26.11% | -26.50% | -0.39pp | **moved** |  |
| fixed grid | cell n22 lb126 thr0.00 CAGR | +10.43% | +10.45% | +0.02pp | **moved** |  |
| fixed grid | cell n22 lb126 thr0.00 Sharpe | 0.41 | 0.41 | — | unchanged |  |
| fixed grid | cell n22 lb126 thr0.00 MaxDD | -16.15% | -16.15% | — | unchanged |  |
| fixed grid | cell n22 lb126 thr0.35 CAGR | +11.01% | +10.99% | -0.02pp | **moved** |  |
| fixed grid | cell n22 lb126 thr0.35 Sharpe | 0.45 | 0.44 | -0.0064 | **moved** |  |
| fixed grid | cell n22 lb126 thr0.35 MaxDD | -22.11% | -22.11% | — | unchanged |  |
| fixed grid | cell n22 lb126 thr0.60 CAGR | +11.36% | +11.31% | -0.05pp | **moved** |  |
| fixed grid | cell n22 lb126 thr0.60 Sharpe | 0.45 | 0.44 | -0.0060 | **moved** |  |
| fixed grid | cell n22 lb126 thr0.60 MaxDD | -26.35% | -26.35% | — | unchanged |  |
| fixed grid | cell n22 lb252 thr0.00 CAGR | +9.47% | +9.48% | +0.01pp | **moved** |  |
| fixed grid | cell n22 lb252 thr0.00 Sharpe | 0.31 | 0.32 | +0.0059 | **moved** |  |
| fixed grid | cell n22 lb252 thr0.00 MaxDD | -17.01% | -17.01% | — | unchanged |  |
| fixed grid | cell n22 lb252 thr0.35 CAGR | +10.37% | +10.35% | -0.02pp | **moved** |  |
| fixed grid | cell n22 lb252 thr0.35 Sharpe | 0.38 | 0.38 | — | unchanged |  |
| fixed grid | cell n22 lb252 thr0.35 MaxDD | -22.11% | -22.11% | — | unchanged |  |
| fixed grid | cell n22 lb252 thr0.60 CAGR | +10.96% | +10.91% | -0.05pp | **moved** |  |
| fixed grid | cell n22 lb252 thr0.60 Sharpe | 0.41 | 0.41 | — | unchanged |  |
| fixed grid | cell n22 lb252 thr0.60 MaxDD | -26.35% | -26.35% | — | unchanged |  |
| fixed grid | cell n30 lb126 thr0.00 CAGR | +10.09% | +10.10% | +0.01pp | **moved** |  |
| fixed grid | cell n30 lb126 thr0.00 Sharpe | 0.38 | 0.38 | — | unchanged |  |
| fixed grid | cell n30 lb126 thr0.00 MaxDD | -17.87% | -17.87% | — | unchanged |  |
| fixed grid | cell n30 lb126 thr0.35 CAGR | +10.70% | +10.65% | -0.05pp | **moved** |  |
| fixed grid | cell n30 lb126 thr0.35 Sharpe | 0.42 | 0.42 | — | unchanged |  |
| fixed grid | cell n30 lb126 thr0.35 MaxDD | -23.80% | -23.80% | — | unchanged |  |
| fixed grid | cell n30 lb126 thr0.60 CAGR | +11.08% | +10.98% | -0.10pp | **moved** |  |
| fixed grid | cell n30 lb126 thr0.60 Sharpe | 0.43 | 0.42 | -0.0077 | **moved** |  |
| fixed grid | cell n30 lb126 thr0.60 MaxDD | -28.01% | -28.01% | — | unchanged |  |
| fixed grid | cell n30 lb252 thr0.00 CAGR | +8.84% | +8.85% | +0.01pp | **moved** |  |
| fixed grid | cell n30 lb252 thr0.00 Sharpe | 0.26 | 0.26 | — | unchanged |  |
| fixed grid | cell n30 lb252 thr0.00 MaxDD | -17.87% | -17.87% | — | unchanged |  |
| fixed grid | cell n30 lb252 thr0.35 CAGR | +9.88% | +9.82% | -0.06pp | **moved** |  |
| fixed grid | cell n30 lb252 thr0.35 Sharpe | 0.35 | 0.34 | -0.0079 | **moved** |  |
| fixed grid | cell n30 lb252 thr0.35 MaxDD | -23.80% | -23.80% | — | unchanged |  |
| fixed grid | cell n30 lb252 thr0.60 CAGR | +10.56% | +10.46% | -0.10pp | **moved** |  |
| fixed grid | cell n30 lb252 thr0.60 Sharpe | 0.39 | 0.38 | -0.0127 | **moved** |  |
| fixed grid | cell n30 lb252 thr0.60 MaxDD | -28.01% | -28.01% | — | unchanged |  |

### Negative control and loader-rule-C9 attribution

| negative control | control OOS CAGR | +10.04% | +10.05% | +0.01pp | **moved** |  |
| negative control | control OOS Sharpe | 0.37 | 0.37 | — | unchanged |  |
| negative control | control OOS MaxDD | -25.05% | -25.05% | — | unchanged |  |
| C9 attribution | pre-C9 annual turnover | 1.9913x | 1.9858x | -0.0055x | **moved** |  |
| C9 attribution | pre-C9 cost drag | +5.9297% | +5.7802% | -0.1495pp | **moved** |  |
| C9 attribution | pre-C9 full-panel in-sample CAGR | +16.63% | +16.48% | -0.15pp | **moved** |  |
| C9 attribution | pre-C9 walk-forward OOS CAGR | +9.71% | +9.52% | -0.19pp | **moved** |  |
| C9 attribution | pre-C9 walk-forward OOS Sharpe | 0.34 | 0.32 | -0.0163 | **moved** |  |

## 0. Baseline, turnover and cost-drag sanity

| Metric | v3 (`d93815344bd3`) | **v4 (`29764f562cd5`)** | status |
|--------|------------------|------------------------|--------|
| OOS cagr | +9.71% | **+9.52%** | **moved** |
| OOS sharpe | 0.34 | **0.32** | **moved** |
| OOS maxdd | -14.92% | **-14.92%** | unchanged |
| OOS calmar | 0.65 | **0.64** | **moved** |
| OOS bm_cagr | +17.12% | **+17.12%** | unchanged |
| OOS bm_sharpe | 0.68 | **0.68** | unchanged |
| OOS bm_maxdd | -37.97% | **-37.97%** | unchanged |
| annual turnover | 1.9964x/yr | **1.9910x/yr** | **moved** |
| cost drag | 6.1692%/yr | **6.0137%/yr** | **moved** |
| average names held | 21.9 | **21.9** | unchanged |

**Turnover and cost drag moved, and that is expected.** The brief flagged these as the numbers most likely to change, because the tie-break decides *which* names are held on the dates where scores tie — and on a real composite they tie on 177 of 225 rebalances. The `PortfolioConfig` position count is untouched, so `avg_names` stays at 21.9; only the identity of the holdings changed.

### Loader rule C9 — re-measured, still not an engine regression

| Panel | annual turnover | cost drag | full-panel in-sample CAGR | walk-forward OOS CAGR | OOS Sharpe |
|-------|----------------:|----------:|-------------------------:|-------------------:|-----------:|
| pre-C9 (C9 disabled) | 1.9858x | 5.7802%/yr | +16.48% | +9.52% | 0.3202 |
| current (C9 active) | 1.9910x | 6.0137%/yr | +16.72% | +9.52% | 0.3202 |

**C9 is still inert out-of-sample, exactly as v3 found it.** The frozen bars sit inside the earliest *training* windows, never in a test window, so the two panels give the same walk-forward result (+9.52% / 0.32 pre-C9 versus +9.52% / 0.32 current). **What moved is the level, on both panels equally** — 5.9297% -> 5.7802% pre-C9 and 6.1692% -> 6.0137% with C9 active, i.e. -0.1495pp and -0.1555pp. A shift that common to both panels cancels out of their difference, so the tie-break — which changes the delivered book — is the cause, and C9's own contribution is unchanged at +0.2335pp (v3: +0.2395pp). C9 remains a data-cleaning rule whose direction is **upward** on cost drag, i.e. more conservative, and it is still invisible to the engine hash.

### Walk-forward folds (out-of-sample)

| Fold | Test window | v3 selected | v4 selected | v3 CAGR | **v4 CAGR** | v3 Sharpe | **v4 Sharpe** | v4 MaxDD |
|------|-------------|-------------|-------------|--------:|-------------:|---------:|-------------:|---------:|
| 1 | 2024-10-18 -> 2026-10-01 | n22 lb126 thr0.35 | n22 lb126 thr0.35 | -0.80% | **-0.68%** | -0.85 | **-0.83** | -10.46% |
| 2 | 2022-10-25 -> 2024-10-17 | n22 lb126 thr0.6 | n22 lb252 thr0.6 | +28.80% | **+29.37%** | 1.68 | **1.73** | -7.53% |
| 3 | 2020-11-04 -> 2022-10-24 | n22 lb126 thr0.6 | n22 lb126 thr0.6 | +13.22% | **+12.63%** | 0.57 | **0.52** | -11.77% |
| 4 | 2018-11-09 -> 2020-11-03 | n15 lb126 thr0.0 | n15 lb126 thr0.0 | +1.35% | **+1.13%** | -0.42 | **-0.44** | -14.92% |
| 5 | 2016-11-22 -> 2018-11-07 | n15 lb126 thr0.35 | n15 lb126 thr0.35 | +13.16% | **+12.65%** | 0.71 | **0.66** | -11.62% |
| 6 | 2014-11-26 -> 2016-11-21 | n30 lb126 thr0.6 | n30 lb126 thr0.6 | +5.08% | **+4.69%** | -0.07 | **-0.11** | -11.24% |

**1 of 6 folds selected a different grid cell.** This is the mechanism behind every movement in this report: the tie-break changed the delivered book on a small fraction of rebalances, and a train window that ranks 18 cells by Sharpe is sensitive enough for that to flip its argmax.

## 1. Gate 4.1 — slippage stress (2x and 3x)

The **entire** walk-forward was re-run — including train-window parameter re-selection — at 5, 10 and 15 bps of slippage.

| Setting | slippage | v3 CAGR | **v4 CAGR** | v3 Sharpe | **v4 Sharpe** | v4 MaxDD | bench CAGR | v4 alpha CAGR | v4 alpha Sharpe |
|---------|---------:|--------:|-------------:|----------:|-------------:|---------:|-----------:|--------------:|---------------:|
| 1x (base) | 5 bps | +9.71% | **+9.52%** | 0.34 | **0.32** | -14.92% | +17.12% | -7.60% | -0.36 |
| 2x | 10 bps | +9.25% | **+9.07%** | 0.30 | **0.28** | -14.96% | +17.12% | -8.05% | -0.40 |
| 3x | 15 bps | +8.79% | **+8.62%** | 0.26 | **0.24** | -14.99% | +17.12% | -8.50% | -0.44 |

- Alpha against the benchmark: **-7.60%** at 1x -> **-8.05%** at 2x -> **-8.50%** at 3x
- Net CAGR falls +0.45pp at 2x and +0.91pp at 3x
- "Without collapsing" is read as: **CAGR and Sharpe both stay positive** at 2x and 3x.
- A buy-and-hold book pays one round trip in 19 years, so raising slippage moves the benchmark by well under 0.1%/yr; the relative (alpha) columns are the meaningful ones and they are **negative at every setting**.

## 2. Gate 4.2 — +/-20% parameter perturbation

One parameter moved at a time, everything else held, full walk-forward re-run so re-selection still happens. Factor lookbacks are exposed through a parameterised rebuild of `build_composite_score` from the same exported primitives, asserted **bit-identical** to the stock composite at the base values.

| Perturbation | v3 CAGR | **v4 CAGR** | v3 Sharpe | **v4 Sharpe** | v3 MaxDD | **v4 MaxDD** | vs v4 base | status |
|--------------|-------:|-------------:|----------:|-------------:|--------:|-------------:|------------:|--------|
| mom_long 244->195 (-20%) | +10.14% | **+9.87%** | 0.38 | **0.36** | -14.92% | **-14.92%** | +0.35% | **moved** |
| mom_long 244->293 (+20%) | +9.31% | **+9.30%** | 0.30 | **0.30** | -17.41% | **-17.41%** | -0.23% | **moved** |
| mom_skip 21->17 (-20%) | +10.19% | **+10.08%** | 0.37 | **0.36** | -17.85% | **-17.85%** | +0.56% | **moved** |
| mom_skip 21->25 (+20%) | +9.64% | **+9.42%** | 0.33 | **0.31** | -15.84% | **-15.84%** | -0.11% | **moved** |
| mom_6m 126->101 (-20%) | +9.80% | **+9.90%** | 0.34 | **0.35** | -17.51% | **-17.51%** | +0.38% | **moved** |
| mom_6m 126->151 (+20%) | +9.75% | **+10.32%** | 0.34 | **0.39** | -16.05% | **-16.05%** | +0.80% | **moved** |
| trend_lb 200->160 (-20%) | +8.67% | **+8.40%** | 0.25 | **0.22** | -15.82% | **-15.82%** | -1.12% | **moved** |
| trend_lb 200->240 (+20%) | +9.76% | **+9.48%** | 0.34 | **0.32** | -14.92% | **-14.92%** | -0.04% | **moved** |
| vol_lb 60->48 (-20%) | +8.90% | **+8.84%** | 0.26 | **0.26** | -14.92% | **-14.92%** | -0.69% | **moved** |
| vol_lb 60->72 (+20%) | +9.38% | **+9.28%** | 0.31 | **0.30** | -14.92% | **-14.92%** | -0.25% | **moved** |
| overlay lookback x0.80 (-20%) | +8.49% | **+9.12%** | 0.23 | **0.28** | -21.94% | **-17.02%** | -0.40% | **moved** |
| overlay lookback x1.20 (+20%) | +9.11% | **+9.01%** | 0.28 | **0.28** | -18.20% | **-14.46%** | -0.52% | **moved** |
| overlay threshold x0.80 (-20%) | +9.82% | **+9.68%** | 0.35 | **0.34** | -14.92% | **-14.92%** | +0.16% | **moved** |
| overlay threshold x1.20 (+20%) | +9.71% | **+9.44%** | 0.33 | **0.31** | -14.92% | **-14.92%** | -0.08% | **moved** |

- CAGR spread: v3 **+8.49% .. +10.19%** -> v4 **+8.40% .. +10.32%**
- Sharpe spread: v3 **0.23 .. 0.38** -> v4 **0.22 .. 0.39**
- Baseline v4 is +9.52% / 0.32; **0 of 14** perturbations flip the sign of CAGR; **14 of 14** are profitable at all.

> **Source observation, not a change made here:** the docstring of `momentum_12_1` says *"252d return"* but the code uses `core.TRADING_DAYS = 244`. This sweep perturbs from the **code** value (244), as v3 did, so the base row is bit-identical to production. Worth reconciling in a later change; not fixed here because this sweep owns no source file.

## 3. Gate 4.3 — no single year contributes > 35% of total P&L

Measured on the compounding OOS equity curve: `contribution_y = (E_y - E_{y-1}) / (E_final - 1)`. These sum exactly to 100%, and a losing year correctly shows a negative share.

| Year | v3 share | **v4 P&L** | **v4 share of total** | v4 calendar return | v4 log share | status |
|------|---------:|------------:|----------------------:|-------------------:|---------------:|--------|
| 2014 | +0.12% | +0.0025 | +0.13% | +0.25% | +0.23% | **moved** |
| 2015 | +1.47% | +0.0223 | +1.13% | +2.22% | +2.01% | **moved** |
| 2016 | +3.77% | +0.0763 | +3.86% | +7.45% | +6.58% | **moved** |
| 2017 | +15.91% | +0.3095 | +15.63% | +28.11% | +22.69% | **moved** |
| 2018 | -0.37% | -0.0075 | -0.38% | -0.53% | -0.49% | **moved** |
| 2019 | +7.38% | +0.1412 | +7.13% | +10.06% | +8.78% | **moved** |
| 2020 | -5.82% | -0.1162 | -5.87% | -7.53% | -7.17% | **moved** |
| 2021 | +15.17% | +0.2852 | +14.41% | +19.97% | +16.68% | **moved** |
| 2022 | +3.62% | +0.0748 | +3.78% | +4.37% | +3.92% | **moved** |
| 2023 | +25.83% | +0.5275 | +26.65% | +29.50% | +23.68% | **moved** |
| 2024 | +35.80% | +0.7133 | +36.03% | +30.80% | +24.60% | **moved** |
| 2025 | +12.09% | +0.2452 | +12.39% | +8.10% | +7.13% | **moved** |
| 2026 | -14.97% | -0.2946 | -14.88% | -9.00% | -8.64% | **moved** |

**Max single-year share: 36.03% (2024)** (v3: 35.80% (2024)) against a gate of 35.00% — **FAIL**.

> **The failure stands.** The peak year still carries 36.03% of total P&L against a 35.00% gate.

## 4. Gate 4.4 — no single stock contributes > 20% of total P&L

Out-of-sample only. For each fold the backtest is re-run on the **test** window with that fold's train-selected parameters. Each day's gross book return is attributed by held weight; each day's cost charge is split across stocks by that stock's share of the day's `|dW|`. The engine's own compounding equity loop is replayed to recover the per-date charge and is **asserted against `BacktestResult.costs_paid`**, so the split is an exact decomposition rather than a pro-rata guess. The regime overlay is then applied to every leg and the cash leg reported separately.

Reconciliation error (max |per-stock daily sum − engine daily return|): **3.23e-16**.

Total net stock P&L **+1.0133** normalised equity units (v3 +1.0357); cash leg (overlay idle time in T-bills) **+0.1447** (v3 +0.1420).

| # | symbol | net P&L | v4 share of net | share of gross | cost charged |
|--:|--------|--------:|---------------:|---------------:|-------------:|
| 1 | trent | +0.0831 | +8.20% | +7.56% | 0.0018 |
| 2 | powergrid | +0.0536 | +5.29% | +5.01% | 0.0026 |
| 3 | bel | +0.0533 | +5.26% | +4.92% | 0.0019 |
| 4 | titan | +0.0450 | +4.44% | +4.27% | 0.0030 |
| 5 | hdfcbank | +0.0436 | +4.31% | +4.07% | 0.0021 |

| symbol | net P&L | share of net |
|--------|--------:|------------:|
| cipla | -0.0137 | -1.36% |
| axisbank | -0.0179 | -1.77% |
| icicibank | -0.0187 | -1.85% |

- Top 5 combined share of net P&L: **27.51%** (v3 27.93%)
- **Max single-stock share: 8.20% (trent)** (v3 8.01% (trent)) against a gate of 20.00% — **PASS**
- 40 of 48 names contributed positive net P&L

## 5. Gate 4.5 — at least 4 of 6 neighbouring settings profitable

**Definition of "neighbouring"** (stated because the gate requires it): a single-axis **+/-20%** shift of one of the three lookback knobs that define the operating point, every other parameter held, with the standard walk-forward re-selection left **on** — so every neighbour is an honest end-to-end out-of-sample number.

| # | neighbour | v3 CAGR | **v4 CAGR (net)** | v3 Sharpe | **v4 Sharpe** | v4 MaxDD |
|--:|-----------|-------:|------------------:|----------:|-------------:|---------:|
| 1 | mom_6m 126->101 (-20%) | +9.80% | **+9.90%** | 0.34 | **0.35** | -17.51% |
| 2 | mom_6m 126->151 (+20%) | +9.75% | **+10.32%** | 0.34 | **0.39** | -16.05% |
| 3 | trend_lb 200->160 (-20%) | +8.67% | **+8.40%** | 0.25 | **0.22** | -15.82% |
| 4 | trend_lb 200->240 (+20%) | +9.76% | **+9.48%** | 0.34 | **0.32** | -14.92% |
| 5 | overlay lookback x0.80 (-20%) | +8.49% | **+9.12%** | 0.23 | **0.28** | -17.02% |
| 6 | overlay lookback x1.20 (+20%) | +9.11% | **+9.01%** | 0.28 | **0.28** | -14.46% |

**Profitable: 6 of 6** against a gate of >= 4 of 6 — **PASS**. CAGR range across neighbours: +8.40% .. +10.32% (v3 +8.49% .. +9.80%).

### Supplementary — the full grid, FIXED parameters, no train selection

The same 18 cells `walk_forward` chooses between, each evaluated on the fold test windows with **no per-fold re-fitting**. Reported whether or not it flatters the strategy.

| n_positions | overlay lookback | threshold | v3 CAGR | **v4 CAGR** | v3 Sharpe | **v4 Sharpe** | v4 MaxDD |
|------------:|-----------------:|----------:|-------:|-------------:|----------:|-------------:|---------:|
| 15 | 126 | 0.00 | +9.28% | **+9.23%** | 0.30 | **0.30** | -14.92% |
| 15 | 126 | 0.35 | +9.36% | **+9.28%** | 0.30 | **0.29** | -21.47% |
| 15 | 126 | 0.60 | +9.35% | **+9.24%** | 0.29 | **0.28** | -26.11% |
| 15 | 252 | 0.00 | +8.02% | **+7.94%** | 0.19 | **0.18** | -17.80% |
| 15 | 252 | 0.35 | +8.53% | **+8.42%** | 0.23 | **0.22** | -21.97% |
| 15 | 252 | 0.60 | +8.83% | **+8.71%** | 0.24 | **0.23** | -26.50% |
| 22 | 126 | 0.00 | +10.43% | **+10.45%** | 0.41 | **0.41** | -16.15% |
| 22 | 126 | 0.35 | +11.01% | **+10.99%** | 0.45 | **0.44** | -22.11% |
| 22 | 126 | 0.60 | +11.36% | **+11.31%** | 0.45 | **0.44** | -26.35% |
| 22 | 252 | 0.00 | +9.47% | **+9.48%** | 0.31 | **0.32** | -17.01% |
| 22 | 252 | 0.35 | +10.37% | **+10.35%** | 0.38 | **0.38** | -22.11% |
| 22 | 252 | 0.60 | +10.96% | **+10.91%** | 0.41 | **0.41** | -26.35% |
| 30 | 126 | 0.00 | +10.09% | **+10.10%** | 0.38 | **0.38** | -17.87% |
| 30 | 126 | 0.35 | +10.70% | **+10.65%** | 0.42 | **0.42** | -23.80% |
| 30 | 126 | 0.60 | +11.08% | **+10.98%** | 0.43 | **0.42** | -28.01% |
| 30 | 252 | 0.00 | +8.84% | **+8.85%** | 0.26 | **0.26** | -17.87% |
| 30 | 252 | 0.35 | +9.88% | **+9.82%** | 0.35 | **0.34** | -23.80% |
| 30 | 252 | 0.60 | +10.56% | **+10.46%** | 0.39 | **0.38** | -28.01% |

- Profitable cells: **18 of 18**
- CAGR range **+7.94% .. +11.31%**, Sharpe range **0.18 .. 0.44**
- The train-selected baseline is **+9.52% / 0.32**. Where it lands inside that unselected spread is the tell.

## 6. Negative control

`NEGATIVE_CONTROL_WEIGHTS` (45% `reversal_5d`, 30% `reversal_20d`, 25% `low_volatility`) through the **same** walk-forward harness and the same cost stack. It must underperform the trend composite; if it does not, the harness is mining noise, and that would be the single most important finding on this page.

| composite | v3 OOS CAGR | **v4 OOS CAGR** | v3 Sharpe | **v4 Sharpe** | v4 MaxDD |
|-----------|------------:|----------------:|----------:|-------------:|---------:|
| trend (production) | +9.71% | **+9.52%** | 0.34 | **0.32** | -14.92% |
| reversal (control) | +10.04% | **+10.05%** | 0.37 | **0.37** | -25.05% |

**Control underperforms on both CAGR and Sharpe: FAIL.**

> ### This is the most important line in this report
>
`reversal_5d` and `reversal_20d` are short-term reversal factors. The factor module's own literature review concludes, from two methodologically disjoint Indian studies plus the only multiple-testing-corrected one, that **reversal does not work in Indian cash equities and trend does**. A composite built *entirely* from those two rejected factors returned a higher out-of-sample CAGR (+10.05% vs +9.52%) and a higher Sharpe (0.37 vs 0.32) than the production trend composite, net of the full cost stack.
>
Read together with the supplementary grid in §5, the picture is that almost anything built from this factor set on this universe returns a positive out-of-sample result — the signature of a long-only, equity-beta-tilted book in a market that rose, not of a validated signal. Per `GOAL.md` §6, a strategy whose negative control does not fail cannot be certified by the robustness tests it passes.

## 7. Gate 4 verdict

- [PASS] **G4.1 survives 2x/3x slippage stress without collapsing** — 2x +9.07% / 0.28; 3x +8.62% / 0.24; alpha -7.60% -> -8.50%
- [PASS] **G4.2 survives +/-20% parameter perturbation** — 14/14 profitable, CAGR +8.40%..+10.32%, Sharpe 0.22..0.39, 0 sign flip(s)
- [FAIL] **G4.3 no single year > 35% of total P&L** — max 36.03% (2024)
- [PASS] **G4.4 no single stock > 20% of total P&L** — max 8.20% (trent)
- [PASS] **G4.5 >= 4 of 6 neighbouring settings profitable** — 6 of 6, CAGR +8.40%..+10.32%
- [PASS] **X   turnover / cost-drag sanity (no engine regression)** — 1.9910x/y, 6.0137%/y; loader C9's own contribution +0.2395pp (v3) -> +0.2335pp (v4), 21.92 bps unchanged
- [FAIL] **X   negative control (reversal) underperforms** — reversal Sharpe 0.37 vs trend 0.32; CAGR +10.05% vs +9.52%

**Overall: Gate 4 DOES NOT PASS (5 of 7 pass, 2 fail).**

The remaining failure(s), stated plainly:

- **G4.3 no single year > 35% of total P&L** — max 36.03% (2024)
- **X   negative control (reversal) underperforms** — reversal Sharpe 0.37 vs trend 0.32; CAGR +10.05% vs +9.52%

> **Read the failures together, not separately.** Where the negative control is among them, the other failure is what a beta-driven result looks like: concentration in a short window, because the whole return comes from the market's direction rather than from a signal that pays in every regime. The passes are not evidence against this reading — a 22-name, monthly-rebalanced, mildly quality-tilted book passes slippage, parameter, per-stock and neighbour stress regardless of whether it has an edge.

> **This does not say the strategy has no edge.** It says the evidence collected here cannot demonstrate one. `GOAL.md` §5's default verdict applies: keep researching, do not loosen the gate, do not deploy.

## 8. Bottom line

**Gate 4 on the tie-break-fixed engine: 5 of 7 checks pass, 2 fail** — the same count as on `d93815344bd3`, and the same two checks fail. The walk-forward baseline moved +9.71% / 0.34 -> +9.52% / 0.32, and turnover and cost drag moved 1.9964x -> 1.9910x/yr and 6.1692% -> 6.0137%/yr. That movement is expected and is attributable: the tie-break changes *which* names are held on the rebalance dates where a real composite's median-filled factors tie, so the book it delivers changes shape, while the configured position count does not (21.9 names on both engines). Loader rule C9's own contribution is unchanged at +0.2335pp against v3's +0.2395pp, so nothing in the engine's cost charge moved.

**The negative control still fails, and that is the finding that survives the fix.** `reversal_5d` and `reversal_20d` are factors this repo's own literature review rules out on published Indian evidence, and a composite built entirely from them returns +10.05% / 0.37 against production's +9.52% / 0.32 — net of the full 21.92bps stack. **Its lead did not shrink: it is +0.52pp on v4 versus +0.33pp on v3.** A tie-break bias fix removed an alphabetical selection effect and the control still wins, by slightly more. One caveat has to travel with that number: `reports/CONTROL_DIAGNOSTIC_v2.md` §H4 measures the gap as statistically indistinguishable on both engines (robust paired p = 0.78 over 2,928 daily observations), so v4 is the same fact as v3 stated with the right hedging — the harness cannot tell the two composites apart, rather than the harness having proved the worse one is better. Gate 4 as written asks the control to *underperform*, and it does not, so the check fails either way.

**The yearly-concentration failure also survives, and it is now a wider miss.** 2024 carries 36.03% of total P&L against a 35.00% gate, against v3's 35.80% in 2024 — a move of +0.23pp, and still the same calendar year carrying it, that came entirely from reshuffling the book on tied-score dates. That is the signature of a result driven by market beta rather than by a signal that pays in every regime: one strong calendar year does most of the work, and *which* year that is has no stable answer.

So: **a bias fix moved the headline 0.19pp and did not make the evidence better.** What passed passes for the same reason it passed on v3 — a 22-name, monthly-rebalanced, mildly quality-tilted NIFTY-50 book survives slippage, parameter perturbation, per-stock concentration and neighbouring-settings stress whether or not its signal is worth anything, and 18 of 18 fixed grid cells are profitable net. Per `GOAL.md` §5 the gate does not pass; §6's anti-fraud rules forbid treating the passing checks as grounds to relax it. The honest summary of this re-run is that the *integrity* of the number improved while the *number* did not: on `d93815344bd3` part of every composite's book was chosen by ticker order, and that is now gone — but the result it produced is unchanged in character, and the correct response is still to change what counts as success rather than to search harder for parameters.
---

*Produced by `research/revalidate_v2/run_stress.py` + `report_stress.py` against engine `29764f562cd5`, loader `c1badf5f7df8`, costs `ba350aef75b3`, panel `389b082b832f`. v3 is `reports/STRESS_v3.md` (engine `d93815344bd3`; its `research/stress_tests.py` keeps no result cache, so the v3 column above is transcribed from that report at its printed precision rather than re-derived). Any result from this system must be quoted with its end date — the OOS window here ends 2026-10-01. Survivorship bias is present and disclosed. `GOAL.md` §6 anti-fraud rules apply: no in-sample number is presented as a result, and no cost was reduced to rescue anything.*
