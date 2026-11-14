"""FIFO tax lots and explicit corporate-action accounting (audit F-013).

This module is the single owner of lot-level portfolio accounting for the
research platform:

- per-symbol FIFO lot queues (quantity, cost price, acquisition date);
- sells realised strictly FIFO into STCG/LTCG records: a holding period of
  more than 365 days is long-term, matching the repository's ground-truth
  engine ``src/cryptobot/core/tax_equity.py`` (dated holding-period rules are a
  documented extension candidate under audit section 7.11);
- corporate actions applied ONLY from an explicit event list — there is no
  auto-detection anywhere in this module (audit F-013 requirement).

Corporate-action ratio semantics (``CorporateAction.ratio``), stated to remove
the classic Indian-notation ambiguity:

- split 1:2 ("one existing share becomes two new shares") -> ``ratio=2``:
  every lot's quantity is multiplied by 2 and its cost price divided by 2;
  cash is unchanged. ``ratio < 1`` models a consolidation/reverse split.
- bonus 1:1 ("one bonus share for every one held") -> ``ratio=1``: every lot
  spawns an equal zero-cost lot dated at the ex-date; cash is unchanged.
  bonus 1:2 ("one bonus share for every two held") -> ``ratio=0.5``.

Lot cost basis is the trade price, deliberately excluding fill fees: FIFO
capital gains use trade prices exactly like the ground-truth tax engine, while
the cash ledger's fee-inclusive average entry remains the account-level view.
With zero-fee fills the two aggregates coincide (asserted by the invariant
loop in ``tests/unit/test_research_platform_dated_costs.py``).

All money is ``Decimal`` (repo rule). Basis conservation under non-terminating
ratios (for example a 1:3 split of an odd-paise price) holds to the default
Decimal context of 28 significant digits; tests assert exact equality for
terminating ratios and a 1e-9 rupee tolerance otherwise.

``apply_corporate_action`` keeps the cash ``MarketLedger`` ``Position``
(quantity and average entry) consistent with the lot queue after every event —
CR-013 invariant: cash and positions are correct after every event, and a
corporate action never touches cash.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Iterable

from .market import MarketLedger


D = Decimal

#: A holding period of more than 365 days is long-term (repo ground truth:
#: ``src/cryptobot/core/tax_equity.py``).
LONG_TERM_HOLDING_DAYS = 365

KIND_STCG = "STCG"
KIND_LTCG = "LTCG"


def _as_date(value: date | datetime) -> date:
    """Normalise a date-ish input to a plain calendar date."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raise TypeError(f"expected date or datetime, got {type(value).__name__}")


def _as_decimal(value: Decimal | int | str, name: str) -> Decimal:
    """Coerce exact numeric inputs; reject floats which cannot represent paise."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        raise TypeError(f"{name} must be Decimal, int or str, got bool")
    if isinstance(value, (int, str)):
        return D(value)
    raise TypeError(f"{name} must be Decimal, int or str, got {type(value).__name__}")


@dataclass(frozen=True, slots=True)
class TaxLot:
    """One open long lot: quantity, cost price and acquisition date."""

    quantity: Decimal
    price_inr: Decimal
    acquired_on: date

    def __post_init__(self) -> None:
        # Zero-price lots are exactly how bonus shares are represented.
        if self.quantity <= 0:
            raise ValueError("lot quantity must be positive")
        if self.price_inr < 0:
            raise ValueError("lot cost price cannot be negative (zero = bonus lot)")
        object.__setattr__(self, "acquired_on", _as_date(self.acquired_on))


@dataclass(frozen=True, slots=True)
class RealizedGain:
    """One FIFO-matched slice of a sell, classified by holding period."""

    symbol: str
    quantity: Decimal
    cost_price_inr: Decimal
    sell_price_inr: Decimal
    proceeds_inr: Decimal
    cost_basis_inr: Decimal
    gain_inr: Decimal
    acquired_on: date
    sold_on: date
    holding_days: int
    kind: str  # KIND_STCG | KIND_LTCG

    def to_dict(self) -> dict[str, object]:
        """Return the record with dates as ISO strings for experiment records."""
        return {
            "symbol": self.symbol,
            "quantity": str(self.quantity),
            "cost_price_inr": str(self.cost_price_inr),
            "sell_price_inr": str(self.sell_price_inr),
            "proceeds_inr": str(self.proceeds_inr),
            "cost_basis_inr": str(self.cost_basis_inr),
            "gain_inr": str(self.gain_inr),
            "acquired_on": self.acquired_on.isoformat(),
            "sold_on": self.sold_on.isoformat(),
            "holding_days": self.holding_days,
            "kind": self.kind,
        }


@dataclass(frozen=True, slots=True)
class CorporateAction:
    """One declared corporate action with its ex-date. No auto-detection exists.

    ``ratio`` counts new shares per existing share: for a split it is the total
    post-split shares per pre-split share (2 doubles the quantity); for a bonus
    it is the number of free shares per held share (1 doubles the quantity at
    zero cost). Splits with ``ratio < 1`` model consolidations.
    """

    action: str  # "split" | "bonus"
    symbol: str
    ex_date: date
    ratio: Decimal

    def __post_init__(self) -> None:
        if self.action not in ("split", "bonus"):
            raise ValueError(f"unknown corporate action: {self.action!r}")
        if not isinstance(self.symbol, str) or not self.symbol.strip():
            raise ValueError("corporate action symbol is required")
        object.__setattr__(self, "ex_date", _as_date(self.ex_date))
        ratio = _as_decimal(self.ratio, "ratio")
        if ratio <= 0:
            raise ValueError("corporate action ratio must be positive")
        object.__setattr__(self, "ratio", ratio)


class TaxLotLedger:
    """Per-symbol FIFO lot queue; long-only and Decimal-exact."""

    def __init__(self) -> None:
        self._lots: dict[str, list[TaxLot]] = {}

    def open_lot(
        self,
        symbol: str,
        quantity: Decimal,
        price_inr: Decimal,
        acquired_on: date | datetime,
    ) -> None:
        """Append one lot to the symbol's FIFO queue."""
        if not isinstance(symbol, str) or not symbol.strip():
            raise ValueError("symbol is required")
        qty = _as_decimal(quantity, "quantity")
        price = _as_decimal(price_inr, "price_inr")
        if qty <= 0:
            raise ValueError("lot quantity must be positive")
        if price < 0:
            raise ValueError("lot cost price cannot be negative")
        self._lots.setdefault(symbol, []).append(
            TaxLot(qty, price, _as_date(acquired_on))
        )

    def lots(self, symbol: str) -> tuple[TaxLot, ...]:
        """Return the open lots for one symbol, oldest first."""
        return tuple(self._lots.get(symbol, ()))

    def symbols(self) -> tuple[str, ...]:
        """Return every symbol with at least one open lot."""
        return tuple(sorted(self._lots))

    def total_quantity(self, symbol: str) -> Decimal:
        """Sum the open lot quantities for one symbol."""
        return sum((lot.quantity for lot in self._lots.get(symbol, ())), D("0"))

    def total_cost_basis_inr(self, symbol: str) -> Decimal:
        """Sum quantity x cost price over the symbol's open lots."""
        return sum(
            (lot.quantity * lot.price_inr for lot in self._lots.get(symbol, ())),
            D("0"),
        )

    def realize_fifo(
        self,
        symbol: str,
        quantity: Decimal,
        price_inr: Decimal,
        sold_on: date | datetime,
    ) -> tuple[RealizedGain, ...]:
        """Close lots strictly FIFO and return the STCG/LTCG records.

        Raises ``ValueError`` when the open lots cannot cover the quantity;
        a sell without lots is corrupt state, never an implicit short.
        """
        if not isinstance(symbol, str) or not symbol.strip():
            raise ValueError("symbol is required")
        qty = _as_decimal(quantity, "quantity")
        price = _as_decimal(price_inr, "price_inr")
        if qty <= 0:
            raise ValueError("realized quantity must be positive")
        if price <= 0:
            raise ValueError("sell price must be positive")
        sold = _as_date(sold_on)
        pool = self._lots.get(symbol)
        available = self.total_quantity(symbol)
        if not pool or available < qty:
            raise ValueError(
                f"cannot realize {qty} {symbol}: only {available} in open FIFO lots"
            )
        remaining = qty
        records: list[RealizedGain] = []
        while remaining > 0:
            lot = pool[0]
            take = lot.quantity if lot.quantity <= remaining else remaining
            holding_days = (sold - lot.acquired_on).days
            kind = KIND_LTCG if holding_days > LONG_TERM_HOLDING_DAYS else KIND_STCG
            proceeds = take * price
            basis = take * lot.price_inr
            records.append(
                RealizedGain(
                    symbol=symbol,
                    quantity=take,
                    cost_price_inr=lot.price_inr,
                    sell_price_inr=price,
                    proceeds_inr=proceeds,
                    cost_basis_inr=basis,
                    gain_inr=proceeds - basis,
                    acquired_on=lot.acquired_on,
                    sold_on=sold,
                    holding_days=holding_days,
                    kind=kind,
                )
            )
            remaining -= take
            if take == lot.quantity:
                pool.pop(0)
            else:
                pool[0] = TaxLot(lot.quantity - take, lot.price_inr, lot.acquired_on)
        if not pool:
            del self._lots[symbol]
        return tuple(records)

    def apply_corporate_action(self, event: CorporateAction) -> None:
        """Adjust the lot queue for one declared event; the lot queue must be open.

        Split: multiply every lot's quantity by ``ratio`` and divide its cost
        price by ``ratio`` (basis preserved to Decimal context precision).
        Bonus: append a zero-cost lot of ``quantity x ratio`` per existing lot,
        dated at the ex-date so FIFO holding periods start at the event.
        """
        pool = self._lots.get(event.symbol)
        if not pool:
            raise ValueError(
                f"corporate action {event.action} for {event.symbol} without open lots"
            )
        if event.action == "split":
            self._lots[event.symbol] = [
                TaxLot(
                    lot.quantity * event.ratio,
                    lot.price_inr / event.ratio,
                    lot.acquired_on,
                )
                for lot in pool
            ]
        else:
            pool.extend(
                TaxLot(lot.quantity * event.ratio, D("0"), event.ex_date)
                for lot in list(pool)
            )


def apply_corporate_action(
    ledger: MarketLedger, tax_lots: TaxLotLedger, event: CorporateAction
) -> None:
    """Apply one corporate action to the lot queue AND the cash ledger position.

    Cash is unchanged by construction: splits and bonus issues are non-cash.
    The helper raises before any mutation when the lot queue and the ledger
    position disagree, so inconsistent state can never absorb an event.
    Split adjusts the ledger quantity by ``ratio`` and divides the average
    entry by ``ratio``; bonus dilutes the average entry across the enlarged
    quantity at zero marginal cost.
    """
    position = ledger.positions.get(event.symbol)
    held = position.quantity if position is not None else D("0")
    lot_total = tax_lots.total_quantity(event.symbol)
    if held != lot_total:
        raise ValueError(
            f"{event.symbol}: lot queue ({lot_total}) and ledger position ({held}) "
            "disagree; refusing to apply the corporate action to inconsistent state"
        )
    if held == 0:
        raise ValueError(
            f"corporate action {event.action} for {event.symbol} without an open position"
        )
    tax_lots.apply_corporate_action(event)
    if event.action == "split":
        new_quantity = held * event.ratio
        new_average = position.average_entry_inr / event.ratio
    else:
        new_quantity = held + held * event.ratio
        new_average = (position.average_entry_inr * held) / new_quantity
    position.quantity = new_quantity
    position.average_entry_inr = new_average
