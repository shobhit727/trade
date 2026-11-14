"""Tests for date-effective fee schedules (F-012) and FIFO tax lots with
corporate actions (F-013), including the CR-013 accounting invariant loop.

Money assertions are paise-exact Decimal comparisons. Every historical rate
window used here is verified in ``research/platform/costs.py`` module docs.
"""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from research.platform.costs import (
    DatedFeeScheduleError,
    FeeComponentSchedule,
    NSE_STATUTORY_DELIVERY_SCHEDULE,
    NSEDeliveryFeeCalculator,
    SCHEDULE_FLOOR_DATE,
    SCHEDULE_VERSION,
)
from research.platform.domain import Market
from research.platform.lots import (
    KIND_LTCG,
    KIND_STCG,
    CorporateAction,
    TaxLotLedger,
    apply_corporate_action,
)
from research.platform.market import Fill, MarketLedger, Side


UTC = timezone.utc
D = Decimal

BOUNDARY_PRE = date(2024, 9, 28)   # last Saturday inside the slab-era window
BOUNDARY_POST = date(2024, 10, 1)  # first day of the NSE/FA/64232 flat era
LAKH = D(100000)


def _dated(symbol_days: int, side: Side, quantity: D, price: D) -> Fill:
    """Build a whole-share NSE fill dated N days after the schedule floor."""
    return Fill(
        fill_id=f"lot-{side.value}-{quantity}-{price}-{symbol_days}",
        market=Market.NSE,
        instrument="LOT",
        side=side,
        quantity=quantity,
        price_inr=price,
        fee_inr=D("0"),
        timestamp=datetime(2013, 6, 1, tzinfo=UTC) + timedelta(days=symbol_days),
        cost_model_id="dated-lot-test",
        fx_provenance="synthetic-test-fixture",
    )


# --------------------------------------------------------------------------- #
# F-012: dated STT resolution across verified boundaries
# --------------------------------------------------------------------------- #


class TestDateEffectiveSchedules:
    """Paise-exact resolutions at each verified schedule boundary."""

    def test_stt_is_constant_across_october_2024_boundary_both_sides(self) -> None:
        # The 2024-10-01 circular (NSE/FATAX/63809) changed F&O STT only:
        # delivery equity is 0.1% both sides before AND after the boundary.
        calculator = NSEDeliveryFeeCalculator()
        for side in (Side.BUY, Side.SELL):
            pre = calculator.breakdown_asof(BOUNDARY_PRE, side, D(1), LAKH)
            post = calculator.breakdown_asof(BOUNDARY_POST, side, D(1), LAKH)
            assert pre.stt == D("100.00")
            assert post.stt == D("100.00")

    def test_exchange_txn_boundary_paise_exact(self) -> None:
        # Rs 1,00,000 per side at the 2024-10-01 boundary (verified table).
        calculator = NSEDeliveryFeeCalculator()
        buy_pre = calculator.breakdown_asof(BOUNDARY_PRE, Side.BUY, D(1), LAKH)
        buy_post = calculator.breakdown_asof(BOUNDARY_POST, Side.BUY, D(1), LAKH)
        sell_pre = calculator.breakdown_asof(BOUNDARY_PRE, Side.SELL, D(1), LAKH)
        sell_post = calculator.breakdown_asof(BOUNDARY_POST, Side.SELL, D(1), LAKH)

        assert buy_pre.exchange_txn == D("3.25")
        assert buy_post.exchange_txn == D("3.07")
        assert sell_pre.exchange_txn == D("3.25")
        assert sell_post.exchange_txn == D("3.07")

        assert buy_pre.total == D("119.01")   # stt 100 + txn 3.25 + sebi 0.15 + stamp 15 + gst 0.61
        assert buy_post.total == D("118.80")  # stt 100 + txn 3.07 + sebi 0.15 + stamp 15 + gst 0.58
        assert sell_pre.total == D("119.94")  # + dp 15.93, no stamp
        assert sell_post.total == D("119.73")

    def test_sebi_turnover_fee_windows(self) -> None:
        # Verified series: Rs10/cr -> Rs20/cr (2014-05-23) -> Rs15/cr (2017-04-01).
        calculator = NSEDeliveryFeeCalculator()
        buy = lambda when: calculator.breakdown_asof(when, Side.BUY, D(1), LAKH)
        assert buy(date(2013, 6, 1)).sebi == D("0.10")
        assert buy(date(2014, 5, 22)).sebi == D("0.10")
        assert buy(date(2014, 5, 23)).sebi == D("0.20")
        assert buy(date(2017, 3, 31)).sebi == D("0.20")
        assert buy(date(2017, 4, 1)).sebi == D("0.15")
        assert buy(date(2026, 1, 1)).sebi == D("0.15")

    def test_stamp_duty_boundary_is_both_sides_then_buy_only(self) -> None:
        # Pre-unification (state regime): 0.01% BOTH sides; from 2020-07-01:
        # uniform 0.015% buy-side only.
        calculator = NSEDeliveryFeeCalculator()
        pre_sell = calculator.breakdown_asof(date(2020, 6, 29), Side.SELL, D(1), LAKH)
        post_sell = calculator.breakdown_asof(date(2020, 7, 1), Side.SELL, D(1), LAKH)
        pre_buy = calculator.breakdown_asof(date(2020, 6, 29), Side.BUY, D(1), LAKH)
        post_buy = calculator.breakdown_asof(date(2020, 7, 1), Side.BUY, D(1), LAKH)
        assert pre_sell.stamp_duty == D("10.00")
        assert post_sell.stamp_duty == D("0.00")
        assert pre_buy.stamp_duty == D("10.00")
        assert post_buy.stamp_duty == D("15.00")
        # Verified paise totals across the stamp boundary (txn-era 0.00325%).
        assert pre_sell.total == D("129.94")
        assert post_sell.total == D("119.94")

    def test_gst_era_switch_2017(self) -> None:
        # Service-tax era modelled at the 15% ceiling; 18% GST from 2017-07-01.
        calculator = NSEDeliveryFeeCalculator()
        pre = calculator.breakdown_asof(date(2017, 6, 30), Side.BUY, D(1), LAKH)
        post = calculator.breakdown_asof(date(2017, 7, 1), Side.BUY, D(1), LAKH)
        # (txn 3.25 + sebi 0.15) * 0.15 = 0.51; (3.25 + 0.15) * 0.18 = 0.612 -> 0.61
        assert pre.gst == D("0.51")
        assert post.gst == D("0.61")

    def test_era_paise_table_across_history(self) -> None:
        # Verified paise totals for buys across every statutory era.
        calculator = NSEDeliveryFeeCalculator()
        cases = {
            date(2016, 5, 15): D("113.97"),  # sebi 0.20, gst 0.52, stamp 10
            date(2019, 1, 15): D("114.01"),  # sebi 0.15, gst 0.61, stamp 10
            date(2020, 7, 1): D("119.01"),   # stamp 15, gst 0.61, txn-era 3.25
            date(2024, 9, 28): D("119.01"),
            date(2024, 10, 1): D("118.80"),
            date(2026, 11, 1): D("118.80"),
        }
        for when, expected in cases.items():
            assert calculator.breakdown_asof(when, Side.BUY, D(1), LAKH).total == expected

    def test_unknown_date_is_an_explicit_error_not_a_silent_default(self) -> None:
        # Dates before the verified floor (2013-06-01) must fail loudly.
        calculator = NSEDeliveryFeeCalculator()
        with pytest.raises(DatedFeeScheduleError, match="2012-11-15"):
            calculator.fee_asof(date(2012, 11, 15), Side.BUY, D(1), LAKH)
        with pytest.raises(DatedFeeScheduleError, match="no verified fee rate"):
            calculator.breakdown_asof(date(2000, 1, 1), Side.SELL, D(1), LAKH)

    def test_current_era_matches_nsealgo_component_by_component(self) -> None:
        # Current era vs the repository's ground-truth model over a grid:
        # statutory components exactly equal; SEBI/GST strictly >= (verified
        # Rs15/cr SEBI vs the stale nsealgo Rs10/cr constant). GOAL.md 6.4:
        # never reduce costs.
        from nsealgo.costs import CostModel

        calculator = NSEDeliveryFeeCalculator()
        ground_truth = CostModel(segment="delivery", slippage_bps=D("0"))
        current = date(2026, 11, 1)
        for quantity in (D(1), D(37), D(625)):
            for price in (D("123.45"), D(1000), D(150000)):
                for side in (Side.BUY, Side.SELL):
                    dated = calculator.breakdown_asof(current, side, quantity, price)
                    model = ground_truth.cost(side.value.upper(), quantity, price)
                    assert dated.stt == model.stt
                    assert dated.exchange_txn == model.exchange_txn
                    assert dated.stamp_duty == model.stamp_duty
                    assert dated.dp_charges == model.dp_charges
                    assert dated.brokerage == model.brokerage
                    assert dated.sebi >= model.sebi
                    assert dated.gst >= model.gst
        # Round trip at Rs 1L/side strictly above the nsealgo 11.92 bps floor.
        buy = calculator.breakdown_asof(current, Side.BUY, D(1), LAKH)
        sell = calculator.breakdown_asof(current, Side.SELL, D(1), LAKH)
        bps = ((buy.total + sell.total) / (LAKH * 2) * D(10000)).quantize(D("0.01"))
        assert bps == D("11.93")  # (118.80 + 119.73) / 2L * 10^4 = 11.9265
        assert bps > D("11.92")   # strictly above the nsealgo 11.92 bps floor

    def test_undated_fee_api_unchanged_for_existing_callers(self) -> None:
        # fee() keeps the calibrated behaviour and pinned model id.
        calculator = NSEDeliveryFeeCalculator()
        assert calculator.model_id == "nse-delivery-cost-model"
        assert calculator.schedule_version == SCHEDULE_VERSION == "nse-delivery-dated-v1"
        assert calculator.fee(Side.BUY, D(1), LAKH) == D("118.74")

    def test_fee_asof_rejects_injected_custom_model(self) -> None:
        from nsealgo.costs import CostModel

        calculator = NSEDeliveryFeeCalculator(
            model=CostModel(segment="delivery", slippage_bps=D("0"))
        )
        with pytest.raises(ValueError, match="built-in statutory schedule"):
            calculator.fee_asof(BOUNDARY_POST, Side.BUY, D(1), LAKH)

    def test_schedule_validation_rejects_gaps_and_open_penultimate(self) -> None:
        window = lambda start, end=None: __import__(
            "research.platform.costs", fromlist=["DatedRateWindow"]
        ).DatedRateWindow(rate=D("0.001"), start_date=start, end_date=end)
        with pytest.raises(ValueError, match="contiguous"):
            FeeComponentSchedule(
                name="test",
                windows=(window(SCHEDULE_FLOOR_DATE, date(2015, 1, 1)), window(date(2015, 3, 1))),
            )
        with pytest.raises(ValueError, match="open-ended"):
            FeeComponentSchedule(
                name="test",
                windows=(window(SCHEDULE_FLOOR_DATE), window(date(2015, 1, 1))),
            )
        with pytest.raises(ValueError, match="final window must be open-ended"):
            FeeComponentSchedule(
                name="test",
                windows=(window(SCHEDULE_FLOOR_DATE, date(2015, 1, 1)),),
            )


# --------------------------------------------------------------------------- #
# F-012: the portfolio simulator resolves fees per fill date
# --------------------------------------------------------------------------- #


def test_portfolio_fills_resolve_fees_asof_fill_date() -> None:
    """A two-era simulation bills each fill under its own statutory schedule."""
    import pandas as pd

    from research.platform.portfolio import PortfolioConfig, PortfolioSimulator

    dates = pd.date_range("2024-09-27", periods=7, freq="D", tz="UTC")
    bars = {
        "ERA": pd.DataFrame(
            {
                "open": [100.0] * 7,
                "high": [101.0] * 7,
                "low": [99.0] * 7,
                "close": [100.0] * 7,
                "volume": [1_000_000.0] * 7,
            },
            index=dates,
        )
    }
    # Decision on 09-28 close (0.5) buys on 09-29 (slab era); decision on
    # 10-01 close (0.0) sells on 10-02 (flat era).
    targets = pd.DataFrame(
        {"ERA": [0.0, 0.5, 0.5, 0.5, 0.5, 0.0, 0.0]}, index=dates
    )
    result = PortfolioSimulator(
        PortfolioConfig(
            market=Market.NSE,
            fee_bps=D("0"),
            slippage_bps=D("0"),
            impact_coefficient_bps=D("0"),
            max_participation=D("1"),
            max_gross_exposure=D("1"),
            assumed_timezone="UTC",
            cost_model_id="nse-delivery-cost-model",
            fee_calculator=NSEDeliveryFeeCalculator(),
        )
    ).run(bars, targets)

    # The large rebalance buy lands in the slab era; the final flatten sell
    # lands in the flat era (small intra-era rebalances may also appear).
    buy_fill = max(
        (item for item in result.fills if item.fill.side is Side.BUY),
        key=lambda item: item.fill.quantity,
    )
    sell_fill = max(
        (item for item in result.fills if item.fill.side is Side.SELL),
        key=lambda item: item.fill.quantity,
    )
    buy_date = buy_fill.fill.timestamp.date()
    sell_date = sell_fill.fill.timestamp.date()
    assert buy_date == date(2024, 9, 29)   # slab-era window (<= 2024-09-30)
    assert sell_date == date(2024, 10, 3)  # flat-era window (>= 2024-10-01)
    assert buy_date < date(2024, 10, 1) < sell_date

    # Each fill's fee equals the dated schedule total for its own quantity.
    buy_total = NSE_STATUTORY_DELIVERY_SCHEDULE.breakdown(
        buy_date, Side.BUY, buy_fill.fill.quantity, buy_fill.fill.price_inr
    ).total
    sell_total = NSE_STATUTORY_DELIVERY_SCHEDULE.breakdown(
        sell_date, Side.SELL, sell_fill.fill.quantity, sell_fill.fill.price_inr
    ).total
    assert buy_fill.fill.fee_inr == buy_total
    assert sell_fill.fill.fee_inr == sell_total
    assert result.fee_schedule_version == "nse-delivery-dated-v1"


# --------------------------------------------------------------------------- #
# F-013: FIFO tax lots and corporate actions
# --------------------------------------------------------------------------- #


def _fresh_ledger() -> MarketLedger:
    return MarketLedger(Market.NSE)


class TestFifoRealization:
    """FIFO lot matching and STCG/LTCG classification."""

    def test_fifo_mixed_lot_sell(self) -> None:
        # Buy 100@10, buy 100@20, sell 150 -> 100@10 then 50@20.
        ledger = _fresh_ledger()
        ledger.apply_fill(_dated(0, Side.BUY, D(100), D(10)))
        ledger.apply_fill(_dated(1, Side.BUY, D(100), D(20)))
        ledger.apply_fill(_dated(2, Side.SELL, D(150), D(25)))
        ledger.apply_fill(
            _dated(3, Side.SELL, D(0), D(25))
        ) if False else None  # keep the 50-lot open
        lots = TaxLotLedger()
        # Reconstruct the same queue to exercise realize() directly:
        lots.open_lot("LOT", D(100), D(10), date(2013, 6, 1))
        lots.open_lot("LOT", D(100), D(20), date(2013, 6, 2))
        records = lots.realize_fifo("LOT", D(150), D(25), date(2013, 6, 3))
        assert [(r.quantity, r.cost_price_inr) for r in records] == [
            (D(100), D(10)),
            (D(50), D(20)),
        ]
        assert sum(r.quantity for r in records) == D(150)
        assert lots.total_quantity("LOT") == D(50)
        assert lots.lots("LOT")[0].price_inr == D(20)

    def test_fifo_oversell_rejected(self) -> None:
        lots = TaxLotLedger()
        lots.open_lot("LOT", D(10), D(100), date(2013, 6, 1))
        with pytest.raises(ValueError, match="cannot realize"):
            lots.realize_fifo("LOT", D(11), D(120), date(2013, 6, 2))
        with pytest.raises(ValueError, match="cannot realize"):
            lots.realize_fifo("MISSING", D(1), D(120), date(2013, 6, 2))

    def test_short_term_and_long_term_split(self) -> None:
        # Sell after 400 days: the lot is long-term (> 365 days).
        lots = TaxLotLedger()
        lots.open_lot("LOT", D(100), D(10), date(2013, 6, 1))
        records = lots.realize_fifo("LOT", D(100), D(20), date(2014, 7, 6))
        assert [r.kind for r in records] == [KIND_LTCG]
        assert records[0].holding_days == 400
        assert records[0].gain_inr == D(1000)

        # 365 days exactly is short-term; 366 is long-term.
        lots.open_lot("LOT", D(10), D(10), date(2013, 6, 1))
        st = lots.realize_fifo("LOT", D(5), D(10), date(2014, 6, 1))
        assert [r.kind for r in st] == [KIND_STCG]  # 365 days -> STCG
        lots.open_lot("LOT", D(10), D(10), date(2013, 6, 1))
        lt = lots.realize_fifo("LOT", D(5), D(10), date(2014, 6, 2))
        assert [r.kind for r in lt] == [KIND_LTCG]  # 366 days -> LTCG

    def test_mixed_holding_periods_in_one_sell(self) -> None:
        # One sell can span a long-term and a short-term lot.
        lots = TaxLotLedger()
        lots.open_lot("OLD", D(50), D(100), date(2013, 6, 1))   # > 365d by sell
        lots.open_lot("OLD", D(50), D(110), date(2015, 6, 1))   # < 365d by sell
        records = lots.realize_fifo("OLD", D(100), D(150), date(2016, 1, 1))
        assert [r.kind for r in records] == [KIND_LTCG, KIND_STCG]
        assert records[0].holding_days == 944
        assert records[1].holding_days == 214


class TestCorporateActions:
    """Explicit-event corporate actions; cash is never touched."""

    def test_split_doubles_quantity_and_halves_basis_cash_unchanged(self) -> None:
        # Split 1:2 on 100 shares @ Rs 50 -> 200 shares @ Rs 25, cash unchanged.
        ledger = _fresh_ledger()
        ledger.apply_fill(_dated(0, Side.BUY, D(100), D(50)))
        cash_before = ledger.cash_inr
        lots = TaxLotLedger()
        lots.open_lot("LOT", D(100), D(50), date(2013, 6, 1))
        ex = date(2013, 6, 10)
        apply_corporate_action(ledger, lots, CorporateAction("split", "LOT", ex, D(2)))

        assert lots.total_quantity("LOT") == D(200)
        assert lots.total_cost_basis_inr("LOT") == D(5000)
        lot = lots.lots("LOT")[0]
        assert (lot.quantity, lot.price_inr, lot.acquired_on) == (D(200), D("25"), date(2013, 6, 1))
        assert ledger.cash_inr == cash_before
        assert ledger.positions["LOT"].quantity == D(200)
        # Fee-inclusive average entry divides by the ratio: basis is conserved.
        assert ledger.positions["LOT"].average_entry_inr == D("25")

        # FIFO still realizes the enlarged lots at the adjusted basis.
        records = lots.realize_fifo("LOT", D(200), D(30), date(2013, 6, 20))
        assert records[0].cost_price_inr == D("25")
        assert records[0].gain_inr == D(1000)

    def test_bonus_appends_zero_cost_lots_cash_unchanged(self) -> None:
        # Bonus 1:1 on 100 shares @ Rs 50 -> +100 zero-cost lots, cash unchanged.
        ledger = _fresh_ledger()
        ledger.apply_fill(_dated(0, Side.BUY, D(100), D(50)))
        cash_before = ledger.cash_inr
        lots = TaxLotLedger()
        lots.open_lot("LOT", D(100), D(50), date(2013, 6, 1))
        ex = date(2013, 6, 10)
        apply_corporate_action(ledger, lots, CorporateAction("bonus", "LOT", ex, D(1)))

        assert lots.total_quantity("LOT") == D(200)
        assert lots.total_cost_basis_inr("LOT") == D(5000)
        original, bonus = lots.lots("LOT")
        assert (bonus.quantity, bonus.price_inr, bonus.acquired_on) == (D(100), D(0), ex)
        assert ledger.cash_inr == cash_before
        assert ledger.positions["LOT"].quantity == D(200)

        # Selling 150 realizes 100@50 then 100 bonus@0 FIFO, full gain on bonus lot.
        records = lots.realize_fifo("LOT", D(150), D(60), date(2013, 6, 15))
        assert [(r.quantity, r.cost_price_inr, r.kind) for r in records] == [
            (D(100), D(50), KIND_STCG),
            (D(50), D(0), KIND_STCG),
        ]
        assert sum(r.gain_inr for r in records) == D(1000 + 3000)

    def test_bonus_fractional_ratio_1_for_2(self) -> None:
        # Bonus 1:2: one free share per two held.
        ledger = _fresh_ledger()
        ledger.apply_fill(_dated(0, Side.BUY, D(100), D(50)))
        lots = TaxLotLedger()
        lots.open_lot("LOT", D(100), D(50), date(2013, 6, 1))
        apply_corporate_action(
            ledger, lots, CorporateAction("bonus", "LOT", date(2013, 6, 10), D("0.5"))
        )
        assert lots.total_quantity("LOT") == D(150)
        assert lots.total_cost_basis_inr("LOT") == D(5000)
        assert ledger.positions["LOT"].quantity == D(150)

    def test_corporate_actions_require_explicit_events_and_consistency(self) -> None:
        # No auto-detection: events come only from the caller's list, and a
        # ledger/lot-queue mismatch is refused before any mutation.
        lots = TaxLotLedger()
        lots.open_lot("LOT", D(100), D(50), date(2013, 6, 1))
        empty_ledger = _fresh_ledger()
        with pytest.raises(ValueError, match="disagree"):
            apply_corporate_action(
                empty_ledger, lots, CorporateAction("split", "LOT", date(2013, 6, 5), D(2))
            )
        assert lots.total_quantity("LOT") == D(100)  # untouched after refusal

        # An event for a symbol with no lots anywhere is refused too.
        ghost_lots = TaxLotLedger()
        with pytest.raises(ValueError, match="disagree|without an open position"):
            apply_corporate_action(
                empty_ledger, ghost_lots, CorporateAction("split", "GHOST", date(2013, 6, 5), D(2))
            )

    def test_consolidation_sub_unit_ratio(self) -> None:
        # Reverse split 1:2 (ratio 0.5) halves quantity and doubles basis.
        ledger = _fresh_ledger()
        ledger.apply_fill(_dated(0, Side.BUY, D(100), D(50)))
        lots = TaxLotLedger()
        lots.open_lot("LOT", D(100), D(50), date(2013, 6, 1))
        apply_corporate_action(
            ledger, lots, CorporateAction("split", "LOT", date(2013, 6, 10), D("0.5"))
        )
        assert lots.total_quantity("LOT") == D(50)
        assert lots.total_cost_basis_inr("LOT") == D(5000)
        assert ledger.positions["LOT"].quantity == D(50)
        assert ledger.positions["LOT"].average_entry_inr == D(100)


# --------------------------------------------------------------------------- #
# CR-013: accounting invariant loop (fixed seed, random event sequence)
# --------------------------------------------------------------------------- #


def test_cr013_invariant_loop_cash_and_positions_stay_correct() -> None:
    """Random event sequence, fixed seed: cash never negative, no duplicate
    fills, and sum(lot qty) == position qty after EVERY event."""
    rng = random.Random(20260701)
    ledger = _fresh_ledger()
    lots = TaxLotLedger()
    symbols = ("AAA", "BBB", "CCC")
    prices = {symbol: D(50 + 25 * index) for index, symbol in enumerate(symbols)}
    fee_counter = [0]
    event_log: list[str] = []
    days = [date(2013, 6, 1) + timedelta(days=step) for step in range(1200)]

    def _apply_fill(symbol: str, side: Side, quantity: D) -> None:
        fee_counter[0] += 1
        day = days[len(event_log) % len(days)]
        ledger.apply_fill(
            Fill(
                fill_id=f"cr013-{fee_counter[0]}",
                market=Market.NSE,
                instrument=symbol,
                side=side,
                quantity=quantity,
                price_inr=prices[symbol],
                fee_inr=D("0"),
                timestamp=datetime(day.year, day.month, day.day, tzinfo=UTC),
                cost_model_id="cr013-invariant",
                fx_provenance="synthetic-test-fixture",
            )
        )
        if side is Side.BUY:
            lots.open_lot(symbol, quantity, prices[symbol], day)
        else:
            lots.realize_fifo(symbol, quantity, prices[symbol], day)
        event_log.append(f"{day.isoformat()} {side.value} {quantity} {symbol}")

    for _ in range(600):
        symbol = rng.choice(symbols)
        held = ledger.positions.get(symbol)
        held_qty = held.quantity if held else D(0)
        action = rng.random()
        if held_qty == 0 or action < 0.55:
            quantity = D(rng.randint(1, 60))
            _apply_fill(symbol, Side.BUY, quantity)
        else:
            held_after = ledger.positions.get(symbol)
            available = int(held_after.quantity) if held_after else 0
            quantity = D(rng.randint(1, available)) if available >= 1 else D(0)
            if quantity > 0:
                _apply_fill(symbol, Side.SELL, quantity)

        # Corporate actions only on symbols with open positions NOW (the fill
        # may have fully closed the position), ~15% of steps.
        held_now = ledger.positions.get(symbol)
        if action >= 0.85 and held_now is not None and held_now.quantity > 0:
            ratio = rng.choice([D(2), D("0.5"), D(1), D("0.5")])
            kind = "split" if ratio != D(1) else "bonus"
            if kind == "bonus" and rng.random() < 0.5:
                ratio = D(1)
            ex_day = days[(len(event_log) * 7) % len(days)]
            event = CorporateAction(kind, symbol, ex_day, ratio)
            apply_corporate_action(ledger, lots, event)
            event_log.append(f"{ex_day.isoformat()} {kind} {ratio} {symbol}")

        # Invariants after EVERY event.
        assert ledger.cash_inr >= 0, f"negative cash at event {len(event_log)}"
        assert len(ledger._fill_ids) == fee_counter[0], "duplicate fill detected"
        for check_symbol in symbols:
            position = ledger.positions.get(check_symbol)
            position_qty = position.quantity if position else D(0)
            assert lots.total_quantity(check_symbol) == position_qty, (
                f"lot/position divergence for {check_symbol} after event {len(event_log)}"
            )
            def _had_non_cash_event(symbol: str) -> bool:
                for item in event_log:
                    parts = item.split()
                    if len(parts) == 4 and parts[3] == symbol and parts[1] in ("split", "bonus"):
                        return True
                return False

            if position_qty > 0 and not _had_non_cash_event(check_symbol):
                # Zero-fee fills keep the fee-inclusive average entry equal to
                # the lot-queue cost basis per share (basis conservation).
                # Bonus issues dilute the ledger average at zero marginal cost,
                # which is intentionally NOT lot-basis equality.
                basis = lots.total_cost_basis_inr(check_symbol)
                assert basis == position_qty * position.average_entry_inr

    assert event_log, "the invariant loop must exercise real events"
    buys = sum(1 for item in event_log if " buy " in f" {item} ")
    assert buys > 0
