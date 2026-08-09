from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.core.events import OrderSide


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
    """Funding-carry: enter short-perp/long-spot when funding is attractively
    positive or the perp trades at a premium; exit when the premium
    collapses. Both legs are emitted per decision and the pair is closed
    together from the exit signal.
    """

    name = "funding_arb"

    def __init__(self, config: FundingArbConfig | None = None):
        self.config = config or FundingArbConfig()
        self._exec = None
        self.fills: list = []
        self.last_action: str | None = None
        self._in_position = False
        self.reduce_only = False
        self.qty = self.config.quantity

    @property
    def in_position(self) -> bool:
        return self._in_position

    def attach_execution(self, engine) -> None:
        self._exec = engine

    def feed(self, *args) -> tuple[OrderSide, OrderSide] | None:
        """Back-compat: accept FundingArbState or (ts, spot, perp, rate)."""
        if len(args) == 1 and isinstance(args[0], FundingArbState):
            st = args[0]
            return self.decide(st.spot_price, st.perp_price, Decimal(str(st.funding_rate)))
        ts, s, p, rate = args
        return self.decide(s, p, Decimal(str(rate)))

    def decide(
        self, spot: Decimal, perp: Decimal, rate: Decimal
    ) -> tuple[OrderSide, OrderSide] | None:
        cfg = self.config
        if spot <= 0 or perp <= 0:
            return None
        rate_f = float(rate)
        if cfg.max_funding_rate > 0 and rate_f > cfg.max_funding_rate:
            self.last_action = "funding_cap"
            return None
        basis_bps = float((perp - spot) / spot) * 10_000.0
        if not self._in_position:
            # Enter when either funding pays us to be short the perp, or the
            # basis premium is wide enough to bank on reversion.
            enter = rate_f >= cfg.min_funding_rate and basis_bps >= cfg.basis_entry_bps
            if enter:
                self._in_position = True
                self.last_action = "enter_short_perp_long_spot"
                return (OrderSide.SELL, OrderSide.BUY)
            self.last_action = "no_funding"
            return None
        # In position: exit when the premium compress (basis reverted) or the
        # funding turned against keeping the hedge on.
        exit_now = basis_bps <= cfg.basis_exit_bps or rate_f <= 0
        if exit_now:
            self._in_position = False
            self.last_action = "exit"
            return (OrderSide.BUY, OrderSide.SELL)
        self.last_action = "hold"
        return None

    def feed_and_signal(self, state: FundingArbState) -> tuple[OrderSide, OrderSide] | None:
        return self.decide(state.spot_price, state.perp_price, Decimal(str(state.funding_rate)))


__all___ = ["FundingArbConfig", "FundingArbState", "FundingArbStrategy"]
