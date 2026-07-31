# 01. System Architecture

> **Last Updated**: 2026-07-31 (audit v2)
> **Confidence**: High for what exists; Low for what is intended (Rust).

## Verified layers

```
┌─────────────────────────────────────────────────────────────────┐
│                    Python Orchestration Layer (3.14)             │
│  config │ core │ data │ strategies │ risk │ execution           │
│  backtest │ monitoring │ utils │ cli │ ml │ market_data          │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│          Rust Layer (buildable; core stub only)                 │
│  Cargo.toml (root) → 1 member: cryptobot-core (lib.rs stub +    │
│  unit test). Sibling crates (backtest/features/orderbook/py/    │
│  risk/stats) deleted until each gets a Cargo.toml + lib.rs.     │
│  `cargo build` + `cargo test` pass (rustup stable 1.97.1).      │
└─────────────────────────────────────────────────────────────────┘
```

## Verified modules

| Layer | Files | Status |
|-------|-------|--------|
| Config | `src/cryptobot/config.py` | ✅ Pydantic v2 BaseSettings + `from_yaml_safe` (uses `_flatten_yaml`) translates nested YAML to flat field names. `extra="ignore"` retained as safety net. |
| Core | `events.py`, `bus.py`, `clock.py`, `state.py`, `portfolio.py` | ✅ Implemented. SQLite path now `/app/data/cryptobot.db` (B069). Daily PnL auto-resets at UTC day boundary (B034). |
| Data | `ingestion.py`, `storage.py`, `cleaning.py`, `features.py` | ✅ `data/features.py` re-exports `cryptobot.ml.features` (B056). `BinanceDataIngestion` reuses `aiohttp.ClientSession` via `_ensure_session()` (B042). |
| Strategies | `base.py`, `registry.py` + 6 concrete (`mean_reversion`, `trend_following`, `stat_arb`, `funding_arb`, `market_making`, `ml_strategy`) | ✅ All 6 implemented. Registry wired to YAML via `load_strategies_from_config` (B057/B059). |
| Risk | `manager.py`, `limits.py`, `sizing.py`, `kill_switch.py`, `correlation.py` | ✅ Implemented. Notional check skipped on no-price (B038, B060, B061). |
| Execution | `engine.py`, `algorithms.py`, `router.py`, `adverse_selection.py`, `venue/{base,simulated,binance}.py` | ✅ Implemented. `BinanceVenue` via `ccxt.async_support` with sandbox, retries, guards. SOR + adverse-selection wired. |
| Backtest | `engine.py`, `metrics.py`, `simulator.py`, `validation.py`, `reporting.py`, `runner.py`, `data.py` | ✅ Real WFA + MC + deflated Sharpe; equity double-count fix (B063); entry-price zero guard (B064). |
| Monitoring | `metrics.py`, `alerting.py`, `health.py`, `dashboard.py` | ✅ Implemented. `total_pnl` is `Gauge` (B025). `ThreadPoolExecutor` shared for alert fan-out (B067). Health monitor exposes runtime register/unregister (B043). |
| Utils | `logging.py`, `decorators.py`, `types.py`, `health_server.py` | ✅ stdlib `ThreadingHTTPServer` for `/health` + `/metrics`. |
| Market Data | `manager.py` | ✅ Binance WS with fallback symbols+timeframes (B044). |
| CLI | `main.py` | ✅ argparse `validate/paper/bot/serve` with real logic. |
| ML | `features.py`, `online.py`, `models/direction.py` | ✅ Core. `volatility.py`, `regime.py`, `ensemble.py` 🔲 missing. Walk-forward stats persistence (B065). |
| Rust | `crates/*` | ✅ Workspace trimmed to 1 member (`cryptobot-core`) with `lib.rs` stub + 1 unit test. `cargo build` + `cargo test` pass. Empty `src/{events,math,time,types}/` subdirs preserved. Sibling crates removed (planned to be re-added when each gets a manifest). |

## Event flow (verified)

- `market_data.manager.BinanceWSClient` → publishes events into `core.bus.EventBus`.
- `strategies.base.BaseStrategy.on_market_data(event)` consumes events (or `ml_strategy.MLStrategy.feed` for the ML one).
- Strategies emit `OrderEvent`s.
- `execution.engine.ExecutionEngine.submit_order(order)` calls `risk.manager.RiskManager.check_order(order, price)` (B061 fetches market price for market orders), then `venue.submit_order`.
- `risk.manager.RiskCheckResult.to_event` publishes `RiskEvent`. Rejected orders emit `ORDER_REJECTED` with `reason` and `check_type` (B040).
- `execution.router.SmartOrderRouter` can intercept pre-venue for multi-venue selection.
- `execution.adverse_selection.AdverseSelectionGuard` cancels active orders on mid-move / spread-widen / toxicity spikes.
- `backtest.engine.BacktestEngine` runs event-driven loop; `backtest.runner.run_backtest` wires OHLCV → strategy → ExecutionEngine → SimulatedVenue end-to-end.

## Key cross-cutting decisions

- All timestamps: `datetime.utcnow()`.
- All money: `Decimal`.
- All async API entry points: `asyncio`.
- Async-first, sync fallback only for selected decorators (`utils/decorators.py`).
- Prometheus `Gauge` for any value that can be negative (no `Counter` for PnL).
- YAML loader accepts the existing `configs/base.yaml` nested shape via `_flatten_yaml`; new code should prefer `Settings.from_yaml_safe`.

## Runtime pre-requisites

- Python 3.14 slim (Dockerfile).
- Optional third-party: `prometheus_client`, `aiohttp`, `asyncpg`, `pyarrow`, `pandas`, `numpy`, `ccxt`, `scikit-learn`.
- Optional infrastructure: TimescaleDB, Redis.
- If `_sqlite3` unavailable, `core.state.StateManager` skips persistence and emits a warning (B024).
- Container DB path resolves to `/app/data/cryptobot.db` first (B069); falls back to cwd.

## Known gaps

- `crates/{cryptobot-backtest,features,risk,stats,orderbook,py}/` lack `Cargo.toml` even though listed in workspace `members`. `cargo build` from root errors until either each gets a manifest or the array is trimmed.
- 6 dead empty dirs under `src/cryptobot/`: `allocator/`, `altdata/`, `api/`, `exchanges/`, `funding/`, `xmr/`.
- ML volatility / regime / ensemble models not implemented (disabled in `configs/base.yaml`).

## Detailed API references

- `06_API_Reference.md` — public re-exports per package.
- `05_Control_Flow.md` — module-level call order.
- `12_Feature_Status.md` — feature-by-feature status.

## Confidence

- High: diagram, file presence, public classes, recent bug fixes.
- Medium: behavior not exercised by tests.
- Low: Rust performance layer, live Binance behavior under load.
