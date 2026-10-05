# 13. Bug Tracker

> **Last Updated**: 2026-08-22 (full-repo audit: 34 issues filed as GitHub #20–#53; see Open → GitHub Issues below)
> **Confidence**: High for resolved; high for newly-filed (each verified by code reading, several reproduced empirically).

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

> **2026-08-22 full-repo audit**: all newly-found bugs are tracked as GitHub issues (#20–#53) with
> severity labels (`critical`/`high`/`medium`/`low`) and area labels (`backtest`/`ml`/`risk`/
> `monitoring`/`infra`/`rust`). The table below indexes them; consult the issue bodies for
> evidence, repros, and suggested fixes.

### Critical

| Issue | Area | Summary |
|-------|------|---------|
| [#20](https://github.com/shobhit727/trade/issues/20) | backtest | Equity curve stamped wall-clock → `_periods_per_year` ≈ 31.5M; Sharpe/Sortino meaningless on `run_bars`. |
| [#21](https://github.com/shobhit727/trade/issues/21) | ml | `future_returns` labels are backward returns, identical to `ret_h` feature → identity leakage in ML training. |
| [#22](https://github.com/shobhit727/trade/issues/22) | infra | Dockerfile production CMD duplicates `-m` under ENTRYPOINT → container crashes instantly. |
| [#23](https://github.com/shobhit727/trade/issues/23) | infra | compose/docker-compose.yml broken end-to-end (bad Dockerfile path, nonexistent `--mode` flag, wrong migrations path). |
| [#24](https://github.com/shobhit727/trade/issues/24) | rust | ERC `risk_parity_weights` update reduces to w∝w² → converges to 100%-single-asset corner. |
| [#25](https://github.com/shobhit727/trade/issues/25) | backtest | Flip signals never establish shorts (single close order) — all 84 catalog strategies run long-only-flip semantics. |
| [#26](https://github.com/shobhit727/trade/issues/26) | execution/costs | TransactionCostModel sums raw `*_bps` values as currency; slippage returned as fraction; bounds rescale mangles everything. |
| [#27](https://github.com/shobhit727/trade/issues/27) | ml | WalkForwardOptimizer non-functional: every Optuna trial TypeErrors; SHARPE objective never computed; fallback in-sample. |
| [#28](https://github.com/shobhit727/trade/issues/28) | infra/k8s | Deployment runs one-shot `paper` (probes fail); duplicate Service+HPA break kustomize; invalid `:ro` mountPath. |

### High

| Issue | Area | Summary |
|-------|------|---------|
| [#29](https://github.com/shobhit727/trade/issues/29) | monitoring/config | `MonitoringSettings` missing all email_* fields → AttributeError when email alerts enabled. |
| [#30](https://github.com/shobhit727/trade/issues/30) | backtest | Funding settlement skipped on 6h/12h bar grids (exact-hour gate); minutes unchecked. |
| [#31](https://github.com/shobhit727/trade/issues/31) | backtest | funding_sim prices decisions off the unclosed bar's future close (lookahead). |
| [#32](https://github.com/shobhit727/trade/issues/32) | backtest | `run_bars` never marks positions to market between fills; drawdown/Sharpe ignore unrealized PnL. |
| [#33](https://github.com/shobhit727/trade/issues/33) | risk | `backtest_mode=True` disables kill switch + size/exposure/position limits, not just time-based checks. |
| [#34](https://github.com/shobhit727/trade/issues/34) | monitoring | Data-freshness check vacuously HEALTHY when no tickers exist at all. |
| [#35](https://github.com/shobhit727/trade/issues/35) | monitoring | Component health ignores HealthChecker results (kill-switch state invisible in /health). |
| [#36](https://github.com/shobhit727/trade/issues/36) | ml | `RegimeDetector.predict` ignores input features; returns stale in-sample labels. |
| [#37](https://github.com/shobhit727/trade/issues/37) | deps | `asyncpg`/`pyarrow` imported by data/storage.py but absent from every dependency manifest. |
| [#38](https://github.com/shobhit727/trade/issues/38) | infra/CI | release.yml omits PYTHON_TAG → v-tag images built on Python 3.13 vs 3.14 elsewhere. |
| [#39](https://github.com/shobhit727/trade/issues/39) | backtest | Python Sortino uses losses-only std instead of downside deviation (also optimize objective). |
| [#40](https://github.com/shobhit727/trade/issues/40) | rust | Rust Sortino wrong formula (~2–4×); max_drawdown understated by `max(peak,1.0)` divisor. |
| [#41](https://github.com/shobhit727/trade/issues/41) | risk/rust | NaN passes all Rust limit checks; Kelly −inf; vol_target unbounded leverage. |
| [#42](https://github.com/shobhit727/trade/issues/42) | rust | Backtest engine/runner/validation/reporting modules dead code referencing nonexistent core APIs. |
| [#43](https://github.com/shobhit727/trade/issues/43) | execution | BinanceVenue retries non-retryable errors / can double-send market orders; stop types likely invalid via ccxt unified API. |
| [#44](https://github.com/shobhit727/trade/issues/44) | cli | `cryptobot ml` crashes: `build_features(bars)` + `DirectionClassifier(horizon=)` misuse. |

### Medium/Low (grouped sweep issues)

| Issue | Scope |
|-------|-------|
| [#45](https://github.com/shobhit727/trade/issues/45) | MarketMaking never submits orders; mm CLI fabricates fills; attach_to_engine is a no-op wrapper. |
| [#46](https://github.com/shobhit727/trade/issues/46) | `VWAPSchedule.at()` index double-scaled → wrong slice (repro'd). |
| [#47](https://github.com/shobhit727/trade/issues/47) | absolute_momentum neutral zone returns −1 instead of 0. |
| [#48](https://github.com/shobhit727/trade/issues/48) | ML sweep ×10: ensemble class-0 prob, variance×252 "annualized vol", features_and_labels crash, QUANTILE fitted flag, inference cache keys, FeatureSet.to_array, DriftDetector zero-mean, optimizer forecast call, random-label scoring, k-means NaN centroids. |
| [#49](https://github.com/shobhit727/trade/issues/49) | Risk sweep ×4: correlation limit dead code, strategy daily-loss inert + tracker drawdown math, vol_target cap bypass, KillSwitch.reset no-op. |
| [#50](https://github.com/shobhit727/trade/issues/50) | Monitoring sweep ×6: phantom position gauges, drawdown gauge always 0, alert dedup defeats auto-resolve, unbounded alert history, interval_seconds dead config, dashboard PromQL vector mismatch. |
| [#51](https://github.com/shobhit727/trade/issues/51) | Backtest/data sweep ×15: carry alignment timestamps, stale-mark funding, SimulatedVenue unconditional limit fills, √252 hardcodes, deflated Sharpe math, optimize in-sample, Parquet dupes, save_order crash, publish_batch deadlock, HybridStorage cutoff dup, resample aliases, depthUpdate/markPrice handlers, z-score validator, CsvFundingProvider symbol ignore, mock equity report, naive datetimes. |
| [#52](https://github.com/shobhit727/trade/issues/52) | Infra sweep ×13: Codecov condition never true, prod stage installs test reqs by default, `${VAR}` placeholders literal + dead YAML blocks, dead env vars, Grafana provider path unmounted, Prometheus scrapes nonexistent exporters, `${ENVIRONMENT}` label, release workflow_dispatch always fails, port-8080 collision, @latest action pin, cancel-in-progress on release, tag-scheme mismatch, floating prod deps/pyproject drift. |
| [#53](https://github.com/shobhit727/trade/issues/53) | Rust sweep ×8: bollinger period=0 panic, VPIN not VPIN, walk_forward slice panic, RSI 99.01, EWMA λ unvalidated, Markowitz silent truncation, Decimal→f64 silent zeros, hardcoded √252 annualization. |

### Legacy open

| ID | File | Bug | Risk |
|----|------|------|------|
| B073 | `git` (remote branch) | `origin/fix/realistic-venue-bugs` is **stale** — based on `f837152`; diverges from `main` by −2276 lines (deletes `execution/costs.py`, `ml/optimizer.py`, `live/paper_harness.py` etc.). Its realistic-venue changes were superseded by `932e7e2`. | Low. Delete branch or rebase onto `main`; do not merge as-is. |

### Environment note

`Makefile` defaults `PY ?= python3.13`; hosts with only python3.14 must override (`make test PY=python3`). Consider defaulting to `python3`.

## Will-surprise areas

- `core/portfolio.py` `StrategyAllocation` initial `max_weight=0.2` is hardcoded; reads `settings.risk.max_single_position_pct` only if `register_strategy` is called with an explicit `max_weight` arg.
- `risk/manager.py` uses `state.used_margin + notional` for total exposure. `used_margin` may not reflect actual margin usage for cross-margin venues.
- Catalog strategies are **long-only in effect** under the current engine (issue #25): `-1` flips close but never open shorts, and each strategy's internal `_pos` diverges from engine state after a flip. Any research conclusion drawn from catalog backtests before a fix carries this bias.
- Backtest headline metrics (Sharpe/Sortino/maxDD) are unreliable until #20/#32/#39 are fixed; treat all pre-audit backtest numbers as directional only.

## Verification plan

- `python3 -m py_compile` on all edited files: passes.
- `pytest -q`: 781 passed / 6 skipped (2026-08-22).
- `cargo clippy --workspace --all-targets -- -D warnings` + `cargo test --workspace`: green; 63 tests (2026-08-22) — note tests are trivially-satisfiable in several cases (#24/#40), so green ≠ correct.
- `docker compose --profile test config`: passes.
- Full Docker runtime blocked by host daemon instability on some hosts.
- Production image runtime: **known broken** until #22 is fixed (CI never runs the production target).
