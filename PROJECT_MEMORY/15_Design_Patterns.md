# 15. Design Patterns

> **Last Updated**: 2026-07-31 (audit v2)
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
- `cryptobot.execution.venue.base.Venue` (abstract) + `SimulatedVenue` (concrete) + `BinanceVenue` (ccxt).
- `cryptobot.execution.engine.build_venue(mode)` selects by `settings.execution.mode`.
- `cryptobot.execution.algorithms.slicer_for(name)` (TWAP/VWAP/POV/IS/Iceberg/arrival/etc).
- `cryptobot.strategies.registry.load_strategies_from_config` instantiates enabled strategies from YAML.

## Strategy

- `cryptobot.strategies.base.BaseStrategy` ABC with 6 concrete subclasses (mean_reversion, trend_following, stat_arb, funding_arb, market_making, ml_strategy).

## Observer / Pub-Sub

- `cryptobot.core.bus.EventBus` with sync/async callbacks, wildcard, filter, history, replay, atomic `publish_batch`.

## Registry

- `cryptobot.strategies.base.StrategyRegistry`.
- `cryptobot.strategies.registry._STRATEGY_REGISTRY_MAP` — name → `(class, config_class)`.
- `cryptobot.execution.venue.base.Venue` registry via `build_venue`.

## Decorator

- `cryptobot.utils.decorators.retry` (jitter clamped to ≥0), `timeout_decorator`, `circuit_breaker` (raises in running loop).

## Dataclass + Pydantic boundary

- Pydantic (`config.py`) for external config (Settings groups).
- `dataclass` for internal state, events, metrics, strategy configs.

## Pipeline

- `cryptobot.backtest.engine.BacktestEngine.run(stream)` consumes `AsyncIterator[Event]`.

## Anti-patterns observed (resolved)

- ~~Global singletons everywhere; no DI container.~~  (still an architectural choice; consider `dependency-injector` later.)
- ~~`print(...)` mixed with structlog~~ — removed from `core/clock.py`, `backtest/engine.py`, `strategies/base.py` (B046/B049 and follow-ups).
- ~~`Counter` used for PnL~~ — replaced with `Gauge` (B025/B037).
- ~~`Settings(extra="ignore")` swallows YAML mismatch~~ — `_flatten_yaml` + `from_yaml_safe` translates nested YAML (B050).
- ~~`market_data.manager.BinanceWSClient` prints status messages~~ — fallback to `default_symbol` + `["1m"]` instead of warning (B044).
- ~~`StrategyRegistry.__new__` prints on import~~ — removed (B049).

## Anti-patterns still observed

- `monitoring/__init__.py` eagerly re-exports `cryptobot.monitoring.metrics` (Prometheus dep at import time) — B051 still Open; importers should use lazy imports where applicable.
- 6 dead empty dirs under `src/cryptobot/` — left in tree.

## Confidence

- High.
