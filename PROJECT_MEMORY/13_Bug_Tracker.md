# 13. Bug Tracker

> **Last Updated**: 2026-08-04 (backtest CLI + Rust workspace fixes closed)
> **Confidence**: High for resolved; medium for open.

## Resolved (verified)

| ID | File | Bug | Fix |
|----|------|------|------|
| B001 | `backtest/metrics.py` | Missing `List`, `Optional`, `datetime`, `PortfolioState` imports. | Added. |
| B002 | `backtest/metrics.py` | `BacktestMetricsRecorder` called missing `calculate_sortino_ratio`. | Added. |
| B003 | `backtest/metrics.py` | Drawdown divided by zero when peak=0. | Replace 0 with NaN, fillna(0) before max. |
| B004 | `backtest/engine.py` | `Position`/`PositionSide` not imported. | Added. |
| B005 | `backtest/engine.py` | `from cryptobot.core.bus import bus` failed (no module-level `bus`). | Removed. |
| B006 | `backtest/engine.py` | `avg_win`/`avg_loss` divide-by-zero if all wins or all losses. | Guarded. |
| B007 | `backtest/engine.py` | `profit_factor` was avg/avg, not gross/gross. | Rewrote. |
| B008 | `backtest/engine.py` | String side compare used literal `"LONG"`. | Use `PositionSide.LONG`. |
| B009 | `backtest/validation.py` | `run_validation` returned `None`. | Returns full report. |
| B010 | `data/storage.py` | `timedelta` not imported. | Added. |
| B011 | `data/cleaning.py` | `validate_ohlcv(df)` crashed on `None`/empty. | Guard added. |
| B012 | `data/cleaning.py` | `clean_*` read `df["..."]` before required-column check. | Reordered. |
| B013 | `monitoring/health.py` | Async check wrappers in lambdas treated as sync; false-return was ignored. | `inspect.isawaitable`, await-with-timeout, treat falsy as `UNHEALTHY`. |
| B014 | `monitoring/health.py` | `_process_result` dropped checks if component never registered. | Auto-register. |
| B015 | `strategies/base.py` | `MeanReversionStrategy` built `OrderEvent(type="SELL", side='SHORT')` (wrong types). | Use `OrderType.MARKET`, `OrderSide.BUY/SELL`, `PositionSide`. |
| B016 | `strategies/base.py` | `from __future__ import annotations` missing; forward ref to `Event` failed. | Added. |
| B017 | `core/clock.py` | `AcceleratedClock` used `time.monotonic()` but `time` not imported. | Added. |
| B018 | `core/state.py` | Hard `import sqlite3` broke Python without `_sqlite3`. | Try/except + skip DB. |
| B019 | `requirements/prod.txt` | `monero-rpc==0.3.0` incompatible with Python 3.11+ and unused. | Removed. |
| B020 | `tests/unit/test_core_foundation.py` | Tests referenced nonexistent APIs. | Replaced with real smoke tests. |
| B021 | `Dockerfile` | Missing. | Created. |
| B022 | `docker-compose.yml` | No test service. | Added `cryptobot-test` in profile `test`. |
| B023 | `.dockerignore` | Large `monitoring/` files in context. | Added minimal context. |
| B024 | `core/state.py` | If `sqlite3` unavailable, persistence silently no-ops. | Log warning on import fail. |
| B025 | `monitoring/metrics.py` | `record_pnl(..., realized_pnl=...)` uses Prometheus `Counter` which cannot decrement. | `total_pnl` is now `Gauge`. |
| B026 | `monitoring/health.py` | `create_standard_checks` wrapped async functions in sync lambdas — fragile style. | Replaced lambdas with named `async def` functions. |
| B027 | `utils/decorators.py` | `retry` jitter could go negative. | Clamped with `max(0.0, sleep_time)`. |
| B028 | `utils/decorators.py` | `circuit_breaker` sync wrapper used `run_until_complete` inside running loop. | Raises `RuntimeError` in running loop. |
| B029 | `monitoring/metrics.py` | `ProfitFactor` uses `Counter` for realized PnL with negative values. | Same as B025 — `Gauge` used. |
| B030 | `data/cleaning.py` | `clean_klines` `report.start`/`end` defaulted to `datetime.utcnow()` when columns missing. | Made `start`/`end` Optional; set to `None` when column missing. |
| B031 | `monitoring/alerting.py` | `init_alerting` may attempt to start threads even without channels. | Skip `start()` when no channels configured. `stop()` idempotent. |
| B032 | `backtest/engine.py` | `_handle_order_fill` did not subtract fees from equity. | Trade `pnl` nets fees; `pnl_pct` computed from net. |
| B033 | `backtest/validation.py` | `_perform_walk_forward` and `_run_monte_carlo` returned fixed values. | Replaced with real math. |
| B034 | `core/portfolio.py` | `check_kill_switch` reads `daily_loss_pct` from state; `daily_pnl` reset relied on external cron. | `update_equity` auto-detects day boundary and resets `_daily_pnl_start`. |
| B035 | `monitoring/dashboard.py` | Dashboard JSON builders reference Prometheus expression names. | Verified — all referenced metrics exist in `metrics.py`. False positive. |
| B036 | `execution/venue/simulated.py` | Ignored slippage/fees. | Slippage + commission applied. |
| B037 | `monitoring/metrics.py` | `total_pnl` `Counter` cannot accept negative PnL. | Same as B025 — `Gauge`. |
| B038 | `risk/manager.py` | `notional_price = price or order.price or ...` yielded zero for unfilled market orders → reject by min size. | Skip notional check when no valid price. |
| B039 | `data/cleaning.py` | `clean_trades` allowed non-numeric silently. | Coerce via `pd.to_numeric`; non-numeric + non-positive rows dropped and reported. |
| B040 | `execution/engine.py` | `submit_order` published `OrderEvent` after risk rejection, but type was not `EventType.ORDER_REJECTED`. | Emit `ORDER_REJECTED` event with reason + check_type on risk reject and venue reject. |
| B041 | `monitoring/alerting.py` | Multiple channels all share `init_alerting` resource; no teardown error path. | `stop()` idempotent, guards `_running`. |
| B042 | `data/ingestion.py` | `BinanceDataIngestion` opened `aiohttp.ClientSession` per call. | Added `_ensure_session()` with lock; sessions created once, reused across calls. |
| B043 | `monitoring/health.py` | `HealthMonitor.start` had no runtime config update mechanism. | Added `unregister_check()`, `update_check_interval()`, `get_check()` methods. |
| B044 | `market_data/manager.py` | `BinanceWSClient` built stream URL from `settings.exchange.symbols` (empty by default). | Fallback to `default_symbol` and `["1m"]` when empty. |
| B045 | `core/bus.py` | `EventBus.publish_batch` called `_dispatch` per event; no transaction. | All events dispatched atomically under single lock. |
| B046 | `backtest/engine.py` | `print(...)` statements throughout. | Removed. |
| B047 | `cli/main.py` | Three subcommands existed but only printed-and-exited. | `validate`, `paper`, `bot`, `serve` now have real logic. |
| B048 | `risk/manager.py` | `RiskCheckResult.to_event` converted `Decimal` to `float`. | Payload now carries `str(Decimal)` to preserve precision. |
| B049 | `strategies/base.py` | `StrategyRegistry.__new__` printed on import. | Removed. |
| B050 | `config.py` | `Settings(extra="ignore")` swallowed YAML mismatch. | Added `_flatten_yaml` and `Settings.from_yaml_safe`. |
| B051 | `monitoring/metrics.py` + `monitoring/alerting.py` | `metrics.py` imported `prometheus_client` at module level (line 10) and constructed ~80 Prometheus objects; `alerting.py` imported `aiohttp` at module level. In environments without these packages, `import cryptobot.monitoring.metrics` or `import cryptobot.monitoring.alerting` would crash, blocking any code (incl. tests) that did `from cryptobot.monitoring import ...`. | **Resolved 2026-07-31**: wrapped `from prometheus_client import ...` in `metrics.py` with try/except + `_NoOpMetric` stub classes (`inc`/`set`/`observe`/`labels` are no-ops); `PROMETHEUS_AVAILABLE` flag exposed. `alerting.py` removed module-level `import aiohttp`; `aiohttp` is now imported lazily inside `TelegramChannel._send_async` / `DiscordChannel._send_async` / `PagerDutyChannel._send_async`. `monitoring/__init__.py` already used `__getattr__` for lazy submodule export. New test `tests/unit/test_monitoring_lazy_imports.py` (6 tests) verifies: (a) package facade imports with no eager deps; (b) `alerting` module imports without aiohttp; (c) AST-level check that `aiohttp` is not imported at alerting module level; (d) noop fallback classes exercised in a subprocess with broken-stub injection. |
| **NEW** | `Cargo.toml [workspace] members` + 6 empty `crates/*` | `cargo build` fails: workspace declared 7 members; only `cryptobot-core` had a `Cargo.toml`. | **Resolved 2026-08-04**: workspace re-expanded to 7 real crates (core/features/risk/stats/orderbook/backtest/py) with PyO3 0.29; fmt/clippy/test green on stable 1.97+. (Intermediate 2026-07-31 step: trimmed members + stub lib.rs — superseded.) Note: `[target.*] rustflags` (`-C target-cpu=native`) later REMOVED from `.cargo/config.toml` on 2026-08-06 — it breaks cached builds across heterogeneous runner CPUs (proc-macro `.so` SIGILL). |
| B060 | `risk/manager.py:43-44` | Notional check bypassed for market orders. | Added `notional_price > 0` check; skip notional when no valid price. |
| B061 | `execution/engine.py:40` | `check_order(order, order.price)` passed `None` for market orders. | Fetch market price via `venue.get_price()` for market orders before risk check. |
| B062 | `backtest/engine.py:235` | `event.payload.get("price", event.payload.get("close_price", 0))` returned `"0"` if both missing. | Skip mark price update if no valid price in payload. |
| B063 | `backtest/engine.py:306` | Equity update added unrealized PnL on top of `total_equity` (double-count). | Removed manual equity update; portfolio tracks equity via position updates. |
| B064 | `backtest/engine.py:294` | `pnl_pct` divided by zero if `entry_price=0`. | Guarded with `pos.entry_price > 0` check. |
| B065 | `ml/models/direction.py:114-115` | Walk-forward `predict` normalized test using its own mean/std — data leakage. | Store train statistics (`_feature_means`, `_feature_stds`) in `fit()`; use in `predict()`. |
| B066 | `monitoring/health.py:443,472` | `settings.exchange.symbols` empty — health checks passed vacuously. | Fallback to `[settings.exchange.default_symbol]`. |
| B067 | `monitoring/alerting.py:259-260` | Email sent via `run_in_executor(None, _send_sync)` — new thread per email. | Shared `ThreadPoolExecutor` (max_workers=2), lazy init + shutdown in `AlertManager.stop()`. |
| B068 | `data/cleaning.py:88-89` | `start`/`end` defaulted to `datetime.utcnow()` if `open_time` missing. | Made `start`/`end` Optional; `None` when column missing. |
| B069 | `core/state.py:202` | DB path `cryptobot.db` in cwd not in mounted volume. | Use `/app/data` if exists, else cwd. |
| B053 | `deploy/k8s/` | Missing `Service` and `HPA` resources. | `05-service.yaml` (ClusterIP) + `06-hpa.yaml` (CPU/memory HPA) added; kustomization.yaml updated. |
| B054 | `src/cryptobot/strategies/ml_strategy.py` | File did not exist; plan.md Phase 4 claimed `[x]`. | Created `MLStrategy` + `MLStrategyConfig` using `DirectionClassifier`. |
| B055 | `requirements/prod.txt` | Listed `lightgbm>=4.5` but implementation uses sklearn. | Removed `lightgbm>=4.5`. |
| B056 | `src/cryptobot/data/features.py` | File did not exist; `ml/features.py` was canonical. | Created `data/features.py` as re-export of `cryptobot.ml.features`. |
| B057 | `strategies/registry.py` | `ml_strategy` missing from strategy registry map. | Added `ml_strategy` to `_STRATEGY_REGISTRY_MAP`. |
| B058 | `configs/base.yaml` | `ml.models.direction.type: lightgbm` but implementation uses sklearn. | Changed to `sklearn_logreg`; disabled `volatility`/`regime`. |
| B059 | `configs/base.yaml` | `strategies.enabled` list not read by any code. | Added `load_strategies_from_config()` with `_STRATEGY_REGISTRY_MAP`. |
| B070 | `backtest/engine.py` | Backtest trade `entry_time` used wall-clock instead of bar time. | **Fixed 2026-08-04**: `Position.opened_at` stamped with clock (bar) time. |
| B071 | `cli/main.py` | `--json` CLI output polluted by log lines on stdout. | **Fixed 2026-08-04**: logs routed to stderr for JSON modes; stdout carries only JSON. |
| B072 | Rust workspace | `cargo build` failed on invalid pyo3 `generate-abi3` feature; clippy/tests broken. | **Fixed 2026-08-04**: pyo3 0.29 feature fixes, submodule wiring, Kelly test correction. `cargo fmt --check`, `cargo clippy --workspace --all-targets -- -D warnings`, `cargo test --workspace` (31 tests) all green. |

## Open (verified)

> **Updated 2026-08-06**: B051 (lazy import) and dead-dir rows removed — both resolved:
> `monitoring/__init__.py` defers submodule imports via `__getattr__` (no-Prometheus safe);
> `src/cryptobot/{allocator,altdata,api,exchanges,funding,xmr}/` dirs were deleted 2026-07-31.

| ID | File | Bug | Risk |
|----|------|------|------|
| B073 | `git` (remote branch) | `origin/fix/realistic-venue-bugs` is **stale** — based on `f837152`; diverges from `main` by −2276 lines (deletes `execution/costs.py`, `ml/optimizer.py`, `live/paper_harness.py` etc.). Its realistic-venue changes were superseded by `932e7e2`. | Low. Delete branch or rebase onto `main`; do not merge as-is. |

## Will-surprise areas

- `core/portfolio.py` `StrategyAllocation` initial `max_weight=0.2` is hardcoded; reads `settings.risk.max_single_position_pct` only if `register_strategy` is called with an explicit `max_weight` arg.
- `risk/manager.py` uses `state.used_margin + notional` for total exposure. `used_margin` may not reflect actual margin usage for cross-margin venues.
- `BinanceWSClient._symbols` / `_timeframes` fallback is silent (B044) — if YAML is misconfigured the bot quietly streams only `BTCUSDT 1m`. Add a `get_logger().warning` when fallback fires.

## Verification plan

- `python3 -m py_compile` on all edited files: passes.
- `docker compose --profile test config`: passes.
- `docker compose config` (default profile): passes (scaffolded `monitoring/{loki,promtail,nginx}`).
- `cargo build` from repo root: ✅ workspace builds (verified 2026-08-04).
- Full Docker runtime blocked by host daemon instability on some hosts.
