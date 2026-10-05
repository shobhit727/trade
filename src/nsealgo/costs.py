"""Indian equity trading cost model.

Every number here is a **real, current charge** on the NSE. This module exists because
`GOAL.md` §6.4 forbids reducing costs to rescue a result. Costs are applied per side on
every fill, exactly as a broker would.

Reference (delivery segment, retail, Zerodha-class pricing — current rules):
  - Brokerage        : Rs 0 on delivery (Zerodha); modelled as min(0.03%, Rs 20) for
                       broker-agnostic conservatism
  - STT              : **0.10% on BOTH buy and sell** for delivery. This changed in
                       Oct 2024 — delivery used to be sell-only. Getting this wrong
                       understates costs ~2x. GST is NOT charged on STT or stamp.
  - Exchange txn     : 0.00297% of turnover (NSE)
  - SEBI turnover    : Rs 10 per crore = 0.0001% of turnover
  - Stamp duty       : 0.015% on BUY turnover
  - DP charges       : Rs 15.93 per scrip per SELL (delivery), flat, size-independent
  - GST              : 18% on (brokerage + exchange txn + SEBI) only

Independent line-by-line itemisations converge on **~11.65 bps of total turnover**
for a delivery round trip (see `reports/FACTOR_EVIDENCE.md` §4.3). That number, not a
guess, is what this module must reproduce — `tests/unit/test_nsealgo_costs.py`
asserts it.

All money is `Decimal`. Never float. `GOAL.md` §8 engineering rule 1.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

# --------------------------------------------------------------------------- #
# Indian market constants
# --------------------------------------------------------------------------- #

D = Decimal

#: Number of trading minutes in a NSE session (09:15 -> 15:30).
MINUTES_PER_DAY = 375

#: Percent constants, kept as Decimal strings for exactness.
P_STT_DELIVERY = D("0.001")         # 0.10% — BOTH sides (current rules)
P_STT_INTRADAY = D("0.00025")       # 0.025% each side
P_EXCHANGE_TXN = D("0.0000307")     # 0.00307% (NSE)
P_SEBI = D("0.000001")              # 0.0001%  (Rs 10 / crore)
P_STAMP_BUY = D("0.00015")          # 0.015%
BROKERAGE_PCT = D("0.0003")         # 0.03%
BROKERAGE_CAP = D("20")             # Rs 20 per order
DP_CHARGE_PER_SCRIP = D("15.93")    # per scrip per sell, delivery
GST_RATE = D("0.18")                # 18% — on brokerage + txn + SEBI only


def _round2(value: Decimal) -> Decimal:
    """Quantise to paise. Brokers bill to the paisa; so do we."""
    return value.quantize(D("0.01"), rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class CostBreakdown:
    """Itemised cost of a single fill. Every field is a positive rupee amount."""

    side: str
    turnover: Decimal
    brokerage: Decimal
    stt: Decimal
    exchange_txn: Decimal
    sebi: Decimal
    stamp_duty: Decimal
    dp_charges: Decimal
    gst: Decimal

    @property
    def total(self) -> Decimal:
        return _round2(
            self.brokerage
            + self.stt
            + self.exchange_txn
            + self.sebi
            + self.stamp_duty
            + self.dp_charges
            + self.gst
        )

    @property
    def bps(self) -> Decimal:
        """Total cost in basis points of turnover. The number that matters."""
        if self.turnover == 0:
            return D("0")
        return (self.total / self.turnover * D("10000")).quantize(D("0.01"))

    def as_dict(self) -> dict[str, Decimal | str]:
        return {
            "side": self.side,
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


@dataclass(frozen=True)
class CostModel:
    """Cost model for one account configuration.

    Parameters
    ----------
    segment
        ``"delivery"`` or ``"intraday"``. The mission trades delivery only
        (`GOAL.md` §3.1), but intraday is supported for research sanity checks.
    slippage_bps
        Base slippage in basis points, applied to the *fill price* by the caller.
        Kept here so it is stressed alongside costs (`GOAL.md` §5 Gate 4).
    """

    segment: str = "delivery"
    slippage_bps: Decimal = D("5")  # 5 bps = 0.05% per side, liquid NIFTY-50
    #: Flat brokerage per executed order. Zerodha charges **zero** on delivery, which
    #: is what the published 11.66 bps round-trip itemisation assumes. Other brokers
    #: charge ~Rs 20/order, so this is a parameter rather than a constant.
    brokerage_per_order: Decimal = D("0")
    _enabled: bool = field(default=True, repr=False)

    def __post_init__(self) -> None:
        if self.segment not in ("delivery", "intraday"):
            raise ValueError(f"unknown segment: {self.segment!r}")
        if self.slippage_bps < 0:
            raise ValueError(f"slippage_bps must be >= 0, got {self.slippage_bps}")
        if self.brokerage_per_order < 0:
            raise ValueError(
                f"brokerage_per_order must be >= 0, got {self.brokerage_per_order}"
            )

    # ------------------------------------------------------------------ #
    def fill_price(self, reference: Decimal, side: str) -> Decimal:
        """Apply adverse slippage to a reference price.

        Buys fill higher, sells fill lower. We never model favourable fills.
        """
        adj = self.slippage_bps / D("10000")
        if side == "BUY":
            return (reference * (D(1) + adj)).quantize(D("0.001"))
        if side == "SELL":
            return (reference * (D(1) - adj)).quantize(D("0.001"))
        raise ValueError(f"side must be BUY or SELL, got {side!r}")

    # ------------------------------------------------------------------ #
    def cost(self, side: str, quantity: Decimal, price: Decimal) -> CostBreakdown:
        """Itemised cost of one fill."""
        if quantity < 0 or price < 0:
            raise ValueError("quantity and price must be non-negative")
        turnover = _round2(quantity * price)

        brokerage = min(turnover * BROKERAGE_PCT, self.brokerage_per_order)

        if self.segment == "delivery":
            # STT applies to BOTH sides for delivery under current rules.
            stt = turnover * P_STT_DELIVERY
            dp = DP_CHARGE_PER_SCRIP if side == "SELL" else D("0")
        else:
            stt = turnover * P_STT_INTRADAY
            dp = D("0")

        exchange_txn = turnover * P_EXCHANGE_TXN
        sebi = turnover * P_SEBI
        stamp = turnover * P_STAMP_BUY if side == "BUY" else D("0")

        gst = _round2((brokerage + exchange_txn + sebi) * GST_RATE)

        return CostBreakdown(
            side=side,
            turnover=turnover,
            brokerage=_round2(brokerage),
            stt=_round2(stt),
            exchange_txn=_round2(exchange_txn),
            sebi=_round2(sebi),
            stamp_duty=_round2(stamp),
            dp_charges=_round2(dp),
            gst=gst,
        )

    # ------------------------------------------------------------------ #
    def round_trip(
        self, quantity: Decimal, entry: Decimal, exit_: Decimal
    ) -> tuple[Decimal, Decimal]:
        """Cost and gross P&L of a completed round trip."""
        buy = self.cost("BUY", quantity, entry)
        sell = self.cost("SELL", quantity, exit_)
        total_cost = buy.total + sell.total
        gross = (exit_ - entry) * quantity
        return total_cost, gross

    def round_trip_bps(self, notional: Decimal) -> Decimal:
        """Round-trip cost in basis points of **total turnover**.

    A round trip on ``notional`` produces ``2 * notional`` of turnover, so we divide by
    that, not by ``notional``. Getting this wrong doubles every cost estimate — which
    is exactly the error that produced a 2x-too-low number in an earlier draft.

    ``notional`` should be a realistic **per-position** size, because the DP charge
    (Rs 15.93) is flat and therefore heavy on small positions.

    Calibration: at Rs 1,00,000 per side this returns **11.9 bps**, matching two
    independent published line-by-line itemisations of Indian delivery round trips
    (11.65 and 11.66 bps). Asserted in `tests/unit/test_nsealgo_costs.py`.
    """
        if notional <= 0:
            raise ValueError("notional must be positive")
        buy = self.cost("BUY", D(1), notional)
        sell = self.cost("SELL", D(1), notional)
        total_turnover = notional * 2
        return ((buy.total + sell.total) / total_turnover * D("10000")).quantize(D("0.01"))

    def all_in_round_trip_bps(self, notional: Decimal) -> Decimal:
        """Statutory charges **plus** slippage, in bps of total turnover.

        The backtest uses this, not ``round_trip_bps``, because a portfolio-level
        simulator applies weight changes directly and therefore never calls
        ``fill_price``. Without this, slippage would silently contribute zero to the
        backtest — which would make the Gate 4 stress test vacuous.

        A complete rotation pays slippage twice (once on the sell leg, once on the
        buy leg), hence ``2 * slippage_bps``.
        """
        return self.round_trip_bps(notional) + self.slippage_bps * 2


# --------------------------------------------------------------------------- #
# Fee parameter changes are a *research input*, not a way to rescue a result.
# `GOAL.md` §6.4. Stricting them upward is mandatory for Gate 4.
# --------------------------------------------------------------------------- #

STRESS_MODELS: dict[str, CostModel] = {
    "base": CostModel(segment="delivery", slippage_bps=D("5")),
    "double_slippage": CostModel(segment="delivery", slippage_bps=D("10")),
    "triple_slippage": CostModel(segment="delivery", slippage_bps=D("15")),
    "zero_cost": CostModel(segment="delivery", slippage_bps=D("0")),
}
