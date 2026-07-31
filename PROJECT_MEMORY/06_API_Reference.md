# 06. API Reference

> **Last Updated**: 2026-07-31 (audit v2)
> **Confidence**: High (verified by reading re-exports).

## Configuration

`cryptobot.config.settings` → `cryptobot.config.Settings` (Pydantic v2 BaseSettings).

```python
from cryptobot.config import settings, get_settings, Settings

Settings.from_yaml_safe("configs/base.yaml")   # preferred (uses _flatten_yaml)
Settings.from_yaml("configs/base.yaml")        # legacy direct spread
```

`Settings(extra="ignore")` silently drops unmapped YAML keys; `Settings.from_yaml_safe` translates the nested YAML (e.g. `exchanges.binance.*`, `monitoring.alerts.*`, `xmr.*`) to flat Settings field names, so `configs/base.yaml` is honored as-is.

| Setting group | Env prefix | Highlight fields |
|---|---|---|
| `app` | `APP_` | name, env, log_level, timezone |
| `exchange` | `BINANCE_` | enabled, testnet, api_key, api_secret, base_url, ws_url, rate_limit, symbols, default_symbol, timeframes, max_positions, position_size_pct |
| `market_data` | `MARKET_DATA_` | buffer_size, orderbook_depth, redis_host/port/db/max_connections, update_interval_ms, cache_ttl_seconds |
| `risk` | `RISK_` | max_*_pct, kill_switch_*, position_sizing, kelly_fraction, volatility_target, min/max_order_size_usd |
| `execution` | `EXECUTION_` | mode (paper/binance/testnet), smart_routing, order_type, limit_offset_bps, ioc_timeout_ms, max_slippage_bps |
| `ml` | `ML_` | enabled, inference_mode, model_path, features, min_samples_train, feature_lookback |
| `xmr` | `XMR_` | enabled, daemon_*/wallet_*, funding_* |
| `monitoring` | `MONITORING_` | prometheus_enabled/port, grafana_enabled/port, telegram_*, discord_webhook, email_enabled, health_check_interval |
| `database` | `DB_` | type, host, port, name, user, password, pool_size, max_overflow |
| `backtest` | `BACKTEST_` | enabled, start_date, end_date, initial_capital, commission_bps, slippage_bps, funding_rate_included |

## Core

`cryptobot.core.events` re-exports: `Event`, `EventType`, `SignalEvent`, `OrderEvent`, `SignalSide`, `SignalStrength`, `OrderSide`, `OrderType`, `OrderStatus`, `TimeInForce`, `PositionSide`, `TickerEvent`, `OrderBookEvent`, `TradeEvent`, `KlineEvent`, `FundingRateEvent`, `PositionEvent`, `PnLEvent`, `RiskEvent`, `KillSwitchEvent`, `HeartbeatEvent`, `ErrorEvent`, `create_event`.

`cryptobot.core.state`: `StateManager`, `Order`, `Position`, `AccountState`, `state_manager`. DB path resolves to `/app/data/cryptobot.db` when that mount exists (B069).

`cryptobot.core.bus`: `EventBus`, `EventBusMode`, `Subscription`, `get_event_bus`, `init_event_bus`, `close_event_bus`. `publish_batch` dispatches atomically under single lock (B045).

`cryptobot.core.clock`: `Clock`, `ClockMode`, `ClockConfig`, `RealtimeClock`, `SimulatedClock`, `AcceleratedClock`, `ClockFactory`, `LiveClock`, `BacktestClock`, `get_clock`, `set_clock`, `init_clock`.

`cryptobot.core.portfolio`: `PortfolioManager`, `PortfolioMode`, `StrategyAllocation`, `PortfolioState`, `PositionMetrics`, `get_portfolio_manager`, `init_portfolio_manager`. `update_equity` auto-resets daily PnL on UTC day boundary (B034).

## Data

`cryptobot.data` re-exports: `DataSourceConfig`, `DataIngestion`, `BinanceDataIngestion`, `DataIngestionManager`, `get_ingestion_manager`, `OHLCV`, `Tick`, `TradeData`, `StorageConfig`, `StorageBackend`, `TimescaleDBStorage`, `TimescaleStorage`, `ParquetStorage`, `ParquetDataFrameStorage`, `HybridStorage`, `get_storage`, `init_storage`, `shutdown_storage`, `DataQualityIssue`, `QualityReport`, `DataCleaner`, `clean_klines`, `clean_tickers`, `clean_trades`, `validate_ohlcv`, `detect_outliers_zscore`, `fill_missing_bars`.

`cryptobot.data.features` (re-export of `cryptobot.ml.features`): `build_features`, `future_returns`, `compute_returns`, `compute_rsi`, `compute_macd`, `compute_atr_ratio`, `compute_bollinger`, `compute_log_volume`.

## Strategies

`cryptobot.strategies`: all six concrete strategies + configs.

```python
from cryptobot.strategies import (
    BaseStrategy, StrategyRegistry, registry,
    MeanReversionStrategy, MeanReversionConfig,
    TrendFollowingStrategy, TrendFollowingConfig,
    StatArbStrategy, StatArbConfig,
    FundingArbStrategy, FundingArbConfig,
    MarketMakingStrategy, MarketMakingConfig,
    MLStrategy, MLStrategyConfig,
)
```

`cryptobot.strategies.registry`: `load_strategies_from_config(strategies_cfg, enabled_names=None)` — auto-instantiates enabled strategies by name. Internal `_STRATEGY_REGISTRY_MAP` maps name → `(class, config_class)`.

## Risk

`cryptobot.risk`: `KillSwitch`, `RiskCheckResult`, `RiskLimits`, `RiskManager`, `fixed_fraction_size`, `get_risk_manager`, `kelly_size`, `max_abs_correlation`, `volatility_target_size`.

## Execution

`cryptobot.execution`: `ExecutionEngine`, `SimulatedVenue`, `Venue`, `build_venue`, `get_execution_engine`, plus `pov_quantity`, `twap_slices`, `vwap_slices`, `vwap_schedule`, `slicer_for`, `implementation_shortfall`, `iceberg`, `liquidity_seek`, `arrival_price`.

`cryptobot.execution.router`: `SmartOrderRouter`, `RankByPrice`, `RankByLatency`, `route` method (best venue or split).

`cryptobot.execution.adverse_selection`: `AdverseSelectionGuard`, `QueuePosition`, `TopOfBook`, `attach_to_engine`.

`cryptobot.execution.venue.binance`: `BinanceVenue` (ccxt.async_support; sandbox, retries, guards).

## Backtest

Public classes: `BacktestEngine`, `BacktestResult`, `TradeRecord`, `FillSimulator`, `FillParams`, `FillResult`, `FillSimulatorFactory`, `PerformanceMetrics`, `BacktestMetricsRecorder`, `BacktestResults`, `ValidationFramework`, `OhlcvBar`, `OhlcvDataset`, `load_csv`, `load_parquet`, `load_timescale`, `generate_synthetic_ohlcv`, `run_backtest`.

`backtest.engine`: `create_backtest_engine()` returns a `BacktestEngine`.
`backtest.simulator`: `create_fill_simulator(mode)` returns a `FillSimulator`.
`backtest.validation`: `run_validation(backtest_results)` returns full report with walk-forward, Monte Carlo, and deflated-Sharpe sections.
`backtest.reporting`: `generate_html_report(result) -> str` (HTML tearsheet, stdlib only).

## Monitoring

`cryptobot.monitoring` re-exports a large Prometheus surface: counters, gauges, histograms (system, order, position, risk, market data, execution, strategy, ML, connection, errors). Also `MetricsCollector`, `MetricsContext`, `timed`, `record_*` helpers, `get_metrics`, `get_metrics_text`. `total_pnl` is a `Gauge`.

Alerting: `Alert`, `AlertSeverity`, `AlertCategory`, `AlertRule`, `AlertManager`, `NotificationChannel`, `TelegramChannel`, `DiscordChannel`, `EmailChannel`, `PagerDutyChannel`, `get_alert_manager`, `init_alerting` (no-op when no channels), `shutdown_alerting`, `alert`, `alert_critical`, `alert_emergency`, `resolve_alert`.

Health: `HealthStatus`, `ComponentType`, `HealthCheck`, `HealthResult`, `ComponentHealth`, `HealthMonitor`, `HealthChecker`, `ExchangeHealthChecker`, `DataFeedHealthChecker`, `DatabaseHealthChecker`, `CacheHealthChecker`, `RiskEngineHealthChecker`, `StrategyEngineHealthChecker`, `get_health_monitor`, `get_health_checker`, `init_health_monitor`, `shutdown_health_monitor`, `create_standard_checks`. Runtime: `unregister_check`, `update_check_interval`, `get_check`.

Dashboard: `create_pnl_dashboard`, `create_risk_dashboard`, `create_system_dashboard`, `create_strategy_dashboard`, `create_ml_dashboard`, `create_execution_dashboard`, `create_all_dashboards`, `save_dashboards`.

## ML

`cryptobot.ml`: `build_features`, `future_returns`, `compute_returns`, `compute_rsi`, `compute_macd`, `compute_atr_ratio`, `compute_bollinger`, `compute_log_volume`, `DirectionClassifier`, `DirectionConfig`, `WalkForwardTrainer`, `DriftDetector`.

## CLI

`cryptobot.cli.main`: `main(argv)`. Subcommands: `validate`, `paper`, `bot`, `serve`. Each has real wiring (no print-and-exit placeholders). `serve` starts `utils.health_server.HealthServer`.

## Utils

`cryptobot.utils`: `get_logger`, `setup_logging`, `configure_logging_from_settings`, `LoggerMixin`, `get_correlation_id`, `set_correlation_id`, `clear_correlation_id`, `set_strategy_context`, `set_symbol_context`, `clear_context`, `ContextFilter`, `retry`, `timeout_decorator`, `circuit_breaker`, `CircuitBreaker`, `CircuitBreakerOpenError`, `Candle`, `OrderBookLevel`, `OrderBook`, `Trade`, `TickData`, `OHLCVBar`, `PerformanceMetrics`, `HealthServer`, `start_health_server`, `stop_health_server`.

## Confidence

- High: re-export lists.
- Medium: behavior of every exported symbol.
