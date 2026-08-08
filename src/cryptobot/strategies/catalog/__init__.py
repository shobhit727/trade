"""Catalog of signal strategies (one module per strategy)."""

from __future__ import annotations

from cryptobot.strategies.catalog.absolute_momentum import AbsoluteMomentumConfig, AbsoluteMomentumStrategy
from cryptobot.strategies.catalog.adaptive_allocation import (
    AdaptiveAllocationConfig,
    AdaptiveAllocationStrategy,
)
from cryptobot.strategies.catalog.adx_trend import AdxTrendConfig, AdxTrendStrategy
from cryptobot.strategies.catalog.anchored_vwap import AnchoredVwapConfig, AnchoredVwapStrategy
from cryptobot.strategies.catalog.atr_breakout import AtrBreakoutConfig, AtrBreakoutStrategy
from cryptobot.strategies.catalog.atr_trailing import AtrTrailingConfig, AtrTrailingStrategy
from cryptobot.strategies.catalog.basket import BasketConfig, BasketStrategy
from cryptobot.strategies.catalog.bb_squeeze2 import BbSqueeze2Config, BbSqueeze2Strategy
from cryptobot.strategies.catalog.bollinger import BollingerConfig, BollingerStrategy
from cryptobot.strategies.catalog.break_momentum import BreakMomentumConfig, BreakMomentumStrategy
from cryptobot.strategies.catalog.breakout_momentum import BreakoutMomentumConfig, BreakoutMomentumStrategy
from cryptobot.strategies.catalog.cci import CciConfig, CciStrategy
from cryptobot.strategies.catalog.cmf import CmfConfig, CmfStrategy
from cryptobot.strategies.catalog.cointegration import CointegrationConfig, CointegrationStrategy
from cryptobot.strategies.catalog.corr_gate import CorrGateConfig, CorrGateStrategy
from cryptobot.strategies.catalog.cross_sectional import CrossSectionalConfig, CrossSectionalStrategy
from cryptobot.strategies.catalog.cumulative_delta import CumulativeDeltaConfig, CumulativeDeltaStrategy
from cryptobot.strategies.catalog.dema import DemaConfig, DemaStrategy
from cryptobot.strategies.catalog.dispersion import DispersionConfig, DispersionStrategy
from cryptobot.strategies.catalog.distance_ma import DistanceMaConfig, DistanceMaStrategy
from cryptobot.strategies.catalog.donchian import DonchianConfig, DonchianStrategy
from cryptobot.strategies.catalog.dual_ma import DualMaConfig, DualMaStrategy
from cryptobot.strategies.catalog.dual_momentum import DualMomentumConfig, DualMomentumStrategy
from cryptobot.strategies.catalog.ema_cross import EmaCrossConfig, EmaCrossStrategy
from cryptobot.strategies.catalog.ensemble_signals import EnsembleSignalsConfig, EnsembleSignalsStrategy
from cryptobot.strategies.catalog.fisher import FisherConfig, FisherStrategy
from cryptobot.strategies.catalog.flag import FlagConfig, FlagStrategy
from cryptobot.strategies.catalog.funding_basis import FundingBasisConfig, FundingBasisStrategy
from cryptobot.strategies.catalog.funding_trend import FundingTrendConfig, FundingTrendStrategy
from cryptobot.strategies.catalog.gap import GapConfig, GapStrategy
from cryptobot.strategies.catalog.garch_classic import GarchClassicConfig, GarchClassicStrategy
from cryptobot.strategies.catalog.gaussian import GaussianConfig, GaussianStrategy
from cryptobot.strategies.catalog.hull import HullConfig, HullStrategy
from cryptobot.strategies.catalog.impl_real_vol import ImplRealVolConfig, ImplRealVolStrategy
from cryptobot.strategies.catalog.inside_bar import InsideBarConfig, InsideBarStrategy
from cryptobot.strategies.catalog.kama import KamaConfig, KamaStrategy
from cryptobot.strategies.catalog.keltner import KeltnerConfig, KeltnerStrategy
from cryptobot.strategies.catalog.keltner_momentum import KeltnerMomentumConfig, KeltnerMomentumStrategy
from cryptobot.strategies.catalog.linear_reg_channel import LinearRegChannelConfig, LinearRegChannelStrategy
from cryptobot.strategies.catalog.liquidation_hunt import LiquidationHuntConfig, LiquidationHuntStrategy
from cryptobot.strategies.catalog.ma_cross import MaCrossConfig, MaCrossStrategy
from cryptobot.strategies.catalog.macd import MacdConfig, MacdStrategy
from cryptobot.strategies.catalog.macd_momentum import MacdMomentumConfig, MacdMomentumStrategy
from cryptobot.strategies.catalog.meta import MetaStrategy, MetaStrategyConfig
from cryptobot.strategies.catalog.mfi import MfiConfig, MfiStrategy
from cryptobot.strategies.catalog.momentum_factor import MomentumFactorConfig, MomentumFactorStrategy
from cryptobot.strategies.catalog.momentum_vol import MomentumVolConfig, MomentumVolStrategy
from cryptobot.strategies.catalog.multi_factor import MultiFactorConfig, MultiFactorStrategy
from cryptobot.strategies.catalog.nr4 import Nr4Config, Nr4Strategy
from cryptobot.strategies.catalog.obv import ObvConfig, ObvStrategy
from cryptobot.strategies.catalog.open_range import OpenRangeConfig, OpenRangeStrategy
from cryptobot.strategies.catalog.price_channel import PriceChannelConfig, PriceChannelStrategy
from cryptobot.strategies.catalog.rectangle import RectangleConfig, RectangleStrategy
from cryptobot.strategies.catalog.regime_switch import RegimeSwitchConfig, RegimeSwitchStrategy
from cryptobot.strategies.catalog.regression import RegressionConfig, RegressionStrategy
from cryptobot.strategies.catalog.relative_strength import RelativeStrengthConfig, RelativeStrengthStrategy
from cryptobot.strategies.catalog.resistance import ResistanceConfig, ResistanceStrategy
from cryptobot.strategies.catalog.roc import RocConfig, RocStrategy
from cryptobot.strategies.catalog.roll_cross import RollCrossConfig, RollCrossStrategy
from cryptobot.strategies.catalog.rsi import RsiConfig, RsiStrategy
from cryptobot.strategies.catalog.rsi_momentum import RsiMomentumConfig, RsiMomentumStrategy
from cryptobot.strategies.catalog.spot_futures import SpotFuturesConfig, SpotFuturesStrategy
from cryptobot.strategies.catalog.squeeze import SqueezeConfig, SqueezeStrategy
from cryptobot.strategies.catalog.stablecoin_peg import StablecoinPegConfig, StablecoinPegStrategy
from cryptobot.strategies.catalog.stochastic import StochasticConfig, StochasticStrategy
from cryptobot.strategies.catalog.supertrend import SupertrendConfig, SupertrendStrategy
from cryptobot.strategies.catalog.support import SupportConfig, SupportStrategy
from cryptobot.strategies.catalog.tema import TemaConfig, TemaStrategy
from cryptobot.strategies.catalog.time_series import TimeSeriesConfig, TimeSeriesStrategy
from cryptobot.strategies.catalog.trend_momentum import TrendMomentumConfig, TrendMomentumStrategy
from cryptobot.strategies.catalog.trend_mr import TrendMrConfig, TrendMrStrategy
from cryptobot.strategies.catalog.trend_volume import TrendVolumeConfig, TrendVolumeStrategy
from cryptobot.strategies.catalog.triangle import TriangleConfig, TriangleStrategy
from cryptobot.strategies.catalog.triple_ma import TripleMaConfig, TripleMaStrategy
from cryptobot.strategies.catalog.vol_expansion import VolExpansionConfig, VolExpansionStrategy
from cryptobot.strategies.catalog.vol_scaling import VolScalingConfig, VolScalingStrategy
from cryptobot.strategies.catalog.vol_target import VolTargetConfig, VolTargetStrategy
from cryptobot.strategies.catalog.volume_momentum import VolumeMomentumConfig, VolumeMomentumStrategy
from cryptobot.strategies.catalog.volume_profile import VolumeProfileConfig, VolumeProfileStrategy
from cryptobot.strategies.catalog.volume_spike import VolumeSpikeConfig, VolumeSpikeStrategy
from cryptobot.strategies.catalog.vw_momentum import VwMomentumConfig, VwMomentumStrategy
from cryptobot.strategies.catalog.vwap import VwapConfig, VwapStrategy
from cryptobot.strategies.catalog.williams_r import WilliamsRConfig, WilliamsRStrategy
from cryptobot.strategies.catalog.zscore import ZscoreConfig, ZscoreStrategy

_SPECS: list[tuple[str, type, type]] = [
    ("absolute_momentum", AbsoluteMomentumStrategy, AbsoluteMomentumConfig),
    ("adaptive_allocation", AdaptiveAllocationStrategy, AdaptiveAllocationConfig),
    ("adx_trend", AdxTrendStrategy, AdxTrendConfig),
    ("anchored_vwap", AnchoredVwapStrategy, AnchoredVwapConfig),
    ("atr_breakout", AtrBreakoutStrategy, AtrBreakoutConfig),
    ("atr_trailing", AtrTrailingStrategy, AtrTrailingConfig),
    ("basket", BasketStrategy, BasketConfig),
    ("bb_squeeze2", BbSqueeze2Strategy, BbSqueeze2Config),
    ("bollinger", BollingerStrategy, BollingerConfig),
    ("break_momentum", BreakMomentumStrategy, BreakMomentumConfig),
    ("breakout_momentum", BreakoutMomentumStrategy, BreakoutMomentumConfig),
    ("cci", CciStrategy, CciConfig),
    ("cmf", CmfStrategy, CmfConfig),
    ("cointegration", CointegrationStrategy, CointegrationConfig),
    ("corr_gate", CorrGateStrategy, CorrGateConfig),
    ("cross_sectional", CrossSectionalStrategy, CrossSectionalConfig),
    ("cumulative_delta", CumulativeDeltaStrategy, CumulativeDeltaConfig),
    ("dema", DemaStrategy, DemaConfig),
    ("dispersion", DispersionStrategy, DispersionConfig),
    ("distance_ma", DistanceMaStrategy, DistanceMaConfig),
    ("donchian", DonchianStrategy, DonchianConfig),
    ("dual_ma", DualMaStrategy, DualMaConfig),
    ("dual_momentum", DualMomentumStrategy, DualMomentumConfig),
    ("ema_cross", EmaCrossStrategy, EmaCrossConfig),
    ("ensemble_signals", EnsembleSignalsStrategy, EnsembleSignalsConfig),
    ("fisher", FisherStrategy, FisherConfig),
    ("flag", FlagStrategy, FlagConfig),
    ("funding_basis", FundingBasisStrategy, FundingBasisConfig),
    ("funding_trend", FundingTrendStrategy, FundingTrendConfig),
    ("gap", GapStrategy, GapConfig),
    ("garch_classic", GarchClassicStrategy, GarchClassicConfig),
    ("gaussian", GaussianStrategy, GaussianConfig),
    ("hull", HullStrategy, HullConfig),
    ("impl_real_vol", ImplRealVolStrategy, ImplRealVolConfig),
    ("inside_bar", InsideBarStrategy, InsideBarConfig),
    ("kama", KamaStrategy, KamaConfig),
    ("keltner", KeltnerStrategy, KeltnerConfig),
    ("keltner_momentum", KeltnerMomentumStrategy, KeltnerMomentumConfig),
    ("linear_reg_channel", LinearRegChannelStrategy, LinearRegChannelConfig),
    ("liquidation_hunt", LiquidationHuntStrategy, LiquidationHuntConfig),
    ("ma_cross", MaCrossStrategy, MaCrossConfig),
    ("macd", MacdStrategy, MacdConfig),
    ("macd_momentum", MacdMomentumStrategy, MacdMomentumConfig),
    ("meta", MetaStrategy, MetaStrategyConfig),
    ("mfi", MfiStrategy, MfiConfig),
    ("momentum_factor", MomentumFactorStrategy, MomentumFactorConfig),
    ("momentum_vol", MomentumVolStrategy, MomentumVolConfig),
    ("multi_factor", MultiFactorStrategy, MultiFactorConfig),
    ("nr4", Nr4Strategy, Nr4Config),
    ("obv", ObvStrategy, ObvConfig),
    ("open_range", OpenRangeStrategy, OpenRangeConfig),
    ("price_channel", PriceChannelStrategy, PriceChannelConfig),
    ("rectangle", RectangleStrategy, RectangleConfig),
    ("regime_switch", RegimeSwitchStrategy, RegimeSwitchConfig),
    ("regression", RegressionStrategy, RegressionConfig),
    ("relative_strength", RelativeStrengthStrategy, RelativeStrengthConfig),
    ("resistance", ResistanceStrategy, ResistanceConfig),
    ("roc", RocStrategy, RocConfig),
    ("roll_cross", RollCrossStrategy, RollCrossConfig),
    ("rsi", RsiStrategy, RsiConfig),
    ("rsi_momentum", RsiMomentumStrategy, RsiMomentumConfig),
    ("spot_futures", SpotFuturesStrategy, SpotFuturesConfig),
    ("squeeze", SqueezeStrategy, SqueezeConfig),
    ("stablecoin_peg", StablecoinPegStrategy, StablecoinPegConfig),
    ("stochastic", StochasticStrategy, StochasticConfig),
    ("supertrend", SupertrendStrategy, SupertrendConfig),
    ("support", SupportStrategy, SupportConfig),
    ("tema", TemaStrategy, TemaConfig),
    ("time_series", TimeSeriesStrategy, TimeSeriesConfig),
    ("trend_momentum", TrendMomentumStrategy, TrendMomentumConfig),
    ("trend_mr", TrendMrStrategy, TrendMrConfig),
    ("trend_volume", TrendVolumeStrategy, TrendVolumeConfig),
    ("triangle", TriangleStrategy, TriangleConfig),
    ("triple_ma", TripleMaStrategy, TripleMaConfig),
    ("vol_expansion", VolExpansionStrategy, VolExpansionConfig),
    ("vol_scaling", VolScalingStrategy, VolScalingConfig),
    ("vol_target", VolTargetStrategy, VolTargetConfig),
    ("volume_momentum", VolumeMomentumStrategy, VolumeMomentumConfig),
    ("volume_profile", VolumeProfileStrategy, VolumeProfileConfig),
    ("volume_spike", VolumeSpikeStrategy, VolumeSpikeConfig),
    ("vw_momentum", VwMomentumStrategy, VwMomentumConfig),
    ("vwap", VwapStrategy, VwapConfig),
    ("williams_r", WilliamsRStrategy, WilliamsRConfig),
    ("zscore", ZscoreStrategy, ZscoreConfig),
]

_REGISTRY: dict[str, tuple[type, type]] = {n: (s, c) for n, s, c in _SPECS}

__all__ = ["_REGISTRY", "_SPECS"]
__all__.extend(["AbsoluteMomentumConfig", "AbsoluteMomentumStrategy"])
__all__.extend(["AdaptiveAllocationConfig", "AdaptiveAllocationStrategy"])
__all__.extend(["AdxTrendConfig", "AdxTrendStrategy"])
__all__.extend(["AnchoredVwapConfig", "AnchoredVwapStrategy"])
__all__.extend(["AtrBreakoutConfig", "AtrBreakoutStrategy"])
__all__.extend(["AtrTrailingConfig", "AtrTrailingStrategy"])
__all__.extend(["BasketConfig", "BasketStrategy"])
__all__.extend(["BbSqueeze2Config", "BbSqueeze2Strategy"])
__all__.extend(["BollingerConfig", "BollingerStrategy"])
__all__.extend(["BreakMomentumConfig", "BreakMomentumStrategy"])
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
__all__.extend(["DualMaConfig", "DualMaStrategy"])
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
__all__.extend(["MaCrossConfig", "MaCrossStrategy"])
__all__.extend(["MacdConfig", "MacdStrategy"])
__all__.extend(["MacdMomentumConfig", "MacdMomentumStrategy"])
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
__all__.extend(["RollCrossConfig", "RollCrossStrategy"])
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
