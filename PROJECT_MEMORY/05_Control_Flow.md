# 05. Control Flow

> **Last Updated**: 2026-07-31 (audit v2)
> **Confidence**: High for live, backtest, and CLI; medium for ML.

## Startup (verified)

```
cli/main.py:build_parser()
  └─► cli/main.py:main()
        └─► asyncio.run(_run(args))
              └─► switch on `args.command`: validate | paper | bot | serve
```

`serve` starts `utils.health_server.HealthServer` (stdlib `ThreadingHTTPServer`) exposing `/health` JSON and `/metrics` Prometheus text. Docker `HEALTHCHECK` hits `localhost:8080/health`.

## Backtest startup (verified)

```
backtest/engine.py:BacktestEngine(start, end, capital)
  └─► async initialize()
        ├─► ClockFactory.create_for_backtest(start, end)
        ├─► get_portfolio_manager(PortfolioMode.BACKTEST).initialize()
        └─► portfolio.update_equity(initial_capital)
  └─► async run(data_stream: AsyncIterator[Event])
        └─► for event in data_stream: await _process_event(event)

backtest/runner.py:run_backtest(...)     # end-to-end orchestrator
  └─► load OHLCV from backtest/data.py (CSV/Parquet/TimescaleDB/synthetic)
        └─► feed to strategy → ExecutionEngine → SimulatedVenue
              └─► BacktestEngine consumes resulting events
```

## Live startup (verified)

```
market_data.manager.BinanceWSClient.start()
  ├─► aiohttp.ClientSession (reused per start)
  ├─► ws_connect(...)  (uses settings.exchange.symbols, falls back to default_symbol + ["1m"])
  ├─► asyncio.create_task(self._heartbeat())
  └─► asyncio.create_task(self._listen())
        └─► for each ws message: parse → publish event onto EventBus
```

## Order flow (verified)

```
strategies.base.BaseStrategy.on_market_data(event)
  └─► List[OrderEvent]
        └─► execution.engine.ExecutionEngine.submit_order(order)
              ├─► for market order: price = venue.get_price(order.symbol) (B061)
              ├─► risk.manager.RiskManager.check_order(order, price)
              │     ├─► kill_switch.evaluate(portfolio)             # B068 daily-loss guard
              │     ├─► notional check (skip if notional_price is None or ≤0; B038/B060)
              │     ├─► total exposure check (used_margin + notional) / total_equity
              │     └─► emit RiskEvent via to_event
              ├─► if rejected → emit ORDER_REJECTED with reason + check_type (B040)
              ├─► optional SmartOrderRouter.route(...) (if execution.smart_routing)
              ├─► AdverseSelectionGuard.maybe_cancel on quote change (if attached)
              └─► venue.submit_order(order) → filled OrderEvent
                    └─► event_bus.publish(Event(ORDER_FILLED, payload=filled.payload))
```

## Risk check order (verified)

```
risk.manager.RiskManager.check_order(order, price)
  ├─► kill_switch.evaluate(portfolio)
  ├─► notional_price = price or order.price or order.avg_fill_price
  ├─► if notional_price is None or notional_price <= 0: skip notional bounds (B038/B060)
  ├─► notional = order.quantity * notional_price
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
  │     ├─► if inspect.isawaitable(value): await with timeout (B013/B026)
  │     ├─► if value is False (or tuple (False, msg)): UNHEALTHY
  │     └─► else: HEALTHY
  └─► for each HealthChecker: result = await checker.check() → _process_result
```

Runtime mutation API: `HealthMonitor.unregister_check`, `update_check_interval`, `get_check` (B043).

## ML training and inference (verified)

```
ml.online.WalkForwardTrainer.fit(X, y)
  └─► direction.py.DirectionClassifier.fit(X_train, y_train)
        ├─► if sklearn: LogisticRegression()
        ├─► if numpy fallback: closed-form logreg
        └─► persist _feature_means, _feature_stds for predict (B065)

ml.online.DriftDetector.score(...)  # detects mean/std shift on incoming features
  └─► if drift: signal via event_bus; orchestrator may trigger retrain
```

## Failure modes

- **No sqlite3**: `core.state.StateManager` logs a warning (B024), skips DB init; persistence silently disabled. State diverges across restart.
- **No prometheus_client**: `monitoring.metrics` import fails. `monitoring/__init__.py` eagerly re-exports metrics symbols; importing `cryptobot.monitoring` from a no-Prometheus env crashes (B051 still open).
- **No asyncpg**: `data.storage.TimescaleDBStorage` import-time dependency; `data/__init__.py` re-exports it.
- **No pandas**: `data.cleaning` import fails; `data/__init__.py` re-exports.
- **No aiohttp**: `data.ingestion` import fails; `market_data.manager` import fails. After import, `_ensure_session()` lazy-creates and reuses a session (B042).
- **No redis**: `market_data.manager` import fails.
- **No scikit-learn**: `ml.models.direction.DirectionClassifier` falls back to numpy closed-form implementation.

## Confidence

- High: control flow in code paths that exist.
- Medium: behavior under partial optional dependencies.
- Low: live Binance behavior under adversarial network conditions.
