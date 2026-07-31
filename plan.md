# Cryptobot - Elite Quantitative Trading System
## Master Plan & Architecture Document

> **Status**: Active development | **Last Updated**: 2026-07-31 (audit sync + docs align)
> **Context**: Core, backtester, risk, execution, monitoring, ML core (features + direction + walk-forward), live exchange adapter, smart order router, adverse-selection guard, health server, K8s manifests, multi-arch CI all implemented. Concrete `ml_strategy.py` wiring still pending. Rust crate members are empty scaffolding (workspace manifest + empty `src/` dirs, no `lib.rs`). Default `docker-compose.yml` profile now valid (monitoring dirs scaffolded). Verified against `PROJECT_MEMORY/25_Audit_2026-07-31.md`.
> **Current Python**: 3.14 (Docker base `python:3.14-slim`).
> **Repository**: `git@github.com:shobhit727/trade.git` (private).

---

## 1. Project Context & Goals

> Operational guide: see [`docs/RUNBOOK.md`](docs/RUNBOOK.md) for prerequisites, common Compose commands, profiles, troubleshooting.

### User Requirements
- **Scope**: "Everything" - multi-asset, multi-strategy, institutional-grade
- **Capital**: Retail ($10K-$100K), seconds-to-minutes latency acceptable
- **Priority**: Backtesting → Strategies → ML Pipeline → Risk Management
- **Venue**: Primarily crypto perpetuals (Binance testnet → mainnet), extensible to spot, equities, futures

### Guiding Principles
1. **Statistical rigor over simplicity** - Every strategy must survive walk-forward validation
2. **Modular architecture** - Pluggable strategies, data sources, execution venues
3. **Production-first** - Paper trading parity, observability, graceful degradation
4. **Continuous improvement** - Auto-retraining, regime adaptation, A/B testing framework

---

## 2. Existing Foundation (Verified)

| Module | File | Status |
|--------|------|--------|
| Configuration System | `src/cryptobot/config.py` | ✅ Pydantic v2 + YAML + env. **Note**: `configs/base.yaml` keys do not match `Settings` field names; `extra="ignore"` swallows the mismatch. See `PROJECT_MEMORY/08_Config_Reference.md`. |
| Event System | `src/cryptobot/core/events.py` | ✅ 40+ event types (market, signals, orders, positions, P&L, risk, system). |
| Event Bus | `src/cryptobot/core/bus.py` | ✅ Pub/sub + history + replay. Async + sync callbacks, wildcard, filter. |
| Clock | `src/cryptobot/core/clock.py` | ✅ `RealtimeClock`, `SimulatedClock`, `AcceleratedClock`, factory. |
| State Management | `src/cryptobot/core/state.py` | ✅ SQLite persistence. Graceful fallback if `_sqlite3` missing. |
| Portfolio | `src/cryptobot/core/portfolio.py` | ✅ Multi-strategy portfolio, kill-switch wiring. |
| Market Data | `src/cryptobot/market_data/manager.py` | ✅ Binance WS client, REST helpers, Redis cache. |
| Data Ingestion | `src/cryptobot/data/ingestion.py` | ✅ OHLCV/Tick/TradeData, BinanceDataIngestion. |
| Data Storage | `src/cryptobot/data/storage.py` | ✅ TimescaleDBStorage, ParquetStorage, HybridStorage. |
| Data Cleaning | `src/cryptobot/data/cleaning.py` | ✅ DataCleaner + helpers. |
| Backtest Engine | `src/cryptobot/backtest/engine.py` | ✅ Event-driven, fills, equity curve. |
| Backtest Metrics | `src/cryptobot/backtest/metrics.py` | ✅ Sharpe, Sortino, drawdown, profit factor. |
| Backtest Simulator | `src/cryptobot/backtest/simulator.py` | ✅ FillSimulator + factory. |
| Backtest Validation | `src/cryptobot/backtest/validation.py` | ✅ Real walk-forward (rolling + embargo) + Monte Carlo block-permutation + deflated Sharpe. |
| Strategy Base | `src/cryptobot/strategies/base.py` | ✅ BaseStrategy, registry, MeanReversionStrategy placeholder. |
| Risk Manager | `src/cryptobot/risk/manager.py` | ✅ Pre-trade checks (kill switch, notional, exposure). |
| Risk Limits | `src/cryptobot/risk/limits.py` | ✅ |
| Risk Sizing | `src/cryptobot/risk/sizing.py` | ✅ Fixed-fraction, volatility-target, Kelly. |
| Risk Kill Switch | `src/cryptobot/risk/kill_switch.py` | ✅ |
| Risk Correlation | `src/cryptobot/risk/correlation.py` | ✅ Helper. |
| Execution Engine | `src/cryptobot/execution/engine.py` | ✅ Order lifecycle + risk gate. |
| Execution Algorithms | `src/cryptobot/execution/algorithms.py` | ✅ TWAP/VWAP/POV. |
| Execution Venue Base | `src/cryptobot/execution/venue/base.py` | ✅ Abstract. |
| Execution Simulated | `src/cryptobot/execution/venue/simulated.py` | ✅ In-memory. |
| Execution Binance | `src/cryptobot/execution/venue/binance.py` | ✅ Live/testnet via ccxt.async_support. |
| Monitoring Metrics | `src/cryptobot/monitoring/metrics.py` | ✅ Prometheus metrics. |
| Monitoring Alerting | `src/cryptobot/monitoring/alerting.py` | ✅ Telegram/Discord/Email/PagerDuty. |
| Monitoring Health | `src/cryptobot/monitoring/health.py` | ✅ HealthMonitor + checkers. |
| Monitoring Dashboard | `src/cryptobot/monitoring/dashboard.py` | ✅ Grafana JSON builders. |
| CLI Main | `src/cryptobot/cli/main.py` | ✅ argparse (validate + paper + bot subcommands). |
| Utils Logging | `src/cryptobot/utils/logging.py` | ✅ structlog wrapper. |
| Utils Decorators | `src/cryptobot/utils/decorators.py` | ✅ retry (clamped jitter), timeout_decorator, circuit_breaker (raises in running loop). |
| Utils Types | `src/cryptobot/utils/types.py` | ✅ Candle, OrderBook, Trade, etc. |
| Utils Health Server | `src/cryptobot/utils/health_server.py` | ✅ stdlib ThreadingHTTPServer `/health` + `/metrics`. |
| Tests | `tests/unit/` | ✅ 22 unit test files. |
| Dockerfile | `Dockerfile` | ✅ Multi-stage (`base`/`production`/`test`), `python:3.14-slim`. |
| Compose | `docker-compose.yml` | ✅ Test + default profiles valid (monitoring dirs scaffolded). |
| `.dockerignore` | `.dockerignore` | ✅ Minimal context. |
| `.gitignore` | `.gitignore` | ✅ Includes `__pycache__/`. |
| Cargo workspace | `Cargo.toml` + 7 member crates | 🔲 Manifest + empty `src/` dirs in all 7; no `lib.rs`; `cargo build` fails. |
| `pyproject.toml` | `pyproject.toml` | ✅ setuptools build + CLI entry. |
| Migrations SQL | `migrations/001_extension.sql`, `002_hypertables.sql` | ✅ TimescaleDB schema. |
| ML Features | `src/cryptobot/ml/features.py` | ✅ 8 features (returns, RSI, MACD, ATR ratio, BB pos+width, log volume). |
| ML Models | `src/cryptobot/ml/models/direction.py` | ✅ sklearn logreg + numpy fallback. |
| ML Online | `src/cryptobot/ml/online.py` | ✅ `WalkForwardTrainer` (purged CV) + `DriftDetector`. |
| ML Strategy | `src/cryptobot/strategies/ml_strategy.py` | 🔲 Missing. |
| Backtest Runner | `src/cryptobot/backtest/runner.py` | ✅ OHLCV → strategy → exec → venue end-to-end. |
| Backtest Data | `src/cryptobot/backtest/data.py` | ✅ CSV / Parquet / TimescaleDB / synthetic. |
| Backtest Reporting | `src/cryptobot/backtest/reporting.py` | ✅ HTML tearsheet. |
| Backtest Validation | `src/cryptobot/backtest/validation.py` | ✅ Real walk-forward (rolling + embargo) + Monte Carlo block-permutation + deflated Sharpe. |
| Backtest Simulator | `src/cryptobot/backtest/simulator.py` | ✅ FillSimulator + factory. |
| Smart Order Router | `src/cryptobot/execution/router.py` | ✅ Best-price + latency rankers, fallback, split. |
| Adverse Selection | `src/cryptobot/execution/adverse_selection.py` | ✅ Mid-move / spread-widening / toxicity-spike cancel + `attach_to_engine`. |
| Risk Manager | `src/cryptobot/risk/manager.py` | ✅ Pre-trade (kill switch, notional, exposure); notional skipped when no price. |
| K8s | `deploy/k8s/` | ⚠️ Namespace, ConfigMap, Secret, PVC, Deployment, kustomization. **No Service, no HPA.** |

---

## 3. Current Architecture (Verified)

```
src/cryptobot/
├── config.py                 # ✅ Pydantic v2 Settings + YAML + env
├── core/
│   ├── events.py             # ✅ 40+ event types
│   ├── state.py              # ✅ SQLite persistence
│   ├── bus.py                # ✅ Pub/sub + history + replay
│   ├── portfolio.py          # ✅ Multi-strategy portfolio
│   └── clock.py              # ✅ Realtime / Simulated / Accelerated
├── data/
│   ├── ingestion.py          # ✅ OHLCV + BinanceDataIngestion
│   ├── storage.py            # ✅ TimescaleDB + Parquet + Hybrid
│   ├── cleaning.py           # ✅ DataCleaner + helpers
│   └── features.py           # 🔲 Missing (use ml/features.py)
├── strategies/
│   ├── base.py               # ✅ BaseStrategy + registry
│   ├── registry.py           # ✅ Re-export
│   ├── mean_reversion.py     # ✅ Z-score + RSI + BB
│   ├── trend_following.py    # ✅ EMA + ADX + ATR trailing
│   ├── stat_arb.py           # ✅ Pairs trading
│   ├── funding_arb.py        # ✅ Funding / basis arb
│   ├── market_making.py      # ✅ Avellaneda-Stoikov + AdverseSelectionGuard
│   └── ml_strategy.py        # 🔲 ML-driven strategy
├── ml/                       # ✅ Core pipeline
│   ├── features.py           # ✅ 8 features (returns, RSI, MACD, ATR, BB, log vol)
│   ├── models/
│   │   ├── direction.py      # ✅ sklearn logreg + numpy fallback
│   │   ├── volatility.py     # 🔲 Quantile regression
│   │   ├── regime.py         # 🔲 HMM / Transformer
│   │   └── ensemble.py       # 🔲 Stacking
│   ├── training.py           # 🔲 Purged CV + walk-forward
│   ├── inference.py          # 🔲 Online inference
│   └── auto_retrain.py       # 🔲 Drift detection
│   └── online.py             # ✅ WalkForwardTrainer (purged) + DriftDetector
├── execution/
│   ├── engine.py             # ✅ Order lifecycle + risk gate
│   ├── algorithms.py         # ✅ TWAP / VWAP / POV / IS / Iceberg / sweep / arrival / vwap_schedule
│   ├── router.py             # ✅ SmartOrderRouter (price + latency, fallback, split)
│   ├── adverse_selection.py  # ✅ AdverseSelectionGuard + QueuePosition + TopOfBook
│   ├── venue/
│   │   ├── base.py           # ✅ Abstract Venue
│   │   ├── simulated.py      # ✅ SimulatedVenue (slippage + commission)
│   │   └── binance.py        # ✅ BinanceVenue (ccxt.async_support; sandbox, retries, guardrails)
│   └── simulator.py          # 🔲 Realistic fill simulator (separate from backtest)
├── risk/
│   ├── manager.py            # ✅ Pre-trade (kill switch, notional, exposure)
│   ├── sizing.py             # ✅ Fixed / vol-target / Kelly
│   ├── limits.py             # ✅ RiskLimits
│   ├── correlation.py        # ✅ Helper
│   └── kill_switch.py        # ✅ Portfolio-driven
├── backtest/
│   ├── engine.py             # ✅ Event-driven backtester
│   ├── data.py               # ✅ CSV / Parquet / TimescaleDB / synthetic replay
│   ├── metrics.py            # ✅ Performance metrics (Sharpe, Sortino, DD, PF)
│   ├── validation.py         # ✅ Real WFA (rolling+embargo) + MC (block perm) + deflated Sharpe
│   ├── reporting.py          # ✅ HTML tearsheet
│   ├── simulator.py          # ✅ FillSimulator + factory
│   └── runner.py             # ✅ OHLCV → strategy → exec → venue end-to-end
├── monitoring/
│   ├── metrics.py            # ✅ Prometheus (Gauge for PnL, Counter for orders)
│   ├── dashboard.py          # ✅ Grafana JSON builders
│   ├── alerting.py           # ✅ Telegram/Discord/Email/PagerDuty (lazy init)
│   └── health.py             # ✅ HealthMonitor + checkers (async-aware)
├── cli/
│   ├── main.py               # ✅ argparse (validate/paper/bot/serve subcommands)
│   ├── backtest.py           # 🔲 (folded into main.py)
│   ├── paper.py              # 🔲 (folded into main.py)
│   ├── live.py               # 🔲
│   └── optimize.py           # 🔲 Parameter optimization (Optuna)
└── utils/
    ├── logging.py            # ✅ structlog wrapper
    ├── decorators.py         # ✅ retry (clamped jitter) / timeout / circuit_breaker (raises in running loop)
    ├── types.py              # ✅ Candle, OrderBook, Trade, OHLCVBar, PerformanceMetrics
    └── health_server.py      # ✅ stdlib ThreadingHTTPServer `/health` + `/metrics`
```

```

## 4. Implementation Phases

> **Status legend**: ✅ implemented · ⚠️ partial · 🔲 pending.
> Cross-reference `PROJECT_MEMORY/12_Feature_Status.md`.

### Phase 1: Core Infrastructure (Week 1-2) — ✅ mostly done
- [x] Event bus with replay capability (`core/bus.py`)
- [x] Portfolio state management (`core/portfolio.py`)
- [x] Time abstraction (`core/clock.py`, three clock modes + factory)
- [x] Data ingestion pipeline (Binance helpers in `data/ingestion.py`)
- [x] TimescaleDB schema (defined in `data/storage.py`; no SQL migrations yet)
- [x] Structured logging + Prometheus metrics

### Phase 2: Backtesting Engine (Week 2-3) ⭐ — ✅ done
- [x] Event-driven backtester core (`backtest/engine.py`)
- [x] Fill simulation (`backtest/simulator.py`, `execution/venue/simulated.py`)
- [x] Historical data replay helper (`backtest/data.py` — CSV/Parquet/TimescaleDB/synthetic)
- [x] Performance metrics: Sharpe, Sortino, MaxDD, win_rate, profit_factor
- [x] Full backtest reporting & tearsheet (`backtest/reporting.py` — HTML)
- [x] Walk-forward validation framework (`backtest/validation.py` — rolling + embargo)
- [x] Monte Carlo robustness testing (`backtest/validation.py` — block permutation)
- [x] Deflated Sharpe ratio (`backtest/validation.py`)
- [x] Tearsheet generation (HTML) (`backtest/reporting.py`)
- [x] End-to-end runner (`backtest/runner.py` — OHLCV → strategy → exec → venue)

### Phase 3: Strategy Framework (Week 3-4) ⭐ — ⚠️ partial
- [x] Base strategy class with lifecycle hooks (`strategies/base.py`)
- [x] Signal generation interface (returns `List[OrderEvent]`)
- [ ] Position management primitives (scaling, stops) — BaseStrategy exposes lifecycle only
- [x] Strategy registry (`StrategyRegistry` singleton)
- [ ] Parameter optimization (Optuna) — no integration yet

### Phase 4: Core Strategies (Week 4-6) ⭐ — ⚠️ partial (ml_strategy.py missing)
- [x] Mean Reversion: Z-score + RSI + BB (`strategies/mean_reversion.py`)
- [x] Trend Following: EMA + ADX + ATR trailing stops (`strategies/trend_following.py`)
- [x] Statistical Arbitrage: hedge ratio + correlation gate + z-score (`strategies/stat_arb.py`)
- [x] Funding Arbitrage: basis + carry + funding rate (`strategies/funding_arb.py`)
- [x] Market Making: Avellaneda-Stoikov + AdverseSelectionGuard (`strategies/market_making.py`)
- [ ] ML-driven strategy (`strategies/ml_strategy.py`) — file does not exist

### Phase 5: Risk Management (Week 6-7) ⭐ — ⚠️ partial
- [x] Pre-trade risk checks (exposure, drawdown via kill switch, notional bounds)
- [x] Notional check skipped when no price available (market order pre-trade) — implemented (B038)
- [x] Dynamic position sizing helpers (Kelly, vol-target, fixed-fraction)
- [ ] Portfolio optimization (HRP, mean-CVaR) — not implemented
- [x] Kill switch (`risk/kill_switch.py` driven by portfolio signal)
- [ ] Real-time risk dashboard — Grafana panels exist but not wired live

### Phase 6: ML Pipeline (Week 7-9) ⭐ — ⚠️ partial (core only)
- [x] Feature engineering (`ml/features.py`) — returns, RSI, MACD, ATR ratio, BB pos+width, log volume
- [x] Direction classifier (`ml/models/direction.py`) — sklearn logreg preferred, numpy fallback
- [x] Walk-forward training with purged CV (`ml/online.py` WalkForwardTrainer)
- [x] Auto-retrain on drift detection (`ml/online.py` DriftDetector)
- [ ] Feature store with versioning (stretch)
- [ ] Volatility forecasting (`ml/models/volatility.py` missing)
- [ ] Regime detection (`ml/models/regime.py` missing)
- [ ] Ensemble stacking / blending (`ml/models/ensemble.py` missing)
- [ ] Online inference pipeline — current DirectionClassifier <10ms; production pipeline deferred

### Phase 7: Execution Engine (Week 9-10) — ✅ done
- [x] Order management (`execution/engine.py`) with `build_venue(mode)` factory
- [x] Execution algorithms helpers (TWAP/VWAP/POV/IS/Iceberg/sweep/arrival/vwap_schedule in `execution/algorithms.py`)
- [x] `Venue` interface + `SimulatedVenue` (slippage + commission)
- [x] `BinanceVenue` (ccxt.async_support; retries, sandbox mode, credential guard)
- [x] Smart order routing (`execution/router.py`) — `SmartOrderRouter` with price-rank and latency-rank, fallbacks, split-and-route
- [x] Adverse selection protection (`execution/adverse_selection.py`)
  Mid-move cancel threshold, spread-widening cancel, toxicity-spike cancel,
  QueuePosition + TopOfBook + integrate via `attach_to_engine`.
- [x] Latency monitoring (`monitoring/metrics.py` `record_venue_quote_latency`,
      `record_routing_decision`, `record_execution_latency`). Router records per-venue
      quote latency + selected/fallback/split/failed; SimulatedVenue + BinanceVenue
      record their own round-trip on submit/cancel.

### Phase 8: Live Trading & Monitoring (Week 10-12) — ⚠️ partial
- [x] Compose stack (`docker-compose.yml`: Timescale, Redis, Prometheus, Grafana, Alertmanager, Loki, Promtail, Nginx)
- [x] Default profile valid (monitoring dirs scaffolded)
- [x] Paper trading profile (`cryptobot-paper` service, `EXECUTION_MODE=paper` env)
- [x] Live trading profile fully wired (BinanceVenue, build_venue factory)
- [x] Grafana dashboards (JSON under `monitoring/grafana/` and `docker/grafana/`)
- [x] Alerting channels (Telegram/Discord/Email/PagerDuty stubs)
- [x] Health checks (`monitoring/health.py`)
- [x] `cryptobot` HTTP `/health` endpoint — stdlib ThreadingHTTPServer in `utils/health_server.py`, exposed via `cli serve` / `cli bot`. Dockerfile HEALTHCHECK passes against it.
- [x] Docker base `python:3.14-slim`
- [x] Kubernetes manifests (`deploy/k8s/`) — namespace, ConfigMap, Secret, PVC, Deployment, kustomization. **No Service, no HPA.**
- [x] Multi-arch Docker images (`scripts/build_multiarch.sh`, `.github/workflows/release.yml`)
- [x] GitHub Actions CI (`.github/workflows/ci.yml`) — lint, unit, docker test target, multi-arch buildx

---

## 5. Key Technical Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Primary Language** | Python 3.14 | ML ecosystem, rapid iteration. `Dockerfile` uses `python:3.14-slim`. |
| **Performance-Critical** | **Rust (via PyO3/maturin)** — pending | Backtest engine, fill simulator, feature computation, order book math. Currently: `Cargo.toml` + 7 member crates with empty `src/` dirs (all 7). No `lib.rs` files. `cargo build` fails. CI does not run cargo. |
| **Async Framework** | asyncio + aiohttp | Native, high-performance, WebSocket support |
| **Database** | TimescaleDB + SQLite | Time-series optimized, local dev friendly |
| **Message Bus** | Redis Streams + local asyncio | Pub/sub, replay, persistence |
| **ML Framework** | sklearn + LightGBM (optional) | DirectionClassifier uses sklearn logreg preferred; numpy fallback. LightGBM in `requirements/prod.txt` but `ml/models/direction.py` does not import it — config mismatch (`ml.models.direction.type: lightgbm` in YAML). Remove dep or implement. |
| **Optimization** | Optuna | Bayesian optimization, pruning, distributed |
| **Backtesting** | Custom event-driven (Rust core) | Full control over fill logic, microstructure |
| **Config** | Pydantic + YAML | Type safety, validation, env overrides |
| **Monitoring** | Prometheus + Grafana | Industry standard, rich ecosystem |
| **Deployment** | Docker Compose → K8s | Local dev → production scaling |
| **VPS Target** | Linux x86_64 / ARM64 | Multi-arch Docker, systemd services |

---

## 5b. Multi-Language Architecture (Python + Rust)

```
┌─────────────────────────────────────────────────────────────┐
│                    Python Layer (Orchestration)              │
│  Config │ CLI │ Strategies │ ML Pipeline │ Monitoring       │
└──────────────────────────┬────────────────────────────────────┘
                           │ PyO3 / CFFI
┌──────────────────────────▼────────────────────────────────────┐
│                    Rust Layer (Performance)                   │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐           │
│  │ Backtest    │  │ Features    │  │ Order Book  │           │
│  │ Engine      │  │ Engine      │  │ Math        │           │
│  │ (simulator) │  │ (100+ feat) │  │ (VPIN, etc) │           │
│  └─────────────┘  └─────────────┘  └─────────────┘           │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐           │
│  │ Risk Math   │  │ Portfolio   │  │ Statistics  │           │
│  │ (Kelly,     │  │ Optimizer   │  │ (PBO, MC)   │           │
│  │  CVaR)      │  │ (HRP)       │  │             │           │
│  └─────────────┘  └─────────────┘  └─────────────┘           │
└─────────────────────────────────────────────────────────────┘
```

### Rust Crate Structure (`crates/`)
```
crates/
├── cryptobot-core/          # Shared types, events, math
├── cryptobot-backtest/      # Event-driven backtester, fill simulator
├── cryptobot-features/      # Feature computation (SIMD optimized)
├── cryptobot-risk/          # Risk math: Kelly, CVaR, HRP, correlation
├── cryptobot-stats/         # Statistical validation: PBO, Monte Carlo, deflated Sharpe
├── cryptobot-orderbook/     # Order book operations, VPIN, microstructure
└── cryptobot-py/            # PyO3 bindings for Python integration
```

**Current state**: All 7 crates exist with `Cargo.toml` + empty `src/` dirs (no `lib.rs`). `cargo build` fails. Not integrated in CI.

### Build & Deploy
- **Local**: `maturin develop` (auto-compiles Rust, installs Python package)
- **CI/CD**: Cross-compile for x86_64 + ARM64, publish wheels to PyPI
- **VPS**: Pre-built wheels, no Rust toolchain needed on server
- **Docker**: Multi-stage build (Rust builder → Python runtime)

---

## 6. Strategy Design Principles

### Statistical Validation Requirements (Per Strategy)
1. **Minimum 5 years out-of-sample data** (or equivalent walk-forward windows)
2. **Purged/embargoed cross-validation** to prevent look-ahead bias
3. **Monte Carlo permutation testing** (1000+ runs) for significance
4. **Probabilistic Backtest Overfitting (PBO)** score < 0.5
5. **Deflated Sharpe Ratio** accounting for multiple testing
6. **Sensitivity analysis** on key parameters (±20%)
7. **Stress testing**: 2020 COVID, 2022 bear, 2023 recovery regimes

### Signal Quality Metrics
- **Information Coefficient (IC)** > 0.05
- **ICIR** (IC / std(IC)) > 1.0
- **Turnover** < strategy capacity
- **Decay profile** characterized (half-life)

---

## 7. Risk Management Framework

### Position Sizing Hierarchy
```
1. Strategy Signal Strength → Target Weight
2. Kelly Fraction (constrained) → Risk-Adjusted Weight
3. Volatility Targeting → Vol-Normalized Weight
4. Correlation Adjustment → Diversified Weight
5. Portfolio Optimization (HRP/CVaR) → Final Weight
6. Hard Limits → Capped Weight
```

### Risk Limits (from config)
- Max total exposure: 80% capital
- Max single position: 20% capital
- Max daily loss: 5% (soft), 10% (hard kill switch)
- Max drawdown: 15%
- Max pair correlation: 0.7
- Min order size: $10, Max: $10,000

---

## 8. ML Feature Categories (100+ Features)

| Category | Examples |
|----------|----------|
| **Returns** | 1m, 5m, 15m, 1h, 4h, 1d log returns |
| **Volatility** | Realized vol (5m-1d), Parkinson, Garman-Klass, Yang-Zhang |
| **Trend** | EMA ratios, MACD, ADX, Aroon, Supertrend |
| **Mean Reversion** | Z-score, RSI, Stochastic, BB position, Percentile rank |
| **Microstructure** | Spread, depth imbalance, VPIN, order flow toxicity, Kyle's lambda |
| **Volume** | Volume ratio, OBV, VWAP deviation, volume profile |
| **Funding** | Funding rate, basis, term structure, predicted funding |
| **Regime** | HMM state, volatility regime, trend regime, correlation regime |
| **Cross-Asset** | BTC dominance, ETH/BTC ratio, stablecoin supply, DXY |
| **On-Chain** | Exchange flows, whale alerts, funding rates, OI changes |
| **Alternative** | Fear & Greed, Google Trends, GitHub activity |

---

## 9. Next Immediate Steps

### Step 1: Create Project Structure & Core Infrastructure
```bash
# Create missing directories
mkdir -p src/cryptobot/{core,strategies,ml,execution,risk,backtest,monitoring,cli,utils,data}
mkdir -p tests/{unit,integration,fixtures}
mkdir -p docker seccomp compose scripts migrations
```

### Step 2: Implement Event Bus & Portfolio (core/)
- `core/bus.py` - Async event bus with replay
- `core/portfolio.py` - Multi-strategy portfolio state
- `core/clock.py` - Simulated/real time abstraction

### Step 3: Build Backtesting Engine (backtest/) ⭐
- `backtest/engine.py` - Event-driven backtester
- `backtest/simulator.py` - Realistic fill model
- `backtest/metrics.py` - Comprehensive analytics
- `backtest/validation.py` - Walk-forward, Monte Carlo

### Step 4: Strategy Framework (strategies/)
- `strategies/base.py` - Abstract base class
- `strategies/registry.py` - Plugin system
- Implement 4 core strategies

### Step 5: Risk Manager (risk/)
- Pre-trade checks, sizing, limits, kill switch

### Step 6: ML Pipeline (ml/)
- Features, models, training, inference, auto-retrain

---

## 10. Validation & Quality Gates

### Before Merging Any Strategy
- [ ] Unit tests pass (>90% coverage)
- [ ] Integration test with backtester passes
- [ ] Walk-forward validation on 3+ regimes
- [ ] Monte Carlo robustness (p < 0.05)
- [ ] No look-ahead bias (purged CV)
- [ ] Parameter sensitivity acceptable
- [ ] Capacity analysis documented

### Before Live Deployment
- [ ] Paper trading 30+ days positive
- [ ] Max drawdown < 10% in paper
- [ ] Kill switch tested and verified
- [ ] Failover tested (exchange disconnect, data gap)
- [ ] Latency < 100ms p99 (order to ack)
- [ ] Monitoring alerts configured and tested

---

## 11. File Tracking

### Created in This Plan
- [x] `plan.md` (this file)

### To Create Next
- [ ] `src/cryptobot/strategies/ml_strategy.py` — ML-driven strategy (Phase 4)
- [ ] `src/cryptobot/data/features.py` — or update references to use `ml/features.py`
- [ ] `src/cryptobot/ml/models/volatility.py` — Quantile regression
- [ ] `src/cryptobot/ml/models/regime.py` — HMM / Transformer
- [ ] `src/cryptobot/ml/models/ensemble.py` — Stacking
- [ ] `src/cryptobot/ml/training.py` — Purged CV + walk-forward
- [ ] `src/cryptobot/ml/inference.py` — Online inference
- [ ] `src/cryptobot/ml/auto_retrain.py` — Drift detection
- [ ] `crates/*/src/lib.rs` — Rust crate implementations
- [ ] `deploy/k8s/05-service.yaml` — K8s Service
- [ ] `deploy/k8s/06-hpa.yaml` — K8s HPA
- [ ] `src/cryptobot/cli/optimize.py` — Parameter optimization (Optuna)

---

## 12. Notes for Future Sessions

> **Context Restoration Prompt**: "Read `plan.md` to understand the full architecture and current phase."

### Key References
- Existing config: `configs/base.yaml`
- Existing code: `src/cryptobot/`
- Requirements: `requirements/prod.txt`

### Current Phase
**Phase 4/6/8 overlap**: Core infrastructure ✅, Backtester ✅, Strategies 6/6 ✅ (ml_strategy.py created), ML core ✅, Execution ✅, Risk ✅, Monitoring ✅, Live/Compose ✅, K8s ✅. Next: Rust crate implementations, ML volatility/regime/ensemble models.

### Blockers
- Rust workspace non-functional — `cargo build` fails, no `lib.rs` in any crate
- ML volatility/regime/ensemble models not implemented (disabled in config)
- Need TimescaleDB running for integration tests (docker-compose)
- Need historical data for backtesting (Binance API or data vendor)

---

## 13. Comprehensive Algorithmic Trading Strategy Catalog

This section documents ALL algorithmic trading strategies that the system must support, organized by category. Each strategy represents a potential implementation in the strategies/ directory.

### 13.1 Trend Following Strategies (20 strategies)
| Strategy | Description | Implementation Priority |
|----------|-------------|------------------------|
| Moving Average Crossover | Buys/sells when fast MA crosses slow MA | High (core) |
| Exponential Moving Average (EMA) | Recent prices weighted more heavily | High (core) |
| Simple Moving Average (SMA) | Average price over fixed period | High (core) |
| Triple Moving Average | Three MAs to reduce false signals | Medium |
| Dual Moving Average | Fast/slow MA for entry/exit | High (core) |
| MACD Strategy | MACD for momentum changes | High (core) |
| ADX Trend Following | ADX for trend strength | High (core) |
| Donchian Channel Breakout | Breakouts of historical highs/lows | High (core) |
| Supertrend | Volatility + trend for direction | High (core) |
| Ichimoku Cloud | Multi-indicator: trend, momentum, S/R | Medium |
| Parabolic SAR | Trailing stop points for trends | Medium |
| Hull Moving Average | Reduced lag, smooth trend detection | Medium |
| Kaufman's Adaptive MA (KAMA) | Adjusts sensitivity to volatility | Medium |
| Triple Exponential MA (TEMA) | Reduced lag vs traditional MA | Medium |
| Double Exponential MA (DEMA) | Faster trend detection than EMA | Medium |
| Zero Lag Moving Average | Attempts to eliminate lag | Low |
| Regression Trend | Regression line for trend direction | Medium |
| Linear Regression Channel | Upper/lower channels around regression | Medium |
| Trendline Breakout | Automated trendline break detection | Low |
| Price Channel Breakout | Highest/lowest prices over period | Medium |

### 13.2 Mean Reversion Strategies (14 strategies)
| Strategy | Description | Implementation Priority |
|----------|-------------|------------------------|
| Bollinger Band Reversion | Buy lower band, sell upper band | High (core) |
| RSI Reversion | Overbought/oversold RSI levels | High (core) |
| Stochastic Oscillator | Momentum relative to price range | High (core) |
| Z-Score Reversion | Deviation from mean (statistical) | High (core) |
| VWAP Reversion | Price returns to VWAP | High (core) |
| Anchored VWAP | VWAP from significant event | Medium |
| Keltner Channel Reversion | ATR-based price channels | High (core) |
| Commodity Channel Index (CCI) | Extreme deviations from average | Medium |
| Williams %R | Momentum for reversal signals | Medium |
| Fisher Transform | Prices to normal distribution | Medium |
| Ornstein-Uhlenbeck Process | Mathematical mean-reversion model | Medium (Rust) |
| Distance from Moving Average | Deviation from MA | Medium |
| Gaussian Mean Reversion | Normal distribution assumptions | Medium |
| Kalman Filter Mean Reversion | Dynamic true mean estimation | High (Rust) |

### 13.3 Statistical Arbitrage (15 strategies)
| Strategy | Description | Implementation Priority |
|----------|-------------|------------------------|
| Pair Trading | Two correlated assets diverge | High (core) |
| Basket Trading | Multiple related assets simultaneously | Medium |
| Cointegration Trading | Long-term statistical relationships | High (core) |
| Correlation Trading | Temporary correlation changes | Medium |
| PCA Arbitrage | Principal Component Analysis anomalies | Medium (Rust) |
| ETF Arbitrage | ETF vs holdings price differences | Low |
| Index Arbitrage | Index vs futures differences | Low |
| Convertible Arbitrage | Convertible bonds vs stock | Low |
| Dispersion Trading | Index vol vs constituent vol | Low |
| Volatility Arbitrage | Volatility pricing differences | Medium |
| Cross Exchange Arbitrage | Same asset, different exchanges | High (core) |
| Cross Asset Arbitrage | Relationships between asset classes | Medium |
| Calendar Arbitrage | Different contract expirations | Medium |
| Triangular Arbitrage | Exchange rate inconsistencies | Low |
| Interest Rate Arbitrage | Interest rate differences | Low |

### 13.4 Market Making (9 strategies)
| Strategy | Description | Implementation Priority |
|----------|-------------|------------------------|
| Passive Market Making | Resting limit orders | High (core) |
| Dynamic Market Making | Continuously adjusts spreads | High (core) |
| Inventory-Based Market Making | Controls inventory risk | High (core) |
| Spread Capture | Profits from bid-ask spread | High (core) |
| Liquidity Provision | Supplies market liquidity | High (core) |
| Adaptive Quote Market Making | Adjusts quotes using conditions | High (core) |
| Avellaneda-Stoikov | Mathematical optimal model | High (core, Rust) |
| Optimal Bid-Ask Quoting | Optimizes quote placement | High (core, Rust) |
| Reinforcement Learning Market Maker | AI learns optimal policy | Medium (ML) |

### 13.5 High-Frequency Trading (13 strategies) - *Research/Advanced*
| Strategy | Description | Implementation Priority |
|----------|-------------|------------------------|
| Latency Arbitrage | Tiny timing differences | Low (specialized) |
| Quote Stuffing | Floods market (often prohibited) | Excluded |
| Momentum Ignition | Trigger momentum (regulated) | Excluded |
| Flash Arbitrage | Extremely short-lived arb | Low |
| Smart Order Routing | Best execution venue | High (core) |
| Liquidity Detection | Finds hidden liquidity | Medium |
| Order Book Imbalance | Bid/ask imbalance signals | High (core, Rust) |
| Queue Position Optimization | Execution priority improvement | Medium |
| Microstructure Alpha | Market microstructure patterns | High (Rust) |
| Tick Scalping | Tiny price movements | Low |
| Sub-penny Trading | Fractions of tick size | Low |
| Hidden Liquidity Detection | Iceberg order detection | Medium (Rust) |
| Iceberg Detection | Partially hidden orders | Medium (Rust) |

### 13.6 Momentum Strategies (11 strategies)
| Strategy | Description | Implementation Priority |
|----------|-------------|------------------------|
| RSI Momentum | RSI for strong momentum | High (core) |
| MACD Momentum | MACD confirmation | High (core) |
| Rate of Change (ROC) | Percentage price change | Medium |
| Momentum Factor | Ranks assets by momentum | Medium |
| Relative Strength Ranking | Asset performance comparison | Medium |
| Dual Momentum | Relative + absolute momentum | High (core) |
| Absolute Momentum | Positive/negative returns | Medium |
| Cross-sectional Momentum | Buy strongest, sell weakest | High (core) |
| Time-Series Momentum | Asset's own history | High (core) |
| Price Breakout Momentum | New highs/lows | High (core) |
| Volume Momentum | Volume confirms trends | Medium |

### 13.7 Breakout Strategies (12 strategies)
| Strategy | Description | Implementation Priority |
|----------|-------------|------------------------|
| Opening Range Breakout | First period range break | High (core) |
| Donchian Breakout | Channel breakout | High (core) |
| Resistance Breakout | Resistance level break | High (core) |
| Support Breakdown | Support level break | High (core) |
| Bollinger Squeeze | Volatility compression then expansion | High (core) |
| Volatility Expansion | Volatility breakout | Medium |
| NR4/NR7 Breakout | Narrow range bars | Medium |
| Gap Breakout | Price gap continuation | Medium |
| Inside Bar Breakout | Inside bar pattern break | Medium |
| Triangle Breakout | Triangle pattern break | Medium |
| Rectangle Breakout | Rectangle pattern break | Medium |
| Flag Breakout | Flag pattern break | Medium |

### 13.8 Volatility Strategies (10 strategies)
| Strategy | Description | Implementation Priority |
|----------|-------------|------------------------|
| ATR Breakout | ATR-based breakout | High (core) |
| ATR Trailing Stop | ATR for trailing stops | High (core) |
| GARCH Volatility Forecasting | GARCH model forecasting | High (Rust/ML) |
| Implied vs Realized Volatility | IV/RV spread | Medium |
| Volatility Targeting | Target portfolio volatility | High (core) |
| Volatility Scaling | Scale positions by vol | High (core) |
| Volatility Carry | Carry from vol term structure | Medium |
| VIX Strategy | VIX-based signals | Low (crypto: use IV) |
| Gamma Scalping | Options gamma scalping | Low (equities) |
| Vega Arbitrage | Vega exposure arbitrage | Low |

### 13.9 Volume-Based Strategies (10 strategies)
| Strategy | Description | Implementation Priority |
|----------|-------------|------------------------|
| VWAP | Volume-weighted average price | High (core) |
| TWAP | Time-weighted average price | High (core) |
| Percentage of Volume (POV) | Participate at % of volume | High (core) |
| On-Balance Volume (OBV) | Cumulative volume flow | Medium |
| Chaikin Money Flow | Volume-weighted momentum | Medium |
| Volume Profile | Price-volume distribution | Medium |
| Volume Spike Detection | Unusual volume spikes | High (core) |
| Cumulative Delta | Buy vs sell pressure | Medium |
| Footprint Trading | Detailed volume at price | Medium |
| Volume Weighted Momentum | Momentum weighted by volume | Medium |

### 13.10 Order Book Strategies (10 strategies)
| Strategy | Description | Implementation Priority |
|----------|-------------|------------------------|
| Level II Analysis | Full depth analysis | High (core, Rust) |
| DOM (Depth of Market) | Order book visualization | High (core, Rust) |
| Order Flow Imbalance | Bid/ask flow imbalance | High (core, Rust) |
| Iceberg Detection | Hidden order detection | High (core, Rust) |
| Absorption Detection | Large order absorption | Medium (Rust) |
| Delta Divergence | Price vs delta divergence | Medium (Rust) |
| Queue Prediction | Queue position prediction | Medium (Rust) |
| Order Book Pressure | Weighted book pressure | High (core, Rust) |
| Hidden Order Detection | Undisclosed orders | Medium (Rust) |
| Liquidity Vacuum | Thin liquidity zones | Medium (Rust) |

### 13.11 Execution Algorithms (10 strategies)
| Strategy | Description | Implementation Priority |
|----------|-------------|------------------------|
| TWAP | Time-weighted average price | High (core) |
| VWAP | Volume-weighted average price | High (core) |
| Implementation Shortfall | Minimize slippage vs arrival | High (core) |
| Arrival Price | Benchmark to arrival price | Medium |
| Percentage of Volume | Participate at target rate | High (core) |
| Adaptive Participation | Dynamic participation rate | Medium |
| Sniper Algorithm | Opportunistic execution | Medium |
| Dark Pool Routing | Dark pool access | Low |
| Smart Order Routing | Multi-venue optimization | High (core) |
| Child Order Execution | Order slicing logic | High (core) |

### 13.12 Machine Learning Strategies (22 strategies)
| Strategy | Description | Implementation Priority |
|----------|-------------|------------------------|
| Random Forest | Ensemble trees | Medium |
| Gradient Boosting | Sequential boosting | High (core) |
| XGBoost | Optimized gradient boosting | High (core) |
| LightGBM | Fast gradient boosting | High (core) |
| CatBoost | Categorical boosting | High (core) |
| Support Vector Machine (SVM) | Kernel-based classification | Low |
| K-Nearest Neighbors | Distance-based | Low |
| Decision Trees | Interpretable rules | Low |
| Bayesian Networks | Probabilistic graphical | Low |
| Hidden Markov Models | Regime detection | High (core) |
| LSTM | Long short-term memory | High (ML) |
| GRU | Gated recurrent unit | High (ML) |
| Transformers | Attention-based sequence | High (ML) |
| CNN for Time Series | Convolutional time series | Medium |
| Autoencoders | Feature learning | Medium |
| GANs | Generative adversarial | Low |
| Reinforcement Learning | Policy optimization | Medium |
| Deep Q Learning | Value-based RL | Medium |
| PPO | Proximal policy optimization | Medium |
| Actor-Critic | Policy + value | Medium |
| Meta-Learning | Learning to learn | Low |
| Online Learning | Incremental updates | High (ML) |

### 13.13 AI-Based Trading (8 strategies)
| Strategy | Description | Implementation Priority |
|----------|-------------|------------------------|
| Sentiment Analysis | News/social sentiment | Medium |
| News Trading | Event-driven news | Medium |
| Earnings Call NLP | Transcript analysis | Low |
| Social Media Analysis | Twitter/Reddit signals | Low |
| LLM Signal Generation | Large language models | Medium |
| Event Extraction | Structured event parsing | Low |
| Knowledge Graph Trading | Entity relationships | Low |
| AI Portfolio Optimization | ML-based allocation | Medium |

### 13.14 Options Strategies (12 strategies) - *Equities/Crypto Options*
| Strategy | Description | Implementation Priority |
|----------|-------------|------------------------|
| Delta Hedging | Neutralize delta exposure | Low |
| Gamma Scalping | Gamma exposure trading | Low |
| Vega Neutral | Neutralize vega | Low |
| Theta Harvesting | Collect time decay | Low |
| Iron Condor | Defined risk spread | Low |
| Covered Calls | Income generation | Low |
| Straddle | Volatility play | Low |
| Strangle | Wide volatility play | Low |
| Butterfly Spread | Targeted range | Low |
| Calendar Spread | Time spread | Low |
| Ratio Spread | Asymmetric spread | Low |
| Volatility Surface Arbitrage | Surface anomalies | Low |

### 13.15 Portfolio Strategies (11 strategies)
| Strategy | Description | Implementation Priority |
|----------|-------------|------------------------|
| Risk Parity | Equal risk contribution | High (core) |
| Equal Weight | Equal allocation | Medium |
| Mean-Variance Optimization | Markowitz optimization | High (core) |
| Black-Litterman | View-adjusted optimization | Medium |
| Kelly Criterion | Optimal bet sizing | High (core, Rust) |
| Hierarchical Risk Parity | Hierarchical clustering | High (core, Rust) |
| Minimum Variance | Minimize portfolio variance | Medium |
| Maximum Sharpe Ratio | Optimize risk-adjusted return | Medium |
| Equal Risk Contribution | ERC allocation | Medium |
| Factor Investing | Factor-based allocation | Medium |
| Smart Beta | Factor-tilted indexing | Low |

### 13.16 Factor Investing (10 factors)
| Factor | Description | Implementation Priority |
|--------|-------------|------------------------|
| Value | Cheap vs fundamentals | Medium |
| Growth | Earnings growth | Medium |
| Quality | Profitability/low debt | Medium |
| Momentum | Price momentum | High (core) |
| Low Volatility | Low beta/volatility | Medium |
| Dividend Yield | Income focus | Low (equities) |
| Size | Small vs large cap | Medium |
| Profitability | High profit margins | Medium |
| Investment | Low asset growth | Medium |
| Multi-Factor Models | Combined factors | High (core) |

### 13.17 Event-Driven Strategies (11 strategies)
| Strategy | Description | Implementation Priority |
|----------|-------------|------------------------|
| Earnings Releases | Post-earnings drift | Low (equities) |
| Dividend Capture | Ex-dividend arbitrage | Low |
| Merger Arbitrage | M&A deal spreads | Low |
| Acquisition Arbitrage | Takeover plays | Low |
| Spin-Off Trading | Post-spin performance | Low |
| IPO Trading | New listing patterns | Low |
| Insider Transactions | Insider buying/selling | Low |
| Economic Calendar Events | CPI, NFP, Fed decisions | Medium |
| Central Bank Announcements | Rate decisions | Medium |
| Options Expiration | OpEx effects | Low |
| Index Rebalancing | Rebalance front-running | Low |

### 13.18 Calendar Strategies (8 strategies)
| Strategy | Description | Implementation Priority |
|----------|-------------|------------------------|
| Turn-of-the-Month | Month-end effects | Low |
| January Effect | January anomaly | Low |
| Weekend Effect | Weekend patterns | Low (crypto 24/7) |
| Holiday Effect | Pre/post holiday | Low |
| End-of-Quarter | Quarter-end flows | Low |
| Options Expiration Week | OpEx week patterns | Low |
| Futures Rollover | Contract roll effects | Medium |
| Triple Witching | Quad witching effects | Low |

### 13.19 Cryptocurrency-Specific Strategies (11 strategies)
| Strategy | Description | Implementation Priority |
|----------|-------------|------------------------|
| Funding Rate Arbitrage | Perpetual funding capture | **Highest (core)** |
| Spot-Futures Arbitrage | Spot vs futures basis | **Highest (core)** |
| Perpetual Futures Basis | Basis term structure | **Highest (core)** |
| Cross-Chain Arbitrage | Same asset different chains | Medium |
| DEX Arbitrage | DEX price differences | High (core) |
| CEX-DEX Arbitrage | Centralized vs decentralized | High (core) |
| Flash Loan Arbitrage | Atomic arbitrage | Medium (DeFi) |
| MEV Searchers | Maximal extractable value | Low (specialized) |
| Yield Farming Rotation | Yield optimization | Medium |
| Liquidation Hunting | Forced liquidation signals | Medium |
| Stablecoin Arbitrage | Peg deviation | High (core) |

### 13.20 Risk Management Algorithms (10 strategies)
| Strategy | Description | Implementation Priority |
|----------|-------------|------------------------|
| Dynamic Position Sizing | Signal-strength sizing | **Highest (core)** |
| Kelly Position Sizing | Kelly criterion | **Highest (core, Rust)** |
| Volatility Position Sizing | Vol-targeted sizing | **Highest (core)** |
| Fixed Fractional Position Sizing | Fixed % per trade | Medium |
| Maximum Drawdown Control | Portfolio DD limits | **Highest (core)** |
| Circuit Breakers | Auto-stop on thresholds | **Highest (core)** |
| Dynamic Stop Loss | Adaptive stops | High (core) |
| Trailing Stop | Trend-following stops | High (core) |
| Portfolio Hedging | Correlation hedges | High (core) |
| Correlation Hedging | Dynamic correlation mgmt | High (core) |

### 13.21 Quantitative Models (14 models)
| Model | Description | Implementation Priority |
|-------|-------------|------------------------|
| CAPM | Capital asset pricing | Low |
| Fama-French Three-Factor | Size, value, market | Medium |
| Fama-French Five-Factor | +profitability, investment | Medium |
| Carhart Four-Factor | +momentum | Medium |
| Black-Scholes | Option pricing | Low |
| Binomial Tree | Discrete option pricing | Low |
| Heston Model | Stochastic volatility | Low |
| SABR Model | Volatility smile | Low |
| Monte Carlo Simulation | Path simulation | High (Rust) |
| Geometric Brownian Motion | Price process | Medium |
| Jump Diffusion | Jumps in price | Medium |
| Ornstein-Uhlenbeck | Mean-reverting process | High (Rust) |
| Kalman Filter | State estimation | High (Rust) |
| Hidden Markov Models | Regime detection | High (core, ML) |

### 13.22 Alternative Data Strategies (11 strategies)
| Strategy | Description | Implementation Priority |
|----------|-------------|------------------------|
| Satellite Imagery | Physical activity | Low |
| Weather Data | Commodity impacts | Low |
| Shipping Data | Global trade flows | Low |
| Credit Card Transactions | Consumer spending | Low |
| Mobile Location Data | Foot traffic | Low |
| Web Traffic | Company activity | Low |
| Patent Analysis | Innovation signals | Low |
| Job Postings | Hiring trends | Low |
| ESG Data | Sustainability factors | Low |
| Supply Chain Data | Production signals | Low |
| Google Trends | Search interest | Medium |
| Internet Search Volume | Attention metrics | Medium |

### 13.23 Hybrid Strategies (9 strategies)
| Strategy | Description | Implementation Priority |
|----------|-------------|------------------------|
| Trend + Momentum | Combined signals | High (core) |
| Trend + Mean Reversion | Regime-adaptive | High (core) |
| Momentum + Volatility | Vol-adjusted momentum | High (core) |
| Multi-Factor Models | Multiple factor signals | High (core) |
| Ensemble Learning | Model combination | High (ML) |
| Meta-Strategy Selection | Strategy selector | High (ML) |
| Regime Switching | HMM-based switching | High (core, ML) |
| Adaptive Portfolio Allocation | Dynamic allocation | High (core) |
| Bayesian Strategy Selection | Probabilistic selection | Medium |

### 13.24 Professional Quantitative Techniques (26 techniques)
| Technique | Description | Implementation Priority |
|-----------|-------------|------------------------|
| Cross-Sectional Equity Models | Stock selection models | Low (equities) |
| Market-Neutral Stat Arb | Dollar-neutral pairs | High (core) |
| Global Macro Models | Macro factor models | Medium |
| Cross-Asset Allocation | Multi-asset allocation | Medium |
| Multi-Factor Investing | Factor combinations | High (core) |
| Alternative Data Pipelines | Non-traditional data | Low |
| Reinforcement Learning Execution | RL for execution | Medium |
| Order Flow Prediction | Predict flow direction | High (Rust) |
| Market Impact Prediction | Predict slippage | High (Rust) |
| Optimal Execution | Minimize implementation shortfall | High (core) |
| Dynamic Hedging | Real-time hedge adjustment | High (core) |
| Volatility Forecasting | GARCH, ML vol models | High (core, Rust) |
| Liquidity Forecasting | Predict liquidity | Medium (Rust) |
| Regime Detection | HMM, ML regimes | High (core, ML) |
| Online Learning | Incremental model updates | High (ML) |
| Bayesian Optimization | Hyperparameter tuning | Medium |
| Ensemble Forecasting | Model averaging | High (ML) |
| Meta-Labeling | Label quality improvement | Medium |
| Feature Engineering Pipelines | Automated features | High (core, Rust) |
| Graph Neural Networks (GNNs) | Relational modeling | Low |
| Transformer-Based Forecasting | Attention forecasting | High (ML) |
| Explainable AI (XAI) | Model interpretability | Medium |
| Evolutionary Algorithms | Genetic optimization | Low |
| Genetic Algorithms | Evolutionary search | Low |
| Particle Swarm Optimization | Swarm optimization | Low |
| Simulated Annealing | Annealing optimization | Low |
| Bayesian Inference | Probabilistic inference | Medium |

---

## 14. Detailed TODO List

> Status legend: ✅ done · ⚠️ partial · 🔲 pending. Mirror of section 4 (Implementation Phases) keyed by file.
> Live view: `PROJECT_MEMORY/12_Feature_Status.md`, `13_Bug_Tracker.md`, `23_Repository_History.md`.

### Phase 1: Core Infrastructure
- [x] Create project directories structure
- [x] Implement EventBus (`core/bus.py`)
- [x] Implement Clock abstraction (`core/clock.py`)
- [x] Implement Portfolio management (`core/portfolio.py`)
- [x] Update `core/__init__.py` exports
- [x] Create data ingestion pipeline (`data/ingestion.py`)
- [x] Create data storage layer (`data/storage.py` — TimescaleDB + Parquet)
- [x] Create data cleaning/validation (`data/cleaning.py`)
- [x] Create structured logging (`utils/logging.py`)
- [x] Add Prometheus metrics (`monitoring/metrics.py`)
- [x] Create docker-compose.yml for local dev (TimescaleDB, Redis, Grafana, Loki, Alertmanager, Promtail)
- [x] Add `Dockerfile` (`python:3.14-slim`)
- [x] Add `.dockerignore`, `.gitignore`
- [x] Add `pyproject.toml` + `pytest.ini` + `Settings.from_yaml_safe` (configs/settings mismatch fixed 2026-07-29)
- [ ] Set up Rust workspace (`Cargo.toml` exists, `crates/cryptobot-core/Cargo.toml` manifest only)
- [ ] Implement core Rust types (`cryptobot-core`)
- [ ] Implement feature engine in Rust (`cryptobot-features`)

### Phase 2: Backtesting Engine
- [x] Event-driven backtester core (`backtest/engine.py`)
- [x] Fill simulator (`backtest/simulator.py`)
- [x] Performance metrics (`backtest/metrics.py`) — Sharpe, Sortino, MaxDD, win_rate, profit_factor
- [x] Realistic fills (`execution/venue/simulated.py`) with slippage + commission
- [x] OHLCV data manager + runner (`backtest/runner.py`) — synthetic data + end-to-end orchestration
- [x] Walk-forward validation with real math (`backtest/validation.py`)
- [x] Monte Carlo robustness testing (`backtest/validation.py`)
- [x] Deflated Sharpe ratio
- [x] Tearsheet generation (`backtest/reporting.py`)
- [x] Historical data replay from CSV / Parquet / TimescaleDB (`backtest/data.py`)

### Phase 3: Strategy Framework
- [x] Base strategy class with lifecycle hooks (`strategies/base.py`)
- [x] Signal generation interface (`List[OrderEvent]`)
- [x] Strategy registry (`StrategyRegistry`)
- [ ] Position management primitives (scaling, stops)
- [ ] Parameter optimization with Optuna (`cli/optimize.py`)

### Phase 4: Core Strategies
- [x] Strategy base + registry + placeholder mean-reversion
- [ ] Mean Reversion concrete (`strategies/mean_reversion.py`)
- [ ] Trend Following concrete (`strategies/trend_following.py`)
- [ ] Statistical Arbitrage concrete (`strategies/stat_arb.py`)
- [ ] Funding Arbitrage concrete (`strategies/funding_arb.py`)
- [ ] Market Making concrete (`strategies/market_making.py`)
- [ ] ML-driven strategy (`strategies/ml_strategy.py`)

### Phase 5: Risk Management
- [x] Risk engine with pre-trade checks (`risk/manager.py`)
- [x] Dynamic position sizing helpers (`risk/sizing.py` — fixed, vol-target, Kelly)
- [x] Risk limits (`risk/limits.py`)
- [x] Correlation helper (`risk/correlation.py`)
- [x] Kill switch (`risk/kill_switch.py`)
- [ ] Portfolio optimization (HRP, mean-CVaR)
- [ ] Replace `print`-based status with structlog

### Phase 6: ML Pipeline
- [ ] Feature engineering pipeline (`ml/features.py`) — directory missing
- [ ] Feature store with versioning
- [ ] Direction classifier (`ml/models/direction.py`)
- [ ] Volatility forecasting (`ml/models/volatility.py`)
- [ ] Regime detection (`ml/models/regime.py`)
- [ ] Ensemble stacking (`ml/models/ensemble.py`)
- [ ] Walk-forward training with purged CV (`ml/training.py`)
- [ ] Online inference (`ml/inference.py`)
- [ ] Auto-retrain on drift (`ml/auto_retrain.py`)

### Phase 7: Execution Engine
- [x] Order management (`execution/engine.py`) with `build_venue(mode)` factory, optional SOR
- [x] `Venue` interface + `SimulatedVenue` (slippage + commission) + `BinanceVenue` (ccxt async)
- [x] TWAP/VWAP/POV helpers (`execution/algorithms.py`)
- [x] SmartOrderRouter (`execution/router.py`) — price + latency rankers, fallback, split
- [x] AdverseSelectionGuard (`execution/adverse_selection.py`) — mid-move cancel, spread-widening cancel, toxicity-spike cancel
- [x] Latency monitoring (`monitoring/metrics.py`) — `record_venue_quote_latency`, `record_routing_decision`, `record_execution_latency`
- [x] Implementation Shortfall (Perée-Clark), Iceberg (display qty + randomization),
      liquidity-seek sweeps, POV (cap + randomized), arrival-price benchmark,
      `VWAPSchedule` with horizon-minute lookup, `slicer_for(name)` dispatcher

### Phase 8: Live Trading & Monitoring
- [x] `cryptobot-test` Compose service (profile `test`)
- [x] `cryptobot-paper` Compose profile
- [x] Grafana dashboards JSON (`docker/grafana/`, `monitoring/grafana/`)
- [x] Alerting channels (`monitoring/alerting.py`)
- [x] Health checks (`monitoring/health.py`)
- [x] `cryptobot` HTTP `/health` endpoint (`utils/health_server.py` ThreadingHTTPServer)
- [x] Real walk-forward / Monte Carlo in `backtest/validation.py`
- [x] Live trading profile wired (Binance adapter done; `EXECUTION_MODE=binance|testnet|live`)
- [x] Kubernetes manifests (`deploy/k8s/*.yaml`) — namespace, configmap, secret, pvc, deployment, service, hpa; kustomization overlay
- [x] Multi-arch Docker images (`scripts/build_multiarch.sh`, `.github/workflows/release.yml`)
- [x] GitHub Actions CI (`.github/workflows/ci.yml`) — lint + unit + compose-validate + multi-arch buildx

### Tests
- [x] 14 unit test files in `tests/unit/` covering event bus, retry, simulated execution, backtest fill flow, reporting, mean reversion + validation + reporting, smart order router, latency metrics, Binance venue, backtest runner, backtest data, config loading, basic foundation
- [ ] Property-based tests (hypothesis) for risk/math
- [ ] Integration tests (TimescaleDB / Redis / Prometheus)
- [x] CI/CD pipeline (GitHub Actions; cross-compile via QEMU + buildx matrix)
- [ ] Regression tests on backtest metrics
- [x] Multi-arch Docker images (x86_64, ARM64)

### Testing & Quality
- [ ] Unit tests for all core modules (>90% coverage)
- [ ] Integration tests for backtester
- [ ] Property-based tests for risk/math
- [ ] CI/CD pipeline with cross-compilation

---

*This document is the **architectural** source of truth for the project. Update it after every major milestone. For day-to-day knowledge (bugs, debt, decisions, recent changes), see `PROJECT_MEMORY/` which is the operational source of truth.*

---

## 15. Project Memory & Knowledge Management

### 15.1 Development Methodology

> **Context**: This section defines how the project should be understood, maintained, and extended. This is the **agent methodology** that must be followed in every session.

#### PHASE 1: COMPLETE REPOSITORY ANALYSIS
Before implementing features or fixing bugs:
1. Read **every** source file (never skip any file, even if it appears unimportant)
2. Read every configuration file
3. Read every build file
4. Read all documentation
5. Read all tests
6. Read CI/CD configuration
7. Read dependency manifests
8. Read all scripts
9. Read assets only if relevant
10. Build a complete mental model of the entire system

#### PHASE 2: BUILD PROJECT MEMORY
Create and maintain a `PROJECT_MEMORY/` directory with comprehensive documentation:

```
PROJECT_MEMORY/
00_Project_Overview.md
01_System_Architecture.md
02_Module_Index.md
03_Component_Map.md
04_Data_Flow.md
05_Control_Flow.md
06_API_Reference.md
07_Database_Model.md
08_Config_Reference.md
09_External_Dependencies.md
10_Build_System.md
11_Testing.md
12_Feature_Status.md
13_Bug_Tracker.md
14_Technical_Debt.md
15_Design_Patterns.md
16_Coding_Standards.md
17_Performance.md
18_Security.md
19_Open_Questions.md
20_Assumptions.md
21_Risk_Assessment.md
22_Improvement_Ideas.md
23_Repository_History.md
24_Agent_Log.md
```

**Each document must:**
- Remain concise (1-2 pages max per document)
- Be organized with clear headings
- Be continuously updated as understanding improves
- Preserve historical context when understanding changes
- Clearly distinguish between:
  - **Known with high confidence**
  - **Known with medium confidence**
  - **Known with low confidence**
  - **Unknown**
  - **Assumptions** (never present assumptions as facts)

#### PHASE 3: FOR EVERY FILE, UNDERSTAND
For each file in the repository, determine:
- **Purpose**: What problem does this file solve?
- **Responsibilities**: What is this module accountable for?
- **Public interfaces**: What is exported/accessible from outside?
- **Internal logic**: How does it actually work?
- **Dependencies**: What modules does it depend on?
- **Reverse dependencies**: What modules depend on this one?
- **Data structures**: What types and structures does it use?
- **Algorithms**: What key algorithms are implemented?
- **Error handling**: How are errors detected and handled?
- **Performance considerations**: What is the time/space complexity?
- **Security considerations**: What security properties must be maintained?
- **Thread safety**: Is it thread-safe? What synchronization is used?
- **Side effects**: What external state does it modify?
- **State management**: What state does it maintain?
- **Future extension points**: How can this be extended safely?
- **Possible bugs**: What are common failure modes?
- **Technical debt**: What corners were cut? What needs refactoring?
- **Code quality**: What is the current quality level?
- **Confidence level**: How certain are we of our understanding?

#### PHASE 4: BUILD SEMANTIC UNDERSTANDING
Infer and document:
- **Overall software architecture**: What is the big picture?
- **Design philosophy**: What principles guide design decisions?
- **Engineering principles**: What engineering practices are followed?
- **Developer intent**: What was the original vision?
- **Implicit assumptions**: What is assumed but not stated?
- **Hidden constraints**: What limitations exist that aren't documented?
- **Naming conventions**: How are things named and why?
- **Coding style**: What patterns dominate the codebase?
- **Architectural patterns**: What design patterns are used?
- **Communication between modules**: How do components talk?
- **Runtime behaviour**: What happens at runtime?
- **Startup sequence**: How does the system initialize?
- **Shutdown sequence**: How does the system terminate?
- **Failure modes**: How does the system fail?
- **Recovery mechanisms**: How does it recover from failures?

#### PHASE 5: BUILD KNOWLEDGE GRAPHS
Construct logical graphs for:
- **Module dependencies**: Which modules depend on which?
- **Function call hierarchy**: What is the call stack structure?
- **Class relationships**: Inheritance, composition, aggregation
- **Data flow**: How does data move through the system?
- **Control flow**: What is the execution flow?
- **Configuration relationships**: How does config affect behavior?
- **External services**: What external systems does it integrate with?
- **Build dependencies**: What is required to build/test?

**Identify:**
- Central modules (highly connected, critical to functionality)
- High-risk modules (complex, critical, poorly tested)
- Bottlenecks (slow operations, serialization points)
- Circular dependencies (should be avoided)
- Dead code (unused, possibly safe to remove)
- Unused APIs (exported but never called)
- Duplicate logic (should be consolidated)

#### PHASE 6: SELF-EVALUATION
Continuously record your state of understanding:
- **Known with high confidence**: Facts verified through code reading
- **Known with medium confidence**: Informed inferences based on patterns
- **Known with low confidence**: Speculative, needs verification
- **Unknown**: Things not yet understood or not documented
- **Assumptions**: Working hypotheses that may be wrong
- **Questions requiring further investigation**: Open questions

**Never present assumptions as facts.** Always label them as assumptions.

#### PHASE 7: CONTINUOUS MEMORY MAINTENANCE
Whenever code changes:
- **Update every affected memory document**
- **Remove outdated information**
- **Preserve historical context** (use versioning or timestamps)
- **Record why understanding changed** (document the learning)
- **Update confidence levels** based on new evidence

#### PHASE 8: BEFORE IMPLEMENTING FEATURES
Before making any modification to the codebase:
1. **Verify your understanding** by reading relevant files
2. **Identify affected modules** (forward and reverse dependencies)
3. **Predict side effects** (what else might break?)
4. **Estimate implementation complexity** (time, risk)
5. **Identify risks** (what can go wrong?)
6. **Update the plan** (add tasks, adjust priorities)
7. **Only then begin implementation**

### 15.2 Knowledge Base Structure

The `PROJECT_MEMORY/` directory should be structured as a **long-term knowledge base** that:

1. **Reduces rereading**: After initial analysis, future sessions can read memory docs instead of entire repo
2. **Preserves context**: When returning to project after months/years, memory docs provide immediate orientation
3. **Enables incremental understanding**: Each session builds on previous knowledge
4. **Documents evolution**: Shows how understanding changed over time
5. **Serves as documentation**: Memory docs become project documentation

### 15.3 Agent Role
You are a **persistent software engineering agent** with the following responsibilities:

1. **Continuously improve understanding**: Every session should deepen understanding of the system
2. **Continuously improve memory**: Every session should update and expand the knowledge base
3. **Maintain accuracy**: Never let memory become outdated or incorrect
4. **Question assumptions**: Always verify that assumptions are still valid
5. **Document uncertainty**: Be explicit about what is known vs unknown
6. **Preserve historical context**: When something changes, document why
7. **Think in systems**: Understand how components interact, not just individual pieces

### 15.4 Quality Gates for Knowledge
Before considering understanding "complete", verify:
- [ ] Can you explain the entire system architecture from memory?
- [ ] Can you trace data flow from input to output for a典型 use case?
- [ ] Can you identify all critical modules and their responsibilities?
- [ ] Can you explain the startup sequence and key initialization logic?
- [ ] Do you know which modules are most likely to contain bugs?
- [ ] Do you know which modules are most critical to correct functionality?
- [ ] Have you identified all external dependencies and their purposes?
- [ ] Have you mapped all configuration options and their effects?

### 15.5 Context Restoration
When returning to this project in future sessions, **always**:
1. Read `plan.md` to understand current phase and priorities
2. Read relevant `PROJECT_MEMORY/` files to refresh understanding
3. Check for any TODO items that need attention
4. Look at recent changes to understand current state
5. Identify any open questions that need investigation

> **Remember**: The goal is to act as a persistent agent, not a stateless assistant. Your memory (both the memory docs AND your understanding of this methodology) is your primary tool for long-term effectiveness.