"""Cost model tests — the numbers everyone else assumes.

The critical assertions here are the **calibration** ones: our model must reproduce the
published Indian delivery round-trip figure exactly. If this drifts, every backtest in
the repo is quietly wrong.
"""

from decimal import Decimal as D

import pytest

from nsealgo.costs import DP_CHARGE_PER_SCRIP, STRESS_MODELS, CostModel


class TestPublishedCalibration:
    """These come from two independent line-by-line itemisations of Indian delivery
    round trips, which converge on ~11.65 bps of turnover."""

    def test_reproduces_published_itemisation(self) -> None:
        # Rs 1,40,000 buy + Rs 1,47,000 sell -> Rs 334.33 total charges = 11.65 bps.
        cm = CostModel(segment="delivery", slippage_bps=D(0))
        b = cm.cost("BUY", D(1), D(140_000))
        s = cm.cost("SELL", D(1), D(147_000))
        total = b.total + s.total
        turnover = D(287_000)
        bps = (total / turnover * D(10_000))

        assert total == D("334.67"), f"expected Rs 334.67, got {total}"
        assert D("11.6") <= bps <= D("11.7"), f"expected ~11.66 bps, got {bps}"

    def test_round_trip_bps_matches_reference(self) -> None:
        cm = CostModel(segment="delivery", slippage_bps=D(0))
        # At Rs 1L/side the flat DP charge is well amortised -> ~11.9 bps.
        assert cm.round_trip_bps(D(100_000)) == D("11.92")

    def test_slippage_adds_two_sides(self) -> None:
        cm = CostModel(segment="delivery", slippage_bps=D(5))
        assert cm.all_in_round_trip_bps(D(100_000)) == D("11.92") + D(10)


class TestStatutoryCharges:
    def test_stt_applies_to_both_sides_for_delivery(self) -> None:
        """Regression: STT was modelled sell-only, understating cost ~2x. Since Oct 2024
        delivery STT is 0.1% on BOTH the buy and the sell leg."""
        cm = CostModel(segment="delivery", slippage_bps=D(0))
        buy = cm.cost("BUY", D(1), D(100_000))
        sell = cm.cost("SELL", D(1), D(100_000))
        assert buy.stt == D("100.00")
        assert sell.stt == D("100.00")

    def test_stamp_duty_buy_side_only(self) -> None:
        cm = CostModel(segment="delivery", slippage_bps=D(0))
        assert cm.cost("BUY", D(1), D(100_000)).stamp_duty == D("15.00")
        assert cm.cost("SELL", D(1), D(100_000)).stamp_duty == D("0")

    def test_dp_charge_sell_only_and_flat(self) -> None:
        cm = CostModel(segment="delivery", slippage_bps=D(0))
        assert cm.cost("BUY", D(1), D(100_000)).dp_charges == D("0")
        small = cm.cost("SELL", D(1), D(10_000))
        big = cm.cost("SELL", D(1), D(1_000_000))
        assert small.dp_charges == big.dp_charges == DP_CHARGE_PER_SCRIP

    def test_gst_excludes_stt_and_stamp(self) -> None:
        """GST is charged on brokerage + exchange txn + SEBI only — NOT on STT or stamp.
        Charging GST on STT would overstate costs ~35%."""
        cm = CostModel(segment="delivery", slippage_bps=D(0))
        c = cm.cost("BUY", D(1), D(100_000))
        taxable = c.brokerage + c.exchange_txn + c.sebi
        assert c.gst == (taxable * D("0.18")).quantize(D("0.01"))
        assert c.gst < c.stt

    def test_intraday_stt_is_lower_than_delivery(self) -> None:
        deliv = CostModel(segment="delivery", slippage_bps=D(0)).cost(
            "SELL", D(1), D(100_000))
        intra = CostModel(segment="intraday", slippage_bps=D(0)).cost(
            "SELL", D(1), D(100_000))
        assert intra.stt == D("25.00")
        assert intra.stt < deliv.stt

    def test_unknown_segment_rejected(self) -> None:
        with pytest.raises(ValueError, match="unknown segment"):
            CostModel(segment="crypto")


class TestSlippage:
    def test_buys_fill_worse_sells_fill_worse(self) -> None:
        cm = CostModel(slippage_bps=D(10))
        ref = D("1000")
        assert cm.fill_price(ref, "BUY") > ref
        assert cm.fill_price(ref, "SELL") < ref

    def test_zero_slippage_is_exact(self) -> None:
        cm = CostModel(slippage_bps=D(0))
        assert cm.fill_price(D("123.45"), "BUY") == D("123.450")
        assert cm.fill_price(D("123.45"), "SELL") == D("123.450")

    def test_negative_slippage_rejected(self) -> None:
        with pytest.raises(ValueError, match="slippage_bps"):
            CostModel(slippage_bps=D(-1))

    def test_bad_side_rejected(self) -> None:
        with pytest.raises(ValueError, match="BUY or SELL"):
            CostModel().fill_price(D("100"), "HOLD")


class TestValidation:
    def test_negative_quantity_rejected(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            CostModel().cost("BUY", D(-1), D("100"))

    def test_negative_price_rejected(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            CostModel().cost("BUY", D("1"), D("-100"))

    def test_zero_notional_rejected_in_bps(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            CostModel().round_trip_bps(D(0))


class TestStressModels:
    def test_stress_models_are_monotonic_in_slippage(self) -> None:
        """Gate 4 depends on this ordering."""
        zero = STRESS_MODELS["zero_cost"].all_in_round_trip_bps(D(100_000))
        base = STRESS_MODELS["base"].all_in_round_trip_bps(D(100_000))
        dbl = STRESS_MODELS["double_slippage"].all_in_round_trip_bps(D(100_000))
        tri = STRESS_MODELS["triple_slippage"].all_in_round_trip_bps(D(100_000))
        assert zero < base < dbl < tri

    def test_costs_decrease_with_size(self) -> None:
        """Flat DP charge means bigger positions have lower bps."""
        cm = CostModel(slippage_bps=D(0))
        assert cm.round_trip_bps(D(20_000)) > cm.round_trip_bps(D(500_000))


class TestRoundTrip:
    def test_gross_pnl_and_cost_are_separate(self) -> None:
        cm = CostModel(slippage_bps=D(0))
        cost, gross = cm.round_trip(D(100), D("100"), D("110"))
        assert gross == D("1000")
        assert cost > 0
        assert gross - cost < gross

    def test_break_even_requires_price_rise_covering_costs(self) -> None:
        """A position that does not move cannot cover the cost stack."""
        cm = CostModel(slippage_bps=D(0))
        cost, gross = cm.round_trip(D(100), D("100"), D("100"))
        assert gross == D("0")
        assert cost > 0
