# 10. Build System

> **Last Updated**: 2026-07-29 (audit pass)
> **Confidence**: High (verified).

## Build artifacts (verified)

| Artifact | Status | Notes |
|----------|--------|-------|
| `Dockerfile` | Present | Multi-stage (`base`, `test`, `production`). ARG `REQUIREMENTS` swaps deps list. `python:3.14-slim`. |
| `docker-compose.yml` | Present | Names: `timescaledb`, `redis`, `prometheus`, `alertmanager`, `grafana`, `loki`, `promtail`, `cryptobot`, `cryptobot-paper`, `cryptobot-backtest`, `cryptobot-test`, `nginx`. Profiles: `paper`, `backtest`, `test`, `tracing`. |
| `Cargo.toml` (root) | Present | No crate members, no dependencies. |
| `crates/cryptobot-core/Cargo.toml` | Present | Manifest only, no `src/`. |
| `pyproject.toml` | Missing | Pydantic settings still load via YAML directly. |
| `setup.py` | Missing | No pip-installable package. |
| `migrations/` | Empty | Compose mounts empty dir into TimescaleDB entrypoint. |
| `.dockerignore` | Present | Minimal context (Dockerfile, requirements, src, tests, configs, migrations, feature-status). |

## What the Dockerfile does

- Base: `python:3.14-slim`, installs `build-essential`, `curl`, `gcc`, `g++`, `libgomp1`.
- Upgrades pip, setuptools, wheel.
- Installs `requirements/$REQUIREMENTS` (ARG).
- Copies project root.
- `test` target: `pytest -q tests/unit/test_core_foundation.py`.
- `production` target: `python -m cryptobot.cli.main paper`.

## Build/test commands

- Tests: `docker compose --profile test run --rm cryptobot-test`.
- Production: `docker compose up cryptobot`.
- Local Python: `PYTHONPATH=src python3 -m cryptobot.cli.main paper`.

## Build failures observed

- Earlier attempt with `monero-rpc==0.3.0` failed.
- Docker Desktop host sometimes aborts build with `qemu: process terminated unexpectedly` (host-side, not code).

## Recommendations

- Add `pyproject.toml` for `pip install -e .`.
- Add `setup.cfg` / `pytest.ini` for `asyncio_mode = auto`.
- Add `Makefile` targets for `build`, `test`, `lint`, `run`.
- Multi-arch build (x86_64, ARM64) pinned to actual deployment.

## Confidence

- High: all files inspected.
- Low: behavior of full ML build (deps unverified under Python 3.14).
