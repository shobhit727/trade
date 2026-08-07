from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio


def _utcnow() -> datetime:
    return datetime.now(UTC)


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset global singletons between tests to prevent state leakage."""
    import cryptobot.core.bus as bus_mod
    import cryptobot.core.portfolio as pf_mod
    import cryptobot.core.state as state_mod
    import cryptobot.monitoring.alerting as alert_mod
    import cryptobot.monitoring.health as health_mod

    bus_mod._bus = None
    pf_mod._portfolio_manager = None
    state_mod.state_manager._orders.clear()
    state_mod.state_manager._positions.clear()
    alert_mod._alert_manager = None
    health_mod._health_monitor = None
    yield


@pytest.fixture
def fixed_now() -> datetime:
    """Frozen UTC timestamp for deterministic tests."""
    return datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def sample_ohlcv():
    """Minimal OHLCV dataset."""
    return [
        {
            "open_time": _utcnow() - timedelta(minutes=5 * i),
            "open": 100.0 + i,
            "high": 101.0 + i,
            "low": 99.0 + i,
            "close": 100.5 + i,
            "volume": 10.0,
        }
        for i in range(5)
    ]


@pytest.fixture
def sample_order_event():
    """Order event with sane defaults."""
    from cryptobot.core.events import OrderEvent, OrderSide, OrderType

    return OrderEvent(
        order_id="test-order-1",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        type=OrderType.LIMIT,
        quantity=Decimal("1.0"),
        price=Decimal("50000"),
        strategy="test",
    )


@pytest.fixture
def sample_signal_event():
    """Signal event with sane defaults."""
    from cryptobot.core.events import SignalEvent, SignalSide, SignalStrength

    return SignalEvent(
        strategy="trend",
        symbol="BTCUSDT",
        side=SignalSide.BUY,
        strength=SignalStrength.MODERATE,
        price=Decimal("50000"),
        quantity=Decimal("1.0"),
    )


@pytest.fixture
def metrics_registry(monkeypatch):
    """Fresh Prometheus registry + module metrics for each test.

    Replaces the module-level ``registry`` and the ``_real_generate_latest``
    binding so every test sees an isolated, empty metric set. Metrics are
    recorded through the module's record_* functions which reference the
    original metric objects, so those are re-created too by reloading the
    module against the fresh registry.
    """
    import importlib

    import cryptobot.monitoring.metrics as metrics_mod

    if metrics_mod.PROMETHEUS_AVAILABLE:
        metrics_mod.registry = metrics_mod.CollectorRegistry()
        importlib.reload(metrics_mod)
        yield
        importlib.reload(metrics_mod)
    else:
        yield


@pytest_asyncio.fixture
async def event_bus():
    """Fresh event bus for each test."""
    from cryptobot.core.bus import close_event_bus, init_event_bus
    bus = await init_event_bus(max_history=100)
    yield bus
    await close_event_bus()
