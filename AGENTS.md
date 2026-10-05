# AGENTS.md — Trading Repository Guide

## ⚠️ READ THIS FIRST: the mission lives in `GOAL.md`

**`GOAL.md` is the binding constitution for this project.** It defines the capital
(₹21,00,000), the return target (3%/month net), the hard risk limits, the anti-fraud
rules, and the 7 go/no-go gates that must ALL pass before real capital is deployed.

**Read `GOAL.md` before writing any strategy code.** If code and `GOAL.md` disagree,
`GOAL.md` wins — fix the code. In particular:
- §3.3 risk limits are **hard-coded and not configurable upward**
- §6 anti-fraud rules are binding (no in-sample numbers as results, no cost reductions
  to rescue a result, no survivorship-bias concealment)
- §5 gates are **not waivable** to ship faster

## 🐍 Run policy: tests on host, app in Docker

| What | Where it runs | Why |
|------|---------------|-----|
| **Unit / integration tests (`pytest`)** | **Host venv** (`.venv/bin/python`) | Fast iteration; no rebuild per test cycle |
| **Research & analysis scripts (`research/*.py`)** | **Host venv**, or research container | Same speed reasoning; container for reproducibility |
| **The application** (`nsealgo` live/paper engine) | **Docker only** | Matches deployment; proves the image works |
| **Lint** | Host venv | Speed |

```bash
# TESTS + LINT -> host venv (never rebuild a container to test)
.venv/bin/python -m pytest tests/unit -q
.venv/bin/ruff check src tests

# APP -> Docker
docker compose -f docker-compose.nse.yml up -d --build
docker compose -f docker-compose.nse.yml logs -f nsealgo

# RESEARCH -> host by default; container for reproducibility
.venv/bin/python research/audit_data.py
docker compose -f docker-compose.research.yml run --rm research python research/audit_data.py
```

**Never edit a file inside a container.** Edit on the host, rebuild the image.

---

## Project Overview

This repo hosts **two trading systems** sharing one backbone:

1. **`src/cryptobot/`** — the crypto quantitative system (Python + Rust workspace),
   with backtesting, live trading, risk, monitoring, multi-arch Docker deploys.
2. **`src/nsealgo/`** — the **NSE NIFTY-50 equity system** (the active mission,
   see `GOAL.md`). Swing-horizon, daily-bar, cost-aware, walk-forward validated.

**Shared backbone reused by `nsealgo`:** `EventBus`, `Clock`, `Decimal` money
handling, Pydantic Settings config, Prometheus monitoring, health checks, Docker/CI.

**Key Stack:**
- Python 3.13+ (`src/cryptobot/`, `src/nsealgo/`)
- Rust workspace (`crates/`) — 7 crates, PyO3 0.29 bindings (crypto hot paths)
- NSE data: 50 NIFTY-50 symbols, ~24y daily OHLCV in `data/nse/`
- Broker: Zerodha KiteConnect
- Docker multi-arch (amd64/arm64) via buildx
- TimescaleDB + Redis (crypto); SQLite state (nsealgo)
- Prometheus/Grafana monitoring stack

---

## NSE System (`src/nsealgo`) — the active mission

### Hard constraints (from data reality, audited)
| Timeframe | History | Use |
|-----------|---------|-----|
| **1d** | ~6,000 bars, ~24y (2002→2026-10) | ✅ primary research substrate |
| 1h / 4h | ~1–2y | ⚠️ corroboration only |
| 5m/15m/30m | weeks–months | ⚠️ sanity only |
| **1m** | **~1,800 bars, ~30 days** | ❌ **unusable — intraday is BANNED** |

- **Daily bars only.** Holding period 5–60 days. Weekly/biweekly rebalance.
- **Survivorship bias is present** (today's NIFTY-50 backfilled) — disclose it in every report.
- Data ends **2026-10-01** (panel re-fetched 2026-10-06 via `tools/recover_nse_data.py`,
  verified 49/50 vs `research/_audit_1d.csv`) → staleness resolved, but the refresh is a
  one-off script: a Kite historical feed is still required before live.
- **Always quote an nsealgo result with its end date.** Moving the end date 27 sessions
  (2026-08-25 → 2026-10-01) moved walk-forward Sharpe 0.66 → 0.44 and the band C → D.
  Current authoritative result: **10.97% OOS, Sharpe 0.44, MaxDD −12.91%, Band D, four gates
  failing** — see `reports/VALIDATION_v1.md` §0.

### Rules that code must obey
1. **`Decimal` for all money. Never `float`.**
2. **No lookahead.** Event-driven engine + explicit `Clock`. No `datetime.now()` in logic.
3. **Walk-forward is the only accepted performance evidence.**
4. **Full Indian cost stack on every fill**: STT, exchange txn, SEBI, stamp duty,
   DP charges, brokerage, **18% GST**. Never skip.
5. **Live and paper share one code path** — only the broker adapter differs.
6. **Risk limits from `GOAL.md` §3.3 are hard-coded** in `nsealgo/risk/limits.py`.

### Commands
```bash
# Validate a strategy (the only result that counts)
.venv/bin/python -m nsealgo.cli validate --strategy momentum --walk-forward

# Paper trade (no capital)
docker compose -f docker-compose.nse.yml run --rm nsealgo paper --duration 1w

# Research
.venv/bin/python research/audit_data.py
.venv/bin/python research/sweep.py --factor momentum
```

---

## Essential Commands

### Development
```bash
# Install dependencies
make install          # production deps only
make install-test     # test + dev deps (includes numpy/pandas)

# Run tests  (HOST venv)
.venv/bin/python -m pytest tests -q
.venv/bin/python -m pytest tests/unit/test_nsealgo_costs.py -v  # single file

# Lint  (HOST venv)
make lint             # ruff check + pyflakes
.venv/bin/ruff check --fix src tests

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