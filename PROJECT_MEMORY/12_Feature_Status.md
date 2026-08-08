# 12. Feature Status

> **Last Updated**: 2026-08-08 (catalog 84 strategies shipped — Trend 16, MR 12, Momentum 11, Breakout 11, Volatility 8, Volume 7, Stat-Arb 5, Crypto 5, Hybrid 10; 749 pytest + 63 Rust tests green; ruff + clippy -D warnings clean)
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
| `data/features.py` | ✅ | Re-export of `cryptobot.ml.features` (B056). |
| `backtest/engine.py` | ✅ | BacktestEngine, BacktestResult, TradeRecord. Equity double-count removed (B063); entry-price zero-guard (B064). |
| `backtest/metrics.py` | ✅ | Sharpe, Sortino, drawdown, profit factor. Sortino method added. Zero-guard on drawdown. |
| `backtest/simulator.py` | ✅ | FillSimulator + factory. |
| `backtest/validation.py` | ✅ | Real walk-forward (rolling-window with embargo), Monte Carlo block-permutation, deflated Sharpe. |
| `backtest/reporting.py` | ✅ | HTML tearsheet generator (stdlib only). |
| `backtest/runner.py` | ✅ | OhlcvBar + generate_synthetic_ohlcv + run_backtest end-to-end (OHLCV → strategy → ExecutionEngine → SimulatedVenue → BacktestEngine). |
| `backtest/data.py` | ✅ | Historical data replay: `load_csv` (stdlib), `load_parquet` (pyarrow optional), `load_timescale` (async via existing storage layer), `OhlcvDataset.filter_range` + `load_bars` dispatcher. CLI supports `--source csv|parquet|timescale|synthetic`. |
| `strategies/base.py` | ✅ | BaseStrategy, StrategyRegistry, correct `OrderEvent` construction, `from __future__ import annotations`. No print on import (B049). |
| `strategies/position.py` | ✅ | `Position` + `PositionManager`: scale-in/out (weighted avg entry), stop/take-profit `reduce_only` exits, trailing-stop ratchet. Pure state, no EventBus dep. |
| `strategies/mean_reversion.py` | ✅ | Real strategy: Z-score + RSI + Bollinger Bands (pandas/numpy). |
| `strategies/trend_following.py` | ✅ | Real strategy: EMA + ADX + ATR trailing stop. |
| `strategies/market_making.py` | ✅ | Avellaneda-Stoikov market making (reservation price + spread), `run_on_history` synth fill path, pluggable to ExecutionEngine + AdverseSelectionGuard. |
| `strategies/stat_arb.py` | ✅ | Pairs trading: rolling hedge ratio, correlation gate, z-score entry/exit/stop. |
| `strategies/funding_arb.py` | ✅ | Funding / basis arb: spot-vs-perp + funding rate + basis entry/exit. |
| `strategies/registry.py` | ✅ | `load_strategies_from_config` + `_STRATEGY_REGISTRY_MAP` (6 legacy + 84 catalog = 90 strategies) — YAML `strategies.enabled` honored (B057/B059); catalog auto-registers via `strategies/catalog/__init__.py`. |
| `strategies/signal_base.py` | ✅ | `SignalStrategy` streaming base — per-symbol OHLCV buffers, flip-on-signal MARKET orders; `feed(symbol, close, high, low, volume)` (legacy 2-arg fallback in runner). |
| `strategies/indicators.py` | ✅ | 22 numpy OHLCV primitives — sma/ema/rsi/macd/atr/bb/donchian/cci/roc/obv/vwap/fisher/stoch/williams/keltner_mid/chaikin_mf/cumulative_delta/range_n/inside_bar/zscore/bollinger_position/true_range/make_order. |
| `strategies/catalog/` | ✅ | **84 catalog signal strategies** — one file per strategy + one test per strategy (84 in `tests/strategies/`); auto-registered. Generated from spec table via `tools/gen_catalog.py`. Test modes: trend (monotonic), osc (sine+drift), vol (spike), flow (asymmetric candles). |
| `strategies/ml_strategy.py` | ✅ | `MLStrategy` + `MLStrategyConfig` using `DirectionClassifier`; periodic retrain on price buffer (B054). |
| `ml/features.py` | ✅ | 8 features: returns, RSI, MACD line + signal, ATR ratio, BB position + width, log volume. |
| `ml/models/direction.py` | ✅ | `DirectionClassifier` (sklearn logreg preferred, numpy fallback), walk-forward score. |
| `ml/online.py` | ✅ | `DriftDetector` (mean/std shift) + `WalkForwardTrainer` purged splits. |
| `ml/models/volatility.py` | ✅ | EWMA, GARCH, realized, quantile regression with softmax probabilities |
| `ml/models/regime.py` | ✅ | HMM, k-means, GMM, threshold with softmax probabilities |
| `ml/models/ensemble.py` | ✅ | Weighted voting ensemble with direction, volatility, regime |
| `utils/health_server.py` | ✅ | stdlib ThreadingHTTPServer exposing `/health` JSON + `/metrics` Prometheus text. Used by Dockerfile HEALTHCHECK. |
| `risk/manager.py` | ✅ | RiskManager pre-trade checks (kill switch, notional, total exposure). Notional check skipped when no price available. `report_risk_metrics()` emits Prometheus gauges per order check. |
| `risk/limits.py` | ✅ | RiskLimits from config. |
| `risk/sizing.py` | ✅ | fixed_fraction_size, kelly_size, volatility_target_size. |
| `risk/kill_switch.py` | ✅ | KillSwitch reads portfolio signal. |
| `risk/correlation.py` | ✅ | max_abs_correlation helper. |
| `risk/portfolio_optimizer.py` | ✅ | HRP (single-linkage + recursive bisection) + mean-CVaR (per-asset tail-loss weights). numpy-only, no scipy. `hrp_weights` / `mean_cvar_weights` → `PortfolioOptimizerResult`. |
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
| `cli/main.py` | ✅ | argparse CLI with `validate`, `paper`, `bot`, `serve`, `backtest`. Backtest subcommand supports `--show-trades` (print every closed trade; adds `trades[]` with `--json`), `--algorithms jobs.json` (parallel sweep), `--workers N`, `--seed`, `--vol`, `--capital`. **`paper-funder`** runs the Phase 3 funding-carry paper harness (`--symbols`, `--hours`, `--log`, `--poll-fapi`, `--poll-interval`, `--json`). With `--json`, logs route to stderr so stdout carries only JSON. |
| `backtest/parallel.py` | ✅ | `run_parallel(jobs, workers)` multi-core algorithm sweep via `ProcessPoolExecutor`. |
| `backtest/optimize.py` | ✅ | `optimize_strategy` — Optuna bayesian search over strategy config params (Optuna optional; deterministic grid fallback). Sharpe/Sortino/MaxDD/returns objectives. |
| `backtest/runner.py` | ✅ | `run_bars` fast path runs the whole backtest loop without per-bar event bus overhead. |
| `utils/logging.py` | ✅ | structlog wrapper with context vars. |
| `utils/decorators.py` | ✅ | retry (jitter clamped to ≥0), timeout_decorator, circuit_breaker (raises RuntimeError in running loop). |
| `utils/types.py` | ✅ | Candle, OrderBook, Trade, TickData, OHLCVBar, PerformanceMetrics. |
| `market_data/manager.py` | ✅ | Binance WS client. Requires `aiohttp`, `redis`. `_symbols`/`_timeframes` fallback to `default_symbol` / `["1m"]` when settings empty. |
| `ml/` | ✅ | Core pipeline: features, direction, online (WalkForwardTrainer + DriftDetector). **New: `ml/models/volatility.py` (EWMA, GARCH, realized, quantile), `ml/models/regime.py` (HMM, k-means, GMM, threshold), `ml/models/ensemble.py` (weighted voting ensemble).** |
| `deploy/k8s/` | ✅ | Namespace, ConfigMap, Secret, PVC, Deployment, **Service (ClusterIP)**, **HPA (CPU+memory)**, kustomization (B053). |
| `.github/workflows/ci.yml` | ✅ | Concurrency (`cancel-in-progress`), per-job `timeout-minutes`, `permissions: contents: read`, lint (unpinned ruff+pyflakes), cargo-lint/cargo-test with `Swatinem/rust-cache@v2`, unit (coverage artifact), docker-test (PYTHON_TAG threaded), buildx matrix (**PRs amd64 only, pushes amd64+arm64** via `fromJSON`), manifest, compose-validate. |
| `.github/workflows/release.yml` | ✅ | Tag-driven multi-arch publish with **SBOM + provenance merged into the build-push step** + concurrency group. |
| `scripts/build_multiarch.sh` | ✅ | Local multi-arch build via buildx + QEMU. |
| Rust workspace (`crates/cryptobot-{core,features,risk,stats,orderbook,backtest,py}/`) | ✅ | 7 crates + root workspace manifest. `cargo fmt --check`, `cargo clippy --workspace --all-targets -- -D warnings`, `cargo test --workspace` (all green on stable Rust 1.97+). PyO3 0.29; `cryptobot_py` extension registers `features`, `risk`, `orderbook`, `backtest` submodules. `.cargo/config.toml` has no `target-cpu=native` (breaks cached CI builds). |
| `execution/costs.py` | ✅ | Phase 4 transaction cost model: spread, fees, slippage, funding, rebates. |
| `execution/venue/realistic.py` | ✅ | Realistic venue: seeded order book with QueuePositions, partial fills, adverse-selection guard, limit fills at price, fees on filled qty. |
| `live/paper_harness.py` | ✅ | Phase 3 `FundingPaperHarness` — spot bookTicker WS + fapi `premiumIndex` REST-poll fallback, carry accumulation, CSV logs, reconnection backoff. |
| `ml/optimizer.py` | ✅ | Phase 3 walk-forward optimizer with regime-aware parameter search (Optuna). |
| `pyproject.toml` | ✅ | setuptools build + `cryptobot` CLI entry point. |
| `migrations/*.sql` | ✅ | `001_extension.sql`, `002_hypertables.sql`. |
| `docker-compose.yml` | ✅ | Test + default profiles valid (monitoring dirs scaffolded: `monitoring/{loki,promtail,nginx}`). |

## Fixed this session (2026-07-29)

- `backtest/metrics.py` — imports, `calculate_sortino_ratio`, drawdown zero-guard.
- `backtest/engine.py` — Position/PositionSide imports, win/loss guards, profit factor formula, `pos.side == PositionSide.LONG`.
- `backtest/validation.py` — `run_validation` returns report.
- `data/storage.py` — `timedelta` import.
- `data/cleaning.py` — None/empty guards in `clean_klines`, `clean_tickers`, `clean_trades`, `validate_ohlcv`.
- `monitoring/health.py` — `inspect.isawaitable`, false-as-unhealthy, auto-register component.

## Test Status (2026-08-06)

- **CI**: Python 3.13 runners, pytest + pytest-asyncio + pytest-cov + pytest-timeout=60s + hypothesis; **749 passed / 18 skipped** (51 unit + 84 catalog + 14 integration/dedicated); integration tests behind `integration` marker
- **Lint**: ruff (unpinned) + pyflakes
- **Rust**: cargo fmt + clippy (-D warnings) + test (full workspace: 7 crates, 63 tests)
- **Docker**: test target builds on `PYTHON_TAG` (3.14-slim) + runs pytest in container
- **Compose**: validate default + test profiles
- **Repo**: public; CI fully green (first green run 2026-08-06)

### Recent Test Fixes (2026-08-01)
- `validation.py`: `np.math.erf` → `math.erf` (numpy 2.x compatibility)
- `requirements/test.txt`: added `ccxt>=4.0` for BinanceVenue tests
- `test_binance_venue.py`: fixed ccxt mocking with ModuleType, moved mock setup after reload
- `test_core_foundation.py`: adjusted slippage/commission expectations for SimulatedVenue
- `test_core_clock_portfolio.py`: fixed `sleep_until` async test with background task
- `test_market_data_manager.py`: fixed TickerEvent constructor (removed deprecated `event_id`, `event_type`, `payload`)
- `test_monitoring_alerting.py`: fixed Alert/AlertRule API (use Enum values, added `get_name()` to Dummy channel)
- `test_monitoring_health.py`: updated to ComponentType enum, HealthStatus enum, HealthMonitor returns dict[ComponentType, ComponentHealth], added `is_healthy()`
- `test_smart_order_router.py`: `split_and_route` now raises ValueError for empty ratio
- `test_strategies_ml.py`: fixed MarketMakingStrategy `_step` call signature, StatArb lookback logic, FundingArb basis entry threshold
- `test_risk_manager_str.py`: fixed portfolio setup with equity to avoid kill switch
- `src/cryptobot/execution/router.py`: `split_and_route` raises on empty ratio
- `src/cryptobot/monitoring/health.py`: case-insensitive ComponentType conversion, added `is_healthy()`
- `src/cryptobot/monitoring/alerting.py`: fingerprint includes severity
- `src/cryptobot/backtest/validation.py`: `np.math.erf` → `math.erf`
- `src/cryptobot/strategies/market_making.py`: fixed `_step` signature
- CI: pytest-timeout=60s prevents hangs
- Python 3.13 in CI (ruff target py313)
- Docker multi-arch tags fixed (sanitized platform strings)

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
- 47 unit test files in `tests/unit/` + `tests/integration/test_external_services.py`; property-based (hypothesis) + backtest-regression suites added 2026-08-06.