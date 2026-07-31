# 14. Technical Debt

> **Last Updated**: 2026-07-31 (audit v2)
> **Confidence**: High.

## Categories

### Code quality

- ~~`monitoring/metrics.py` uses `Counter` for realized PnL~~ — **RESOLVED** (B025/B037).
- ~~`utils/decorators.py` jitter can produce negative sleep~~ — **RESOLVED** (B027).
- ~~`utils/decorators.py` `circuit_breaker` sync wrapper used `run_until_complete` inside running loop~~ — **RESOLVED** (B028).
- ~~`strategies/base.py` printed on import inside `StrategyRegistry.__new__`~~ — **RESOLVED** (B049).
- ~~`backtest/engine.py` mixed `print` with logic~~ — **RESOLVED** (B046).
- ~~`core/clock.py` had `print` statements~~ — **RESOLVED** (B046).
- Unused imports in some modules — not yet swept.

### Architecture

- ~~`Settings(extra="ignore")` masks YAML mismatch~~ — **mitigated** via `_flatten_yaml` + `from_yaml_safe` (B050).
- `core/state.py` and `core/portfolio.py` both hold account state. Duplicating updates.
- `risk/manager.py` is global; not DI-friendly.
- ~~`market_data.manager.BinanceWSClient` builds URLs from empty defaults → empty subscription~~ — **RESOLVED** (B044).
- ~~`data/features.py` missing~~ — **RESOLVED**: re-export created (B056).

### Performance

- `backtest/engine.py` `_handle_order_fill` is O(N) per fill.
- `data/cleaning.py` `vol_zscore` not accelerated.
- `core/clock.py` `SimulatedClock._notify_waiters` is O(W) per step.
- ~~`data/ingestion.py` opens `aiohttp` sessions per call — no session reuse~~ — **RESOLVED** (B042).
- ~~`monitoring/health.py` `create_standard_checks` wrapped async in sync lambdas~~ — **RESOLVED** (B026).

### Security

- `BINANCE_API_KEY`/`SECRET` env vars empty in compose defaults.
- `monitoring/alerting.py` may serialize webhook URLs.
- `risk/manager.py` reads `settings.risk.kill_switch_daily_loss_pct` at construction; restart needed for changes.

### Maintainability

- ML pipeline: only core (features + direction + online). Volatility, regime, ensemble still missing.
- ~~`ml_strategy.py` missing — plan.md claims `[x]`~~ — **RESOLVED** (B054).
- ~~No `pyproject.toml` / `setup.py`~~ — **RESOLVED**: `pyproject.toml` exists.
- Many modules have unused imports.
- ~~`docker-compose.yml` default profile references missing `monitoring/{loki,promtail,nginx}` dirs~~ — **RESOLVED**: scaffolded.
- ~~`deploy/k8s/` missing `Service` and `HPA`~~ — **RESOLVED** (B053).
- **NEW** Rust workspace: 7 members declared in `Cargo.toml`; only `cryptobot-core` has manifest. `cargo build` fails.
- **NEW** 6 dead empty dirs under `src/cryptobot/`: `allocator/`, `altdata/`, `api/`, `exchanges/`, `funding/`, `xmr/`.

### Test coverage

- 22 unit test files in `tests/unit/`.
- No integration tests (TimescaleDB / Redis / Prometheus).
- No property-based tests (hypothesis) for risk/math.
- No CI/CD test run verification (pytest not run in this audit env).

## Critical debt (highest impact, post-fix)

| Item | Effort | Priority | Status |
|------|--------|----------|--------|
| Align `configs/base.yaml` with `Settings` field names (or keep `_flatten_yaml`) | 0.5 day | High | **Done** (B050) |
| Add `pyproject.toml` for `pip install -e .` | 0.5 day | High | **Done** |
| Implement real walk-forward + Monte Carlo | 3-5 days | High | **Done** |
| Implement ML feature pipeline (one indicator module) | 1-2 days | High | **Done** (core) |
| Implement `execution/venue/binance.py` (ccxt adapter) | 1-2 days | High | **Done** |
| Replace `Counter` with `Gauge` for realized PnL | 1 hour | High | **Done** (B025/B037) |
| Bound `retry` jitter so sleep_time ≥ 0 | 0.5 hour | High | **Done** (B027) |
| Fix `circuit_breaker` sync wrapper | 0.5 hour | High | **Done** (B028) |
| Remove `print(...)` from `core/clock.py`, `backtest/engine.py`, `strategies/base.py` | 1 hour | Medium | **Done** |
| Add `requirements/test.txt` and Dockerfile test target | 0.5 day | Medium | **Done** |
| Remove `monero-rpc` references | 0.1 hour | Medium | **Done** (B019) |
| Add explicit `Venue.submit_order` params for slippage/fees | 1 day | Medium | **Done** (B036) |
| Fix `docker-compose.yml` default profile (loki/promtail/nginx) | 0.5 day | Critical | **Done** |
| Add `Service` + `HPA` to `deploy/k8s/` | 0.5 day | High | **Done** (B053) |
| Implement `ml_strategy.py` or downgrade plan.md | 1-2 days | High | **Done** (B054) |
| Remove dead dirs `src/cryptobot/{allocator,altdata,api,exchanges,funding,xmr}/` | 5 min | Medium | **Open** |
| Drop `lightgbm` from `requirements/prod.txt` | 5 min | Medium | **Done** (B055) |
| Fix `configs/base.yaml` `ml.models.direction.type` mismatch | 5 min | Medium | **Done** (B058) |
| Add `data/features.py` as alias | 1 day | Medium | **Done** (B056) |
| **Fix Rust workspace (trim members or add manifests)** | 5 min | **High** | **Done** — trimmed to `["crates/cryptobot-core"]`, deleted 6 empty sibling crate dirs, added `lib.rs` stub, moved `[target.*]` to `.cargo/config.toml`, fixed `[build-profile]` key, dropped dead `python` feature. `cargo build` + `cargo test` pass. |
| **Tighten `BinanceWSClient` fallback to log when fired** | 5 min | Low | **Open** |

## Removal candidates

- 6 dead empty dirs under `src/cryptobot/`.
- Stray `)` character in `plan.md` section 3.
- Self-contradiction in `plan.md` Section 8 (claims Service + HPA done; Section 2 still says "No Service, no HPA"). Both wrong post-fix.

## Risk

- Bypassing `risk/manager.py` would be catastrophic. No guard today.
- `state_manager` silent no-op on missing `_sqlite3` is invisible to users — now logs warning (B024).

## Lazy noop fallbacks for monitoring (B051, resolved)

When `prometheus_client` or `aiohttp` are absent, `cryptobot.monitoring.{metrics, alerting}` import cleanly:

- `metrics.py` exposes `PROMETHEUS_AVAILABLE` and a `_NoOpMetric` stub that swallows `.inc/.set/.observe/.labels/.time/.info/.dec` calls.
- `alerting.py` defers `import aiohttp` to the HTTP channel `_send` methods.
- `monitoring/__init__.py` already routes symbol access through `__getattr__` so the package facade never touches the failing submodules until a symbol is actually requested.
- New `tests/unit/test_monitoring_lazy_imports.py` covers the no-op fallbacks (subprocess + AST).

## Confidence

- High.
