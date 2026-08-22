# Cryptobot

Elite Quantitative Trading System — Python + Rust

**Latest Release**: v0.1.0 (multi-arch Docker images on GHCR) · package version 0.2.0

## Quick Start

```bash
# Prereqs: Docker 24+, Docker Compose v2
git clone git@github.com:shobhit727/trade.git cryptobot
cd cryptobot

# Run test suite (validates build + logic)
docker compose --profile test run --rm --build cryptobot-test

# Start paper trading + observability stack
docker compose up -d cryptobot-paper

# Health check
curl http://localhost:8080/health

# View logs
docker compose logs -f cryptobot-paper
```

## Architecture

| Layer | Tech |
|-------|------|
| Core  | Python 3.14 (async), Rust workspace (7 crates: core, features, risk, stats, orderbook, backtest, py) |
| Exchange | Binance (REST + WebSocket) |
| Risk  | Real-time position/portfolio limits |
| Strategies | Trend following, market making, stat arb |
| Backtest | Event-driven, synthetic or CSV data |
| Observability | Prometheus, Grafana, Loki, Alertmanager |
| Storage | TimescaleDB, Redis, Parquet |

## Profiles (Docker Compose)

```bash
docker compose --profile <name> up -d
```

| Profile | Services | Purpose |
|---------|----------|---------|
| (default) | full stack | Paper trading + monitoring |
| `test` | test runner | Unit/integration tests |
| `backtest` | backtest engine | Historical simulation |
| `paper` | paper trading | Debug-level paper trading |

## Configuration

Settings in `configs/base.yaml`. Override via env:

```bash
# Risk
RISK_MAX_DAILY_LOSS_PCT=0.02 \
RISK_KILL_SWITCH_DAILY_LOSS_PCT=0.05

# Live trading (requires Binance keys)
EXECUTION_MODE=binance \
BINANCE_API_KEY=$KEY \
BINANCE_API_SECRET=$SECRET
```

Prefixes: `APP_`, `RISK_`, `EXECUTION_`, `BINANCE_`, `MARKET_DATA_`, `MONITORING_`, `DB_`, `ML_`, `BACKTEST_`.

## Testing

```bash
# Local (needs pyproject.toml deps)
pip install -e . -r requirements/test.txt
pytest -q

# In Docker (CI-like)
docker compose --profile test run --rm --build cryptobot-test
```

## CI Pipeline (`.github/workflows/ci.yml`)

| Job | Runs |
|-----|------|
| `lint` | ruff (pinned) |
| `unit` | pytest + coverage gate 70% (matrix: Python 3.13 + 3.14) |
| `cargo-lint` | cargo fmt + clippy `-D warnings` |
| `cargo-test` | cargo test --workspace |
| `docker-test` | build test image + run tests inside + trivy scan |
| `docker-build` | buildx (amd64 on PRs; amd64+arm64 on push) |
| `compose-validate` | compose config validation |

Independent jobs: `security-review` (gitleaks), `security-audit` (pip-audit), `pyo3` (maturin import smoke test, on core changes).

> ⚠️ CI never *runs* the production image target (only builds/scans it) — a known gap; see #22.

**Release** (`.github/workflows/release.yml`): Tag-driven `v*` → multi-arch build + SBOM + provenance + GHCR push (`latest`, `vX.Y.Z`, `vX.Y.Z-multiarch`). Note: release images currently build on the Dockerfile default Python 3.13-slim (#38).

## Project Structure

```
src/cryptobot/
├── backtest/      # Engine, runner, metrics, reporting
├── cli/           # CLI entrypoint (main.py)
├── core/          # Events, bus, clock, portfolio, state
├── data/          # Ingestion, cleaning, storage (Timescale/Parquet)
├── execution/     # Router, algorithms, venues (Binance/Simulated)
├── market_data/   # WebSocket manager, Binance client
├── monitoring/    # Metrics, alerting, health, dashboard
├── risk/          # Correlation, position limits, kill switch
├── strategies/    # Base, trend, market_making, stat_arb
└── utils/         # Logging, decorators, types

crates/                        # Rust workspace (root Cargo.toml): core, features,
│                              # risk, stats, orderbook, backtest, py (PyO3 bindings)
```

## Documentation

| File | Description |
|------|-------------|
| `docs/RUNBOOK.md` | Operations guide (compose, profiles, troubleshooting) |
| `plan.md` | Master plan with phases & status |
| `PROJECT_MEMORY/` | Architecture, configs, bugs, features, API refs |
| `deploy/k8s/` | Kubernetes manifests |

## Development

```bash
# Install dev deps
pip install -e . -r requirements/test.txt

# Lint
ruff check src tests
pyflakes src tests

# Format
ruff format src tests

# Type check (if mypy added)
mypy src
```

## Known Issues

Tracked on GitHub (2026-08-22 audit, issues #20–#53). Headline items:

- **Production Docker image cannot start** — CMD duplicates `-m` under ENTRYPOINT (#22)
- **Backtest Sharpe/drawdown unreliable** — wall-clock equity stamps (#20), no per-bar mark-to-market (#32), Sortino formula (#39/#40)
- **Catalog strategies are effectively long-only** — flip signals close instead of reversing (#25)
- **ML training labels leak features** — `future_returns` is backward-looking (#21); optimizer layer non-functional (#27)
- In-memory SQLite fallback when `_sqlite3` missing (`B024`)
- Prometheus metrics optional dependency handled via lazy imports (`B051`)

Full index: [`PROJECT_MEMORY/13_Bug_Tracker.md`](PROJECT_MEMORY/13_Bug_Tracker.md)

## License

MIT# CI trigger
