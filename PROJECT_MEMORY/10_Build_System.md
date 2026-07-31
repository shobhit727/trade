# 10. Build System

> **Last Updated**: 2026-07-31 (audit v2)
> **Confidence**: High.

## Build artifacts (verified)

| Artifact | Status | Notes |
|----------|--------|-------|
| `Dockerfile` | ✅ | Multi-stage (`base`, `test`, `production`). ARG `REQUIREMENTS` swaps deps list. `python:3.14-slim`. |
| `docker-compose.yml` | ✅ | Names: `timescaledb`, `redis`, `prometheus`, `alertmanager`, `grafana`, `loki`, `promtail`, `cryptobot`, `cryptobot-paper`, `cryptobot-backtest`, `cryptobot-test`, `nginx`. Profiles: `paper`, `backtest`, `test`, `tracing`. Default profile validates; monitoring subdirs scaffolded. |
| `Cargo.toml` (root) | ⚠️ | Workspace manifest with 7 declared members + `[workspace.dependencies]`. Only `crates/cryptobot-core/Cargo.toml` exists; the other 6 members lack manifests. `cargo build` from root fails. |
| `crates/cryptobot-core/Cargo.toml` | ⚠️ | Manifest present; `src/{events,math,time,types}/` empty subdirs; no `lib.rs` so the package compiles but produces no artifact. |
| `crates/cryptobot-{backtest,features,orderbook,py,risk,stats}/Cargo.toml` | 🔲 | No manifest. Empty `src/`, `benches/`, `tests/` only. |
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

- Trim `Cargo.toml [workspace] members` to `["crates/cryptobot-core"]` until Rust crates are populated, or add minimal `Cargo.toml` per empty crate.
- Delete or document the 6 dead empty dirs under `src/cryptobot/`.
- Add `USER` directive in `Dockerfile` (non-root runtime).
- Add `seccomp/` profile files (dir exists but empty).

## Confidence

- High: all files inspected.
- Low: full ML build behavior under Python 3.14 (deps unverified at runtime in this env).
