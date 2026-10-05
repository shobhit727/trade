"""Tests for the multi-algorithm trader."""

from __future__ import annotations

from decimal import Decimal

import pytest

from cryptobot.core.events import OrderStatus
from cryptobot.live.multi_trader import MultiAlgoConfig, MultiAlgoTrader


def make_trader(algos=None) -> MultiAlgoTrader:
    cfg = MultiAlgoConfig(
        strategy="dual_ma", warmup_bars=0, port=18097, gate_enabled=False,
        algos=algos or [
            {"name": "dual_ma", "params": {"fast": 1, "slow": 2}, "weight": 0.5},
            {"name": "time_series", "params": {"period": 3, "threshold": 0.0},
             "weight": 0.5},
        ],
    )
    return MultiAlgoTrader(cfg)


def test_weights_normalized():
    tr = make_trader()
    total = sum(s.weight for s in tr.slots)
    assert abs(total - 1.0) < 1e-9
    assert [s.name for s in tr.slots] == ["dual_ma", "time_series"]


def test_requires_positive_weight():
    with pytest.raises(ValueError):
        make_trader(algos=[{"name": "dual_ma", "weight": 0}])


def test_each_algo_gets_own_strategy_instance():
    tr = make_trader()
    assert tr.slots[0].strategy is not tr.slots[1].strategy
    assert tr.slots[0].strategy.config.fast == 1
    assert tr.slots[1].strategy.config.period == 3


def test_feed_collects_orders_from_both_algos():
    tr = make_trader()
    # prime buffers so both algos are past warmup
    for px in (100, 102, 103):
        tr._feed_strategy(px, px, px, 1.0)
    orders = tr._feed_strategy(104, 104, 100, 1.0)
    assert orders is not None and len(orders) >= 1
    tags = {o.strategy for o in orders}
    assert tags <= {"dual_ma", "time_series"}
    assert all(o.strategy for o in orders)


def test_rescale_uses_algo_weight_slice():
    tr = make_trader()
    tr._portfolio._state.total_equity = Decimal("10000")
    from cryptobot.core.events import OrderEvent, OrderSide, OrderType

    o = OrderEvent(symbol="BTCUSDT", side=OrderSide.BUY, type=OrderType.MARKET,
                   quantity=Decimal(1), strategy="dual_ma")
    tr._rescale_order(o, Decimal("100"))
    # weight 0.5 * equity 10000 / price 100 = 50 units
    assert o.quantity == Decimal("50.00000000")


def test_reduce_only_closes_algo_leg():
    tr = make_trader()
    slot = tr.slots[0]
    slot.net_qty = Decimal("3")
    from cryptobot.core.events import OrderEvent, OrderSide, OrderType

    o = OrderEvent(symbol="BTCUSDT", side=OrderSide.SELL, type=OrderType.MARKET,
                   quantity=Decimal(99), reduce_only=True, strategy="dual_ma")
    tr._rescale_order(o, Decimal("100"))
    assert o.quantity == Decimal("3")


def test_per_algo_net_tracking_via_fills():
    tr = make_trader()

    class F:
        status = OrderStatus.FILLED
        symbol = "BTCUSDT"
        strategy = "dual_ma"
        filled_quantity = Decimal("2")
        avg_fill_price = Decimal("100")
        price = None

        def __init__(self, side):
            self.side = side

    from cryptobot.core.events import OrderSide

    trader_fill = F(OrderSide.BUY)
    trader_fill.strategy = "time_series"
    tr._update_position_book(trader_fill)
    assert tr.slots[1].net_qty == Decimal("2")
    assert tr._net_qty["BTCUSDT"] == Decimal("2")  # shared book too


def test_snapshot_lists_algos():
    tr = make_trader()
    snap = tr.stats_snapshot()
    names = [a["name"] for a in snap["algos"]]
    assert names == ["dual_ma", "time_series"]
