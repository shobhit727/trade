# 03. Component Map

> **Last Updated**: 2026-07-29 (audit pass)
> **Confidence**: High (verified by code inspection).

## Verified import graph

```
config.py
  └─ core.events, core.state, core.bus, core.portfolio, core.clock, etc.

core.events         ─ leaf (dataclasses + enums)
core.bus            ─ core.events
core.clock          ─ leaf (asyncio + dataclasses)
core.state          ─ core.events, config
core.portfolio      ─ core.events, core.state, config

data.ingestion      ─ core.events, core.bus, config
data.storage        ─ config
data.cleaning       ─ leaf (uses pandas/numpy)

strategies.base     ─ core.events, utils.decorators
strategies.registry ─ strategies.base

risk.manager        ─ core.events, core.portfolio, risk.kill_switch, risk.limits
risk.{limits,kill_switch,correlation,sizing} ─ config

execution.engine    ─ core.bus, core.events, risk.manager, execution.venue.base
execution.algorithms─ leaf
execution.venue.base─ leaf
execution.venue.simulated ─ core.events, execution.venue.base

backtest.engine     ─ core.events, core.clock, core.portfolio, core.state, utils.types
backtest.metrics    ─ core.portfolio
backtest.simulator  ─ leaf
backtest.validation ─ leaf

market_data.manager ─ core.events, config

monitoring.metrics  ─ prometheus_client (optional)
monitoring.alerting ─ leaf
monitoring.health   ─ core.events, core.bus, config, utils.logging
monitoring.dashboard─ leaf

cli.main            ─ argparse only (no project imports)

utils.{logging,decorators,types} ─ stdlib only
```

## Real circular dependency

- `core.portfolio` imports `core.state` (uses `state_manager`).
- `core.state` imports `config` (Pydantic settings).
- No cycle so far.

## Module-level singletons

| Module | Singleton entry |
|--------|-----------------|
| State | `state_manager = StateManager()` |
| EventBus | `get_event_bus()` / `init_event_bus()` |
| Clock | `get_clock()` / `set_clock()` |
| Portfolio | `get_portfolio_manager()` |
| Risk | `get_risk_manager()` |
| Execution | `get_execution_engine()` |
| Strategy | `registry = StrategyRegistry()` |
| Storage | `get_storage()` / `init_storage()` |
| Health | `get_health_monitor()` / `init_health_monitor()` |
| Alerts | `get_alert_manager()` / `init_alerting()` |
| Metrics | `get_metrics_collector()` |
| Ingestion | `get_ingestion_manager()` |

## Reverse dependency (who depends on each module)

| Module | Direct importers |
|--------|------------------|
| `core.events` | core.bus, core.state, core.portfolio, data.ingestion, market_data.manager, execution.engine, risk.manager, strategies.base, backtest.engine, monitoring.health |
| `config` | core.state, core.portfolio, data.ingestion, data.storage, market_data.manager, risk.limits, risk.kill_switch, monitoring.health |
| `core.bus` | data.ingestion, execution.engine, monitoring.health |
| `utils.decorators` | strategies.base |
| `core.portfolio` | risk.manager, backtest.engine, backtest.metrics |
| `core.state` | core.portfolio, backtest.engine |
| `core.clock` | backtest.engine |
| `utils.types` | backtest.engine |

## Confidence

- High: all of the above.
- Notes: `monitoring/__init__.py` uses lazy `__getattr__` (B051) — `import cryptobot.monitoring` succeeds even without `prometheus_client`; `metrics.py` falls back to `_NoOpMetric` no-ops. Verified by `tests/unit/test_monitoring_lazy_imports.py`.
