"""
Prometheus metrics for the trading system.

Provides counters, histograms, and gauges for monitoring
trading performance, system health, and risk metrics.

When ``prometheus_client`` is not installed, ``PROMETHEUS_AVAILABLE`` is
``False`` and every metric object below is replaced with a no-op stub
whose ``.inc``/``.set``/``.observe``/``.labels`` etc. are harmless
no-ops. This keeps ``import cryptobot.monitoring`` and submodule
imports cheap when the binary is run in environments without the
optional dependency (e.g. a slim test container).
"""

from __future__ import annotations

try:
    from prometheus_client import (
        Counter as _RealCounter,
        Gauge as _RealGauge,
        Histogram as _RealHistogram,
        Info as _RealInfo,
        CollectorRegistry as _RealCollectorRegistry,
        generate_latest as _real_generate_latest,
    )
    PROMETHEUS_AVAILABLE = True
except Exception:
    PROMETHEUS_AVAILABLE = False

    class _NoOpLabels:
        def __getattr__(self, _name):
            return lambda *_a, **_kw: None

    class _NoOpMetric:
        def __init__(self, *_a, **_kw):
            pass

        def labels(self, *_a, **_kw):
            return _NoOpLabels()

        def inc(self, *_a, **_kw):
            return None

        def dec(self, *_a, **_kw):
            return None

        def set(self, *_a, **_kw):
            return None

        def observe(self, *_a, **_kw):
            return None

        def time(self):
            from contextlib import nullcontext

            return nullcontext()

        def info(self, *_a, **_kw):
            return None

    class _NoOpRegistry:
        def __init__(self, *_a, **_kw):
            pass

    _RealCounter = _RealGauge = _RealHistogram = _RealInfo = _NoOpMetric
    _RealCollectorRegistry = _NoOpRegistry

    def _real_generate_latest(_registry):
        return b""


if PROMETHEUS_AVAILABLE:
    Counter = _RealCounter
    Gauge = _RealGauge
    Histogram = _RealHistogram
    Info = _RealInfo
    CollectorRegistry = _RealCollectorRegistry
    generate_latest = _real_generate_latest
else:
    Counter = _NoOpMetric
    Gauge = _NoOpMetric
    Histogram = _NoOpMetric
    Info = _NoOpMetric
    CollectorRegistry = _NoOpRegistry

    def generate_latest(_registry):
        return b""


from cryptobot.config import settings


# Create custom registry for isolation
registry = CollectorRegistry()

# =============================================================================
# System Info
# =============================================================================

system_info = Info(
    "cryptobot_system_info",
    "Cryptobot system information",
    registry=registry,
)

# =============================================================================
# Trading Metrics
# =============================================================================

# Order metrics
orders_total = Counter(
    "cryptobot_orders_total",
    "Total number of orders placed",
    ["strategy", "symbol", "side", "type", "status"],
    registry=registry,
)

orders_filled = Counter(
    "cryptobot_orders_filled_total",
    "Total number of orders filled",
    ["strategy", "symbol", "side"],
    registry=registry,
)

orders_rejected = Counter(
    "cryptobot_orders_rejected_total",
    "Total number of orders rejected",
    ["strategy", "symbol", "reason"],
    registry=registry,
)

# Position metrics
positions_open = Gauge(
    "cryptobot_positions_open",
    "Number of currently open positions",
    ["strategy", "symbol", "side"],
    registry=registry,
)

position_size = Gauge(
    "cryptobot_position_size_usd",
    "Current position size in USD",
    ["strategy", "symbol", "side"],
    registry=registry,
)

position_pnl_unrealized = Gauge(
    "cryptobot_position_pnl_unrealized_usd",
    "Unrealized PnL for open positions in USD",
    ["strategy", "symbol"],
    registry=registry,
)

position_pnl_realized = Gauge(
    "cryptobot_position_pnl_realized_usd",
    "Realized PnL in USD per strategy/symbol (signed)",
    ["strategy", "symbol"],
    registry=registry,
)

# PnL metrics
daily_pnl = Gauge(
    "cryptobot_daily_pnl_usd",
    "Daily PnL in USD",
    ["strategy"],
    registry=registry,
)

total_pnl = Gauge(
    "cryptobot_total_pnl_usd",
    "Total PnL in USD (realized + unrealized)",
    ["strategy"],
    registry=registry,
)

total_equity = Gauge(
    "cryptobot_total_equity_usd",
    "Total portfolio equity in USD",
    registry=registry,
)

available_balance = Gauge(
    "cryptobot_available_balance_usd",
    "Available balance in USD",
    registry=registry,
)

used_margin = Gauge(
    "cryptobot_used_margin_usd",
    "Used margin in USD",
    registry=registry,
)

# Performance metrics
sharpe_ratio = Gauge(
    "cryptobot_sharpe_ratio",
    "Strategy Sharpe ratio",
    ["strategy", "period"],
    registry=registry,
)

sortino_ratio = Gauge(
    "cryptobot_sortino_ratio",
    "Strategy Sortino ratio",
    ["strategy", "period"],
    registry=registry,
)

max_drawdown = Gauge(
    "cryptobot_max_drawdown_pct",
    "Maximum drawdown as percentage",
    ["strategy"],
    registry=registry,
)

win_rate = Gauge(
    "cryptobot_win_rate_pct",
    "Strategy win rate percentage",
    ["strategy"],
    registry=registry,
)

profit_factor = Gauge(
    "cryptobot_profit_factor",
    "Strategy profit factor (gross profit / gross loss)",
    ["strategy"],
    registry=registry,
)

# =============================================================================
# Risk Metrics
# =============================================================================

risk_exposure_pct = Gauge(
    "cryptobot_risk_exposure_pct",
    "Current portfolio exposure as percentage of equity",
    ["strategy"],
    registry=registry,
)

risk_daily_loss_pct = Gauge(
    "cryptobot_risk_daily_loss_pct",
    "Daily loss as percentage of equity",
    ["strategy"],
    registry=registry,
)

risk_drawdown_pct = Gauge(
    "cryptobot_risk_drawdown_pct",
    "Current drawdown as percentage of peak equity",
    registry=registry,
)

risk_kill_switch_active = Gauge(
    "cryptobot_risk_kill_switch_active",
    "Whether kill switch is active (1) or not (0)",
    registry=registry,
)

risk_correlation = Gauge(
    "cryptobot_risk_correlation",
    "Correlation between strategy positions",
    ["strategy_a", "strategy_b"],
    registry=registry,
)

position_concentration = Gauge(
    "cryptobot_position_concentration_pct",
    "Largest position as percentage of equity",
    ["strategy"],
    registry=registry,
)

# =============================================================================
# Market Data Metrics
# =============================================================================

market_data_latency = Histogram(
    "cryptobot_market_data_latency_seconds",
    "Market data processing latency",
    ["source", "symbol", "type"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
    registry=registry,
)

market_data_messages = Counter(
    "cryptobot_market_data_messages_total",
    "Total market data messages received",
    ["source", "symbol", "type"],
    registry=registry,
)

market_data_gaps = Counter(
    "cryptobot_market_data_gaps_total",
    "Detected gaps in market data sequence",
    ["source", "symbol"],
    registry=registry,
)

market_data_staleness = Gauge(
    "cryptobot_market_data_staleness_seconds",
    "Seconds since last market data update",
    ["source", "symbol"],
    registry=registry,
)

orderbook_depth = Gauge(
    "cryptobot_orderbook_depth",
    "Order book depth (number of levels)",
    ["symbol", "side"],
    registry=registry,
)

spread_bps = Gauge(
    "cryptobot_spread_bps",
    "Bid-ask spread in basis points",
    ["symbol"],
    registry=registry,
)

# =============================================================================
# Execution Metrics
# =============================================================================

execution_latency = Histogram(
    "cryptobot_execution_latency_seconds",
    "Order execution latency (order sent to ack)",
    ["venue", "symbol", "order_type"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
    registry=registry,
)

execution_slippage = Histogram(
    "cryptobot_execution_slippage_bps",
    "Execution slippage in basis points",
    ["venue", "symbol", "side"],
    buckets=[0, 1, 2, 5, 10, 20, 50, 100, 200, 500, 1000],
    registry=registry,
)

execution_fill_rate = Gauge(
    "cryptobot_execution_fill_rate_pct",
    "Order fill rate percentage",
    ["venue", "symbol"],
    registry=registry,
)

execution_retry_count = Counter(
    "cryptobot_execution_retry_total",
    "Number of order retries",
    ["venue", "symbol", "reason"],
    registry=registry,
)

# =============================================================================
# Strategy Metrics
# =============================================================================

strategy_signals = Counter(
    "cryptobot_strategy_signals_total",
    "Total signals generated by strategy",
    ["strategy", "signal_type", "symbol"],
    registry=registry,
)

strategy_signal_latency = Histogram(
    "cryptobot_strategy_signal_latency_seconds",
    "Strategy signal generation latency",
    ["strategy"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
    registry=registry,
)

strategy_active = Gauge(
    "cryptobot_strategy_active",
    "Whether strategy is active (1) or inactive (0)",
    ["strategy"],
    registry=registry,
)

strategy_capital_allocated = Gauge(
    "cryptobot_strategy_capital_allocated_usd",
    "Capital allocated to strategy in USD",
    ["strategy"],
    registry=registry,
)

strategy_capital_used = Gauge(
    "cryptobot_strategy_capital_used_usd",
    "Capital currently used by strategy in USD",
    ["strategy"],
    registry=registry,
)

# =============================================================================
# ML Metrics
# =============================================================================

ml_inference_latency = Histogram(
    "cryptobot_ml_inference_latency_seconds",
    "ML model inference latency",
    ["model", "type"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
    registry=registry,
)

ml_prediction = Histogram(
    "cryptobot_ml_prediction",
    "ML model prediction values",
    ["model", "type"],
    buckets=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
    registry=registry,
)

ml_model_accuracy = Gauge(
    "cryptobot_ml_model_accuracy",
    "ML model accuracy on validation set",
    ["model", "type"],
    registry=registry,
)

ml_retrain_count = Counter(
    "cryptobot_ml_retrain_total",
    "Number of model retraining events",
    ["model", "trigger"],
    registry=registry,
)

ml_feature_importance = Gauge(
    "cryptobot_ml_feature_importance",
    "Feature importance from ML model",
    ["model", "feature"],
    registry=registry,
)

ml_drift_score = Gauge(
    "cryptobot_ml_drift_score",
    "Data drift detection score",
    ["model", "feature"],
    registry=registry,
)

# =============================================================================
# System Health Metrics
# =============================================================================

system_uptime = Gauge(
    "cryptobot_system_uptime_seconds",
    "System uptime in seconds",
    registry=registry,
)

system_memory_usage = Gauge(
    "cryptobot_system_memory_bytes",
    "System memory usage in bytes",
    ["type"],
    registry=registry,
)

system_cpu_usage = Gauge(
    "cryptobot_system_cpu_percent",
    "System CPU usage percentage",
    registry=registry,
)

system_disk_usage = Gauge(
    "cryptobot_system_disk_percent",
    "System disk usage percentage",
    ["mount"],
    registry=registry,
)

# Connection health
connection_status = Gauge(
    "cryptobot_connection_status",
    "Connection status (1=connected, 0=disconnected)",
    ["component", "endpoint"],
    registry=registry,
)

connection_latency = Histogram(
    "cryptobot_connection_latency_seconds",
    "Connection latency to external services",
    ["component", "endpoint"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
    registry=registry,
)

# Error metrics
errors_total = Counter(
    "cryptobot_errors_total",
    "Total errors by type and component",
    ["component", "error_type"],
    registry=registry,
)

warnings_total = Counter(
    "cryptobot_warnings_total",
    "Total warnings by type and component",
    ["component", "warning_type"],
    registry=registry,
)

# =============================================================================
# Backtest Metrics
# =============================================================================

backtest_runs = Counter(
    "cryptobot_backtest_runs_total",
    "Total backtest runs",
    ["strategy", "status"],
    registry=registry,
)

backtest_duration = Histogram(
    "cryptobot_backtest_duration_seconds",
    "Backtest execution duration",
    ["strategy"],
    buckets=[1, 5, 10, 30, 60, 120, 300, 600, 1800, 3600],
    registry=registry,
)

backtest_trades = Counter(
    "cryptobot_backtest_trades_total",
    "Total trades in backtest",
    ["strategy", "result"],
    registry=registry,
)

# =============================================================================
# Internal state
# =============================================================================

# Track running realized-PnL totals so Gauge can hold signed values.
_realized_pnl_totals: dict[tuple[str, str], float] = {}


# =============================================================================
# Helper Functions
# =============================================================================

def init_system_info(version: str, git_commit: str = "", build_date: str = "") -> None:
    """Initialize system info metric."""
    system_info.info({
        "version": version,
        "git_commit": git_commit,
        "build_date": build_date,
        "environment": settings.app.env,
    })


def record_order(
    strategy: str,
    symbol: str,
    side: str,
    order_type: str,
    status: str,
    filled: bool = False,
    rejected_reason: str = "",
) -> None:
    """Record order metrics."""
    orders_total.labels(strategy=strategy, symbol=symbol, side=side, type=order_type, status=status).inc()
    if filled:
        orders_filled.labels(strategy=strategy, symbol=symbol, side=side).inc()
    if rejected_reason:
        orders_rejected.labels(strategy=strategy, symbol=symbol, reason=rejected_reason).inc()


def record_position_update(
    strategy: str,
    symbol: str,
    side: str,
    size_usd: float,
    unrealized_pnl: float = 0.0,
    realized_pnl: float = 0.0,
) -> None:
    """Record position metrics."""
    if size_usd > 0:
        positions_open.labels(strategy=strategy, symbol=symbol, side=side).set(1)
        position_size.labels(strategy=strategy, symbol=symbol, side=side).set(size_usd)
        position_pnl_unrealized.labels(strategy=strategy, symbol=symbol).set(unrealized_pnl)
    else:
        positions_open.labels(strategy=strategy, symbol=symbol, side=side).set(0)
        position_size.labels(strategy=strategy, symbol=symbol, side=side).set(0)

    if realized_pnl != 0:
        key = (strategy, symbol)
        prev = _realized_pnl_totals.get(key, 0.0)
        new_total = prev + realized_pnl
        _realized_pnl_totals[key] = new_total
        position_pnl_realized.labels(strategy=strategy, symbol=symbol).set(new_total)


def record_pnl(strategy: str, daily: float, total: float, equity: float, available: float, margin: float) -> None:
    """Record PnL metrics."""
    daily_pnl.labels(strategy=strategy).set(daily)
    total_pnl.labels(strategy=strategy).set(total)
    total_equity.set(equity)
    available_balance.set(available)
    used_margin.set(margin)


def record_performance(strategy: str, sharpe: float, sortino: float, max_dd: float, win_rate_val: float, profit_f: float) -> None:
    """Record performance metrics."""
    sharpe_ratio.labels(strategy=strategy, period="all").set(sharpe)
    sortino_ratio.labels(strategy=strategy, period="all").set(sortino)
    max_drawdown.labels(strategy=strategy).set(max_dd)
    win_rate.labels(strategy=strategy).set(win_rate_val)
    profit_factor.labels(strategy=strategy).set(profit_f)


def record_risk(
    exposure_pct: float,
    daily_loss_pct: float,
    drawdown_pct: float,
    kill_switch: bool,
    concentration_pct: float = 0.0,
) -> None:
    """Record risk metrics."""
    risk_exposure_pct.labels(strategy="portfolio").set(exposure_pct)
    risk_daily_loss_pct.labels(strategy="portfolio").set(daily_loss_pct)
    risk_drawdown_pct.set(drawdown_pct)
    risk_kill_switch_active.set(1 if kill_switch else 0)
    position_concentration.labels(strategy="portfolio").set(concentration_pct)


def record_market_data_latency(source: str, symbol: str, msg_type: str, latency: float) -> None:
    """Record market data latency."""
    market_data_latency.labels(source=source, symbol=symbol, type=msg_type).observe(latency)
    market_data_messages.labels(source=source, symbol=symbol, type=msg_type).inc()


def record_execution_latency(venue: str, symbol: str, order_type: str, latency: float) -> None:
    """Record execution latency."""
    execution_latency.labels(venue=venue, symbol=symbol, order_type=order_type).observe(latency)


def record_execution_slippage(venue: str, symbol: str, side: str, slippage_bps: float) -> None:
    """Record execution slippage."""
    execution_slippage.labels(venue=venue, symbol=symbol, side=side).observe(slippage_bps)


def record_venue_quote_latency(venue: str, symbol: str, latency: float) -> None:
    """Record venue quote (best-bid/ask fetch) latency."""
    try:
        execution_latency.labels(
            venue=venue, symbol=symbol, order_type="quote"
        ).observe(latency)
    except Exception:
        pass


def record_routing_decision(venue: str, symbol: str, action: str) -> None:
    """Smart-order-router selector counter.

    `action` is one of: ``selected``, ``fallback``, ``split``, ``failed``.
    """
    try:
        execution_retry_count.labels(venue=venue, symbol=symbol).inc()
        execution_fill_rate.labels(venue=venue, symbol=symbol).set(1.0 if action in {"selected", "split"} else 0.0)
    except Exception:
        pass


def record_strategy_signal(strategy: str, signal_type: str, symbol: str) -> None:
    """Record strategy signal."""
    strategy_signals.labels(strategy=strategy, signal_type=signal_type, symbol=symbol).inc()


def record_ml_inference(model: str, model_type: str, latency: float, prediction: float) -> None:
    """Record ML inference metrics."""
    ml_inference_latency.labels(model=model, type=model_type).observe(latency)
    ml_prediction.labels(model=model, type=model_type).observe(prediction)


def record_error(component: str, error_type: str) -> None:
    """Record error."""
    errors_total.labels(component=component, error_type=error_type).inc()


def record_warning(component: str, warning_type: str) -> None:
    """Record warning."""
    warnings_total.labels(component=component, warning_type=warning_type).inc()


def record_connection_status(component: str, endpoint: str, connected: bool) -> None:
    """Record connection status."""
    connection_status.labels(component=component, endpoint=endpoint).set(1 if connected else 0)


def record_backtest_run(strategy: str, status: str, duration: float, trades: int, winning: int, losing: int) -> None:
    """Record backtest run metrics."""
    backtest_runs.labels(strategy=strategy, status=status).inc()
    backtest_duration.labels(strategy=strategy).observe(duration)
    backtest_trades.labels(strategy=strategy, result="win").inc(winning)
    backtest_trades.labels(strategy=strategy, result="loss").inc(losing)


def get_metrics() -> bytes:
    """Get Prometheus metrics in exposition format."""
    return generate_latest(registry)


def get_metrics_text() -> str:
    """Get Prometheus metrics as text."""
    return get_metrics().decode("utf-8")


# =============================================================================
# Metrics Collection Context Manager
# =============================================================================

class MetricsContext:
    """Context manager for timed metrics collection."""

    def __init__(self, histogram: Histogram, **labels):
        self.histogram = histogram
        self.labels = labels
        self.start_time = 0.0

    def __enter__(self):
        import time
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        import time
        duration = time.perf_counter() - self.start_time
        self.histogram.labels(**self.labels).observe(duration)


def timed(histogram: Histogram, **labels) -> MetricsContext:
    """Create a timed context manager for a histogram."""
    return MetricsContext(histogram, **labels)


# =============================================================================
# Minimal Prometheus-free MetricsCollector
# =============================================================================

import threading
from collections import defaultdict


class _Counter:
    def __init__(self, name: str, help: str = "", labelnames: tuple = ()):
        self.name = name
        self.help = help
        self.labelnames = labelnames
        self._lock = threading.Lock()
        self._values: Dict[tuple, float] = defaultdict(float)

    def inc(self, amount: float = 1.0, **labels):
        key = self._key(labels)
        with self._lock:
            self._values[key] += amount

    def _key(self, labels: dict) -> tuple:
        return tuple(labels.get(n, "") for n in self.labelnames)


class _Gauge:
    def __init__(self, name: str, help: str = "", labelnames: tuple = ()):
        self.name = name
        self.help = help
        self.labelnames = labelnames
        self._lock = threading.Lock()
        self._values: Dict[tuple, float] = {}

    def set(self, value: float, **labels):
        key = self._key(labels)
        with self._lock:
            self._values[key] = float(value)

    def inc(self, amount: float = 1.0, **labels):
        key = self._key(labels)
        with self._lock:
            self._values[key] = self._values.get(key, 0.0) + amount

    def dec(self, amount: float = 1.0, **labels):
        self.inc(-amount, **labels)

    def _key(self, labels: dict) -> tuple:
        return tuple(labels.get(n, "") for n in self.labelnames)


class _Histogram:
    DEFAULT_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)

    def __init__(self, name: str, help: str = "", labelnames: tuple = (), buckets: tuple = ()):
        self.name = name
        self.help = help
        self.labelnames = labelnames
        self.buckets = tuple(sorted(buckets or self.DEFAULT_BUCKETS))
        self._lock = threading.Lock()
        self._counts: Dict[tuple, int] = defaultdict(int)
        self._sums: Dict[tuple, float] = defaultdict(float)
        self._bucket_counts: Dict[tuple, List[int]] = {}

    def observe(self, value: float, **labels):
        key = self._key(labels)
        with self._lock:
            self._counts[key] += 1
            self._sums[key] += float(value)
            bucket_counts = self._bucket_counts.setdefault(key, [0] * (len(self.buckets) + 1))
            placed = False
            for i, b in enumerate(self.buckets):
                if value <= b:
                    bucket_counts[i] += 1
                    placed = True
                    break
            if not placed:
                bucket_counts[-1] += 1

    def _key(self, labels: dict) -> tuple:
        return tuple(labels.get(n, "") for n in self.labelnames)


class MetricsCollector:
    """Minimal in-memory metrics collector with Prometheus text export."""

    def __init__(self):
        self._lock = threading.Lock()
        self._metrics: Dict[str, Any] = {}

    def counter(self, name: str, help: str = "", labelnames: tuple = ()) -> _Counter:
        with self._lock:
            if name not in self._metrics:
                self._metrics[name] = _Counter(name, help, tuple(labelnames))
            return self._metrics[name]

    def gauge(self, name: str, help: str = "", labelnames: tuple = ()) -> _Gauge:
        with self._lock:
            if name not in self._metrics:
                self._metrics[name] = _Gauge(name, help, tuple(labelnames))
            return self._metrics[name]

    def histogram(self, name: str, help: str = "", labelnames: tuple = (), buckets: tuple = ()) -> _Histogram:
        with self._lock:
            if name not in self._metrics:
                self._metrics[name] = _Histogram(name, help, tuple(labelnames), tuple(buckets))
            return self._metrics[name]

    def to_prometheus_text(self) -> str:
        lines: List[str] = []
        with self._lock:
            for name, metric in self._metrics.items():
                if isinstance(metric, _Counter):
                    lines.append(f"# HELP {name} {metric.help}")
                    lines.append(f"# TYPE {name} counter")
                    for labels_tuple, value in metric._values.items():
                        label_str = self._format_labels(metric.labelnames, labels_tuple)
                        lines.append(f"{name}{label_str} {value}")
                elif isinstance(metric, _Gauge):
                    lines.append(f"# HELP {name} {metric.help}")
                    lines.append(f"# TYPE {name} gauge")
                    for labels_tuple, value in metric._values.items():
                        label_str = self._format_labels(metric.labelnames, labels_tuple)
                        lines.append(f"{name}{label_str} {value}")
                elif isinstance(metric, _Histogram):
                    lines.append(f"# HELP {name} {metric.help}")
                    lines.append(f"# TYPE {name} histogram")
                    for labels_tuple, counts in metric._bucket_counts.items():
                        cumulative = 0
                        for i, b in enumerate(metric.buckets):
                            cumulative += counts[i]
                            bucket_label = dict(zip(metric.labelnames, labels_tuple))
                            bucket_label["le"] = str(b)
                            label_str = self._format_labels(list(metric.labelnames) + ["le"], tuple(bucket_label[l] for l in metric.labelnames) + (str(b),))
                            lines.append(f"{name}_bucket{label_str} {cumulative}")
                        cumulative += counts[-1]
                        bucket_label = dict(zip(metric.labelnames, labels_tuple))
                        bucket_label["le"] = "+Inf"
                        label_str = self._format_labels(list(metric.labelnames) + ["le"], tuple(bucket_label[l] for l in metric.labelnames) + ("+Inf",))
                        lines.append(f"{name}_bucket{label_str} {cumulative}")
                        label_str = self._format_labels(metric.labelnames, labels_tuple)
                        lines.append(f"{name}_sum{label_str} {metric._sums[labels_tuple]}")
                        lines.append(f"{name}_count{label_str} {metric._counts[labels_tuple]}")
        return "\n".join(lines) + "\n"

    def _format_labels(self, labelnames: tuple, values: tuple) -> str:
        if not labelnames:
            return ""
        parts = ",".join(f'{n}="{v}"' for n, v in zip(labelnames, values))
        return "{" + parts + "}"

    def reset(self):
        with self._lock:
            self._metrics.clear()


_collector: Optional[MetricsCollector] = None
_collector_lock = threading.Lock()


def get_metrics_collector() -> MetricsCollector:
    global _collector
    with _collector_lock:
        if _collector is None:
            _collector = MetricsCollector()
    return _collector


__all__ = [
    "system_info",
    "init_system_info",
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
    "MetricsCollector",
    "get_metrics_collector",
]