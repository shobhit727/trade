# 22. Improvement Ideas

> **Last Updated**: 2026-07-29 (audit pass)
> **Confidence**: Suggestions, not commitments.

## Quick wins (1-2 hours each)

- Align `configs/base.yaml` with `Settings` field names.
- Add `pyproject.toml` + `setuptools-scm`.
- Add `pytest.ini` with `asyncio_mode = auto`.
- Add `Makefile` (`make test`, `make lint`, `make run`).
- Bounce retry jitter so `sleep_time ≥ 0`.
- Replace `Counter` with `Gauge` for realized PnL.
- Replace `print(...)` in `core/clock.py`, `backtest/engine.py`, `strategies/base.py` with `get_logger`.
- Add `USER` directive in `Dockerfile` for non-root runtime.
- Add blank-env defaults in `docker-compose.yml` to silence warnings.

## Medium (1-2 days)

- Replace `backtest/validation.py` stubs with rolling-window logic.
- Add `cryptobot.execution.venue.binance` adapter using `ccxt.async_support`.
- Add `cryptobot.ml.features` with at least one technical indicator module.
- Add `cryptobot.ml.models.direction` v0 (LightGBM).
- Wire `cryptobot.cli.main` `backtest` to `BacktestEngine`.

## Large (1+ weeks)

- Implement `crates/cryptobot-features` SIMD features.
- Wire `cryptobot.ml` online inference + drift detection.
- Add walk-forward service.
- Implement `cryptobot.execution.algorithms` server with TWAP/VWAP/POV/IS algos.

## Architectural

- DI container (`dependency-injector`).
- Replace global singletons with `Settings` + lifetime.
- Add OpenTelemetry tracing for `EventBus.publish`/`_dispatch`.
- Add `prometheus_client` switch: `MetricsCollector` interface so non-Prometheus backend can be used.

## Nice-to-have

- `cryptobot dashboard` TUI command.
- `cryptobot replay` command for replaying events from `state.py` DB.
- `pre-commit` config with `ruff` + `black`.
- `cryptobot` CLI command to regenerate `configs/base.yaml` from `Settings`.

## Confidence

- High: each item is identifiable.
