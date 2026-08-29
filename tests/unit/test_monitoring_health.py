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
    HealthStatus,
    RiskEngineHealthChecker,
    StrategyEngineHealthChecker,
    _check_data_freshness,
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
    exchange_health = results.get(ComponentType.EXCHANGE)
    assert exchange_health is not None
    check_names = {c.check_name for c in exchange_health.checks}
    assert "ok" in check_names
    assert "bad" in check_names
    ok_check = next(c for c in exchange_health.checks if c.check_name == "ok")
    bad_check = next(c for c in exchange_health.checks if c.check_name == "bad")
    assert ok_check.status == HealthStatus.HEALTHY
    assert bad_check.status == HealthStatus.UNHEALTHY
    assert monitor.is_healthy() is False


@pytest.mark.asyncio
async def test_health_monitor_auto_registers_components():
    monitor = HealthMonitor(check_interval=0.01)
    monitor.register_check(
        HealthCheck(name="mystery", component="EXECUTION", check_fn=lambda: True)
    )
    snapshot = await monitor.run_all_checks()
    assert ComponentType.EXECUTION in snapshot


@pytest.mark.asyncio
async def test_health_monitor_timeout_becomes_unhealthy():
    monitor = HealthMonitor(check_interval=0.01)

    async def slow():
        await asyncio.sleep(2.0)

    monitor.register_check(
        HealthCheck(
            name="slow",
            component="EXCHANGE",
            check_fn=slow,
            timeout_seconds=0.05,
        )
    )
    results = await monitor.run_all_checks()
    exchange_health = results.get(ComponentType.EXCHANGE)
    assert exchange_health is not None
    slow_check = next(c for c in exchange_health.checks if c.check_name == "slow")
    assert slow_check.status == HealthStatus.UNHEALTHY


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
    exchange_health = results.get(ComponentType.EXCHANGE)
    assert exchange_health is not None
    async_ok_check = next(c for c in exchange_health.checks if c.check_name == "async_ok")
    async_bad_check = next(c for c in exchange_health.checks if c.check_name == "async_bad")
    assert async_ok_check.status == HealthStatus.HEALTHY
    assert async_bad_check.status == HealthStatus.UNHEALTHY


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
    ch = ComponentHealth(component=ComponentType.EXCHANGE, status=HealthStatus.HEALTHY)
    assert ch.success_rate == 1.0
    assert ch.is_healthy is True


def test_component_health_tracks_failed():
    ch = ComponentHealth(component=ComponentType.EXCHANGE, status=HealthStatus.UNHEALTHY)
    assert ch.is_healthy is False


def test_health_result_creation():
    hr = HealthResult(
        check_name="test",
        component=ComponentType.EXCHANGE,
        status=HealthStatus.HEALTHY,
        latency_ms=1.5,
        message="OK",
    )
    assert hr.check_name == "test"
    assert "test" in str(hr)
    assert "HEALTHY" in str(hr)
    assert "1.5" in str(hr)


def test_component_health_success_rate_starts_one():
    ch = ComponentHealth(component=ComponentType.EXCHANGE, status=HealthStatus.HEALTHY)
    assert ch.success_rate == 1.0
    assert ch.is_healthy


def test_health_check_decorator_no_op():
    assert create_standard_checks() == []


# --- Built-in checkers can be instantiated and queried for component_type ---


def test_exchange_health_checker_component_type():
    assert ExchangeHealthChecker({}).component_type == ComponentType.EXCHANGE


def test_data_feed_health_checker_component_type():
    assert DataFeedHealthChecker(None).component_type == ComponentType.DATA_FEED


def test_database_health_checker_component_type():
    assert DatabaseHealthChecker(None).component_type == ComponentType.DATABASE


def test_cache_health_checker_component_type():
    assert CacheHealthChecker(None).component_type == ComponentType.CACHE


def test_risk_engine_health_checker_component_type():
    assert RiskEngineHealthChecker(None, None).component_type == ComponentType.RISK_ENGINE


def test_strategy_engine_health_checker_component_type():
    assert StrategyEngineHealthChecker(None).component_type == ComponentType.STRATEGY_ENGINE


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
    assert all(h.status == HealthStatus.HEALTHY for h in results.values())


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
    comp = monitor.get_component_health(ComponentType.EXCHANGE)
    assert comp is not None
    assert comp.is_healthy


# --- HealthChecker subclasses can be instantiated ---


def test_exchange_health_checker_instantiates():
    ch = ExchangeHealthChecker({})
    assert ch.component_type == ComponentType.EXCHANGE


# --- Comprehensive test: HealthMonitor with multiple checkers ---


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
    exchange_health = results.get(ComponentType.EXCHANGE)
    assert exchange_health is not None
    failing = next(c for c in exchange_health.checks if c.check_name == "failing_check")
    assert failing.status == HealthStatus.UNHEALTHY


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
    exchange_health = results.get(ComponentType.EXCHANGE)
    assert exchange_health is not None
    slow = next(c for c in exchange_health.checks if c.check_name == "slow_check")
    assert slow.status == HealthStatus.UNHEALTHY
    assert "timeout" in slow.message.lower()


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
    exchange_health = results.get(ComponentType.EXCHANGE)
    assert exchange_health is not None
    check = next(c for c in exchange_health.checks if c.check_name == "returns_false")
    assert check.status == HealthStatus.UNHEALTHY


# --- Issue #34: a feed that delivers no ticker data must be UNHEALTHY, not "fresh" ---


class _NoDataManager:
    """A market-data manager that never returns any ticker."""

    def get_ticker(self, symbol):  # noqa: ANN001
        return None


@pytest.mark.asyncio
async def test_data_feed_checker_unhealthy_without_tickers():
    checker = DataFeedHealthChecker(_NoDataManager())
    result = await checker.check()
    assert result.status == HealthStatus.UNHEALTHY
    assert "No market data received from feed" in result.message


@pytest.mark.asyncio
async def test_check_data_freshness_raises_without_tickers():
    with pytest.raises(Exception, match="No market data received from feed"):
        await _check_data_freshness(_NoDataManager())


# --- Issue #35: HealthChecker results (not registered HealthChecks) must surface ---


@pytest.mark.asyncio
async def test_component_status_reflects_checker_results():
    monitor = HealthMonitor(check_interval=0.01)
    comp = ComponentType.RISK_ENGINE
    monitor._component_health[comp] = ComponentHealth(
        component=comp,
        status=HealthStatus.UNKNOWN,
        checks=[
            HealthResult(
                check_name="risk_limits",
                component=comp,
                status=HealthStatus.UNHEALTHY,
                message="Kill switch engaged",
            )
        ],
    )
    await monitor._update_component_statuses()
    health = monitor.get_component_health(comp)
    assert health is not None
    assert health.status == HealthStatus.UNHEALTHY
