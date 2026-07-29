# 15. Design Patterns

> **Last Updated**: 2026-07-29 (audit pass)
> **Confidence**: High.

## Singleton

- `cryptobot.core.state.state_manager` (class-level `_instance` + `threading.Lock`).
- `cryptobot.core.bus.get_event_bus()` / `init_event_bus()` (module-level `_bus`).
- `cryptobot.core.clock.get_clock()` / `set_clock()` (module-level `_clock`).
- `cryptobot.core.portfolio.get_portfolio_manager()` (module-level `_portfolio_manager`).
- `cryptobot.risk.manager.get_risk_manager()` (module-level `_risk_manager`).
- `cryptobot.execution.engine.get_execution_engine()` (module-level `_execution_engine`).
- `cryptobot.strategies.base.registry = StrategyRegistry()` (creates singleton on import).
- `cryptobot.backtest.engine.create_backtest_engine()` (factory).
- `cryptobot.data.storage.get_storage()` / `init_storage()`.
- `cryptobot.monitoring.alerting.get_alert_manager()` / `init_alerting()`.
- `cryptobot.monitoring.health.get_health_monitor()` / `init_health_monitor()`.
- `cryptobot.monitoring.metrics.get_metrics_collector()`.
- `cryptobot.data.ingestion.get_ingestion_manager()`.
- `cryptobot.config.settings` (cached via `lru_cache`).

## Factory

- `cryptobot.core.clock.ClockFactory.create(...)` / `create_for_backtest` / `create_for_paper` / `create_for_live`.
- `cryptobot.backtest.simulator.FillSimulatorFactory.create_for_backtest` / `create_for_paper` / `create_for_live`.
- `cryptobot.execution.venue.base.Venue` (abstract) + `SimulatedVenue` (concrete).

## Strategy

- `cryptobot.strategies.base.BaseStrategy` ABC. `MeanReversionStrategy` placeholder implementation.

## Observer / Pub-Sub

- `cryptobot.core.bus.EventBus` with sync/async callbacks, wildcard, filter, history.

## Registry

- `cryptobot.strategies.base.StrategyRegistry` (overwrites duplicates silently).

## Decorator

- `cryptobot.utils.decorators.retry`, `timeout_decorator`, `circuit_breaker`.

## Dataclass + Pydantic boundary

- Pydantic (`config.py`) for external config.
- `dataclass` for internal state, events, metrics.

## Pipeline

- `cryptobot.backtest.engine.BacktestEngine.run(stream)` consumes `AsyncIterator[Event]`.

## Anti-patterns observed

- Global singletons everywhere; no DI container.
- `print(...)` mixed with structlog.
- `Counter` used for PnL (must be `Gauge`).
- `Settings(extra="ignore")` swallows YAML mismatch.
- `market_data.manager.BinanceWSClient` prints status messages.
- `StrategyRegistry.__new__` prints on import.

## Confidence

- High.
