from __future__ import annotations

from typing import Any

import pytest

from cryptobot.core.events import Event, OrderEvent
from cryptobot.strategies.base import (
    BaseStrategy,
    MeanReversionStrategyPlaceholder,
    StrategyRegistry,
)


class _DummyStrategy(BaseStrategy):
    name = "dummy"

    async def initialize(self, initial_data: Any):
        self.internal_state["ready"] = True

    async def on_market_data(self, event: Event) -> list[OrderEvent]:
        return []


# --- BaseStrategy ---------------------------------------------------------

def test_basestrategy_get_name():
    s = _DummyStrategy("my_strat", {"k": "v"})
    assert s.get_name() == "my_strat"


def test_basestrategy_initial_state():
    s = _DummyStrategy("s", {})
    assert s.internal_state == {}


def test_basestrategy_default_on_order_update():
    import asyncio
    s = _DummyStrategy("s", {})
    result = asyncio.run(s.on_order_update(Event()))
    assert result == []


# --- StrategyRegistry -----------------------------------------------------

def test_registry_register_non_subclass():
    reg = StrategyRegistry()
    reg.strategies.clear()
    with pytest.raises(TypeError):
        reg.register(dict, {})


def test_registry_register_and_get():
    reg = StrategyRegistry()
    reg.strategies.clear()
    reg.register(_DummyStrategy, {"name": "alpha"})
    assert "alpha" in reg.strategies


def test_registry_get_all_active_strategies():
    reg = StrategyRegistry()
    reg.strategies.clear()
    reg.register(_DummyStrategy, {"name": "s1"})
    reg.register(_DummyStrategy, {"name": "s2"})
    active = reg.get_all_active_strategies()
    assert len(active) == 2


# --- MeanReversionStrategyPlaceholder -------------------------------------

def test_mr_placeholder_initialize(monkeypatch):
    import cryptobot.utils.decorators as dec
    # Patch the timeout decorator to a no-op (avoid 0.5s timing flakiness)
    monkeypatch.setattr(dec, "timeout_decorator", lambda timeout: lambda f: f)
    monkeypatch.setattr(
        "cryptobot.strategies.base.timeout_decorator",
        lambda timeout: lambda f: f,
    )
    import asyncio
    s = MeanReversionStrategyPlaceholder("mr_test", {"high_trigger": 1.5, "low_trigger": 0.5})
    asyncio.run(s.initialize(None))
    assert "z_score" in s.internal_state


def test_mr_placeholder_no_price():
    import asyncio
    s = MeanReversionStrategyPlaceholder("mr_test", {})
    event = Event(payload={"symbol": "BTCUSDT"})
    result = asyncio.run(s.on_market_data(event))
    assert result == []


__all__ = []
