# Monitoring & Observability

## Overview

Cryptobot provides comprehensive monitoring with Prometheus metrics, structured logging, health checks, and alerting.

## Metrics

### Prometheus Metrics

```python
from cryptobot.monitoring.metrics import (
    record_order,
    record_fill,
    record_pnl,
    record_execution_latency,
    record_venue_quote_latency,
    record_routing_decision,
    PROMETHEUS_AVAILABLE,
)

# Record order
record_order(
    strategy="trend_following",
    symbol="BTCUSDT",
    side="BUY",
    order_type="MARKET",
)

# Record fill
record_fill(
    symbol="BTCUSDT",
    side="BUY",
    quantity=Decimal("1"),
    price=Decimal("50000"),
    commission=Decimal("2.50"),
)

# Record PnL
record_pnl(
    strategy="trend_following",
    daily=Decimal("100"),
    total=Decimal("5000"),
    equity=Decimal("15000"),
    available=Decimal("12000"),
    margin=Decimal("3000"),
)

# Execution latency
record_execution_latency(
    venue="binance",
    symbol="BTCUSDT",
    order_type="MARKET",
    latency=0.045,
)

# Venue quote latency
record_venue_quote_latency(
    venue="binance",
    symbol="BTCUSDT",
    order_type="MARKET",
    latency=0.012,
)

# Routing decision
record_routing_decision(
    venue="binance",
    symbol="BTCUSDT",
    action="selected",  # selected, fallback, failed
)
```

### Available Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `orders_total` | Counter | Total orders submitted |
| `fills_total` | Counter | Total fills |
| `fills_latency_seconds` | Histogram | Fill latency |
| `execution_latency_seconds` | Histogram | End-to-end latency |
| `venue_quote_latency_seconds` | Histogram | Quote latency per venue |
| `orders_rejected_total` | Counter | Rejected orders |
| `routing_decisions_total` | Counter | Routing decisions |
| `pnl_total` | Gauge | Total P&L |
| `pnl_daily` | Gauge | Daily P&L |
| `equity` | Gauge | Total equity |
| `drawdown_pct` | Gauge | Drawdown percentage |
| `position_size` | Gauge | Position size per symbol |
| `venue_quote_latency_seconds` | Histogram | Quote latency |

### Exposing Metrics

```python
from cryptobot.monitoring.metrics import get_metrics_text, generate_latest, registry

# Text format (Prometheus scrape)
metrics_text = get_metrics_text()

# Binary protobuf
metrics_bytes = generate_latest(registry)
```

### Prometheus Scrape Config

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'cryptobot'
    static_configs:
      - targets: ['cryptobot:8080']
    metrics_path: /metrics
```

## Logging

### Structured Logging

```python
from cryptobot.utils.logging import get_logger, configure_logging

# Configure
configure_logging(
    level="INFO",
    json_output=True,  # JSON for log aggregation
)

# Get logger
logger = get_logger(__name__)

# Log with context
logger.info(
    "Order submitted",
    symbol="BTCUSDT",
    side="BUY",
    quantity=1.0,
    order_id=order.order_id,
)
```

### Log Output (JSON)

```json
{
  "timestamp": "2024-01-15T10:30:45.123Z",
  "level": "INFO",
  "logger": "cryptobot.execution.engine",
  "message": "Order submitted",
  "symbol": "BTCUSDT",
  "side": "BUY",
  "quantity": 1.0,
  "order_id": "abc123",
  "correlation_id": "corr-123"
}
```

### Log Levels

```python
from cryptobot.utils.logging import configure_logging

configure_logging(
    level="DEBUG",          # DEBUG, INFO, WARNING, ERROR, CRITICAL
    json_output=True,       # JSON format for log aggregation
    console_output=True,    # Also output to console
)
```

### Log Rotation

```bash
# Docker
docker run --log-opt max-size=10m --log-opt max-file=3 ...
```

## Health Checks

### Health Monitor

```python
from cryptobot.monitoring.health import HealthMonitor, HealthCheck, ComponentType

monitor = HealthMonitor(check_interval=30.0)

# Register custom check
monitor.register_check(HealthCheck(
    name="exchange_ping",
    component=ComponentType.EXCHANGE,
    check_fn=lambda: exchange.get_server_time(),
    interval_seconds=30.0,
    timeout_seconds=5.0,
    critical=True,
))

# Run checks
results = await monitor.run_all_checks()

# Get component health
exchange_health = monitor.get_component_health(ComponentType.EXCHANGE)

# Overall health
is_healthy = monitor.is_healthy()
overall_status = monitor.get_overall_status()
```

### Built-in Checkers

```python
from cryptobot.monitoring.health import (
    ExchangeHealthChecker,
    DataFeedHealthChecker,
    DatabaseHealthChecker,
    CacheHealthChecker,
    RiskEngineHealthChecker,
    StrategyEngineHealthChecker,
    create_standard_checks,
)

# Create standard checks
checks = create_standard_checks(
    exchange_client=exchange,
    market_data_manager=manager,
    redis_client=redis,
    db_pool=pool,
)

for check in checks:
    monitor.register_check(check)
```

### HealthCheck Definition

```python
from cryptobot.monitoring.health import HealthCheck, ComponentType

check = HealthCheck(
    name="exchange_ping",
    component=ComponentType.EXCHANGE,
    check_fn=lambda: exchange.get_server_time(),
    interval_seconds=30.0,
    timeout_seconds=5.0,
    critical=True,
    tags={"environment": "production"},
)
```

### Component Types

```python
from cryptobot.monitoring.health import ComponentType

ComponentType.EXCHANGE
ComponentType.DATA_FEED
ComponentType.RISK_ENGINE
ComponentType.STRATEGY_ENGINE
ComponentType.ORDER_MANAGER
ComponentType.DATABASE
ComponentType.CACHE
ComponentType.ML_PIPELINE
ComponentType.EXECUTION
```

### HealthResult

```python
from cryptobot.monitoring.health import HealthResult, HealthStatus

result = HealthResult(
    check_name="exchange_ping",
    component=ComponentType.EXCHANGE,
    status=HealthStatus.HEALTHY,
    latency_ms=12.5,
    message="OK",
    details={"server_time": 1234567890},
)
```

### ComponentHealth

```python
from cryptobot.monitoring.health import ComponentHealth

comp = ComponentHealth(
    component=ComponentType.EXCHANGE,
    status=HealthStatus.HEALTHY,
    checks=[...],
    last_check=datetime.utcnow(),
    uptime_start=datetime.utcnow(),
    total_checks=100,
    failed_checks=2,
)

print(comp.success_rate)  # 0.98
print(comp.is_healthy)    # True
```

### Health Status

```python
from cryptobot.monitoring.health import HealthStatus

HealthStatus.HEALTHY
HealthStatus.DEGRADED
HealthStatus.UNHEALTHY
HealthStatus.UNKNOWN
```

### Running Checks

```python
# Run all checks
results = await monitor.run_all_checks()

# Get component health
exchange_health = monitor.get_component_health(ComponentType.EXCHANGE)

# Overall status
status = monitor.get_overall_status()

# Check if healthy
if monitor.is_healthy():
    print("System healthy")
```

### Health HTTP Endpoint

```python
from cryptobot.utils.health_server import create_health_server

app = create_health_server(monitor)

# GET /health    - Overall health
# GET /health/ready  - Readiness
# GET /health/live   - Liveness
# GET /metrics   - Prometheus metrics
```

### Running Health Server

```bash
# Standalone
python -m cryptobot.utils.health_server

# In Docker
docker run -p 8080:8080 cryptobot:latest serve --health-port 8080
```

## Alerting

### Alert Manager

```python
from cryptobot.monitoring.alerting import (
    AlertManager,
    Alert,
    AlertSeverity,
    AlertCategory,
    AlertRule,
    NotificationChannel,
)
```

### Alert Rules

```python
from cryptobot.monitoring.alerting import AlertRule, AlertSeverity, AlertCategory

rule = AlertRule(
    name="high_drawdown",
    category=AlertCategory.RISK,
    severity=AlertSeverity.CRITICAL,
    labels={"drawdown_pct": "0.15"},
    channels=["telegram", "pagerduty"],
    cooldown=timedelta(minutes=15),
    auto_resolve=True,
    resolve_after=timedelta(hours=1),
)
```

### Channels

```python
from cryptobot.monitoring.alerting import (
    TelegramChannel,
    DiscordChannel,
    EmailChannel,
    PagerDutyChannel,
)

# Telegram
telegram = TelegramChannel(
    bot_token="your_token",
    chat_id="your_chat_id",
)

# Discord
discord = DiscordChannel(
    webhook_url="https://discord.com/api/webhooks/...",
)

# Email
email = EmailChannel(
    smtp_host="smtp.gmail.com",
    smtp_port=587,
    username="alerts@example.com",
    password="password",
    from_email="alerts@example.com",
    to_emails=["oncall@example.com"],
)

# PagerDuty
pagerduty = PagerDutyChannel(
    integration_key="your_key",
)

# Add to manager
manager.add_channel("telegram", telegram)
manager.add_channel("discord", discord)
manager.add_channel("email", email)
manager.add_channel("pagerduty", pagerduty)

# Add rules
manager.add_rule("high_drawdown", rule)
```

### Alert Severity

```python
from cryptobot.monitoring.alerting import AlertSeverity

AlertSeverity.INFO
AlertSeverity.WARNING
AlertSeverity.CRITICAL
AlertSeverity.EMERGENCY
```

### Alert Categories

```python
from cryptobot.monitoring.alerting import AlertCategory

AlertCategory.SYSTEM
AlertCategory.TRADING
AlertCategory.RISK
AlertCategory.EXECUTION
AlertCategory.ML
AlertCategory.DATA
```

### Firing Alerts

```python
alert = Alert(
    title="High Drawdown",
    message="Portfolio drawdown 15% exceeds limit 10%",
    severity=AlertSeverity.CRITICAL,
    category=AlertCategory.RISK,
    source="risk_engine",
    labels={"drawdown_pct": "0.15"},
)

sent_count = await manager.fire(alert)
```

### Alert Lifecycle

```
FIRED → ACTIVE → (cooldown) → RESOLVED → (auto-resolve) → CLEARED
```

### Cooldown & Deduplication

```python
AlertRule(
    name="high_drawdown",
    cooldown=timedelta(minutes=15),  # Don't re-alert for 15 min
    auto_resolve=True,                # Auto-resolve when condition clears
    resolve_after=timedelta(hours=1), # Force resolve after 1 hour
)
```

### Fingerprint (Deduplication)

```python
alert = Alert(
    severity=AlertSeverity.CRITICAL,
    category=AlertCategory.RISK,
    source="risk_engine",
    title="High Drawdown",
    message="Drawdown 15%",
    fingerprint="risk:system:high_drawdown",  # Custom fingerprint
)
```

### Built-in Rules

```python
from cryptobot.monitoring.alerting import create_standard_rules

rules = create_standard_rules(
    kill_switch_active=True,
    max_drawdown_pct=0.15,
    daily_loss_limit_pct=0.05,
    error_rate_threshold=0.05,
    latency_p99_ms=1000,
)

for rule in rules:
    manager.add_rule(rule.name, rule)
```

## Grafana Dashboards

### Pre-built Dashboards

```bash
# Import from docs/grafana/dashboards/
```

### Dashboard Panels

| Panel | Query | Description |
|-------|-------|-------------|
| Equity Curve | `equity` | Portfolio equity over time |
| PnL | `pnl_total`, `pnl_daily` | Daily and total P&L |
| Drawdown | `drawdown_pct` | Current drawdown % |
| Sharpe Ratio | `sharpe_ratio` | Rolling Sharpe |
| Win Rate | `win_rate` | Win rate % |
| Trades | `orders_total`, `fills_total` | Order/fill counts |
| Latency | `execution_latency_seconds` | Execution latency |
| Slippage | `slippage_bps` | Average slippage |
| Fill Rate | `fills_total / orders_total` | Fill rate |
| Rejection Rate | `orders_rejected_total / orders_total` | Rejection rate |

## Grafana Alerting

```yaml
# grafana/alerting/rules.yml
groups:
  - name: cryptobot
    rules:
      - alert: HighDrawdown
        expr: drawdown_pct > 0.15
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "High drawdown: {{ $value }}"
          
      - alert: HighErrorRate
        expr: orders_rejected_total / orders_total > 0.1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High rejection rate"
          
      - alert: HighLatency
        expr: histogram_quantile(0.99, execution_latency_seconds) > 1
        for: 5m
        labels:
          severity: warning
```

## Docker Compose Monitoring Stack

```yaml
# docker-compose.yml
services:
  prometheus:
    image: prom/prometheus
    volumes:
      - ./monitoring/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml
    ports:
      - "9090:9090"
      
  grafana:
    image: grafana/grafana
    volumes:
      - ./monitoring/grafana/dashboards:/etc/grafana/provisioning/dashboards
    ports:
      - "3000:3000"
      
  alertmanager:
    image: prom/alertmanager
    volumes:
      - ./monitoring/alertmanager/alertmanager.yml:/etc/alertmanager/alertmanager.yml
    ports:
      - "9093:9093"
      
  loki:
    image: grafana/loki
    ports:
      - "3100:3100"
      
  promtail:
    image: grafana/promtail
    volumes:
      - ./logs:/var/log
      - ./monitoring/promtail/config.yml:/etc/promtail/config.yml
```

## Tracing

```python
# OpenTelemetry (future)
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

with tracer.start_as_current_span("submit_order") as span:
    span.set_attribute("symbol", "BTCUSDT")
    span.set_attribute("side", "BUY")
    span.set_attribute("quantity", 1.0)
    filled = await engine.submit_order(order)
```

## Files

- `src/cryptobot/monitoring/metrics.py` - Prometheus metrics
- `src/cryptobot/monitoring/alerting.py` - AlertManager
- `src/cryptobot/monitoring/health.py` - HealthMonitor
- `src/cryptobot/monitoring/dashboard.py` - Grafana JSON
- `src/cryptobot/utils/logging.py` - Structured logging
- `src/cryptobot/utils/health_server.py` - HTTP health endpoint
- `monitoring/prometheus/prometheus.yml` - Prometheus config
- `monitoring/grafana/dashboards/*.json` - Grafana dashboards
- `monitoring/alertmanager/alertmanager.yml` - Alertmanager config