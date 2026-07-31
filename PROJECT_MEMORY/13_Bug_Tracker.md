# 13. Bug Tracker

> **Last Updated**: 2026-07-31 (audit sync)
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
| B020 | `tests/unit/test_core_foundation.py` | Tests referenced nonexistent APIs (`SubscriptionMode`, `update_on_trade`). | Replaced. |
| B021 | `Dockerfile` | Missing. | Created. |
| B022 | `docker-compose.yml` | No test service. | Added `cryptobot-test` in profile `test`. |
| B023 | `.dockerignore` | Large `monitoring/` files in context. | Added minimal context. |
| B024 | `core/state.py` | If `sqlite3` unavailable, persistence silently no-ops. | Log warning on import fail. |
| B025 | `monitoring/metrics.py` | `record_pnl(..., realized_pnl=...)` uses Prometheus `Counter` which cannot decrement. | `total_pnl` is now `Gauge`. |
| B026 | `monitoring/health.py` | `create_standard_checks` wraps async functions in sync lambdas. With B013 fix, await path works, but style is fragile. | Open — future refactor. |
| B027 | `utils/decorators.py` | `retry` jitter: `sleep_time = backoff_factor * (2**attempt) + random.uniform(-0.1, 0.1)` may go negative. | Clamped with `max(0.0, sleep_time)`. |
| B028 | `utils/decorators.py` | `circuit_breaker` sync wrapper uses `asyncio.get_event_loop().run_until_complete(...)` inside running loop. | Raises `RuntimeError` in running loop. |
| B029 | `monitoring/metrics.py` | `ProfitFactor` uses `Counter` for realized PnL with negative values. | Same as B025 — `Gauge` used. |
| B030 | `data/cleaning.py` | `clean_klines` `report.start`/`end` defaults to `datetime.utcnow()` when columns missing at top of function. | Cosmetic; not fixed. |
| B031 | `monitoring/alerting.py` | `init_alerting` may attempt to start threads even without channels. | Skip `start()` when no channels configured. `stop()` idempotent. |
| B032 | `backtest/engine.py` | `_handle_order_fill` updates equity using unrealized PnL from payload, but does not subtract fees from equity. | Trade `pnl` nets fees, `pnl_pct` computed from net. |
| B033 | `backtest/validation.py` | `_perform_walk_forward` and `_run_monte_carlo` return fixed values. | Replaced with real math. |
| B034 | `core/portfolio.py` | `check_kill_switch` reads `daily_loss_pct` from state; `daily_pnl` reset relies on external cron. | `update_equity` auto-detects day boundary and resets `_daily_pnl_start`. |
| B035 | `monitoring/dashboard.py` | Dashboard JSON builders reference Prometheus expression names with `cryptobot_` prefix; not exercised. | Unknown. |
| B036 | `execution/venue/simulated.py` | Ignores slippage/fees. | Slippage + commission applied. |
| B037 | `monitoring/metrics.py` | `total_pnl` `Counter` cannot accept negative PnL. | Same as B025 — `Gauge`. |
| B038 | `risk/manager.py` | `notional_price = price or order.price or order.avg_fill_price or Decimal("0")` yields zero for unfilled market orders → reject by min size. | Skip notional check when no price available (market order pre-trade). |
| B039 | `data/cleaning.py` | `clean_trades` allows non-numeric price/quantity silently. | Coerce via `pd.to_numeric`; non-numeric + non-positive rows dropped and reported. |
| B040 | `execution/engine.py` | `submit_order` publishes `OrderEvent` after risk rejection, but `type` is still `OrderType.MARKET`, not `EventType.ORDER_REJECTED`. | Emit `ORDER_REJECTED` event with reason + check_type on risk reject and venue reject. |
| B041 | `monitoring/alerting.py` | Multiple channels all share `init_alerting` resource; no teardown error path. | `stop()` idempotent, guards `_running`. |
| B042 | `data/ingestion.py` | `BinanceDataIngestion` uses `aiohttp.ClientSession` directly without session reuse; opens per-call. | Performance + leak. |
| B043 | `monitoring/health.py` | `HealthMonitor.start` spawns a task but no mechanism to update config-driven checks at runtime. | Hardcoded list. |
| B044 | `market_data/manager.py` | `BinanceWSClient` builds stream URL from `settings.exchange.symbols` (empty by default). | Fallback to `default_symbol` and `["1m"]` when empty. |
| B045 | `core/bus.py` | `EventBus.publish_batch` calls `_dispatch` per event; no transaction. | All events dispatched atomically under single lock. |
| B046 | `backtest/engine.py` | `print(...)` statements throughout. | Removed. |
| B047 | `cli/main.py` | Three subcommands exist but only print-and-exit. | `validate`, `paper`, `bot`, `serve` now have real logic. |
| B048 | `risk/manager.py` | `RiskCheckResult.to_event` converts `Decimal` to `float` (`float(self.current_value)`). | Payload now carries `str(Decimal)` to preserve precision. |
| B049 | `strategies/base.py` | `StrategyRegistry.__new__` prints "initialized" on import. | Removed. |
| B050 | `config.py` | `Settings(extra="ignore")` swallows YAML mismatch. | Added `_flatten_yaml` and `Settings.from_yaml_safe`. |
| B051 | `monitoring/__init__.py` | Eagerly imports `cryptobot.monitoring.metrics`, which fails without `prometheus_client`. | Documented in `19_Open_Questions.md` AV-2. Importers should `import cryptobot.monitoring.metrics` lazily if they need it without Prometheus installed. |
| B060 | `risk/manager.py:43-44` | Notional check uses `price or order.price or order.avg_fill_price` — evaluates to `Decimal("0")` for market orders; `notional_price is not None` is True. Market orders bypass sizing. | Added `notional_price > 0` check; skip notional validation when no valid price. |
| B061 | `execution/engine.py:40` | `check_order(order, order.price)` passes `None` for market orders. | Fetch market price via `venue.get_price()` for market orders before risk check. |
| B062 | `backtest/engine.py:235` | `event.payload.get("price", event.payload.get("close_price", 0))` returns `"0"` if both missing. | Skip mark price update if no valid price in payload. |
| B063 | `backtest/engine.py:306` | Equity update adds unrealized PnL on top of `total_equity` (already includes it). Double-counts. | Removed manual equity update; portfolio tracks equity via position updates. |
| B064 | `backtest/engine.py:294` | `pnl_pct = pnl_net_fees / (pos.entry_price * filled_qty)` — division by zero if entry_price=0. | Guard with `pos.entry_price > 0` check. |
| B065 | `ml/models/direction.py:114-115` | Walk-forward `predict` normalizes test using its own mean/std — data leakage. | Store train statistics (`_feature_means`, `_feature_stds`) in `fit()`; use them in `predict()`. |
| B066 | `monitoring/health.py:443,472` | `settings.exchange.symbols` empty if YAML missing — health checks pass vacuously. | Fallback to `[settings.exchange.default_symbol]` when symbols list empty. |
| B067 | `monitoring/alerting.py:259-260` | `run_in_executor(None, _send_sync)` creates new thread per email — thread leak. | Shared `ThreadPoolExecutor` (max_workers=2) with lazy init + shutdown in `AlertManager.stop()`. |
| B068 | `data/cleaning.py:88-89` | `start`/`end` default to `datetime.utcnow()` if `open_time` missing — misleading timestamps. | Made `start`/`end` Optional; set to `None` when column missing. |
| B069 | `core/state.py:202` | DB path `cryptobot.db` in cwd (`/app`) not in mounted volume (`/app/data`) — state lost on restart. | Use `/app/data` if exists, else cwd; DB now at `/app/data/cryptobot.db` (persisted). |

## Open (verified)

| ID | File | Bug | Risk |
|----|------|------|------|
| B026 | `monitoring/health.py` | `create_standard_checks` wraps async functions in sync lambdas. With B013 fix, await path works, but style is fragile. | Future regressions. |
| B030 | `data/cleaning.py` | `clean_klines` `report.start`/`end` defaults to `datetime.utcnow()` when columns missing at top of function. | Cosmetic. |
| B035 | `monitoring/dashboard.py` | Dashboard JSON builders reference Prometheus expression names with `cryptobot_` prefix; not exercised. | Unknown. |
| B042 | `data/ingestion.py` | `BinanceDataIngestion` uses `aiohttp.ClientSession` directly without session reuse; opens per-call. | Performance + leak. |
| B043 | `monitoring/health.py` | `HealthMonitor.start` spawns a task but no mechanism to update config-driven checks at runtime. | Hardcoded list. |
| B052 | `docker-compose.yml` | Default profile references missing `monitoring/{loki,promtail,nginx}` dirs — compose config fails on default profile. | Compose won't start. | **RESOLVED** — scaffolded 3 dirs with minimal configs; `docker compose config` passes.
| B053 | `deploy/k8s/` | Missing `Service` and `HPA` resources claimed in plan.md. | Cluster-internal only, no ingress. |
| B054 | `src/cryptobot/strategies/ml_strategy.py` | File does not exist; plan.md Phase 4 claims `[x]`. | ML strategy cannot be instantiated. |
| B055 | `requirements/prod.txt` | Lists `lightgbm>=4.5` but `ml/models/direction.py` uses sklearn/numpy only — no lightgbm import. | Heavy native dep unused. |
| B056 | `src/cryptobot/data/features.py` | File does not exist; plan.md section 2 lists as `🔲 Missing`. | Use `ml/features.py` instead; update references. |
| B057 | `crates/*/src/` | All 7 Rust crates have empty `src/` — `cargo build` fails. | Rust layer non-functional. |
| B058 | `configs/base.yaml` | `ml.models.direction.type: lightgbm` but implementation uses sklearn. | Config mismatch; silent loss. |
| B059 | `configs/base.yaml` | `strategies.enabled` list not read by any code — strategies never auto-instantiated from config. | Strategies not loaded from config. |

## Will-surprise areas

- `backtest/engine.py` `_handle_order_fill` opens positions using `PositionSide.LONG if side == "BUY" else PositionSide.SHORT`. This is correct for spot but ambiguous for futures with hedge mode. Verify.
- `core/portfolio.py` `StrategyAllocation` initial `max_weight=0.2` is hardcoded; reads `settings.risk.max_single_position_pct` only if `register_strategy` is called with an explicit `max_weight` arg.
- `risk/manager.py` uses `state.used_margin + notional` for total exposure. `used_margin` may not reflect actual margin usage for cross-margin venues.

## Verification plan

- `python3 -m py_compile` on all edited files: passes.
- `docker compose --profile test config`: passes.
- `docker compose config` (default profile): fails on missing `monitoring/{loki,promtail,nginx}`.
- Full Docker run blocked by host daemon instability.