"""Isolated perpetual-futures ledger for the crypto research platform.

Audit F-014 requires derivatives accounting that never reuses the spot cash
ledger: "Each derivative contract has a separate tested ledger. Do not use the
spot cash ledger to represent derivatives."

Scope and conventions (all documented, all asserted at construction):

- One ``PerpetualLedger`` simulates exactly one instrument on one market. The
  ledger is bound to ``Market.CRYPTO`` at construction; an NSE-scoped ledger
  is a construction-time error, and every order must carry the ledger's
  market. No API exists to draw on the NSE cash budget.
- USD-margined-style linear perp: order prices are venue-native USD quotes,
  converted to INR once at the single conversion point via a configurable
  ``fx_rate_inr_per_usd`` with mandatory ``fx_provenance`` documentation,
  mirroring the spot path's INR-denominated fills. Coin-margined inverse
  perps (BTC-denominated margin, non-linear PnL) are OUT OF SCOPE here.
- Funding settles at 8h UTC boundaries (00/08/16, matching the engine's
  ``SETTLEMENT_HOURS``). Payment per contract: ``size * mark_price_usd *
  rate``. With the default ``LONGS_PAY`` convention a positive rate debits
  longs and credits shorts; ``SHORTS_PAY`` flips the sign. Rates must be
  supplied for the exact boundary timestamp (no lookahead interpolation).
- Margin: opening initial margin is ``notional / leverage``. Position equity
  is margin posted plus unrealized PnL (mark-to-market); liquidation closes
  the position at the current mark when equity <= maintenance requirement
  (``maintenance_margin_fraction * notional``).
- All money math is :class:`decimal.Decimal`; fills, funding events and
  liquidations are recorded as auditable frozen records.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Mapping

from .domain import Market

ZERO = Decimal("0")

#: Real perps settle funding at the top of these UTC hours (engine parity).
SETTLEMENT_HOURS_UTC = (0, 8, 16)


class FundingConvention(StrEnum):
    """Who pays when the funding rate is positive.

    ``LONGS_PAY`` is the standard convention (Binance/Bybit/OKX): positive
    rate means longs pay shorts. ``SHORTS_PAY`` is provided for venues that
    invert the sign.
    """

    LONGS_PAY = "longs_pay"
    SHORTS_PAY = "shorts_pay"


class PerpSide(StrEnum):
    """Direction of a perpetual position."""

    LONG = "long"
    SHORT = "short"


def funding_payment_usd(
    side: PerpSide,
    size: Decimal,
    mark_price_usd: Decimal,
    rate: Decimal,
    convention: FundingConvention = FundingConvention.LONGS_PAY,
) -> Decimal:
    """Funding cashflow in USD for one settlement of one position.

    With ``LONGS_PAY`` a positive ``rate`` debits the long (payment is
    negative for the long) and credits the short by the same amount; a
    negative rate reverses the flow. ``SHORTS_PAY`` flips the sign. This
    mirrors ``funding_cashflow`` in the backtest engine's funding module.
    """
    if size <= ZERO or mark_price_usd <= ZERO or rate == ZERO:
        return ZERO
    notional = size * mark_price_usd
    payment = notional * rate
    if convention is FundingConvention.LONGS_PAY:
        return -payment if side is PerpSide.LONG else payment
    return payment if side is PerpSide.LONG else -payment


@dataclass(frozen=True, slots=True)
class DerivativesOrder:
    """One venue-native USD-quoted derivatives order.

    ``price_usd`` is the venue execution price; the single FX conversion to
    INR happens inside the ledger at its configured rate. Margin sufficiency
    is checked against INR wallet funds, never against another market's
    capital.
    """

    order_id: str
    market: Market
    instrument: str
    side: PerpSide
    quantity: Decimal
    price_usd: Decimal
    leverage: Decimal
    timestamp: datetime

    def __post_init__(self) -> None:
        if not self.order_id.strip() or not self.instrument.strip():
            raise ValueError("order_id and instrument must be non-empty")
        if self.side not in (PerpSide.LONG, PerpSide.SHORT):
            raise ValueError("side must be LONG or SHORT")
        if self.quantity <= ZERO or self.price_usd <= ZERO:
            raise ValueError("quantity and price must be positive")
        if self.leverage <= ZERO:
            raise ValueError("leverage must be positive")
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("order timestamp must be timezone-aware")


@dataclass(frozen=True, slots=True)
class DerivativesFill:
    """Executed derivatives fill with venue-native and INR book values."""

    order: DerivativesOrder
    margin_posted_inr: Decimal
    notional_inr: Decimal
    margin_released_inr: Decimal
    fee_inr: Decimal

    def __post_init__(self) -> None:
        if self.notional_inr <= ZERO or self.margin_posted_inr < ZERO:
            raise ValueError("notional must be positive and margin non-negative")
        if self.margin_released_inr < ZERO or self.fee_inr < ZERO:
            raise ValueError("margin released and fee cannot be negative")


@dataclass(frozen=True, slots=True)
class FundingEvent:
    """One settled funding payment against one position."""

    instrument: str
    boundary_utc: datetime
    rate: Decimal
    mark_price_usd: Decimal
    payment_inr: Decimal

    def __post_init__(self) -> None:
        if self.boundary_utc.tzinfo is None or self.boundary_utc.utcoffset() is None:
            raise ValueError("funding boundary timestamp must be timezone-aware")
        if self.boundary_utc.astimezone(UTC).hour not in SETTLEMENT_HOURS_UTC:
            raise ValueError("funding boundaries must land on 8h UTC settlement hours")


@dataclass(frozen=True, slots=True)
class LiquidationEvent:
    """Forced close of a position whose equity fell to maintenance."""

    instrument: str
    boundary_equity_inr: Decimal
    maintenance_requirement_inr: Decimal
    realized_pnl_inr: Decimal


@dataclass(slots=True)
class PerpPosition:
    """Open perpetual position with weighted-average entry accounting.

    ``opened_at`` is the fill timestamp; funding applies only to settlement
    boundaries at or after it (positions held at the funding instant pay).
    """

    side: PerpSide
    quantity: Decimal
    entry_price_usd: Decimal
    leverage: Decimal
    margin_inr: Decimal
    opened_at: datetime

    @property
    def notional_usd(self) -> Decimal:
        return self.quantity * self.entry_price_usd

    def unrealized_pnl_usd(self, mark_price_usd: Decimal) -> Decimal:
        """Linear perp PnL in USD; coin-margined non-linear PnL is out of scope."""
        if self.side is PerpSide.LONG:
            return (mark_price_usd - self.entry_price_usd) * self.quantity
        return (self.entry_price_usd - mark_price_usd) * self.quantity


@dataclass(frozen=True, slots=True)
class DerivativesSnapshot:
    """Point-in-time state of the isolated derivatives account."""

    market: Market
    instrument: str
    balance_inr: Decimal
    used_margin_inr: Decimal
    available_margin_inr: Decimal
    unrealized_pnl_inr: Decimal
    equity_inr: Decimal
    realized_pnl_inr: Decimal
    funding_paid_inr: Decimal
    fees_paid_inr: Decimal
    position_quantity: Decimal
    position_side: PerpSide | None
    entry_price_usd: Decimal
    mark_price_usd: Decimal | None
    maintenance_requirement_inr: Decimal
    order_count: int
    funding_event_count: int
    liquidation_count: int


@dataclass(frozen=True, slots=True)
class PerpetualLedgerConfig:
    """Static contract specification for one perpetual instrument.

    ``fx_rate_inr_per_usd`` is the only FX conversion point: order prices are
    USD quotes, and every INR book value derives from this rate, mirroring the
    spot ledger's INR-denominated, provenance-documented fills.
    """

    market: Market
    instrument: str
    fx_rate_inr_per_usd: Decimal
    maintenance_margin_fraction: Decimal
    funding_convention: FundingConvention = FundingConvention.LONGS_PAY
    max_leverage: Decimal = Decimal("20")

    def __post_init__(self) -> None:
        # Cross-market isolation is asserted at construction, before any order.
        if self.market is not Market.CRYPTO:
            raise ValueError(
                "derivatives ledger supports Market.CRYPTO only; "
                "NSE capital must never back crypto derivatives"
            )
        if not self.instrument.strip():
            raise ValueError("instrument must be non-empty")
        if self.fx_rate_inr_per_usd <= ZERO:
            raise ValueError("fx_rate_inr_per_usd must be positive")
        if not ZERO < self.maintenance_margin_fraction < Decimal("1"):
            raise ValueError("maintenance_margin_fraction must be in (0, 1)")
        if self.max_leverage <= ZERO:
            raise ValueError("max_leverage must be positive")


class PerpetualLedger:
    """Margin-aware perpetual ledger, fully isolated from the spot cash ledger.

    Wallet-balance margin convention (as on real venues): ``balance_inr`` is
    the wallet total with posted margin included, ``used_margin_inr`` reserves
    part of it, free funds are ``balance - used_margin``, and equity is the
    balance plus unrealized PnL at the current INR-converted mark. No method
    can move funds to or from ``MarketLedger`` or NSE capital.
    """

    def __init__(
        self,
        config: PerpetualLedgerConfig,
        initial_margin_inr: Decimal,
        *,
        fx_provenance: str = "manual usdinr reference rate supplied by caller",
    ) -> None:
        if initial_margin_inr <= ZERO:
            raise ValueError("initial margin must be positive")
        if not fx_provenance.strip():
            raise ValueError("fx_provenance must document the INR conversion")
        self.config = config
        self.fx_provenance = fx_provenance
        self.balance_inr = initial_margin_inr
        self.used_margin_inr = ZERO
        self.realized_pnl_inr = ZERO
        self.funding_paid_inr = ZERO
        self.fees_paid_inr = ZERO
        self.position: PerpPosition | None = None
        self.mark_price_usd: Decimal | None = None
        self.funding_events: list[FundingEvent] = []
        self.liquidation_events: list[LiquidationEvent] = []
        self.fills: list[DerivativesFill] = []
        self._order_ids: set[str] = set()
        self._last_funding_utc: datetime | None = None

    # ------------------------------------------------------------------
    # conversion helpers (the single FX conversion point)
    # ------------------------------------------------------------------
    def _to_inr(self, amount_usd: Decimal) -> Decimal:
        return amount_usd * self.config.fx_rate_inr_per_usd

    # ------------------------------------------------------------------
    # trading
    # ------------------------------------------------------------------
    def open_position(self, order: DerivativesOrder, fee_inr: Decimal) -> DerivativesFill:
        """Open a position; the ledger is one-instrument and one-position."""
        self._accept_order(order)
        if self.position is not None:
            raise ValueError(
                "position already open; this ledger supports one position per instrument"
            )
        self._check_leverage(order)
        if fee_inr < ZERO:
            raise ValueError("fee cannot be negative")
        notional_inr = self._to_inr(order.quantity * order.price_usd)
        initial_margin = self._margin_for(order)
        if initial_margin + fee_inr > self.available_margin_inr():
            raise ValueError("insufficient margin for order including fees")
        # Wallet-balance convention: the balance keeps the posted margin inside
        # the wallet; reserving it via used_margin_inr makes it unavailable.
        self.balance_inr -= fee_inr
        self.used_margin_inr += initial_margin
        self.fees_paid_inr += fee_inr
        self.mark_price_usd = order.price_usd
        self.position = PerpPosition(
            side=order.side,
            quantity=order.quantity,
            entry_price_usd=order.price_usd,
            leverage=order.leverage,
            margin_inr=initial_margin,
            opened_at=order.timestamp,
        )
        fill = DerivativesFill(
            order=order,
            margin_posted_inr=initial_margin,
            notional_inr=notional_inr,
            margin_released_inr=ZERO,
            fee_inr=fee_inr,
        )
        self.fills.append(fill)
        self._order_ids.add(order.order_id)
        return fill

    def close_position(self, order: DerivativesOrder, fee_inr: Decimal) -> DerivativesFill:
        """Close the open position (full close; re-opening requires a new order)."""
        self._accept_order(order)
        if self.position is None:
            raise ValueError("no open position to close")
        if fee_inr < ZERO:
            raise ValueError("fee cannot be negative")
        position = self.position
        # A close must flatten the whole position exactly: partial closes and
        # same-side closes are rejected so margin accounting cannot drift.
        if order.quantity != position.quantity:
            raise ValueError("close order quantity must equal the open position quantity")
        if order.side is position.side:
            raise ValueError("close order must be on the opposite side of the open position")
        pnl_inr = self._to_inr(position.unrealized_pnl_usd(order.price_usd))
        initial_margin = position.margin_inr
        # The close fee may draw on free wallet funds as well as the released
        # margin and PnL, mirroring the spot ledger's sell-fee cash rule.
        funds_after_release = self.balance_inr - self.used_margin_inr + initial_margin
        if fee_inr > funds_after_release + pnl_inr:
            raise ValueError("close fee exceeds released margin, PnL and free wallet funds")
        # Release the margin reservation, settle PnL into the wallet, pay the fee.
        self.balance_inr += pnl_inr - fee_inr
        self.used_margin_inr -= initial_margin
        self.realized_pnl_inr += pnl_inr
        self.fees_paid_inr += fee_inr
        self.mark_price_usd = order.price_usd
        self.position = None
        fill = DerivativesFill(
            order=order,
            margin_posted_inr=ZERO,
            notional_inr=self._to_inr(order.quantity * order.price_usd),
            margin_released_inr=initial_margin,
            fee_inr=fee_inr,
        )
        self.fills.append(fill)
        self._order_ids.add(order.order_id)
        return fill

    def mark_to_market(self, mark_price_usd: Decimal) -> None:
        """Record the venue mark used for funding and liquidation checks."""
        if mark_price_usd <= ZERO:
            raise ValueError("mark price must be positive")
        self.mark_price_usd = mark_price_usd

    # ------------------------------------------------------------------
    # funding
    # ------------------------------------------------------------------
    def settle_funding(self, rate: Decimal, boundary: datetime) -> FundingEvent | None:
        """Apply one funding settlement at an 8h UTC boundary.

        Boundary enforcement mirrors the backtest engine: settlement happens
        at 00/08/16 UTC, monotonic in time, and never twice for the same
        boundary. The rate must be the settled rate for the exact boundary
        (no lookahead). ``None`` means nothing was paid: either no position
        was open, or the position was opened after this boundary and must not
        be charged retroactively.
        """
        if boundary.tzinfo is None or boundary.utcoffset() is None:
            raise ValueError("funding boundary timestamp must be timezone-aware")
        b = boundary.astimezone(UTC)
        if b.hour not in SETTLEMENT_HOURS_UTC or b.minute or b.second or b.microsecond:
            raise ValueError(
                "funding must settle exactly on an 8h UTC boundary (00:00, 08:00, 16:00)"
            )
        if self._last_funding_utc is not None and b <= self._last_funding_utc:
            raise ValueError("funding boundary must be strictly after the previous one")
        self._last_funding_utc = b
        position = self.position
        if position is None:
            return None
        # open_position stamps the entry price as the initial mark, so an open
        # position always has a valuation mark here.
        if position.opened_at > b:
            # Venue rule: only positions held at the funding instant pay.
            # A position opened after this boundary must not be charged
            # retroactively for an interval it did not hold.
            return None
        payment_usd = funding_payment_usd(
            position.side,
            position.quantity,
            self.mark_price_usd,
            rate,
            self.config.funding_convention,
        )
        payment_inr = self._to_inr(payment_usd)
        self.balance_inr += payment_inr
        self.funding_paid_inr -= payment_inr
        event = FundingEvent(
            instrument=self.config.instrument,
            boundary_utc=b,
            rate=rate,
            mark_price_usd=self.mark_price_usd,
            payment_inr=payment_inr,
        )
        self.funding_events.append(event)
        return event

    def funding_boundaries_between(
        self, previous: datetime, current: datetime
    ) -> tuple[datetime, ...]:
        """8h UTC boundaries with ``previous < b <= current`` (engine parity)."""
        for ts in (previous, current):
            if ts.tzinfo is None or ts.utcoffset() is None:
                raise ValueError("boundary window timestamps must be timezone-aware")
        prev = previous.astimezone(UTC)
        cur = current.astimezone(UTC)
        if cur <= prev:
            return ()
        # Walk from the first boundary after prev.
        hour = (prev.hour // 8) * 8
        candidate = prev.replace(hour=hour, minute=0, second=0, microsecond=0)
        if candidate <= prev:
            candidate += timedelta(hours=8)
        boundaries: list[datetime] = []
        while candidate <= cur:
            boundaries.append(candidate)
            candidate += timedelta(hours=8)
        return tuple(boundaries)

    # ------------------------------------------------------------------
    # margin and liquidation
    # ------------------------------------------------------------------
    def _margin_for(self, order: DerivativesOrder) -> Decimal:
        return self._to_inr(order.quantity * order.price_usd) / order.leverage

    def maintenance_requirement_inr(self, mark_price_usd: Decimal) -> Decimal:
        """Maintenance margin for the open position at the current mark."""
        position = self.position
        if position is None:
            return ZERO
        notional_inr = self._to_inr(position.quantity * mark_price_usd)
        return notional_inr * self.config.maintenance_margin_fraction

    def equity(self, mark_price_usd: Decimal) -> Decimal:
        """Wallet balance plus mark-to-market PnL of the open position."""
        if mark_price_usd <= ZERO:
            raise ValueError("mark price must be positive")
        pnl = (
            self._to_inr(self.position.unrealized_pnl_usd(mark_price_usd))
            if self.position is not None
            else ZERO
        )
        # Balance holds wallet total (posted margin included) in this convention.
        return self.balance_inr + pnl

    def unrealized_pnl_inr(self, mark_price_usd: Decimal) -> Decimal:
        if self.position is None:
            return ZERO
        if mark_price_usd <= ZERO:
            raise ValueError("mark price must be positive")
        return self._to_inr(self.position.unrealized_pnl_usd(mark_price_usd))

    def available_margin_inr(self) -> Decimal:
        """Free collateral: wallet balance minus margin already posted."""
        return self.balance_inr - self.used_margin_inr

    def check_liquidation(self, mark_price_usd: Decimal) -> LiquidationEvent | None:
        """Liquidate when equity <= maintenance requirement at the current mark.

        Equity is compared with the maintenance requirement using inclusive
        ``<=`` (the requirement itself must be covered). The forced close
        settles PnL at the current mark, releases margin, and clears the
        position. The mark is recorded first, so the caller can re-check
        after any price move.
        """
        self.mark_to_market(mark_price_usd)
        position = self.position
        if position is None:
            return None
        requirement = self.maintenance_requirement_inr(mark_price_usd)
        equity = self.equity(mark_price_usd)
        if equity > requirement:
            return None
        pnl_inr = self._to_inr(position.unrealized_pnl_usd(mark_price_usd))
        # Forced close: posted margin returns to the wallet together with
        # realized PnL. Equity can go negative; the wallet absorbs it and the
        # balance reflects the loss exactly (no insurance-fund modelling).
        self.balance_inr += pnl_inr
        self.used_margin_inr -= position.margin_inr
        self.realized_pnl_inr += pnl_inr
        self.position = None
        event = LiquidationEvent(
            instrument=self.config.instrument,
            boundary_equity_inr=equity,
            maintenance_requirement_inr=requirement,
            realized_pnl_inr=pnl_inr,
        )
        self.liquidation_events.append(event)
        return event

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------
    def _accept_order(self, order: DerivativesOrder) -> None:
        # Cross-market isolation: orders from another market are rejected
        # before any ledger mutation, mirroring MarketLedger.apply_fill.
        if order.market is not self.config.market:
            raise ValueError(
                f"cross-market order rejected: {order.market.value} order on "
                f"{self.config.market.value} derivatives ledger"
            )
        if order.instrument != self.config.instrument:
            raise ValueError("order instrument must match the ledger's instrument")
        if order.order_id in self._order_ids:
            raise ValueError(f"duplicate order id: {order.order_id}")

    def _check_leverage(self, order: DerivativesOrder) -> None:
        if order.leverage > self.config.max_leverage:
            raise ValueError(
                f"leverage {order.leverage} exceeds the instrument cap {self.config.max_leverage}"
            )

    def snapshot(self, mark_price_usd: Decimal | None = None) -> DerivativesSnapshot:
        """Return the isolated account state, optionally re-marked first.

        Opening a position records its entry price as the first mark, so an
        open position always has a valuation mark.
        """
        if mark_price_usd is not None:
            self.mark_to_market(mark_price_usd)
        position = self.position
        if position is not None:
            mark = self.mark_price_usd
            requirement = self.maintenance_requirement_inr(mark)
            pnl = self._to_inr(position.unrealized_pnl_usd(mark))
            equity = self.equity(mark)
        else:
            requirement, pnl, equity = ZERO, ZERO, self.balance_inr
            mark = self.mark_price_usd
        return DerivativesSnapshot(
            market=self.config.market,
            instrument=self.config.instrument,
            balance_inr=self.balance_inr,
            used_margin_inr=self.used_margin_inr,
            available_margin_inr=self.available_margin_inr(),
            unrealized_pnl_inr=pnl,
            equity_inr=self.equity(mark) if mark is not None else self.balance_inr,
            realized_pnl_inr=self.realized_pnl_inr,
            funding_paid_inr=self.funding_paid_inr,
            fees_paid_inr=self.fees_paid_inr,
            position_quantity=self.position.quantity if self.position else ZERO,
            position_side=self.position.side if self.position else None,
            entry_price_usd=self.position.entry_price_usd if self.position else ZERO,
            mark_price_usd=mark,
            maintenance_requirement_inr=requirement,
            order_count=len(self._order_ids),
            funding_event_count=len(self.funding_events),
            liquidation_count=len(self.liquidation_events),
        )
