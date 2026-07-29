from __future__ import annotations

from decimal import Decimal

import pytest

from cryptobot.core.events import OrderEvent, OrderSide, OrderType
from cryptobot.execution.adverse_selection import (
    AdverseAction,
    AdverseSelectionConfig,
    AdverseSelectionGuard,
    QueuePosition,
    TopOfBook,
    attach_to_engine,
)


def _buy_order(order_id: str = "o1", price: Decimal = Decimal("100")) -> OrderEvent:
    return OrderEvent(
        order_id=order_id,
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        type=OrderType.LIMIT,
        quantity=Decimal("1"),
        price=price,
    )


def _top(mid: Decimal = Decimal("100"), bid: Decimal = Decimal("99.5"), ask: Decimal = Decimal("100.5")) -> TopOfBook:
    return TopOfBook.from_levels([bid], [ask])


def test_top_of_book_computes_mid_spread_imbalance():
    top = TopOfBook.from_levels([Decimal(99), Decimal(98)], [Decimal(101), Decimal(102)])
    assert top.mid == Decimal("100")
    assert top.bid == Decimal(99)
    assert top.ask == Decimal(101)
    assert top.spread_bps > 0


def test_register_records_queue_position():
    g = AdverseSelectionGuard()
    order = _buy_order()
    pos = g.register(order, _top())
    assert pos.mid_at_place == Decimal("100")
    assert order.order_id in g.tracked
    g.forget(order.order_id)
    assert order.order_id not in g.tracked


def test_step_returns_none_when_top_unchanged():
    g = AdverseSelectionGuard(AdverseSelectionConfig(mid_move_bps=5.0))
    order = _buy_order()
    g.register(order, _top())
    action = g.step(order.order_id, _top())
    assert action == AdverseAction.NONE


def test_step_cancels_when_mid_moves_beyond_threshold():
    g = AdverseSelectionGuard(AdverseSelectionConfig(mid_move_bps=2.0))
    order = _buy_order()
    g.register(order, _top())
    moved_top = TopOfBook.from_levels([Decimal(99.0)], [Decimal(101.0)])
    assert g.step(order.order_id, moved_top) == AdverseAction.CANCEL


def test_step_cancels_when_spread_widens():
    g = AdverseSelectionGuard(AdverseSelectionConfig(mid_move_bps=999, spread_widening_bps=1.5))
    order = _buy_order()
    g.register(order, TopOfBook.from_levels([Decimal(99)], [Decimal(101)]))
    wider_top = TopOfBook.from_levels([Decimal(98)], [Decimal(104)])
    assert g.step(order.order_id, wider_top) == AdverseAction.CANCEL


def test_step_cancels_on_toxic_imbalance_spike():
    cfg = AdverseSelectionConfig(
        mid_move_bps=10_000,
        spread_widening_bps=10_000,
        toxicity_threshold=0.3,
        book_imbalance_threshold=0.6,
    )
    g = AdverseSelectionGuard(cfg)
    order = _buy_order()
    g.register(order, TopOfBook.from_levels([Decimal(99)], [Decimal(101)]))
    for _ in range(20):
        g.note_top(TopOfBook(imbalance=1.0, bid=Decimal(0), ask=Decimal(0), mid=Decimal(0)))
    flipped = TopOfBook.from_levels([Decimal(110)], [Decimal(112)])
    assert g.step(order.order_id, flipped) == AdverseAction.CANCEL


def test_step_returns_none_when_no_position():
    g = AdverseSelectionGuard()
    assert g.step("missing-id", _top()) == AdverseAction.NONE


def test_attach_to_engine_requires_cancel_order():
    class _Noop:
        pass

    g = AdverseSelectionGuard()
    with pytest.raises(TypeError):
        import asyncio

    asyncio.run(attach_to_engine(_Noop(), g))


class _StubEngine:
    def __init__(self):
        self.cancelled = []
        self.submitted = []

    async def submit_order(self, order: OrderEvent) -> OrderEvent:
        self.submitted.append(order)
        return order

    async def cancel_order(self, order_id: str) -> bool:
        self.cancelled.append(order_id)
        return True


@pytest.mark.asyncio
async def test_attach_to_engine_links_guard():
    g = AdverseSelectionGuard()
    engine = _StubEngine()
    await attach_to_engine(engine, g)
    assert getattr(engine, "adverse_guard", None) is g


def test_decide_replace_returns_mid_when_side_matches():
    g = AdverseSelectionGuard()
    order = _buy_order()
    pos = g.register(order, _top())
    assert g.decide_replace(pos, _top(), side=order.side.value) == pos.mid_at_place


def test_toxicity_average_increases_with_polarised_top():
    g = AdverseSelectionGuard()
    base_top = _top()
    for _ in range(5):
        g.note_top(base_top)
    for _ in range(50):
        polarised = TopOfBook(bid=Decimal("0"), ask=Decimal("0"), mid=Decimal("0"), imbalance=0.95)
        g.note_top(polarised)
    assert g.last_toxicity > 0.5


def test_forget_removes_position():
    g = AdverseSelectionGuard()
    order = _buy_order(order_id="o42")
    g.register(order, _top())
    assert "o42" in g.tracked
    g.forget("o42")
    assert "o42" not in g.tracked
