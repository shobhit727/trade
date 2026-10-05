"""India equity capital-gains engine tests (FIFO, STCG/LTCG, exemption)."""

from __future__ import annotations

from datetime import datetime

import pytest

from cryptobot.core.tax_equity import LTCG_EXEMPT, TaxLedger

D = datetime.fromisoformat


def test_fifo_matching():
    led = TaxLedger()
    led.on_buy("X", 10, 100.0, D("2025-01-01T10:00+05:30"))
    led.on_buy("X", 10, 200.0, D("2025-06-01T10:00+05:30"))
    recs = led.on_sell("X", 15, 300.0, D("2026-08-25T15:00+05:30"))
    assert len(recs) == 2
    assert recs[0].qty == 10 and recs[0].cost == 1000      # first lot first
    assert recs[1].qty == 5 and recs[1].cost == 1000       # half of second
    assert led.lots["X"][0].qty == 5                       # remainder left


def test_stcg_vs_ltcg_classification():
    led = TaxLedger()
    led.on_buy("A", 10, 100.0, D("2024-01-01T10:00+05:30"))   # >365d -> LTCG
    led.on_buy("B", 10, 100.0, D("2026-01-01T10:00+05:30"))   # <365d -> STCG
    r_long = led.on_sell("A", 10, 150.0, D("2026-08-25T15:00+05:30"))[0]
    r_short = led.on_sell("B", 10, 150.0, D("2026-08-25T15:00+05:30"))[0]
    assert r_long.kind == "LTCG" and r_long.holding_days > 365
    assert r_short.kind == "STCG" and r_short.holding_days <= 365


def test_ltcg_exemption_one_twenty_five_k():
    led = TaxLedger()
    led.on_buy("A", 1000, 100.0, D("2020-01-01T10:00+05:30"))
    led.on_sell("A", 1000, 250.0, D("2026-08-25T15:00+05:30"))   # +1.5L gain
    s = led.summary()
    assert s["ltcg_gain"] == pytest.approx(150_000)
    assert s["ltcg_exempt_used"] == pytest.approx(LTCG_EXEMPT)
    assert s["ltcg_taxable"] == pytest.approx(25_000)
    assert s["ltcg_tax"] == pytest.approx(25_000 * 0.125)


def test_stcg_tax_and_negative_gain_no_tax():
    led = TaxLedger()
    led.on_buy("S", 100, 100.0, D("2026-01-01T10:00+05:30"))
    led.on_sell("S", 100, 90.0, D("2026-03-01T15:00+05:30"))     # -1000 STCG
    s = led.summary()
    assert s["stcg_gain"] == pytest.approx(-1000)
    assert s["stcg_tax"] == 0.0                                   # losses not taxed


def test_sell_without_lot_raises():
    led = TaxLedger()
    with pytest.raises(ValueError, match="ledger corrupt"):
        led.on_sell("GHOST", 5, 100.0, D("2026-08-25T15:00+05:30"))


def test_fy_filter():
    led = TaxLedger()
    led.on_buy("A", 1, 100.0, D("2025-05-01T10:00+05:30"))
    led.on_sell("A", 1, 200.0, D("2026-05-10T15:00+05:30"))      # FY27 (Apr26-Mar27)
    from datetime import date
    s_all = led.summary()
    s_fy26 = led.summary(fy_end=date(2026, 3, 31))
    assert s_all["trades"] == 1 and s_fy26["trades"] == 0
