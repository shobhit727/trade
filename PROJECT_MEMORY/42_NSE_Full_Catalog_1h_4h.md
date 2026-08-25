# NSE full-catalog test — all algos on 1h & 4h

Generated 2026-08-25T19:27:05+00:00 · 89-algo registry × ~50 stocks × {1h, 4h(session-resampled)} × {intraday MIS, delivery CNC} costs.
volume_spike excluded (#57 precedence bug). Rows with ≤3 trades dropped.

## Summary — top 10 per grid (by mean Sharpe across stocks)

### 1h · MIS(2+1) — 4346 active runs, 1087 profitable (25%)

| rank | algo | wins | mean sharpe | median ret |
|---|---|---|---|---|
| 1 | vwap | 27/50 | -0.15 | +4.8% |
| 2 | anchored_vwap | 26/50 | -0.19 | +1.3% |
| 3 | zscore | 29/50 | -0.19 | +8.5% |
| 4 | gaussian | 29/50 | -0.20 | +7.9% |
| 5 | macd | 22/50 | -0.22 | -3.8% |
| 6 | macd_momentum | 22/50 | -0.22 | -3.8% |
| 7 | ema_cross | 19/50 | -0.23 | -8.7% |
| 8 | dual_momentum | 18/50 | -0.24 | -8.2% |
| 9 | dual_ma | 14/50 | -0.25 | -8.1% |
| 10 | roll_cross | 18/50 | -0.26 | -12.2% |

### 1h · CNC(11+1) — 4346 active runs, 256 profitable (6%)

| rank | algo | wins | mean sharpe | median ret |
|---|---|---|---|---|
| 1 | vwap | 15/50 | -0.28 | -9.3% |
| 2 | anchored_vwap | 14/50 | -0.32 | -12.2% |
| 3 | dual_ma | 11/50 | -0.34 | -17.8% |
| 4 | zscore | 14/50 | -0.35 | -11.3% |
| 5 | gaussian | 14/50 | -0.35 | -12.1% |
| 6 | ema_cross | 9/50 | -0.38 | -25.4% |
| 7 | dual_momentum | 8/50 | -0.40 | -25.2% |
| 8 | cointegration | 6/50 | -0.43 | -18.8% |
| 9 | spot_futures | 6/50 | -0.43 | -18.8% |
| 10 | roll_cross | 8/50 | -0.44 | -30.4% |

### 4h · MIS(2+1) — 3959 active runs, 1266 profitable (32%)

| rank | algo | wins | mean sharpe | median ret |
|---|---|---|---|---|
| 1 | anchored_vwap | 25/50 | 0.08 | +1.0% |
| 2 | vwap | 24/50 | 0.03 | -3.0% |
| 3 | stablecoin_peg | 30/50 | 0.03 | +5.4% |
| 4 | zscore | 30/50 | 0.03 | +9.0% |
| 5 | gaussian | 29/50 | 0.02 | +7.7% |
| 6 | cointegration | 26/50 | -0.01 | +2.0% |
| 7 | spot_futures | 26/50 | -0.01 | +2.0% |
| 8 | macd | 24/50 | -0.05 | -3.7% |
| 9 | macd_momentum | 24/50 | -0.05 | -3.7% |
| 10 | distance_ma | 29/50 | -0.16 | +1.7% |

### 4h · CNC(11+1) — 3959 active runs, 638 profitable (16%)

| rank | algo | wins | mean sharpe | median ret |
|---|---|---|---|---|
| 1 | anchored_vwap | 24/50 | -0.00 | -3.9% |
| 2 | vwap | 21/50 | -0.05 | -8.4% |
| 3 | gaussian | 25/50 | -0.07 | +0.6% |
| 4 | zscore | 26/50 | -0.07 | +1.8% |
| 5 | cointegration | 23/50 | -0.10 | -3.3% |
| 6 | spot_futures | 23/50 | -0.10 | -3.3% |
| 7 | stablecoin_peg | 20/50 | -0.12 | -5.2% |
| 8 | macd | 15/50 | -0.24 | -15.4% |
| 9 | macd_momentum | 15/50 | -0.24 | -15.4% |
| 10 | ma_cross | 10/50 | -0.30 | -20.2% |

## Full rankings (every algo, every grid)

### 1h · MIS(2+1)

| algo | wins | mean sharpe | median ret |
|---|---|---|---|
| vwap | 27/50 | -0.15 | +4.8% |
| anchored_vwap | 26/50 | -0.19 | +1.3% |
| zscore | 29/50 | -0.19 | +8.5% |
| gaussian | 29/50 | -0.20 | +7.9% |
| macd | 22/50 | -0.22 | -3.8% |
| macd_momentum | 22/50 | -0.22 | -3.8% |
| ema_cross | 19/50 | -0.23 | -8.7% |
| dual_momentum | 18/50 | -0.24 | -8.2% |
| dual_ma | 14/50 | -0.25 | -8.1% |
| roll_cross | 18/50 | -0.26 | -12.2% |
| ma_cross | 17/50 | -0.26 | -12.2% |
| cointegration | 24/50 | -0.26 | -3.2% |
| spot_futures | 24/50 | -0.26 | -3.2% |
| funding_basis | 18/50 | -0.28 | -14.3% |
| linear_reg_channel | 18/50 | -0.28 | -14.3% |
| meta | 18/50 | -0.28 | -14.3% |
| regression | 18/50 | -0.28 | -14.3% |
| absolute_momentum | 13/50 | -0.29 | -12.4% |
| time_series | 14/50 | -0.30 | -17.2% |
| cumulative_delta | 15/50 | -0.30 | -14.0% |
| dema | 16/50 | -0.31 | -17.0% |
| hull | 16/50 | -0.31 | -17.0% |
| kama | 16/50 | -0.31 | -17.0% |
| tema | 16/50 | -0.31 | -17.0% |
| multi_factor | 16/50 | -0.33 | -18.2% |
| stablecoin_peg | 13/50 | -0.33 | -13.7% |
| open_range | 14/50 | -0.34 | -13.4% |
| adaptive_allocation | 15/50 | -0.35 | -13.6% |
| momentum_factor | 15/50 | -0.35 | -13.6% |
| relative_strength | 15/50 | -0.35 | -13.6% |
| rsi_momentum | 11/50 | -0.35 | -16.6% |
| triple_ma | 13/50 | -0.36 | -11.2% |
| funding_trend | 16/50 | -0.36 | -15.8% |
| ensemble_signals | 11/50 | -0.37 | -18.9% |
| trend_following | 19/50 | -0.38 | -7.4% |
| momentum_vol | 16/50 | -0.38 | -17.5% |
| vw_momentum | 16/50 | -0.38 | -17.5% |
| corr_gate | 15/50 | -0.41 | -18.9% |
| basket | 10/50 | -0.42 | -14.8% |
| cross_sectional | 10/50 | -0.42 | -14.8% |
| volume_profile | 10/50 | -0.42 | -17.4% |
| trend_momentum | 12/50 | -0.43 | -13.4% |
| cmf | 8/50 | -0.45 | -14.6% |
| dispersion | 14/50 | -0.45 | -9.8% |
| volume_momentum | 15/50 | -0.50 | -10.5% |
| roc | 10/50 | -0.53 | -19.4% |
| nse_orb | 18/50 | -0.54 | -14.4% |
| trend_mr | 10/50 | -0.54 | -11.8% |
| mean_reversion | 13/50 | -0.57 | -10.3% |
| fisher | 5/50 | -0.60 | -32.0% |
| rsi | 5/50 | -0.61 | -20.3% |
| cci | 7/50 | -0.63 | -20.7% |
| bb_squeeze2 | 7/50 | -0.63 | -50.2% |
| squeeze | 7/50 | -0.63 | -50.2% |
| atr_breakout | 10/50 | -0.63 | -19.0% |
| keltner | 12/50 | -0.64 | -7.0% |
| stochastic | 5/50 | -0.66 | -27.7% |
| williams_r | 5/50 | -0.66 | -27.7% |
| triangle | 11/50 | -0.69 | -10.8% |
| keltner_momentum | 10/50 | -0.70 | -13.9% |
| atr_trailing | 14/50 | -0.71 | -12.7% |
| mfi | 17/50 | -0.72 | -7.7% |
| adx_trend | 1/50 | -0.82 | -69.7% |
| liquidation_hunt | 1/50 | -0.82 | -69.7% |
| supertrend | 1/50 | -0.82 | -69.7% |
| flag | 5/50 | -0.87 | -37.3% |
| distance_ma | 20/50 | -0.89 | -3.2% |
| regime_switch | 5/50 | -0.89 | -48.9% |
| nr4 | 1/50 | -0.89 | -37.9% |
| impl_real_vol | 1/50 | -0.90 | -65.8% |
| gap | 1/50 | -0.96 | -70.7% |
| vol_scaling | 1/50 | -0.96 | -70.4% |
| vol_target | 1/50 | -0.97 | -71.2% |
| bollinger | 8/50 | -1.02 | -11.9% |
| obv | 0/50 | -1.03 | -69.7% |
| trend_volume | 2/50 | -1.04 | -35.5% |
| inside_bar | 1/50 | -1.20 | -30.9% |
| vwap_revert | 15/50 | -1.31 | -4.2% |
| vol_expansion | 3/50 | -1.35 | -26.8% |
| garch_classic | 15/50 | -2.12 | -2.4% |
| break_momentum | 12/50 | -3.23 | -2.0% |
| breakout_momentum | 12/50 | -3.23 | -2.0% |
| donchian | 12/50 | -3.23 | -2.0% |
| price_channel | 12/50 | -3.23 | -2.0% |
| rectangle | 12/50 | -3.23 | -2.0% |
| resistance | 18/49 | -4.89 | -0.7% |
| support | 10/47 | -5.13 | -1.1% |

### 1h · CNC(11+1)

| algo | wins | mean sharpe | median ret |
|---|---|---|---|
| vwap | 15/50 | -0.28 | -9.3% |
| anchored_vwap | 14/50 | -0.32 | -12.2% |
| dual_ma | 11/50 | -0.34 | -17.8% |
| zscore | 14/50 | -0.35 | -11.3% |
| gaussian | 14/50 | -0.35 | -12.1% |
| ema_cross | 9/50 | -0.38 | -25.4% |
| dual_momentum | 8/50 | -0.40 | -25.2% |
| cointegration | 6/50 | -0.43 | -18.8% |
| spot_futures | 6/50 | -0.43 | -18.8% |
| roll_cross | 8/50 | -0.44 | -30.4% |
| ma_cross | 8/50 | -0.44 | -30.4% |
| open_range | 6/50 | -0.45 | -23.3% |
| trend_following | 13/50 | -0.51 | -17.7% |
| macd | 3/50 | -0.56 | -41.4% |
| macd_momentum | 3/50 | -0.56 | -41.4% |
| time_series | 3/50 | -0.59 | -44.4% |
| stablecoin_peg | 1/50 | -0.61 | -38.9% |
| absolute_momentum | 4/50 | -0.62 | -46.0% |
| cumulative_delta | 3/50 | -0.65 | -48.1% |
| triple_ma | 2/50 | -0.67 | -36.6% |
| funding_basis | 5/50 | -0.72 | -55.3% |
| linear_reg_channel | 5/50 | -0.73 | -55.5% |
| meta | 5/50 | -0.73 | -55.5% |
| regression | 5/50 | -0.73 | -55.5% |
| dispersion | 5/50 | -0.73 | -28.8% |
| funding_trend | 1/50 | -0.75 | -45.8% |
| trend_mr | 2/50 | -0.77 | -24.1% |
| adaptive_allocation | 2/50 | -0.79 | -50.5% |
| momentum_factor | 2/50 | -0.79 | -50.5% |
| relative_strength | 2/50 | -0.79 | -50.5% |
| dema | 3/50 | -0.79 | -59.9% |
| hull | 3/50 | -0.79 | -59.9% |
| kama | 3/50 | -0.79 | -59.9% |
| tema | 3/50 | -0.79 | -59.9% |
| multi_factor | 2/50 | -0.82 | -56.7% |
| momentum_vol | 2/50 | -0.82 | -50.4% |
| vw_momentum | 2/50 | -0.82 | -50.4% |
| mean_reversion | 0/50 | -0.82 | -25.4% |
| basket | 2/50 | -0.84 | -44.4% |
| cross_sectional | 2/50 | -0.84 | -44.4% |
| trend_momentum | 0/50 | -0.86 | -44.7% |
| corr_gate | 1/50 | -0.86 | -50.8% |
| rsi_momentum | 1/50 | -0.86 | -55.7% |
| volume_momentum | 3/50 | -0.87 | -33.7% |
| ensemble_signals | 3/50 | -0.89 | -59.4% |
| cmf | 2/50 | -0.93 | -49.9% |
| volume_profile | 1/50 | -0.93 | -54.8% |
| triangle | 1/50 | -1.03 | -25.9% |
| mfi | 2/50 | -1.08 | -22.3% |
| distance_ma | 6/50 | -1.10 | -9.1% |
| rsi | 0/50 | -1.11 | -46.5% |
| roc | 0/50 | -1.12 | -57.0% |
| keltner | 0/50 | -1.15 | -33.6% |
| keltner_momentum | 1/50 | -1.22 | -36.6% |
| cci | 0/50 | -1.24 | -52.9% |
| nse_orb | 3/50 | -1.26 | -52.5% |
| atr_breakout | 0/50 | -1.27 | -49.6% |
| atr_trailing | 1/50 | -1.29 | -35.5% |
| fisher | 0/50 | -1.37 | -74.7% |
| stochastic | 0/50 | -1.41 | -65.3% |
| williams_r | 0/50 | -1.41 | -65.3% |
| bb_squeeze2 | 1/50 | -1.74 | -90.4% |
| squeeze | 1/50 | -1.74 | -90.4% |
| adx_trend | 0/50 | -1.76 | -98.0% |
| liquidation_hunt | 0/50 | -1.76 | -98.0% |
| supertrend | 0/50 | -1.79 | -98.0% |
| bollinger | 0/50 | -1.82 | -38.6% |
| vwap_revert | 0/50 | -2.11 | -22.1% |
| nr4 | 0/50 | -2.17 | -81.6% |
| flag | 0/50 | -2.30 | -86.4% |
| garch_classic | 3/50 | -2.36 | -6.2% |
| regime_switch | 0/50 | -2.45 | -92.4% |
| trend_volume | 0/50 | -2.54 | -78.9% |
| impl_real_vol | 0/50 | -2.62 | -97.7% |
| inside_bar | 0/50 | -2.79 | -75.0% |
| vol_scaling | 0/50 | -2.86 | -98.0% |
| gap | 0/50 | -2.87 | -98.0% |
| vol_target | 0/50 | -2.87 | -98.0% |
| obv | 0/50 | -2.98 | -98.0% |
| vol_expansion | 0/50 | -3.02 | -68.9% |
| break_momentum | 2/50 | -3.40 | -4.7% |
| breakout_momentum | 2/50 | -3.40 | -4.7% |
| donchian | 2/50 | -3.40 | -4.7% |
| price_channel | 2/50 | -3.40 | -4.7% |
| rectangle | 2/50 | -3.40 | -4.7% |
| resistance | 7/49 | -4.77 | -1.9% |
| support | 2/47 | -5.07 | -3.1% |

### 4h · MIS(2+1)

| algo | wins | mean sharpe | median ret |
|---|---|---|---|
| anchored_vwap | 25/50 | 0.08 | +1.0% |
| vwap | 24/50 | 0.03 | -3.0% |
| stablecoin_peg | 30/50 | 0.03 | +5.4% |
| zscore | 30/50 | 0.03 | +9.0% |
| gaussian | 29/50 | 0.02 | +7.7% |
| cointegration | 26/50 | -0.01 | +2.0% |
| spot_futures | 26/50 | -0.01 | +2.0% |
| macd | 24/50 | -0.05 | -3.7% |
| macd_momentum | 24/50 | -0.05 | -3.7% |
| distance_ma | 29/50 | -0.16 | +1.7% |
| funding_basis | 16/50 | -0.18 | -9.5% |
| linear_reg_channel | 16/50 | -0.18 | -9.5% |
| meta | 16/50 | -0.18 | -9.5% |
| regression | 16/50 | -0.18 | -9.5% |
| keltner | 28/50 | -0.18 | +1.8% |
| rsi | 27/50 | -0.19 | +1.7% |
| ma_cross | 16/50 | -0.21 | -14.9% |
| roll_cross | 16/50 | -0.21 | -14.9% |
| dema | 18/50 | -0.21 | -11.1% |
| hull | 18/50 | -0.21 | -11.1% |
| kama | 18/50 | -0.21 | -11.1% |
| tema | 18/50 | -0.21 | -11.1% |
| mean_reversion | 26/50 | -0.22 | +1.1% |
| cci | 16/50 | -0.23 | -4.3% |
| rsi_momentum | 13/50 | -0.25 | -9.2% |
| open_range | 16/49 | -0.25 | -8.8% |
| multi_factor | 11/50 | -0.26 | -13.2% |
| ensemble_signals | 14/50 | -0.26 | -15.2% |
| dual_momentum | 14/50 | -0.26 | -18.3% |
| bb_squeeze2 | 13/50 | -0.26 | -17.8% |
| squeeze | 13/50 | -0.26 | -17.8% |
| fisher | 15/50 | -0.27 | -12.6% |
| ema_cross | 13/50 | -0.27 | -18.2% |
| volume_profile | 16/50 | -0.28 | -13.6% |
| absolute_momentum | 12/50 | -0.29 | -16.3% |
| time_series | 12/50 | -0.29 | -18.9% |
| trend_momentum | 14/50 | -0.32 | -12.8% |
| stochastic | 15/50 | -0.32 | -11.0% |
| williams_r | 15/50 | -0.32 | -11.0% |
| adaptive_allocation | 12/50 | -0.34 | -18.2% |
| momentum_factor | 12/50 | -0.34 | -18.2% |
| relative_strength | 12/50 | -0.34 | -18.2% |
| corr_gate | 10/50 | -0.34 | -12.8% |
| cumulative_delta | 12/50 | -0.34 | -22.0% |
| momentum_vol | 12/50 | -0.35 | -17.8% |
| vw_momentum | 12/50 | -0.35 | -17.8% |
| basket | 12/50 | -0.35 | -16.1% |
| cross_sectional | 12/50 | -0.35 | -16.1% |
| dual_ma | 16/50 | -0.35 | -19.9% |
| funding_trend | 12/50 | -0.36 | -16.8% |
| triple_ma | 13/50 | -0.36 | -15.2% |
| trend_following | 16/50 | -0.36 | -12.5% |
| triangle | 15/50 | -0.37 | -9.6% |
| dispersion | 13/50 | -0.39 | -13.3% |
| roc | 13/50 | -0.39 | -16.8% |
| mfi | 29/50 | -0.40 | +0.9% |
| adx_trend | 14/50 | -0.41 | -26.9% |
| liquidation_hunt | 14/50 | -0.41 | -26.9% |
| bollinger | 18/50 | -0.41 | -4.0% |
| flag | 12/50 | -0.41 | -17.8% |
| inside_bar | 22/50 | -0.41 | -3.4% |
| supertrend | 14/50 | -0.41 | -27.3% |
| cmf | 11/50 | -0.43 | -13.6% |
| atr_breakout | 13/50 | -0.44 | -9.6% |
| volume_momentum | 13/50 | -0.45 | -14.5% |
| trend_volume | 14/50 | -0.45 | -11.1% |
| impl_real_vol | 13/50 | -0.48 | -27.5% |
| vol_scaling | 13/50 | -0.48 | -27.5% |
| trend_mr | 14/50 | -0.48 | -10.9% |
| obv | 13/50 | -0.48 | -27.6% |
| gap | 13/50 | -0.49 | -29.6% |
| regime_switch | 8/50 | -0.49 | -20.1% |
| atr_trailing | 15/50 | -0.51 | -5.7% |
| keltner_momentum | 12/50 | -0.55 | -9.5% |
| nr4 | 12/50 | -0.59 | -10.1% |
| vol_target | 10/50 | -0.59 | -31.2% |
| vol_expansion | 8/50 | -1.07 | -8.5% |
| garch_classic | 8/40 | -1.93 | -2.7% |
| support | 0/1 | -2.21 | -4.4% |
| resistance | 1/4 | -2.43 | -1.0% |
| break_momentum | 2/13 | -2.72 | -1.8% |
| breakout_momentum | 2/13 | -2.72 | -1.8% |
| donchian | 2/13 | -2.72 | -1.8% |
| price_channel | 2/13 | -2.72 | -1.8% |
| rectangle | 2/13 | -2.72 | -1.8% |

### 4h · CNC(11+1)

| algo | wins | mean sharpe | median ret |
|---|---|---|---|
| anchored_vwap | 24/50 | -0.00 | -3.9% |
| vwap | 21/50 | -0.05 | -8.4% |
| gaussian | 25/50 | -0.07 | +0.6% |
| zscore | 26/50 | -0.07 | +1.8% |
| cointegration | 23/50 | -0.10 | -3.3% |
| spot_futures | 23/50 | -0.10 | -3.3% |
| stablecoin_peg | 20/50 | -0.12 | -5.2% |
| macd | 15/50 | -0.24 | -15.4% |
| macd_momentum | 15/50 | -0.24 | -15.4% |
| ma_cross | 10/50 | -0.30 | -20.2% |
| roll_cross | 10/50 | -0.30 | -20.2% |
| open_range | 15/49 | -0.32 | -12.2% |
| dual_momentum | 13/50 | -0.35 | -23.1% |
| ema_cross | 9/50 | -0.36 | -24.0% |
| mean_reversion | 20/50 | -0.40 | -4.1% |
| distance_ma | 14/50 | -0.40 | -7.1% |
| dual_ma | 14/50 | -0.40 | -23.1% |
| trend_following | 15/50 | -0.44 | -14.5% |
| funding_basis | 9/50 | -0.44 | -25.4% |
| linear_reg_channel | 9/50 | -0.44 | -25.4% |
| meta | 9/50 | -0.44 | -25.4% |
| regression | 9/50 | -0.44 | -25.4% |
| time_series | 10/50 | -0.45 | -29.0% |
| absolute_momentum | 8/50 | -0.47 | -26.2% |
| rsi | 12/50 | -0.48 | -8.8% |
| keltner | 11/50 | -0.48 | -7.8% |
| dema | 8/50 | -0.49 | -27.5% |
| hull | 8/50 | -0.49 | -27.5% |
| kama | 8/50 | -0.49 | -27.5% |
| tema | 8/50 | -0.49 | -27.5% |
| cumulative_delta | 10/50 | -0.51 | -31.6% |
| triple_ma | 9/50 | -0.53 | -23.6% |
| multi_factor | 6/50 | -0.54 | -28.4% |
| dispersion | 10/50 | -0.54 | -19.6% |
| rsi_momentum | 6/50 | -0.54 | -26.3% |
| trend_momentum | 5/50 | -0.55 | -22.8% |
| ensemble_signals | 8/50 | -0.55 | -30.3% |
| volume_profile | 7/50 | -0.57 | -28.3% |
| adaptive_allocation | 5/50 | -0.57 | -30.5% |
| momentum_factor | 5/50 | -0.57 | -30.5% |
| relative_strength | 5/50 | -0.57 | -30.5% |
| cci | 3/50 | -0.57 | -18.9% |
| funding_trend | 6/50 | -0.57 | -27.4% |
| momentum_vol | 3/50 | -0.59 | -28.6% |
| vw_momentum | 3/50 | -0.59 | -28.6% |
| basket | 4/50 | -0.59 | -28.3% |
| cross_sectional | 4/50 | -0.59 | -28.3% |
| corr_gate | 3/50 | -0.60 | -26.1% |
| trend_mr | 11/50 | -0.61 | -15.6% |
| mfi | 18/50 | -0.62 | -3.3% |
| volume_momentum | 8/50 | -0.65 | -22.1% |
| triangle | 5/50 | -0.65 | -21.2% |
| fisher | 3/50 | -0.69 | -34.6% |
| cmf | 6/50 | -0.71 | -24.9% |
| roc | 4/50 | -0.74 | -32.9% |
| stochastic | 3/50 | -0.75 | -27.9% |
| williams_r | 3/50 | -0.75 | -27.9% |
| atr_breakout | 3/50 | -0.79 | -22.3% |
| bollinger | 10/50 | -0.81 | -12.9% |
| atr_trailing | 6/50 | -0.82 | -14.4% |
| bb_squeeze2 | 4/50 | -0.83 | -47.8% |
| squeeze | 4/50 | -0.83 | -47.8% |
| keltner_momentum | 3/50 | -0.85 | -17.6% |
| trend_volume | 2/50 | -1.04 | -30.8% |
| inside_bar | 3/50 | -1.14 | -24.8% |
| flag | 2/50 | -1.16 | -46.5% |
| regime_switch | 1/50 | -1.31 | -54.0% |
| adx_trend | 1/50 | -1.32 | -69.4% |
| liquidation_hunt | 1/50 | -1.32 | -69.4% |
| supertrend | 1/50 | -1.34 | -70.1% |
| nr4 | 0/50 | -1.35 | -33.1% |
| obv | 1/50 | -1.47 | -70.2% |
| impl_real_vol | 1/50 | -1.48 | -70.4% |
| vol_scaling | 1/50 | -1.48 | -70.4% |
| gap | 1/50 | -1.50 | -71.4% |
| vol_target | 0/50 | -1.64 | -70.4% |
| garch_classic | 4/40 | -2.13 | -3.8% |
| support | 0/1 | -2.32 | -5.1% |
| vol_expansion | 0/50 | -2.33 | -28.1% |
| resistance | 0/4 | -2.59 | -1.8% |
| break_momentum | 1/13 | -2.82 | -2.5% |
| breakout_momentum | 1/13 | -2.82 | -2.5% |
| donchian | 1/13 | -2.82 | -2.5% |
| price_channel | 1/13 | -2.82 | -2.5% |
| rectangle | 1/13 | -2.82 | -2.5% |

