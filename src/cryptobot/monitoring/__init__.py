"""Monitoring package for cryptobot."""

from cryptobot.monitoring import metrics as _metrics

system_info = _metrics.system_info
init_system_info = _metrics.init_system_info

orders_total = _metrics.orders_total
orders_filled = _metrics.orders_filled
orders_rejected = _metrics.orders_rejected
positions_open = _metrics.positions_open
position_size = _metrics.position_size
position_pnl_unrealized = _metrics.position_pnl_unrealized
position_pnl_realized = _metrics.position_pnl_realized
daily_pnl = _metrics.daily_pnl
total_pnl = _metrics.total_pnl
total_equity = _metrics.total_equity
available_balance = _metrics.available_balance
used_margin = _metrics.used_margin
sharpe_ratio = _metrics.sharpe_ratio
sortino_ratio = _metrics.sortino_ratio
max_drawdown = _metrics.max_drawdown
win_rate = _metrics.win_rate
profit_factor = _metrics.profit_factor
risk_exposure_pct = _metrics.risk_exposure_pct
risk_daily_loss_pct = _metrics.risk_daily_loss_pct
risk_drawdown_pct = _metrics.risk_drawdown_pct
risk_kill_switch_active = _metrics.risk_kill_switch_active
risk_correlation = _metrics.risk_correlation
position_concentration = _metrics.position_concentration
market_data_latency = _metrics.market_data_latency
market_data_messages = _metrics.market_data_messages
market_data_gaps = _metrics.market_data_gaps
market_data_staleness = _metrics.market_data_staleness
orderbook_depth = _metrics.orderbook_depth
spread_bps = _metrics.spread_bps
execution_latency = _metrics.execution_latency
execution_slippage = _metrics.execution_slippage
execution_fill_rate = _metrics.execution_fill_rate
execution_retry_count = _metrics.execution_retry_count
strategy_signals = _metrics.strategy_signals
strategy_signal_latency = _metrics.strategy_signal_latency
strategy_active = _metrics.strategy_active
strategy_capital_allocated = _metrics.strategy_capital_allocated
strategy_capital_used = _metrics.strategy_capital_used
ml_inference_latency = _metrics.ml_inference_latency
ml_prediction = _metrics.ml_prediction
ml_model_accuracy = _metrics.ml_model_accuracy
ml_retrain_count = _metrics.ml_retrain_count
ml_feature_importance = _metrics.ml_feature_importance
ml_drift_score = _metrics.ml_drift_score
system_uptime = _metrics.system_uptime
system_memory_usage = _metrics.system_memory_usage
system_cpu_usage = _metrics.system_cpu_usage
system_disk_usage = _metrics.system_disk_usage
connection_status = _metrics.connection_status
connection_latency = _metrics.connection_latency
errors_total = _metrics.errors_total
warnings_total = _metrics.warnings_total
backtest_runs = _metrics.backtest_runs
backtest_duration = _metrics.backtest_duration
backtest_trades = _metrics.backtest_trades
record_order = _metrics.record_order
record_position_update = _metrics.record_position_update
record_pnl = _metrics.record_pnl
record_performance = _metrics.record_performance
record_risk = _metrics.record_risk
record_market_data_latency = _metrics.record_market_data_latency
record_execution_latency = _metrics.record_execution_latency
record_execution_slippage = _metrics.record_execution_slippage
record_strategy_signal = _metrics.record_strategy_signal
record_ml_inference = _metrics.record_ml_inference
record_error = _metrics.record_error
record_warning = _metrics.record_warning
record_connection_status = _metrics.record_connection_status
record_backtest_run = _metrics.record_backtest_run
get_metrics = _metrics.get_metrics
get_metrics_text = _metrics.get_metrics_text
timed = _metrics.timed
MetricsContext = _metrics.MetricsContext
MetricsCollector = _metrics.MetricsCollector
get_metrics_collector = _metrics.get_metrics_collector

from cryptobot.monitoring.dashboard import (
    create_pnl_dashboard,
    create_risk_dashboard,
    create_system_dashboard,
    create_strategy_dashboard,
    create_ml_dashboard,
    create_execution_dashboard,
    create_all_dashboards,
    save_dashboards,
)

from cryptobot.monitoring.alerting import (
    Alert,
    AlertSeverity,
    AlertCategory,
    AlertRule,
    AlertManager,
    NotificationChannel,
    TelegramChannel,
    DiscordChannel,
    EmailChannel,
    PagerDutyChannel,
    get_alert_manager,
    init_alerting,
    shutdown_alerting,
    alert,
    alert_critical,
    alert_emergency,
    resolve_alert,
)

from cryptobot.monitoring.health import (
    HealthStatus,
    ComponentType,
    HealthCheck,
    HealthResult,
    ComponentHealth,
    HealthMonitor,
    HealthChecker,
    ExchangeHealthChecker,
    DataFeedHealthChecker,
    DatabaseHealthChecker,
    CacheHealthChecker,
    RiskEngineHealthChecker,
    StrategyEngineHealthChecker,
    get_health_monitor,
    get_health_checker,
    init_health_monitor,
    shutdown_health_monitor,
    create_standard_checks,
)

__all__ = [
    "system_info", "init_system_info",
    "orders_total", "orders_filled", "orders_rejected",
    "positions_open", "position_size", "position_pnl_unrealized", "position_pnl_realized",
    "daily_pnl", "total_pnl", "total_equity", "available_balance", "used_margin",
    "sharpe_ratio", "sortino_ratio", "max_drawdown", "win_rate", "profit_factor",
    "risk_exposure_pct", "risk_daily_loss_pct", "risk_drawdown_pct",
    "risk_kill_switch_active", "risk_correlation", "position_concentration",
    "market_data_latency", "market_data_messages", "market_data_gaps",
    "market_data_staleness", "orderbook_depth", "spread_bps",
    "execution_latency", "execution_slippage", "execution_fill_rate", "execution_retry_count",
    "strategy_signals", "strategy_signal_latency", "strategy_active",
    "strategy_capital_allocated", "strategy_capital_used",
    "ml_inference_latency", "ml_prediction", "ml_model_accuracy",
    "ml_retrain_count", "ml_feature_importance", "ml_drift_score",
    "system_uptime", "system_memory_usage", "system_cpu_usage", "system_disk_usage",
    "connection_status", "connection_latency",
    "errors_total", "warnings_total",
    "backtest_runs", "backtest_duration", "backtest_trades",
    "record_order", "record_position_update", "record_pnl", "record_performance",
    "record_risk", "record_market_data_latency", "record_execution_latency",
    "record_execution_slippage", "record_strategy_signal", "record_ml_inference",
    "record_error", "record_warning", "record_connection_status", "record_backtest_run",
    "get_metrics", "get_metrics_text", "timed", "MetricsContext",
    "MetricsCollector", "get_metrics_collector",
    "create_pnl_dashboard", "create_risk_dashboard", "create_system_dashboard",
    "create_strategy_dashboard", "create_ml_dashboard", "create_execution_dashboard",
    "create_all_dashboards", "save_dashboards",
    "Alert", "AlertSeverity", "AlertCategory", "AlertRule", "AlertManager",
    "NotificationChannel", "TelegramChannel", "DiscordChannel", "EmailChannel", "PagerDutyChannel",
    "get_alert_manager", "init_alerting", "shutdown_alerting",
    "alert", "alert_critical", "alert_emergency", "resolve_alert",
    "HealthStatus", "ComponentType", "HealthCheck", "HealthResult", "ComponentHealth",
    "HealthMonitor", "HealthChecker", "ExchangeHealthChecker", "DataFeedHealthChecker",
    "DatabaseHealthChecker", "CacheHealthChecker", "RiskEngineHealthChecker",
    "StrategyEngineHealthChecker", "get_health_monitor", "get_health_checker",
    "init_health_monitor", "shutdown_health_monitor", "create_standard_checks",
]
