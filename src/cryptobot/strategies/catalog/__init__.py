"""Catalog of signal strategies (one module per strategy)."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path
from typing import Any

_SPECS: list[tuple[str, type, type]] = []

from cryptobot.strategies.catalog.absolute_momentum import AbsoluteMomentumConfig as AbsoluteMomentumConfig, AbsoluteMomentumStrategy as AbsoluteMomentumStrategy
from cryptobot.strategies.catalog.adaptive_allocation import AdaptiveAllocationConfig as AdaptiveAllocationConfig, AdaptiveAllocationStrategy as AdaptiveAllocationStrategy
from cryptobot.strategies.catalog.adx_trend import AdxTrendConfig as AdxTrendConfig, AdxTrendStrategy as AdxTrendStrategy
from cryptobot.strategies.catalog.anchored_vwap import AnchoredVwapConfig as AnchoredVwapConfig, AnchoredVwapStrategy as AnchoredVwapStrategy
from cryptobot.strategies.catalog.atr_breakout import AtrBreakoutConfig as AtrBreakoutConfig, AtrBreakoutStrategy as AtrBreakoutStrategy
from cryptobot.strategies.catalog.atr_trailing import AtrTrailingConfig as AtrTrailingConfig, AtrTrailingStrategy as AtrTrailingStrategy
from cryptobot.strategies.catalog.basket import BasketConfig as BasketConfig, BasketStrategy as BasketStrategy
from cryptobot.strategies.catalog.bb_squeeze2 import BbSqueeze2Config as BbSqueeze2Config, BbSqueeze2Strategy as BbSqueeze2Strategy
from cryptobot.strategies.catalog.bollinger import BollingerConfig as BollingerConfig, BollingerStrategy as BollingerStrategy
from cryptobot.strategies.catalog.break_momentum import BreakMomentumConfig as BreakMomentumConfig, BreakMomentumStrategy as BreakMomentumStrategy
from cryptobot.strategies.catalog.breakout_momentum import BreakoutMomentumConfig as BreakoutMomentumConfig, BreakoutMomentumStrategy as BreakoutMomentumStrategy
from cryptobot.strategies.catalog.cci import CciConfig as CciConfig, CciStrategy as CciStrategy
from cryptobot.strategies.catalog.cmf import CmfConfig as CmfConfig, CmfStrategy as CmfStrategy
from cryptobot.strategies.catalog.cointegration import CointegrationConfig as CointegrationConfig, CointegrationStrategy as CointegrationStrategy
from cryptobot.strategies.catalog.corr_gate import CorrGateConfig as CorrGateConfig, CorrGateStrategy as CorrGateStrategy
from cryptobot.strategies.catalog.cross_sectional import CrossSectionalConfig as CrossSectionalConfig, CrossSectionalStrategy as CrossSectionalStrategy
from cryptobot.strategies.catalog.cumulative_delta import CumulativeDeltaConfig as CumulativeDeltaConfig, CumulativeDeltaStrategy as CumulativeDeltaStrategy
from cryptobot.strategies.catalog.dema import DemaConfig as DemaConfig, DemaStrategy as DemaStrategy
from cryptobot.strategies.catalog.dispersion import DispersionConfig as DispersionConfig, DispersionStrategy as DispersionStrategy
from cryptobot.strategies.catalog.distance_ma import DistanceMaConfig as DistanceMaConfig, DistanceMaStrategy as DistanceMaStrategy
from cryptobot.strategies.catalog.donchian import DonchianConfig as DonchianConfig, DonchianStrategy as DonchianStrategy
from cryptobot.strategies.catalog.dual_ma import DualMaConfig as DualMaConfig, DualMaStrategy as DualMaStrategy
from cryptobot.strategies.catalog.dual_momentum import DualMomentumConfig as DualMomentumConfig, DualMomentumStrategy as DualMomentumStrategy
from cryptobot.strategies.catalog.ema_cross import EmaCrossConfig as EmaCrossConfig, EmaCrossStrategy as EmaCrossStrategy
from cryptobot.strategies.catalog.ensemble_signals import EnsembleSignalsConfig as EnsembleSignalsConfig, EnsembleSignalsStrategy as EnsembleSignalsStrategy
from cryptobot.strategies.catalog.fisher import FisherConfig as FisherConfig, FisherStrategy as FisherStrategy
from cryptobot.strategies.catalog.flag import FlagConfig as FlagConfig, FlagStrategy as FlagStrategy
from cryptobot.strategies.catalog.funding_basis import FundingBasisConfig as FundingBasisConfig, FundingBasisStrategy as FundingBasisStrategy
from cryptobot.strategies.catalog.funding_trend import FundingTrendConfig as FundingTrendConfig, FundingTrendStrategy as FundingTrendStrategy
from cryptobot.strategies.catalog.gap import GapConfig as GapConfig, GapStrategy as GapStrategy
from cryptobot.strategies.catalog.garch_classic import GarchClassicConfig as GarchClassicConfig, GarchClassicStrategy as GarchClassicStrategy
from cryptobot.strategies.catalog.gaussian import GaussianConfig as GaussianConfig, GaussianStrategy as GaussianStrategy
from cryptobot.strategies.catalog.hull import HullConfig as HullConfig, HullStrategy as HullStrategy
from cryptobot.strategies.catalog.impl_real_vol import ImplRealVolConfig as ImplRealVolConfig, ImplRealVolStrategy as ImplRealVolStrategy
from cryptobot.strategies.catalog.inside_bar import InsideBarConfig as InsideBarConfig, InsideBarStrategy as InsideBarStrategy
from cryptobot.strategies.catalog.kama import KamaConfig as KamaConfig, KamaStrategy as KamaStrategy
from cryptobot.strategies.catalog.keltner import KeltnerConfig as KeltnerConfig, KeltnerStrategy as KeltnerStrategy
from cryptobot.strategies.catalog.keltner_momentum import KeltnerMomentumConfig as KeltnerMomentumConfig, KeltnerMomentumStrategy as KeltnerMomentumStrategy
from cryptobot.strategies.catalog.linear_reg_channel import LinearRegChannelConfig as LinearRegChannelConfig, LinearRegChannelStrategy as LinearRegChannelStrategy
from cryptobot.strategies.catalog.liquidation_hunt import LiquidationHuntConfig as LiquidationHuntConfig, LiquidationHuntStrategy as LiquidationHuntStrategy
from cryptobot.strategies.catalog.ma_cross import MaCrossConfig as MaCrossConfig, MaCrossStrategy as MaCrossStrategy
from cryptobot.strategies.catalog.macd import MacdConfig as MacdConfig, MacdStrategy as MacdStrategy
from cryptobot.strategies.catalog.macd_momentum import MacdMomentumConfig as MacdMomentumConfig, MacdMomentumStrategy as MacdMomentumStrategy
from cryptobot.strategies.catalog.meta import MetaStrategyConfig as MetaStrategyConfig, MetaStrategy as MetaStrategy
from cryptobot.strategies.catalog.mfi import MfiConfig as MfiConfig, MfiStrategy as MfiStrategy
from cryptobot.strategies.catalog.momentum_factor import MomentumFactorConfig as MomentumFactorConfig, MomentumFactorStrategy as MomentumFactorStrategy
from cryptobot.strategies.catalog.momentum_vol import MomentumVolConfig as MomentumVolConfig, MomentumVolStrategy as MomentumVolStrategy
from cryptobot.strategies.catalog.multi_factor import MultiFactorConfig as MultiFactorConfig, MultiFactorStrategy as MultiFactorStrategy
from cryptobot.strategies.catalog.nr4 import Nr4Config as Nr4Config, Nr4Strategy as Nr4Strategy
from cryptobot.strategies.catalog.obv import ObvConfig as ObvConfig, ObvStrategy as ObvStrategy
from cryptobot.strategies.catalog.open_range import OpenRangeConfig as OpenRangeConfig, OpenRangeStrategy as OpenRangeStrategy
from cryptobot.strategies.catalog.price_channel import PriceChannelConfig as PriceChannelConfig, PriceChannelStrategy as PriceChannelStrategy
from cryptobot.strategies.catalog.rectangle import RectangleConfig as RectangleConfig, RectangleStrategy as RectangleStrategy
from cryptobot.strategies.catalog.regime_switch import RegimeSwitchConfig as RegimeSwitchConfig, RegimeSwitchStrategy as RegimeSwitchStrategy
from cryptobot.strategies.catalog.regression import RegressionConfig as RegressionConfig, RegressionStrategy as RegressionStrategy
from cryptobot.strategies.catalog.relative_strength import RelativeStrengthConfig as RelativeStrengthConfig, RelativeStrengthStrategy as RelativeStrengthStrategy
from cryptobot.strategies.catalog.resistance import ResistanceConfig as ResistanceConfig, ResistanceStrategy as ResistanceStrategy
from cryptobot.strategies.catalog.roc import RocConfig as RocConfig, RocStrategy as RocStrategy
from cryptobot.strategies.catalog.roll_cross import RollCrossConfig as RollCrossConfig, RollCrossStrategy as RollCrossStrategy
from cryptobot.strategies.catalog.rsi import RsiConfig as RsiConfig, RsiStrategy as RsiStrategy
from cryptobot.strategies.catalog.rsi_momentum import RsiMomentumConfig as RsiMomentumConfig, RsiMomentumStrategy as RsiMomentumStrategy
from cryptobot.strategies.catalog.spot_futures import SpotFuturesConfig as SpotFuturesConfig, SpotFuturesStrategy as SpotFuturesStrategy
from cryptobot.strategies.catalog.squeeze import SqueezeConfig as SqueezeConfig, SqueezeStrategy as SqueezeStrategy
from cryptobot.strategies.catalog.stablecoin_peg import StablecoinPegConfig as StablecoinPegConfig, StablecoinPegStrategy as StablecoinPegStrategy
from cryptobot.strategies.catalog.stochastic import StochasticConfig as StochasticConfig, StochasticStrategy as StochasticStrategy
from cryptobot.strategies.catalog.supertrend import SupertrendConfig as SupertrendConfig, SupertrendStrategy as SupertrendStrategy
from cryptobot.strategies.catalog.support import SupportConfig as SupportConfig, SupportStrategy as SupportStrategy
from cryptobot.strategies.catalog.tema import TemaConfig as TemaConfig, TemaStrategy as TemaStrategy
from cryptobot.strategies.catalog.time_series import TimeSeriesConfig as TimeSeriesConfig, TimeSeriesStrategy as TimeSeriesStrategy
from cryptobot.strategies.catalog.trend_momentum import TrendMomentumConfig as TrendMomentumConfig, TrendMomentumStrategy as TrendMomentumStrategy
from cryptobot.strategies.catalog.trend_mr import TrendMrConfig as TrendMrConfig, TrendMrStrategy as TrendMrStrategy
from cryptobot.strategies.catalog.trend_volume import TrendVolumeConfig as TrendVolumeConfig, TrendVolumeStrategy as TrendVolumeStrategy
from cryptobot.strategies.catalog.triangle import TriangleConfig as TriangleConfig, TriangleStrategy as TriangleStrategy
from cryptobot.strategies.catalog.triple_ma import TripleMaConfig as TripleMaConfig, TripleMaStrategy as TripleMaStrategy
from cryptobot.strategies.catalog.vol_expansion import VolExpansionConfig as VolExpansionConfig, VolExpansionStrategy as VolExpansionStrategy
from cryptobot.strategies.catalog.vol_scaling import VolScalingConfig as VolScalingConfig, VolScalingStrategy as VolScalingStrategy
from cryptobot.strategies.catalog.vol_target import VolTargetConfig as VolTargetConfig, VolTargetStrategy as VolTargetStrategy
from cryptobot.strategies.catalog.volume_momentum import VolumeMomentumConfig as VolumeMomentumConfig, VolumeMomentumStrategy as VolumeMomentumStrategy
from cryptobot.strategies.catalog.volume_profile import VolumeProfileConfig as VolumeProfileConfig, VolumeProfileStrategy as VolumeProfileStrategy
from cryptobot.strategies.catalog.volume_spike import VolumeSpikeConfig as VolumeSpikeConfig, VolumeSpikeStrategy as VolumeSpikeStrategy
from cryptobot.strategies.catalog.vw_momentum import VwMomentumConfig as VwMomentumConfig, VwMomentumStrategy as VwMomentumStrategy
from cryptobot.strategies.catalog.vwap import VwapConfig as VwapConfig, VwapStrategy as VwapStrategy
from cryptobot.strategies.catalog.williams_r import WilliamsRConfig as WilliamsRConfig, WilliamsRStrategy as WilliamsRStrategy
from cryptobot.strategies.catalog.zscore import ZscoreConfig as ZscoreConfig, ZscoreStrategy as ZscoreStrategy

_SPECS = [
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

def _make_registry() -> dict[str, tuple]:
    return {name: (cls, cfg) for name, cls, cfg in _SPECS}

_REGISTRY = _make_registry()

__all__ = [
    "AbsoluteMomentumConfig",
    "AdaptiveAllocationConfig",
    "AdxTrendConfig",
    "AnchoredVwapConfig",
    "AtrBreakoutConfig",
    "AtrTrailingConfig",
    "BasketConfig",
    "BbSqueeze2Config",
    "BollingerConfig",
    "BreakMomentumConfig",
    "BreakoutMomentumConfig",
    "CciConfig",
    "CmfConfig",
    "CointegrationConfig",
    "CorrGateConfig",
    "CrossSectionalConfig",
    "CumulativeDeltaConfig",
    "DemaConfig",
    "DispersionConfig",
    "DistanceMaConfig",
    "DonchianConfig",
    "DualMaConfig",
    "DualMomentumConfig",
    "EmaCrossConfig",
    "EnsembleSignalsConfig",
    "FisherConfig",
    "FlagConfig",
    "FundingBasisConfig",
    "FundingTrendConfig",
    "GapConfig",
    "GarchClassicConfig",
    "GaussianConfig",
    "HullConfig",
    "ImplRealVolConfig",
    "InsideBarConfig",
    "KamaConfig",
    "KeltnerConfig",
    "KeltnerMomentumConfig",
    "LinearRegChannelConfig",
    "LiquidationHuntConfig",
    "MaCrossConfig",
    "MacdConfig",
    "MacdMomentumConfig",
    "MetaStrategyConfig",
    "MfiConfig",
    "MomentumFactorConfig",
    "MomentumVolConfig",
    "MultiFactorConfig",
    "Nr4Config",
    "ObvConfig",
    "OpenRangeConfig",
    "PriceChannelConfig",
    "RectangleConfig",
    "RegimeSwitchConfig",
    "RegressionConfig",
    "RelativeStrengthConfig",
    "ResistanceConfig",
    "RocConfig",
    "RollCrossConfig",
    "RsiConfig",
    "RsiMomentumConfig",
    "SpotFuturesConfig",
    "SqueezeConfig",
    "StablecoinPegConfig",
    "StochasticConfig",
    "SupertrendConfig",
    "SupportConfig",
    "TemaConfig",
    "TimeSeriesConfig",
    "TrendMomentumConfig",
    "TrendMrConfig",
    "TrendVolumeConfig",
    "TriangleConfig",
    "TripleMaConfig",
    "VolExpansionConfig",
    "VolScalingConfig",
    "VolTargetConfig",
    "VolumeMomentumConfig",
    "VolumeProfileConfig",
    "VolumeSpikeConfig",
    "VwMomentumConfig",
    "VwapConfig",
    "WilliamsRConfig",
    "ZscoreConfig",
    "AbsoluteMomentumStrategy",
    "AdaptiveAllocationStrategy",
    "AdxTrendStrategy",
    "AnchoredVwapStrategy",
    "AtrBreakoutStrategy",
    "AtrTrailingStrategy",
    "BasketStrategy",
    "BbSqueeze2Strategy",
    "BollingerStrategy",
    "BreakMomentumStrategy",
    "BreakoutMomentumStrategy",
    "CciStrategy",
    "CmfStrategy",
    "CointegrationStrategy",
    "CorrGateStrategy",
    "CrossSectionalStrategy",
    "CumulativeDeltaStrategy",
    "DemaStrategy",
    "DispersionStrategy",
    "DistanceMaStrategy",
    "DonchianStrategy",
    "DualMaStrategy",
    "DualMomentumStrategy",
    "EmaCrossStrategy",
    "EnsembleSignalsStrategy",
    "FisherStrategy",
    "FlagStrategy",
    "FundingBasisStrategy",
    "FundingTrendStrategy",
    "GapStrategy",
    "GarchClassicStrategy",
    "GaussianStrategy",
    "HullStrategy",
    "ImplRealVolStrategy",
    "InsideBarStrategy",
    "KamaStrategy",
    "KeltnerStrategy",
    "KeltnerMomentumStrategy",
    "LinearRegChannelStrategy",
    "LiquidationHuntStrategy",
    "MaCrossStrategy",
    "MacdStrategy",
    "MacdMomentumStrategy",
    "MetaStrategy",
    "MfiStrategy",
    "MomentumFactorStrategy",
    "MomentumVolStrategy",
    "MultiFactorStrategy",
    "Nr4Strategy",
    "ObvStrategy",
    "OpenRangeStrategy",
    "PriceChannelStrategy",
    "RectangleStrategy",
    "RegimeSwitchStrategy",
    "RegressionStrategy",
    "RelativeStrengthStrategy",
    "ResistanceStrategy",
    "RocStrategy",
    "RollCrossStrategy",
    "RsiStrategy",
    "RsiMomentumStrategy",
    "SpotFuturesStrategy",
    "SqueezeStrategy",
    "StablecoinPegStrategy",
    "StochasticStrategy",
    "SupertrendStrategy",
    "SupportStrategy",
    "TemaStrategy",
    "TimeSeriesStrategy",
    "TrendMomentumStrategy",
    "TrendMrStrategy",
    "TrendVolumeStrategy",
    "TriangleStrategy",
    "TripleMaStrategy",
    "VolExpansionStrategy",
    "VolScalingStrategy",
    "VolTargetStrategy",
    "VolumeMomentumStrategy",
    "VolumeProfileStrategy",
    "VolumeSpikeStrategy",
    "VwMomentumStrategy",
    "VwapStrategy",
    "WilliamsRStrategy",
    "ZscoreStrategy",
    "_REGISTRY",
    "_SPECS",
]
