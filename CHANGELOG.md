# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-08-31

### Added
- **New configuration sections** in `configs/base.yaml` and `src/cryptobot/config.py`:
  - `ExternalServicesSettings`: All external API URLs (Kite, Yahoo Finance, Binance prod/futures, Telegram, PagerDuty, WhatsApp)
  - `TimeoutSettings`: All HTTP timeouts (default=20s, long=30s, short=10s, strategy=0.5s, stop=30s, SMTP=30s)
  - `ServerSettings`: Bind host/ports (127.0.0.1:8080, NSE basket=8084, NSE powerhour=8085)
- **WhatsApp alerting** support via Meta Business Cloud API
- **Dashboard** at `/dashboard` with:
  - Equity card (equity, P&L, peak equity, max drawdown)
  - Price chart with BUY/SELL markers
  - Equity curve sparkline
  - Trading stats (bars, orders, fills, rejects, positions)
  - Paper gate progress bar with dynamic color
  - Global fund balance + frozen state
  - Circuit breaker status
  - India VDA tax breakdown
  - Live trade tape (auto-refresh 5s)
  - Strategy sweep with backtest runner & trade drill-down
- **Health server** (`/health`, `/metrics`, `/dashboard`) served by stdlib ThreadingHTTPServer
- **State reconciliation** in `BasketState.from_dict()` - restores missing tax lots from trade history on load

### Fixed
- **Dockerfile** production CMD no longer duplicates `-m` under ENTRYPOINT (issue #22)
- **docker-compose.yml** all services use correct command format for new ENTRYPOINT (issue #23)
- **Equity curve** now uses simulated clock time instead of wall-clock (issue #20)
- **ML labels** now use forward returns instead of backward (identity leakage) (issue #21)
- **ERC risk_parity_weights** fixed Spinu fixed-point iteration (was w∝w²) (issue #24)
- **TransactionCostModel** slippage returned in quote currency, bounds scale consistently (issue #26)
- **WalkForwardOptimizer** search spaces match actual config fields (issue #27)
- **k8s deployment** fixed command format, removed duplicate Service/HPA (issue #28)
- **Funding settlement** now settles on boundary crossing (6h/12h grids) (issue #30)
- **funding_sim lookahead bias** fixed with `bisect_left - 1` (issue #31)
- **run_bars** now marks positions to market every bar (issue #32)
- **backtest_mode** only disables time-based checks, structural limits apply in both modes (issue #33)
- **Data freshness check** raises exception when no ticker data (issue #34)
- **RiskEngineHealthChecker** surfaces kill-switch as UNHEALTHY (issue #35)
- **RegimeDetector.predict** uses fitted model for new samples (issue #36)
- **asyncpg/pyarrow** added to requirements/prod.txt (issue #37)
- **release.yml** includes PYTHON_TAG=3.14-slim (issue #38)
- **Sortino** uses full-sample downside deviation in Python (issue #39)
- **Rust Sortino** fixed formula and max_drawdown (issue #40)
- **Rust NaN checks** all use `is_finite()` fail-closed (issue #41)
- **Rust dead code** removed from backtest crate (issue #42)
- **BinanceVenue** idempotency keys + only retry `NetworkError` (issue #43)
- **NSE basket ledger corruption** on restart fixed with state reconciliation (new)

### Changed
- **Dockerfile** production ENTRYPOINT now includes module path (`python -m cryptobot.cli.main`)
- **docker-compose.yml** all services use simplified command format
- **All external URLs/timeouts/ports** externalized to config system
- **WhatsApp/email/alerting** configs moved to settings-based system
- **Health server** dashboard now renders polished HTML with auto-refresh
- **Sortino calculation** uses full-sample downside deviation (was losses-only std)

### Security
- Removed all hardcoded URLs, timeouts, and ports from source code
- All secrets now properly loaded via env vars through Pydantic Settings

## [0.2.0] - 2026-08-22

### Added
- Initial production-ready release
- Docker multi-arch builds (amd64/arm64)
- CI/CD pipeline with lint, test, docker build, security scans
- Paper trading gate with 60-day validation
- India VDA tax engine
- Circuit breaker and risk management

### Fixed
- 51 bugs from 2026-08-22 audit (issues #20-#53)

## [0.1.0] - 2026-07-31

### Added
- Initial prototype
- Backtest engine with synthetic data
- Basic strategies (mean_reversion, trend_following, funding_arbitrage, stat_arb)
- Simulated venue for paper trading