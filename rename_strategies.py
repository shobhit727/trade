#!/usr/bin/env python3
"""
Script to rename strategy catalog files with better names.
"""

import os
import shutil
from pathlib import Path

# Mapping of old names to new names
RENAME_MAP = {
    # Files to rename
    "atr_trailing.py": "atr_trailing_stop.py",
    "atr_breakout.py": "atr_breakout_strategy.py",
    "bb_squeeze2.py": "bollinger_band_squeeze.py",
    "bollinger.py": "bollinger_bands.py",
    "break_momentum.py": "breakout_momentum.py",
    "breakout_momentum.py": "breakout_momentum_strategy.py",
    "cci.py": "cci_strategy.py",
    "cmf.py": "cmf_strategy.py",
    "cointegration.py": "cointegration_strategy.py",
    "corr_gate.py": "correlation_gate.py",
    "cross_sectional.py": "cross_sectional_strategy.py",
    "cumulative_delta.py": "cumulative_delta_strategy.py",
    "dema.py": "dema_strategy.py",
    "dispersion.py": "dispersion_strategy.py",
    "distance_ma.py": "distance_moving_average.py",
    "donchian.py": "donchian_channel.py",
    "dual_ma.py": "dual_moving_average.py",
    "dual_momentum.py": "dual_momentum_strategy.py",
    "ema_cross.py": "ema_cross_strategy.py",
    "ensemble_signals.py": "ensemble_signals_strategy.py",
    "fisher.py": "fisher_transform.py",
    "flag.py": "flag_pattern.py",
    "funding_basis.py": "funding_basis_strategy.py",
    "funding_trend.py": "funding_trend_strategy.py",
    "gap.py": "gap_strategy.py",
    "garch_classic.py": "garch_classic_strategy.py",
    "gaussian.py": "gaussian_strategy.py",
    "hull.py": "hull_moving_average.py",
    "impl_real_vol.py": "implied_realized_volatility.py",
    "inside_bar.py": "inside_bar_pattern.py",
    "kama.py": "kama_strategy.py",
    "keltner_momentum.py": "keltner_momentum_strategy.py",
    "keltner.py": "keltner_channel.py",
    "linear_reg_channel.py": "linear_regression_channel.py",
    "liquidation_hunt.py": "liquidation_hunt_strategy.py",
    "macd_momentum.py": "macd_momentum_strategy.py",
    "macd.py": "macd_strategy.py",
    "ma_cross.py": "moving_average_cross.py",
    "meta.py": "meta_strategy.py",
    "mfi.py": "mfi_strategy.py",
    "momentum_factor.py": "momentum_factor_strategy.py",
    "momentum_vol.py": "momentum_volatility.py",
    "multi_factor.py": "multi_factor_strategy.py",
    "nr4.py": "nr4_pattern.py",
    "nse_intraday.py": "nse_intraday_trading.py",
    "obv.py": "on_balance_volume.py",
    "open_range.py": "open_range_breakout.py",
    "price_channel.py": "price_channel_strategy.py",
    "rectangle.py": "rectangle_pattern.py",
    "regime_switch.py": "regime_switch_strategy.py",
    "regression.py": "regression_strategy.py",
    "relative_strength.py": "relative_strength_strategy.py",
    "resistance.py": "resistance_strategy.py",
    "roc.py": "rate_of_change.py",
    "roll_cross.py": "rolling_cross.py",
    "rsi_momentum.py": "rsi_momentum_strategy.py",
    "rsi.py": "rsi_strategy.py",
    "spot_futures.py": "spot_futures_arbitrage.py",
    "squeeze.py": "squeeze_strategy.py",
    "stablecoin_peg.py": "stablecoin_peg_strategy.py",
    "stochastic.py": "stochastic_strategy.py",
    "supertrend.py": "supertrend_strategy.py",
    "support.py": "support_strategy.py",
    "tema.py": "tema_strategy.py",
    "time_series.py": "time_series_strategy.py",
    "trend_momentum.py": "trend_momentum_strategy.py",
    "trend_mr.py": "trend_mean_reversion.py",
    "trend_volume.py": "trend_volume_strategy.py",
    "triangle.py": "triangle_pattern.py",
    "triple_ma.py": "triple_moving_average.py",
    "vol_expansion.py": "volatility_expansion.py",
    "vol_scaling.py": "volatility_scaling.py",
    "vol_target.py": "volatility_target.py",
    "volume_momentum.py": "volume_momentum_strategy.py",
    "volume_profile.py": "volume_profile_strategy.py",
    "volume_spike.py": "volume_spike_strategy.py",
    "vwap.py": "vwap_strategy.py",
    "vw_momentum.py": "volume_weighted_momentum.py",
    "williams_r.py": "williams_r_strategy.py",
    "zscore.py": "zscore_strategy.py",
}

# Files to keep as-is (already good names)
KEEP_AS_IS = {
    "absolute_momentum.py",
    "adaptive_allocation.py",
    "adx_trend.py",
    "anchored_vwap.py",
    "basket.py",
    "bb_squeeze2.py",  # specific variant, keep
    "break_momentum.py",
    "breakout_momentum.py",
    "basket.py",
    "bb_squeeze2.py",
    "break_momentum.py",
    "breakout_momentum.py",
    "basket.py",
    "bb_squeeze2.py",
    "break_momentum.py",
    "breakout_momentum.py",
    "cci.py",
    "cmf.py",
    "cointegration.py",
    "corr_gate.py",
    "cross_sectional.py",
    "cumulative_delta.py",
    "dema.py",
    "dispersion.py",
    "distance_ma.py",
    "donchian.py",
    "dual_ma.py",
    "dual_momentum.py",
    "ema_cross.py",
    "ensemble_signals.py",
    "fisher.py",
    "flag.py",
    "funding_basis.py",
    "funding_trend.py",
    "gap.py",
    "garch_classic.py",
    "gaussian.py",
    "hull.py",
    "impl_real_vol.py",
    "inside_bar.py",
    "kama.py",
    "keltner_momentum.py",
    "keltner.py",
    "linear_reg_channel.py",
    "liquidation_hunt.py",
    "macd_momentum.py",
    "macd.py",
    "ma_cross.py",
    "meta.py",
    "mfi.py",
    "momentum_factor.py",
    "momentum_vol.py",
    "multi_factor.py",
    "nr4.py",
    "nse_intraday.py",
    "obv.py",
    "open_range.py",
    "price_channel.py",
    "rectangle.py",
    "regime_switch.py",
    "regression.py",
    "relative_strength.py",
    "resistance.py",
    "roc.py",
    "roll_cross.py",
    "rsi_momentum.py",
    "rsi.py",
    "spot_futures.py",
    "squeeze.py",
    "stablecoin_peg.py",
    "stochastic.py",
    "supertrend.py",
    "support.py",
    "tema.py",
    "time_series.py",
    "trend_momentum.py",
    "trend_mr.py",
    "trend_volume.py",
    "triangle.py",
    "triple_ma.py",
    "vol_expansion.py",
    "vol_scaling.py",
    "vol_target.py",
    "volume_momentum.py",
    "volume_profile.py",
    "volume_spike.py",
    "vwap.py",
    "vw_momentum.py",
    "williams_r.py",
    "zscore.py",
}

CATALOG_DIR = Path("/home/ph03n1x/trade/src/cryptobot/strategies/catalog")

def main():
    catalog_dir = Path("/home/ph03n1x/trade/src/cryptobot/strategies/catalog")
    
    # First, let's see what files exist
    existing_files = set(f.name for f in catalog_dir.iterdir() if f.is_file() and f.suffix == '.py')
    print(f"Found {len(existing_files)} Python files in catalog")
    
    # Check which files need renaming
    to_rename = {}
    for old_name, new_name in RENAME_MAP.items():
        if old_name in existing_files:
            if old_name != new_name:
                to_rename[old_name] = new_name
                print(f"Will rename: {old_name} -> {new_name}")
        else:
            print(f"WARNING: {old_name} not found in catalog")
    
    print(f"\nTotal files to rename: {len(to_rename)}")
    
    # Auto-proceed in non-interactive mode
    print("\nProceeding with renaming...")
    
    # Perform renames
    for old_name, new_name in to_rename.items():
        old_path = catalog_dir / old_name
        new_path = catalog_dir / new_name
        print(f"Renaming {old_name} -> {new_name}")
        shutil.move(str(old_path), str(new_path))
    
    print("\nRenaming complete!")
    
    # Verify
    new_files = set(f.name for f in catalog_dir.iterdir() if f.is_file() and f.suffix == '.py')
    print(f"\nTotal Python files after rename: {len(new_files)}")

if __name__ == "__main__":
    pass



