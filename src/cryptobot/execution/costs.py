"""
Transaction Cost Model

Comprehensive transaction cost modeling including:
- Spread costs (crossing the spread)
- Maker/Taker fee structures
- Slippage models (fixed, volatility-based, volume-based)
- Funding rate costs for perpetual futures
- Maker rebates / taker fees
- Market impact models (linear, square-root, Almgren-Chriss)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class FeeType(StrEnum):
    """Fee structure type."""
    FLAT = "flat"
    TIERED = "tiered"
    VOLUME_DISCOUNT = "volume_discount"


class SlippageModel(StrEnum):
    """Slippage model type."""
    FIXED_BPS = "fixed_bps"
    VOLATILITY_ADJUSTED = "volatility_adjusted"
    VOLUME_WEIGHTED = "volume_weighted"
    SQUARE_ROOT = "square_root"
    ALMGREN_CHRISS = "almgren_chriss"


class FundingModel(StrEnum):
    """Funding rate model."""
    FIXED = "fixed"
    MARKET_BASED = "market_based"
    PREDICTED = "predicted"


@dataclass
class FeeSchedule:
    """Fee schedule for a venue/symbol."""
    maker_fee_bps: Decimal = Decimal("1")   # Maker rebate (negative) or fee (positive)
    taker_fee_bps: Decimal = Decimal("5")   # Taker fee
    fee_type: FeeType = FeeType.FLAT

    # Tiered fee structure
    tiers: list[dict[str, Any]] = field(default_factory=list)  # [{"volume_30d": Decimal, "maker_bps": Decimal, "taker_bps": Decimal}, ...]

    # Volume discount
    volume_30d: Decimal = Decimal("0")

    def get_fees(self, is_maker: bool, volume_30d: Decimal | None = None) -> Decimal:
        """Get fee in basis points for a given order type and volume."""
        vol = volume_30d or self.volume_30d

        if self.fee_type == FeeType.TIERED and self.tiers:
            for tier in reversed(self.tiers):  # Check highest tier first
                if vol >= tier["volume_30d"]:
                    return tier["maker_bps"] if is_maker else tier["taker_bps"]

        return self.maker_fee_bps if is_maker else self.taker_fee_bps

    def calculate_fee(self, notional: Decimal, is_maker: bool, volume_30d: Decimal | None = None) -> Decimal:
        """Calculate fee in quote currency."""
        fee_bps = self.get_fees(is_maker, volume_30d)
        return (notional * fee_bps / Decimal("10000")).quantize(Decimal("0.0001"))


@dataclass
class SlippageConfig:
    """Slippage model configuration."""
    model: SlippageModel = SlippageModel.VOLATILITY_ADJUSTED
    base_slippage_bps: Decimal = Decimal("2")
    max_slippage_bps: Decimal = Decimal("50")

    # Volatility-adjusted
    vol_window: int = 20
    vol_multiplier: Decimal = Decimal("1.5")

    # Volume-weighted
    avg_daily_volume: Decimal = Decimal("1000000")
    participation_cap: Decimal = Decimal("0.1")

    # Square-root model
    sqrt_coefficient: Decimal = Decimal("0.1")

    # Almgren-Chriss
    ac_risk_aversion: Decimal = Decimal("1e-6")
    ac_volatility: Decimal = Decimal("0.02")
    ac_time_horizon: int = 1  # hours


@dataclass
class SpreadCostConfig:
    """Spread cost configuration."""
    # Cross-spread cost: pay half-spread when crossing
    cross_spread_pct: Decimal = Decimal("0.5")

    # Use real-time spread vs. fixed
    use_realtime_spread: bool = True
    fixed_spread_bps: Decimal = Decimal("2")


@dataclass
class FundingConfig:
    """Funding rate cost configuration."""
    model: FundingModel = FundingModel.MARKET_BASED
    fixed_rate: Decimal = Decimal("0.0001")  # 0.01% per 8h
    funding_interval_hours: int = 8

    # For market-based
    max_funding_rate: Decimal = Decimal("0.001")  # 0.1% cap
    min_funding_rate: Decimal = Decimal("-0.001")


@dataclass
class RebateConfig:
    """Maker rebate configuration."""
    enabled: bool = True
    rebate_bps: Decimal = Decimal("1")  # Negative = rebate to maker
    min_volume_bps: Decimal = Decimal("10000")  # Min volume for rebate


@dataclass
class TransactionCostConfig:
    """Complete transaction cost configuration."""
    fees: FeeSchedule = field(default_factory=FeeSchedule)
    slippage: SlippageConfig = field(default_factory=SlippageConfig)
    spread: SpreadCostConfig = field(default_factory=SpreadCostConfig)
    funding: FundingConfig = field(default_factory=FundingConfig)
    rebate: RebateConfig = field(default_factory=RebateConfig)

    # Global settings
    min_cost_bps: Decimal = Decimal("0.5")  # Minimum total cost
    max_cost_bps: Decimal = Decimal("200")   # Maximum total cost (sanity check)


class TransactionCostModel:
    """
    Comprehensive transaction cost calculator.

    Calculates total execution cost including:
    - Explicit costs: fees, spread, slippage
    - Implicit costs: market impact, adverse selection
    - Carry costs: funding rates for perpetual positions
    - Rebates: maker rebates
    """

    def __init__(self, config: TransactionCostConfig | None = None):
        self.config = config or TransactionCostConfig()
        self._historical_volatility: dict[str, Decimal] = {}
        self._daily_volumes: dict[str, Decimal] = {}

    def calculate_total_cost(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: Decimal,
        price: Decimal,
        mark_price: Decimal,
        volatility: Decimal | None = None,
        daily_volume: Decimal | None = None,
        spread: Decimal | None = None,
        is_maker: bool | None = None,
        volume_30d: Decimal | None = None,
        position_side: str = "FLAT",  # FLAT, LONG, SHORT
        holding_hours: int = 0,
    ) -> dict[str, Decimal]:
        """
        Calculate total transaction cost for an order.

        Returns dict with cost breakdown in quote currency (USDT).
        """
        # Determine if maker/taker
        if is_maker is None:
            is_maker = order_type in ("LIMIT", "LIMIT_MAKER")

        notional = quantity * price
        costs = {}

        # 1. Fee cost
        fee_bps = self.config.fees.get_fees(is_maker, volume_30d)
        fee_cost = self.config.fees.calculate_fee(notional, is_maker)
        costs["fee"] = fee_cost
        costs["fee_bps"] = fee_bps

        # 2. Spread cost (crossing the spread)
        spread_cost = self._calculate_spread_cost(
            notional, price, mark_price, spread, is_maker, side
        )
        costs["spread"] = spread_cost
        costs["spread_bps"] = (spread_cost / notional * Decimal("10000")) if notional > 0 else Decimal("0")

        # 3. Slippage (returned in quote currency, not a fraction — issue #26)
        slippage_cost, slippage_bps = self._calculate_slippage(
            notional, price, volatility, daily_volume, side, order_type
        )
        costs["slippage"] = slippage_cost
        costs["slippage_bps"] = slippage_bps

        # 4. Market impact
        impact_cost, impact_bps = self._calculate_market_impact(
            notional, daily_volume, volatility, side
        )
        costs["market_impact"] = impact_cost
        costs["market_impact_bps"] = impact_bps

        # 5. Funding cost (for perpetual positions)
        funding_cost = Decimal("0")
        if holding_hours > 0:
            funding_cost = self._calculate_funding_cost(
                notional, side, position_side, holding_hours
            )
        costs["funding"] = funding_cost

        # 6. Maker rebate (if applicable)
        rebate = Decimal("0")
        if is_maker and self.config.rebate.enabled:
            rebate = self._calculate_rebate(notional)
        costs["rebate"] = rebate  # Negative = rebate received

        # Total cost in quote currency. Only *_cost components are summed — the
        # raw bps scalars used to pollute this sum and corrupt everything (#26).
        currency_keys = ("fee", "spread", "slippage", "market_impact", "funding", "rebate")
        total = sum((costs[k] for k in currency_keys), Decimal("0"))
        costs["total"] = total
        costs["total_bps"] = (total / notional * Decimal("10000")) if notional > 0 else Decimal("0")

        # Sanity checks (scale bps + their currency counterparts consistently)
        costs = self._apply_bounds(costs, notional)

        return costs

    def _calculate_spread_cost(
        self,
        notional: Decimal,
        price: Decimal,
        mark_price: Decimal,
        spread: Decimal | None,
        is_maker: bool,
        side: str,
    ) -> Decimal:
        """Calculate spread crossing cost."""
        if not is_maker:
            # Taker crosses the spread
            if self.config.spread.use_realtime_spread and spread is not None:
                spread_cost = notional * (spread / Decimal("2") / mark_price) * self.config.spread.cross_spread_pct
            else:
                spread_bps = self.config.spread.fixed_spread_bps / Decimal("10000")
                spread_cost = notional * spread_bps * self.config.spread.cross_spread_pct
            return spread_cost.quantize(Decimal("0.0001"))
        return Decimal("0")  # Makers don't cross spread

    def _calculate_slippage(
        self,
        notional: Decimal,
        price: Decimal,
        volatility: Decimal | None,
        daily_volume: Decimal | None,
        side: str,
        order_type: str,
    ) -> tuple[Decimal, Decimal]:
        """Calculate slippage cost based on configured model."""
        cfg = self.config.slippage

        if cfg.model == SlippageModel.FIXED_BPS:
            slippage_bps = cfg.base_slippage_bps

        elif cfg.model == SlippageModel.VOLATILITY_ADJUSTED:
            vol = volatility or Decimal("0.02")
            slippage_bps = cfg.base_slippage_bps + (vol * cfg.vol_multiplier * Decimal("10000"))
            slippage_bps = min(slippage_bps, cfg.max_slippage_bps)

        elif cfg.model == SlippageModel.VOLUME_WEIGHTED:
            if daily_volume and daily_volume > 0:
                participation = Decimal("1")  # Would need order quantity context
                # Simplified: higher volume = lower slippage
                vol_ratio = min(Decimal("1"), participation / cfg.participation_cap)
                slippage_bps = cfg.base_slippage_bps * (Decimal("1") + vol_ratio)
            else:
                slippage_bps = cfg.base_slippage_bps

        elif cfg.model == SlippageModel.SQUARE_ROOT:
            # Square-root model: slippage ~ sqrt(participation)
            # Using a default participation rate
            participation = Decimal("0.01")
            slippage_bps = cfg.sqrt_coefficient * (Decimal("10000") * (participation ** Decimal("0.5")))
            slippage_bps = min(slippage_bps, cfg.max_slippage_bps)

        elif cfg.model == SlippageModel.ALMGREN_CHRISS:
            # Almgren-Chriss model: impact = permanent + temporary
            # Simplified implementation
            participation = Decimal("0.01")
            permanent = cfg.ac_risk_aversion * cfg.ac_volatility * Decimal("10000")
            temporary = cfg.ac_volatility * (Decimal("10000") * (participation ** Decimal("0.5")))
            slippage_bps = permanent + temporary
            slippage_bps = min(slippage_bps, cfg.max_slippage_bps)

        else:
            slippage_bps = cfg.base_slippage_bps

        slippage_bps = min(slippage_bps, cfg.max_slippage_bps)
        # Convert bps to quote-currency cost so it sums with fee/spread/impact.
        return (notional * slippage_bps / Decimal("10000")).quantize(Decimal("0.0001")), slippage_bps

    def _calculate_market_impact(
        self,
        notional: Decimal,
        daily_volume: Decimal | None,
        volatility: Decimal | None,
        side: str,
    ) -> tuple[Decimal, Decimal]:
        """Calculate market impact cost using square-root model."""
        if not daily_volume or daily_volume <= 0:
            return Decimal("0"), Decimal("0")

        participation = notional / daily_volume
        participation = min(participation, Decimal("0.2"))  # Cap at 20%

        # Square-root impact model
        vol = volatility or Decimal("0.02")
        impact_bps = Decimal("10") * (participation ** Decimal("0.5")) * (Decimal("1") + vol * Decimal("10"))

        # Cap at reasonable level
        impact_bps = min(impact_bps, Decimal("100"))

        impact_cost = notional * (impact_bps / Decimal("10000"))
        return impact_cost.quantize(Decimal("0.0001")), impact_bps

    def _calculate_funding_cost(
        self,
        notional: Decimal,
        side: str,
        position_side: str,
        holding_hours: int,
    ) -> Decimal:
        """Calculate funding cost for holding a position."""
        cfg = self.config.funding

        if cfg.model == FundingModel.FIXED:
            rate_per_interval = cfg.fixed_rate
        elif cfg.model == FundingModel.MARKET_BASED:
            # Would fetch from market data - using fixed as fallback
            rate_per_interval = cfg.fixed_rate
        else:
            rate_per_interval = cfg.fixed_rate

        rate_per_interval = max(cfg.min_funding_rate, min(cfg.max_funding_rate, rate_per_interval))

        intervals = holding_hours / cfg.funding_interval_hours

        # Long positions pay funding, shorts receive (or vice versa depending on rate sign)
        if position_side == "LONG":
            funding_cost = notional * rate_per_interval * Decimal(str(intervals))
        elif position_side == "SHORT":
            funding_cost = -notional * rate_per_interval * Decimal(str(intervals))
        else:
            # Determine from side
            if side == "BUY":
                funding_cost = notional * rate_per_interval * Decimal(str(intervals))
            else:
                funding_cost = -notional * rate_per_interval * Decimal(str(intervals))

        return funding_cost.quantize(Decimal("0.0001"))

    def _calculate_rebate(self, notional: Decimal) -> Decimal:
        """Calculate maker rebate (negative = money received)."""
        if not self.config.rebate.enabled:
            return Decimal("0")

        rebate_bps = self.config.rebate.rebate_bps
        rebate = (notional * rebate_bps / Decimal("10000")).quantize(Decimal("0.0001"))
        return -rebate  # Negative = money received

    def _apply_bounds(self, costs: dict[str, Decimal], notional: Decimal) -> dict[str, Decimal]:
        """Apply sanity bounds to the total (scales currency + bps consistently)."""
        total_bps = costs.get("total_bps", Decimal("0"))
        currency_keys = ("fee", "spread", "slippage", "market_impact", "funding", "rebate")

        if 0 < total_bps < self.config.min_cost_bps:
            scale = self.config.min_cost_bps / total_bps
            for k in list(costs):
                if k == "total" or k in currency_keys:
                    costs[k] = costs[k] * scale
                elif k.endswith("_bps"):
                    costs[k] = costs[k] * scale

        if total_bps > self.config.max_cost_bps:
            scale = self.config.max_cost_bps / total_bps
            for k in list(costs):
                if k == "total" or k in currency_keys:
                    costs[k] = costs[k] * scale
                elif k.endswith("_bps"):
                    costs[k] = costs[k] * scale

        return costs


# Convenience functions
def estimate_total_cost_bps(
    symbol: str,
    side: str,
    order_type: str,
    quantity: Decimal,
    price: Decimal,
    mark_price: Decimal,
    config: TransactionCostConfig | None = None,
) -> Decimal:
    """Quick estimate of total cost in basis points."""
    model = TransactionCostModel(config)
    costs = model.calculate_total_cost(
        symbol=symbol,
        side=side,
        order_type=order_type,
        quantity=quantity,
        price=price,
        mark_price=mark_price,
    )
    return costs.get("total_bps", Decimal("0"))


def create_cost_config_from_settings(settings: dict) -> TransactionCostConfig:
    """Create cost config from settings dict (e.g., from YAML)."""
    return TransactionCostConfig(
        fees=FeeSchedule(
            maker_fee_bps=Decimal(str(settings.get("maker_fee_bps", 1))),
            taker_fee_bps=Decimal(str(settings.get("taker_fee_bps", 5))),
        ),
        slippage=SlippageConfig(
            model=SlippageModel(settings.get("slippage_model", "volatility_adjusted")),
            base_slippage_bps=Decimal(str(settings.get("base_slippage_bps", 2))),
        ),
        spread=SpreadCostConfig(
            use_realtime_spread=settings.get("use_realtime_spread", "true").lower() == "true",
            fixed_spread_bps=Decimal(str(settings.get("fixed_spread_bps", 2))),
        ),
        funding=FundingConfig(
            model=FundingModel(settings.get("funding_model", "market_based")),
            fixed_rate=Decimal(str(settings.get("funding_rate", "0.0001"))),
        ),
        rebate=RebateConfig(
            enabled=settings.get("rebate_enabled", "true").lower() == "true",
            rebate_bps=Decimal(str(settings.get("rebate_bps", 1))),
        ),
    )


__all__ = [
    "FeeType",
    "SlippageModel",
    "FundingModel",
    "FeeSchedule",
    "SlippageConfig",
    "SpreadCostConfig",
    "FundingConfig",
    "RebateConfig",
    "TransactionCostConfig",
    "TransactionCostModel",
    "estimate_total_cost_bps",
    "create_cost_config_from_settings",
]
