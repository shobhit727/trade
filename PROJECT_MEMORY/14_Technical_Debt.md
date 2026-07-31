# 14. Technical Debt

> **Last Updated**: 2026-07-31 (audit sync)
> **Confidence**: High.

## Categories

### Code quality

- `monitoring/metrics.py` uses `Counter` for realized PnL — **RESOLVED**: now `Gauge`.
- `utils/decorators.py` jitter can produce negative sleep — **RESOLVED**: clamped to `max(0.0, sleep_time)`.
- `utils/decorators.py` `circuit_breaker` sync wrapper used `run_until_complete` inside running loop — **RESOLVED**: raises `RuntimeError`.
- `strategies/base.py` printed on import inside `StrategyRegistry.__new__` — **RESOLVED**: removed.
- `backtest/engine.py` mixed `print` with logic — **RESOLVED**: removed.
- `core/clock.py` had `print` statements — **RESOLVED**: removed.

### Architecture

- `Settings(extra="ignore")` masks YAML mismatch — **mitigated**: `_flatten_yaml` + `from_yaml_safe` added.
- `core/state.py` and `core/portfolio.py` both hold account state. Duplicating updates.
- `risk/manager.py` is global; not DI-friendly.
- `market_data.manager.BinanceWSClient` builds URLs from empty defaults → empty subscription — **RESOLVED**: fallback to `default_symbol` and `["1m"]`.
- `data/features.py` missing — canonical feature pipeline is `ml/features.py`. Update references or remove `data/features.py` from plan.

### Performance

- `backtest/engine.py` `_handle_order_fill` is O(N) per fill.
- `data/cleaning.py` `vol_zscore` not accelerated.
- `core/clock.py` `SimulatedClock._notify_waiters` is O(W) per step.
- `data/ingestion.py` opens `aiohttp` sessions per call — no session reuse (B042).
- `monitoring/health.py` `create_standard_checks` wraps async in sync lambdas — fragile style (B026).

### Security

- `BINANCE_API_KEY`/`SECRET` env vars empty in compose defaults.
- `monitoring/alerting.py` may serialize webhook URLs.
- `risk/manager.py` reads `settings.risk.kill_switch_daily_loss_pct` at construction; restart needed for changes.

### Maintainability

- ML pipeline: only core (features + direction + online). Volatility, regime, ensemble missing.
- `ml_strategy.py` missing — plan.md claims `[x]`.
- No `pyproject.toml` / `setup.py` — **RESOLVED**: `pyproject.toml` exists.
- Many modules have unused imports.
- `docker-compose.yml` default profile references missing `monitoring/{loki,promtail,nginx}` dirs — compose fails.
- `deploy/k8s/` missing `Service` and `HPA`.
- Rust workspace: 7 crates with empty `src/` — `cargo build` fails.
- 6 dead empty dirs under `src/cryptobot/`: `allocator/`, `altdata/`, `api/`, `exchanges/`, `funding/`, `xmr/`.

### Test coverage

- 22 unit test files in `tests/unit/`.
- No integration tests (TimescaleDB / Redis / Prometheus).
- No property-based tests (hypothesis) for risk/math.
- No CI/CD test run verification (pytest not run in this env).

## Critical debt (highest impact)

| Item | Effort | Priority | Status |
|------|--------|----------|--------|
| Align `configs/base.yaml` with `Settings` field names (or keep `_flatten_yaml`) | 0.5 day | High | Mitigated |
| Add `pyproject.toml` for `pip install -e .` | 0.5 day | High | **Done** |
| Implement real walk-forward + Monte Carlo | 3-5 days | High | **Done** |
| Implement ML feature pipeline (one indicator module) | 1-2 days | High | **Done** (core) |
| Implement `execution/venue/binance.py` (ccxt adapter) | 1-2 days | High | **Done** |
| Replace `Counter` with `Gauge` for realized PnL | 1 hour | High | **Done** |
| Bound `retry` jitter so sleep_time ≥ 0 | 0.5 hour | High | **Done** |
| Fix `circuit_breaker` sync wrapper (use `nest_asyncio` or always async) | 0.5 hour | High | **Done** (raises) |
| Remove `print(...)` from `core/clock.py`, `backtest/engine.py`, `strategies/base.py` | 1 hour | Medium | **Done** |
| Add `requirements/test.txt` cd into `Dockerfile` test target | 0.5 hour | Medium | **Done** |
| Remove `monero-rpc` references | 0.1 hour | Medium | **Done** |
| Add explicit `Venue.submit_order` params for slippage/fees | 1 day | Medium | **Done** (simulated venue) |
| **Fix `docker-compose.yml` default profile (missing loki/promtail/nginx)** | 0.5 day | **Critical** | **Open** |
| **Add `Service` + `HPA` to `deploy/k8s/`** | 0.5 day | High | **Open** |
| **Implement `ml_strategy.py` or downgrade plan.md** | 1-2 days | High | **Open** |
| **Remove dead dirs `src/cryptobot/{allocator,altdata,api,exchanges,funding,xmr}/`** | 5 min | Medium | **Open** |
| **Drop `lightgbm` from `requirements/prod.txt` if unused** | 5 min | Medium | **Open** |
| **Fix `configs/base.yaml` `ml.models.direction.type: lightgbm` mismatch** | 5 min | Medium | **Open** |
| **Add `data/features.py` or remove reference from plan** | 1 day | Medium | **Open** |
| **Rust: add `lib.rs` to crates or remove from workspace** | 1-2 days | Low | **Open** |

## Removal candidates

- `lightgbm` from `requirements/prod.txt` (declared but unused).
- `src/cryptobot/{allocator,altdata,api,exchanges,funding,xmr}/` (empty dirs).
- `data/features.py` reference in plan.md (use `ml/features.py`).

## Risk

- Bypassing `risk/manager.py` would be catastrophic. No guard today.
- `state_manager` silent no-op on missing `_sqlite3` is invisible to users — now logs warning.

## Confidence

- High.