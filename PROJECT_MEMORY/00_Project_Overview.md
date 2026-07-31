# 00. Project Overview

> **Last Updated**: 2026-07-31 (audit sync)
> **Confidence**: High for current state; Medium for intent.

## What it is

Crypto trading bot framework: Python 3.14, Rust workspace (7 crates, empty scaffolding), TimescaleDB + Redis, Binance live/testnet. Targets multi-asset, multi-strategy, statistical rigor.

## Why it exists

Repo documents the goal of an institutional-grade retail-trading bot. Same project as the planning docs imply. Source-of-truth files: `plan.md`, `PROJECT_MEMORY/`.

## High-level architecture

- Python orchestration: `src/cryptobot/` (22 unit test files, 30+ modules)
- Rust placeholder: `Cargo.toml` + 7 member crates with empty `src/` dirs
- Storage: TimescaleDB (prod), SQLite (in-process), Parquet (local)
- Cache/Bus: Redis (intended), asyncio EventBus (in-process)
- Observability: Prometheus + Grafana, Loki/Promtail (referenced but missing dirs), Alertmanager
- Run: `Dockerfile` + `docker-compose.yml` (test profile ✅; default profile ✅ fixed)
- CI: GitHub Actions (lint + unit + compose-validate + multi-arch buildx)

## Current state (verified)

- `src/cryptobot/core/`: events, bus, clock, state, portfolio — implemented.
- `src/cryptobot/data/`: ingestion, storage, cleaning — implemented. `features.py` missing (use `ml/features.py`).
- `src/cryptobot/backtest/`: engine, metrics, simulator, validation (real math), reporting (HTML), runner (end-to-end), data (CSV/Parquet/TimescaleDB/synthetic) — implemented.
- `src/cryptobot/utils/`: logging, decorators (jitter clamped, circuit_breaker raises), types, health_server — implemented.
- `src/cryptobot/market_data/manager.py`: Binance WS client with fallback — implemented.
- `src/cryptobot/strategies/`: BaseStrategy, registry, **5 concrete strategies** (mean_reversion, trend_following, stat_arb, funding_arb, market_making). `ml_strategy.py` **missing**.
- `src/cryptobot/risk/`: limits, sizing, kill_switch, manager, correlation — implemented.
- `src/cryptobot/execution/`: engine, algorithms (TWAP/VWAP/POV/IS/Iceberg/sweep/arrival/vwap_schedule), router (SmartOrderRouter), adverse_selection (AdverseSelectionGuard), venue/base+simulated+binance — implemented.
- `src/cryptobot/monitoring/`: metrics (Gauge for PnL), alerting (lazy init), health (async-aware), dashboard — implemented.
- `src/cryptobot/cli/main.py`: argparse with `validate`, `paper`, `bot`, `serve` subcommands — implemented.
- `src/cryptobot/ml/`: features (8), models/direction (sklearn logreg + numpy fallback), online (WalkForwardTrainer + DriftDetector) — implemented. volatility/regime/ensemble missing.
- `tests/unit/`: 22 test files covering all major modules.
- `docker-compose.yml`: full stack. Test profile ✅. Default profile ✅ (monitoring dirs scaffolded).
- `deploy/k8s/`: namespace, ConfigMap, Secret, PVC, Deployment, kustomization. **No Service, no HPA.**
- `migrations/`: `001_extension.sql`, `002_hypertables.sql`.
- `Cargo.toml` + 7 crates: all empty scaffolding.
- `pyproject.toml`: setuptools build + CLI entry.

## Notable discrepancies (verified)

- `configs/base.yaml` keys do **not** match `src/cryptobot/config.py` Settings field names. Examples: `exchanges.binance` vs `exchange`, `monitoring.prometheus.port` vs `monitoring.prometheus_port`, `xmr.daemon` vs `xmr.daemon_host`, `monitoring.alerts.telegram_enabled` vs `monitoring.telegram_enabled`, `market_data.redis` vs `market_data.redis_host`. `Settings(extra="ignore")` swallows the mismatch and returns defaults — mitigated by `_flatten_yaml` + `from_yaml_safe`.
- `configs/base.yaml` `ml.models.direction.type: lightgbm` but `ml/models/direction.py` uses sklearn/numpy fallback — config unused.
- `configs/base.yaml` `strategies.enabled` list not read by any code — strategies never auto-instantiated from config.
- `plan.md` Phase 4 claims `[x] ML-driven strategy (strategies/ml_strategy.py)` — file does not exist.
- `deploy/k8s/` missing `Service` and `HPA` claimed in plan.md Phase 8.
- Rust workspace: 7 crates with empty `src/` — `cargo build` fails.
- 6 dead empty dirs under `src/cryptobot/`: `allocator/`, `altdata/`, `api/`, `exchanges/`, `funding/`, `xmr/`.

## Confidence per subject

- High: directory tree, file presence, line counts, public class/symbol names.
- Medium: behavior of modules not exercised by tests.
- Low: anything not yet implemented (ML volatility/regime/ensemble, Rust core, live trading durability).

## Recent changes

- Audit 2026-07-31: synced `plan.md` and `PROJECT_MEMORY/` with actual repo state. 26 doc/code mismatches identified and documented in `25_Audit_2026-07-31.md`.
- **Fixed 2026-07-31**: Scaffolded `monitoring/{loki,promtail,nginx}` directories with minimal configs; `docker compose config` (default profile) now passes.
- Prior: Added `risk/`, `execution/`, `cli/`, smoke tests, `Dockerfile`, `requirements/test.txt`, `cryptobot-test` compose service, `.dockerignore`.
- Patched imports, env imports, validation logic, sqlite fallback, health-check async detection.
- See `23_Repository_History.md`, `24_Agent_Log.md`, `13_Bug_Tracker.md`.