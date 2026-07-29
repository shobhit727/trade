# 23. Repository History

> **Last Updated**: 2026-07-29 (audit pass)
> **Confidence**: Git history not present in this workspace; entries below are session-level snapshots.

## Original state (pre-session)

- Repository mostly planning-stage scaffolding.
- `plan.md` (51 KB) describes a 120+ module crypto quant platform.
- `PROJECT_MEMORY/00-14` documents aspirational architecture.
- `core/bus.py`, `core/clock.py`, `core/portfolio.py` were implemented but `PROJECT_MEMORY` listed them as "Not Implemented".
- `tests/unit/test_core_foundation.py` referenced non-existent APIs (`SubscriptionMode`, `update_on_trade`).
- No `Dockerfile`, no `requirements/test.txt`, no `.dockerignore`.
- `requirements/prod.txt` pinned to versions incompatible with Python 3.11+ and contained `monero-rpc==0.3.0` (no PyPI wheel).

## Session 2026-07-29 (audit)

### Code fixes

- `backtest/metrics.py` — imports, sortino, drawdown guard.
- `backtest/engine.py` — Position/PositionSide imports, win/loss guards, profit factor formula.
- `backtest/validation.py` — `run_validation` returns report.
- `data/storage.py` — `timedelta` import.
- `data/cleaning.py` — None/empty guards.
- `monitoring/health.py` — async detection, false-as-unhealthy.
- `strategies/base.py` — correct `OrderEvent` construction.
- `core/clock.py` — `time` import.
- `core/state.py` — graceful SQLite fallback.

### New modules

- `risk/{limits,sizing,kill_switch,correlation,manager}.py`.
- `execution/{engine,algorithms}.py` + `execution/venue/{base,simulated}.py`.
- `cli/main.py`.
- `tests/unit/test_core_foundation.py` smoke tests.

### Build / Docker

- `Dockerfile` (`python:3.14-slim`, multi-stage).
- `requirements/test.txt`, `requirements/prod.txt` updated.
- `.dockerignore` minimal context.
- `docker-compose.yml` `cryptobot-test` service in profile `test`.

### Memory

- `PROJECT_MEMORY/00-24` rewritten/created to reflect verified code state.

## Verification

- `python3 -m py_compile` passes on all edited files.
- `docker compose --profile test config` parses.
- Docker run blocked by host daemon instability (qemu crash).
- Local smoke run via `python3 -m py_compile` only; full pytest run requires Docker.

## Confidence

- High.
