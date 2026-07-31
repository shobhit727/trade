# 21. Risk Assessment

> **Last Updated**: 2026-07-31 (audit v2)
> **Confidence**: Medium.

## Operational

- **R1**: Docker daemon instability on some hosts (QEMU aborts reported historically; not always reproducible). Mitigate by relying on CI rather than local Docker Desktop for release builds.
- **R2**: `_sqlite3` may be missing in interpreter. Persistence silently no-ops with a `logging.warning` (B024). State lost on restart.
- **R3**: ~~`configs/base.yaml` is ignored by `Settings`~~ — **resolved** via `_flatten_yaml` + `from_yaml_safe` (B050). Mapped keys still pass through correctly.
- **R4**: TimescaleDB + Redis services in compose require ports 5432/6379 free. Localhost conflicts possible.

## Code

- **R5**: ~~`backtest/validation.py` returns fabricated pass results~~ — **resolved**: real walk-forward + Monte Carlo block permutation + deflated Sharpe (B033; current `validation.py`).
- **R6**: ~~`monitoring/metrics.py` Prometheus `Counter` cannot accept negative PnL~~ — **resolved**: `total_pnl` is now `Gauge` (B025/B037).
- **R7**: `core/clock.py` `SimulatedClock` lacks lock around `pause`/`resume`. Race possible — not yet exercised by tests.
- **R8**: ~~`execution/venue/binance.py` absent~~ — **resolved**: `BinanceVenue` via `ccxt.async_support` with sandbox/retries/credential guards (current `binance.py`).
- **R9**: ~~`crates/` empty / non-buildable.~~ **Resolved 2026-07-31**: workspace `members` trimmed to `["crates/cryptobot-core"]`; 6 empty sibling crates deleted; `cryptobot-core` has `lib.rs` stub + passing unit test; `cargo build` + `cargo test` clean.
- **R10**: ~~`risk/manager.py` uses `Decimal("0")` fallback when no price set~~ — **resolved**: notional check skipped when no valid price (B038, B060, B061 fetches market price pre-check).
- **R11**: ~~`utils/decorators.py` jitter can produce negative sleep~~ — **resolved**: clamped to `max(0.0, sleep_time)` (B027).
- **R12**: ~~`utils/decorators.py` `circuit_breaker` sync wrapper breaks in async context~~ — **resolved**: raises `RuntimeError` in running loop (B028).
- **R13**: `monitoring/__init__.py` eagerly imports `cryptobot.monitoring.metrics` — B051 still Open. Document for consumers; consider lazy re-exports.

## Business

- **R14**: Trading real money depends on `risk/manager.py` checks. Bypass is catastrophic.
- **R15**: ~~Daily kill switch reset relies on external cron~~ — **resolved**: `core/portfolio.py update_equity` auto-detects UTC day boundary and resets `_daily_pnl_start` (B034).
- **R16**: ~~`BacktestEngine._handle_order_fill` does not subtract fees; reported equity is optimistic~~ — **resolved**: trade `pnl` is net of fees; `pnl_pct` from net. Manual equity double-count removed (B032, B063).

## Mitigations

- M1: Tests that fail if `ExecutionEngine` lets over-limit orders through.
- M2: `pyproject.toml` for reproducible packaging — done.
- M3: `seccomp` profiles and `read_only` root filesystem — `seccomp/` dir exists but empty; consider populated profiles.
- M4: Real walk-forward + Monte Carlo — done.
- M5: Wire `StrategyRegistry` to `core/portfolio.py` so unregistered strategies cannot operate — partially done via `load_strategies_from_config` (B057/B059).

## Confidence

- High on risks R1, R4, R7, R9, R13, R14.
- Medium on R2.
- All previously-listed high risks (R3, R5, R6, R8, R10, R11, R12, R15, R16) are now resolved.
