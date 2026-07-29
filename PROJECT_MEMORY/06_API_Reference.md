# 06. API Reference

> **Last Updated**: 2026-07-29 (audit pass)
> **Confidence**: High (verified by reading re-exports).

## Configuration

`cryptobot.config.settings` → `cryptobot.config.Settings` (Pydantic v2 BaseSettings).

```python
from cryptobot.config import settings, get_settings, Settings

settings.app                  # AppSettings
settings.exchange             # ExchangeSettings  (singular; YAML has `exchanges`)
settings.market_data          # MarketDataSettings
settings.risk                 # RiskSettings
settings.execution            # ExecutionSettings
settings.ml                   # MLSettings
settings.xmr                  # XMRSettings
settings.monitoring           # MonitoringSettings
settings.database             # DatabaseSettings
settings.backtest             # BacktestSettings
```

Note: `Settings(extra="ignore")` silently drops unmapped YAML keys; `configs/base.yaml` is not mapped, so loading uses defaults.

## Core

`cryptobot.core.events` re-exports: `Event`, `EventType`, `SignalEvent`, `OrderEvent`, `SignalSide`, `SignalStrength`, `OrderSide`, `OrderType`, `OrderStatus`, `TimeInForce`, `PositionSide`, `TickerEvent`, `OrderBookEvent`, `TradeEvent`, `KlineEvent`, `FundingRateEvent`, `PositionEvent`, `PnLEvent`, `RiskEvent`, `KillSwitchEvent`, `HeartbeatEvent`, `ErrorEvent`, `create_event`.

`cryptobot.core.state`: `StateManager`, `Order`, `Position`, `AccountState`, `state_manager`.

`cryptobot.core.bus`: `EventBus`, `EventBusMode`, `Subscription`, `get_event_bus`, `init_event_bus`, `close_event_bus`.

`cryptobot.core.clock`: `Clock`, `ClockMode`, `ClockConfig`, `RealtimeClock`, `SimulatedClock`, `AcceleratedClock`, `ClockFactory`, `LiveClock`, `BacktestClock`, `get_clock`, `set_clock`, `init_clock`.

`cryptobot.core.portfolio`: `PortfolioManager`, `PortfolioMode`, `StrategyAllocation`, `PortfolioState`, `PositionMetrics`, `get_portfolio_manager`, `init_portfolio_manager`.

## Data

`cryptobot.data` re-exports: `DataSourceConfig`, `DataIngestion`, `BinanceDataIngestion`, `DataIngestionManager`, `get_ingestion_manager`, `OHLCV`, `Tick`, `TradeData`, `StorageConfig`, `StorageBackend`, `TimescaleDBStorage`, `TimescaleStorage`, `ParquetStorage`, `ParquetDataFrameStorage`, `HybridStorage`, `get_storage`, `init_storage`, `shutdown_storage`, `DataQualityIssue`, `QualityReport`, `DataCleaner`, `clean_klines`, `clean_tickers`, `clean_trades`, `validate_ohlcv`, `detect_outliers_zscore`, `fill_missing_bars`.

## Strategies

`cryptobot.strategies`: `BaseStrategy`, `MeanReversionStrategy`, `StrategyRegistry`, `registry`.
`cryptobot.strategies.registry`: `StrategyRegistry`, `registry`.

## Risk

`cryptobot.risk`: `KillSwitch`, `RiskCheckResult`, `RiskLimits`, `RiskManager`, `fixed_fraction_size`, `get_risk_manager`, `kelly_size`, `max_abs_correlation`, `volatility_target_size`.

## Execution

`cryptobot.execution`: `ExecutionEngine`, `SimulatedVenue`, `Venue`, `get_execution_engine`, `pov_quantity`, `twap_slices`, `vwap_slices`.

## Backtest

Public classes: `BacktestEngine`, `BacktestResult`, `TradeRecord`, `FillSimulator`, `FillParams`, `FillResult`, `FillSimulatorFactory`, `PerformanceMetrics`, `BacktestMetricsRecorder`, `BacktestResults`, `ValidationFramework`.

`backtest.engine`: `create_backtest_engine()` returns a `BacktestEngine`.
`backtest.simulator`: `create_fill_simulator(mode)` returns a `FillSimulator`.
`backtest.validation`: `run_validation(backtest_results)`.

## Monitoring

`cryptobot.monitoring` re-exports a large Prometheus surface: counters, gauges, histograms (system, order, position, risk, market data, execution, strategy, ML, connection, errors). Also `MetricsCollector`, `MetricsContext`, `timed`, `record_*` helpers, `get_metrics`, `get_metrics_text`.

Alerting: `Alert`, `AlertSeverity`, `AlertCategory`, `AlertRule`, `AlertManager`, `NotificationChannel`, `TelegramChannel`, `DiscordChannel`, `EmailChannel`, `PagerDutyChannel`, `get_alert_manager`, `init_alerting`, `shutdown_alerting`, `alert`, `alert_critical`, `alert_emergency`, `resolve_alert`.

Health: `HealthStatus`, `ComponentType`, `HealthCheck`, `HealthResult`, `ComponentHealth`, `HealthMonitor`, `HealthChecker`, `ExchangeHealthChecker`, `DataFeedHealthChecker`, `DatabaseHealthChecker`, `CacheHealthChecker`, `RiskEngineHealthChecker`, `StrategyEngineHealthChecker`, `get_health_monitor`, `get_health_checker`, `init_health_monitor`, `shutdown_health_monitor`, `create_standard_checks`.

Dashboard: `create_pnl_dashboard`, `create_risk_dashboard`, `create_system_dashboard`, `create_strategy_dashboard`, `create_ml_dashboard`, `create_execution_dashboard`, `create_all_dashboards`, `save_dashboards`.

## CLI

`cryptobot.cli.main`: `main(argv)`. Subcommands: `backtest`, `validate`, `paper`. All currently placeholder.

## Utils

`cryptobot.utils`: `get_logger`, `setup_logging`, `configure_logging_from_settings`, `LoggerMixin`, `get_correlation_id`, `set_correlation_id`, `clear_correlation_id`, `set_strategy_context`, `set_symbol_context`, `clear_context`, `ContextFilter`, `retry`, `timeout_decorator`, `circuit_breaker`, `CircuitBreaker`, `CircuitBreakerOpenError`, `Candle`, `OrderBookLevel`, `OrderBook`, `Trade`, `TickData`, `OHLCVBar`, `PerformanceMetrics`.

## Confidence

- High: re-export lists.
- Medium: behavior of every exported symbol.
