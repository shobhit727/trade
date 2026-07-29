# 00. Project Overview

> **Last Updated**: 2026-07-29 (audit pass)
> **Confidence**: High for current state; Medium for intent.

## What it is

Crypto trading bot framework: Python 3.14, Rust workspace (placeholder), TimescaleDB + Redis, Binance live/testnet. Targets multi-asset, multi-strategy, statistical rigor.

## Why it exists

Repo documents the goal of an institutional-grade retail-trading bot. Same project as the planning docs imply. Source-of-truth files: `plan.md`, `PROJECT_MEMORY/`.

## High-level architecture

- Python orchestration: `src/cryptobot/`
- Rust placeholder: `Cargo.toml` only (no crate members, `crates/cryptobot-core/Cargo.toml` exists but no `src/`)
- Storage: TimescaleDB (prod), SQLite (in-process), Parquet (local)
- Cache/Bus: Redis (intended), asyncio EventBus (in-process)
- Observability: Prometheus + Grafana, Loki/Promtail, Alertmanager
- Run: `Dockerfile` + `docker-compose.yml`

## Current state (verified)

- `src/cryptobot/core/`: events, bus, clock, state, portfolio — implemented.
- `src/cryptobot/data/`: ingestion, storage, cleaning — implemented.
- `src/cryptobot/backtest/`: engine, metrics, simulator, validation — implemented.
- `src/cryptobot/utils/`: logging, decorators, types — implemented.
- `src/cryptobot/market_data/manager.py`: Binance WS client — implemented.
- `src/cryptobot/strategies/`: BaseStrategy, registry, MeanReversionStrategy placeholder — implemented.
- `src/cryptobot/risk/`: minimal scaffold (limits, sizing, kill_switch, manager, correlation) — implemented.
- `src/cryptobot/execution/`: engine, algorithms, venue/base+simulated — implemented.
- `src/cryptobot/cli/main.py`: argparse CLI — implemented.
- `src/cryptobot/ml/`: empty.
- `src/cryptobot/execution/venue/binance.py`: missing.
- `tests/`: only `tests/unit/test_core_foundation.py`.

## Notable discrepancies (verified)

- `configs/base.yaml` keys do **not** match `src/cryptobot/config.py` Settings field names. Examples: `exchanges.binance` vs `exchange`, `monitoring.prometheus.port` vs `monitoring.prometheus_port`, `xmr.daemon` vs `xmr.daemon_host`, `monitoring.alerts.telegram_enabled` vs `monitoring.telegram_enabled`, `market_data.redis` vs `market_data.redis_host`. `Settings(extra="ignore")` swallows the mismatch and returns defaults.
- `tests/unit/test_core_foundation.py` referenced `SubscriptionMode` and `update_on_trade` which do not exist. Replaced this session with real smoke tests.
- `mean_reversion` / `trend_following` / `funding_arbitrage` / `statistical_arbitrage` classes referenced in `configs/base.yaml` are not implemented as `src/cryptobot/strategies/*.py` files.

## Confidence per subject

- High: directory tree, file presence, line counts, public class/symbol names.
- Medium: behavior of modules not exercised by tests.
- Low: anything not yet implemented (ML, Binance live adapter, walk-forward math).

## Recent changes

- Added `risk/`, `execution/`, `cli/`, smoke tests, `Dockerfile`, `requirements/test.txt`, `cryptobot-test` compose service, `.dockerignore`.
- Patched imports, env imports, validation logic, sqlite fallback, health-check async detection.
- See `23_Repository_History.md`, `24_Agent_Log.md`, `13_Bug_Tracker.md`.
