# 20. Assumptions

> **Last Updated**: 2026-07-29 (audit pass)
> **Confidence**: Working set, not facts.

## Active

- AS-1: Project targets Python 3.14. Verified by `Dockerfile`.
- AS-2: Strategies produce `OrderEvent` only. All live order routing must go through `ExecutionEngine`.
- AS-3: Pydantic v2 settings loaded lazily via `get_settings()`.
- AS-4: TimescaleDB for time-series, Parquet for local cold storage, SQLite for ephemeral state.
- AS-5: Backtest is the source of truth for validation before any live deployment.
- AS-6: `risk/manager.py` is the only authoritative pre-trade gate.
- AS-7: `core/portfolio.py` is the only authoritative equity/KPI source.
- AS-8: Tests run inside Docker (Python 3.14), not on host.

## Stale (drop)

- SA-1: "EventBus not implemented" → wrong.
- SA-2: "Clock not implemented" → wrong.
- SA-3: "Portfolio not implemented" → wrong.
- SA-4: "Data ingestion/storage/cleaning not implemented" → wrong.
- SA-5: "Monitoring not implemented" → wrong.
- SA-6: "Risk/Execution not implemented" → scaffolded this session.
- SA-7: "Production deps complete" → wrong; `monero-rpc` removed.

## To verify

- AV-1: `cryptobot` service's `8080/health` HTTP endpoint actually exists. No HTTP handler found.
- AV-2: `monitoring/metrics.py` import under no-Prometheus env.
- AV-3: `Settings` parser handles YAML `version: "1.0"` key quietly (verified — ignored).
- AV-4: `Settings` parser handles missing `xmr.daemon` group (verified — defaults).
- AV-5: `BinanceWSClient.start` works with empty `settings.exchange.symbols` (likely empty URL).
- AV-6: `BacktestEngine.run` accepts any `AsyncIterator[Event]` (used in tests).

## Confidence

- High: project facts.
- Medium: assumption set.
