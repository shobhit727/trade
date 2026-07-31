"""Monitoring package for cryptobot.

Re-exports from ``cryptobot.monitoring.{metrics, alerting, dashboard,
health}``. Each submodule's import is deferred via ``__getattr__`` so
``import cryptobot.monitoring`` succeeds even when optional dependencies
(prometheus_client, aiohttp) aren't installed; the missing package is
only surfaced when a specific symbol is actually accessed.
"""

from __future__ import annotations

from typing import Any

_METRICS_EXPORTS = {
    "system_info",
    "init_system_info",
    "orders_total",
    "orders_filled",
    "orders_rejected",
    "positions_open",
    "position_size",
    "position_pnl_unrealized",
    "position_pnl_realized",
    "daily_pnl",
    "total_pnl",
    "total_equity",
    "available_balance",
    "used_margin",
    "sharpe_ratio",
    "sortino_ratio",
    "max_drawdown",
    "win_rate",
    "profit_factor",
    "risk_exposure_pct",
    "risk_daily_loss_pct",
    "risk_drawdown_pct",
    "risk_kill_switch_active",
    "risk_correlation",
    "position_concentration",
    "market_data_latency",
    "market_data_messages",
    "market_data_gaps",
    "market_data_staleness",
    "orderbook_depth",
    "spread_bps",
    "execution_latency",
    "execution_slippage",
    "execution_fill_rate",
    "execution_retry_count",
    "strategy_signals",
    "strategy_signal_latency",
    "strategy_active",
    "strategy_capital_allocated",
    "strategy_capital_used",
    "ml_inference_latency",
    "ml_prediction",
    "ml_model_accuracy",
    "ml_retrain_count",
    "ml_feature_importance",
    "ml_drift_score",
    "system_uptime",
    "system_memory_usage",
    "system_cpu_usage",
    "system_disk_usage",
    "connection_status",
    "connection_latency",
    "errors_total",
    "warnings_total",
    "backtest_runs",
    "backtest_duration",
    "backtest_trades",
    "record_order",
    "record_position_update",
    "record_pnl",
    "record_performance",
    "record_risk",
    "record_market_data_latency",
    "record_execution_latency",
    "record_execution_slippage",
    "record_venue_quote_latency",
    "record_routing_decision",
    "record_strategy_signal",
    "record_ml_inference",
    "record_error",
    "record_warning",
    "record_connection_status",
    "record_backtest_run",
    "get_metrics",
    "get_metrics_text",
    "timed",
    "MetricsContext",
    "MetricsCollector",
    "get_metrics_collector",
}

_DASHBOARD_EXPORTS = {
    "create_pnl_dashboard",
    "create_risk_dashboard",
    "create_system_dashboard",
    "create_strategy_dashboard",
    "create_ml_dashboard",
    "create_execution_dashboard",
    "create_all_dashboards",
    "save_dashboards",
}

_ALERTING_EXPORTS = {
    "Alert",
    "AlertSeverity",
    "AlertCategory",
    "AlertRule",
    "AlertManager",
    "NotificationChannel",
    "TelegramChannel",
    "DiscordChannel",
    "EmailChannel",
    "PagerDutyChannel",
    "get_alert_manager",
    "init_alerting",
    "shutdown_alerting",
    "alert",
    "alert_critical",
    "alert_emergency",
    "resolve_alert",
}

_HEALTH_EXPORTS = {
    "HealthStatus",
    "ComponentType",
    "HealthCheck",
    "HealthResult",
    "ComponentHealth",
    "HealthMonitor",
    "HealthChecker",
    "ExchangeHealthChecker",
    "DataFeedHealthChecker",
    "DatabaseHealthChecker",
    "CacheHealthChecker",
    "RiskEngineHealthChecker",
    "StrategyEngineHealthChecker",
    "get_health_monitor",
    "get_health_checker",
    "init_health_monitor",
    "shutdown_health_monitor",
    "create_standard_checks",
}


def __getattr__(name: str) -> Any:
    if name in _METRICS_EXPORTS:
        from cryptobot.monitoring import metrics as _metrics

        value = getattr(_metrics, name)
        globals()[name] = value
        return value
    if name in _DASHBOARD_EXPORTS:
        from cryptobot.monitoring import dashboard as _dashboard

        value = getattr(_dashboard, name)
        globals()[name] = value
        return value
    if name in _ALERTING_EXPORTS:
        from cryptobot.monitoring import alerting as _alerting

        value = getattr(_alerting, name)
        globals()[name] = value
        return value
    if name in _HEALTH_EXPORTS:
        from cryptobot.monitoring import health as _health

        value = getattr(_health, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = sorted(
    _METRICS_EXPORTS | _DASHBOARD_EXPORTS | _ALERTING_EXPORTS | _HEALTH_EXPORTS
)
