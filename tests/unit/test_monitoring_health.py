"""Tests for cryptobot.monitoring.health"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from cryptobot.monitoring.health import (
    CacheHealthChecker,
    ComponentHealth,
    ComponentType,
    DatabaseHealthChecker,
    DataFeedHealthChecker,
    ExchangeHealthChecker,
    HealthCheck,
    HealthMonitor,
    HealthResult,
    RiskEngineHealthChecker,
    StrategyEngineHealthChecker,
    create_standard_checks,
)


def _check(name: str, result: Any, component: str = "EXCHANGE") -> HealthCheck:
    return HealthCheck(
        name=name,
        component=ComponentType(component),
        check_fn=lambda: result,
        timeout_seconds=1.0,
    )


@pytest.mark.asyncio
async def test_health_monitor_run_all_checks_aggregates_results():
    monitor = HealthMonitor(check_interval=0.01)
    monitor.register_check(HealthCheck(name="ok", component="EXCHANGE", check_fn=lambda: True))
    monitor.register_check(HealthCheck(name="bad", component="EXCHANGE", check_fn=lambda: False))

    results = await monitor.run_all_checks()
    by_check = {r.check_name: r for r in results.values()}
    assert by_check["ok"].status == "HEALTHY"
    assert by_check["bad"].status == "UNHEALTHY"
    assert monitor.is_healthy() is False


@pytest.mark.asyncio
async def test_health_monitor_auto_registers_components():
    monitor = HealthMonitor(check_interval=0.01)
    monitor.register_check(
        HealthCheck(name="mystery", component="EXECUTION", check_fn=lambda: True)
    )
    snapshot = await monitor.run_all_checks()
    assert "EXECUTION" in snapshot


@pytest.mark.asyncio
async def test_health_monitor_timeout_becomes_unhealthy():
    monitor = HealthMonitor(check_interval=0.01)

    async def slow():
        await asyncio.sleep(2.0)

    monitor.register_check(
        HealthCheck(
            name="slow",
            component="EXCHANGE",
            check_fn=_slow,
            timeout_seconds=0.05,
        )
    )
    results = await monitor.run_all_checks()
    assert results["slow"].status == "UNHEALTHY"


async def _slow():
    await asyncio.sleep(2.0)
    return True


@pytest.mark.asyncio
async def test_health_monitor_supports_async_check_fns():
    monitor = HealthMonitor(check_interval=0.01)

    async def async_ok():
        await asyncio.sleep(0)
        return True

    async def async_bad():
        await asyncio.sleep(0)
        return False

    monitor.register_check(
        HealthCheck(
            name="async_ok",
            component="EXCHANGE",
            check_fn=async_ok,
        )
    )
    monitor.register_check(
        HealthCheck(
            name="async_bad",
            component="EXCHANGE",
            check_fn=async_bad,
        )
    )

    results = await monitor.run_all_checks()
    assert results["async_ok"].status == "HEALTHY"
    assert results["async_bad"].status == "UNHEALTHY"


def test_create_standard_checks_skips_missing_components():
    checks = create_standard_checks(
        exchange_client=None,
        market_data_manager=None,
    )
    _ = {c.name for c in checks}
    assert "exchange_ping" not in {c.name for c in checks}
    assert "data_freshness" not in {c.name for c in checks}


def test_create_standard_checks_uses_present_components():
    class FakeExchange:
        async def get_server_time(self):
            return 12345

    checks = create_standard_checks(exchange_client=object())
    names = {c.name for c in checks}
    assert "exchange_ping" in names


def test_component_health_success_rate():
    ch = ComponentHealth(component="EXCHANGE", status="HEALTHY")
    assert ch.success_rate == 1.0
    assert ch.is_healthy is True


def test_component_health_tracks_failed():
    ch = ComponentHealth(component="EXCHANGE", status="UNHEALTHY")
    assert ch.is_healthy is False


def test_health_result_creation():
    hr = HealthResult(
        check_name="test",
        component="EXCHANGE",
        status="HEALTHY",
        latency_ms=1.5,
        message="OK",
    )
    assert hr.check_name == "test"
    assert str(hr) == "test: HEALTHY (1.5ms)"


def test_component_health_success_rate_starts_one():
    ch = ComponentHealth(component="EXCHANGE", status="HEALTHY")
    assert ch.success_rate == 1.0
    assert ch.is_healthy


def test_health_check_decorator_no_op():
    assert create_standard_checks() == []


# --- Built-in checkers can be instantiated and queried for component_type ---


def test_exchange_health_checker_component_type():
    assert ExchangeHealthChecker({}).component_type == "EXCHANGE"


def test_data_feed_health_checker_component_type():
    assert DataFeedHealthChecker(None).component_type == "DATA_FEED"


def test_database_health_checker_component_type():
    assert DatabaseHealthChecker(None).component_type == "DATABASE"


def test_cache_health_checker_component_type():
    assert CacheHealthChecker(None).component_type == "CACHE"


def test_risk_engine_health_checker_component_type():
    assert RiskEngineHealthChecker(None).component_type == "RISK"


def test_strategy_engine_health_checker_component_type():
    assert StrategyEngineHealthChecker(None).component_type == "STRATEGY"


# --- Comprehensive test: HealthMonitor with multiple checkers ---


@pytest.mark.asyncio
async def test_health_monitor_with_multiple_checkers():
    monitor = HealthMonitor(check_interval=0.01)
    monitor.register_check(
        HealthCheck(
            name="exchange_ping",
            component="EXCHANGE",
            check_fn=lambda: True,
            timeout_seconds=1.0,
        )
    )
    monitor.register_check(
        HealthCheck(
            name="data_freshness",
            component="DATA_FEED",
            check_fn=lambda: True,
            timeout_seconds=1.0,
        )
    )
    results = await monitor.run_all_checks()
    assert len(results) == 2
    assert all(r.status == "HEALTHY" for r in results.values())


@pytest.mark.asyncio
async def test_health_monitor_component_health_updates():
    monitor = HealthMonitor(check_interval=0.01)
    monitor.register_check(
        HealthCheck(
            name="test",
            component="EXCHANGE",
            check_fn=lambda: True,
            timeout_seconds=1.0,
        )
    )
    await monitor.run_all_checks()
    comp = monitor.get_component_health("EXCHANGE")
    assert comp is not None
    assert comp.is_healthy


# --- HealthChecker subclasses can be instantiated ---


def test_exchange_health_checker_instantiates():
    ch = ExchangeHealthChecker({})
    assert ch.component_type == "EXCHANGE"


# --- Comprehensive test: HealthMonitor with multiple checkers ---


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_health_check_handles_false_return():
    monitor = HealthMonitor(check_interval=0.01)
    monitor.register_check(
        HealthCheck(
            name="failing_check",
            component="EXCHANGE",
            check_fn=lambda: False,
            timeout_seconds=1.0,
        )
    )
    results = await monitor.run_all_checks()
    assert results["failing_check"].status == "UNHEALTHY"


@pytest.mark.asyncio
async def test_health_check_timeout_becomes_unhealthy():
    monitor = HealthMonitor(check_interval=0.01)

    async def slow_check():
        await asyncio.sleep(10)

    monitor.register_check(
        HealthCheck(
            name="slow_check",
            component="EXCHANGE",
            check_fn=slow_check,
            timeout_seconds=0.05,
        )
    )
    results = await monitor.run_all_checks()
    assert results["slow_check"].status == "UNHEALTHY"
    assert "timeout" in results["slow_check"].message.lower()


# --- Edge cases: false return value should be unhealthy ---


@pytest.mark.asyncio
async def test_false_return_is_unhealthy():
    monitor = HealthMonitor(check_interval=0.01)
    monitor.register_check(
        HealthCheck(
            name="returns_false",
            component="EXCHANGE",
            check_fn=lambda: False,
            timeout_seconds=1.0,
        )
    )
    results = await monitor.run_all_checks()
    assert results["returns_false"].status == "UNHEALTHY"
