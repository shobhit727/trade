# 11. Testing

> **Last Updated**: 2026-07-29 (audit pass)
> **Confidence**: High.

## What exists

- `tests/unit/test_core_foundation.py` — 4 smoke tests.
- `tests/integration/` — directory empty.
- `tests/fixtures/` — directory empty.

## Tests run (verified by reading)

```python
async def test_event_bus_subscription_and_history()
async def test_retry_decorator()
async def test_execution_engine_simulated_fill()
async def test_backtest_toy_fill_flow()
```

Each test exercises a real public API and asserts concrete behavior.

## Verified behaviors

| Test | Asserts |
|------|---------|
| `test_event_bus_subscription_and_history` | subscribe → publish delivers to single async handler; `get_history(event_type=...)` returns the event; `unsubscribe` returns True |
| `test_retry_decorator` | `retry(max_attempts=3, backoff_factor=0)` succeeds on attempt 3 |
| `test_execution_engine_simulated_fill` | `submit_order` returns a `OrderEvent` with `filled_quantity == 1` and `avg_fill_price == 100` from `SimulatedVenue` |
| `test_backtest_toy_fill_flow` | buy → ticker → sell produces exactly 1 trade with `pnl == 10` |

## Verified compile

- `python3 -m py_compile tests/unit/test_core_foundation.py` passes.

## Container execution

- `docker compose --profile test run --rm cryptobot-test` attempted on host.
- Build proceeded past dep install but host Docker daemon crashed at `apt-get install` (`qemu` abort). Subsequent runs may succeed if Docker Desktop is stable.

## Coverage gaps

- No tests for `core/portfolio.py`, `core/state.py`, `core/clock.py`, `data/cleaning.py`, `data/storage.py`, `monitoring/*`, `risk/*`, `strategies/*`.
- No integration tests (TimescaleDB, Redis, Prometheus).
- No property-based tests.
- No regression tests on backtest metrics.

## Strategy for new tests

- One file per package.
- Smoke tests only; no harness mocking.
- Use real APIs end-to-end.

## Confidence

- High: existing tests.
- Low: docker run post-host-recovery.
