"""F-014: perpetual-futures ledger tests — funding, margin, liquidation, isolation.

Every monetary assertion is Decimal-exact. The ledger is USD-margined-style
linear perp converted to INR via a configurable FX rate; coin-margined perps
are out of scope by design. FX = 80 INR/USD keeps every division exact so
assertions stay plain integer decimals.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from research.platform.derivatives import (
    DerivativesOrder,
    FundingConvention,
    PerpSide,
    PerpetualLedger,
    PerpetualLedgerConfig,
    funding_payment_usd,
)
from research.platform.domain import Market

D = Decimal

FX = D("80")  # INR per USD for the whole suite
IST = timezone(offset=timedelta(hours=5, minutes=30))


def make_config(**overrides) -> PerpetualLedgerConfig:
    defaults = dict(
        market=Market.CRYPTO,
        instrument="BTCUSDT-PERP",
        fx_rate_inr_per_usd=FX,
        maintenance_margin_fraction=D("0.005"),
    )
    defaults.update(overrides)
    return PerpetualLedgerConfig(**defaults)


def make_ledger(initial_margin: Decimal = D("1_000_000")) -> PerpetualLedger:
    return PerpetualLedger(make_config(), initial_margin)


def open_order(
    side: PerpSide,
    quantity: Decimal,
    price_usd: Decimal,
    leverage: Decimal,
    order_id: str = "o1",
) -> DerivativesOrder:
    return DerivativesOrder(
        order_id=order_id,
        market=Market.CRYPTO,
        instrument="BTCUSDT-PERP",
        side=side,
        quantity=quantity,
        price_usd=price_usd,
        leverage=leverage,
        timestamp=datetime(2024, 3, 1, 0, 0, tzinfo=UTC),
    )


def close_order(order: DerivativesOrder, price_usd: Decimal, order_id: str = "o2") -> DerivativesOrder:
    return DerivativesOrder(
        order_id=order_id,
        market=order.market,
        instrument=order.instrument,
        side=PerpSide.SHORT if order.side is PerpSide.LONG else PerpSide.LONG,
        quantity=order.quantity,
        price_usd=price_usd,
        leverage=order.leverage,
        timestamp=order.timestamp + timedelta(hours=1),
    )


# ---------------------------------------------------------------------------
# funding sign convention
# ---------------------------------------------------------------------------

def test_funding_sign_long_pays_positive_rate() -> None:
    # Standard convention: positive rate debits the long, credits the short.
    size, mark, rate = D("2"), D("50000"), D("0.0001")
    notional = size * mark  # 100000 USD
    assert funding_payment_usd(PerpSide.LONG, size, mark, rate) == -notional * rate
    assert funding_payment_usd(PerpSide.SHORT, size, mark, rate) == notional * rate
    # INR payment booked on a live ledger for a long position.
    ledger = make_ledger()
    order = open_order(PerpSide.LONG, D("1"), D("50000"), D("20"))
    ledger.open_position(order, D("80"))
    ledger.mark_to_market(D("50000"))
    event = ledger.settle_funding(D("0.0001"), datetime(2024, 3, 1, 8, 0, tzinfo=UTC))
    assert event is not None
    # 1 * 50000 * 0.0001 = 5 USD -> 400 INR paid by the long.
    assert event.payment_inr == D("-400")
    assert event.payment_inr == -(D("50000") * D("0.0001") * FX)
    assert ledger.balance_inr == D("1_000_000") - D("80") - D("400")


def test_funding_sign_shorts_pay_negative_rate() -> None:
    # A negative rate reverses the flow: shorts pay, longs receive.
    ledger = make_ledger()
    order = open_order(PerpSide.SHORT, D("1"), D("50000"), D("20"))
    ledger.open_position(order, D("0"))
    ledger.mark_to_market(D("50000"))
    event = ledger.settle_funding(D("-0.0001"), datetime(2024, 3, 1, 8, 0, tzinfo=UTC))
    assert event is not None
    assert event.payment_inr == D("-400")  # short pays 400 INR
    assert ledger.balance_inr == D("1_000_000") - D("400")


def test_funding_convention_configurable() -> None:
    # SHORTS_PAY flips the sign relative to the default LONGS_PAY.
    longs_pay = funding_payment_usd(PerpSide.LONG, D("1"), D("50000"), D("0.0001"))
    shorts_pay = funding_payment_usd(
        PerpSide.LONG, D("1"), D("50000"), D("0.0001"), FundingConvention.SHORTS_PAY
    )
    assert longs_pay == -shorts_pay
    assert longs_pay == D("-5")
    # A ledger built with the flipped convention books the flipped payment.
    ledger = PerpetualLedger(
        make_config(funding_convention=FundingConvention.SHORTS_PAY), D("1_000_000")
    )
    ledger.open_position(open_order(PerpSide.LONG, D("1"), D("50000"), D("20")), D("0"))
    ledger.mark_to_market(D("50000"))
    event = ledger.settle_funding(D("0.0001"), datetime(2024, 3, 1, 8, 0, tzinfo=UTC))
    assert event is not None
    assert event.payment_inr == D("400")  # the long now receives
    assert ledger.balance_inr == D("1_000_000") + D("400")


# ---------------------------------------------------------------------------
# 8h boundary settlement
# ---------------------------------------------------------------------------

def test_settlement_only_on_eight_hour_utc_boundaries() -> None:
    ledger = make_ledger()
    ledger.open_position(open_order(PerpSide.LONG, D("1"), D("50000"), D("20")), D("0"))
    ledger.mark_to_market(D("50000"))
    # 07:59 UTC is not a settlement boundary.
    with pytest.raises(ValueError, match="8h UTC boundary"):
        ledger.settle_funding(D("0.0001"), datetime(2024, 3, 1, 7, 59, tzinfo=UTC))
    # A boundary with a stray minute component is rejected.
    with pytest.raises(ValueError, match="8h UTC boundary"):
        ledger.settle_funding(D("0.0001"), datetime(2024, 3, 1, 8, 0, 30, tzinfo=UTC))
    # IST 13:30 == 08:00 UTC: a non-UTC clock normalises onto the UTC grid.
    ist = datetime(2024, 3, 1, 13, 30, tzinfo=IST)
    event = ledger.settle_funding(D("0.0001"), ist)
    assert event is not None and event.boundary_utc.hour == 8


def test_two_funding_payments_in_a_twenty_four_hour_hold() -> None:
    # 24h hold: open AT the 08:00 boundary, close AT the next-day 08:00
    # boundary before its settlement. Exactly two payments (16:00 and 00:00)
    # fall inside the hold; the open and close boundaries themselves charge
    # nothing. The half-open (prev < b <= cur) window still enumerates all
    # three boundaries; the final one is a no-op because the position is flat.
    ledger = make_ledger()
    order = replace(
        open_order(PerpSide.LONG, D("1"), D("50000"), D("20")),
        timestamp=datetime(2024, 3, 1, 8, 0, tzinfo=UTC),
    )
    ledger.open_position(order, D("0"))
    start = datetime(2024, 3, 1, 8, 0, tzinfo=UTC)
    end = datetime(2024, 3, 2, 8, 0, tzinfo=UTC)
    boundaries = ledger.funding_boundaries_between(start, end)
    assert boundaries == (
        datetime(2024, 3, 1, 16, 0, tzinfo=UTC),
        datetime(2024, 3, 2, 0, 0, tzinfo=UTC),
        datetime(2024, 3, 2, 8, 0, tzinfo=UTC),
    )
    ledger.mark_to_market(D("50000"))
    paid = ledger.settle_funding(D("0.0001"), datetime(2024, 3, 1, 16, 0, tzinfo=UTC))
    assert paid is not None and paid.payment_inr == D("-400")
    paid = ledger.settle_funding(D("0.0001"), datetime(2024, 3, 2, 0, 0, tzinfo=UTC))
    assert paid is not None and paid.payment_inr == D("-400")
    assert ledger.balance_inr == D("1_000_000") - D("400") * 2
    assert ledger.funding_paid_inr == D("400") * 2
    # Close exactly at the final 08:00 boundary, then settle it: the position
    # is already flat, so the closing boundary is a no-op (returns None).
    ledger.close_position(close_order(order, D("50000")), D("0"))
    closing = ledger.settle_funding(D("0.0001"), datetime(2024, 3, 2, 8, 0, tzinfo=UTC))
    assert closing is None
    snap = ledger.snapshot()
    assert snap.funding_event_count == 2


def test_no_retroactive_funding_for_boundary_before_open() -> None:
    # Venue rule: only positions held at the funding instant pay. A position
    # opened at 20:00 must not be charged for the 16:00 boundary that already
    # passed, even if the caller replays it; the skipped boundary is consumed
    # for monotonicity and the next one pays normally.
    ledger = make_ledger()
    order = replace(
        open_order(PerpSide.LONG, D("1"), D("50000"), D("20")),
        timestamp=datetime(2024, 3, 1, 20, 0, tzinfo=UTC),
    )
    ledger.open_position(order, D("0"))
    ledger.mark_to_market(D("50000"))
    skipped = ledger.settle_funding(D("0.0001"), datetime(2024, 3, 1, 16, 0, tzinfo=UTC))
    assert skipped is None
    assert ledger.funding_events == []
    assert ledger.balance_inr == D("1_000_000")
    # The skipped boundary is consumed: replaying it or going back is refused.
    with pytest.raises(ValueError, match="strictly after"):
        ledger.settle_funding(D("0.0001"), datetime(2024, 3, 1, 16, 0, tzinfo=UTC))
    # The next boundary after the open pays in full.
    paid = ledger.settle_funding(D("0.0001"), datetime(2024, 3, 2, 0, 0, tzinfo=UTC))
    assert paid is not None and paid.payment_inr == D("-400")
    assert ledger.funding_paid_inr == D("400")


def test_funding_boundary_monotonic_no_double_settlement() -> None:
    ledger = make_ledger()
    ledger.open_position(open_order(PerpSide.LONG, D("1"), D("50000"), D("20")), D("0"))
    ledger.mark_to_market(D("50000"))
    b = datetime(2024, 3, 10, 16, 0, tzinfo=UTC)
    assert ledger.settle_funding(D("0.0001"), b) is not None
    # Same boundary again must fail, not silently pay twice.
    with pytest.raises(ValueError, match="strictly after"):
        ledger.settle_funding(D("0.0001"), b)
    # An earlier boundary is also refused.
    with pytest.raises(ValueError, match="strictly after"):
        ledger.settle_funding(D("0.0001"), b - timedelta(hours=8))


def test_funding_without_position_is_noop_and_entry_mark_prices_first_settlement() -> None:
    ledger = make_ledger()
    # No open position: settlement is a no-op returning None.
    assert (
        ledger.settle_funding(D("0.0001"), datetime(2024, 3, 1, 8, 0, tzinfo=UTC)) is None
    )
    # open_position stamps the entry price as the first mark, so funding can
    # settle immediately without a separate mark_to_market call.
    fresh = make_ledger()
    fresh.open_position(open_order(PerpSide.LONG, D("1"), D("50000"), D("20")), D("0"))
    event = fresh.settle_funding(D("0.0001"), datetime(2024, 3, 1, 8, 0, tzinfo=UTC))
    assert event is not None
    assert event.payment_inr == D("-400")


# ---------------------------------------------------------------------------
# margin math
# ---------------------------------------------------------------------------

def test_initial_margin_deducted_and_released_on_close() -> None:
    ledger = make_ledger()
    # 1 BTC notional at 50k USD = 50k USD = 4_000_000 INR; leverage 10x.
    order = open_order(PerpSide.LONG, D("1"), D("50000"), D("10"))
    fill = ledger.open_position(order, D("80"))  # fee = 1 USD
    expected_margin = D("4_000_000") / D("10")
    assert fill.margin_posted_inr == expected_margin
    snap = ledger.snapshot()
    assert snap.used_margin_inr == expected_margin
    assert snap.available_margin_inr == D("1_000_000") - D("80") - expected_margin
    assert snap.balance_inr == D("1_000_000") - D("80")
    # Unchanged mark: equity is the wallet balance (margin included), no PnL.
    assert snap.equity_inr == D("1_000_000") - D("80")
    assert snap.maintenance_requirement_inr == D("4_000_000") * D("0.005")
    # Close at the same price: margin fully released, no PnL, only fees lost.
    closing = close_order(order, D("50000"), "o2")
    close_fill = ledger.close_position(closing, D("80"))
    assert close_fill.margin_released_inr == expected_margin
    snap2 = ledger.snapshot()
    assert snap2.used_margin_inr == D("0")
    assert snap2.balance_inr == D("1_000_000") - D("80") - D("80")
    assert snap2.realized_pnl_inr == D("0")
    assert snap2.position_side is None


def test_leverage_cap_enforced() -> None:
    ledger = PerpetualLedger(make_config(max_leverage=D("5")), D("1_000_000"))
    with pytest.raises(ValueError, match="exceeds the instrument cap"):
        ledger.open_position(open_order(PerpSide.LONG, D("1"), D("50000"), D("10")), D("0"))


# ---------------------------------------------------------------------------
# realized PnL on close
# ---------------------------------------------------------------------------

def test_realized_pnl_long_close_is_decimal_exact() -> None:
    ledger = make_ledger()
    order = open_order(PerpSide.LONG, D("1"), D("50000"), D("20"))
    ledger.open_position(order, D("0"))
    ledger.close_position(close_order(order, D("55000")), D("0"))
    # (55000 - 50000) * 1 * 80 = 400_000 INR, exact.
    assert ledger.realized_pnl_inr == D("400_000")
    assert ledger.balance_inr == D("1_400_000")
    snap = ledger.snapshot()
    assert snap.equity_inr == D("1_400_000")


def test_realized_pnl_short_close_is_decimal_exact() -> None:
    ledger = make_ledger()
    order = open_order(PerpSide.SHORT, D("0.5"), D("50000"), D("2"))
    ledger.open_position(order, D("0"))
    ledger.close_position(close_order(order, D("49000")), D("0"))
    # (50000 - 49000) * 0.5 * 80 = 40_000 INR.
    assert ledger.realized_pnl_inr == D("40_000")


def test_negative_realized_pnl_and_fractional_quantity_exact() -> None:
    ledger = make_ledger()
    order = open_order(PerpSide.LONG, D("0.25"), D("50000"), D("2"))
    ledger.open_position(order, D("0"))
    ledger.close_position(close_order(order, D("48000")), D("0"))
    # (48000 - 50000) * 0.25 * 80 = -40_000 INR.
    assert ledger.realized_pnl_inr == D("-40_000")
    assert ledger.balance_inr == D("960_000")


# ---------------------------------------------------------------------------
# liquidation boundary
# ---------------------------------------------------------------------------

def test_liquidation_boundary_above_and_below_maintenance() -> None:
    # The maintenance requirement floats with the current mark (notional at
    # the current price times the fraction), so the exact boundary solves
    # equity(m) == maintenance(m): with wallet W=816_000, entry 50_000 USD,
    # 1 BTC and FX=80 that is m = 40_000 USD.
    #   equity(40000)      = 816_000 - 800_000 = 16_000
    #   maintenance(40000) = 40_000 * 80 * 0.005 = 16_000
    # One tick is 0.0125 USD (= 1/80, exact): equity moves 1 INR per tick,
    # maintenance only 0.005 * 80 * 0.0125 = 0.005 INR per tick.
    config = make_config()
    wallet = D("816_000")

    # Just above the boundary: equity 16_001 > maintenance 16_000.005.
    above = PerpetualLedger(config, wallet)
    above.open_position(open_order(PerpSide.LONG, D("1"), D("50000"), D("10")), D("0"))
    assert above.check_liquidation(D("40000.0125")) is None
    assert above.position is not None

    # Exactly at the boundary: the inclusive <= rule liquidates.
    at = PerpetualLedger(config, wallet)
    at.open_position(open_order(PerpSide.LONG, D("1"), D("50000"), D("10")), D("0"))
    assert at.equity(D("40000")) == D("16_000")
    assert at.maintenance_requirement_inr(D("40000")) == D("16_000")
    event = at.check_liquidation(D("40000"))
    assert event is not None
    assert event.boundary_equity_inr == D("16_000")
    assert event.maintenance_requirement_inr == D("16_000")
    assert at.position is None
    assert at.balance_inr == D("16_000")
    assert at.realized_pnl_inr == D("-800_000")

    # Just below the boundary: equity 15_999 < maintenance 15_999.995.
    below = PerpetualLedger(config, wallet)
    below.open_position(open_order(PerpSide.LONG, D("1"), D("50000"), D("10")), D("0"))
    event_below = below.check_liquidation(D("39999.9875"))
    assert event_below is not None
    assert event_below.boundary_equity_inr == D("15_999")


def test_liquidation_realizes_loss_and_clears_margin() -> None:
    ledger = make_ledger()
    ledger.open_position(open_order(PerpSide.LONG, D("1"), D("50000"), D("10")), D("0"))
    # Exact wipe-out: equity 0 at mark 50000 - 1000000/80 = 37500.
    event = ledger.check_liquidation(D("37500"))
    assert event is not None
    assert event.boundary_equity_inr == D("0")
    assert ledger.position is None
    assert ledger.used_margin_inr == D("0")
    assert ledger.balance_inr == D("0")
    assert ledger.realized_pnl_inr == D("-1_000_000")
    # Wallet exactly drained; equity with no open position equals the balance.
    assert ledger.snapshot().equity_inr == D("0")


def test_liquidation_can_drive_wallet_negative_and_keeps_exact_loss() -> None:
    ledger = make_ledger()
    ledger.open_position(open_order(PerpSide.LONG, D("1"), D("50000"), D("20")), D("0"))
    # Gap through zero: equity -50_000 INR at the liquidation mark.
    mark = D("50000") - D("1_050_000") / FX  # 36875
    event = ledger.check_liquidation(mark)
    assert event is not None
    assert event.boundary_equity_inr == D("-50_000")
    assert ledger.balance_inr == D("-50_000")
    assert ledger.realized_pnl_inr == D("-1_050_000")
    assert ledger.used_margin_inr == D("0")


# ---------------------------------------------------------------------------
# cross-market isolation and ledger validation
# ---------------------------------------------------------------------------

def test_nse_currency_derivatives_ledger_raises_at_construction() -> None:
    with pytest.raises(ValueError, match="Market.CRYPTO only"):
        PerpetualLedgerConfig(
            market=Market.NSE,
            instrument="RELIANCE-PERP",
            fx_rate_inr_per_usd=FX,
            maintenance_margin_fraction=D("0.005"),
        )


def test_cross_market_order_rejected_before_mutation() -> None:
    ledger = make_ledger()
    foreign = DerivativesOrder(
        order_id="nse-o1",
        market=Market.NSE,
        instrument="BTCUSDT-PERP",
        side=PerpSide.LONG,
        quantity=D("1"),
        price_usd=D("50000"),
        leverage=D("2"),
        timestamp=datetime(2024, 3, 1, tzinfo=UTC),
    )
    with pytest.raises(ValueError, match="cross-market order rejected"):
        ledger.open_position(foreign, D("0"))
    # Nothing was mutated by the rejected order.
    snap = ledger.snapshot()
    assert snap.balance_inr == D("1_000_000")
    assert snap.used_margin_inr == D("0")
    assert snap.order_count == 0


def test_wrong_instrument_and_naive_timestamp_rejected() -> None:
    ledger = make_ledger()
    with pytest.raises(ValueError, match="timezone-aware"):
        DerivativesOrder(
            order_id="t2",
            market=Market.CRYPTO,
            instrument="BTCUSDT-PERP",
            side=PerpSide.LONG,
            quantity=D("1"),
            price_usd=D("50000"),
            leverage=D("2"),
            timestamp=datetime(2024, 3, 1, 0, 0),  # naive
        )
    wrong_instrument = DerivativesOrder(
        order_id="t3",
        market=Market.CRYPTO,
        instrument="ETHUSDT-PERP",
        side=PerpSide.LONG,
        quantity=D("1"),
        price_usd=D("3000"),
        leverage=D("2"),
        timestamp=datetime(2024, 3, 1, tzinfo=UTC),
    )
    with pytest.raises(ValueError, match="instrument must match"):
        ledger.open_position(wrong_instrument, D("0"))


def test_duplicate_order_id_rejected() -> None:
    ledger = make_ledger()
    first = open_order(PerpSide.LONG, D("0.1"), D("50000"), D("2"), order_id="dup")
    ledger.open_position(first, D("0"))
    ledger.close_position(close_order(first, D("50000")), D("0"))
    # Re-using the order id is rejected even after the position is flat again.
    replay = open_order(PerpSide.LONG, D("0.1"), D("50000"), D("2"), order_id="dup")
    with pytest.raises(ValueError, match="duplicate order id"):
        ledger.open_position(replay, D("0"))


def test_overposition_rejected() -> None:
    ledger = make_ledger()
    ledger.open_position(open_order(PerpSide.LONG, D("1"), D("50000"), D("20")), D("0"))
    # A second position while one is open is rejected (one position per instrument).
    with pytest.raises(ValueError, match="position already open"):
        ledger.open_position(
            open_order(PerpSide.SHORT, D("1"), D("50000"), D("2"), order_id="second"),
            D("0"),
        )
    # A close order whose quantity differs from the open position is rejected
    # (no partial-close API), so quantity drift cannot create phantom exposure.
    mismatched = replace(close_order(ledger.fills[0].order, D("55000")), quantity=D("2"))
    with pytest.raises(ValueError, match="quantity must equal the open position"):
        ledger.close_position(mismatched, D("0"))
    # The position remains intact after both rejections.
    assert ledger.position is not None and ledger.position.quantity == D("1")
    snap = ledger.snapshot(D("50000"))
    assert snap.order_count == 1


def test_insufficient_margin_rejected_with_fee() -> None:
    ledger = PerpetualLedger(make_config(), D("10_000"))
    # Notional 4_000_000 INR at 2x needs 2_000_000 INR margin: impossible.
    with pytest.raises(ValueError, match="insufficient margin"):
        ledger.open_position(open_order(PerpSide.LONG, D("1"), D("50000"), D("2")), D("0"))
    # A huge-fee order is refused even when the margin itself fits:
    # 0.001 BTC at 20x posts 200 INR, but the 99_999 INR fee does not fit.
    tiny = PerpetualLedger(make_config(), D("100_000"))
    with pytest.raises(ValueError, match="insufficient margin"):
        tiny.open_position(
            open_order(PerpSide.LONG, D("0.001"), D("50000"), D("20")), D("99_999")
        )
    snap = ledger.snapshot()
    assert snap.balance_inr == D("10_000")
    assert snap.order_count == 0


def test_snapshot_entry_mark_and_explicit_remark() -> None:
    ledger = make_ledger()
    ledger.open_position(open_order(PerpSide.LONG, D("1"), D("50000"), D("20")), D("0"))
    # The entry price is the initial mark: no explicit mark call is required.
    snap = ledger.snapshot()
    assert snap.mark_price_usd == D("50000")
    assert snap.unrealized_pnl_inr == D("0")
    assert snap.equity_inr == D("1_000_000")
    # An explicit mark revalues the position: (60000 - 50000) * 1 * 80.
    snap2 = ledger.snapshot(D("60000"))
    assert snap2.unrealized_pnl_inr == D("800_000")
    assert snap2.equity_inr == D("1_800_000")
    # The new mark persists for the next funding settlement.
    assert ledger.mark_price_usd == D("60000")


def test_mismatched_fx_provenance_rejected() -> None:
    with pytest.raises(ValueError, match="fx_provenance"):
        PerpetualLedger(make_config(), D("1_000_000"), fx_provenance="   ")
