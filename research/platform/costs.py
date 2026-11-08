"""Market-specific fill fee calculators for the research portfolio simulator."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from .domain import Market
from .market import Side


D = Decimal


class FeeCalculator(Protocol):
    """Runtime fee calculator contract; returns a non-negative INR charge."""

    market: Market
    model_id: str

    def fee(self, side: Side, quantity: Decimal, price: Decimal) -> Decimal:
        """Return the fee for one simulated fill."""


@dataclass(frozen=True, slots=True)
class NSEDeliveryFeeCalculator:
    """Delegate statutory delivery fees to the repository's established CostModel."""

    model_id: str = "nse-delivery-cost-model"
    model: object | None = None

    @property
    def market(self) -> Market:
        # NSE delivery assumptions must never be attached to crypto fills.
        return Market.NSE

    def _get_model(self):
        # Import lazily to keep the generic platform independent from NSE package setup.
        if self.model is not None:
            return self.model
        from nsealgo.costs import CostModel

        return CostModel(segment="delivery", slippage_bps=D("0"))

    def fee(self, side: Side, quantity: Decimal, price: Decimal) -> Decimal:
        # Reuse itemised brokerage/STT/exchange/SEBI/stamp/DP/GST calculations.
        result = self._get_model().cost(side.value.upper(), quantity, price)
        amount = result.total
        if amount < D("0"):
            raise ValueError("NSE fee calculator returned a negative charge")
        return amount


@dataclass(frozen=True, slots=True)
class CryptoVenueFeeCalculator:
    """Exchange-specific maker/taker fee schedule for spot or derivatives adapters."""

    exchange: str
    maker_fee_bps: Decimal
    taker_fee_bps: Decimal
    liquidity_role: str = "taker"

    def __post_init__(self) -> None:
        # Require venue-specific values and a known order-liquidity classification.
        if not self.exchange.strip():
            raise ValueError("exchange identifier is required")
        if self.maker_fee_bps < 0 or self.taker_fee_bps < 0:
            raise ValueError("maker and taker fees cannot be negative")
        if self.liquidity_role not in {"maker", "taker"}:
            raise ValueError("liquidity_role must be maker or taker")

    @property
    def market(self) -> Market:
        # Crypto venue fee schedules are isolated from NSE transaction charges.
        return Market.CRYPTO

    @property
    def model_id(self) -> str:
        # Encode assumptions so every experiment can reproduce the fee tier.
        return (
            f"crypto-{self.exchange}-{self.liquidity_role}-"
            f"maker{self.maker_fee_bps}-taker{self.taker_fee_bps}"
        )

    def fee(self, side: Side, quantity: Decimal, price: Decimal) -> Decimal:
        # The current market-order simulator defaults to taker; maker mode is explicit.
        rate = self.maker_fee_bps if self.liquidity_role == "maker" else self.taker_fee_bps
        return (quantity * price * rate / D("10000")).quantize(D("0.01"))


@dataclass(frozen=True, slots=True)
class ProportionalFeeCalculator:
    """Generic declared fee schedule for controlled sensitivity experiments."""

    market: Market
    model_id: str
    fee_bps: Decimal

    def __post_init__(self) -> None:
        # Generic fee assumptions must be named and non-negative.
        if not self.model_id.strip() or self.fee_bps < 0:
            raise ValueError("fee model identifier and non-negative bps are required")

    def fee(self, side: Side, quantity: Decimal, price: Decimal) -> Decimal:
        # Quantise to paise to preserve rupee accounting semantics.
        return (quantity * price * self.fee_bps / D("10000")).quantize(D("0.01"))
