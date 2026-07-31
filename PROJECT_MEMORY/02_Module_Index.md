# 02. Module Index

> **Last Updated**: 2026-07-31 (audit v2; re-verified full src/ tree)
> **Confidence**: High (verified by directory walk + LOC).

## Actual project tree (Python)

```
src/cryptobot/
  config.py                       # Pydantic v2 BaseSettings; _flatten_yaml + from_yaml_safe
  __init__.py
  core/
    events.py                     # 40+ event types
    bus.py                        # EventBus (async + sync, wildcard, filter, history, replay)
    clock.py                      # Realtime / Simulated / Accelerated + ClockFactory
    state.py                      # StateManager (SQLite; /app/data path in container)
    portfolio.py                  # PortfolioManager (killswitch wire, daily-PnL reset)
    __init__.py
  data/
    ingestion.py                  # OHLCV/Tick/TradeData, BinanceDataIngestion, _ensure_session reuse
    storage.py                    # TimescaleDBStorage, ParquetStorage, HybridStorage
    cleaning.py                   # DataCleaner + validate_ohlcv + detect_outliers_zscore + fill_missing_bars
    features.py                   # re-export of cryptobot.ml.features (B056)
    __init__.py
  strategies/
    base.py                       # BaseStrategy + StrategyRegistry
    registry.py                   # 6-way _STRATEGY_REGISTRY_MAP + load_strategies_from_config
    mean_reversion.py             # Z-score + RSI + Bollinger
    trend_following.py            # EMA + ADX + ATR trailing
    stat_arb.py                   # Pairs (rolling hedge, corr gate, z-score)
    funding_arb.py                # Spot vs perp + funding + basis
    market_making.py              # Avellaneda-Stoikov + AdverseSelectionGuard
    ml_strategy.py                # MLStrategy + MLStrategyConfig (uses DirectionClassifier)
    __init__.py
  risk/
    manager.py                    # Pre-trade: kill switch + notional (+>0 guard) + exposure
    limits.py                     # RiskLimits from config
    sizing.py                     # fixed_fraction, kelly, volatility_target
    kill_switch.py                # KillSwitch on portfolio signal
    correlation.py                # max_abs_correlation helper
    __init__.py
  execution/
    engine.py                     # ExecutionEngine + risk gate + build_venue factory
    algorithms.py                 # TWAP/VWAP/POV/IS/Iceberg/sweep/arrival/vwap_schedule/slicer_for
    router.py                     # SmartOrderRouter (price + latency rank, fallback, split)
    adverse_selection.py          # AdverseSelectionGuard + QueuePosition + TopOfBook + attach_to_engine
    venue/
      base.py                     # Abstract Venue
      simulated.py                # In-memory with slippage + commission
      binance.py                  # ccxt.async_support; sandbox; retries; guards
      __init__.py
    __init__.py
  backtest/
    engine.py                     # Event-driven BacktestEngine + TradeRecord
    metrics.py                    # Sharpe, Sortino, drawdown (zero-guard), PF
    simulator.py                  # FillSimulator + factory
    validation.py                 # Real walk-forward (rolling + embargo) + MC block perm + deflated Sharpe
    reporting.py                  # HTML tearsheet (stdlib)
    runner.py                     # OHLCV → strategy → ExecutionEngine → SimulatedVenue end-to-end
    data.py                       # load_csv + load_parquet + load_timescale + synthetic
  monitoring/
    metrics.py                    # Prometheus (Gauge for PnL) + record_* helpers
    alerting.py                   # AlertManager + Telegram/Discord/Email/PagerDuty (lazy init, idempotent stop)
    health.py                     # HealthMonitor + HealthChecker; runtime register/unregister/update_check_interval
    dashboard.py                  # Grafana JSON builders
    __init__.py
  cli/
    main.py                       # argparse (validate/paper/bot/serve) with real logic
    __init__.py
  market_data/
    manager.py                    # BinanceWSClient (fallback to default_symbol + ["1m"])
  ml/
    features.py                   # 8 features (returns, RSI, MACD, ATR ratio, BB, log vol)
    online.py                     # WalkForwardTrainer (purged) + DriftDetector
    models/
      direction.py                # sklearn logreg + numpy fallback; train stats persistence
    __init__.py
  utils/
    logging.py                    # structlog wrapper
    decorators.py                 # retry (jitter ≥ 0) + timeout_decorator + circuit_breaker
    types.py                      # Candle, OrderBook, Trade, OHLCVBar, PerformanceMetrics
    health_server.py              # stdlib ThreadingHTTPServer /health + /metrics
    __init__.py

tests/unit/                        # 22 test files
crates/                            # Workspace lists 7; only cryptobot-core has Cargo.toml
src/cryptobot/                     # 6 dead empty dirs: allocator/ altdata/ api/ exchanges/ funding/ xmr/
```

## Verified approximate LOC (recent audit)

| File | LOC |
|------|-----|
| `monitoring/metrics.py` | 817 |
| `monitoring/health.py` | 806 |
| `monitoring/alerting.py` | 680 |
| `monitoring/dashboard.py` | 638 |
| `data/storage.py` | 736 |
| `core/events.py` | 521 |
| `core/state.py` | 468 |
| `data/cleaning.py` | 476 |
| `core/portfolio.py` | 402 |
| `data/ingestion.py` | 384 |
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
| `ml/models/direction.py` | 156 |
| `ml/features.py` | 154 |
| `strategies/market_making.py` | 179 |
| `strategies/trend_following.py` | 102 |
| `strategies/stat_arb.py` | 118 |
| `strategies/mean_reversion.py` | 65 |
| `strategies/funding_arb.py` | 68 |
| `strategies/ml_strategy.py` | 145 |
| `strategies/base.py` | 119 |
| `execution/venue/binance.py` | 240 |
| `tests/unit/test_core_foundation.py` | 100 |

## Status legend

- ✅ Verified implemented.
- ⚠️ Partial / fragile / known issue.
- 🔲 Missing or empty.

## Highest-impact remaining gaps (post-fix)

- `crates/*` empty member crates — `cargo build` fails (only `cryptobot-core` has manifest).
- 6 dead empty dirs under `src/cryptobot/`: `allocator/`, `altdata/`, `api/`, `exchanges/`, `funding/`, `xmr/`.
- `ml/models/{volatility,regime,ensemble}.py` missing.
- Live Binance runtime credentials; integration tests for TimescaleDB/Redis/Prometheus.

## Confidence

- High: file presence, public symbol names, line counts.
- Medium: behavior of modules not exercised by tests.
- Low: live Binance behavior, k8s deployment validity, Rust perf not yet realized.
