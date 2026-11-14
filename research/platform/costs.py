"""Market-specific fill fee calculators with date-effective statutory schedules.

The undated ``FeeCalculator`` protocol remains the runtime contract used by the
portfolio simulator. NSE delivery fees additionally resolve per statutory
component **as of the fill date** (audit F-012): every component carries a
verified effective-date window list, a fill resolves its fee through
``fee_asof``, and a date without verified coverage is an explicit error — never
a silent default.

Verified history encoded below (sources cited on each window; never guess a
date — extend windows only with verified references):

- STT, equity delivery: **0.1% on both sides** since Finance Act 2012
  (eff. 2012-07-01, which cut delivery from 0.125% to 0.1%). The Union Budget
  2024 change effective 2024-10-01 (NSE Circular Ref. 2/2024, download ref
  NSE/FATAX/63809) revised **F&O STT only** (options premium 0.0625%→0.1%,
  futures 0.0125%→0.02%); delivery equity stayed 0.1% both sides. The older
  "delivery used to be sell-only" gloss in ``src/nsealgo/costs.py`` is a wrong
  historical comment on a real code-bug regression and is deliberately **not**
  encoded here: a sell-only pre-2024 window would understate a decade of
  buy-side costs (``GOAL.md`` §6.4 forbids that direction).
- Exchange transaction charge, NSE cash segment: long-standing headline rate
  0.00325% of turnover until 2024-09-30; NSE/FA/64232 (2024-09-27) replaced
  the slab-wise structure with a uniform flat 0.00297% (₹297/crore) from
  2024-10-01. The current window is modelled at the repository's conservative
  nsealgo floor 0.00307% (``P_EXCHANGE_TXN``), never weaker than the real
  post-2024 slab rate. The three numbers in play: 0.00325% (real pre-2024 rate
  and the pre-window value below), 0.00307% (nsealgo code constant, current
  window), 0.00297% (real new flat slab rate, unused because it would weaken
  the modelled floor).
- SEBI turnover fee, cash segment: verified series ₹10/crore (0.0001%) →
  ₹20/crore (SEBI Payment of Fees Amendment Regulations, eff. 2014-05-23) →
  ₹15/crore (eff. 2017-04-01). The current window encodes the verified
  ₹15/crore (0.00015%) — strictly above the stale nsealgo P_SEBI floor, which
  is honoured as an inequality (never reduce costs, ``GOAL.md`` §6.4).
- Stamp duty: pre-unification state regime (NSE/Maharashtra convention 0.01%
  on BOTH sides) until 2020-06-30; uniform 0.015% buy-side only from
  2020-07-01 (Indian Stamp Act collection rules eff. 2020-07-01). Buy-only
  modelling before 2020 would understate the round trip.
- GST on (brokerage + exchange txn + SEBI): service-tax era modelled at the
  15% ceiling until 2017-06-30; GST 18% from 2017-07-01 (GST rollout).
- DP charges ₹15.93 per scrip per sell and zero delivery brokerage are flat
  documented simplifications over the modelled era (floor 2013-06-01).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Protocol

from .domain import Market
from .market import Side


D = Decimal

#: First day with verified statutory coverage for the dated NSE schedule.
SCHEDULE_FLOOR_DATE = date(2013, 6, 1)

#: Fee-schedule provenance recorded with every dated fee resolution.
SCHEDULE_VERSION = "nse-delivery-dated-v1"


def _round2(value: Decimal) -> Decimal:
    """Quantise to paise exactly like the repository's ground-truth cost model."""
    return value.quantize(D("0.01"), rounding=ROUND_HALF_UP)


class FeeCalculator(Protocol):
    """Runtime fee calculator contract; returns a non-negative INR charge."""

    market: Market
    model_id: str

    def fee(self, side: Side, quantity: Decimal, price: Decimal) -> Decimal:
        """Return the fee for one simulated fill."""


class DatedFeeScheduleError(ValueError):
    """A date-effective schedule has no verified coverage for a requested date."""


@dataclass(frozen=True, slots=True)
class DatedRateWindow:
    """One verified statutory rate segment, effective on start (inclusive)."""

    rate: Decimal
    start_date: date
    end_date: date | None = None  # inclusive; None = open-ended current window
    source: str = ""  # verified act/circular reference, provenance only


@dataclass(frozen=True, slots=True)
class FeeComponentSchedule:
    """Contiguous, sorted, open-ended window list for one fee component."""

    name: str
    windows: tuple[DatedRateWindow, ...]

    def __post_init__(self) -> None:
        # Malformed schedule data must fail at construction, never at fill time.
        if not self.windows:
            raise ValueError(f"{self.name}: at least one rate window is required")
        starts = [window.start_date for window in self.windows]
        if starts != sorted(starts) or len(set(starts)) != len(starts):
            raise ValueError(f"{self.name}: rate windows must be sorted and unique")
        for previous, following in zip(self.windows, self.windows[1:]):
            if previous.end_date is None:
                raise ValueError(f"{self.name}: only the final window may be open-ended")
            if following.start_date != previous.end_date + timedelta(days=1):
                raise ValueError(
                    f"{self.name}: windows must be contiguous at "
                    f"{previous.end_date.isoformat()} -> {following.start_date.isoformat()}"
                )
        if self.windows[-1].end_date is not None:
            raise ValueError(f"{self.name}: the final window must be open-ended")

    def rate_asof(self, when: date) -> Decimal:
        """Resolve the verified rate for ``when`` or raise; never silently default."""
        for window in self.windows:
            if when >= window.start_date and (window.end_date is None or when <= window.end_date):
                return window.rate
        floor = self.windows[0].start_date
        raise DatedFeeScheduleError(
            f"{self.name}: no verified fee rate covers {when.isoformat()}; "
            f"the schedule floor is {floor.isoformat()}. Refusing to silently default "
            "to the current window — extend the schedule with a verified reference."
        )


@dataclass(frozen=True, slots=True)
class DatedFeeBreakdown:
    """Itemised, paise-quantised cost of one fill under one dated schedule."""

    when: date
    side: str
    schedule_id: str
    turnover: Decimal
    brokerage: Decimal
    stt: Decimal
    exchange_txn: Decimal
    sebi: Decimal
    stamp_duty: Decimal
    dp_charges: Decimal
    gst: Decimal
    total: Decimal

    @property
    def bps(self) -> Decimal:
        """Total cost in basis points of the fill's turnover."""
        if self.turnover == 0:
            return D("0")
        return (self.total / self.turnover * D("10000")).quantize(D("0.01"))

    def as_dict(self) -> dict[str, object]:
        """Return every dated component plus provenance for experiment records."""
        return {
            "when": self.when.isoformat(),
            "side": self.side,
            "schedule_id": self.schedule_id,
            "turnover": self.turnover,
            "brokerage": self.brokerage,
            "stt": self.stt,
            "exchange_txn": self.exchange_txn,
            "sebi": self.sebi,
            "stamp_duty": self.stamp_duty,
            "dp_charges": self.dp_charges,
            "gst": self.gst,
            "total": self.total,
            "bps": self.bps,
        }


@dataclass(frozen=True, slots=True)
class NSEDatedFeeSchedule:
    """Date-effective NSE delivery statutory schedule (audit F-012).

    Every fractional component resolves through its own verified window list;
    flat charges (DP, brokerage) carry documented simplification constants.
    """

    schedule_id: str
    floor_date: date
    stt_delivery: FeeComponentSchedule
    exchange_txn: FeeComponentSchedule
    sebi_turnover: FeeComponentSchedule
    stamp_duty_buy: FeeComponentSchedule
    stamp_duty_sell: FeeComponentSchedule
    gst_on_services: FeeComponentSchedule
    dp_per_scrip_sell: Decimal
    brokerage_per_order: Decimal

    def __post_init__(self) -> None:
        # One uniform floor keeps "unknown date" semantics explicit and identical.
        components = (
            self.stt_delivery,
            self.exchange_txn,
            self.sebi_turnover,
            self.stamp_duty_buy,
            self.stamp_duty_sell,
            self.gst_on_services,
        )
        for component in components:
            if component.windows[0].start_date != self.floor_date:
                raise ValueError(
                    f"{component.name}: first window must start at the schedule floor "
                    f"{self.floor_date.isoformat()}"
                )
        if self.dp_per_scrip_sell < 0 or self.brokerage_per_order < 0:
            raise ValueError("flat charges cannot be negative")

    def breakdown(
        self,
        when: datetime | date,
        side: Side | str,
        quantity: Decimal,
        price: Decimal,
    ) -> DatedFeeBreakdown:
        """Resolve every component as of ``when`` and itemise the fill cost."""
        on_date = when.date() if isinstance(when, datetime) else when
        if not isinstance(on_date, date):
            raise TypeError("when must be a date or timezone-aware datetime")
        side_value = side.value if isinstance(side, Side) else str(side).strip().lower()
        if side_value not in ("buy", "sell"):
            raise ValueError(f"side must be buy or sell, got {side!r}")
        for name, value in (("quantity", quantity), ("price", price)):
            if isinstance(value, float):
                raise TypeError(f"{name} must be Decimal for money, got float")
        qty = quantity if isinstance(quantity, Decimal) else D(str(quantity))
        rate_price = price if isinstance(price, Decimal) else D(str(price))
        if qty < 0 or rate_price < 0:
            raise ValueError("quantity and price must be non-negative")

        # Mirror the ground-truth model: round turnover first, then components.
        turnover = _round2(qty * rate_price)
        brokerage = min(turnover * D("0.0003"), self.brokerage_per_order)
        stt = turnover * self.stt_delivery.rate_asof(on_date)
        exchange_txn = turnover * self.exchange_txn.rate_asof(on_date)
        sebi = turnover * self.sebi_turnover.rate_asof(on_date)
        if side_value == "buy":
            stamp = turnover * self.stamp_duty_buy.rate_asof(on_date)
            dp = D("0")
        else:
            stamp = turnover * self.stamp_duty_sell.rate_asof(on_date)
            dp = self.dp_per_scrip_sell
        # GST charges the unrounded service base exactly like nsealgo.costs.
        gst = _round2((brokerage + exchange_txn + sebi) * self.gst_on_services.rate_asof(on_date))
        total = _round2(
            _round2(brokerage)
            + _round2(stt)
            + _round2(exchange_txn)
            + _round2(sebi)
            + _round2(stamp)
            + _round2(dp)
            + gst
        )
        return DatedFeeBreakdown(
            when=on_date,
            side=side_value,
            schedule_id=self.schedule_id,
            turnover=turnover,
            brokerage=_round2(brokerage),
            stt=_round2(stt),
            exchange_txn=_round2(exchange_txn),
            sebi=_round2(sebi),
            stamp_duty=_round2(stamp),
            dp_charges=_round2(dp),
            gst=gst,
            total=total,
        )

    @classmethod
    def statutory_delivery_v1(cls) -> "NSEDatedFeeSchedule":
        """Build the verified NSE delivery schedule v1 (floor 2013-06-01)."""
        return cls(
            schedule_id=SCHEDULE_VERSION,
            floor_date=SCHEDULE_FLOOR_DATE,
            stt_delivery=FeeComponentSchedule(
                name="stt_delivery",
                windows=(
                    DatedRateWindow(
                        rate=D("0.001"),
                        start_date=SCHEDULE_FLOOR_DATE,
                        source=(
                            "Finance Act 2012 (eff. 2012-07-01) 0.1% both sides; unchanged "
                            "by NSE Circular Ref. 2/2024 / NSE/FATAX/63809 eff. 2024-10-01, "
                            "which revised F&O STT only"
                        ),
                    ),
                ),
            ),
            exchange_txn=FeeComponentSchedule(
                name="exchange_txn",
                windows=(
                    DatedRateWindow(
                        rate=D("0.0000325"),
                        start_date=SCHEDULE_FLOOR_DATE,
                        end_date=date(2024, 9, 30),
                        source="NSE cash-segment slab-era headline rate 0.00325%",
                    ),
                    DatedRateWindow(
                        rate=D("0.0000307"),
                        start_date=date(2024, 10, 1),
                        source=(
                            "NSE/FA/64232 (2024-09-27): uniform flat 0.00297% (Rs 297/crore) "
                            "eff. 2024-10-01; modelled at the conservative nsealgo floor 0.00307%"
                        ),
                    ),
                ),
            ),
            sebi_turnover=FeeComponentSchedule(
                name="sebi_turnover",
                windows=(
                    DatedRateWindow(
                        rate=D("0.000001"),
                        start_date=SCHEDULE_FLOOR_DATE,
                        end_date=date(2014, 5, 22),
                        source="SEBI Payment of Fees Regulations: Rs10/crore (0.0001%)",
                    ),
                    DatedRateWindow(
                        rate=D("0.000002"),
                        start_date=date(2014, 5, 23),
                        end_date=date(2017, 3, 31),
                        source=(
                            "SEBI Payment of Fees (Amendment) Regulations 2014 eff. "
                            "2014-05-23: Rs20/crore (0.0002%)"
                        ),
                    ),
                    DatedRateWindow(
                        rate=D("0.0000015"),
                        start_date=date(2017, 4, 1),
                        source=(
                            "SEBI amendment eff. 2017-04-01: Rs15/crore (0.00015%), "
                            "strictly above the nsealgo Rs10/crore floor"
                        ),
                    ),
                ),
            ),
            stamp_duty_buy=FeeComponentSchedule(
                name="stamp_duty_buy",
                windows=(
                    DatedRateWindow(
                        rate=D("0.0001"),
                        start_date=SCHEDULE_FLOOR_DATE,
                        end_date=date(2020, 6, 30),
                        source="Pre-unification state regime (NSE/Maharashtra convention 0.01%)",
                    ),
                    DatedRateWindow(
                        rate=D("0.00015"),
                        start_date=date(2020, 7, 1),
                        source="Indian Stamp Act collection rules eff. 2020-07-01: 0.015% delivery buy",
                    ),
                ),
            ),
            stamp_duty_sell=FeeComponentSchedule(
                name="stamp_duty_sell",
                windows=(
                    DatedRateWindow(
                        rate=D("0.0001"),
                        start_date=SCHEDULE_FLOOR_DATE,
                        end_date=date(2020, 6, 30),
                        source="Pre-unification both-sides 0.01% (state regime)",
                    ),
                    DatedRateWindow(
                        rate=D("0"),
                        start_date=date(2020, 7, 1),
                        source="No seller stamp duty after uniform collection eff. 2020-07-01",
                    ),
                ),
            ),
            gst_on_services=FeeComponentSchedule(
                name="gst_on_services",
                windows=(
                    DatedRateWindow(
                        rate=D("0.15"),
                        start_date=SCHEDULE_FLOOR_DATE,
                        end_date=date(2017, 6, 30),
                        source="Service-tax era modelled at the 15% ceiling",
                    ),
                    DatedRateWindow(
                        rate=D("0.18"),
                        start_date=date(2017, 7, 1),
                        source="GST 18% on brokerage + exchange txn + SEBI eff. 2017-07-01",
                    ),
                ),
            ),
            dp_per_scrip_sell=D("15.93"),
            brokerage_per_order=D("0"),
        )


#: The canonical dated schedule used by the NSE delivery fee calculator.
NSE_STATUTORY_DELIVERY_SCHEDULE = NSEDatedFeeSchedule.statutory_delivery_v1()


@dataclass(frozen=True, slots=True)
class NSEDeliveryFeeCalculator:
    """Undated statutory delivery fees + date-effective resolution (F-012).

    ``fee()`` keeps the established, calibrated behaviour so existing callers
    and pinned ``cost_model_id="nse-delivery-cost-model"`` experiments are
    unchanged. Date-effective resolution is exposed through ``fee_asof`` /
    ``breakdown_asof``, which resolve the built-in verified schedule at the
    fill date; a date without coverage raises ``DatedFeeScheduleError``.
    """

    model_id: str = "nse-delivery-cost-model"
    model: object | None = None
    schedule: NSEDatedFeeSchedule = NSE_STATUTORY_DELIVERY_SCHEDULE

    @property
    def market(self) -> Market:
        # NSE delivery assumptions must never be attached to crypto fills.
        return Market.NSE

    @property
    def schedule_version(self) -> str:
        """Dated schedule version recorded with every experiment (audit 7.13)."""
        return self.schedule.schedule_id

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

    def breakdown_asof(
        self,
        when: datetime | date,
        side: Side | str,
        quantity: Decimal,
        price: Decimal,
    ) -> DatedFeeBreakdown:
        """Itemise the statutory cost under the schedule effective on ``when``."""
        if self.model is not None:
            raise ValueError(
                "breakdown_asof requires the built-in statutory schedule; "
                "this calculator delegates to an injected custom model without date windows"
            )
        return self.schedule.breakdown(when, side, quantity, price)

    def fee_asof(
        self,
        when: datetime | date,
        side: Side | str,
        quantity: Decimal,
        price: Decimal,
    ) -> Decimal:
        """Return the fill fee under the schedule effective on ``when``."""
        return self.breakdown_asof(when, side, quantity, price).total


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
