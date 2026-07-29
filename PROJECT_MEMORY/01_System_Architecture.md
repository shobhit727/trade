# 01. System Architecture

> **Last Updated**: 2026-07-29 (audit pass)
> **Confidence**: High for the diagram and what exists; Low for what is intended.

## Verified layers

```
┌─────────────────────────────────────────────────────────────────┐
│                    Python Orchestration Layer (3.14)             │
│  config │ core │ data │ strategies │ risk │ execution           │
│  backtest │ monitoring │ utils │ cli │ market_data              │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│          Rust Layer (placeholder)                               │
│  Cargo.toml (root) + crates/cryptobot-core/Cargo.toml (no src)  │
└─────────────────────────────────────────────────────────────────┘
```

## Verified modules

| Layer | Files | Status |
|-------|-------|--------|
| Config | `src/cryptobot/config.py` | Pydantic v2 BaseSettings; YAML loader via `Settings.from_yaml`; `extra="ignore"` swallows unknown keys. |
| Core | `events.py`, `bus.py`, `clock.py`, `state.py`, `portfolio.py` | Implemented. |
| Data | `ingestion.py`, `storage.py`, `cleaning.py` | Implemented. |
| Strategies | `base.py`, `registry.py` | Implemented (placeholder only). |
| Risk | `manager.py`, `limits.py`, `sizing.py`, `kill_switch.py`, `correlation.py` | Implemented (minimal). |
| Execution | `engine.py`, `algorithms.py`, `venue/base.py`, `venue/simulated.py` | Implemented (mock venue only). |
| Backtest | `engine.py`, `metrics.py`, `simulator.py`, `validation.py` | Implemented. |
| Monitoring | `metrics.py`, `alerting.py`, `health.py`, `dashboard.py` | Implemented. |
| Utils | `logging.py`, `decorators.py`, `types.py` | Implemented. |
| Market Data | `manager.py` | Binance WS client implemented. |
| CLI | `main.py` | argparse implemented. |
| ML | empty | Not implemented. |
| Rust | `crates/cryptobot-core/Cargo.toml` | Manifest only. |

## Event flow (verified)

- `market_data.manager` → publishes events into `core.bus.EventBus`.
- `strategies.base.BaseStrategy.on_market_data(event)` consumes events.
- Strategies emit `OrderEvent`s.
- `execution.engine.ExecutionEngine.submit_order(order)` calls `risk.manager.RiskManager.check_order(order)`, then venue.
- `risk.manager.RiskCheckResult.to_event` publishes `RiskEvent`.
- `backtest.engine.BacktestEngine` runs the loop in event-driven mode.

## Key cross-cutting decisions

- All timestamps: `datetime.utcnow()`.
- All money: `Decimal`.
- All async API entry points: `asyncio`.
- Async-first, sync fallback only for selected decorators (`utils/decorators.py`).

## Known mismatches

- **`configs/base.yaml` vs `Settings`**: YAML keys do not match Settings field names. Examples:
  - `exchanges.binance` → Settings has `exchange` (singular).
  - `monitoring.alerts.telegram_enabled` → Settings has `monitoring.telegram_enabled`.
  - `monitoring.alerts.discord_webhook` → Settings has `monitoring.discord_webhook`.
  - `monitoring.alerts.email_enabled` → Settings has `monitoring.email_enabled`.
  - `monitoring.prometheus.port` → Settings has `monitoring.prometheus_port`.
  - `monitoring.grafana.port` → Settings has `monitoring.grafana_port`.
  - `xmr.daemon` → Settings has `xmr.daemon_host`, `daemon_port`, `daemon_ssl`, `daemon_username`, `daemon_password`.
  - `xmr.wallet_rpc` → Settings has `xmr.wallet_host`, `wallet_port`, `wallet_ssl`, `wallet_username`, `wallet_password`.
  - `xmr.funding` → Settings has `xmr.funding_enabled`, `min_balance_xmr`, `target_balance_xmr`, `withdraw_threshold_xmr`, `withdraw_address`, `confirmations`.
  - `market_data.redis` → Settings has `market_data.redis_host`, `redis_port`, `redis_db`, `redis_max_connections`.
  - `monitoring.grafana.port` → Settings has `monitoring.grafana_port`.
  - `monitoring.alerts.telegram_enabled` → Settings has `monitoring.telegram_enabled`.
- `extra="ignore"` in `Settings` means YAML loading silently uses defaults for all unmatched keys. Effective config = all defaults.
- `mean_reversion` / `trend_following` / `funding_arbitrage` / `statistical_arbitrage` strategies listed in YAML are not implemented as concrete classes.

## Runtime pre-requisites

- Python 3.14 slim (Dockerfile).
- Optional third-party: `prometheus_client`, `aiohttp`, `asyncpg`, `pyarrow`, `pandas`, `numpy`, `ccxt`.
- Optional infrastructure: TimescaleDB, Redis.
- If `_sqlite3` unavailable, `core.state.StateManager` skips persistence silently.

## Detailed API references

- `06_API_Reference.md` — public re-exports per package.
- `05_Control_Flow.md` — module-level call order.
- `12_Feature_Status.md` — feature-by-feature status.

## Confidence

- High: diagram, file presence, public classes.
- Medium: behavior not exercised by tests.
- Low: intended Rust surface, ML pipeline internals.
