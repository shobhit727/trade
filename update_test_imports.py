#!/usr/bin/env python3
"""
Script to update test file imports to use new module names.
"""

import re
from pathlib import Path

# Mapping of old module names to new names
RENAME_MAP = {
    "atr_trailing": "atr_trailing_stop",
    "atr_breakout": "atr_breakout_strategy",
    "bb_squeeze2": "bollinger_band_squeeze",
    "bollinger": "bollinger_bands",
    "break_momentum": "breakout_momentum",
    "breakout_momentum": "breakout_momentum_strategy",
    "cci": "cci_strategy",
    "cmf": "cmf_strategy",
    "cointegration": "cointegration_strategy",
    "corr_gate": "correlation_gate",
    "cross_sectional": "cross_sectional_strategy",
    "cumulative_delta": "cumulative_delta_strategy",
    "dema": "dema_strategy",
    "dispersion": "dispersion_strategy",
    "distance_ma": "distance_moving_average",
    "donchian": "donchian_channel",
    "dual_ma": "dual_moving_average",
    "dual_momentum": "dual_momentum_strategy",
    "ema_cross": "ema_cross_strategy",
    "ensemble_signals": "ensemble_signals_strategy",
    "fisher": "fisher_transform",
    "flag": "flag_pattern",
    "funding_basis": "funding_basis_strategy",
    "funding_trend": "funding_trend_strategy",
    "gap": "gap_strategy",
    "garch_classic": "garch_classic_strategy",
    "gaussian": "gaussian_strategy",
    "hull": "hull_moving_average",
    "impl_real_vol": "implied_realized_volatility",
    "inside_bar": "inside_bar_pattern",
    "kama": "kama_strategy",
    "keltner_momentum": "keltner_momentum_strategy",
    "keltner": "keltner_channel",
    "linear_reg_channel": "linear_regression_channel",
    "liquidation_hunt": "liquidation_hunt_strategy",
    "macd_momentum": "macd_momentum_strategy",
    "macd": "macd_strategy",
    "ma_cross": "moving_average_cross",
    "meta": "meta_strategy",
    "mfi": "mfi_strategy",
    "momentum_factor": "momentum_factor_strategy",
    "momentum_vol": "momentum_volatility",
    "multi_factor": "multi_factor_strategy",
    "nr4": "nr4_pattern",
    "nse_intraday": "nse_intraday_trading",
    "obv": "on_balance_volume",
    "open_range": "open_range_breakout",
    "price_channel": "price_channel_strategy",
    "rectangle": "rectangle_pattern",
    "regime_switch": "regime_switch_strategy",
    "regression": "regression_strategy",
    "relative_strength": "relative_strength_strategy",
    "resistance": "resistance_strategy",
    "roc": "rate_of_change",
    "roll_cross": "rolling_cross",
    "rsi_momentum": "rsi_momentum_strategy",
    "rsi": "rsi_strategy",
    "spot_futures": "spot_futures_arbitrage",
    "squeeze": "squeeze_strategy",
    "stablecoin_peg": "stablecoin_peg_strategy",
    "stochastic": "stochastic_strategy",
    "supertrend": "supertrend_strategy",
    "support": "support_strategy",
    "tema": "tema_strategy",
    "time_series": "time_series_strategy",
    "trend_momentum": "trend_momentum_strategy",
    "trend_mr": "trend_mean_reversion",
    "trend_volume": "trend_volume_strategy",
    "triangle": "triangle_pattern",
    "triple_ma": "triple_moving_average",
    "vol_expansion": "volatility_expansion",
    "vol_scaling": "volatility_scaling",
    "vol_target": "volatility_target",
    "volume_momentum": "volume_momentum_strategy",
    "volume_profile": "volume_profile_strategy",
    "volume_spike": "volume_spike_strategy",
    "vwap": "vwap_strategy",
    "vw_momentum": "volume_weighted_momentum",
    "williams_r": "williams_r_strategy",
    "zscore": "zscore_strategy",
}

# Files that don't need changes (already have good names)
KEEP_AS_IS = {
    "absolute_momentum",
    "adaptive_allocation",
    "adx_trend",
    "anchored_vwap",
    "basket",
    "bb_squeeze2",
    "break_momentum",
    "breakout_momentum",
    "basket",
    "bb_squeeze2",
    "break_momentum",
    "breakout_momentum",
    "cci",
    "cmf",
    "cointegration",
    "corr_gate",
    "cross_sectional",
    "cumulative_delta",
    "dema",
    "dispersion",
    "distance_ma",
    "donchian",
    "dual_ma",
    "dual_momentum",
    "ema_cross",
    "ensemble_signals",
    "fisher",
    "flag",
    "funding_basis",
    "funding_trend",
    "gap",
    "garch_classic",
    "gaussian",
    "hull",
    "impl_real_vol",
    "inside_bar",
    "kama",
    "keltner_momentum",
    "keltner",
    "linear_reg_channel",
    "liquidation_hunt",
    "macd_momentum",
    "macd",
    "ma_cross",
    "meta",
    "mfi",
    "momentum_factor",
    "momentum_vol",
    "multi_factor",
    "nr4",
    "nse_intraday",
    "obv",
    "open_range",
    "price_channel",
    "rectangle",
    "regime_switch",
    "regression",
    "relative_strength",
    "resistance",
    "roc",
    "roll_cross",
    "rsi_momentum",
    "rsi",
    "spot_futures",
    "squeeze",
    "stablecoin_peg",
    "stochastic",
    "supertrend",
    "support",
    "tema",
    "time_series",
    "trend_momentum",
    "trend_mr",
    "trend_volume",
    "triangle",
    "triple_ma",
    "vol_expansion",
    "vol_scaling",
    "vol_target",
    "volume_momentum",
    "volume_profile",
    "volume_spike",
    "vwap",
    "vw_momentum",
    "williams_r",
    "zscore",
}

def update_test_file(filepath: Path):
    """Update a single test file to use new import paths."""
    content = filepath.read_text()
    original = content
    
    # Replace imports
    for old_name, new_name in RENAME_MAP.items():
        # Pattern: from cryptobot.strategies.catalog.old_name import ...
        old_import = f"from cryptobot.strategies.catalog.{old_name} import"
        new_import = f"from cryptobot.strategies.catalog.{new_name} import"
        if old_import in content:
            content = content.replace(old_import, new_import)
    
    if content != original:
        filepath.write_text(content)
        return True
    return False

def main():
    test_dir = Path("/home/ph03n1x/trade/tests")
    
    # Find all test files that import from catalog
    test_files = list(Path("/home/ph03n1x/trade/tests").rglob("test_*.py"))
    
    updated = 0
    for filepath in test_files:
        if filepath.name.startswith("test_") and filepath.suffix == ".py":
            if update_test_file(filepath):
                print(f"Updated: {filepath}")
                updated += 1
    
    print(f"\nUpdated {updated} test files")

if __name__ == "__main__":
    main()