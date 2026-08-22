# AGENTS.md — Cryptobot Repository Guide

## Project Overview
Cryptobot is an elite quantitative trading system written in Python 3.14+ with a Rust workspace (`cryptobot-core`). It's a production-grade trading bot with backtesting, live trading, risk management, monitoring, and multi-arch Docker deployments.

**Key Stack:**
- Python 3.14+ (src/cryptobot/)
- Rust workspace (crates/) — 7 crates (core, features, risk, stats, orderbook, backtest, py) with PyO3 0.29 bindings, executable locally via `rustup`
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
1. lint          # ruff (pinned) — Makefile target runs ruff only; CI adds pyflakes as a separate step
2. cargo-lint    # cargo fmt --check + cargo clippy -D warnings
3. cargo-test    # cargo test --workspace
4. unit          # pytest with coverage gate (--cov-fail-under=70), matrix on 3.13+3.14 (depends on lint)
5. docker-test   # cached image build + pytest inside container + trivy scan (needs: lint + changes path-filter)
6. docker-build  # multi-arch buildx (push only on push); gated by changes path-filter
```

> **Reality check (2026-08-22 audit)**: `docker-test` depends only on `[lint, changes]` and runs in
> parallel with cargo/unit — it does NOT wait for them. That's how the broken production CMD (#22)
> shipped green: the production target is built+scanned but never *run* by CI.

### Parallel / Independent CI Jobs
- `changes` (path filter: core/docker) — a *skip* gate, not a true dependency stage
- `security-review` (gitleaks secrets scan) — independent
- `security-audit` (pip-audit on prod+test requirements) — independent
- `pyo3` (maturin build + import smoke test of `cryptobot_rs`) — runs when `core` paths change
- `compose-validate` (docker compose config) — after lint
- `docker-manifest` (multi-arch manifest) — after `docker-build`, push only

### Docker Image Scans
- `docker-test` + `docker-build` + `release.yml` all run Trivy (CRITICAL/HIGH, ignore-unfixed, fail on findings)
- `release.yml` also emits SBOM + provenance on the multi-arch push

### Coverage Gate
- `unit` enforces `--cov-fail-under=70` and uploads `coverage.xml` (artifact + Codecov when `CODECOV_TOKEN` set)

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

crates/cryptobot-*/      # Rust workspace — 7 crates (core, features, risk, stats, orderbook, backtest, py)
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
  PYTHON_TAG: "3.14-slim"    # Docker base image (threaded into builds as --build-arg)
  CI_PYTHON: "3.13"          # Python version for CI runners
  REGISTRY_IMAGE: ghcr.io/${{ github.repository }}
```

> **Reality check (2026-08-22 audit)**: only `ci.yml` actually passes `PYTHON_TAG=3.14-slim`;
> `release.yml`, `scripts/build_multiarch.sh`, and compose omit it, so tagged release images build
> on the Dockerfile default (`3.13-slim`). See issue #38.

### Python Version
- **CI runners**: 3.13 + 3.14 (unit tests run a matrix on both)
- **Docker base image**: 3.14-slim in CI; Dockerfile *default* ARG is still `3.13-slim` (#38)
- **Local**: 3.14 works (`pyproject requires-python >=3.13`); override Makefile if no `python3.13`:
  `make test PY=python3`

### Rust Toolchain
- Uses `dtolnay/rust-toolchain@stable` (auto-installs) + `Swatinem/rust-cache@v2` (caches target dir)
- Workspace: 7 crates in `crates/` (core, features, risk, stats, orderbook, backtest, py); fully buildable locally via `rustup`
- Targets: `cargo fmt --all -- --check`, `cargo clippy --workspace --all-targets -- -D warnings`, `cargo test --workspace`
- PyO3: `0.29` for Rust 1.97+ compatibility
- All Rust tests pass
- ⚠️ `.cargo/config.toml` must NOT set `-C target-cpu=native` — it breaks cached builds across heterogeneous runner CPUs (proc-macro `.so` SIGILL). For local builds opt in via `CARGO_RUSTFLAGS="-C target-cpu=native"`.

### CI job details (ci.yml)
- `concurrency: ci-..., cancel-in-progress: true` keyed per workflow+branch — rapid pushes cancel superseded runs
- Every job has `timeout-minutes` (15–60) to bound cost
- `permissions: contents: read` at workflow level; `docker-build`/`docker-manifest` donate `packages: write`
- `lint` dep: pin ruff==0.16.1 + pyflakes==3.4.0; `checkout@v6`, `setup-python@v5`
- `unit`: coverage gate `--cov-fail-under=70` + `coverage.xml` artifact (+ Codecov when `CODECOV_TOKEN` set)
- `pyo3`: `maturin==1.9.6` build + import smoke test of `cryptobot_rs` (gated by `core` path filter)
- `security-review` (gitleaks) + `security-audit` (pip-audit) run in parallel, no deps
- `docker-test` + `docker-build` run Trivy (CRITICAL/HIGH, ignore-unfixed, fail on findings)
- Docker build uses `docker/build-push-action@v6` with GHA cache (`cache-from/to: type=gha`)
- `docker-build` matrix: **PRs build amd64 only; pushes build amd64 + arm64** (dynamic `fromJSON` matrix); both docker jobs gated by `changes` path filter
- Build args threaded through: `PYTHON_TAG`, `REQUIREMENTS`, `GIT_SHA`, `BUILD_DATE`

---

## Release Process

```bash
# Tag a version
git tag v0.1.0
git push origin v0.1.0

# Triggers release-multiarch workflow:
# 1. Validates tag format (refs/tags/v*)
# 2. Builds multi-arch production image (amd64 + arm64 in one buildx push)
# 3. Pushes to GHCR with tags: latest, vX.Y.Z, vX.Y.Z-multiarch
# 4. Attaches SBOM + provenance to the same push step
```

### Version Sources
- **Python**: `pyproject.toml` `[project].version` (0.2.0)
- **Rust**: `Cargo.toml` `[workspace.package].version` (0.2.0)
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
- **Bug Tracker**: `PROJECT_MEMORY/13_Bug_Tracker.md` (indexed against GitHub issues #20–#53, filed 2026-08-22 audit)
- **Feature Status**: `PROJECT_MEMORY/12_Feature_Status.md`

> **2026-08-22 audit**: 34 verified bugs filed as #20–#53 (9 critical, 16 high). Headline caveats
> until fixed: production Docker image cannot start (#22), backtest Sharpe/drawdown unreliable
> (#20/#32/#39/#40), catalog strategies effectively long-only (#25), ML training labels leak
> features (#21), optimizer layer non-functional (#27). Check the tracker before trusting any
> module marked ✅ elsewhere.

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

# Rust workspace
make cargo-lint && make cargo-test && make cargo-build

# Backtest: per-trade output
python -m cryptobot.cli.main backtest --strategy trend_following --bars 5000000 --show-trades

# Backtest: parallel algorithm sweep (multi-core)
python -m cryptobot.cli.main backtest --algorithms jobs.json --workers 8 --json
```

---

*Generated from repo analysis. Update when conventions change.*