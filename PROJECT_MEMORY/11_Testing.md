# 11. Testing

> **Last Updated**: 2026-08-06 (audit)
> **Confidence**: High — `413 passed, 4 skipped` locally (Python 3.14, 6.6s), 31 Rust tests green, CI green.

## What exists

`tests/unit/` — **44 Python test files**. No `tests/integration/` or `tests/fixtures/` beyond an empty marker.

Test files (44):

```
test_adverse_selection.py
test_backtest_data.py
test_backtest_metrics.py
test_backtest_runner.py
test_backtest_simulator.py
test_binance_venue.py
test_cli.py
test_config_loading.py
test_core_clock_portfolio.py
test_core_foundation.py
test_core_state.py
test_data_cleaning.py
test_data_ingestion.py
test_data_storage.py
test_execution_algorithms.py
test_execution_costs.py
test_funding_sim.py
test_health_server.py
test_latency_metrics.py
test_live_paper_harness.py
test_market_data_manager.py
test_ml_auto_retrain.py
test_ml_ensemble.py
test_ml_inference.py
test_ml_regime.py
test_ml_training.py
test_ml_volatility.py
test_monitoring_alerting.py
test_monitoring_dashboard.py
test_monitoring_health.py
test_monitoring_lazy_imports.py
test_risk_extended.py
test_risk_helpers.py
test_risk_manager_str.py
test_smart_order_router.py
test_strategies_base.py
test_strategies_mean_reversion.py
test_strategies_ml.py
test_strategies_ml_strategy.py
test_strategies_registry.py
test_strategies_trend_following.py
test_strategies_validation_reporting.py
test_utils_logging.py
test_utils_types.py
```

## Verified behaviors (representative)

| Test (representative) | Asserts |
|------|---------|
| `test_core_foundation.py` | subscribe → publish delivers to single async handler; history returns event; unsubscribe returns True |
| `test_execution_engine_simulated_fill` | `submit_order` returns `OrderEvent(filled_quantity == 1, avg_fill_price == 100)` from `SimulatedVenue` |
| `test_backtest_toy_fill_flow` | buy → ticker → sell produces exactly 1 trade with `pnl == 10` |
| `test_smart_order_router.py` | price-rank, latency-rank, fallback, split behavior |
| `test_adverse_selection.py` | mid-move cancel, spread-widening cancel, toxicity-spike cancel |
| `test_binance_venue.py` | ccxt async instantiation + credential guards |
| `test_health_server.py` | `/health` JSON and `/metrics` Prometheus text |
| `test_live_paper_harness.py` | Phase 3 funding harness: WS/fapi poll, carry accumulation, CSV log |
| `test_execution_costs.py` | Phase 4 cost model round-trip math |
| `test_realistic_venue.py` | limit fills at limit price, partial fills, adverse selection (in `test_adverse_selection.py` family) |
| `test_monitoring_lazy_imports.py` | no-op fallbacks when `prometheus_client` absent (2 skips when present) |
| `test_ml_{volatility,regime,ensemble}.py` | EWMA/GARCH/realized, HMM/k-means/GMM, weighted voting |

## Container execution

- `docker compose --profile test run --rm cryptobot-test` runs the unit suite inside a `python:3.14-slim` image.
- Dockerfile test target: `pytest -q tests/unit/`.
- CI `unit` job: `pytest -q --tb=short --cov=cryptobot --cov-report=term-missing --timeout=60` (413 passed, 4 skipped).

## Coverage gaps

- No integration tests (TimescaleDB, Redis, Prometheus, real Binance).
- No property-based tests (hypothesis).
- No regression tests on backtest metrics vs prior runs.

## Strategy for new tests

- One file per package.
- Smoke tests only; no harness mocking beyond deterministic fakes.
- Use real APIs end-to-end.

## Confidence

- High: 413/4 local run + green CI on `main` (Lint, Rust, unit, docker-test, buildx amd64+arm64).
