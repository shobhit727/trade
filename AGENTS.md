# Repository Guidelines

**⚠️ READ THIS FIRST: the mission lives in `GOAL.md`.**

**`GOAL.md` is the binding constitution for this project.** It defines the capital
(₹21,00,000), the return target (3%/month net), the hard risk limits, the anti-fraud
rules, and the 7 go/no-go gates that must ALL pass before real capital is deployed.

**Read `GOAL.md` before writing any strategy code.** If code and `GOAL.md` disagree,
`GOAL.md` wins — fix the code. In particular:
- §3.3 risk limits are **hard-coded and not configurable upward**
- §6 anti-fraud rules are binding (no in-sample numbers as results, no cost reductions
  to rescue a result, no survivorship-bias concealment)
- §5 gates are **not waivable** to ship faster

---

## Project Overview

Two trading systems share one backbone in this repo:

1. **`src/cryptobot/`** — async Python crypto engine + 7-crate Rust workspace
   (`cryptobot-core/-backtest/-features/-risk/-stats/-orderbook/-py`), ~90-strategy catalog,
   event-bus architecture. PyO3 0.29/maturin extension `cryptobot_rs` is CI-built and
   import-smoke-tested only — **not** imported by `src/` or `tools/` (known bugs #24 ERC,
   #40 Sortino/drawdown, #41 NaN limits; dead `-backtest` crate modules #42).
2. **`src/nsealgo/`** — sync vectorized NSE NIFTY-50 daily-bar engine, the active
   mission (`GOAL.md`). Single paper/live code path.

**Shared backbone**: `EventBus`, `Clock` protocol, `Decimal` money, Pydantic Settings,
Prometheus monitoring, health checks, Docker/CI. Broker: Zerodha KiteConnect (nsealgo);
Binance WS (crypto). Stack: Python ≥3.13, Rust 1.75+, TimescaleDB + Redis (crypto) /
SQLite (nsealgo), Prometheus/Grafana.

---

## Architecture & Data Flow

### cryptobot (crypto, async event-driven)

```
Binance WS → LiveTrader → strategy.feed (per closed bar) → OrderEvent
  → ExecutionEngine (risk check → venue) → EventBus → portfolio / health / tax / fund / breaker / gate  (state under state/)
```

- `core/events.py` — `EventType` enum, `OrderEvent`/`KlineEvent`/`PnLEvent`: the shared
  event vocabulary.
- `core/bus.py` — `EventBus` async pub/sub singleton; Redis mode raises `NotImplementedError`.
- `core/clock.py` — `Realtime`/`Simulated`/`Accelerated` + `ClockFactory`.
  **No `datetime.now()` in engines** — always inject the Clock.
- `core/portfolio.py` — `PortfolioManager` for BACKTEST/PAPER/LIVE; `core/{breaker,gate,tax,fund,state}.py`
  — CircuitBreaker (JSON state), 60-day paper gate, Schedule VDA TaxEngine, GlobalFundLedger, state_manager.
- `backtest/engine.py` — `run()` event-stream + `run_bars()` fast path, funding settlement,
  bankruptcy floor. `execution/engine.py` — `submit_order`: risk check → venue →
  `ORDER_FILLED`/`REJECTED`; `build_venue` maps mode; SmartOrderRouter unwired.
- `strategies/registry.py` + `strategies/catalog/*` — ~90 strategies auto-discovered.
- `live/trader.py` — LiveTrader; `live/nse_basket.py`, `live/nse_powerhour.py` are
  standalone scheduled NSE processes.
- `cli/main.py` subcommands: `backtest, mm, ml, serve, bot, validate, breaker-reset, tax, paper,
  paper-funder, carry`; **live refused** via `PaperGateTracker.allows_live()`.

### nsealgo (NSE, sync vectorized)

```
validate: load_universe → 18-cell grid (n_positions × lookback × threshold)
  → walk_forward (6 train / 2 test years) → OOS metrics
live cycle: kill-switch → target_weights → risk-check every order → CostModel fills
```

- `cli.py` — sole entrypoint: `audit, costs, limits, backtest, validate, paper, flatten`.
- `data/loader.py` — **C1–C10 cleaning**; `_apply_c10` rescales unadjusted bonus/split
  events; raises `DataIntegrityError`.
- `factors/core.py` + `regime.py` — `momentum_12_1`, `trend_strength_200d`,
  `low_volatility`, negative controls; `build_composite_score` (median 0.5 fill for
  missing factor values → ties are common by construction).
- `backtest/engine.py` — vectorized monthly-rebalance long-only; no-lookahead
  t scores → t+1 returns; **blake2b tie-break**; `TRADING_DAYS=244`; provenance SHAs.
- `walkforward.py` — 6 train / 2 test year folds.
- `live/engine.py` + `execution/{broker,paper,kite}.py` — **Broker Protocol**:
  `PaperBroker` vs `KiteBroker` behind one code path; only the adapter differs.
- `risk/limits.py` — frozen `LIMITS` verified at import (from `GOAL.md` §3.3).

---

## Key Directories

```
src/cryptobot/         # crypto engine (src-layout); backtest/ cli/ core/ data/ execution/
                       # market_data/ ml/ monitoring/ risk/ strategies/ live/ utils/
src/nsealgo/           # NSE engine: cli.py, data/ factors/ backtest/ walkforward.py live/ execution/ risk/
crates/cryptobot-*/    # Rust workspace, 7 crates (edition 2021, rust-version 1.75, lto=thin, panic=abort)
tests/                 # unit/ (~150+ files), strategies/ (test_catalog_<strategy>.py per strategy),
                       # integration/ (only test_external_services.py — self-skips via socket probes)
research/              # ~35 self-contained research/agent_<name>/ dirs; sweep/, optimize/
tools/                 # 32 scripts: NSE data, Kite login, crypto data pulls, ops, codegen
scripts/               # 23 bash scripts, all set -euo pipefail with "# Usage:" header
data/                  # data/nse/<symbol>_<tf>.csv (ts,open,high,low,close,vol; ts=epoch ms);
                       # data/nse_membership/ (PIT membership 2008→2026, 104 symbols)
configs/base.yaml      # full config schema; secrets via ${ENV_VAR}
state/ + state-nse/    # runtime state (gitignored)
docs/, reports/, PROJECT_MEMORY/, doc/
```

**Data reality** (`data/nse/`): 50 symbols × {1d,1h,30m,15m,5m}; only **1d is the
validated substrate** (5,997 bars, 2002→2026-10). 1h from 2024-11-18; 5m/15m from
2026-08-18→2026-10-06. 1m is unusable — **intraday is BANNED** (GOAL.md).
Survivorship bias present (today's NIFTY-50 backfilled) — disclose in every report.

---

## Development Commands

```bash
# Install (PY ?= python3.13; override: make test PY=python3)
make install           # production deps only
make install-test      # test deps (pytest stack)

# Tests (HOST venv)
.venv/bin/python -m pytest tests/unit -q
.venv/bin/python -m pytest tests/unit/test_core_foundation.py::test_event_bus_subscription_and_history -v
pytest -m "not integration" -q
make test

# Lint (HOST venv)
make lint              # ruff; CI adds pyflakes separately (ruff==0.16.1, pyflakes==3.4.0)
.venv/bin/ruff check --fix src tests

# Rust (separate from Python CI)
make cargo-lint        # cargo fmt --check + clippy -D warnings
make cargo-test
make cargo-build       # --release

# Docker
make compose-test / make compose-shell
docker build --target test --build-arg REQUIREMENTS=requirements/test.txt -t cryptobot:test .
docker build --target production -t ghcr.io/shobhit727/trade:latest .
docker buildx build --platform linux/amd64,linux/arm64 --target production --push -t ghcr.io/shobhit727/trade:latest .

# Crypto CLI
.venv/bin/python -m cryptobot.cli.main backtest --strategy trend_following --bars 5000000 --show-trades
.venv/bin/python -m cryptobot.cli.main backtest --algorithms jobs.json --workers 8 --json

# NSE validate (the only result that counts) + paper
.venv/bin/python -m nsealgo.cli validate --walk-forward
docker compose -f docker-compose.nse.yml run --rm nsealgo paper --cycles 5

# Research (conventions)
PYTHONPATH=src:. .venv/bin/python -m research.sweep.run --wave N --agent I --agents 40 --out tem/waves/waveN
PYTHONPATH=src .venv/bin/python -m research.optimize.run --smoke
```

**Research entrypoints**: `research/AGENT_BRIEF.md` is mandatory reading —
`sys.path.insert(0, 'src')` + `load_universe('data/nse')`. `research/optimize/`:
84 strategies × 48 stocks, TRAIN-only selection, TEST once, ₹21L/stock, 21.92 bps
round-trip, FIFO CGT (STCG 20% / LTCG 12.5%), `out/test_results.jsonl --resume`.
Loader excludes `adanient`, `jiofin`, `tmpv`.

---

## Code Conventions & Common Patterns

1. **`Decimal` for all money. Never `float`.**
2. **No lookahead.** Event-driven engine + explicit `Clock`. **No `datetime.now()` in
   logic** — inject `Realtime`/`Simulated`/`Accelerated` from `core/clock.py`.
3. **Walk-forward is the only accepted performance evidence.** In-sample numbers are
   not results; no cost reductions to rescue a result (GOAL.md §6).
4. **Full Indian cost stack on every fill**: STT, exchange txn, SEBI, stamp duty, DP
   charges, brokerage, 18% GST — never skip (11.65/11.66 bps statutory + slippage;
   21.92 bps all-in round trip in research/optimize assumptions; CI greps
   costs = 11.92 bps figure in nsealgo).
5. **Live and paper share one code path** — only the broker adapter differs
   (`PaperBroker` vs `KiteBroker`, Broker Protocol).
6. **C1–C10 data cleaning** in `nsealgo/data/loader.py` — never bypass; `DataIntegrityError`
   is a stop, not a warning.
7. **Provenance is fingerprinted** (`nsealgo.provenance`):
   `engine 29764f562cd5 · loader c1badf5f7df8 · costs ba350aef75b3 · panel 389b082b832f`.
   **Always quote an nsealgo result with its end date AND its engine SHA.** A stored
   result whose `engine_sha` does not match the working tree is stale — re-run it,
   never quote it. Current authoritative result (reports/VALIDATION_v1.md §0):
   9.52% OOS, Sharpe 0.32, Sortino 0.38, MaxDD −14.92%, Band D; correction chain
   13.40 → 10.97 → 9.89 → 9.71 → 9.52.
8. **Tie-break rule (binding)**: score ties broken by `blake2b(f"{date}|{symbol}")` via
   `np.lexsort` — deterministic, order-independent, **not alphabetical**. Never
   reintroduce `argsort(..., kind="stable")` (silent alphabetical bias). Binary 0/1
   masks tie every name exactly → 0.0%-turnover book under the old rule. Any result on
   a tied/binary panel from `d93815344bd3` or earlier must be re-run. GOAL.md §11.5.
9. **EventBus** for decoupled component communication (crypto); events vocabulary in
   `core/events.py`.
10. **Risk limits from GOAL.md §3.3 hard-coded** in `nsealgo/risk/limits.py` (verified
    at import; not configurable upward).
11. **Async-first** crypto I/O (asyncio, aiohttp, redis.asyncio); config via Pydantic
    Settings + YAML (`configs/base.yaml`, env-prefix, `${ENV_VAR}` secrets).
12. **src-layout** (`pip install -e .`); import as `cryptobot` / `nsealgo`.
13. **ruff**: py313 target, line 110, E,F,W,I,B,UP (ignore E501), `tests/*=['B']`,
    **`known-first-party = ['nsealgo','cryptobot']`** — keep it updated when adding top-level packages.

### NSE hard constraints (from data reality, audited)

| Timeframe | History | Use |
|-----------|---------|-----|
| **1d** | ~6,000 bars, ~24y (2002→2026-10) | ✅ primary research substrate |
| 1h / 4h | ~1–2y | ⚠️ corroboration only |
| 5m/15m/30m | weeks–months | ⚠️ sanity only |
| **1m** | ~1,800 bars, ~30 days | ❌ **unusable — intraday is BANNED** |

Daily bars only; holding period 5–60 days; weekly/biweekly rebalance.

---

## Important Files

| File | Purpose |
|------|---------|
| `GOAL.md` | Binding constitution — capital, limits, gates (read first) |
| `reports/VALIDATION_v1.md` | **Authoritative** validation evidence |
| `configs/base.yaml` | Full config schema (env-overridable) |
| `src/cryptobot/config.py` | Pydantic Settings loading |
| `src/cryptobot/core/events.py` | All event types + payloads |
| `src/cryptobot/core/clock.py` | Clock protocol (Realtime/Simulated/Accelerated) |
| `src/cryptobot/core/portfolio.py` | Portfolio state, kill-switch logic |
| `src/cryptobot/execution/engine.py` | Order submission flow |
| `src/cryptobot/backtest/engine.py` | Backtest event loop |
| `src/cryptobot/monitoring/health.py` | Health check framework |
| `src/nsealgo/cli.py` | NSE sole CLI entrypoint |
| `src/nsealgo/data/loader.py` | C1–C10 cleaning + `load_universe` |
| `src/nsealgo/risk/limits.py` | Frozen hard limits (import-verified) |
| `src/nsealgo/execution/{broker,paper,kite}.py` | Broker Protocol adapters |
| `research/AGENT_BRIEF.md` | Mandatory research setup (`sys.path.insert(0,'src')`) |
| `docs/RUNBOOK.md` | Ops guide: venv, CLIs, compose paths, provenance |
| `PROJECT_MEMORY/13_Bug_Tracker.md` | Bugs indexed vs GitHub #20–#53 |
| `tools/` | `download_nse.py`, `recover_nse_data.py --verify-only`, `build_pit_membership.py`, `kite_login.py` (token swap → `state-nse/kite_session.json`), `gate_status.py`, `control_room.py` (:8090), `gen_catalog.py` codegen |

`tools/*.py` need repo-root cwd.

---

## Runtime/Tooling Preferences

### Run policy: tests on host, app in Docker

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

- **Wave files**: `tests/unit/test_waveN_*` are generated try/except-True artifacts —
  low-signal; don't infer code health from them.
- **`PYTHONPATH=src:.` pattern** for research module runs (crypto imports fail without
  `pip install -e .`; nsealgo CI slice sets `PYTHONPATH=src` explicitly).
- **Coverage gate is CI-only**: `--cov=cryptobot --cov-fail-under=70 --timeout=60`
  (`COVERAGE_THRESHOLD=70`); don't demand coverage locally.
- **`.cargo/config.toml` must NOT set `-C target-cpu=native`** — breaks cached builds
  across runner CPUs (proc-macro `.so` SIGILL). Local opt-in: `CARGO_RUSTFLAGS="-C target-cpu=native"`.
- **Never edit a file inside a container.** Edit on the host, rebuild the image.
- Root `tools/*.py` need repo-root cwd.
- Rust extension `cryptobot_rs`: CI-built + import-smoke-tested only; not imported by Python.

---

## Testing & QA

### Layout & fixtures
- `tests/unit/` (~150+ files incl. low-signal generated `test_waveN_*`),
  `tests/strategies/` (`test_catalog_<strategy>.py` per strategy), `tests/integration/`
  (`test_external_services.py` — TimescaleDB/Redis/Prometheus; **self-skips** via socket
  probes when services are absent).
- Single `tests/conftest.py`: autouse `reset_singletons` + `reset_logging` every test;
  `metrics_registry` fixture (isolated Prometheus registry); `@pytest_asyncio.fixture event_bus`.

### Config
- `pyproject [tool.pytest.ini_options]`: `asyncio_mode="auto"`, `testpaths=["tests"]`,
  `addopts="-ra"`, marker `integration`. Deps: `requirements/test.txt` (prod + pytest≥8.3,
  pytest-asyncio, pytest-cov, pytest-timeout, hypothesis (max_examples=50), ccxt, tqdm).

### Commands
```bash
.venv/bin/python -m pytest tests/unit -q                 # host venv, fast loop
pytest -m "not integration" -q                           # skip external-service tests
pytest --cov=cryptobot --cov-report=term-missing --timeout=60   # what CI runs (gate CI-only)
# CI nsealgo slice = explicit file list with PYTHONPATH=src
cargo test --workspace                                    # Rust, separate
```

### Quirks & common failures
| Symptom | Cause / fix |
|---------|-------------|
| `ModuleNotFoundError: cryptobot` | `pip install -e .` (or set `PYTHONPATH=src`) |
| `asyncio.run()` inside tests | **Known failure cause** — use `await` directly (asyncio auto-mode is on; explicit `@pytest.mark.asyncio` dominant) |
| `test_nsealgo_data.py` skips/fails | requires `data/nse/asianpaint_1d.csv` or `$NSE_DATA` (68MB, gitignored) |
| `sqlite3` missing | graceful no-op persistence (try/except import) — install `sqlite3` or run in Docker |
| `ccxt` not installed | in `requirements/test.txt`; needed for Binance venue tests |
| CI nsealgo slice imports fail | run with `PYTHONPATH=src` |
| Docker tests | `make compose-test`, test target runs `pytest -q tests` |

### CI pipeline (ci.yml DAG)
`changes` (path filter) → `lint` (ruff 0.16.1 + pyflakes 3.4.0) → `security-review`
(gitleaks) ∥ `security-audit` (pip-audit) → `cargo-lint` → `cargo-test` → `pyo3`
(maturin 1.9.6, core paths) → `nsealgo` (ruff + 4 test files `PYTHONPATH=src` +
calibration greps: costs 11.92 bps; limits 0.15 0.25 0.08 0.02 0.04 0.12 0.25 +
Dockerfile.nse smoke) → `unit` (matrix 3.13/3.14, `--cov-fail-under=70`) →
`docker-test` (Trivy CRITICAL/HIGH fail) → `compose-validate` → `docker-build`
(production; amd64 PR / amd64+arm64 push; /health smoke) → `docker-manifest`.
`release.yml`: tag `v*.*.*` → multiarch + SBOM + provenance. Dependabot: actions/pip/docker Mondays.

---

*Generated from repo analysis + 4 scout reports (2026-11-10). Update when conventions change.*
