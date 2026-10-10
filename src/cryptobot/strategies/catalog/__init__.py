"""Catalog of signal strategies (one module per strategy)."""

from __future__ import annotations

from cryptobot.strategies.catalog.absolute_momentum import AbsoluteMomentumConfig, AbsoluteMomentumStrategy
from cryptobot.strategies.catalog.adaptive_allocation import (
    AdaptiveAllocationConfig,
    AdaptiveAllocationStrategy,
)
from cryptobot.strategies.catalog.adx_trend import AdxTrendConfig, AdxTrendStrategy
from cryptobot.strategies.catalog.anchored_vwap import AnchoredVwapConfig, AnchoredVwapStrategy
from cryptobot.strategies.catalog.atr_breakout_strategy import AtrBreakoutConfig, AtrBreakoutStrategy
from cryptobot.strategies.catalog.atr_trailing_stop import AtrTrailingConfig, AtrTrailingStrategy
from cryptobot.strategies.catalog.basket import BasketConfig, BasketStrategy
from cryptobot.strategies.catalog.bollinger_band_squeeze import BbSqueeze2Config, BbSqueeze2Strategy
from cryptobot.strategies.catalog.bollinger_bands import BollingerBandsConfig, BollingerBandsStrategy
from cryptobot.strategies.catalog.breakout_momentum_strategy import (
    BreakoutMomentumConfig,
    BreakoutMomentumStrategy,
)
from cryptobot.strategies.catalog.cci_strategy import CciConfig, CciStrategy
from cryptobot.strategies.catalog.cmf_strategy import CmfConfig, CmfStrategy
from cryptobot.strategies.catalog.cointegration_strategy import CointegrationConfig, CointegrationStrategy
from cryptobot.strategies.catalog.correlation_gate import CorrGateConfig, CorrGateStrategy
from cryptobot.strategies.catalog.cross_sectional_strategy import CrossSectionalConfig, CrossSectionalStrategy
from cryptobot.strategies.catalog.cumulative_delta_strategy import (
    CumulativeDeltaConfig,
    CumulativeDeltaStrategy,
)
from cryptobot.strategies.catalog.dema_strategy import DemaConfig, DemaStrategy
from cryptobot.strategies.catalog.dispersion_strategy import DispersionConfig, DispersionStrategy
from cryptobot.strategies.catalog.distance_moving_average import DistanceMaConfig, DistanceMaStrategy
from cryptobot.strategies.catalog.donchian_channel import DonchianConfig, DonchianStrategy
from cryptobot.strategies.catalog.dual_momentum_strategy import DualMomentumConfig, DualMomentumStrategy
from cryptobot.strategies.catalog.dual_moving_average import (
    DualMovingAverageConfig,
    DualMovingAverageStrategy,
)
from cryptobot.strategies.catalog.ema_cross_strategy import EmaCrossConfig, EmaCrossStrategy
from cryptobot.strategies.catalog.ensemble_signals_strategy import (
    EnsembleSignalsConfig,
    EnsembleSignalsStrategy,
)
from cryptobot.strategies.catalog.fisher_transform import FisherConfig, FisherStrategy
from cryptobot.strategies.catalog.flag_pattern import FlagConfig, FlagStrategy
from cryptobot.strategies.catalog.funding_basis_strategy import FundingBasisConfig, FundingBasisStrategy
from cryptobot.strategies.catalog.funding_trend_strategy import FundingTrendConfig, FundingTrendStrategy
from cryptobot.strategies.catalog.gap_strategy import GapConfig, GapStrategy
from cryptobot.strategies.catalog.garch_classic_strategy import GarchClassicConfig, GarchClassicStrategy
from cryptobot.strategies.catalog.gaussian_strategy import GaussianConfig, GaussianStrategy
from cryptobot.strategies.catalog.hull_moving_average import HullConfig, HullStrategy
from cryptobot.strategies.catalog.implied_realized_volatility import ImplRealVolConfig, ImplRealVolStrategy
from cryptobot.strategies.catalog.inside_bar_pattern import InsideBarConfig, InsideBarStrategy
from cryptobot.strategies.catalog.kama_strategy import KamaConfig, KamaStrategy
from cryptobot.strategies.catalog.keltner_channel import KeltnerConfig, KeltnerStrategy
from cryptobot.strategies.catalog.keltner_momentum_strategy import (
    KeltnerMomentumConfig,
    KeltnerMomentumStrategy,
)
from cryptobot.strategies.catalog.linear_regression_channel import (
    LinearRegChannelConfig,
    LinearRegChannelStrategy,
)
from cryptobot.strategies.catalog.liquidation_hunt_strategy import (
    LiquidationHuntConfig,
    LiquidationHuntStrategy,
)
from cryptobot.strategies.catalog.macd_momentum_strategy import MacdMomentumConfig, MacdMomentumStrategy
from cryptobot.strategies.catalog.macd_strategy import MacdConfig, MacdStrategy
from cryptobot.strategies.catalog.meta_strategy import MetaStrategy, MetaStrategyConfig
from cryptobot.strategies.catalog.mfi_strategy import MfiConfig, MfiStrategy
from cryptobot.strategies.catalog.momentum_factor_strategy import MomentumFactorConfig, MomentumFactorStrategy
from cryptobot.strategies.catalog.momentum_volatility import MomentumVolConfig, MomentumVolStrategy
from cryptobot.strategies.catalog.moving_average_cross import MaCrossConfig, MaCrossStrategy
from cryptobot.strategies.catalog.multi_factor_strategy import MultiFactorConfig, MultiFactorStrategy
from cryptobot.strategies.catalog.nr4_pattern import Nr4Config, Nr4Strategy
from cryptobot.strategies.catalog.nse_intraday_trading import (
    NseOrbConfig,
    NseOrbStrategy,
    VwapRevertConfig,
    VwapRevertStrategy,
)
from cryptobot.strategies.catalog.on_balance_volume import ObvConfig, ObvStrategy
from cryptobot.strategies.catalog.open_range_breakout import OpenRangeConfig, OpenRangeStrategy
from cryptobot.strategies.catalog.price_channel_strategy import PriceChannelConfig, PriceChannelStrategy
from cryptobot.strategies.catalog.rate_of_change import RocConfig, RocStrategy
from cryptobot.strategies.catalog.rectangle_pattern import RectangleConfig, RectangleStrategy
from cryptobot.strategies.catalog.regime_switch_strategy import RegimeSwitchConfig, RegimeSwitchStrategy
from cryptobot.strategies.catalog.regression_strategy import RegressionConfig, RegressionStrategy
from cryptobot.strategies.catalog.relative_strength_strategy import (
    RelativeStrengthConfig,
    RelativeStrengthStrategy,
)
from cryptobot.strategies.catalog.resistance_strategy import ResistanceConfig, ResistanceStrategy
from cryptobot.strategies.catalog.rolling_cross import RollCrossConfig, RollCrossStrategy
from cryptobot.strategies.catalog.rsi_momentum_strategy import RsiMomentumConfig, RsiMomentumStrategy
from cryptobot.strategies.catalog.rsi_strategy import RsiConfig, RsiStrategy
from cryptobot.strategies.catalog.spot_futures_arbitrage import SpotFuturesConfig, SpotFuturesStrategy
from cryptobot.strategies.catalog.squeeze_strategy import SqueezeConfig, SqueezeStrategy
from cryptobot.strategies.catalog.stablecoin_peg_strategy import StablecoinPegConfig, StablecoinPegStrategy
from cryptobot.strategies.catalog.stochastic_strategy import StochasticConfig, StochasticStrategy
from cryptobot.strategies.catalog.supertrend_strategy import SupertrendConfig, SupertrendStrategy
from cryptobot.strategies.catalog.support_strategy import SupportConfig, SupportStrategy
from cryptobot.strategies.catalog.tema_strategy import TemaConfig, TemaStrategy
from cryptobot.strategies.catalog.time_series_strategy import TimeSeriesConfig, TimeSeriesStrategy
from cryptobot.strategies.catalog.trend_mean_reversion import TrendMrConfig, TrendMrStrategy
from cryptobot.strategies.catalog.trend_momentum_strategy import TrendMomentumConfig, TrendMomentumStrategy
from cryptobot.strategies.catalog.trend_volume_strategy import TrendVolumeConfig, TrendVolumeStrategy
from cryptobot.strategies.catalog.triangle_pattern import TriangleConfig, TriangleStrategy
from cryptobot.strategies.catalog.triple_moving_average import TripleMaConfig, TripleMaStrategy
from cryptobot.strategies.catalog.volatility_expansion import VolExpansionConfig, VolExpansionStrategy
from cryptobot.strategies.catalog.volatility_scaling import VolScalingConfig, VolScalingStrategy
from cryptobot.strategies.catalog.volatility_target import VolTargetConfig, VolTargetStrategy
from cryptobot.strategies.catalog.volume_momentum_strategy import VolumeMomentumConfig, VolumeMomentumStrategy
from cryptobot.strategies.catalog.volume_profile_strategy import VolumeProfileConfig, VolumeProfileStrategy
from cryptobot.strategies.catalog.volume_spike_strategy import VolumeSpikeConfig, VolumeSpikeStrategy
from cryptobot.strategies.catalog.volume_weighted_momentum import VwMomentumConfig, VwMomentumStrategy
from cryptobot.strategies.catalog.vwap_strategy import VwapConfig, VwapStrategy
from cryptobot.strategies.catalog.williams_r_strategy import WilliamsRConfig, WilliamsRStrategy
from cryptobot.strategies.catalog.zscore_strategy import ZscoreConfig, ZscoreStrategy

_SPEC: list[tuple[str, type, type]] = [
    ("absolute_momentum", AbsoluteMomentumStrategy, AbsoluteMomentumConfig),
    ("adaptive_allocation", AdaptiveAllocationStrategy, AdaptiveAllocationConfig),
    ("adx_trend", AdxTrendStrategy, AdxTrendConfig),
    ("anchored_vwap", AnchoredVwapStrategy, AnchoredVwapConfig),
    ("atr_breakout", AtrBreakoutStrategy, AtrBreakoutConfig),
    ("atr_trailing", AtrTrailingStrategy, AtrTrailingConfig),
    ("basket", BasketStrategy, BasketConfig),
    ("bollinger_band_squeeze", BbSqueeze2Strategy, BbSqueeze2Config),
    ("bollinger_bands", BollingerBandsStrategy, BollingerBandsConfig),
    ("breakout_momentum_strategy", BreakoutMomentumStrategy, BreakoutMomentumConfig),
    ("cci_strategy", CciStrategy, CciConfig),
    ("cmf_strategy", CmfStrategy, CmfConfig),
    ("cointegration_strategy", CointegrationStrategy, CointegrationConfig),
    ("correlation_gate", CorrGateStrategy, CorrGateConfig),
    ("cross_sectional_strategy", CrossSectionalStrategy, CrossSectionalConfig),
    ("cumulative_delta_strategy", CumulativeDeltaStrategy, CumulativeDeltaConfig),
    ("dema_strategy", DemaStrategy, DemaConfig),
    ("dispersion_strategy", DispersionStrategy, DispersionConfig),
    ("distance_moving_average", DistanceMaStrategy, DistanceMaConfig),
    ("donchian_channel", DonchianStrategy, DonchianConfig),
    ("dual_moving_average", DualMovingAverageStrategy, DualMovingAverageConfig),
    ("dual_momentum_strategy", DualMomentumStrategy, DualMomentumConfig),
    ("ema_cross_strategy", EmaCrossStrategy, EmaCrossConfig),
    ("ensemble_signals_strategy", EnsembleSignalsStrategy, EnsembleSignalsConfig),
    ("fisher_transform", FisherStrategy, FisherConfig),
    ("flag_pattern", FlagStrategy, FlagConfig),
    ("funding_basis_strategy", FundingBasisStrategy, FundingBasisConfig),
    ("funding_trend_strategy", FundingTrendStrategy, FundingTrendConfig),
    ("gap_strategy", GapStrategy, GapConfig),
    ("garch_classic_strategy", GarchClassicStrategy, GarchClassicConfig),
    ("gaussian_strategy", GaussianStrategy, GaussianConfig),
    ("hull_moving_average", HullStrategy, HullConfig),
    ("implied_realized_volatility", ImplRealVolStrategy, ImplRealVolConfig),
    ("inside_bar_pattern", InsideBarStrategy, InsideBarConfig),
    ("kama_strategy", KamaStrategy, KamaConfig),
    ("keltner_channel", KeltnerStrategy, KeltnerConfig),
    ("keltner_momentum_strategy", KeltnerMomentumStrategy, KeltnerMomentumConfig),
    ("linear_regression_channel", LinearRegChannelStrategy, LinearRegChannelConfig),
    ("liquidation_hunt_strategy", LiquidationHuntStrategy, LiquidationHuntConfig),
    ("macd_strategy", MacdStrategy, MacdConfig),
    ("macd_momentum_strategy", MacdMomentumStrategy, MacdMomentumConfig),
    ("moving_average_cross", MaCrossStrategy, MaCrossConfig),
    ("meta_strategy", MetaStrategy, MetaStrategyConfig),
    ("mfi_strategy", MfiStrategy, MfiConfig),
    ("momentum_factor_strategy", MomentumFactorStrategy, MomentumFactorConfig),
    ("momentum_volatility", MomentumVolStrategy, MomentumVolConfig),
    ("multi_factor_strategy", MultiFactorStrategy, MultiFactorConfig),
    ("nr4_pattern", Nr4Strategy, Nr4Config),
    ("nse_intraday_trading", NseOrbStrategy, NseOrbConfig),
    ("vwap_revert", VwapRevertStrategy, VwapRevertConfig),
    ("on_balance_volume", ObvStrategy, ObvConfig),
    ("open_range_breakout", OpenRangeStrategy, OpenRangeConfig),
    ("price_channel_strategy", PriceChannelStrategy, PriceChannelConfig),
    ("rectangle_pattern", RectangleStrategy, RectangleConfig),
    ("regime_switch_strategy", RegimeSwitchStrategy, RegimeSwitchConfig),
    ("regression_strategy", RegressionStrategy, RegressionConfig),
    ("relative_strength_strategy", RelativeStrengthStrategy, RelativeStrengthConfig),
    ("resistance_strategy", ResistanceStrategy, ResistanceConfig),
    ("rate_of_change", RocStrategy, RocConfig),
    ("rolling_cross", RollCrossStrategy, RollCrossConfig),
    ("rsi_strategy", RsiStrategy, RsiConfig),
    ("rsi_momentum_strategy", RsiMomentumStrategy, RsiMomentumConfig),
    ("spot_futures_arbitrage", SpotFuturesStrategy, SpotFuturesConfig),
    ("squeeze_strategy", SqueezeStrategy, SqueezeConfig),
    ("stablecoin_peg_strategy", StablecoinPegStrategy, StablecoinPegConfig),
    ("stochastic_strategy", StochasticStrategy, StochasticConfig),
    ("supertrend_strategy", SupertrendStrategy, SupertrendConfig),
    ("support_strategy", SupportStrategy, SupportConfig),
    ("tema_strategy", TemaStrategy, TemaConfig),
    ("time_series_strategy", TimeSeriesStrategy, TimeSeriesConfig),
    ("trend_momentum_strategy", TrendMomentumStrategy, TrendMomentumConfig),
    ("trend_mean_reversion", TrendMrStrategy, TrendMrConfig),
    ("trend_volume_strategy", TrendVolumeStrategy, TrendVolumeConfig),
    ("triangle_pattern", TriangleStrategy, TriangleConfig),
    ("triple_moving_average", TripleMaStrategy, TripleMaConfig),
    ("volatility_expansion", VolExpansionStrategy, VolExpansionConfig),
    ("volatility_scaling", VolScalingStrategy, VolScalingConfig),
    ("volatility_target", VolTargetStrategy, VolTargetConfig),
    ("volume_momentum_strategy", VolumeMomentumStrategy, VolumeMomentumConfig),
    ("volume_profile_strategy", VolumeProfileStrategy, VolumeProfileConfig),
    ("volume_spike_strategy", VolumeSpikeStrategy, VolumeSpikeConfig),
    ("vwap_strategy", VwapStrategy, VwapConfig),
    ("volume_weighted_momentum", VwMomentumStrategy, VwMomentumConfig),
    ("vwap_strategy", VwapStrategy, VwapConfig),
    ("williams_r_strategy", WilliamsRStrategy, WilliamsRConfig),
    ("zscore_strategy", ZscoreStrategy, ZscoreConfig),
]

_REGISTRY: dict[str, tuple[type, type]] = {n: (s, c) for n, s, c in _SPEC}

__all__ = ["_REGISTRY", "_SPEC"]
__all__.extend(["AbsoluteMomentumConfig", "AbsoluteMomentumStrategy"])
__all__.extend(["AdaptiveAllocationConfig", "AdaptiveAllocationStrategy"])
__all__.extend(["AdxTrendConfig", "AdxTrendStrategy"])
__all__.extend(["AnchoredVwapConfig", "AnchoredVwapStrategy"])
__all__.extend(["AtrBreakoutConfig", "AtrBreakoutStrategy"])
__all__.extend(["AtrTrailingConfig", "AtrTrailingStrategy"])
__all__.extend(["BasketConfig", "BasketStrategy"])
__all__.extend(["BbSqueeze2Config", "BbSqueeze2Strategy"])
__all__.extend(["BollingerBandsConfig", "BollingerBandsStrategy"])
__all__.extend(["BreakoutMomentumConfig", "BreakoutMomentumStrategy"])
__all__.extend(["BreakoutMomentumConfig", "BreakoutMomentumStrategy"])
__all__.extend(["CciConfig", "CciStrategy"])
__all__.extend(["CmfConfig", "CmfStrategy"])
__all__.extend(["CointegrationConfig", "CointegrationStrategy"])
__all__.extend(["CorrGateConfig", "CorrGateStrategy"])
__all__.extend(["CrossSectionalConfig", "CrossSectionalStrategy"])
__all__.extend(["CumulativeDeltaConfig", "CumulativeDeltaStrategy"])
__all__.extend(["DemaConfig", "DemaStrategy"])
__all__.extend(["DispersionConfig", "DispersionStrategy"])
__all__.extend(["DistanceMaConfig", "DistanceMaStrategy"])
__all__.extend(["DonchianConfig", "DonchianStrategy"])
__all__.extend(["DualMovingAverageConfig", "DualMovingAverageStrategy"])
__all__.extend(["DualMomentumConfig", "DualMomentumStrategy"])
__all__.extend(["EmaCrossConfig", "EmaCrossStrategy"])
__all__.extend(["EnsembleSignalsConfig", "EnsembleSignalsStrategy"])
__all__.extend(["FisherConfig", "FisherStrategy"])
__all__.extend(["FlagConfig", "FlagStrategy"])
__all__.extend(["FundingBasisConfig", "FundingBasisStrategy"])
__all__.extend(["FundingTrendConfig", "FundingTrendStrategy"])
__all__.extend(["GapConfig", "GapStrategy"])
__all__.extend(["GarchClassicConfig", "GarchClassicStrategy"])
__all__.extend(["GaussianConfig", "GaussianStrategy"])
__all__.extend(["HullConfig", "HullStrategy"])
__all__.extend(["ImplRealVolConfig", "ImplRealVolStrategy"])
__all__.extend(["InsideBarConfig", "InsideBarStrategy"])
__all__.extend(["KamaConfig", "KamaStrategy"])
__all__.extend(["KeltnerConfig", "KeltnerStrategy"])
__all__.extend(["KeltnerMomentumConfig", "KeltnerMomentumStrategy"])
__all__.extend(["LinearRegChannelConfig", "LinearRegChannelStrategy"])
__all__.extend(["LiquidationHuntConfig", "LiquidationHuntStrategy"])
__all__.extend(["MacdConfig", "MacdStrategy"])
__all__.extend(["MacdMomentumConfig", "MacdMomentumStrategy"])
__all__.extend(["MovingAverageCrossConfig", "MovingAverageCrossStrategy"])
__all__.extend(["MetaStrategyConfig", "MetaStrategy"])
__all__.extend(["MfiConfig", "MfiStrategy"])
__all__.extend(["MomentumFactorConfig", "MomentumFactorStrategy"])
__all__.extend(["MomentumVolConfig", "MomentumVolStrategy"])
__all__.extend(["MultiFactorConfig", "MultiFactorStrategy"])
__all__.extend(["Nr4Config", "Nr4Strategy"])
__all__.extend(["ObvConfig", "ObvStrategy"])
__all__.extend(["OpenRangeConfig", "OpenRangeStrategy"])
__all__.extend(["PriceChannelConfig", "PriceChannelStrategy"])
__all__.extend(["RectangleConfig", "RectangleStrategy"])
__all__.extend(["RegimeSwitchConfig", "RegimeSwitchStrategy"])
__all__.extend(["RegressionConfig", "RegressionStrategy"])
__all__.extend(["RelativeStrengthConfig", "RelativeStrengthStrategy"])
__all__.extend(["ResistanceConfig", "ResistanceStrategy"])
__all__.extend(["RocConfig", "RocStrategy"])
__all__.extend(["RollingCrossConfig", "RollCrossStrategy"])
__all__.extend(["RsiConfig", "RsiStrategy"])
__all__.extend(["RsiMomentumConfig", "RsiMomentumStrategy"])
__all__.extend(["SpotFuturesConfig", "SpotFuturesStrategy"])
__all__.extend(["SqueezeConfig", "SqueezeStrategy"])
__all__.extend(["StablecoinPegConfig", "StablecoinPegStrategy"])
__all__.extend(["StochasticConfig", "StochasticStrategy"])
__all__.extend(["SupertrendConfig", "SupertrendStrategy"])
__all__.extend(["SupportConfig", "SupportStrategy"])
__all__.extend(["TemaConfig", "TemaStrategy"])
__all__.extend(["TimeSeriesConfig", "TimeSeriesStrategy"])
__all__.extend(["TrendMomentumConfig", "TrendMomentumStrategy"])
__all__.extend(["TrendMrConfig", "TrendMrStrategy"])
__all__.extend(["TrendVolumeConfig", "TrendVolumeStrategy"])
__all__.extend(["TriangleConfig", "TriangleStrategy"])
__all__.extend(["TripleMaConfig", "TripleMaStrategy"])
__all__.extend(["VolExpansionConfig", "VolExpansionStrategy"])
__all__.extend(["VolScalingConfig", "VolScalingStrategy"])
__all__.extend(["VolTargetConfig", "VolTargetStrategy"])
__all__.extend(["VolumeMomentumConfig", "VolumeMomentumStrategy"])
__all__.extend(["VolumeProfileConfig", "VolumeProfileStrategy"])
__all__.extend(["VolumeSpikeConfig", "VolumeSpikeStrategy"])
__all__.extend(["VwMomentumConfig", "VwMomentumStrategy"])
__all__.extend(["VwapConfig", "VwapStrategy"])
__all__.extend(["WilliamsRConfig", "WilliamsRStrategy"])
__all__.extend(["ZscoreConfig", "ZscoreStrategy"])
