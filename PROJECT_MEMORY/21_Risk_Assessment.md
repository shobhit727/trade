# 21. Risk Assessment

> **Last Updated**: 2026-07-29 (audit pass)
> **Confidence**: Medium.

## Operational

- **R1**: Docker daemon instability on host. Blocks reproducible acceptance runs.
- **R2**: `_sqlite3` may be missing in interpreter. Persistence silently no-ops. State lost.
- **R3**: `configs/base.yaml` is ignored by `Settings` (extra keys dropped). Production deploys get defaults.
- **R4**: TimescaleDB + Redis services in compose require ports 5432/6379 free. Localhost conflicts possible.

## Code

- **R5**: `backtest/validation.py` returns fabricated pass results. Strategies appear "validated" but have no statistical evidence.
- **R6**: `monitoring/metrics.py` Prometheus `Counter` cannot accept negative PnL. Misuse raises.
- **R7**: `core/clock.py` `SimulatedClock` lacks lock around `pause`/`resume`. Race possible.
- **R8**: `execution/venue/binance.py` absent. Live trading impossible.
- **R9**: `crates/` empty. Rust perf math missing.
- **R10**: `risk/manager.py` uses `Decimal("0")` fallback when no price set → order rejected by min-size check.
- **R11**: `utils/decorators.py` jitter can produce negative sleep.
- **R12**: `utils/decorators.py` `circuit_breaker` sync wrapper breaks in async context.

## Business

- **R13**: Trading real money depends on `risk/manager.py` checks. Bypass is catastrophic.
- **R14**: Daily kill switch reset relies on external cron. Missed → state stale.
- **R15**: `BacktestEngine._handle_order_fill` does not subtract fees; reported equity is optimistic.

## Mitigations

- M1: Tests that fail if `ExecutionEngine` lets over-limit orders through.
- M2: `pyproject.toml` for reproducible packaging.
- M3: `seccomp` profiles and `read_only` root filesystem.
- M4: Real walk-forward + Monte Carlo.
- M5: Wire `StrategyRegistry` to `core/portfolio.py` so unregistered strategies cannot operate.

## Confidence

- High on R1, R3, R5, R8, R9, R10, R11, R12, R13, R14.
- Medium on R2, R4, R6, R7, R15.
