# Cryptobot — Complete Codebase Documentation

## Overview

Cryptobot is an elite quantitative trading system built with Python 3.14+ (async/await) and a Rust workspace. It implements a full trading stack: market data ingestion, risk management, strategy execution, backtesting, and observability.

---

## Directory Structure

```
├── src/cryptobot/           # Python package (src-layout)
│   ├── backtest/            # Engine, runner, metrics, validation, funding/carry, parallel sweeps
│   ├── cli/                 # Command-line interface (main.py)
│   ├── core/                # Events, bus, clock, portfolio, state
│   ├── data/                # Ingestion, cleaning, storage (Timescale/Parquet), features re-export
│   ├── execution/           # Engine, router, algorithms, costs, adverse selection, venues/
│   ├── live/                # FundingPaperHarness (live paper funding-carry monitor)
│   ├── market_data/         # WebSocket manager, Binance client, Redis cache
│   ├── ml/                  # Features, models (direction/volatility/regime/ensemble), training, optimizer, inference, online
│   ├── monitoring/          # Metrics, alerting, health checks, dashboard builders
│   ├── risk/                # Limits, sizing, kill switch, correlation, portfolio optimizer, rate limit
│   ├── strategies/          # Base + implementations + catalog/ (84 signal strategies)
│   └── utils/               # Logging, decorators, types, health server
├── crates/                  # Rust workspace (root Cargo.toml): 7 crates
│   ├── cryptobot-core       # Primitives (OhlcvBar, decimal helpers)
│   ├── cryptobot-features   # Indicators: trend, mean-reversion, volatility
│   ├── cryptobot-risk       # Sizing (Kelly/vol-target), limits, portfolio optimization
│   ├── cryptobot-stats      # Walk-forward accuracy, math helpers
│   ├── cryptobot-orderbook  # Book model, VPIN
│   ├── cryptobot-backtest   # Metrics (+PyO3 bindings); engine modules currently dead code (#42)
│   └── cryptobot-py         # PyO3 0.29 bindings crate (cryptobot_rs)
├── deploy/k8s/              # Kubernetes manifests
├── docker/                  # Docker configs (Prometheus, Grafana dashboards)
├── monitoring/              # Prometheus/Grafana/Loki/Alertmanager configs
├── configs/                 # Base YAML configuration
├── requirements/            # Pinned Python dependencies
├── tests/                   # unit/ + strategies/ + integration/
└── PROJECT_MEMORY/          # Architecture & design docs
```

---

## Module-by-Module Deep Dive

### 1. `src/cryptobot/core/` — Core Primitives

**Purpose:** Foundation layer. Event system, async clock, portfolio accounting, state persistence.

| File | Key Classes | Description |
|------|-------------|-------------|
| `events.py` | `Event`, `EventType`, `OrderEvent`, `KlineEvent`, `TickerEvent`, `TradeEvent`, `OrderSide`, `OrderType`, `OrderStatus` | All domain events. Dataclasses with `payload` dict for extensibility. |
| `bus.py` | `EventBus`, `get_event_bus()` | Pub/sub with async subscriptions, history replay, topic routing. |
| `clock.py` | `Clock`, `SimulatedClock`, `WallClock` | Time abstraction. SimulatedClock for backtests, WallClock for live. |
| `portfolio.py` | `PortfolioState`, `Position` | Real-time PnL, equity curve, position tracking. |
| `state.py` | `StateManager`, `AccountState`, `Position` | SQLite/PostgreSQL persistence for orders, fills, positions. |

**Key Patterns:**
- All events inherit `Event` with `type: EventType`, `timestamp: datetime`, `payload: dict`
- `EventBus` is singleton via `get_event_bus()`
- `Clock` protocol allows time travel in tests/backtests

---

### 2. `src/cryptobot/config.py` — Configuration

**Purpose:** Pydantic Settings with YAML + env override.

**Key Classes:**
- `Settings` — Root config with nested models: `ExchangeConfig`, `RiskConfig`, `ExecutionConfig`, `BinanceConfig`, `MarketDataConfig`, `MonitoringConfig`, `DatabaseConfig`, `MLConfig`, `BacktestConfig`, `XMRConfig`
- `from_yaml_safe()` — Loads `configs/base.yaml`, flattens nested keys, ignores unknown fields

**Env Override Pattern:**
```bash
RISK_MAX_DAILY_LOSS_PCT=0.02  # Sets settings.risk.max_daily_loss_pct
BINANCE_API_KEY=xyz           # Sets settings.binance.api_key
```

---

### 3. `src/cryptobot/data/` — Data Layer

| File | Purpose |
|------|---------|
| `ingestion.py` | `DataIngestion` ABC + `BinanceDataIngestion` (REST + WS). Rate limiting, session management, historical fetch, real-time subscribe. |
| `cleaning.py` | `DataCleaner`, `validate_ohlcv()`. Drops NaN, fixes timestamps, rejects bid>ask, fills gaps. |
| `storage.py` | `StorageBackend` ABC + `TimescaleDBStorage`, `ParquetStorage`. Partitioned writes, batch flush, time-range reads. |

**Flow:** `BinanceDataIngestion.fetch_historical()` → `DataCleaner.clean_klines()` → `ParquetStorage.write_klines()` / `TimescaleDBStorage.write_klines()`

---

### 4. `src/cryptobot/market_data/` — Market Data Manager

| File | Purpose |
|------|---------|
| `manager.py` | `MarketDataManager` orchestrates `BinanceWSClient`. Maintains order book, ticker, trade, kline streams. Redis caching layer for snapshots. |
| `binance_ws.py` | (if exists) Low-level WS message parsing |

**Key Classes:**
- `BinanceWSClient` — Manages `/stream?streams=...` connection, auto-reconnect with exponential backoff, heartbeat ping/pong.
- `MarketDataManager` — Subscribes symbols/timeframes, emits `KlineEvent`, `TickerEvent`, `TradeEvent`, `OrderBookEvent` to `EventBus`.

---

### 5. `src/cryptobot/execution/` — Execution Layer

| File | Purpose |
|------|---------|
| `router.py` | `SmartOrderRouter` — Chooses venue, slices large orders, handles TWAP/VWAP. |
| `engine.py` | `ExecutionEngine` — Submits orders, tracks fills, manages order lifecycle. |
| `algorithms.py` | `TWAPAlgorithm`, `VWAPAlgorithm`, `POVAlgorithm` — Execution algos. |
| `venues/` | `Venue` ABC + `BinanceVenue`, `SimulatedVenue` — Exchange adapters. |
| `adverse_selection.py` | Toxicity metrics, VPIN, order flow imbalance. |

**Order Flow:**
```
Strategy → SmartOrderRouter → ExecutionEngine → Venue (Binance/Simulated)
                ↓
         RiskManager.check_order()  ← pre-trade risk
```

---

### 6. `src/cryptobot/risk/` — Risk Management

| File | Purpose |
|------|---------|
| `manager.py` | `RiskManager` — Central risk engine. Checks: max position, max daily loss, kill switch, correlation limits, leverage. |
| `correlation.py` | `CorrelationTracker` — Rolling correlation matrix, max abs correlation check. |
| `position_limits.py` | Per-symbol, per-strategy, portfolio-level limits. |

**Key Methods:**
- `RiskManager.check_order(order)` → `RiskCheckResult(allowed, reason, adjustments)`
- `RiskManager.update_fill(fill)` — Updates PnL, checks kill switch
- `CorrelationTracker.max_abs_correlation(symbol)` → float

---

### 7. `src/cryptobot/strategies/` — Strategies

| File | Strategy | Description |
|------|----------|-------------|
| `base.py` | `Strategy` ABC | `on_event(event)`, `generate_signals()` → list[OrderEvent] |
| `trend_following.py` | `TrendFollowingStrategy` | EMA crossover, ADX filter, ATR trailing stop |
| `market_making.py` | `MarketMakingStrategy` | Avellaneda-Stoikov, inventory skew, spread capture |
| `stat_arb.py` | `StatArbStrategy` | Cointegration pairs, z-score entry/exit, half-life |

**Base Protocol:**
```python
class Strategy(Protocol):
    def on_event(self, event: Event) -> None: ...
    def generate_signals(self) -> list[OrderEvent]: ...
    def on_fill(self, fill: OrderEvent) -> None: ...
```

---

### 8. `src/cryptobot/backtest/` — Backtesting Engine

| File | Purpose |
|------|---------|
| `engine.py` | `BacktestEngine` — Event-driven replay. Feeds historical events to strategies, simulates fills via `SimulatedVenue`. |
| `runner.py` | `run_backtest()` — High-level API. Config → Engine → Metrics → Report. |
| `data.py` | `load_bars()`, `generate_synthetic_bars()` — Data loaders. |
| `metrics.py` | `PerformanceMetrics` — Sharpe, Sortino, max DD, Calmar, win rate, profit factor. |
| `reporting.py` | `generate_report()` — JSON/HTML/Markdown output with equity curve, trade list, monthly returns. |

**Backtest Flow:**
```
load_bars() → BacktestEngine(events, strategies, venue, risk)
    → for event in events: strategy.on_event(event)
    → strategy.generate_signals() → engine.submit_order()
    → SimulatedVenue fills → RiskManager updates
    → PerformanceMetrics records equity
    → generate_report()
```

---

### 9. `src/cryptobot/monitoring/` — Observability

| File | Purpose |
|------|---------|
| `metrics.py` | Prometheus metrics (Counter, Histogram, Gauge). Lazy imports — no-op stubs if prometheus-client missing (`B051`). |
| `alerting.py` | `AlertManager` — Telegram, Discord, Email, PagerDuty. Deduplication, escalation, routing by severity/category. |
| `health.py` | `HealthCheck` — `/health` endpoint components (DB, Redis, WS, risk). |
| `dashboard.py` | Grafana dashboard JSON generation. |

**Lazy Import Pattern (B051):**
```python
# metrics.py
try:
    from prometheus_client import Counter, Histogram
except ImportError:
    Counter = Histogram = _NoOpMetric  # no-op stubs
```

---

### 10. `src/cryptobot/cli/` — CLI

| File | Purpose |
|------|---------|
| `main.py` | argparse entrypoint (`python -m cryptobot.cli.main`, or `cryptobot` console script) |

**Subcommands:** `backtest`, `mm`, `ml`, `serve`, `bot`, `validate`, `paper`, `paper-funder`, `carry`.

```bash
cryptobot backtest --strategy trend_following --bars 500 --json   # synthetic/CSV/parquet backtest
cryptobot backtest --algorithms jobs.json --workers 8 --json      # parallel parameter sweep
cryptobot bot --host 0.0.0.0 --port 8080                          # health server + keepalive loop
cryptobot serve --port 8080                                       # standalone /health + /metrics
cryptobot validate --bars 200                                     # walk-forward significance
cryptobot paper-funder --symbols BTCUSDT --hours 6                # live funding-carry paper monitor
cryptobot carry --spot spot.csv --perp perp.csv [--funding f.csv] # two-leg carry backtest
```

> Note: there is no `ingest`, `health`, or `config show` subcommand despite older docs mentioning them.
> `bot` runs the full trading loop (WS klines -> strategy -> risk-checked execution; paper by default,
> `--mode live` gated). See `src/cryptobot/live/trader.py`.

---

### 11. `src/cryptobot/utils/` — Utilities

| File | Purpose |
|------|---------|
| `logging.py` | `configure_logging()`, `get_logger()` — Structlog + stdlib, JSON/console renderers, contextvars. |
| `decorators.py` | `retry()`, `timeout()`, `circuit_breaker()` — Async decorators. |
| `types.py` | Type aliases: `Symbol`, `Timestamp`, `Price`, `Quantity`, `Decimal` helpers. |

---

### 12. `crates/` — Rust Workspace

**Status:** Seven real crates (core, features, risk, stats, orderbook, backtest, py), PyO3 `0.29`
bindings exposed as the `cryptobot_rs` package. `cargo fmt --check`, `cargo clippy
--workspace --all-targets -- -D warnings`, and `cargo test --workspace` (63 tests) are green.

> ⚠️ **2026-08-22 audit**: several Rust modules carry math bugs that tests don't catch — ERC
> solver converges to a corner (#24), Sortino/max-drawdown formulas (#40), NaN passes risk limits
> (#41). The backtest engine/runner/validation modules are dead code referencing nonexistent core
> APIs (#42). See #53 for the full sweep. The Python app does not currently consume `cryptobot_rs`.

---

### 13. `deploy/k8s/` — Kubernetes

| File | Purpose |
|------|---------|
| `00-namespace.yaml` | `cryptobot` namespace |
| `01-config.yaml` | ConfigMap from `configs/base.yaml` |
| `02-secret.yaml` | Secrets (API keys, DB password) — placeholders |
| `03-pvc.yaml` | PersistentVolumeClaims for TimescaleDB, Redis, Prometheus |
| `04-deployment.yaml` | Deployment with HPA, resource limits, health probes |
| `05-service.yaml` | ClusterIP services (8080, metrics) |
| `06-hpa.yaml` | HorizontalPodAutoscaler (CPU + custom metrics) |
| `kustomization.yaml` | Kustomize overlay |

---

### 14. `monitoring/` — Observability Configs

| Path | Purpose |
|------|---------|
| `prometheus/prometheus.yml` | Scrape configs: cryptobot (8080), node-exporter, cadvisor, redis, postgres |
| `prometheus/rules/cryptobot.yml` | Alert rules: high latency, error rate, kill switch, daily loss |
| `grafana/dashboards/` | JSON dashboards: trading overview, risk, execution, system |
| `alertmanager/alertmanager.yml` | Routes: critical → PagerDuty, warning → Slack/Telegram |
| `loki/promtail/` | Log aggregation config |

---

### 15. `tests/` — Test Suite

| File | Coverage |
|------|----------|
| `test_core_foundation.py` | EventBus, Clock, Portfolio, StateManager |
| `test_data_cleaning.py` | DataCleaner, validate_ohlcv |
| `test_monitoring_lazy_imports.py` | B051: metrics/alerting import without deps |
| `test_monitoring_alerting.py` | AlertManager routing, deduplication |
| `test_monitoring_health.py` | HealthCheck components |
| `test_market_data_manager.py` | BinanceWSClient, MarketDataManager |
| `test_execution_algorithms.py` | TWAP, VWAP, POV |
| `test_risk_manager_str.py` | RiskManager checks |
| `test_strategies_*.py` | Strategy signal generation |
| `test_backtest_*.py` | Engine, runner, metrics, reporting |

---

## Data Flow Diagrams

### Live Trading Loop

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│ Binance WS  │────▶│ MarketDataMgr│────▶│  EventBus   │
└─────────────┘     └──────────────┘     └──────┬──────┘
                                                │
                    ┌─────────────┐             │
                    │  Strategy   │◀────────────┘
                    └──────┬──────┘
                           │ signals
                           ▼
                    ┌─────────────┐     ┌──────────────┐
                    │SmartOrderRtr│────▶│ExecutionEngine│
                    └─────────────┘     └──────┬───────┘
                                               │
                    ┌─────────────┐             │
                    │ RiskManager │◀────────────┘
                    └─────────────┘
                           │
                    ┌──────▼──────┐
                    │  Venue      │ (Binance / Simulated)
                    └─────────────┘
```

### Backtest Loop

```
┌──────────────┐     ┌────────────────┐     ┌─────────────┐
│ load_bars()  │────▶│ BacktestEngine │────▶│  Strategies │
└──────────────┘     └───────┬────────┘     └──────┬──────┘
                             │                      │
                    ┌────────▼────────┐     ┌───────▼──────┐
                    │ SimulatedVenue  │     │RiskManager   │
                    └────────┬────────┘     └──────────────┘
                             │
                    ┌────────▼────────┐
                    │PerformanceMetrics│
                    └────────┬────────┘
                             ▼
                    ┌────────────────┐
                    │ generate_report│
                    └────────────────┘
```

---

## Configuration Reference (Flattened)

| Env Var | Default | Description |
|---------|---------|-------------|
| `APP_LOG_LEVEL` | INFO | Structlog level |
| `APP_ENV` | paper | paper \| live \| backtest |
| `EXECUTION_MODE` | paper | paper \| binance |
| `BINANCE_API_KEY` | — | Testnet or live key |
| `BINANCE_API_SECRET` | — | |
| `BINANCE_TESTNET` | true | |
| `BINANCE_WS_URL` | wss://stream.binance.com:9443 | |
| `BINANCE_REST_URL` | https://api.binance.com | |
| `RISK_MAX_POSITION_USD` | 10000 | Per-symbol max |
| `RISK_MAX_DAILY_LOSS_PCT` | 0.03 | 3% daily loss limit |
| `RISK_KILL_SWITCH_DAILY_LOSS_PCT` | 0.05 | 5% hard stop |
| `RISK_MAX_LEVERAGE` | 3.0 | |
| `RISK_MAX_CORRELATION` | 0.7 | Pair correlation limit (currently dead code, #49) |
| `MARKET_DATA_SYMBOLS` | ["BTCUSDT"] | Subscribed symbols |
| `MARKET_DATA_TIMEFRAMES` | ["1m"] | Kline intervals |
| `MARKET_DATA_ORDERBOOK_DEPTH` | 20 | Depth levels |
| `MONITORING_PROMETHEUS_PORT` | 9090 | Metrics port |
| `MONITORING_TELEGRAM_BOT_TOKEN` | — | → settings.monitoring.telegram_bot_token |
| `MONITORING_TELEGRAM_CHAT_ID` | — | → telegram_chat_id |
| `MONITORING_DISCORD_WEBHOOK` | — | → discord_webhook |
| `DB_HOST` | timescaledb | |
| `DB_PORT` | 5432 | |
| `DB_NAME` | cryptobot | |
| `DB_USER` | cryptobot | |
| `DB_PASSWORD` | cryptobot | |
| `MARKET_DATA_REDIS_HOST` | redis | Redis cache host (code reads the MARKET_DATA_ prefix) |

> ⚠️ `REDIS_HOST`/`REDIS_PORT`/`PROMETHEUS_PORT` as set in compose/k8s are read by nothing (#52).
> Email alerting env vars are not yet wired to Settings (#29).

Full reference: `PROJECT_MEMORY/08_Config_Reference.md`

---

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Async Python + Rust | Python for flexibility, Rust for hot paths |
| Event-driven architecture | Decouples components, enables replay/backtest |
| Pydantic Settings + YAML | Type-safe config, env override for secrets |
| Lazy optional deps (B051) | Prometheus/aiohttp optional, no import errors |
| SimulatedClock for backtests | Deterministic time control |
| Parquet + TimescaleDB | Columnar analytics + relational time-series |
| Structlog + contextvars | Structured logs with correlation IDs |
| SmartOrderRouter abstraction | Multi-venue, algo execution, easy to extend |

---

## Known Issues & TODOs

See `PROJECT_MEMORY/13_Bug_Tracker.md` and the GitHub issue index (#20–#53, 2026-08-22 audit).

| ID | Issue | Status |
|----|-------|--------|
| B024 | `_sqlite3` missing → in-memory fallback | Workaround |
| B051 | Prometheus optional deps | Fixed (lazy imports) |
| #22 | Production Docker image cannot start (CMD/ENTRYPOINT `-m` duplication) | Open — critical |
| #20/#32/#39 | Backtest Sharpe/drawdown unreliable (wall-clock stamps, no per-bar MTM, Sortino formula) | Open — critical/high |
| #25 | Catalog strategies effectively long-only (flips close, never reverse) | Open — critical |
| #21/#27 | ML label leakage + non-functional optimizer layer | Open — critical |
| — | `/health` endpoint | Done (`utils/health_server.py`) |
| — | BinanceVenue order placement | Done (ccxt async) — see #43 for retry/idempotency caveats |
| — | ML strategy framework | Exists (`strategies/ml_strategy.py`) — trained labels leak until #21 lands |

---

## Running Tests

```bash
# All tests with coverage
pytest -q --cov=cryptobot --cov-report=term-missing

# Specific module
pytest tests/unit/test_risk_manager_str.py -v

# With logging output
pytest -q -o log_cli=true -o log_cli_level=DEBUG
```

---

## Building & Deploying

```bash
# Multi-arch Docker image
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --target production \
  --tag ghcr.io/shobhit727/trade:latest \
  --push .

# Kubernetes
kubectl apply -k deploy/k8s/

# Release
git tag v0.1.0 && git push origin v0.1.0
# Triggers .github/workflows/release.yml
```

---

## License

MIT — See `LICENSE` file.