"""
Grafana Dashboard Generation for Cryptobot.

Generates JSON dashboard definitions for PnL, Risk, System, and Strategy monitoring.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def create_pnl_dashboard() -> dict[str, Any]:
    """Create PnL overview dashboard."""
    return {
        "dashboard": {
            "title": "Cryptobot - PnL Overview",
            "tags": ["cryptobot", "trading", "pnl"],
            "timezone": "utc",
            "refresh": "10s",
            "panels": [
                {
                    "id": 1,
                    "title": "Total Equity",
                    "type": "stat",
                    "gridPos": {"x": 0, "y": 0, "w": 6, "h": 4},
                    "targets": [
                        {
                            "expr": 'cryptobot_total_equity_usd',
                            "legendFormat": "Equity",
                        }
                    ],
                    "fieldConfig": {
                        "defaults": {
                            "unit": "currencyUSD",
                            "thresholds": {
                                "mode": "absolute",
                                "steps": [
                                    {"color": "red", "value": None},
                                    {"color": "yellow", "value": 5000},
                                    {"color": "green", "value": 10000},
                                ],
                            },
                        }
                    },
                },
                {
                    "id": 2,
                    "title": "Daily PnL",
                    "type": "stat",
                    "gridPos": {"x": 6, "y": 0, "w": 6, "h": 4},
                    "targets": [
                        {"expr": 'cryptobot_daily_pnl_usd', "legendFormat": "Daily PnL"}
                    ],
                    "fieldConfig": {
                        "defaults": {
                            "unit": "currencyUSD",
                            "thresholds": {
                                "mode": "absolute",
                                "steps": [
                                    {"color": "red", "value": None},
                                    {"color": "green", "value": 0},
                                ],
                            },
                        }
                    },
                },
                {
                    "id": 3,
                    "title": "Total PnL",
                    "type": "stat",
                    "gridPos": {"x": 12, "y": 0, "w": 6, "h": 4},
                    "targets": [
                        {"expr": 'cryptobot_total_pnl_usd', "legendFormat": "Total PnL"}
                    ],
                    "fieldConfig": {
                        "defaults": {
                            "unit": "currencyUSD",
                            "thresholds": {
                                "mode": "absolute",
                                "steps": [
                                    {"color": "red", "value": None},
                                    {"color": "green", "value": 0},
                                ],
                            },
                        }
                    },
                },
                {
                    "id": 4,
                    "title": "Available Balance / Used Margin",
                    "type": "stat",
                    "gridPos": {"x": 18, "y": 0, "w": 6, "h": 4},
                    "targets": [
                        {"expr": 'cryptobot_available_balance_usd', "legendFormat": "Available"},
                        {"expr": 'cryptobot_used_margin_usd', "legendFormat": "Used Margin"},
                    ],
                    "fieldConfig": {
                        "defaults": {"unit": "currencyUSD"}
                    },
                },
                {
                    "id": 5,
                    "title": "Equity Curve",
                    "type": "timeseries",
                    "gridPos": {"x": 0, "y": 4, "w": 12, "h": 8},
                    "targets": [
                        {"expr": 'cryptobot_total_equity_usd', "legendFormat": "Equity"},
                    ],
                    "fieldConfig": {
                        "defaults": {"unit": "currencyUSD"},
                    },
                },
                {
                    "id": 6,
                    "title": "PnL by Strategy",
                    "type": "barchart",
                    "gridPos": {"x": 12, "y": 4, "w": 12, "h": 8},
                    "targets": [
                        {"expr": 'cryptobot_total_pnl_usd', "legendFormat": "{{strategy}}"},
                    ],
                    "fieldConfig": {
                        "defaults": {"unit": "currencyUSD"},
                    },
                },
                {
                    "id": 7,
                    "title": "Sharpe / Sortino Ratios",
                    "type": "table",
                    "gridPos": {"x": 0, "y": 12, "w": 12, "h": 8},
                    "targets": [
                        {"expr": 'cryptobot_sharpe_ratio', "legendFormat": "Sharpe ({{strategy}})"},
                        {"expr": 'cryptobot_sortino_ratio', "legendFormat": "Sortino ({{strategy}})"},
                    ],
                },
                {
                    "id": 8,
                    "title": "Win Rate / Profit Factor",
                    "type": "table",
                    "gridPos": {"x": 12, "y": 12, "w": 12, "h": 8},
                    "targets": [
                        {"expr": 'cryptobot_win_rate_pct', "legendFormat": "Win Rate ({{strategy}})"},
                        {"expr": 'cryptobot_profit_factor', "legendFormat": "Profit Factor ({{strategy}})"},
                    ],
                },
                {
                    "id": 9,
                    "title": "Max Drawdown",
                    "type": "stat",
                    "gridPos": {"x": 0, "y": 20, "w": 12, "h": 4},
                    "targets": [
                        {"expr": 'cryptobot_max_drawdown_pct', "legendFormat": "{{strategy}}"},
                    ],
                    "fieldConfig": {
                        "defaults": {
                            "unit": "percent",
                            "thresholds": {
                                "mode": "absolute",
                                "steps": [
                                    {"color": "green", "value": None},
                                    {"color": "yellow", "value": 5},
                                    {"color": "red", "value": 10},
                                ],
                            },
                        }
                    },
                },
            ],
        },
        "overwrite": True,
    }


def create_risk_dashboard() -> dict[str, Any]:
    """Create Risk monitoring dashboard."""
    return {
        "dashboard": {
            "title": "Cryptobot - Risk Monitor",
            "tags": ["cryptobot", "risk"],
            "timezone": "utc",
            "refresh": "10s",
            "panels": [
                {
                    "id": 1,
                    "title": "Kill Switch Status",
                    "type": "stat",
                    "gridPos": {"x": 0, "y": 0, "w": 6, "h": 4},
                    "targets": [
                        {"expr": 'cryptobot_risk_kill_switch_active', "legendFormat": "Active"}
                    ],
                    "fieldConfig": {
                        "defaults": {
                            "mappings": [
                                {"type": "value", "options": {"0": {"text": "INACTIVE", "color": "green"}, "1": {"text": "ACTIVE", "color": "red"}}}
                            ],
                            "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": 0}, {"color": "red", "value": 1}]},
                        }
                    },
                },
                {
                    "id": 2,
                    "title": "Portfolio Exposure %",
                    "type": "gauge",
                    "gridPos": {"x": 6, "y": 0, "w": 6, "h": 4},
                    "targets": [
                        {"expr": 'cryptobot_risk_exposure_pct', "legendFormat": "Exposure"}
                    ],
                    "fieldConfig": {
                        "defaults": {
                            "unit": "percent",
                            "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": None}, {"color": "yellow", "value": 60}, {"color": "red", "value": 80}]},
                            "min": 0,
                            "max": 100,
                        }
                    },
                },
                {
                    "id": 3,
                    "title": "Daily Loss %",
                    "type": "gauge",
                    "gridPos": {"x": 12, "y": 0, "w": 6, "h": 4},
                    "targets": [
                        {"expr": 'cryptobot_risk_daily_loss_pct * 100', "legendFormat": "Daily Loss"}
                    ],
                    "fieldConfig": {
                        "defaults": {
                            "unit": "percent",
                            "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": None}, {"color": "yellow", "value": 3}, {"color": "red", "value": 5}]},
                            "min": -20,
                            "max": 5,
                        }
                    },
                },
                {
                    "id": 4,
                    "title": "Current Drawdown %",
                    "type": "gauge",
                    "gridPos": {"x": 18, "y": 0, "w": 6, "h": 4},
                    "targets": [
                        {"expr": 'cryptobot_risk_drawdown_pct * 100', "legendFormat": "Drawdown"}
                    ],
                    "fieldConfig": {
                        "defaults": {
                            "unit": "percent",
                            "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": None}, {"color": "yellow", "value": 5}, {"color": "red", "value": 10}]},
                            "min": 0,
                            "max": 20,
                        }
                    },
                },
                {
                    "id": 5,
                    "title": "Position Concentration",
                    "type": "stat",
                    "gridPos": {"x": 0, "y": 4, "w": 12, "h": 4},
                    "targets": [
                        {"expr": 'cryptobot_position_concentration_pct', "legendFormat": "{{strategy}}"},
                    ],
                    "fieldConfig": {
                        "defaults": {"unit": "percent"},
                    },
                },
                {
                    "id": 6,
                    "title": "Strategy Correlations",
                    "type": "heatmap",
                    "gridPos": {"x": 12, "y": 4, "w": 12, "h": 8},
                    "targets": [
                        {"expr": 'cryptobot_risk_correlation', "format": "heatmap"},
                    ],
                },
                {
                    "id": 7,
                    "title": "Orders Rejected (Rate)",
                    "type": "timeseries",
                    "gridPos": {"x": 0, "y": 8, "w": 12, "h": 8},
                    "targets": [
                        {"expr": 'rate(cryptobot_orders_rejected_total[5m])', "legendFormat": "{{strategy}} - {{reason}}"},
                    ],
                },
                {
                    "id": 8,
                    "title": "Position Limits Utilization",
                    "type": "bargauge",
                    "gridPos": {"x": 12, "y": 12, "w": 12, "h": 8},
                    "targets": [
                        {"expr": 'cryptobot_position_size_usd / cryptobot_total_equity_usd * 100', "legendFormat": "{{strategy}} - {{symbol}}"},
                    ],
                    "fieldConfig": {
                        "defaults": {"unit": "percent", "max": 20},
                    },
                },
            ],
        },
        "overwrite": True,
    }


def create_system_dashboard() -> dict[str, Any]:
    """Create System health dashboard."""
    return {
        "dashboard": {
            "title": "Cryptobot - System Health",
            "tags": ["cryptobot", "system", "health"],
            "timezone": "utc",
            "refresh": "10s",
            "panels": [
                {
                    "id": 1,
                    "title": "System Uptime",
                    "type": "stat",
                    "gridPos": {"x": 0, "y": 0, "w": 6, "h": 4},
                    "targets": [
                        {"expr": 'cryptobot_system_uptime_seconds / 86400', "legendFormat": "Days"}
                    ],
                    "fieldConfig": {"defaults": {"unit": "ds"}},
                },
                {
                    "id": 2,
                    "title": "CPU Usage",
                    "type": "gauge",
                    "gridPos": {"x": 6, "y": 0, "w": 6, "h": 4},
                    "targets": [
                        {"expr": 'cryptobot_system_cpu_percent', "legendFormat": "CPU"}
                    ],
                    "fieldConfig": {
                        "defaults": {"unit": "percent", "min": 0, "max": 100, "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": None}, {"color": "yellow", "value": 70}, {"color": "red", "value": 90}]}},
                    },
                },
                {
                    "id": 3,
                    "title": "Memory Usage",
                    "type": "gauge",
                    "gridPos": {"x": 12, "y": 0, "w": 6, "h": 4},
                    "targets": [
                        {"expr": 'cryptobot_system_memory_bytes{type="used"} / cryptobot_system_memory_bytes{type="total"} * 100', "legendFormat": "Memory %"}
                    ],
                    "fieldConfig": {
                        "defaults": {"unit": "percent", "min": 0, "max": 100, "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": None}, {"color": "yellow", "value": 80}, {"color": "red", "value": 95}]}},
                    },
                },
                {
                    "id": 4,
                    "title": "Disk Usage",
                    "type": "gauge",
                    "gridPos": {"x": 18, "y": 0, "w": 6, "h": 4},
                    "targets": [
                        {"expr": 'cryptobot_system_disk_percent', "legendFormat": "{{mount}}"}
                    ],
                    "fieldConfig": {"defaults": {"unit": "percent", "min": 0, "max": 100}},
                },
                {
                    "id": 5,
                    "title": "Connection Status",
                    "type": "stat",
                    "gridPos": {"x": 0, "y": 4, "w": 12, "h": 4},
                    "targets": [
                        {"expr": 'cryptobot_connection_status', "legendFormat": "{{component}} - {{endpoint}}"},
                    ],
                    "fieldConfig": {
                        "defaults": {
                            "mappings": [{"type": "value", "options": {"0": {"text": "DISCONNECTED", "color": "red"}, "1": {"text": "CONNECTED", "color": "green"}}}],
                        }
                    },
                },
                {
                    "id": 6,
                    "title": "Connection Latency (p95)",
                    "type": "timeseries",
                    "gridPos": {"x": 12, "y": 4, "w": 12, "h": 8},
                    "targets": [
                        {"expr": 'histogram_quantile(0.95, rate(cryptobot_connection_latency_seconds_bucket[5m]))', "legendFormat": "{{component}} - {{endpoint}}"},
                    ],
                    "fieldConfig": {"defaults": {"unit": "s"}},
                },
                {
                    "id": 7,
                    "title": "Errors Rate (5m)",
                    "type": "timeseries",
                    "gridPos": {"x": 0, "y": 8, "w": 12, "h": 8},
                    "targets": [
                        {"expr": 'rate(cryptobot_errors_total[5m])', "legendFormat": "{{component}} - {{error_type}}"},
                    ],
                },
                {
                    "id": 8,
                    "title": "Warnings Rate (5m)",
                    "type": "timeseries",
                    "gridPos": {"x": 12, "y": 12, "w": 12, "h": 8},
                    "targets": [
                        {"expr": 'rate(cryptobot_warnings_total[5m])', "legendFormat": "{{component}} - {{warning_type}}"},
                    ],
                },
                {
                    "id": 9,
                    "title": "Market Data Latency (p99)",
                    "type": "timeseries",
                    "gridPos": {"x": 0, "y": 16, "w": 12, "h": 8},
                    "targets": [
                        {"expr": 'histogram_quantile(0.99, rate(cryptobot_market_data_latency_seconds_bucket[5m]))', "legendFormat": "{{source}} - {{symbol}}"},
                    ],
                    "fieldConfig": {"defaults": {"unit": "s"}},
                },
                {
                    "id": 10,
                    "title": "Market Data Gaps",
                    "type": "stat",
                    "gridPos": {"x": 12, "y": 16, "w": 12, "h": 4},
                    "targets": [
                        {"expr": 'increase(cryptobot_market_data_gaps_total[1h])', "legendFormat": "{{source}} - {{symbol}}"},
                    ],
                },
            ],
        },
        "overwrite": True,
    }


def create_strategy_dashboard() -> dict[str, Any]:
    """Create Strategy performance dashboard."""
    return {
        "dashboard": {
            "title": "Cryptobot - Strategy Performance",
            "tags": ["cryptobot", "strategy"],
            "timezone": "utc",
            "refresh": "10s",
            "panels": [
                {
                    "id": 1,
                    "title": "Active Strategies",
                    "type": "table",
                    "gridPos": {"x": 0, "y": 0, "w": 12, "h": 8},
                    "targets": [
                        {"expr": 'cryptobot_strategy_active', "legendFormat": "{{strategy}}"},
                    ],
                    "fieldConfig": {
                        "defaults": {
                            "mappings": [{"type": "value", "options": {"0": {"text": "INACTIVE", "color": "red"}, "1": {"text": "ACTIVE", "color": "green"}}}],
                        }
                    },
                },
                {
                    "id": 2,
                    "title": "Capital Allocation",
                    "type": "piechart",
                    "gridPos": {"x": 12, "y": 0, "w": 12, "h": 8},
                    "targets": [
                        {"expr": 'cryptobot_strategy_capital_allocated_usd', "legendFormat": "{{strategy}}"},
                    ],
                },
                {
                    "id": 3,
                    "title": "Capital Used vs Allocated",
                    "type": "bargauge",
                    "gridPos": {"x": 0, "y": 8, "w": 12, "h": 8},
                    "targets": [
                        {"expr": 'cryptobot_strategy_capital_allocated_usd', "legendFormat": "{{strategy}} Allocated"},
                        {"expr": 'cryptobot_strategy_capital_used_usd', "legendFormat": "{{strategy}} Used"},
                    ],
                },
                {
                    "id": 4,
                    "title": "Signals Generated (Rate)",
                    "type": "timeseries",
                    "gridPos": {"x": 12, "y": 8, "w": 12, "h": 8},
                    "targets": [
                        {"expr": 'rate(cryptobot_strategy_signals_total[5m])', "legendFormat": "{{strategy}} - {{signal_type}}"},
                    ],
                },
                {
                    "id": 5,
                    "title": "Signal Latency (p95)",
                    "type": "timeseries",
                    "gridPos": {"x": 0, "y": 16, "w": 12, "h": 8},
                    "targets": [
                        {"expr": 'histogram_quantile(0.95, rate(cryptobot_strategy_signal_latency_seconds_bucket[5m]))', "legendFormat": "{{strategy}}"},
                    ],
                    "fieldConfig": {"defaults": {"unit": "s"}},
                },
            ],
        },
        "overwrite": True,
    }


def create_ml_dashboard() -> dict[str, Any]:
    """Create ML monitoring dashboard."""
    return {
        "dashboard": {
            "title": "Cryptobot - ML Pipeline",
            "tags": ["cryptobot", "ml"],
            "timezone": "utc",
            "refresh": "30s",
            "panels": [
                {
                    "id": 1,
                    "title": "Inference Latency (p99)",
                    "type": "timeseries",
                    "gridPos": {"x": 0, "y": 0, "w": 12, "h": 8},
                    "targets": [
                        {"expr": 'histogram_quantile(0.99, rate(cryptobot_ml_inference_latency_seconds_bucket[5m]))', "legendFormat": "{{model}} - {{type}}"},
                    ],
                    "fieldConfig": {"defaults": {"unit": "s", "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": None}, {"color": "yellow", "value": 0.01}, {"color": "red", "value": 0.05}]}}},
                },
                {
                    "id": 2,
                    "title": "Model Accuracy",
                    "type": "stat",
                    "gridPos": {"x": 12, "y": 0, "w": 12, "h": 4},
                    "targets": [
                        {"expr": 'cryptobot_ml_model_accuracy', "legendFormat": "{{model}} - {{type}}"},
                    ],
                    "fieldConfig": {"defaults": {"unit": "percent", "thresholds": {"mode": "absolute", "steps": [{"color": "red", "value": None}, {"color": "yellow", "value": 50}, {"color": "green", "value": 55}]}}},
                },
                {
                    "id": 3,
                    "title": "Retrain Events",
                    "type": "timeseries",
                    "gridPos": {"x": 12, "y": 4, "w": 12, "h": 8},
                    "targets": [
                        {"expr": 'rate(cryptobot_ml_retrain_total[1h])', "legendFormat": "{{model}} - {{trigger}}"},
                    ],
                },
                {
                    "id": 4,
                    "title": "Prediction Distribution",
                    "type": "heatmap",
                    "gridPos": {"x": 0, "y": 8, "w": 12, "h": 8},
                    "targets": [
                        {"expr": 'rate(cryptobot_ml_prediction_bucket[5m])', "format": "heatmap"},
                    ],
                },
                {
                    "id": 5,
                    "title": "Feature Importance",
                    "type": "table",
                    "gridPos": {"x": 12, "y": 12, "w": 12, "h": 8},
                    "targets": [
                        {"expr": 'cryptobot_ml_feature_importance', "legendFormat": "{{model}} - {{feature}}"},
                    ],
                },
                {
                    "id": 6,
                    "title": "Drift Scores",
                    "type": "timeseries",
                    "gridPos": {"x": 0, "y": 16, "w": 12, "h": 8},
                    "targets": [
                        {"expr": 'cryptobot_ml_drift_score', "legendFormat": "{{model}} - {{feature}}"},
                    ],
                    "fieldConfig": {"defaults": {"thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": None}, {"color": "yellow", "value": 0.1}, {"color": "red", "value": 0.2}]}}},
                },
            ],
        },
        "overwrite": True,
    }


def create_execution_dashboard() -> dict[str, Any]:
    """Create Execution quality dashboard."""
    return {
        "dashboard": {
            "title": "Cryptobot - Execution Quality",
            "tags": ["cryptobot", "execution"],
            "timezone": "utc",
            "refresh": "10s",
            "panels": [
                {
                    "id": 1,
                    "title": "Execution Latency (p95)",
                    "type": "timeseries",
                    "gridPos": {"x": 0, "y": 0, "w": 12, "h": 8},
                    "targets": [
                        {"expr": 'histogram_quantile(0.95, rate(cryptobot_execution_latency_seconds_bucket[5m]))', "legendFormat": "{{venue}} - {{symbol}} - {{order_type}}"},
                    ],
                    "fieldConfig": {"defaults": {"unit": "s"}},
                },
                {
                    "id": 2,
                    "title": "Slippage (bps, p95)",
                    "type": "timeseries",
                    "gridPos": {"x": 12, "y": 0, "w": 12, "h": 8},
                    "targets": [
                        {"expr": 'histogram_quantile(0.95, rate(cryptobot_execution_slippage_bps_bucket[5m]))', "legendFormat": "{{venue}} - {{symbol}} - {{side}}"},
                    ],
                    "fieldConfig": {"defaults": {"unit": "bps"}},
                },
                {
                    "id": 3,
                    "title": "Fill Rate %",
                    "type": "stat",
                    "gridPos": {"x": 0, "y": 8, "w": 12, "h": 4},
                    "targets": [
                        {"expr": 'cryptobot_execution_fill_rate_pct', "legendFormat": "{{venue}} - {{symbol}}"},
                    ],
                    "fieldConfig": {"defaults": {"unit": "percent"}},
                },
                {
                    "id": 4,
                    "title": "Retry Rate",
                    "type": "timeseries",
                    "gridPos": {"x": 12, "y": 8, "w": 12, "h": 8},
                    "targets": [
                        {"expr": 'rate(cryptobot_execution_retry_total[5m])', "legendFormat": "{{venue}} - {{symbol}} - {{reason}}"},
                    ],
                },
            ],
        },
        "overwrite": True,
    }


def create_all_dashboards() -> list[dict[str, Any]]:
    """Generate all dashboards."""
    return [
        create_pnl_dashboard(),
        create_risk_dashboard(),
        create_system_dashboard(),
        create_strategy_dashboard(),
        create_ml_dashboard(),
        create_execution_dashboard(),
    ]


def save_dashboards(output_dir: str = "/app/grafana/dashboards") -> list[str]:
    """Save all dashboards to JSON files. Returns list of written paths."""
    import os
    os.makedirs(output_dir, exist_ok=True)

    written: list[str] = []
    for db in create_all_dashboards():
        title = db["dashboard"]["title"].replace(" - ", "_").replace(" ", "_").lower()
        filepath = os.path.join(output_dir, f"{title}.json")
        with open(filepath, "w") as f:
            json.dump(db, f, indent=2)
        written.append(filepath)
        logger.info("Saved: %s", filepath)
    return written


if __name__ == "__main__":
    save_dashboards()
