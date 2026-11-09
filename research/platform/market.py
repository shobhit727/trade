"""Market-scoped simulated ledgers with explicit cross-market isolation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Mapping

from .domain import MARKET_SPECS, Market


ZERO = Decimal("0")


class Side(StrEnum):
    """Supported cash-account fill sides."""

    BUY = "buy"
    SELL = "sell"


@dataclass(frozen=True, slots=True)
class Fill:
    """A simulated fill expressed in INR after any documented FX conversion."""

    fill_id: str
    market: Market
    instrument: str
    side: Side
    quantity: Decimal
    price_inr: Decimal
    fee_inr: Decimal
    timestamp: datetime
    cost_model_id: str
    fx_provenance: str = "INR-native"

    def __post_init__(self) -> None:
        # Keep fill inputs auditable and reject timestamps without an explicit timezone.
        if not self.fill_id.strip() or not self.instrument.strip():
            raise ValueError("fill_id and instrument must be non-empty")
        if self.side not in (Side.BUY, Side.SELL):
            raise ValueError("side must be BUY or SELL")
        if self.quantity <= ZERO or self.price_inr <= ZERO or self.fee_inr < ZERO:
            raise ValueError("quantity and price must be positive; fee cannot be negative")
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("fill timestamp must be timezone-aware")
        if not self.cost_model_id.strip():
            raise ValueError("cost_model_id must identify the applied cost assumptions")
        if not self.fx_provenance.strip():
            raise ValueError("fx_provenance must document INR conversion provenance")


@dataclass(slots=True)
class Position:
    """Long-only spot position with fee-inclusive average entry value."""

    quantity: Decimal = ZERO
    average_entry_inr: Decimal = ZERO


@dataclass(frozen=True, slots=True)
class LedgerSnapshot:
    """Point-in-time state of one market's simulated cash account."""

    market: Market
    initial_capital_inr: Decimal
    cash_inr: Decimal
    position_values_inr: Mapping[str, Decimal]
    equity_inr: Decimal
    realised_pnl_inr: Decimal
    fees_paid_inr: Decimal
    fill_count: int


@dataclass(slots=True)
class MarketLedger:
    """Single-market, long-only cash ledger; no cross-market transfer API exists."""

    market: Market
    initial_capital_inr: Decimal | None = None
    cash_inr: Decimal | None = None
    positions: dict[str, Position] = field(default_factory=dict)
    realised_pnl_inr: Decimal = ZERO
    fees_paid_inr: Decimal = ZERO
    _fill_ids: set[str] = field(default_factory=set, repr=False)

    def __post_init__(self) -> None:
        # Bind the ledger permanently to its own market budget and account namespace.
        spec = MARKET_SPECS[self.market]
        if self.initial_capital_inr is None:
            self.initial_capital_inr = spec.initial_simulated_capital
        if self.initial_capital_inr != spec.initial_simulated_capital:
            raise ValueError("initial capital must match the market's isolated budget")
        if self.cash_inr is None:
            self.cash_inr = self.initial_capital_inr
        if self.cash_inr != self.initial_capital_inr:
            raise ValueError("opening cash must equal the isolated market seed capital")

    def apply_fill(self, fill: Fill) -> None:
        """Apply a fill only when its market matches this ledger."""
        # Market equality is checked before any ledger mutation.
        if fill.market is not self.market:
            raise ValueError(
                f"cross-market fill rejected: {fill.market.value} fill on {self.market.value} ledger"
            )
        if fill.fill_id in self._fill_ids:
            raise ValueError(f"duplicate fill id: {fill.fill_id}")

        notional = fill.quantity * fill.price_inr
        position = self.positions.get(fill.instrument, Position())

        if fill.side is Side.BUY:
            debit = notional + fill.fee_inr
            if debit > self.cash_inr:
                raise ValueError("insufficient simulated cash for buy fill")
            new_quantity = position.quantity + fill.quantity
            total_entry = position.average_entry_inr * position.quantity + debit
            position.quantity = new_quantity
            position.average_entry_inr = total_entry / new_quantity
            self.cash_inr -= debit
            self.positions[fill.instrument] = position
        else:
            # Short selling and derivatives require a separate margin-aware ledger.
            if position.quantity == ZERO or fill.quantity > position.quantity:
                raise ValueError("cash ledger cannot sell more than the existing long position")
            # Flat per-scrip charges can exceed a very small fill's proceeds.
            # Pay the full fee from account cash, but never permit a negative cash balance.
            cash_after_fee = self.cash_inr + notional - fill.fee_inr
            if cash_after_fee < ZERO:
                raise ValueError("insufficient simulated cash to pay sell fees")
            gross_pnl = (fill.price_inr - position.average_entry_inr) * fill.quantity
            self.realised_pnl_inr += gross_pnl - fill.fee_inr
            self.cash_inr = cash_after_fee
            position.quantity -= fill.quantity
            if position.quantity == ZERO:
                position.average_entry_inr = ZERO
            self.positions[fill.instrument] = position

        # Book identifiers and costs only after all validations and accounting succeed.
        self.fees_paid_inr += fill.fee_inr
        self._fill_ids.add(fill.fill_id)

    def snapshot(self, marks_inr: Mapping[str, Decimal] | None = None) -> LedgerSnapshot:
        """Return a market-only valuation using caller-supplied INR marks."""
        marks = marks_inr or {}
        values: dict[str, Decimal] = {}
        for instrument, position in self.positions.items():
            if position.quantity == ZERO:
                continue
            if instrument not in marks or marks[instrument] <= ZERO:
                raise ValueError(f"positive INR mark required for {instrument}")
            values[instrument] = position.quantity * marks[instrument]
        equity = self.cash_inr + sum(values.values(), ZERO)
        return LedgerSnapshot(
            market=self.market,
            initial_capital_inr=self.initial_capital_inr,
            cash_inr=self.cash_inr,
            position_values_inr=values,
            equity_inr=equity,
            realised_pnl_inr=self.realised_pnl_inr,
            fees_paid_inr=self.fees_paid_inr,
            fill_count=len(self._fill_ids),
        )
