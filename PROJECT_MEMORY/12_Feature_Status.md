# 12. Feature Status

> **Last Updated**: 2026-07-31 (audit sync + plan.md align)
> **Confidence**: High.

## Verified module status

| Module | Status | Notes |
|--------|--------|-------|
| `core/events.py` | ✅ | 40+ event types across market data, signals, orders, positions, P&L, risk, system. |
| `core/bus.py` | ✅ | EventBus with subscribe/unsubscribe/publish/publish_raw/publish_batch/get_history/replay/close. |
| `core/clock.py` | ✅ | Realtime / Simulated / Accelerated clocks + factory. All required `import time` (fixed). |
| `core/state.py` | ✅ | SQLite persistent state. Graceful fallback if `_sqlite3` missing. Logs warning on import fail. |
| `core/portfolio.py` | ✅ | Multi-strategy portfolio, kill-switch, P&L math. `update_equity` auto-resets `_daily_pnl_start` on UTC day boundary. |
| `data/ingestion.py` | ✅ | OHLCV/Tick/TradeData dataclasses, BinanceDataIngestion, DataIngestionManager. |
| `data/storage.py` | ✅ | TimescaleDBStorage, ParquetStorage, HybridStorage. `timedelta` import fixed. |
| `data/cleaning.py` | ✅ | DataCleaner, validate_ohlcv, detect_outliers_zscore, fill_missing_bars. None/empty guards fixed. |
| `data/features.py` | 🔲 | Missing. Canonical feature pipeline is in `ml/features.py`. |
| `backtest/engine.py` | ✅ | BacktestEngine, BacktestResult, TradeRecord. Position/PositionSide import fixed. |
| `backtest/metrics.py` | ✅ | Sharpe, Sortino, drawdown, profit factor. Sortino method added. Zero-guard on drawdown. |
| `backtest/simulator.py` | ✅ | FillSimulator + factory. |
| `backtest/validation.py` | ✅ | Real walk-forward (rolling-window with embargo), Monte Carlo block-permutation, deflated Sharpe. |
| `backtest/reporting.py` | ✅ | HTML tearsheet generator (stdlib only). |
| `backtest/runner.py` | ✅ | OhlcvBar + generate_synthetic_ohlcv + run_backtest end-to-end (OHLCV → strategy → ExecutionEngine → SimulatedVenue → BacktestEngine). |
| `backtest/data.py` | ✅ | Historical data replay: `load_csv` (stdlib), `load_parquet` (pyarrow optional), `load_timescale` (async via existing storage layer), `OhlcvDataset.filter_range` + `load_bars` dispatcher. CLI supports `--source csv|parquet|timescale|synthetic`. |
| `strategies/base.py` | ✅ | BaseStrategy, StrategyRegistry, correct `OrderEvent` construction, `from __future__ import annotations`. |
| `strategies/mean_reversion.py` | ✅ | Real strategy: Z-score + RSI + Bollinger Bands (pandas/numpy). |
| `strategies/trend_following.py` | ✅ | Real strategy: EMA + ADX + ATR trailing stop. |
| `strategies/market_making.py` | ✅ | Avellaneda-Stoikov market making (reservation price + spread), `run_on_history` synth fill path, pluggable to ExecutionEngine + AdverseSelectionGuard. |
| `strategies/stat_arb.py` | ✅ | Pairs trading: rolling hedge ratio, correlation gate, z-score entry/exit/stop. |
| `strategies/funding_arb.py` | ✅ | Funding / basis arb: spot-vs-perp + funding rate + basis entry/exit. |
| `strategies/registry.py` | ✅ | Re-export only. |
| `strategies/ml_strategy.py` | 🔲 | Missing. |
| `ml/features.py` | ✅ | 8 features: returns, RSI, MACD line + signal, ATR ratio, BB position + width, log volume. |
| `ml/models/direction.py` | ✅ | `DirectionClassifier` (sklearn logreg preferred, numpy fallback), walk-forward score. |
| `ml/online.py` | ✅ | `DriftDetector` (mean/std shift) + `WalkForwardTrainer` purged splits. |
| `ml/models/volatility.py` | 🔲 | Missing. |
| `ml/models/regime.py` | 🔲 | Missing. |
| `ml/models/ensemble.py` | 🔲 | Missing. |
| `utils/health_server.py` | ✅ | stdlib ThreadingHTTPServer exposing `/health` JSON + `/metrics` Prometheus text. Used by Dockerfile HEALTHCHECK. |
| `risk/manager.py` | ✅ | RiskManager pre-trade checks (kill switch, notional, total exposure). Notional check skipped when no price available. |
| `risk/limits.py` | ✅ | RiskLimits from config. |
| `risk/sizing.py` | ✅ | fixed_fraction_size, kelly_size, volatility_target_size. |
| `risk/kill_switch.py` | ✅ | KillSwitch reads portfolio signal. |
| `risk/correlation.py` | ✅ | max_abs_correlation helper. |
| `execution/engine.py` | ✅ | ExecutionEngine, risk-gated order submission, `build_venue(mode)` factory selects by `settings.execution.mode`. |
| `execution/algorithms.py` | ✅ | TWAP, VWAP, POV (incl. capped + randomized), Implementation Shortfall (Perée-Clark), Iceberg (display qty + randomization), liquidity-seek sweeps, arrival-price benchmark, `vwap_schedule()` with horizon-minute lookup, `build_pov_schedule`, `slicer_for(name)` dispatcher. |
| `execution/router.py` | ✅ | SmartOrderRouter: best-price ranker, latency-aware ranker, fallback to next venue on failure, split-and-route across venues. |
| `execution/adverse_selection.py` | ✅ | AdverseSelectionGuard (mid-move cancel, spread-widening cancel, toxicity-spike cancel) + QueuePosition + TopOfBook + `attach_to_engine` helper. |
| `execution/venue/base.py` | ✅ | Abstract Venue. |
| `execution/venue/simulated.py` | ✅ | In-memory venue with slippage + commission. |
| `execution/venue/binance.py` | ✅ | Live / testnet Binance via ccxt.async_support. Sandbox mode, retries, error mapping, guardrails for missing credentials. |
| `monitoring/metrics.py` | ✅ | Prometheus metrics + helpers. Requires `prometheus_client`. `total_pnl` is `Gauge` (not Counter). Includes `record_venue_quote_latency` and `record_routing_decision` for SOR observability. |
| `monitoring/alerting.py` | ✅ | AlertManager + Telegram/Discord/Email/PagerDuty channels. `init_alerting()` only starts background task when channels configured; `stop()` idempotent. |
| `monitoring/health.py` | ✅ | HealthMonitor + HealthChecker subclasses. `inspect.isawaitable` + false-as-unhealthy fix. Auto-register component. |
| `monitoring/dashboard.py` | ✅ | Dashboard JSON builders. |
| `cli/main.py` | ✅ | argparse CLI with `validate`, `paper`, `bot`, `serve` subcommands. |
| `utils/logging.py` | ✅ | structlog wrapper with context vars. |
| `utils/decorators.py` | ✅ | retry (jitter clamped to ≥0), timeout_decorator, circuit_breaker (raises RuntimeError in running loop). |
| `utils/types.py` | ✅ | Candle, OrderBook, Trade, TickData, OHLCVBar, PerformanceMetrics. |
| `market_data/manager.py` | ✅ | Binance WS client. Requires `aiohttp`, `redis`. `_symbols`/`_timeframes` fallback to `default_symbol` / `["1m"]` when settings empty. |
| `ml/` | ✅ | Core pipeline: features, direction, online (WalkForwardTrainer + DriftDetector). |
| `deploy/k8s/` | ⚠️ | Namespace, ConfigMap, Secret, PVC, Deployment, kustomization. **No Service, no HPA.** |
| `.github/workflows/ci.yml` | ✅ | Lint + unit + compose-validate + buildx matrix (amd64 + arm64). |
| `.github/workflows/release.yml` | ✅ | Tag-driven multi-arch publish + SBOM + provenance. |
| `scripts/build_multiarch.sh` | ✅ | Local multi-arch build via buildx + QEMU. |
| `crates/cryptobot-core/` | 🔲 | Manifest + empty `src/{events,math,time,types}/` (no `lib.rs`). |
| `crates/cryptobot-backtest/` | 🔲 | Manifest + empty `src/` (no `lib.rs`). |
| `crates/cryptobot-features/` | 🔲 | Manifest + empty `src/` (no `lib.rs`). |
| `crates/cryptobot-risk/` | 🔲 | Manifest + empty `src/` (no `lib.rs`). |
| `crates/cryptobot-stats/` | 🔲 | Manifest + empty `src/` (no `lib.rs`). |
| `crates/cryptobot-orderbook/` | 🔲 | Manifest + empty `src/` (no `lib.rs`). |
| `crates/cryptobot-py/` | 🔲 | Manifest + empty `src/` (no `lib.rs`). |
| `pyproject.toml` | ✅ | setuptools build + `cryptobot` CLI entry point. |
| `migrations/*.sql` | ✅ | `001_extension.sql`, `002_hypertables.sql`. |
| `docker-compose.yml` | ✅ | Test + default profiles valid (monitoring dirs scaffolded). |

## Fixed this session (2026-07-29)

- `backtest/metrics.py` — imports, `calculate_sortino_ratio`, drawdown zero-guard.
- `backtest/engine.py` — Position/PositionSide imports, win/loss guards, profit factor formula, `pos.side == PositionSide.LONG`.
- `backtest/validation.py` — `run_validation` returns report.
- `data/storage.py` — `timedelta` import.
- `data/cleaning.py` — None/empty guards in `clean_klines`, `clean_tickers`, `clean_trades`, `validate_ohlcv`.
- `monitoring/health.py` — `inspect.isawaitable`, false-as-unhealthy, auto-register component.
- `strategies/base.py` — valid `OrderEvent` construction, `from __future__ import annotations`.
- `core/clock.py` — `import time`.
- `core/state.py` — graceful SQLite fallback.
- `tests/unit/test_core_foundation.py` — replaced broken tests with real smoke tests.
- `Dockerfile` (new), `requirements/test.txt` (new), `cryptobot-test` service (new), `.dockerignore` (new).
- `requirements/prod.txt` — modern `>=` ranges, removed `monero-rpc==0.3.0`.

## Fixed this session (2026-07-31)

- `risk/manager.py` (B038) — pre-trade notional check now skipped when no price available; market orders no longer falsely rejected by min-size.
- `execution/engine.py` (B040) — emits `EventType.ORDER_REJECTED` with `reason` + `check_type` on risk reject AND on venue reject; `order.payload` carried in event.
- `market_data/manager.py` (B044) — `BinanceWSClient._symbols`/`_timeframes` fall back to `default_symbol` / `["1m"]` when settings empty.
- `core/portfolio.py` (B034) — `update_equity` auto-resets `_daily_pnl_start` when UTC day boundary crossed (and on first equity push from 0).
- `core/bus.py` (B045) — `publish_batch` dispatches atomically under single lock.
- `monitoring/alerting.py` (B031/B041) — `init_alerting()` only starts background task when channels configured; `stop()` is idempotent.
- `core/state.py` (B024) — emits `logging.warning` when `sqlite3` unavailable.
- `tests/unit/test_cli.py` — fixed `from cryptobot.cli import main` shadowing; now imports `_run` directly.
- `utils/decorators.py` — `retry` jitter clamped to ≥0 via `max(0.0, sleep_time)`. `circuit_breaker` sync wrapper raises `RuntimeError` in running loop instead of `run_until_complete`.
- `monitoring/metrics.py` — `total_pnl` is `Gauge` (not `Counter`), supports negative PnL.
- `strategies/base.py` — removed `print()` in `StrategyRegistry.__new__`.
- `backtest/engine.py` — removed `print()` statements.
- `core/clock.py` — removed `print()` statements.

## Confidence

- High.

## Verification

- `python3 -m py_compile` on all edited files: passes.
- `docker compose --profile test config`: passes.
- Full Docker run blocked by host daemon instability.
- 22 unit test files in `tests/unit/`.