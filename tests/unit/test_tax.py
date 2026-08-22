"""Unit tests for the India VDA tax engine (Seed Phase step 4)."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from cryptobot.core.tax import TaxEngine

T0 = datetime(2026, 1, 1, tzinfo=UTC)
T1 = datetime(2026, 2, 1, tzinfo=UTC)
T2 = datetime(2026, 3, 1, tzinfo=UTC)


def test_fifo_consumes_oldest_lots_first():
    eng = TaxEngine()
    eng.buy("BTC", Decimal("1"), Decimal("100"), T0)   # lot 1 @100
    eng.buy("BTC", Decimal("1"), Decimal("200"), T1)   # lot 2 @200
    d = eng.sell("BTC", Decimal("1"), Decimal("500"), T2)  # sells lot 1
    assert d.cost_basis == Decimal("100")
    assert d.gain == Decimal("400")
    assert eng.holding("BTC") == Decimal("1")


def test_partial_lot_consumption():
    eng = TaxEngine()
    eng.buy("ETH", Decimal("10"), Decimal("50"), T0)
    eng.sell("ETH", Decimal("4"), Decimal("400"), T1)  # 4@50=200 cost, 400 proceeds
    assert eng.holding("ETH") == Decimal("6")
    assert eng.disposals[0].cost_basis == Decimal("200")


def test_sell_spanning_multiple_lots():
    eng = TaxEngine()
    eng.buy("BTC", Decimal("1"), Decimal("100"), T0)
    eng.buy("BTC", Decimal("1"), Decimal("300"), T1)
    d = eng.sell("BTC", Decimal("1.5"), Decimal("900"), T2)
    # cost = 1*100 + 0.5*300 = 250
    assert d.cost_basis == Decimal("250")
    assert d.gain == Decimal("650")
    assert eng.holding("BTC") == Decimal("0.5")


def test_over_sell_rejected_without_mutation():
    eng = TaxEngine()
    eng.buy("BTC", Decimal("1"), Decimal("100"), T0)
    with pytest.raises(ValueError, match="cannot dispose"):
        eng.sell("BTC", Decimal("2"), Decimal("100"), T1)
    assert eng.holding("BTC") == Decimal("1")
    assert eng.disposals == []


def test_invalid_buys_rejected():
    eng = TaxEngine()
    with pytest.raises(ValueError):
        eng.buy("BTC", Decimal("0"), Decimal("100"), T0)
    with pytest.raises(ValueError):
        eng.buy("BTC", Decimal("-1"), Decimal("100"), T0)
    with pytest.raises(ValueError):
        eng.buy("BTC", Decimal("1"), Decimal("-5"), T0)


def test_loss_gets_no_relief_strict_115bbh():
    eng = TaxEngine()
    # disposal A: gain 400
    eng.buy("BTC", Decimal("1"), Decimal("100"), T0)
    eng.sell("BTC", Decimal("1"), Decimal("500"), T1)
    # disposal B: loss 200 (buy high, sell low)
    eng.buy("ETH", Decimal("1"), Decimal("500"), T0)
    eng.sell("ETH", Decimal("1"), Decimal("300"), T1)

    s = eng.summary()
    assert s["gross_gain"] == "200.00000000"             # 400 - 200
    assert s["losses_disallowed"] == "200.00000000"
    assert s["taxable_income"] == "400.00000000"         # positives only!
    # est tax = 400 * 0.30 * 1.04 = 124.80
    assert s["estimated_tax"] == "124.80"


def test_tds_credit_and_net_payable():
    eng = TaxEngine()
    eng.buy("BTC", Decimal("1"), Decimal("100"), T0)
    d = eng.sell("BTC", Decimal("1"), Decimal("500"), T1)
    assert d.tds_credit == Decimal("5")                  # 1% of 500
    s = eng.summary()
    assert s["tds_credits"] == "5.00"
    assert s["net_tax_payable"] == "119.80"              # 124.80 - 5


def test_swap_creates_disposal_plus_acquisition():
    eng = TaxEngine()
    eng.buy("BTC", Decimal("1"), Decimal("100"), T0)
    d = eng.swap("BTC", Decimal("1"), Decimal("600"),
                 "ETH", Decimal("10"), T1)
    assert d.gain == Decimal("500")                      # BTC leg realized
    assert eng.holding("BTC") == Decimal("0")
    assert eng.holding("ETH") == Decimal("10")
    # ETH lot cost basis = 600/10 = 60 per unit
    d2 = eng.sell("ETH", Decimal("10"), Decimal("700"), T2)
    assert d2.cost_basis == Decimal("600")
    assert d2.gain == Decimal("100")


def test_summary_empty_engine():
    s = TaxEngine().summary()
    assert s["taxable_income"] == "0"
    assert s["estimated_tax"] == "0.00"


def test_schedule_vda_csv_export(tmp_path):
    eng = TaxEngine()
    eng.buy("BTC", Decimal("1"), Decimal("100"), T0)
    eng.sell("BTC", Decimal("1"), Decimal("500"), T1)
    eng.buy("ETH", Decimal("1"), Decimal("500"), T0)
    eng.sell("ETH", Decimal("1"), Decimal("300"), T1)  # loss

    out = eng.export_schedule_vda(tmp_path / "vda.csv")
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3  # header + 2 disposals
    header = lines[0].split(",")
    assert "income_chargeable_under_115BBH" in header
    assert "loss_not_allowed" in header
    btc_row = lines[1].split(",")
    eth_row = lines[2].split(",")
    assert btc_row[0] == "BTC" and btc_row[6] == "400.00000000" and btc_row[7] == "0"
    assert eth_row[0] == "ETH" and eth_row[6] == "0" and eth_row[7] == "200.00000000"


def test_custom_rates_propagate():
    eng = TaxEngine(tax_rate=Decimal("0.20"), cess_rate=Decimal("0"))
    eng.buy("X", Decimal("1"), Decimal("0"), T0)
    eng.sell("X", Decimal("1"), Decimal("1000"), T1)
    assert eng.summary()["estimated_tax"] == "200.00"
