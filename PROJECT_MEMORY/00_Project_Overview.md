# 00. Project Overview

> **Last Updated**: 2026-07-31 (audit v2)
> **Confidence**: High for current state; Medium for intent.

## What it is

Crypto trading bot framework: Python 3.14, Rust workspace (7 fleshed-out crates with PyO3 0.29), TimescaleDB + Redis, Binance live/testnet. Targets multi-asset, multi-strategy, statistical rigor.

## Why it exists

Repo documents the goal of an institutional-grade retail-trading bot. Source-of-truth files: `plan.md`, `PROJECT_MEMORY/`.

## High-level architecture

- Python orchestration: `src/cryptobot/` (44 unit test files, 30+ modules)
- Rust: `Cargo.toml` workspace with 7 crates (`core`, `features`, `risk`, `stats`, `orderbook`, `backtest`, `py`) with PyO3 0.29; fmt/clippy/test green on stable 1.97+
- Storage: TimescaleDB (prod), SQLite (in-process), Parquet (local)
- Cache/Bus: Redis (intended), asyncio EventBus (in-process)
- Observability: Prometheus + Grafana, Loki/Promtail, Alertmanager (all dirs scaffolded)
- Run: `Dockerfile` + `docker-compose.yml` (test ✅; default ✅)
- CI: GitHub Actions (lint + unit + compose-validate + multi-arch buildx)

## Current state (verified)

- `src/cryptobot/core/`: events, bus, clock, state, portfolio — implemented.
- `src/cryptobot/data/`: ingestion, storage, cleaning, features (re-export of ml) — implemented.
- `src/cryptobot/backtest/`: engine, metrics, simulator, validation (real math), reporting (HTML), runner (end-to-end), data (CSV/Parquet/TimescaleDB/synthetic) — implemented.
- `src/cryptobot/utils/`: logging, decorators (jitter clamped, circuit_breaker raises), types, health_server — implemented.
- `src/cryptobot/market_data/manager.py`: Binance WS client with fallback to `default_symbol` and `["1m"]` (B044).
- `src/cryptobot/strategies/`: BaseStrategy, registry, **6 concrete strategies** (mean_reversion, trend_following, stat_arb, funding_arb, market_making, ml_strategy) — all implemented. YAML `strategies.enabled` now wired via `load_strategies_from_config` (B057/B059).
- `src/cryptobot/risk/`: limits, sizing, kill_switch, manager (B060/B061 notional price > 0), correlation — implemented.
- `src/cryptobot/execution/`: engine (B040 ORDER_REJECTED), algorithms (TWAP/VWAP/POV/IS/Iceberg/sweep/arrival/vwap_schedule), router (SmartOrderRouter), adverse_selection (AdverseSelectionGuard), venue/base+simulated+binance — implemented.
- `src/cryptobot/monitoring/`: metrics (Gauge for PnL, B025), alerting (lazy init B031, shared executor B067), health (async-aware, runtime mutators B043), dashboard — implemented. **`metrics` + `alerting` are optional-deps-tolerant** (B051 resolved 2026-07-31): no-op `_NoOpMetric` stubs when `prometheus_client` missing; `aiohttp` deferred to per-channel `_send` methods.
- `src/cryptobot/cli/main.py`: argparse with `validate`, `paper`, `bot`, `serve` subcommands — implemented (`serve` starts `HealthServer`).
- `src/cryptobot/ml/`: features (8), models/direction (sklearn logreg + numpy fallback; train stats persisted, B065), online (WalkForwardTrainer + DriftDetector) — implemented. volatility/regime/ensemble still missing.
- `tests/unit/`: 22 test files covering all major modules.
- `docker-compose.yml`: full stack. Test profile ✅. Default profile ✅.
- `deploy/k8s/`: namespace, ConfigMap, Secret, PVC, Deployment, **Service (ClusterIP)**, **HPA (v2 CPU/memory)**, kustomization. (B053)
- `migrations/`: `001_extension.sql`, `002_hypertables.sql`.
- `Cargo.toml` + 1 crate: `cryptobot-core` with `lib.rs` stub + unit test. `cargo build` + `cargo test` clean. Sibling crates deleted until each gets a manifest.
- `pyproject.toml`: setuptools build + CLI entry.

## Notable resolved discrepancies (audit v1 → v2)

- ~~`configs/base.yaml` keys do not match Settings field names~~ → mitigated by `_flatten_yaml` + `Settings.from_yaml_safe` (B050).
- ~~`configs/base.yaml` `ml.models.direction.type: lightgbm`~~ → changed to `sklearn_logreg`; `lightgbm` dep removed (B055/B058).
- ~~`configs/base.yaml` `strategies.enabled` not read~~ → `load_strategies_from_config` added (B057/B059).
- ~~`plan.md` Phase 4 claimed `[x] ML-driven strategy` but file missing~~ → `ml_strategy.py` created (B054).
- ~~`deploy/k8s/` missing Service/HPA~~ → both added (B053).
- ~~Docker compose default profile broken~~ → monitoring dirs scaffolded.
- ~~Risk notional check broken for market orders~~ → fixed (B038/B060/B061).
- ~~Backtest equity double-counts unrealized PnL~~ → fixed (B063/B064).
- ~~ML walk-forward data leakage~~ → fixed (B065).
- ~~Health check `settings.exchange.symbols` empty~~ → fixed (B044/B066).
- ~~SQLite DB at `/app/cryptobot.db` not in mounted volume~~ → fixed (B069).

## Remaining real gaps

- ~~`Cargo.toml [workspace] members` lists 7; only 1 has a manifest. `cargo build` fails until trimmed or per-crate manifests added.~~ → **resolved 2026-08-04** (workspace re-expanded to 7 real crates — core/features/risk/stats/orderbook/backtest/py — with PyO3 0.29; fmt/clippy/test green). Note: `.cargo/config.toml` deliberately has no `target-cpu=native` (proc-macro SIGILL across runner CPUs).
- ~~6 dead empty dirs under `src/cryptobot/`: `allocator/`, `altdata/`, `api/`, `exchanges/`, `funding/`, `xmr/`.~~ → **resolved 2026-07-31** (dirs removed).
- ~~`monitoring/__init__.py` eager-imports metrics~~ → resolved 2026-07-31 (B051: no-op `_NoOpMetric` stub + lazy aiohttp; `monitoring/__init__.py` lazy via `__getattr__`).
- ~~ML models `volatility.py`, `regime.py`, `ensemble.py` still missing.~~ → **resolved** (all implemented; volatility/regime disabled in YAML until validated).

## Confidence per subject

- High: directory tree, file presence, line counts, public class/symbol names, recent bug fixes.
- Medium: behavior of modules not exercised end-to-end.
- Low: live Binance behavior under load, Rust perf layer.

## Recent changes

- **Audit v2 2026-07-31**: Created `26_Audit_2026-07-31_v2.md`. Refreshed stale memory docs (01, 02, 04, 05, 06, 07, 09, 11, 13, 14, 15, 17, 19, 20, 21, 22, 25). Marked v1 audit superseded.
- Prior: B051-B069 fixes landed via `04bfecf / 90efd8f / 0337acb / adc5334 / 97b13f6 / 519fc7f` — K8s Service+HPA, ml_strategy, data/features, lightgbm drop, config fixes, registry load_strategies_from_config, monitoring/health runtime updates, aiohttp session reuse.
- See `23_Repository_History.md`, `24_Agent_Log.md`, `13_Bug_Tracker.md`.