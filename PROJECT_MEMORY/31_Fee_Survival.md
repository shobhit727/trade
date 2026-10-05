# Fee survival — taker vs maker execution (2026-08-23 night analysis)

Sweep measured taker costs (5bps+3bps/side). Maker column re-prices
the same trade counts at 1bps maker / no slip. `flips` = losers at
taker that become winners at maker => maker-only execution candidates.

## BTCUSDT 1m

| survivor at taker | ret | | maker-flip candidates | ret(t) | ret(m) est |
|---|---|---|---|---|---|
| distance_ma | 0.3% | vol_target | -100.0% | 6784.9% | |
|  | | gap | -100.0% | 6784.9% | |
|  | | regime_switch | -100.0% | 6491.5% | |
|  | | flag | -100.0% | 5692.1% | |
|  | | fisher | -100.0% | 3691.5% | |
|  | | stochastic | -100.0% | 3337.0% | |
|  | | williams_r | -100.0% | 3337.0% | |
|  | | atr_breakout | -100.0% | 2828.5% | |

## BTCUSDT 5m

| survivor at taker | ret | | maker-flip candidates | ret(t) | ret(m) est |
|---|---|---|---|---|---|
| mfi | 11.3% | regime_switch | -100.0% | 2749.8% | |
| distance_ma | 1.1% | flag | -100.0% | 2334.0% | |
|  | | fisher | -100.0% | 1615.6% | |
|  | | vol_scaling | -100.0% | 1422.1% | |
|  | | stochastic | -100.0% | 1376.6% | |
|  | | williams_r | -100.0% | 1376.6% | |
|  | | ensemble_signals | -100.0% | 1145.4% | |
|  | | atr_breakout | -100.0% | 1125.8% | |

## BTCUSDT 15m

| survivor at taker | ret | | maker-flip candidates | ret(t) | ret(m) est |
|---|---|---|---|---|---|
| mfi | 34.2% | regime_switch | -100.0% | 1606.9% | |
| distance_ma | 10.9% | vol_scaling | -100.0% | 1568.0% | |
|  | | flag | -100.0% | 1272.4% | |
|  | | bb_squeeze2 | -100.0% | 1169.7% | |
|  | | squeeze | -100.0% | 1169.7% | |
|  | | fisher | -100.0% | 888.0% | |
|  | | stochastic | -100.0% | 749.0% | |
|  | | williams_r | -100.0% | 749.0% | |

## BTCUSDT 1h

| survivor at taker | ret | | maker-flip candidates | ret(t) | ret(m) est |
|---|---|---|---|---|---|
| volume_spike | 16.4% | vol_scaling | -100.0% | 1176.9% | |
| dual_ma | 8.7% | regime_switch | -100.0% | 755.4% | |
|  | | flag | -100.0% | 597.8% | |
|  | | fisher | -99.5% | 391.6% | |
|  | | stochastic | -98.9% | 320.5% | |
|  | | williams_r | -98.9% | 320.5% | |
|  | | atr_breakout | -98.8% | 242.1% | |
|  | | ensemble_signals | -98.5% | 237.2% | |

## BTCUSDT 4h

| survivor at taker | ret | | maker-flip candidates | ret(t) | ret(m) est |
|---|---|---|---|---|---|
| volume_spike | 183.7% | impl_real_vol | -99.8% | 261.3% | |
| trend_following | 52.4% | regime_switch | -99.0% | 229.6% | |
| open_range | 34.8% | bb_squeeze2 | -93.2% | 169.7% | |
| ma_cross | 16.2% | squeeze | -93.2% | 169.7% | |
| roll_cross | 16.2% | flag | -97.4% | 159.2% | |
| dual_ma | 11.5% | fisher | -92.2% | 86.4% | |
| time_series | 1.2% | rsi_momentum | -53.5% | 67.1% | |
|  | | stochastic | -92.5% | 54.9% | |

## BTCUSDT 1d

| survivor at taker | ret | | maker-flip candidates | ret(t) | ret(m) est |
|---|---|---|---|---|---|
| dual_momentum | 366.2% | break_momentum | -11.3% | 24.6% | |
| time_series | 336.6% | breakout_momentum | -11.3% | 24.6% | |
| ema_cross | 235.1% | donchian | -11.3% | 24.6% | |
| funding_basis | 193.5% | price_channel | -11.3% | 24.6% | |
| linear_reg_channel | 193.5% | rectangle | -11.3% | 24.6% | |
| meta | 193.5% | momentum_vol | -14.4% | 16.8% | |
| regression | 193.5% | flag | -56.6% | 15.0% | |
| absolute_momentum | 161.4% | atr_trailing | -14.9% | 14.6% | |

## ETHUSDT 1m

| survivor at taker | ret | | maker-flip candidates | ret(t) | ret(m) est |
|---|---|---|---|---|---|
| volume_spike | 5.5% | gap | -100.0% | 6969.7% | |
| distance_ma | 4.1% | vol_target | -100.0% | 6968.2% | |
|  | | regime_switch | -1265.8% | 6306.4% | |
|  | | flag | -100.0% | 5887.1% | |
|  | | bb_squeeze2 | -1040.3% | 5434.7% | |
|  | | squeeze | -1040.3% | 5434.7% | |
|  | | fisher | -100.0% | 3894.5% | |
|  | | nr4 | -2559.2% | 3735.4% | |

## ETHUSDT 5m

| survivor at taker | ret | | maker-flip candidates | ret(t) | ret(m) est |
|---|---|---|---|---|---|
| mfi | 16.5% | vol_target | -100.0% | 3243.8% | |
|  | | gap | -100.0% | 3230.2% | |
|  | | regime_switch | -100.0% | 2835.5% | |
|  | | bb_squeeze2 | -273.3% | 2374.0% | |
|  | | squeeze | -273.3% | 2374.0% | |
|  | | flag | -100.0% | 2350.7% | |
|  | | vol_scaling | -100.0% | 1979.0% | |
|  | | adx_trend | -1024.4% | 1663.7% | |

## ETHUSDT 15m

| survivor at taker | ret | | maker-flip candidates | ret(t) | ret(m) est |
|---|---|---|---|---|---|
| mfi | 31.2% | vol_scaling | -100.0% | 1944.0% | |
|  | | gap | -879.8% | 1824.8% | |
|  | | vol_target | -879.5% | 1820.5% | |
|  | | regime_switch | -100.0% | 1675.1% | |
|  | | bb_squeeze2 | -100.0% | 1320.9% | |
|  | | squeeze | -100.0% | 1320.9% | |
|  | | flag | -100.0% | 1277.5% | |
|  | | fisher | -100.0% | 907.6% | |

## ETHUSDT 1h

| survivor at taker | ret | | maker-flip candidates | ret(t) | ret(m) est |
|---|---|---|---|---|---|
| open_range | 34.0% | vol_target | -100.0% | 1081.0% | |
| mfi | 30.9% | gap | -321.8% | 941.7% | |
| trend_mr | 22.7% | vol_scaling | -319.6% | 933.5% | |
| ema_cross | 0.4% | regime_switch | -100.0% | 767.0% | |
|  | | flag | -100.0% | 587.6% | |
|  | | bb_squeeze2 | -297.2% | 456.0% | |
|  | | squeeze | -297.2% | 456.0% | |
|  | | impl_real_vol | -99.9% | 413.1% | |

## ETHUSDT 4h

| survivor at taker | ret | | maker-flip candidates | ret(t) | ret(m) est |
|---|---|---|---|---|---|
| open_range | 288.2% | vol_target | -99.5% | 405.9% | |
| macd | 152.7% | gap | -56.0% | 350.8% | |
| macd_momentum | 152.7% | supertrend | -67.1% | 341.5% | |
| time_series | 63.8% | adx_trend | -67.1% | 341.1% | |
| trend_mr | 59.7% | liquidation_hunt | -67.1% | 341.1% | |
| triple_ma | 58.7% | impl_real_vol | -99.0% | 333.6% | |
| dual_ma | 45.9% | vol_scaling | -97.5% | 314.2% | |
| volume_spike | 33.6% | regime_switch | -92.9% | 228.4% | |

## ETHUSDT 1d

| survivor at taker | ret | | maker-flip candidates | ret(t) | ret(m) est |
|---|---|---|---|---|---|
| absolute_momentum | 1689.1% | vol_target | -22.1% | 27.1% | |
| dema | 1093.9% | bb_squeeze2 | -16.1% | 26.1% | |
| hull | 1093.9% | squeeze | -16.1% | 26.1% | |
| kama | 1093.9% | dispersion | -0.1% | 9.3% | |
| tema | 1093.9% | regime_switch | -80.4% | 7.2% | |
| time_series | 688.8% | volume_profile | -24.9% | 6.0% | |
| macd | 447.9% |  | | |
| macd_momentum | 447.9% |  | | |
