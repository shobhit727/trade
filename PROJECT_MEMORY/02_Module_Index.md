# 02. Module Index

> **Last Updated**: 2026-07-29 (audit pass)
> **Confidence**: High (verified by directory walk).

## Actual project tree

```
src/cryptobot/  (2 files)
  config.py                # Settings management (Pydantic v2)
  __init__.py
  core/  (6 files)
    __init__.py
    events.py              # 100+ event types
    bus.py                 # EventBus (subscribe, publish, history, replay)
    clock.py               # Realtime / Simulated / Accelerated clocks
    state.py               # StateManager (SQLite; degrades without _sqlite3)
    portfolio.py           # PortfolioManager
  data/  (4 files)
    __init__.py
    ingestion.py           # OHLCV/Tick/TradeData, BinanceDataIngestion
    storage.py             # TimescaleDBStorage, ParquetStorage, HybridStorage
    cleaning.py            # DataCleaner, validate_ohlcv, detect_outliers_zscore, fill_missing_bars
  strategies/  (3 files)
    __init__.py
    base.py                # BaseStrategy, StrategyRegistry, MeanReversionStrategy placeholder
    registry.py            # re-export of registry
  risk/  (6 files)
    __init__.py
    manager.py             # RiskManager, RiskCheckResult
    limits.py              # RiskLimits (from config)
    sizing.py              # fixed_fraction_size, kelly_size, volatility_target_size
    kill_switch.py         # KillSwitch
    correlation.py         # max_abs_correlation
  execution/  (3 files + venue/)
    __init__.py
    engine.py              # ExecutionEngine
    algorithms.py          # twap_slices, vwap_slices, pov_quantity
    venue/
      __init__.py
      base.py              # Venue (abstract)
      simulated.py         # SimulatedVenue
  backtest/  (4 files)
    engine.py              # BacktestEngine, BacktestResult, TradeRecord
    metrics.py             # PerformanceMetrics, BacktestMetricsRecorder, BacktestResults
    simulator.py           # FillSimulator + factory
    validation.py          # ValidationFramework (WFA + MC; stubs)
  monitoring/  (5 files)
    __init__.py
    metrics.py             # Prometheus metrics + helpers + MetricsCollector
    alerting.py            # AlertManager + Telegram/Discord/Email/PagerDuty channels
    health.py              # HealthMonitor + HealthChecker subclasses
    dashboard.py           # Dashboard JSON builders
  cli/  (2 files)
    __init__.py
    main.py                # argparse CLI with backtest/validate/paper
  market_data/  (1 file)
    manager.py             # Binance WS client
  utils/  (4 files)
    __init__.py
    logging.py             # structlog wrapper with context vars
    decorators.py          # retry, timeout_decorator, circuit_breaker, CircuitBreaker
    types.py               # Candle, OrderBook, Trade, TickData, OHLCVBar, PerformanceMetrics

tests/  (1 file)
  unit/test_core_foundation.py

crates/  (1 file)
  cryptobot-core/Cargo.toml       # manifest only, no src/

configs/base.yaml                  # ⚠ keys do not match Settings; see doc 01

Dockerfile, docker-compose.yml, .dockerignore

requirements/prod.txt, requirements/test.txt
```

## Verified file-level LOC

| File | LOC |
|------|-----|
| `monitoring/metrics.py` | 817 |
| `monitoring/health.py` | 806 |
| `monitoring/alerting.py` | 680 |
| `monitoring/dashboard.py` | 638 |
| `data/storage.py` | 736 |
| `core/events.py` | 521 |
| `core/state.py` | 468 |
| `data/cleaning.py` | 466 |
| `core/portfolio.py` | 402 |
| `data/ingestion.py` | 372 |
| `market_data/manager.py` | 375 |
| `backtest/engine.py` | 339 |
| `backtest/simulator.py` | 290 |
| `core/clock.py` | 337 |
| `utils/decorators.py` | 233 |
| `utils/logging.py` | 235 |
| `utils/types.py` | 212 |
| `backtest/metrics.py` | 210 |
| `core/bus.py` | 209 |
| `config.py` | 186 |
| `monitoring/__init__.py` | 173 |
| `test_core_foundation.py` | 100 |

## Status legend used in this audit

- ✅ Compile-only verified.
- ⚠️ Compile but known issues (e.g., Prometheus Counter with negative PnL).
- 🔲 Missing or empty.

## Highest-impact missing items

- `data/features.py` (planned).
- `src/cryptobot/ml/` (empty).
- `src/cryptobot/execution/venue/binance.py` (live adapter).
- Concrete `strategies/mean_reversion.py`, `trend_following.py`, `stat_arb.py`, `funding_arb.py`, `market_making.py`.
- `crates/cryptobot-*` Rust source.
- `pyproject.toml` / `setup.py`.
- `scripts/`, `seccomp/`, `migrations/` content (mostly empty dirs).

## Confidence

- High: file presence, public symbols, line counts.
- Medium: behavior of untouched modules.
- Low: intended Rust surface and ML pipeline.
