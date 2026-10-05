# Full algorithm sweep — BTC & ETH daily (2026-08-23)

89 algorithms, real Binance daily data (2024-08 → 2026-08), 3bps slippage + 5bps fees, $10k capital, per-bar mark-to-market.

## Profitable on BOTH assets (ranked by combined Sharpe)

| algorithm | BTC ret | BTC shp | BTC mdd | ETH ret | ETH shp | ETH mdd |
|---|---|---|---|---|---|---|
| time_series | 83.0% | 0.69 | 32.1% | 367.8% | 1.19 | 25.8% |
| ema_cross | 78.1% | 0.68 | 31.4% | 179.1% | 0.82 | 61.2% |
| absolute_momentum | 41.4% | 0.43 | 37.4% | 345.7% | 1.05 | 59.6% |
| dual_ma | 75.8% | 0.69 | 41.7% | 131.2% | 0.78 | 39.5% |
| dual_momentum | 79.3% | 0.69 | 31.9% | 160.2% | 0.77 | 67.3% |
| funding_trend | 43.8% | 0.45 | 32.1% | 192.7% | 0.93 | 35.7% |
| dema | 43.0% | 0.43 | 35.0% | 194.2% | 0.84 | 31.7% |
| hull | 43.0% | 0.43 | 35.0% | 194.2% | 0.84 | 31.7% |
| kama | 43.0% | 0.43 | 35.0% | 194.2% | 0.84 | 31.7% |
| tema | 43.0% | 0.43 | 35.0% | 194.2% | 0.84 | 31.7% |
| funding_basis | 48.1% | 0.45 | 44.5% | 96.1% | 0.61 | 52.9% |
| linear_reg_channel | 48.1% | 0.45 | 44.5% | 96.1% | 0.61 | 52.9% |
| meta | 48.1% | 0.45 | 44.5% | 96.1% | 0.61 | 52.9% |
| regression | 48.1% | 0.45 | 44.5% | 96.1% | 0.61 | 52.9% |
| trend_momentum | 25.6% | 0.31 | 37.8% | 110.0% | 0.68 | 43.4% |
| ma_cross | 23.2% | 0.31 | 37.2% | 107.1% | 0.65 | 68.6% |
| roll_cross | 23.2% | 0.31 | 37.2% | 107.1% | 0.65 | 68.6% |
| corr_gate | 45.4% | 0.46 | 28.0% | 30.0% | 0.34 | 44.2% |
| dispersion | 16.8% | 0.24 | 33.1% | 57.4% | 0.55 | 26.5% |
| ensemble_signals | 32.9% | 0.36 | 32.2% | 46.8% | 0.43 | 40.2% |
| trend_following | 11.7% | 0.18 | 34.8% | 62.3% | 0.56 | 44.3% |
| momentum_vol | 26.0% | 0.31 | 37.6% | 48.3% | 0.43 | 45.0% |
| triple_ma | 47.3% | 0.51 | 22.4% | 9.3% | 0.23 | 49.7% |
| basket | 24.5% | 0.29 | 38.4% | 51.5% | 0.44 | 44.7% |
| cross_sectional | 24.5% | 0.29 | 38.4% | 51.5% | 0.44 | 44.7% |
| volume_spike | 40.6% | 0.45 | 53.0% | 5.6% | 0.28 | 67.6% |
| multi_factor | 55.5% | 0.51 | 27.1% | 5.5% | 0.21 | 38.9% |
| rsi_momentum | 43.9% | 0.44 | 32.5% | 10.7% | 0.23 | 46.3% |

## Per-asset profitable (single-asset only)

| algorithm | asset | ret | sharpe | mdd | trades |
|---|---|---|---|---|---|
| open_range | BTC | 52.3% | 0.54 | 28.1% | 6 |
| volume_profile | BTC | 34.5% | 0.38 | 36.5% | 77 |
| resistance | BTC | 17.3% | 0.27 | 18.6% | 51 |
| roc | BTC | 0.3% | 0.08 | 45.7% | 103 |
| macd | ETH | 128.3% | 0.70 | 55.2% | 51 |
| macd_momentum | ETH | 128.3% | 0.70 | 55.2% | 51 |
| adaptive_allocation | ETH | 36.7% | 0.38 | 45.5% | 84 |
| momentum_factor | ETH | 36.7% | 0.38 | 45.5% | 84 |
| relative_strength | ETH | 36.7% | 0.38 | 45.5% | 84 |
| atr_trailing | ETH | 28.9% | 0.32 | 31.9% | 72 |
| keltner_momentum | ETH | 26.8% | 0.31 | 34.2% | 70 |
| triangle | ETH | 1.1% | 0.17 | 45.9% | 80 |
| garch_classic | ETH | 8.7% | 0.12 | 18.4% | 29 |
| support | ETH | 3.6% | 0.07 | 30.7% | 36 |

## time_series walk-forward validation (2026-08-23)

Protocol: tune period/threshold on leading 65% of daily bars, score winner on
untouched final 35% (`tools/validate_time_series.py`).

| asset | tuned params | train sharpe | OOS sharpe | OOS ret | verdict |
|---|---|---|---|---|---|
| BTC | (60, 0.05) | 0.96 | **−0.15** | −6.0% | ❌ fails OOS |
| ETH | (60, 0.05) | 1.62 | **+1.36** | +67.3% | ✅ passes strongly |

Plateau: ETH robust across period 30–60 × all thresholds (Sharpe 1.05–1.28);
BTC mixed, tuned winner does not generalize there.

## Updated portfolio recommendation

| portfolio | ret | sharpe | mdd |
|---|---|---|---|
| A: BTC dual_ma(5,50) + ETH dual_ma(15,80) | +198% | 1.26 | 22.6% |
| **B: BTC dual_ma(5,50) + ETH time_series(60, 0.05)** | **+335%** | **1.63** | 23.4% |

Per-asset assignment follows the OOS evidence: BTC keeps dual_ma (time_series
failed its BTC tail test), ETH switches to time_series. Portfolio B dominates
A on return and Sharpe at essentially unchanged drawdown.

Caveats: single regime (2024–2026 bull), one asset each; the 60-day paper gate
is the true test. Gate requires running TWO strategy processes (one per symbol)
— compose service `cryptobot-eth` to be added at gate start.
