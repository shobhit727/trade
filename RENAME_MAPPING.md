# Strategy Catalog Rename Mapping

## Files to Rename

| Old Name | New Name | Reason |
|----------|----------|--------|
| atr_trailing.py | atr_trailing_stop.py | Clearer: it's a trailing stop using ATR |
| atr_breakout.py | atr_breakout_strategy.py | Clearer: it's a breakout strategy using ATR |
| bb_squeeze2.py | bollinger_band_squeeze.py | Remove version number, use full name |
| bollinger.py | bollinger_bands.py | Plural for consistency |
| break_momentum.py | breakout_momentum.py | Clearer: breakout momentum strategy |
| breakout_momentum.py | breakout_momentum_strategy.py | Consistent naming |
| cci.py | cci_strategy.py | Add _strategy suffix for clarity |
| cmf.py | cmf_strategy.py | Add _strategy suffix |
| cointegration.py | cointegration_strategy.py | Add _strategy suffix |
| corr_gate.py | correlation_gate.py | Full word instead of abbreviation |
| cross_sectional.py | cross_sectional_strategy.py | Add _strategy suffix |
| cumulative_delta.py | cumulative_delta_strategy.py | Add _strategy suffix |
| dema.py | dema_strategy.py | Add _strategy suffix |
| dispersion.py | dispersion_strategy.py | Add _strategy suffix |
| distance_ma.py | distance_moving_average.py | Full name instead of abbreviation |
| donchian.py | donchian_channel.py | Clearer: Donchian channel strategy |
| dual_ma.py | dual_moving_average.py | Full name instead of abbreviation |
| dual_momentum.py | dual_momentum_strategy.py | Add _strategy suffix |
| ema_cross.py | ema_cross_strategy.py | Add _strategy suffix |
| ensemble_signals.py | ensemble_signals_strategy.py | Add _strategy suffix |
| fisher.py | fisher_transform.py | Full name |
| flag.py | flag_pattern.py | More descriptive |
| funding_basis.py | funding_basis_strategy.py | Add _strategy suffix |
| funding_trend.py | funding_trend_strategy.py | Add _strategy suffix |
| gap.py | gap_strategy.py | Add _strategy suffix |
| garch_classic.py | garch_classic_strategy.py | Add _strategy suffix |
| gaussian.py | gaussian_strategy.py | Add _strategy suffix |
| hull.py | hull_moving_average.py | Full name |
| impl_real_vol.py | implied_realized_volatility.py | Full descriptive name |
| inside_bar.py | inside_bar_pattern.py | More descriptive |
| kama.py | kama_strategy.py | Add _strategy suffix |
| keltner_momentum.py | keltner_momentum_strategy.py | Add _strategy suffix |
| keltner.py | keltner_channel.py | Clearer: Keltner channel strategy |
| linear_reg_channel.py | linear_regression_channel.py | Full name |
| liquidation_hunt.py | liquidation_hunt_strategy.py | Add _strategy suffix |
| macd_momentum.py | macd_momentum_strategy.py | Add _strategy suffix |
| macd.py | macd_strategy.py | Add _strategy suffix |
| ma_cross.py | moving_average_cross.py | Full name |
| meta.py | meta_strategy.py | Add _strategy suffix |
| mfi.py | mfi_strategy.py | Add _strategy suffix |
| momentum_factor.py | momentum_factor_strategy.py | Add _strategy suffix |
| momentum_vol.py | momentum_volatility.py | Full word |
| multi_factor.py | multi_factor_strategy.py | Add _strategy suffix |
| nr4.py | nr4_pattern.py | More descriptive |
| nse_intraday.py | nse_intraday_trading.py | More descriptive |
| obv.py | on_balance_volume.py | Full name |
| open_range.py | open_range_breakout.py | More descriptive |
| price_channel.py | price_channel_strategy.py | Add _strategy suffix |
| rectangle.py | rectangle_pattern.py | More descriptive |
| regime_switch.py | regime_switch_strategy.py | Add _strategy suffix |
| regression.py | regression_strategy.py | Add _strategy suffix |
| relative_strength.py | relative_strength_strategy.py | Add _strategy suffix |
| resistance.py | resistance_strategy.py | Add _strategy suffix |
| roc.py | rate_of_change.py | Full name |
| roll_cross.py | rolling_cross.py | Full word |
| rsi_momentum.py | rsi_momentum_strategy.py | Add _strategy suffix |
| rsi.py | rsi_strategy.py | Add _strategy suffix |
| spot_futures.py | spot_futures_arbitrage.py | More descriptive |
| squeeze.py | squeeze_strategy.py | Add _strategy suffix |
| stablecoin_peg.py | stablecoin_peg_strategy.py | Add _strategy suffix |
| stochastic.py | stochastic_strategy.py | Add _strategy suffix |
| supertrend.py | supertrend_strategy.py | Add _strategy suffix |
| support.py | support_strategy.py | Add _strategy suffix |
| tema.py | tema_strategy.py | Add _strategy suffix |
| time_series.py | time_series_strategy.py | Add _strategy suffix |
| trend_momentum.py | trend_momentum_strategy.py | Add _strategy suffix |
| trend_mr.py | trend_mean_reversion.py | Full name |
| trend_volume.py | trend_volume_strategy.py | Add _strategy suffix |
| triangle.py | triangle_pattern.py | More descriptive |
| triple_ma.py | triple_moving_average.py | Full name |
| vol_expansion.py | volatility_expansion.py | Full word |
| vol_scaling.py | volatility_scaling.py | Full word |
| vol_target.py | volatility_target.py | Full word |
| volume_momentum.py | volume_momentum_strategy.py | Add _strategy suffix |
| volume_profile.py | volume_profile_strategy.py | Add _strategy suffix |
| volume_spike.py | volume_spike_strategy.py | Add _strategy suffix |
| vwap.py | vwap_strategy.py | Add _strategy suffix |
| vw_momentum.py | volume_weighted_momentum.py | Full name |
| williams_r.py | williams_r_strategy.py | Add _strategy suffix |
| zscore.py | zscore_strategy.py | Add _strategy suffix |

## Files to Keep As-Is (Already Good Names)
- absolute_momentum.py
- adaptive_allocation.py
- adx_trend.py
- anchored_vwap.py
- basket.py
- bb_squeeze2.py (could be bollinger_band_squeeze.py but it's a specific variant)
- break_momentum.py
- breakout_momentum.py
- basket.py
- bb_squeeze2.py (specific variant, keep)
- break_momentum.py
- breakout_momentum.py
- basket.py
- bb_squeeze2.py
- break_momentum.py
- breakout_momentum.py
- cci.py -> cci_strategy.py
- cmf.py -> cmf_strategy.py
- cointegration.py -> cointegration_strategy.py
- corr_gate.py -> correlation_gate.py
- cross_sectional.py -> cross_sectional_strategy.py
- cumulative_delta.py -> cumulative_delta_strategy.py
- dema.py -> dema_strategy.py
- dispersion.py -> dispersion_strategy.py
- distance_ma.py -> distance_moving_average.py
- donchian.py -> donchian_channel.py
- dual_ma.py -> dual_moving_average.py
- dual_momentum.py -> dual_momentum_strategy.py
- ema_cross.py -> ema_cross_strategy.py
- ensemble_signals.py -> ensemble_signals_strategy.py
- fisher.py -> fisher_transform.py
- flag.py -> flag_pattern.py
- funding_basis.py -> funding_basis_strategy.py
- funding_trend.py -> funding_trend_strategy.py
- gap.py -> gap_strategy.py
- garch_classic.py -> garch_classic_strategy.py
- gaussian.py -> gaussian_strategy.py
- hull.py -> hull_moving_average.py
- impl_real_vol.py -> implied_realized_volatility.py
- inside_bar.py -> inside_bar_pattern.py
- kama.py -> kama_strategy.py
- keltner_momentum.py -> keltner_momentum_strategy.py
- keltner.py -> keltner_channel.py
- linear_reg_channel.py -> linear_regression_channel.py
- liquidation_hunt.py -> liquidation_hunt_strategy.py
- macd_momentum.py -> macd_momentum_strategy.py
- macd.py -> macd_strategy.py
- ma_cross.py -> moving_average_cross.py
- meta.py -> meta_strategy.py
- mfi.py -> mfi_strategy.py
- momentum_factor.py -> momentum_factor_strategy.py
- momentum_vol.py -> momentum_volatility.py
- multi_factor.py -> multi_factor_strategy.py
- nr4.py -> nr4_pattern.py
- nse_intraday.py -> nse_intraday_trading.py
- obv.py -> on_balance_volume.py
- open_range.py -> open_range_breakout.py
- price_channel.py -> price_channel_strategy.py
- rectangle.py -> rectangle_pattern.py
- regime_switch.py -> regime_switch_strategy.py
- regression.py -> regression_strategy.py
- relative_strength.py -> relative_strength_strategy.py
- resistance.py -> resistance_strategy.py
- roc.py -> rate_of_change.py
- roll_cross.py -> rolling_cross.py
- rsi_momentum.py -> rsi_momentum_strategy.py
- rsi.py -> rsi_strategy.py
- spot_futures.py -> spot_futures_arbitrage.py
- squeeze.py -> squeeze_strategy.py
- stablecoin_peg.py -> stablecoin_peg_strategy.py
- stochastic.py -> stochastic_strategy.py
- supertrend.py -> supertrend_strategy.py
- support.py -> support_strategy.py
- tema.py -> tema_strategy.py
- time_series.py -> time_series_strategy.py
- trend_momentum.py -> trend_momentum_strategy.py
- trend_mr.py -> trend_mean_reversion.py
- trend_volume.py -> trend_volume_strategy.py
- triangle.py -> triangle_pattern.py
- triple_ma.py -> triple_moving_average.py
- vol_expansion.py -> volatility_expansion.py
- vol_scaling.py -> volatility_scaling.py
- vol_target.py -> volatility_target.py
- volume_momentum.py -> volume_momentum_strategy.py
- volume_profile.py -> volume_profile_strategy.py
- volume_spike.py -> volume_spike_strategy.py
- vwap.py -> vwap_strategy.py
- vw_momentum.py -> volume_weighted_momentum.py
- williams_r.py -> williams_r_strategy.py
- zscore.py -> zscore_strategy.py