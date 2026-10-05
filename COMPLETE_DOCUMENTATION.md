# Cryptobot - Complete Technical Documentation

> **Elite Quantitative Trading System** — Production-grade algorithmic trading platform with backtesting, live trading, ML pipeline, risk management, and multi-arch deployment.

> ⚠️ **2026-08-22 audit notice**: 34 verified bugs were filed as GitHub #20–#53 (9 critical,
> 16 high) across backtesting metrics, ML training, risk gating, and deployment. The reference
> below describes *intended* behavior; where reality diverges, the tracker and
> `PROJECT_MEMORY/13_Bug_Tracker.md` are authoritative. Headline caveats: production Docker
> image can't start (#22), backtest Sharpe/drawdown unreliable (#20/#32/#39/#40), catalog
> strategies effectively long-only (#25), ML labels leak features (#21), optimizer layer
> non-functional (#27).

---

## 📋 Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Core Modules](#core-modules)
3. [Strategy Framework](#strategy-framework)
4. [Backtesting Engine](#backtesting-engine)
5. [Execution Engine](#execution-engine)
5. [Risk Management](#risk-management)
6. [ML Pipeline](#ml-pipeline)
7. [Monitoring & Observability](#monitoring--observability)
8. [Data Pipeline](#data-pipeline)
9. [Configuration](#configuration)
10. [CLI Reference](#cli-reference)
10. [Docker & Deployment](#docker--deployment)
11. [CI/CD Pipeline](#cicd-pipeline)
11. [Testing](#testing)
12. [Troubleshooting](#troubleshooting)

---

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    Cryptobot Architecture                       │
├─────────────────────────────────────────────────────────────────┤
│  Python 3.14+ (src-layout)          Rust Workspace (PyO3)      │
│  ┌─────────────────────┐          ┌─────────────────────┐       │
│  │ Async-first Python  │  ◄──►   │  cryptobot-core      │       │
│  │  - Strategies       │  PyO3    │  - Events, Math    │       │
│  │  - Risk Mgmt        │          │  - Order Book      │       │
│  │  - Execution        │          │  - Feature Eng     │       │
│  │  - Monitoring       │          │  - Stats/PBO       │       │
│  └─────────────────────┘          └─────────────────────┘       │
│         │                                    │                  │
│         ▼                                    ▼                  │
│  ┌─────────────────────┐          ┌─────────────────────┐       │
│  │ Docker / K8s        │          │  TimescaleDB + Redis │       │
│  │ Multi-arch (amd64/  │          │  Prometheus/Grafana  │       │
│  │  arm64 via buildx)  │          │  Loki/Promtail       │       │
│  └─────────────────────┘          └─────────────────────┘       │
└─────────────────────────────────────────────────────────────────┘
```

### Key Design Principles
- **Async-first**: All I/O uses `asyncio`, `aiohttp`, `redis.asyncio`
- **Decimal for money**: All financial values use `Decimal`, never `float`
- **Event-driven**: Central `EventBus` for decoupled component communication
- **Time abstraction**: `Clock` protocol (Realtime/Simulated/Accelerated)
- **Config**: Pydantic Settings + YAML (`configs/base.yaml`) with env overrides

---

## 🧩 Core Modules

### `src/cryptobot/core/`

| Module | Purpose | Key Classes |
|--------|---------|-------------|
| `events.py` | 40+ event types (market, orders, positions, P&L, risk) | `Event`, `OrderEvent`, `KlineEvent`, `TickerEvent`, `EventType`, `OrderSide`, `OrderType`, `OrderStatus` |
| `bus.py` | Async event bus with pub/sub, history, replay | `EventBus`, `get_event_bus()` |
| `clock.py` | Time abstraction (Realtime/Simulated/Accelerated) | `Clock`, `SimulatedClock`, `RealtimeClock`, `AcceleratedClock`, `ClockFactory` |
| `portfolio.py` | Multi-strategy portfolio, kill-switch, P&L | `PortfolioManager`, `PortfolioState`, `PositionMetrics`, `PortfolioMode` |
| `state.py` | SQLite persistence (orders, positions, account) | `StateManager`, `AccountState`, `Position` |
| `bus.py` | Event bus with pub/sub, history, replay | `EventBus` |

### `src/cryptobot/config.py`
- Pydantic v2 Settings with YAML + environment variable overrides
- Nested config: `ExchangeConfig`, `RiskConfig`, `ExecutionConfig`, `BinanceConfig`, `MarketDataConfig`, `MonitoringConfig`, `DatabaseConfig`, `MLConfig`, `BacktestConfig`, `XMRConfig`
- `Settings.from_yaml_safe()` flattens nested YAML keys

---

## 📈 Strategy Framework

### Base Class (`strategies/base.py`)
```python
class BaseStrategy(Protocol):
    async def on_event(self, event: Event) -> None: ...
    def generate_signals(self) -> list[OrderEvent]: ...
    def on_fill(self, fill: OrderEvent) -> None: ...
```

### Registry (`strategies/registry.py`)
```python
_STRATEGY_REGISTRY_MAP = {
    "trend_following": TrendFollowingStrategy,
    "mean_reversion": MeanReversionStrategy,
    "market_making": MarketMakingStrategy,
    "stat_arb": StatArbStrategy,
    "funding_arb": FundingArbStrategy,
    "ml": MLStrategy,
}
```

### Implemented Strategies (6/6 ✅)

| Strategy | File | Key Logic |
|----------|------|-----------|
| **Trend Following** | `trend_following.py` | EMA crossover + ADX filter + ATR trailing stop |
| **Mean Reversion** | `mean_reversion.py` | Bollinger Bands + RSI + Z-score |
| **Market Making** | `market_making.py` | Avellaneda-Stoikov optimal spread + AdverseSelectionGuard |
| **Stat Arb** | `stat_arb.py` | Rolling hedge ratio, correlation gate, z-score entry/exit |
| **Funding Arb** | `funding_arb.py` | Spot/perp basis + funding rate capture |
| **ML Strategy** | `ml_strategy.py` | DirectionClassifier + periodic retrain |

---

## 🔬 Backtesting Engine

### Core Components

| File | Purpose |
|------|---------|
| `backtest/engine.py` | Event-driven backtester (`BacktestEngine`) |
| `backtest/runner.py` | High-level `run_backtest()` API |
| `backtest/simulator.py` | `FillSimulator` factory |
| `backtest/metrics.py` | Sharpe, Sortino, MaxDD, Profit Factor |
| `backtest/validation.py` | Walk-forward, Monte Carlo, Deflated Sharpe |
| `backtest/reporting.py` | HTML tearsheet generator |
| `backtest/data.py` | Data loading (CSV, Parquet, TimescaleDB, Synthetic) |

### `run_backtest()` API
```python
from cryptobot.backtest.data import load_bars
from cryptobot.backtest.runner import run_backtest

ds = load_bars(source="synthetic", symbol="BTCUSDT", timeframe="1h", n_bars=500)
result = await run_backtest(
    ds.bars,                     # bars first
    strategy=strategy,           # strategy second
    symbol=ds.symbol,
    initial_capital=10000,
    collect_trades=True,         # include per-trade dicts in result.trades
)
```

### BacktestRunResult
```python
@dataclass
class BacktestRunResult:
    initial_capital: Decimal
    final_equity: Decimal
    total_return: float          # fraction (0.0953 = 9.53%)
    n_trades: int
    equity_curve: list[tuple[datetime, Decimal]]
    trades: list[dict]           # per-trade dicts when collect_trades=True
```

### Validation Framework (`backtest/validation.py`)
```python
report = run_validation(
    returns=returns_series,
    n_splits=5,
    n_permutations=1000,
    n_trials=1,
)
# Returns: walk_forward, monte_carlo, deflated_sharpe, passed
```

---

## ⚡ Execution Engine

### Core Components

| Component | File | Purpose |
|-----------|------|---------|
| `ExecutionEngine` | `execution/engine.py` | Order lifecycle, risk gate, venue routing |
| `SmartOrderRouter` | `execution/router.py` | Best-price, latency-aware, fallback, split |
| `Venue` (ABC) | `execution/venue/base.py` | Abstract venue interface |
| `SimulatedVenue` | `execution/venue/simulated.py` | Slippage + commission simulation |
| `BinanceVenue` | `execution/venue/binance.py` | Live/testnet via ccxt.async_support |

### Execution Flow
```
submit_order()
  → risk_manager.check_order()
  → If router: router.route() → smart routing
  → Else: venue.submit_order()
  → ORDER_FILLED / ORDER_REJECTED event
```

### Smart Order Router
```python
router = SmartOrderRouter(
    venues=[venue1, venue2],
    config=RouterConfig(max_slippage_bps=20, max_latency_ms=250),
    ranker=latency_aware_ranker,
)
routed = await router.route(order)
# Or split across venues:
routed = await router.split_and_route(order, ratio=[Decimal("1"), Decimal("1")])
```

### Execution Algorithms (`execution/algorithms.py`)
| Algorithm | Config | Use Case |
|-----------|--------|----------|
| TWAP | `TWAPConfig(duration_min, num_slices)` | Time-weighted execution |
| VWAP | `VWAPConfig(volume_profile)` | Volume-weighted |
| POV | `POVConfig(participation_rate)` | % of volume |
| Implementation Shortfall | `ISConfig(risk_aversion, urgency)` | Minimize implementation shortfall |
| Iceberg | `IcebergConfig(display_qty, randomization)` | Hidden liquidity |

---

## 🛡️ Risk Management

### `RiskManager` (`risk/manager.py`)
```python
result = risk_manager.check_order(order, price=Decimal("50000"))
if not result.passed:
    return RiskCheckResult(False, "Order above maximum size", current=55000, limit=50000)
```

### Risk Checks (in order)
1. **Kill Switch** — Daily loss / max drawdown triggers
2. **Order Size** — Min/max notional per order
3. **Position Limits** — Per-symbol max position
4. **Total Exposure** — Portfolio leverage limit
4. **Correlation** — Max pairwise correlation

### Kill Switch (`risk/kill_switch.py`)
```python
kill_switch = KillSwitch()
active, reason = kill_switch.evaluate(portfolio)
# Triggers: daily loss > 5%, max drawdown > 15%
```

### Position Sizing (`risk/sizing.py`)
| Method | Formula |
|--------|---------|
| Fixed Fraction | `equity * risk_fraction / stop_loss_pct` |
| Kelly | `win_rate * avg_win / avg_win - (1-win_rate)*avg_loss / avg_win` |
| Vol Target | `equity * target_vol / asset_vol` |

### Correlation (`risk/correlation.py`)
```python
max_corr = max_abs_correlation(correlation_matrix)
```

---

## 🤖 ML Pipeline

### Feature Engineering (`ml/features.py`)
```python
features = build_features(bars)  # 8 features
# Returns, RSI, MACD, ATR ratio, BB position/width, log volume
```

### Models (`ml/models/`)

| Model | File | Methods |
|-------|------|---------|
| **Direction** | `direction.py` | `DirectionClassifier` (sklearn logreg + numpy fallback), `fit()`, `predict_proba()`, `walk_forward_score()` |
| **Volatility** | `volatility.py` | `VolatilityModel` (EWMA, GARCH, Realized, Quantile), `forecast()`, `forecast_series()`, `forecast_quantiles()` |
| **Regime** | `regime.py` | `RegimeDetector` (HMM, K-means, GMM, Threshold), `predict()`, `predict_proba()`, `current_regime()` |
| **Ensemble** | `ensemble.py` | `EnsembleModel` (weighted voting), `predict()`, `predict_proba()`, `predict_with_confidence()`, `predict_volatility()`, `current_regime()` |

### Online Learning (`ml/online.py`)
```python
trainer = WalkForwardTrainer(purge=0.02, embargo=0.01)
detector = DriftDetector(threshold=2.0)
```

### ML Strategy (`strategies/ml_strategy.py`)
```python
config = MLStrategyConfig(
    direction_config=DirectionConfig(threshold=0.55, horizon=5),
    retrain_interval=100,
    min_train_samples=500,
)
strategy = MLStrategy(config)
```

---

## 📊 Monitoring & Observability

### Metrics (`monitoring/metrics.py`)
```python
record_order(strategy="trend", symbol="BTCUSDT", side="BUY", type="MARKET")
record_fill(symbol="BTCUSDT", side="BUY", qty=1, price=50000, commission=2.5)
record_pnl(strategy="trend", daily=100, total=5000, equity=15000, available=12000, margin=3000)
record_execution_latency(venue="binance", symbol="BTCUSDT", latency=0.045)
```

**Metrics Exposed**: `orders_total`, `fills_total`, `execution_latency_seconds`, `venue_quote_latency`, `pnl_total`, `pnl_daily`, `equity`, `drawdown_pct`, `position_size`

### Logging
```python
from cryptobot.utils.logging import get_logger, configure_logging

configure_logging(level="INFO", json_output=True)
logger = get_logger(__name__)
logger.info("Order submitted", symbol="BTCUSDT", side="BUY", qty=1.0)
```

### Health Checks (`monitoring/health.py`)
```python
monitor = HealthMonitor(check_interval=30.0)
monitor.register_check(HealthCheck(
    name="exchange_ping",
    component=ComponentType.EXCHANGE,
    check_fn=lambda: exchange.get_server_time(),
    interval_seconds=30.0,
))
results = await monitor.run_all_checks()
is_healthy = monitor.is_healthy()
```

### Alerting (`monitoring/alerting.py`)
```python
manager = AlertManager()
manager.add_channel("telegram", TelegramChannel(bot_token, chat_id))
manager.add_rule(AlertRule(
    name="high_drawdown",
    category=AlertCategory.RISK,
    severity=AlertSeverity.CRITICAL,
    labels={"drawdown_pct": "0.15"},
    channels=["telegram", "pagerduty"],
    cooldown=timedelta(minutes=15),
))
sent = await manager.fire(Alert(...))
```

### Health Server (`utils/health_server.py`)
```bash
# HTTP endpoints
GET /health     # Overall health
GET /health/ready   # Readiness
GET /health/live    # Liveness
GET /metrics   # Prometheus text format
```

---

## 📦 Data Pipeline

### Ingestion (`data/ingestion.py`)
```python
ingestion = BinanceDataIngestion(config)
await ingestion.start()
# WebSocket: klines, trades, orderbook, tickers
# REST: historical klines, funding rates, orderbook snapshots
```

### Storage (`data/storage.py`)
| Backend | Class | Features |
|---------|-------|----------|
| TimescaleDB | `TimescaleDBStorage` | Hypertables, continuous aggregates |
| Parquet | `ParquetStorage` | Partitioned by symbol/year/month, zstd compression |
| Hybrid | `HybridStorage` | Dual-write to both |

### Data Cleaning (`data/cleaning.py`)
```python
cleaner = DataCleaner()
clean_df = cleaner.clean_klines(raw_df)  # Dedupe, fill gaps, validate OHLC
validate_ohlcv(df)  # True/False
```

### Data Loading (`backtest/data.py`)
```python
bars = await load_bars(
    source="csv", path="./data/btcusdt_1m.csv",
    symbol="BTCUSDT", timeframe="1h",
    start=datetime(2024,1,1), end=datetime(2024,12,31)
)
# Also supports: parquet, timescale, synthetic
```

---

## ⚙️ Configuration

### `configs/base.yaml` (Full Schema)
```yaml
app:
  log_level: INFO
  env: paper

exchange:
  enabled: true
  testnet: true
  api_key: ${BINANCE_API_KEY}
  api_secret: ${BINANCE_API_SECRET}
  symbols: ["BTCUSDT"]
  timeframes: ["1m"]

risk:
  max_position_usd: 50000
  max_total_exposure_pct: 0.8
  max_drawdown_pct: 0.15
  kill_switch_daily_loss_pct: 0.05
  max_leverage: 3.0
  max_correlation: 0.7

execution:
  mode: paper
  venue: simulated
  max_slippage_bps: 20
  max_latency_ms: 250

market_data:
  symbols: ["BTCUSDT"]
  timeframes: ["1m"]
  cache_ttl_seconds: 60

monitoring:
  prometheus_port: 9090
  alert_telegram_token: ""
  alert_discord_webhook: ""
```

### Environment Variable Overrides
```bash
export EXECUTION_MODE=paper          # paper, live, backtest
export EXECUTION_VENUE=simulated     # simulated, binance
export BINANCE_API_KEY=your_key
export BINANCE_API_SECRET=your_secret
export APP_LOG_LEVEL=DEBUG
export RISK_MAX_POSITION_USD=50000
```

---

## 🖥️ CLI Reference

```bash
cryptobot --help

# Backtest (synthetic/CSV/parquet; logs to stderr with --json)
python -m cryptobot.cli.main backtest --strategy trend_following --bars 500 --json

# Parallel parameter sweep
python -m cryptobot.cli.main backtest --algorithms jobs.json --workers 8 --json

# Paper dry-run over synthetic bars
python -m cryptobot.cli.main paper --symbol ETHUSDT --bars 500

# Health/metrics server (bot = serve + keepalive loop)
python -m cryptobot.cli.main bot --host 0.0.0.0 --port 8080
python -m cryptobot.cli.main serve --host 0.0.0.0 --port 8080

# Validation / funding monitor / carry backtest
python -m cryptobot.cli.main validate --bars 200 --json
python -m cryptobot.cli.main paper-funder --symbols BTCUSDT --hours 6
python -m cryptobot.cli.main carry --spot spot.csv --perp perp.csv --funding funding.csv
```

> Note: there are no `ingest`, `health`, or `config show/validate` subcommands, no `--validate`
> flag on backtest, and no per-strategy CLI flags — strategy params are varied via the
> `--algorithms` sweep file or programmatically (`make_strategy(name, **params)`).

### Strategy-Specific Options
```bash
# Not exposed as CLI flags. Vary params via the sweep:
[{"strategy": "trend_following", "params": {"fast": 8, "slow": 21}}]  # jobs.json

# Programmatic equivalent:
#   from cryptobot.backtest.runner import make_strategy
#   strat = make_strategy("market_making", gamma=0.5, kappa=1.5)
```

### Environment Variables
```bash
export STRATEGY=trend_following
export BARS=500
export SYMBOL=BTCUSDT
export TIMEFRAME=1m
export INITIAL_CAPITAL=10000
export COMMISSION_BPS=5
export SLIPPAGE_BPS=3

cryptobot backtest
```

### Priority
1. CLI arguments (highest)
2. Environment variables
3. Config file (configs/base.yaml)
4. Defaults

---

## 🐳 Docker & Deployment

### Dockerfile (Multi-stage)
```dockerfile
# Base: python:3.14-slim
# Targets: base, test, production
# ARGs: REQUIREMENTS, GIT_SHA, BUILD_DATE
```

### Build Commands
```bash
# Test image
docker build --target test --build-arg REQUIREMENTS=requirements/test.txt -t cryptobot:test .

# Production
docker build --target production -t ghcr.io/shobhit727/trade:latest .

# Multi-arch
docker buildx build --platform linux/amd64,linux/arm64 --target production --push -t ghcr.io/shobhit727/trade:latest .
```

### Docker Compose
```yaml
version: '3.8'

services:
  timescaledb:
    image: timescale/timescaledb:latest-pg15
    environment:
      POSTGRES_DB: cryptobot
      POSTGRES_USER: cryptobot
      POSTGRES_PASSWORD: cryptobot
    volumes:
      - timescaledb_data:/var/lib/postgresql/data
    ports: ["5432:5432"]

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]

  prometheus:
    image: prom/prometheus
    volumes: ["./monitoring/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml"]
    ports: ["9090:9090"]

  grafana:
    image: grafana/grafana
    volumes: ["./monitoring/grafana/dashboards:/etc/grafana/provisioning/dashboards"]
    ports: ["3000:3000"]

  loki:
    image: grafana/loki
    ports: ["3100:3100"]

  promtail:
    image: grafana/promtail
    volumes: ["./logs:/var/log", "./monitoring/promtail/config.yml:/etc/promtail/config.yml"]

  cryptobot:
    build:
      context: .
      target: production
    environment:
      - EXECUTION_MODE=paper
      - BINANCE_API_KEY=${BINANCE_API_KEY}
      - BINANCE_API_SECRET=${BINANCE_API_SECRET}
    depends_on: [timescaledb, redis]
    ports: ["8080:8080"]

  cryptobot-paper:
    build:
      context: .
      target: production
    environment:
      - EXECUTION_MODE=paper
    profiles: ["paper"]
    depends_on: [timescaledb, redis]

  cryptobot-backtest:
    build:
      context: .
      target: test
    command: pytest -q
    profiles: ["backtest"]

profiles:
  paper: [cryptobot-paper]
  backtest: [cryptobot-backtest]

volumes:
  timescaledb_data:
```

### Run with Docker Compose
```bash
# Full stack
docker compose up -d

# Paper trading
docker compose --profile paper up -d

# Backtest
docker compose --profile backtest run --rm cryptobot-backtest

# Tests
docker compose --profile test run --rm cryptobot-test
```

### Multi-arch Build
```bash
docker buildx create --name cryptobot --use
docker buildx build --platform linux/amd64,linux/arm64 --target production --push -t ghcr.io/shobhit727/trade:latest .
```

---

## 🔄 CI/CD Pipeline

### GitHub Actions (`.github/workflows/ci.yml`)

| Job | Triggers | Steps |
|-----|----------|-------|
| `lint` | push/PR | ruff + pyflakes |
| `cargo-lint` | push/PR | `cargo fmt --check`, `cargo clippy -D warnings` |
| `cargo-test` | push/PR | `cargo test --workspace` |
| `unit` | push/PR (needs lint+cargo) | pytest + coverage |
| `docker-test` | push/PR (needs lint) | Build test image → run pytest in container |
| `docker-build` | push/PR | buildx multi-arch (amd64+arm64) |
| `docker-manifest` | push (after docker-build) | Create multi-arch manifest |
| `compose-validate` | push/PR | `docker compose config --quiet` |

### Key Fixes Applied
| Issue | Fix |
|-------|-----|
| `replace()` not available in GH Actions | Use matrix `include` with `tag_platform` |
| arm64 image not pushed | `push: ${{ github.event_name == 'push' }}` for all platforms |
| Manifest creation fails | Separate `docker-manifest` job with `needs: docker-build` |
| Node.js 20 deprecation | GitHub handles automatically |

### Release Workflow (`.github/workflows/release.yml`)
```bash
git tag v0.1.0 && git push origin v0.1.0
```

### Tagging
```bash
git tag v0.1.0 && git push origin v0.1.0
```

---

## 🧪 Testing

### Run Tests
```bash
# All tests
make test                    # pytest -q --timeout=60

# Specific module
pytest tests/unit/test_core_foundation.py -v
pytest tests/unit/test_ml_volatility.py -v

# With coverage
pytest -q --cov=cryptobot --cov-report=term-missing --timeout=60
```

### Test Structure
```
tests/unit/
├── test_core_foundation.py        # EventBus, Clock, Portfolio, StateManager
├── test_binance_venue.py          # BinanceVenue mocking
├── test_core_clock_portfolio.py   # Clock, PortfolioManager
├── test_core_foundation.py        # EventBus, retry, simulated execution
├── test_core_state.py             # StateManager
├── test_data_cleaning.py          # DataCleaner, validate_ohlcv
├── test_execution_algorithms.py   # TWAP, VWAP, POV
├── test_health_server.py          # Health server
├── test_latency_metrics.py        # Latency metrics
├── test_market_data_manager.py    # BinanceWSClient, MarketDataManager
├── test_monitoring_alerting.py    # AlertManager
├── test_monitoring_health.py      # HealthMonitor
├── test_monitoring_lazy_imports.py # B051 lazy imports
├── test_risk_helpers.py           # Risk sizing
├── test_risk_manager_str.py       # RiskManager
├── test_smart_order_router.py     # SmartOrderRouter
├── test_strategies_ml.py          # ML strategies
├── test_strategies_validation_reporting.py # Validation
├── test_ml_volatility.py          # VolatilityModel
├── test_ml_regime.py              # RegimeDetector
├── test_ml_ensemble.py            # EnsembleModel
├── test_backtest_data.py          # Data loading
├── test_backtest_runner.py        # Backtest runner
├── test_cli.py                    # CLI commands
├── test_config_loading.py         # Config loading
├── test_adverse_selection.py      # AdverseSelectionGuard
├── test_backtest_data.py          # Backtest data
├── test_binance_venue.py          # BinanceVenue
├── test_core_clock_portfolio.py   # Clock, Portfolio
├── test_core_foundation.py        # Core foundation
├── test_core_state.py             # State
├── test_data_cleaning.py          # Data cleaning
├── test_execution_algorithms.py   # Execution algorithms
├── test_health_server.py          # Health server
├── test_latency_metrics.py        # Latency metrics
├── test_market_data_manager.py    # Market data manager
├── test_monitoring_alerting.py    # Monitoring alerting
├── test_monitoring_health.py      # Monitoring health
├── test_monitoring_lazy_imports.py # Lazy imports
├── test_risk_helpers.py           # Risk helpers
├── test_risk_manager_str.py       # Risk manager string
├── test_smart_order_router.py     # Smart order router
├── test_strategies_ml.py          # ML strategies
├── test_strategies_validation_reporting.py # Validation reporting
└── test_ml_volatility.py          # ML volatility
└── test_ml_regime.py              # ML regime
```

### CI Commands
```bash
# Lint
ruff check src tests
ruff format src tests

# Type check (if mypy added)
mypy src

# Rust
cargo fmt --all -- --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace
```

---

## 🔧 Troubleshooting

### Common Issues

| Problem | Solution |
|---------|----------|
| `ModuleNotFoundError: cryptobot` | Run `pip install -e .` |
| `sqlite3` missing | Install `sqlite3` package |
| `ccxt` not installed | `pip install ccxt` |
| `prometheus_client` missing | `pip install prometheus-client` |
| Docker build fails | Check Dockerfile syntax, try `docker build --no-cache` |
| Tests hang | Increase timeout: `pytest --timeout=120` |
| ImportError | Check `PYTHONPATH=src` or `pip install -e .` |

### Binance API
| Error | Solution |
|-------|----------|
| "Service unavailable from restricted location" | Use testnet, check IP whitelist |
| "Invalid API key" | Verify API key/secret, check permissions |
| "Signature invalid" | Check system time sync (NTP) |
| "Rate limit exceeded" | Reduce request frequency, increase `rate_limit_ms` |
| "Order would trigger immediately" | Check stop price vs market price |
| "Insufficient balance" | Check account balance, reduce quantity |

### Performance Tuning
| Issue | Optimization |
|-------|--------------|
| Slow backtest | Use synthetic data, reduce bars, disable logging |
| High memory | Use generators, close DB connections |
| Slow queries | Add indexes, use connection pooling |
| High latency | Use connection pooling, async I/O |
| High CPU | Profile with `py-spy`, optimize hot paths |

---

## 📁 Project Structure

```
cryptobot/
├── src/cryptobot/
│   ├── backtest/          # Backtesting engine
│   ├── cli/               # CLI entrypoint
│   ├── core/              # Events, bus, clock, portfolio, state
│   ├── data/              # Ingestion, storage, cleaning, features
│   ├── execution/         # Engine, router, venues, algorithms
│   ├── market_data/       # WebSocket managers
│   ├── ml/                # Features, models, online learning
│   ├── monitoring/        # Metrics, alerting, health, dashboard
│   ├── risk/              # Manager, limits, sizing, kill switch
│   ├── strategies/        # Base + 6 implementations
│   └── utils/             # Logging, decorators, types, health server
├── crates/cryptobot-core/  # Rust workspace (lib.rs stub)
├── deploy/k8s/            # K8s manifests
├── docker/                # Docker configs (Prometheus, Grafana, etc.)
├── monitoring/            # Grafana dashboards, Prometheus rules
├── requirements/          # prod.txt, test.txt
├── tests/                 # Unit tests
├── configs/               # base.yaml
├── Dockerfile             # Multi-stage build
├── docker-compose.yml     # Local development stack
├── Makefile               # Common commands
├── pyproject.toml         # Package config
├── Cargo.toml             # Rust workspace
├── .github/workflows/     # CI/CD pipelines
└── AGENTS.md              # This file
```

---

## 📚 Key References

| Document | Purpose |
|----------|---------|
| `plan.md` | Architectural source of truth (1200+ lines) |
| `PROJECT_MEMORY/` | Operational knowledge base (26 files) |
| `BACKTEST_GUIDE.md` | Backtesting deep dive |
| `CODEBASE.md` | Complete codebase documentation |
| `docs/RUNBOOK.md` | Operations guide |
| `doc/` | 11 focused guides |

---

## 🔑 Key Files Quick Reference

| Task | File |
|------|------|
| Run backtest | `src/cryptobot/backtest/runner.py` |
| Add strategy | `src/cryptobot/strategies/` |
| Add venue | `src/cryptobot/execution/venue/` |
| Add risk check | `src/cryptobot/risk/manager.py` |
| Add metric | `src/cryptobot/monitoring/metrics.py` |
| Add health check | `src/cryptobot/monitoring/health.py` |
| Add alert | `src/cryptobot/monitoring/alerting.py` |
| Config schema | `src/cryptobot/config.py` |
| CLI commands | `src/cryptobot/cli/main.py` |

---

## 🎯 Quick Start

```bash
# 1. Clone & install
git clone git@github.com:shobhit727/trade.git
cd trade
make install-test

# 2. Run backtest
python -m cryptobot.cli.main backtest --strategy trend_following --bars 500 --validate --json

# 3. Paper trading
docker compose --profile paper up -d

# 4. View metrics
curl http://localhost:8080/metrics
# Grafana: http://localhost:3000 (admin/admin)
```

---

*Generated from Cryptobot codebase analysis. For architectural decisions, see `plan.md`. For operational knowledge, see `PROJECT_MEMORY/`.*