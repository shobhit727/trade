# 17. Performance

> **Last Updated**: 2026-08-04 (5M-bar backtest ~30s, vectorized synthetic gen)
> **Confidence**: Medium.

## Verified

- `core/bus.py` `EventBus.publish` uses `asyncio.Lock` around history/dispatch. `publish_batch` dispatches atomically (B045).
- `core/clock.py` `SimulatedClock` wakeups via `asyncio.Event` cleared on `pause`.
- `backtest/engine.py` recomputes equity curve per fill; manual unrealized-PnL equity add removed (B063).
- `data/cleaning.py` uses pandas/numpy.
- `risk/sizing.py` size calculations are O(1).
- `market_data.manager.BinanceWSClient` reuses one `aiohttp.ClientSession` per start; `BinanceDataIngestion` shares a session via `_ensure_session()` (B042).
- `backtest/runner.py` `run_bars` fast path runs the backtest loop without per-bar event bus dispatch.

## Measured (2026-08-04)

- 5M-bar synthetic backtest (generation + simulation): **~30s total** (was ~13 min before vectorization).
- Synthetic OHLCV generation: **~12s**; fully vectorized numpy (AR loop 17s → ~1.5s).
- Simulation: **~21s**.
- Strategy feed loop **~1.6x faster** via O(1) streaming indicators.
- `run_bars` avoids per-bar events entirely.

## Hot paths

- `EventBus._dispatch` — locked per call. Each subscriber invoked in sequence.
- `BacktestEngine._handle_order_fill` — per fill: position update, equity, pnl, trade record. Equity update uses portfolio-tracked equity (B063). Entry-price zero guarded (B064).
- `DataCleaner.clean_klines` — vectorized ops; OHLC mask via boolean DataFrame.
- `risk.manager.RiskManager.check_order` — O(1); notional check skipped when no price available (B038/B060).

## Mitigations proposed

- Move heavy paths to Rust (workspace buildable today; pyo3 0.29 bindings in place).
- Batch event dispatch (current `publish_batch` is atomic but per-event sequential).
- Cache latest price per symbol.
- Use `numpy` directly instead of `pd.Series` where shape matches.

## Risk

- Strategies that emit thousands of signals per bar will be CPU-bound on the engine, not the bus.

## Confidence

- High: hot path identification.
- Medium: actual numbers without load test.
