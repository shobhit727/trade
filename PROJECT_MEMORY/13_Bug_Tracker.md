# 13. Bug Tracker

> **Last Updated**: 2026-07-31 (audit pass: risk/exec/portfolio/bus/alerting/state)
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

## Open (verified)

| ID | File | Bug | Risk |
|----|------|------|------|
| B024 | `core/state.py` | If `sqlite3` unavailable, persistence silently no-ops. | Resolved 2026-07-31: log warning on import fail. |
| B025 | `monitoring/metrics.py` | `record_pnl(..., realized_pnl=...)` uses Prometheus `Counter` which cannot decrement. Negative PnL raises. | Crash in P&L updates. |
| B026 | `monitoring/health.py` | `create_standard_checks` wraps async functions in sync lambdas. With B013 fix, await path works, but style is fragile. | Future regressions. |
| B027 | `utils/decorators.py` | `retry` jitter: `sleep_time = backoff_factor * (2**attempt) + random.uniform(-0.1, 0.1)` may go negative. | Negative sleep → exception. |
| B028 | `utils/decorators.py` | `circuit_breaker` sync wrapper uses `asyncio.get_event_loop().run_until_complete(...)` inside running loop. | Crashes in async context. |
| B029 | `monitoring/metrics.py` | `ProfitFactor` uses `Counter` for realized PnL with negative values. See B025. | Crash. |
| B030 | `data/cleaning.py` | `clean_klines` `report.start`/`end` defaults to `datetime.utcnow()` when columns missing at top of function. | Cosmetic. |
| B031 | `monitoring/alerting.py` | `init_alerting` may attempt to start threads even without channels. | Resolved 2026-07-31: skip `start()` when no channels configured. Also made `stop()` idempotent (B041). |
| B032 | `backtest/engine.py` | `_handle_order_fill` updates equity using unrealized PnL from payload, but does not subtract fees from equity. | Resolved 2026-07-29: trade `pnl` now nets fees, `pnl_pct` computed from net. |
| B033 | `backtest/validation.py` | `_perform_walk_forward` and `_run_monte_carlo` return fixed values. | Resolved 2026-07-29: replaced with real math. |
| B036 | `execution/venue/simulated.py` | Ignores slippage/fees. | Resolved 2026-07-29: slippage + commission applied. |
| B039 | `data/cleaning.py` | `clean_trades` allows non-numeric price/quantity silently. | Resolved 2026-07-29: coerce via `pd.to_numeric`; non-numeric + non-positive rows are dropped and reported. |
| B048 | `risk/manager.py` | `RiskCheckResult.to_event` converts `Decimal` to `float` (`float(self.current_value)`). | Resolved 2026-07-29: payload now carries `str(Decimal)` to preserve precision. |
| B034 | `core/portfolio.py` | `check_kill_switch` reads `daily_loss_pct` from state; `daily_pnl` reset relies on external cron. | Resolved 2026-07-31: `update_equity` auto-detects day boundary and resets `_daily_pnl_start`. |
| B035 | `monitoring/dashboard.py` | Dashboard JSON builders reference Prometheus expression names with `cryptobot_` prefix; not exercised. | Unknown. |
| B037 | `monitoring/metrics.py` | `total_pnl` `Counter` cannot accept negative PnL. | Same as B025. |
| B038 | `risk/manager.py` | `notional_price = price or order.price or order.avg_fill_price or Decimal("0")` yields zero for unfilled market orders → reject by min size. | Resolved 2026-07-31: skip notional check when no price available (market order pre-trade). |
| B039 | `data/cleaning.py` | `clean_trades` allows non-numeric price/quantity silently. | Bad data passes. |
| B040 | `execution/engine.py` | `submit_order` publishes `OrderEvent` after risk rejection, but `type` is still `OrderType.MARKET`, not `EventType.ORDER_REJECTED`. | Resolved 2026-07-31: emit `ORDER_REJECTED` event with reason + check_type on risk reject and venue reject. |
| B041 | `monitoring/alerting.py` | Multiple channels all share `init_alerting` resource; no teardown error path. | Resolved 2026-07-31: `stop()` idempotent, guards `_running`. |
| B042 | `data/ingestion.py` | `BinanceDataIngestion` uses `aiohttp.ClientSession` directly without session reuse; opens per-call. | Performance + leak. |
| B043 | `monitoring/health.py` | `HealthMonitor.start` spawns a task but no mechanism to update config-driven checks at runtime. | Hardcoded list. |
| B044 | `market_data/manager.py` | `BinanceWSClient` builds stream URL from `settings.exchange.symbols` (empty by default). | Resolved 2026-07-31: fallback to `default_symbol` and `["1m"]` when empty. |
| B045 | `core/bus.py` | `EventBus.publish_batch` calls `_dispatch` per event; no transaction. | Resolved 2026-07-31: all events dispatched atomically under single lock. |
| B046 | `backtest/engine.py` | `print(...)` statements throughout. | Hard to silence. |
| B047 | `cli/main.py` | Three subcommands exist but only print-and-exit. | No real functionality. |
| B048 | `risk/manager.py` | `RiskCheckResult.to_event` converts `Decimal` to `float` (`float(self.current_value)`). | Precision loss. |
| B049 | `strategies/base.py` | `StrategyRegistry.__new__` prints "initialized" on import. | Side effect. |
| B050 | `config.py` | `Settings(extra="ignore")` swallows YAML mismatch. | Resolved 2026-07-29: added `_flatten_yaml` and `Settings.from_yaml_safe`. |
| B051 | `monitoring/__init__.py` | Eagerly imports `cryptobot.monitoring.metrics`, which fails without `prometheus_client`. | Documented in 19_Open_Questions.md AV-2. Importers should `import cryptobot.monitoring.metrics` lazily if they need it without Prometheus installed. |
| — | `tests/unit/test_cli.py` | Test imported `cli.main` as module, but `cli/__init__.py` re-exports `main` function → `AttributeError: '_run'`. | Resolved 2026-07-31: import `_run` directly from module. |

## Will-surprise areas

- `backtest/engine.py` `_handle_order_fill` opens positions using `PositionSide.LONG if side == "BUY" else PositionSide.SHORT`. This is correct for spot but ambiguous for futures with hedge mode. Verify.
- `core/portfolio.py` `StrategyAllocation` initial `max_weight=0.2` is hardcoded; reads `settings.risk.max_single_position_pct` only if `register_strategy` is called with an explicit `max_weight` arg.
- `risk/manager.py` uses `state.used_margin + notional` for total exposure. `used_margin` may not reflect actual margin usage for cross-margin venues.

## Verification plan

- `python3 -m py_compile` on all edited files: passes.
- `docker compose --profile test config`: passes.
- Full Docker run blocked by host daemon instability.
