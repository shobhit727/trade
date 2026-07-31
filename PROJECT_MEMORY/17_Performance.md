# 17. Performance

> **Last Updated**: 2026-07-31 (audit v2)
> **Confidence**: Medium.

## Verified

- `core/bus.py` `EventBus.publish` uses `asyncio.Lock` around history/dispatch. `publish_batch` dispatches atomically (B045).
- `core/clock.py` `SimulatedClock` wakeups via `asyncio.Event` cleared on `pause`.
- `backtest/engine.py` recomputes equity curve per fill; manual unrealized-PnL equity add removed (B063).
- `data/cleaning.py` uses pandas/numpy.
- `risk/sizing.py` size calculations are O(1).
- `market_data.manager.BinanceWSClient` reuses one `aiohttp.ClientSession` per start; `BinanceDataIngestion` shares a session via `_ensure_session()` (B042).

## Hot paths

- `EventBus._dispatch` — locked per call. Each subscriber invoked in sequence.
- `BacktestEngine._handle_order_fill` — per fill: position update, equity, pnl, trade record. Equity update uses portfolio-tracked equity (B063). Entry-price zero guarded (B064).
- `DataCleaner.clean_klines` — vectorized ops; OHLC mask via boolean DataFrame.
- `risk.manager.RiskManager.check_order` — O(1); notional check skipped when no price available (B038/B060).

## Mitigations proposed

- Move heavy paths to Rust (still pending; workspace non-buildable today).
- Batch event dispatch (current `publish_batch` is atomic but per-event sequential).
- Cache latest price per symbol.
- Use `numpy` directly instead of `pd.Series` where shape matches.

## Risk

- Strategies that emit thousands of signals per bar will be CPU-bound on the engine, not the bus.

## Confidence

- High: hot path identification.
- Medium: actual numbers without load test.
