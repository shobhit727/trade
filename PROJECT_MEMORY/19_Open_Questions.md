# 19. Open Questions

> **Last Updated**: 2026-07-29 (audit pass)
> **Confidence**: High.

## Blocking

1. Will `requirements/prod.txt` install cleanly on Python 3.14 inside Docker? Earlier pins were already broken.
2. Does `monitoring/metrics.py` import work without `prometheus_client`? Unknown — code uses `from prometheus_client import Counter, Gauge, Histogram, Info` at module level.
3. Does `monitoring/alerting.py` work without optional channels? Code makes env reads; should be import-safe.
4. Does `data/ingestion.py` import without `aiohttp`? `import aiohttp` is at module level. Will fail.
5. Does `data/storage.py` import without `asyncpg` and `pyarrow`? Yes.

## Architectural

6. How are strategies loaded in production? `StrategyRegistry.register` overwrites duplicates silently.
7. Should `RiskManager` be a singleton or per-strategy? Today global.
8. What populates `data_stream` for `BacktestEngine.run`? Currently caller-supplied.
9. What is the full event flow for trading decisions end-to-end? Larger picture undocumented.
10. Does `Settings` deliberately allow `extra="ignore"`? Yes. Trade-off: silent YAML drift.
11. What's the kill switch reset schedule? `reset_daily_pnl` exists; no scheduler.

## Operational

12. How does `cryptobot` service's `8080/health` HTTP endpoint get built? No HTTP handler in source.
13. What is the cron for `reset_daily_pnl`? Not visible.
14. Does live mode actually connect to Binance? Requires `execution/venue/binance.py` (missing).

## Confidence

- High: questions above are open by inspection.
- Medium: each will shrink as code is filled in.
