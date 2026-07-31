from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.core.events import OrderEvent, OrderSide
from cryptobot.execution.engine import ExecutionEngine


@dataclass
class FundingArbConfig:
    symbol: str = "BTCUSDT"
    perp_symbol: str = "BTCUSDTPERP"
    min_funding_rate: float = 0.0001
    max_funding_rate: float = 0.005
    basis_entry_bps: float = 5.0
    basis_exit_bps: float = 1.5
    hedge_leverage: Decimal = Decimal("1")
    quantity: Decimal = Decimal("1")
    fee_bps: float = 5.0


@dataclass
class FundingArbState:
    spot_price: Decimal = Decimal("0")
    perp_price: Decimal = Decimal("0")
    funding_rate: float = 0.0
    next_funding_seconds: float = 0.0


class FundingArbStrategy:
    name = "funding_arb"

    def __init__(self, config: FundingArbConfig | None = None):
        self.config = config or FundingArbConfig()
        self._exec: ExecutionEngine | None = None
        self.fills: list[OrderEvent] = []
        self.last_action: str | None = None

    def attach_execution(self, engine: ExecutionEngine) -> None:
        self._exec = engine

    def feed(self, state: FundingArbState) -> tuple[OrderSide, OrderSide] | None:
        cfg = self.config
        if state.spot_price <= 0 or state.perp_price <= 0:
            return None
        if state.funding_rate < cfg.min_funding_rate:
            self.last_action = "no_funding"
            return None
        if state.funding_rate > cfg.max_funding_rate:
            self.last_action = "funding_cap"
            return None
        basis_bps = float((state.perp_price - state.spot_price) / state.spot_price) * 10_000.0
        if basis_bps >= cfg.basis_entry_bps:
            self.last_action = "enter_short_perp_long_spot"
            return (OrderSide.SELL, OrderSide.BUY)
        if basis_bps <= cfg.basis_exit_bps:
            self.last_action = "exit"
            return (OrderSide.BUY, OrderSide.SELL)
        self.last_action = "hold"
        return None

    def feed_and_signal(self, state: FundingArbState) -> tuple[OrderSide, OrderSide] | None:
        return self.feed(state)


__all__ = ["FundingArbConfig", "FundingArbState", "FundingArbStrategy"]
