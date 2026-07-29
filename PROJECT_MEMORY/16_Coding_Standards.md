# 16. Coding Standards

> **Last Updated**: 2026-07-29 (audit pass)
> **Confidence**: High.

## Verified conventions

- Python 3.14. Modules using `from __future__ import annotations` keep working at runtime.
- Type hints on every function signature.
- `Decimal` for money, `datetime.utcnow()` for timestamps.
- Async-first in event/bus/clock/risk/execution paths.
- Pydantic v2 for config (`config.py`); `BaseSettings` with `env_prefix`.
- `dataclass` for internal state and event payloads.
- Snake_case file names, PascalCase classes, snake_case functions.
- Public API re-exported via package `__init__.py`.

## Required for new code

- No comments unless explicitly asked (per user instruction).
- No new external dependencies without explicit approval.
- Type hints on every signature.
- Add smoke test in `tests/unit/` if module has public behavior.
- File references in form `path:line`.

## Style nits to clean later

- `print(...)` in `core/clock.py`, `backtest/engine.py`, `strategies/base.py`, `market_data/manager.py`.
- Bare `try/except Exception` in places.
- Unused imports.

## Forbidden

- Hard-coding secrets.
- Returning `None` from top-level async entry points.
- Bypassing `risk/manager.py` checks (must go through `ExecutionEngine`).
- Using `prometheus_client.Counter` for values that can be negative.

## Confidence

- High.
