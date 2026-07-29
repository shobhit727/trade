# 17. Performance

> **Last Updated**: 2026-07-29 (audit pass)
> **Confidence**: Medium.

## Verified

- `core/bus.py` `EventBus.publish` uses `asyncio.Lock` around history/dispatch.
- `core/clock.py` `SimulatedClock` wakeups via `asyncio.Event` cleared on `pause`.
- `backtest/engine.py` recomputes equity curve per fill; O(N).
- `data/cleaning.py` uses pandas/numpy.
- `risk/sizing.py` size calculations are O(1).
- `market_data.manager.BinanceWSClient` reuses one `aiohttp.ClientSession` per start.

## Hot paths

- `EventBus._dispatch` — locked per call. Each subscriber invoked in sequence.
- `BacktestEngine._handle_order_fill` — per fill: position update, equity, pnl, trade record.
- `DataCleaner.clean_klines` — vectorized ops; OHLC mask via boolean DataFrame.
- `risk/manager.RiskManager.check_order` — O(1).

## Known bottlenecks

- `core/clock.py` `SimulatedClock._notify_waiters` is O(W) per step.
- `execution/engine.py` `submit_order` resolves order notional with `Decimal("0")` fallback when no price/avg_fill_price is set.
- `data/ingestion.py` `BinanceDataIngestion` performs REST fetches per call without batching.
- `backtest/engine.py` `_handle_order_fill` updates equity from payload's `unrealized_pnl` literal; no fee deduction.

## Mitigations proposed

- Move heavy paths to Rust (planned).
- Batch event dispatch.
- Cache latest price per symbol.
- Use `numpy` directly instead of `pd.Series` where shape matches.

## Risk

- Strategies that emit thousands of signals per bar will be CPU-bound on the engine, not the bus.

## Confidence

- High: hot path identification.
- Medium: actual numbers without load test.
