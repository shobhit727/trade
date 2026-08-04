# 10. Build System

> **Last Updated**: 2026-08-04 (full Rust workspace green)
> **Confidence**: High.

## Build artifacts (verified)

| Artifact | Status | Notes |
|----------|--------|-------|
| `Dockerfile` | ✅ | Multi-stage (`base`, `test`, `production`). ARG `REQUIREMENTS` swaps deps list. `python:3.14-slim`. |
| `docker-compose.yml` | ✅ | Names: `timescaledb`, `redis`, `prometheus`, `alertmanager`, `grafana`, `loki`, `promtail`, `cryptobot`, `cryptobot-paper`, `cryptobot-backtest`, `cryptobot-test`, `nginx`. Profiles: `paper`, `backtest`, `test`, `tracing`. Default profile validates; monitoring subdirs scaffolded. |
| `Cargo.toml` (root) | ✅ | Workspace manifest at repo root with 7 members (`cryptobot-core`, `cryptobot-backtest`, `cryptobot-features`, `cryptobot-risk`, `cryptobot-stats`, `cryptobot-orderbook`, `cryptobot-py`) + `[workspace.dependencies]`. Builds with stable Rust 1.97+. `cargo fmt --check`, `cargo clippy --workspace --all-targets -- -D warnings`, `cargo test --workspace` (31 tests) all pass (verified 2026-08-04). PyO3 0.29; `cryptobot_py` extension registers `features`, `risk`, `orderbook`, `backtest` submodules. |
| `crates/` | ✅ | 7 crates with full source (backtest, features, risk, stats, orderbook, py, core). |
| `pyproject.toml` | ✅ | setuptools build + `cryptobot` CLI entry point. |
| `setup.py` | n/a | Not used. |
| `migrations/` | ✅ | `001_extension.sql`, `002_hypertables.sql`. Compose mounts the directory into TimescaleDB entrypoint. |
| `.dockerignore` | ✅ | Minimal context (Dockerfile, requirements, src, tests, configs, migrations, `PROJECT_MEMORY/12_Feature_Status.md`). |

## What the Dockerfile does

- Base: `python:3.14-slim`, installs `build-essential`, `curl`, `gcc`, `g++`, `libgomp1`.
- Upgrades pip, setuptools, wheel.
- Installs `requirements/$REQUIREMENTS` (ARG).
- Copies project root.
- `test` target: `pytest -q tests/unit/`.
- `production` target: `python -m cryptobot.cli.main paper`.
- HEALTHCHECK: hits `localhost:8080/health` (served by `utils.health_server.HealthServer` started via `cryptobot serve` or first-time `bot`).

## Build/test commands

- Tests: `docker compose --profile test run --rm cryptobot-test`.
- Production: `docker compose up cryptobot`.
- Local Python: `PYTHONPATH=src python3 -m cryptobot.cli.main paper`.
- Lint: `ruff check src/ tests/`.

## Build failures observed historically

- Earlier attempt with `monero-rpc==0.3.0` failed → removed (B019).
- Docker Desktop host sometimes aborts build with `qemu: process terminated unexpectedly` (host-side, not code).

## Recommendations

- Delete or document the dead empty dirs under `src/cryptobot/` (Rust workspace is fully populated and green).
- Add `seccomp/` profile files (dir exists but empty).

## Confidence

- High: all files inspected.
- Low: full ML build behavior under Python 3.14 (deps unverified at runtime in this env).
