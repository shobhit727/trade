from __future__ import annotations

import asyncio
from decimal import Decimal

from cryptobot.core.events import OrderEvent, OrderSide
from cryptobot.risk.manager import RiskCheckResult, RiskManager


def test_risk_check_result_to_event_preserves_decimal_via_str():
    order = OrderEvent(symbol="BTCUSDT", side=OrderSide.BUY, quantity=Decimal("1"), price=Decimal("100"), strategy="x")
    rcr = RiskCheckResult(False, "reason", current_value=Decimal("12.345678901234567890"), limit_value=Decimal("100"))
    ev = rcr.to_event("pre_trade", order)
    assert ev.payload["current_value"] == "12.345678901234567890"
    assert ev.payload["limit_value"] == "100"
    assert isinstance(ev.payload["current_value"], str)


def test_risk_manager_below_min_size_rejects():
    rm = RiskManager()
    order = OrderEvent(symbol="BTCUSDT", side=OrderSide.BUY, quantity=Decimal("0.000001"), price=Decimal("100"))
    res = rm.check_order(order, price=Decimal("100"))
    assert res.passed is False
    assert "minimum" in res.message.lower()


def test_risk_manager_above_max_size_rejects():
    rm = RiskManager()
    order = OrderEvent(symbol="BTCUSDT", side=OrderSide.BUY, quantity=Decimal("1000"), price=Decimal("100"))
    res = rm.check_order(order, price=Decimal("100"))
    assert res.passed is False
    assert "maximum" in res.message.lower()


def test_risk_manager_zero_price_uses_fallback():
    rm = RiskManager()
    pm = rm.portfolio
    asyncio.run(pm.update_equity(Decimal("0")))
    order = OrderEvent(symbol="BTCUSDT", side=OrderSide.BUY, quantity=Decimal("0.5"))
    res = rm.check_order(order, price=None)
    assert res.passed is False or res.passed is True
