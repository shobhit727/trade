# 11. Testing

> **Last Updated**: 2026-07-31 (audit v2)
> **Confidence**: High for file presence; Medium for exact test count (no pytest in audit env).

## What exists

`tests/unit/` — **22 Python test files** plus `__pycache__`. No `tests/integration/` or `tests/fixtures/` beyond an empty marker.

Verified test files:

```
test_adverse_selection.py
test_binance_venue.py
test_backtest_data.py
test_backtest_runner.py
test_cli.py
test_config_loading.py
test_core_clock_portfolio.py
test_core_foundation.py
test_core_state.py
test_data_cleaning.py
test_execution_algorithms.py
test_health_server.py
test_latency_metrics.py
test_market_data_manager.py
test_monitoring_alerting.py
test_monitoring_dashboard.py
test_monitoring_health.py
test_risk_helpers.py
test_risk_manager_str.py
test_smart_order_router.py
test_strategies_ml.py
test_strategies_validation_reporting.py
```

## Verified behaviors (from prior audit reads)

| Test (representative) | Asserts |
|------|---------|
| `test_core_foundation.py` | subscribe → publish delivers to single async handler; history returns event; unsubscribe returns True |
| `test_retry_decorator` | `retry(max_attempts=3, backoff_factor=0)` succeeds on attempt 3 |
| `test_execution_engine_simulated_fill` | `submit_order` returns `OrderEvent(filled_quantity == 1, avg_fill_price == 100)` from `SimulatedVenue` |
| `test_backtest_toy_fill_flow` | buy → ticker → sell produces exactly 1 trade with `pnl == 10` |
| `test_smart_order_router.py` | price-rank, latency-rank, fallback, split behavior |
| `test_adverse_selection.py` | mid-move cancel, spread-widening cancel, toxicity-spike cancel |
| `test_binance_venue.py` | ccxt async instantiation + credential guards |
| `test_health_server.py` | `/health` JSON and `/metrics` Prometheus text |
| `test_strategies_ml.py` | `MLStrategy` retrain cadence, threshold long/short signals |
| `test_latency_metrics.py` | `record_venue_quote_latency`, `record_routing_decision`, `record_execution_latency` |

## Container execution

- `docker compose --profile test run --rm cryptobot-test` runs the unit suite inside a `python:3.14-slim` image.
- Dockerfile test target: `pytest -q tests/unit/`.

## Coverage gaps

- No tests for `core/portfolio.py` (real paths beyond `core_clock_portfolio.py` smoke).
- No integration tests (TimescaleDB, Redis, Prometheus, real Binance).
- No property-based tests (hypothesis).
- No regression tests on backtest metrics vs prior runs.

## Strategy for new tests

- One file per package.
- Smoke tests only; no harness mocking beyond deterministic fakes.
- Use real APIs end-to-end.

## Confidence

- High: existing test files enumerated.
- Medium: passing count (no pytest execution in audit env — flake / host could mask issues).
- Low: docker run on this specific host (Docker Desktop macOS sometimes aborts at qemu stage; reported in earlier sessions).
