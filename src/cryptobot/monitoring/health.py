"""
System Health Checks for Cryptobot.

Provides comprehensive health monitoring for exchanges, data feeds,
risk systems, and strategy engines.
"""

from __future__ import annotations

import asyncio
import inspect
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from cryptobot.config import settings
from cryptobot.core.events import EventType
from cryptobot.utils.logging import get_logger

logger = get_logger(__name__)


class HealthStatus(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class ComponentType(StrEnum):
    EXCHANGE = "exchange"
    DATA_FEED = "data_feed"
    RISK_ENGINE = "risk_engine"
    RISK = "risk"
    STRATEGY_ENGINE = "strategy_engine"
    STRATEGY = "strategy"
    ORDER_MANAGER = "order_manager"
    DATABASE = "database"
    CACHE = "cache"
    ML_PIPELINE = "ml_pipeline"
    EXECUTION = "execution"


@dataclass
class HealthCheck:
    """Individual health check definition."""
    name: str
    component: ComponentType
    check_fn: Callable[[], Any]  # Returns bool or raises
    interval_seconds: float = 30.0
    timeout_seconds: float = 5.0
    critical: bool = True
    tags: dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        if isinstance(self.check_fn, str):
            raise ValueError("check_fn must be callable, not string")
        if isinstance(self.component, str):
            # Case-insensitive lookup for ComponentType enum
            component_lower = self.component.lower()
            for ct in ComponentType:
                if ct.value == component_lower:
                    self.component = ct
                    break
            else:
                # If not found, try direct construction (will raise if invalid)
                self.component = ComponentType(self.component)


@dataclass
class HealthResult:
    """Result of a health check."""
    check_name: str
    component: ComponentType
    status: HealthStatus
    timestamp: datetime = field(default_factory=datetime.utcnow)
    latency_ms: float = 0.0
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass
class ComponentHealth:
    """Aggregated health for a component."""
    component: ComponentType
    status: HealthStatus
    checks: list[HealthResult] = field(default_factory=list)
    last_check: datetime | None = None
    uptime_start: datetime | None = None
    total_checks: int = 0
    failed_checks: int = 0

    @property
    def success_rate(self) -> float:
        if self.total_checks == 0:
            return 1.0
        return 1.0 - (self.failed_checks / self.total_checks)

    @property
    def is_healthy(self) -> bool:
        return self.status == HealthStatus.HEALTHY


class HealthChecker(ABC):
    """Abstract base for component-specific health checkers."""

    @property
    @abstractmethod
    def component_type(self) -> ComponentType:
        pass

    @abstractmethod
    async def check(self) -> HealthResult:
        pass


class HealthMonitor:
    """
    Central health monitoring system.

    Runs periodic checks, aggregates results, and publishes events.
    """

    def __init__(
        self,
        check_interval: float = 30.0,
        event_bus: Any | None = None,
    ):
        self.check_interval = check_interval
        self._event_bus = event_bus
        self._checks: dict[str, HealthCheck] = {}
        self._checkers: dict[ComponentType, HealthChecker] = {}
        self._results: dict[str, HealthResult] = {}
        self._component_health: dict[ComponentType, ComponentHealth] = {}
        self._running = False
        self._monitor_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

        # Callbacks
        self._status_change_callbacks: list[Callable[[ComponentType, HealthStatus, HealthStatus], Any]] = []

    def register_check(self, check: HealthCheck):
        """Register a health check."""
        self._checks[check.name] = check
        if check.component not in self._component_health:
            self._component_health[check.component] = ComponentHealth(
                component=check.component,
                status=HealthStatus.UNKNOWN,
                uptime_start=datetime.utcnow(),
            )

    def register_checker(self, checker: HealthChecker):
        """Register a component health checker."""
        self._checkers[checker.component_type] = checker

    def add_status_change_callback(self, callback: Callable[[ComponentType, HealthStatus, HealthStatus], Any]):
        """Add callback for status changes."""
        self._status_change_callbacks.append(callback)

    def unregister_check(self, check_name: str) -> bool:
        """Unregister a health check by name."""
        if check_name in self._checks:
            del self._checks[check_name]
            return True
        return False

    def update_check_interval(self, check_name: str, interval_seconds: float) -> bool:
        """Update the interval of an existing check."""
        if check_name in self._checks:
            self._checks[check_name].interval_seconds = interval_seconds
            return True
        return False

    def get_check(self, check_name: str) -> HealthCheck | None:
        """Get a health check by name."""
        return self._checks.get(check_name)

    async def start(self):
        """Start the health monitor."""
        if self._running:
            return
        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("Health monitor started")

    async def stop(self):
        """Stop the health monitor."""
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        logger.info("Health monitor stopped")

    async def _monitor_loop(self):
        """Main monitoring loop."""
        while self._running:
            try:
                await self.run_all_checks()
            except Exception as e:
                logger.error(f"Health monitor error: {e}")
            await asyncio.sleep(self.check_interval)

    async def run_all_checks(self) -> dict[ComponentType, ComponentHealth]:
        """Run all registered health checks."""
        async with self._lock:
            # Run check functions
            for check in self._checks.values():
                await self._run_check(check)

            # Run checkers
            for checker in self._checkers.values():
                try:
                    result = await checker.check()
                    await self._process_result(result)
                except Exception as e:
                    logger.error(f"Checker {checker.component_type} error: {e}")

            # Update component statuses
            self._update_component_statuses()

        return self._component_health.copy()

    async def _run_check(self, check: HealthCheck):
        """Run a single health check with timeout."""
        start = time.perf_counter()
        try:
            # Run with timeout
            value = check.check_fn()
            if inspect.isawaitable(value):
                value = await asyncio.wait_for(value, timeout=check.timeout_seconds)
            if isinstance(value, tuple):
                healthy, message = bool(value[0]), str(value[1] if len(value) > 1 else "")
            else:
                healthy, message = bool(value) if value is not None else True, "OK"

            latency = (time.perf_counter() - start) * 1000
            result = HealthResult(
                check_name=check.name,
                component=check.component,
                status=HealthStatus.HEALTHY if healthy else HealthStatus.UNHEALTHY,
                latency_ms=latency,
                message=message or ("OK" if healthy else "check returned false"),
            )
        except TimeoutError:
            latency = (time.perf_counter() - start) * 1000
            result = HealthResult(
                check_name=check.name,
                component=check.component,
                status=HealthStatus.UNHEALTHY,
                latency_ms=latency,
                message=f"Timeout after {check.timeout_seconds}s",
                error="timeout",
            )
        except Exception as e:
            latency = (time.perf_counter() - start) * 1000
            result = HealthResult(
                check_name=check.name,
                component=check.component,
                status=HealthStatus.UNHEALTHY,
                latency_ms=latency,
                message=str(e),
                error=type(e).__name__,
            )

        await self._process_result(result)

    async def _process_result(self, result: HealthResult):
        """Process and store a health result."""
        self._results[result.check_name] = result

        comp_health = self._component_health.get(result.component)
        if comp_health is None:
            comp_health = ComponentHealth(
                component=result.component,
                status=HealthStatus.UNKNOWN,
                uptime_start=datetime.utcnow(),
            )
            self._component_health[result.component] = comp_health

        comp_health.checks.append(result)
        comp_health.last_check = result.timestamp
        comp_health.total_checks += 1
        if result.status != HealthStatus.HEALTHY:
            comp_health.failed_checks += 1

        if len(comp_health.checks) > 100:
            comp_health.checks = comp_health.checks[-100:]

        # Publish event
        if self._event_bus:
            await self._event_bus.publish(
                EventType.HEARTBEAT,
                {
                    "check_name": result.check_name,
                    "component": result.component.value,
                    "status": result.status.value,
                    "latency_ms": result.latency_ms,
                    "message": result.message,
                    "details": result.details,
                }
            )

    def _update_component_statuses(self):
        """Update aggregated component statuses."""
        for component, health in self._component_health.items():
            old_status = health.status

            if not health.checks:
                health.status = HealthStatus.UNKNOWN
            else:
                # Get latest check per check name
                latest_checks = {}
                for check in health.checks:
                    if check.check_name not in latest_checks or check.timestamp > latest_checks[check.check_name].timestamp:
                        latest_checks[check.check_name] = check

                # Determine status
                critical_failed = False
                any_failed = False
                any_degraded = False

                for check in self._checks.values():
                    if check.component != component:
                        continue
                    latest = latest_checks.get(check.name)
                    if latest:
                        if latest.status == HealthStatus.UNHEALTHY:
                            any_failed = True
                            if check.critical:
                                critical_failed = True
                        elif latest.status == HealthStatus.DEGRADED:
                            any_degraded = True

                if critical_failed:
                    health.status = HealthStatus.UNHEALTHY
                elif any_failed:
                    health.status = HealthStatus.DEGRADED
                elif any_degraded:
                    health.status = HealthStatus.DEGRADED
                else:
                    health.status = HealthStatus.HEALTHY

            # Notify on status change
            if health.status != old_status:
                for callback in self._status_change_callbacks:
                    try:
                        callback(component, old_status, health.status)
                    except Exception as e:
                        logger.error(f"Status change callback error: {e}")

                # Publish status change event
                if self._event_bus:
                    asyncio.create_task(self._event_bus.publish(
                        EventType.HEARTBEAT,
                        {
                            "type": "status_change",
                            "component": component.value,
                            "old_status": old_status.value,
                            "new_status": health.status.value,
                        }
                    ))

    def get_component_health(self, component: ComponentType) -> ComponentHealth | None:
        """Get health for a specific component."""
        return self._component_health.get(component)

    def get_all_health(self) -> dict[ComponentType, ComponentHealth]:
        """Get health for all components."""
        return self._component_health.copy()

    def get_overall_status(self) -> HealthStatus:
        """Get overall system health status."""
        if not self._component_health:
            return HealthStatus.UNKNOWN

        statuses = [h.status for h in self._component_health.values()]

        if HealthStatus.UNHEALTHY in statuses:
            return HealthStatus.UNHEALTHY
        elif HealthStatus.DEGRADED in statuses:
            return HealthStatus.DEGRADED
        elif HealthStatus.UNKNOWN in statuses:
            return HealthStatus.UNKNOWN
        else:
            return HealthStatus.HEALTHY

    def is_healthy(self) -> bool:
        """Check if overall system is healthy."""
        return self.get_overall_status() == HealthStatus.HEALTHY

    def get_summary(self) -> dict[str, Any]:
        """Get health summary."""
        overall = self.get_overall_status()
        return {
            "overall_status": overall.value,
            "timestamp": datetime.utcnow().isoformat(),
            "components": {
                comp.value: {
                    "status": health.status.value,
                    "success_rate": round(health.success_rate * 100, 1),
                    "total_checks": health.total_checks,
                    "failed_checks": health.failed_checks,
                    "last_check": health.last_check.isoformat() if health.last_check else None,
                    "uptime_seconds": (datetime.utcnow() - health.uptime_start).total_seconds() if health.uptime_start else 0,
                }
                for comp, health in self._component_health.items()
            },
        }


# =============================================================================
# Built-in Health Checkers
# =============================================================================

class ExchangeHealthChecker(HealthChecker):
    """Health checker for exchange connections."""

    @property
    def component_type(self) -> ComponentType:
        return ComponentType.EXCHANGE

    def __init__(self, exchange_client: Any):
        self.exchange_client = exchange_client

    async def check(self) -> HealthResult:
        try:
            # Ping exchange
            start = time.perf_counter()
            if hasattr(self.exchange_client, 'ping'):
                await self.exchange_client.ping()
            elif hasattr(self.exchange_client, 'get_server_time'):
                await self.exchange_client.get_server_time()

            latency = (time.perf_counter() - start) * 1000
            return HealthResult(
                check_name="exchange_connectivity",
                component=ComponentType.EXCHANGE,
                status=HealthStatus.HEALTHY,
                latency_ms=latency,
                message="Exchange reachable",
                details={"latency_ms": latency},
            )
        except Exception as e:
            return HealthResult(
                check_name="exchange_connectivity",
                component=ComponentType.EXCHANGE,
                status=HealthStatus.UNHEALTHY,
                message=str(e),
                error=type(e).__name__,
            )


class DataFeedHealthChecker(HealthChecker):
    """Health checker for market data feeds."""

    @property
    def component_type(self) -> ComponentType:
        return ComponentType.DATA_FEED

    def __init__(self, market_data_manager: Any):
        self.manager = market_data_manager

    async def check(self) -> HealthResult:
        try:
            # Check data freshness
            staleness = {}
            symbols = settings.exchange.symbols or [settings.exchange.default_symbol]
            for symbol in symbols:
                ticker = self.manager.get_ticker(symbol)
                if ticker:
                    age = (datetime.utcnow() - ticker.timestamp).total_seconds()
                    staleness[symbol] = age

            max_staleness = max(staleness.values()) if staleness else 0
            if max_staleness > 60:
                return HealthResult(
                    check_name="data_freshness",
                    component=ComponentType.DATA_FEED,
                    status=HealthStatus.UNHEALTHY,
                    message=f"Stale data: max age {max_staleness:.0f}s",
                    details={"staleness": staleness},
                )
            elif max_staleness > 10:
                return HealthResult(
                    check_name="data_freshness",
                    component=ComponentType.DATA_FEED,
                    status=HealthStatus.DEGRADED,
                    message=f"Data slightly stale: max age {max_staleness:.0f}s",
                    details={"staleness": staleness},
                )
            else:
                return HealthResult(
                    check_name="data_freshness",
                    component=ComponentType.DATA_FEED,
                    status=HealthStatus.HEALTHY,
                    message="Data feeds healthy",
                    details={"staleness": staleness},
                )
        except Exception as e:
            return HealthResult(
                check_name="data_freshness",
                component=ComponentType.DATA_FEED,
                status=HealthStatus.UNHEALTHY,
                message=str(e),
                error=type(e).__name__,
            )


class DatabaseHealthChecker(HealthChecker):
    """Health checker for database connections."""

    @property
    def component_type(self) -> ComponentType:
        return ComponentType.DATABASE

    def __init__(self, pool: Any):
        self.pool = pool

    async def check(self) -> HealthResult:
        try:
            start = time.perf_counter()
            async with self.pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            latency = (time.perf_counter() - start) * 1000
            return HealthResult(
                check_name="database_connection",
                component=ComponentType.DATABASE,
                status=HealthStatus.HEALTHY,
                latency_ms=latency,
                message="Database connected",
                details={"latency_ms": latency},
            )
        except Exception as e:
            return HealthResult(
                check_name="database_connection",
                component=ComponentType.DATABASE,
                status=HealthStatus.UNHEALTHY,
                message=str(e),
                error=type(e).__name__,
            )


class CacheHealthChecker(HealthChecker):
    """Health checker for Redis cache."""

    @property
    def component_type(self) -> ComponentType:
        return ComponentType.CACHE

    def __init__(self, redis_client: Any):
        self.redis = redis_client

    async def check(self) -> HealthResult:
        try:
            start = time.perf_counter()
            await self.redis.ping()
            latency = (time.perf_counter() - start) * 1000
            return HealthResult(
                check_name="cache_connection",
                component=ComponentType.CACHE,
                status=HealthStatus.HEALTHY,
                latency_ms=latency,
                message="Cache connected",
                details={"latency_ms": latency},
            )
        except Exception as e:
            return HealthResult(
                check_name="cache_connection",
                component=ComponentType.CACHE,
                status=HealthStatus.UNHEALTHY,
                message=str(e),
                error=type(e).__name__,
            )


class RiskEngineHealthChecker(HealthChecker):
    """Health checker for risk engine."""

    @property
    def component_type(self) -> ComponentType:
        return ComponentType.RISK_ENGINE

    def __init__(self, portfolio_manager: Any, state_manager: Any):
        self.portfolio = portfolio_manager
        self.state = state_manager

    async def check(self) -> HealthResult:
        try:
            # Check portfolio state
            portfolio_state = self.portfolio.get_state()
            daily_loss_pct = self.portfolio.get_daily_pnl_pct()
            max_loss_pct = settings.risk.kill_switch_daily_loss_pct

            details = {
                "daily_pnl_pct": daily_loss_pct,
                "max_allowed_loss_pct": max_loss_pct,
                "kill_switch_active": daily_loss_pct <= -max_loss_pct,
                "open_positions": portfolio_state.open_positions,
                "open_orders": portfolio_state.open_orders,
            }

            if daily_loss_pct <= -max_loss_pct:
                return HealthResult(
                    check_name="risk_limits",
                    component=ComponentType.RISK_ENGINE,
                    status=HealthStatus.UNHEALTHY,
                    message=f"Kill switch triggered: daily loss {daily_loss_pct:.2%}",
                    details=details,
                )
            elif daily_loss_pct <= -max_loss_pct * 0.8:
                return HealthResult(
                    check_name="risk_limits",
                    component=ComponentType.RISK_ENGINE,
                    status=HealthStatus.DEGRADED,
                    message=f"Approaching daily loss limit: {daily_loss_pct:.2%}",
                    details=details,
                )
            else:
                return HealthResult(
                    check_name="risk_limits",
                    component=ComponentType.RISK_ENGINE,
                    status=HealthStatus.HEALTHY,
                    message="Risk limits OK",
                    details=details,
                )
        except Exception as e:
            return HealthResult(
                check_name="risk_limits",
                component=ComponentType.RISK_ENGINE,
                status=HealthStatus.UNHEALTHY,
                message=str(e),
                error=type(e).__name__,
            )


class StrategyEngineHealthChecker(HealthChecker):
    """Health checker for strategy engine."""

    @property
    def component_type(self) -> ComponentType:
        return ComponentType.STRATEGY_ENGINE

    def __init__(self, strategy_manager: Any):
        self.manager = strategy_manager

    async def check(self) -> HealthResult:
        try:
            active_strategies = self.manager.get_active_strategies() if hasattr(self.manager, 'get_active_strategies') else []
            error_count = self.manager.get_error_count() if hasattr(self.manager, 'get_error_count') else 0

            if error_count > 10:
                return HealthResult(
                    check_name="strategy_engine",
                    component=ComponentType.STRATEGY_ENGINE,
                    status=HealthStatus.DEGRADED,
                    message=f"High error count: {error_count}",
                    details={"active_strategies": len(active_strategies), "errors": error_count},
                )
            else:
                return HealthResult(
                    check_name="strategy_engine",
                    component=ComponentType.STRATEGY_ENGINE,
                    status=HealthStatus.HEALTHY,
                    message="Strategy engine OK",
                    details={"active_strategies": len(active_strategies), "errors": error_count},
                )
        except Exception as e:
            return HealthResult(
                check_name="strategy_engine",
                component=ComponentType.STRATEGY_ENGINE,
                status=HealthStatus.UNHEALTHY,
                message=str(e),
                error=type(e).__name__,
            )


# =============================================================================
# Health Check Utilities
# =============================================================================

def create_standard_checks(
    market_data_manager: Any = None,
    portfolio_manager: Any = None,
    state_manager: Any = None,
    exchange_client: Any = None,
    redis_client: Any = None,
    db_pool: Any = None,
    strategy_manager: Any = None,
) -> list[HealthCheck]:
    """Create standard health checks for the system."""
    checks = []

    # Exchange connectivity
    if exchange_client:
        async def _exchange_ping():
            return await _ping_exchange(exchange_client)

        checks.append(HealthCheck(
            name="exchange_ping",
            component=ComponentType.EXCHANGE,
            check_fn=_exchange_ping,
            interval_seconds=30,
            critical=True,
        ))

    # Data feed freshness
    if market_data_manager:
        async def _data_freshness():
            return await _check_data_freshness(market_data_manager)

        checks.append(HealthCheck(
            name="data_freshness",
            component=ComponentType.DATA_FEED,
            check_fn=_data_freshness,
            interval_seconds=15,
            critical=True,
        ))

    # Database
    if db_pool:
        async def _database_ping():
            return await _ping_database(db_pool)

        checks.append(HealthCheck(
            name="database_ping",
            component=ComponentType.DATABASE,
            check_fn=_database_ping,
            interval_seconds=60,
            critical=True,
        ))

    # Cache
    if redis_client:
        async def _cache_ping():
            return await _ping_cache(redis_client)

        checks.append(HealthCheck(
            name="cache_ping",
            component=ComponentType.CACHE,
            check_fn=_cache_ping,
            interval_seconds=60,
            critical=False,
        ))

    return checks


async def _ping_exchange(client: Any):
    """Ping exchange client."""
    if hasattr(client, 'ping'):
        await client.ping()
    elif hasattr(client, 'get_server_time'):
        await client.get_server_time()
    else:
        raise NotImplementedError("No ping method")


async def _check_data_freshness(manager: Any):
    """Check data feed freshness."""
    symbols = settings.exchange.symbols or [settings.exchange.default_symbol]
    max_age = 0
    for symbol in symbols:
        ticker = manager.get_ticker(symbol)
        if ticker:
            age = (datetime.utcnow() - ticker.timestamp).total_seconds()
            max_age = max(max_age, age)

    if max_age > 60:
        raise Exception(f"Data stale: max age {max_age:.0f}s")


async def _ping_database(pool: Any):
    """Ping database pool."""
    async with pool.acquire() as conn:
        await conn.fetchval("SELECT 1")


async def _ping_cache(redis_client: Any):
    """Ping Redis cache."""
    await redis_client.ping()


# Global health monitor
_health_monitor: HealthMonitor | None = None


def get_health_monitor() -> HealthMonitor:
    global _health_monitor
    if _health_monitor is None:
        _health_monitor = HealthMonitor()
    return _health_monitor


def get_health_checker() -> HealthMonitor:
    """Alias for get_health_monitor() — a HealthMonitor satisfies the HealthChecker contract."""
    return get_health_monitor()


async def init_health_monitor(
    market_data_manager: Any = None,
    portfolio_manager: Any = None,
    state_manager: Any = None,
    exchange_client: Any = None,
    redis_client: Any = None,
    db_pool: Any = None,
    strategy_manager: Any = None,
) -> HealthMonitor:
    """Initialize and start health monitor with standard checks."""
    global _health_monitor
    _health_monitor = HealthMonitor()

    # Add standard checks
    for check in create_standard_checks(
        market_data_manager, portfolio_manager, state_manager,
        exchange_client, redis_client, db_pool, strategy_manager
    ):
        _health_monitor.register_check(check)

    # Add checkers
    if portfolio_manager and state_manager:
        _health_monitor.register_checker(RiskEngineHealthChecker(portfolio_manager, state_manager))
    if strategy_manager:
        _health_monitor.register_checker(StrategyEngineHealthChecker(strategy_manager))
    if exchange_client:
        _health_monitor.register_checker(ExchangeHealthChecker(exchange_client))
    if market_data_manager:
        _health_monitor.register_checker(DataFeedHealthChecker(market_data_manager))
    if redis_client:
        _health_monitor.register_checker(CacheHealthChecker(redis_client))
    if db_pool:
        _health_monitor.register_checker(DatabaseHealthChecker(db_pool))

    await _health_monitor.start()
    return _health_monitor


async def shutdown_health_monitor():
    """Shutdown health monitor."""
    global _health_monitor
    if _health_monitor:
        await _health_monitor.stop()
        _health_monitor = None
