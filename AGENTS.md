# AGENTS.md — Cryptobot Repository Guide

## Project Overview
Cryptobot is an elite quantitative trading system written in Python 3.13+ with a Rust workspace (`cryptobot-core`). It's a production-grade trading bot with backtesting, live trading, risk management, monitoring, and multi-arch Docker deployments.

**Key Stack:**
- Python 3.13+ (src/cryptobot/)
- Rust workspace (crates/cryptobot-core) — ready for PyO3 bindings
- Docker multi-arch (amd64/arm64) via buildx
- TimescaleDB + Redis for state
- Prometheus/Grafana monitoring stack

---

## Essential Commands

### Development
```bash
# Install dependencies
make install          # production deps only
make install-test     # test + dev deps (includes numpy/pandas)

# Run tests
make test             # pytest -q (all tests)
pytest tests/unit/test_core_foundation.py -v  # single test file

# Lint
make lint             # ruff check + pyflakes
ruff check --fix src tests  # auto-fix

# Docker
make compose-test     # run test container
make compose-shell    # shell into test container
```

### Docker
```bash
# Build test image
docker build --target test --build-arg REQUIREMENTS=requirements/test.txt -t cryptobot:test .

# Build production
docker build --target production -t ghcr.io/shobhit727/trade:latest .

# Multi-arch (requires buildx)
docker buildx build --platform linux/amd64,linux/arm64 --target production --push -t ghcr.io/shobhit727/trade:latest .
```

### CI Pipeline Order (must run in order)
```bash
# Required order per CI
1. lint          # ruff + pyflakes
2. cargo-lint    # cargo fmt --check + cargo clippy -D warnings
3. cargo-test    # cargo test --workspace
4. unit          # pytest (depends on 1-3)
5. docker-test   # builds test image + runs pytest inside container
6. docker-build  # multi-arch buildx (push only on push)
```

---

## Architecture Notes (Non-Obvious)

### Package Structure
```
src/cryptobot/          # Main Python package (src-layout)
├── backtest/           # Event-driven backtesting engine
├── cli/                # CLI entrypoint (cryptobot.cli.main:main)
├── core/               # Core primitives (events, bus, clock, portfolio, state)
├── data/               # Ingestion, storage (TimescaleDB, Parquet), cleaning
├── execution/          # Engine, router, venues (Binance, simulated), algorithms
├── market_data/        # WebSocket managers
├── ml/                 # Features, models (direction, volatility, regime, ensemble)
├── monitoring/         # Metrics, alerting, health checks, dashboards
├── risk/               # Limits, kill switch, correlation, sizing
├── strategies/         # Base + implementations (trend, MM, stat arb, funding, ML)
└── utils/              # Logging, decorators, types, health server

crates/cryptobot-core/  # Rust workspace (single member, lib.rs stub)
```

### Key Conventions
- **src-layout**: `pip install -e .` installs from `src/cryptobot`
- **Async-first**: All I/O is async (asyncio, aiohttp, redis.asyncio)
- **Config**: Pydantic Settings + YAML (`configs/base.yaml`) with env overrides
- **Events**: Central `EventBus` for decoupled component communication
- **Time abstraction**: `Clock` protocol (Realtime/Simulated/Accelerated) — critical for backtest determinism
- **Decimal for money**: All financial values use `Decimal`, never `float`

### Critical Files to Know
| File | Purpose |
|------|---------|
| `configs/base.yaml` | Full config schema (env-overridable) |
| `src/cryptobot/config.py` | Pydantic Settings loading |
| `src/cryptobot/core/events.py` | All event types + payloads |
| `src/cryptobot/core/portfolio.py` | Portfolio state, kill-switch logic |
| `src/cryptobot/execution/engine.py` | Order submission flow |
| `src/cryptobot/backtest/engine.py` | Backtest event loop |
| `src/cryptobot/monitoring/health.py` | Health check framework |

---

## Testing Quirks

### Running Tests
```bash
# All tests (with coverage, timeout=60s)
pytest -q --tb=short --cov=cryptobot --cov-report=term-missing --timeout=60

# Single test
pytest tests/unit/test_core_foundation.py::test_event_bus_subscription_and_history -v

# Skip slow/integration
pytest -m "not integration" -q
```

### Test Infrastructure
- **Async**: All tests use `pytest-asyncio` (`@pytest.mark.asyncio`)
- **Timeout**: Default 60s per test (CI enforces)
- **Fixtures**: `tests/conftest.py` — check for `monkeypatch`, `asyncio` fixtures
- **Test DB**: Uses in-memory SQLite; `_sqlite3` missing = graceful fallback (warning logged)

### Common Test Failures
| Symptom | Cause |
|---------|-------|
| `ModuleNotFoundError: cryptobot` | Forgot `pip install -e .` |
| `asyncio.run()` in async test | Use `await` directly, not `asyncio.run()` |
| `sqlite3` missing | Install `sqlite3` package or run in Docker |
| `ccxt` not installed | `pip install ccxt` for Binance venue tests |

---

## Docker Gotchas

### Build Targets
| Target | Purpose |
|---------|---------|
| `base` | Shared base with deps |
| `test` | Runs `pytest -q tests` (CI) |
| `production` | Runs bot server with healthcheck |

### Multi-Arch Tags
```bash
# Tags use sanitized platform names (no slashes)
linux/amd64  ->  linux-amd64
linux/arm64  ->  linux-arm64

# Tags pushed:
ghcr.io/shobhit727/trade:<sha>-linux-amd64
ghcr.io/shobhit727/trade:<sha>-linux-arm64
ghcr.io/shobhit727/trade:latest-linux-amd64
ghcr.io/shobhit727/trade:latest-linux-arm64
```

### Manifest Creation
Runs in separate `docker-manifest` job AFTER `docker-build` completes (both platforms pushed). Creates:
- `ghcr.io/...:<sha>` (multi-arch)
- `ghcr.io/...:latest` (multi-arch)

---

## CI/CD Specifics

### Environment Variables
```yaml
env:
  PYTHON_TAG: "3.14-slim"    # Docker base image
  CI_PYTHON: "3.13"          # Python version for CI (runners)
  REGISTRY_IMAGE: ghcr.io/${{ github.repository }}
```

### Python Version
- **CI**: 3.13 (runners)
- **Docker**: 3.14-slim (bleeding edge for prod)
- **Local**: 3.13+ recommended

### Rust Toolchain
- Uses `dtolnay/rust-toolchain@stable` (auto-installs)
- Workspace: `crates/cryptobot-core` only
- Targets: `cargo fmt --check`, `clippy -D warnings`, `test`

---

## Release Process

```bash
# Tag a version
git tag v0.1.0
git push origin v0.1.0

# Triggers release-multiarch workflow:
# 1. Validates tag format (refs/tags/v*)
# 2. Builds multi-arch production image
# 2. Pushes to GHCR with tags: latest, vX.Y.Z, vX.Y.Z-multiarch
# 3. Generates SBOM + provenance
```

### Version Sources
- **Python**: `pyproject.toml` `[project].version`
- **Rust**: `Cargo.toml` `[workspace.package].version`
- **Docker**: Git tag (stripped `v` prefix)

---

## Common Pitfalls

| Issue | Fix |
|-------|-----|
| `ruff` import sorting | Run `ruff check --fix src tests` |
| `datetime.utcnow()` deprecation | Use `datetime.now(timezone.utc)` |
| `np.math.erf` | Use `math.erf` (numpy 2.x) |
| `np.sum(generator)` | Use `np.fromiter(gen, dtype=float, count=n)` |
| `asyncio.run()` in async test | Remove `asyncio.run()`, use `await` |
| `docker buildx imagetools` not found | Ensure `docker/setup-buildx-action@v3` runs first |

---

## Useful References

- **Plan/Architecture**: `plan.md`, `CODEBASE.md`, `PROJECT_MEMORY/`
- **Runbook**: `docs/RUNBOOK.md` (ops guide)
- **Config Reference**: `PROJECT_MEMORY/08_Config_Reference.md`
- **Bug Tracker**: `PROJECT_MEMORY/13_Bug_Tracker.md`
- **Feature Status**: `PROJECT_MEMORY/12_Feature_Status.md`

---

## Quick Reference: Most Common Commands

```bash
# Daily dev loop
make install-test && make lint && make test

# Full CI locally (needs docker)
make lint && make test && docker build --target test -t cryptobot:test . && docker run --rm cryptobot:test

# Release
git tag v0.1.0 && git push origin v0.1.0

# Debug in container
make compose-shell
```

---

*Generated from repo analysis. Update when conventions change.*