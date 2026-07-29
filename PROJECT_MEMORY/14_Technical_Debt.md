# 14. Technical Debt

> **Last Updated**: 2026-07-29 (audit pass)
> **Confidence**: High.

## Categories

### Code quality

- `strategies/base.py` prints on import inside `StrategyRegistry.__new__`.
- `backtest/engine.py` mixes `print` with logic.
- `monitoring/health.py:_process_result` mutates `_component_health` while iterating via `auto_register` (only in new code path).
- `monitoring/metrics.py` uses `Counter` for realized PnL, which cannot decrement.
- `utils/decorators.py` jitter can produce negative sleep.
- `utils/decorators.py` `circuit_breaker` sync wrapper uses `run_until_complete` inside running loop.

### Architecture

- `Settings(extra="ignore")` masks YAML mismatch.
- `core/state.py` and `core/portfolio.py` both hold account state. Duplicating updates.
- `execution/venue/simulated.py` ignores slippage/fees.
- `risk/manager.py` is global; not DI-friendly.
- `market_data.manager.BinanceWSClient` builds URLs from empty defaults → empty subscription.

### Performance

- `backtest/engine.py` `_handle_order_fill` is O(N) per fill.
- `data/cleaning.py` `vol_zscore` not accelerated.
- `core/clock.py` `SimulatedClock._notify_waiters` is O(W) per step.
- `data/ingestion.py` opens `aiohttp` sessions per call.

### Security

- `BINANCE_API_KEY`/`SECRET` env vars empty in compose defaults.
- `monitoring/alerting.py` may serialize webhook URLs.
- `risk/manager.py` reads `settings.risk.kill_switch_daily_loss_pct` at construction; restart needed for changes.

### Maintainability

- ML pipeline empty.
- Live exchange adapter missing.
- No `pyproject.toml` / `setup.py`.
- No CI, no `ruff`, no `mypy`.
- Many modules have unused imports.

### Test coverage

- 4 smoke tests only.
- No integration, no property-based.

## Critical debt (highest impact)

| Item | Effort | Priority |
|------|--------|----------|
| Align `configs/base.yaml` with `Settings` field names | 0.5 day | High |
| Add `pyproject.toml` for `pip install -e .` | 0.5 day | High |
| Implement real walk-forward + Monte Carlo | 3-5 days | High |
| Implement ML feature pipeline (one indicator module) | 1-2 days | High |
| Implement `execution/venue/binance.py` (ccxt adapter) | 1-2 days | High |
| Replace `Counter` with `Gauge` for realized PnL | 1 hour | High |
| Bound `retry` jitter so sleep_time ≥ 0 | 0.5 hour | High |
| Fix `circuit_breaker` sync wrapper (use `nest_asyncio` or always async) | 0.5 hour | High |
| Add `core/clock.py` `SimulatedClock` lock around pause/resume | 0.5 hour | Medium |
| Add blank-env values in compose, remove warning noise | 0.5 hour | Medium |
| Add `pytest.ini` with `asyncio_mode=auto` | 0.5 hour | Medium |
| Remove `print(...)` from `core/clock.py`, `backtest/engine.py`, `strategies/base.py` | 1 hour | Medium |
| Add `requirements/test.txt` cd into `Dockerfile` test target | 0.5 hour | Done |
| Remove `monero-rpc` references | 0.1 hour | Done |
| Add explicit `Venue.submit_order` params for slippage/fees | 1 day | Medium |

## Removal candidates

- `numba` from `requirements/prod.txt` (declared but unused).
- `top-of-file print()` in `strategies/base.py`.

## Risk

- Bypassing `risk/manager.py` would be catastrophic. No guard today.
- `state_manager` silent no-op on missing `_sqlite3` is invisible to users.

## Confidence

- High.
