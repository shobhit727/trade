# 05. Control Flow

> **Last Updated**: 2026-07-29 (audit pass)
> **Confidence**: High for live, backtest, and CLI; medium for ML.

## Startup (verified)

```
cli/main.py:build_parser()
  └─► cli/main.py:main()
        └─► asyncio.run(_run(args))
              └─► switch on `args.command`: backtest | validate | paper
```

Today the CLI is a placeholder. The first three subcommands print "OK" and exit with code 0.

## Backtest startup (verified)

```
backtest/engine.py:BacktestEngine(start, end, capital)
  └─► async initialize()
        ├─► ClockFactory.create_for_backtest(start, end)
        ├─► get_portfolio_manager(PortfolioMode.BACKTEST).initialize()
        └─► portfolio.update_equity(initial_capital)
  └─► async run(data_stream: AsyncIterator[Event])
        └─► for event in data_stream: await _process_event(event)
```

## Live startup (verified)

```
market_data.manager.BinanceWSClient.start()
  ├─► aiohttp.ClientSession
  ├─► ws_connect(...)
  ├─► asyncio.create_task(self._heartbeat())
  └─► asyncio.create_task(self._listen())
        └─► for each ws message: parse → publish event onto EventBus
```

## Order flow (verified)

```
strategies.base.BaseStrategy.on_market_data(event)
  └─► List[OrderEvent]
        └─► execution.engine.ExecutionEngine.submit_order(order)
              ├─► risk.manager.RiskManager.check_order(order, price)
              ├─► event_bus.publish(RiskEvent(...))
              ├─► if rejected → set status REJECTED, publish, return
              └─► venue.submit_order(order) → filled OrderEvent
                    └─► event_bus.publish(Event(ORDER_FILLED, payload=filled.payload))
```

## Risk check order (verified)

```
risk.manager.RiskManager.check_order(order, price)
  ├─► kill_switch.evaluate(portfolio)
  ├─► notional = order.quantity * (price or order.price or order.avg_fill_price or 0)
  ├─► notional < min_order_size_usd → reject
  ├─► notional > max_order_size_usd → reject
  ├─► total_exposure = (used_margin + notional) / total_equity
  └─► if total_exposure > max_total_exposure_pct → reject
```

## Health check (verified)

```
monitoring.health.HealthMonitor.run_all_checks()
  ├─► for each HealthCheck: _run_check(check)
  │     ├─► value = check.check_fn()
  │     ├─► if inspect.isawaitable(value): await with timeout
  │     ├─► if value is False (or tuple (False, msg)): UNHEALTHY
  │     └─► else: HEALTHY
  └─► for each HealthChecker: result = await checker.check() → _process_result
```

## Failure modes

- **No sqlite3**: `core.state.StateManager` skips DB init; persistence silently disabled. State diverges across restart.
- **No prometheus_client**: `monitoring.metrics` import fails. `monitoring/__init__.py` re-exports symbols from metrics; any code importing `cryptobot.monitoring` crashes.
- **No asyncpg**: `data.storage.TimescaleDBStorage` import-time dependency; `data/__init__.py` re-exports it.
- **No pandas**: `data.cleaning` import fails; `data/__init__.py` re-exports.
- **No aiohttp**: `data.ingestion` import fails; `market_data.manager` import fails.
- **No redis**: `market_data.manager` import fails.

## Confidence

- High: control flow in code paths that exist.
- Medium: behavior under partial optional dependencies.
- Low: ML pipeline (no code).
