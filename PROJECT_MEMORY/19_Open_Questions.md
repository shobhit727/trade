# 19. Open Questions

> **Last Updated**: 2026-07-31 (audit v2)
> **Confidence**: High.

## Blocking

1. Does `requirements/prod.txt` install cleanly on Python 3.14 inside Docker? Earlier pins were already broken (`monero-rpc` removed). Need fresh end-to-end image build.
2. Does `monitoring/metrics.py` import work without `prometheus_client`? Code uses `from prometheus_client import Counter, Gauge, Histogram, Info` at module level — fails fast if missing.
3. Does `monitoring/alerting.py` work without optional channels? `init_alerting()` no-ops when no channels configured (B031); should remain import-safe.
4. Does `data/ingestion.py` import without `aiohttp`? `import aiohttp` is at module level. Will fail.
5. Does `data/storage.py` import without `asyncpg` and `pyarrow`? `asyncpg` and `pyarrow` are imported lazily inside `TimescaleDBStorage` / `ParquetStorage` constructors in current source — module-level import is clean.

## Architectural

6. How are strategies loaded in production? `StrategyRegistry.register` overwrites duplicates silently. `load_strategies_from_config` (B059) is the documented path: read `configs/base.yaml` `strategies` block, instantiate enabled ones via `_STRATEGY_REGISTRY_MAP`.
7. Should `RiskManager` be a singleton or per-strategy? Today global. Unchanged.
8. What populates `data_stream` for `BacktestEngine.run`? Caller-supplied; `backtest.runner.run_backtest` provides OHLCV→strategy→venue wiring. `backtest.data.load_csv/parquet/timescale/synthetic` are the canonical sources.
9. What is the full event flow for trading decisions end-to-end? See `04_Data_Flow.md`.
10. Does `Settings` deliberately allow `extra="ignore"`? Yes; safety net behind `_flatten_yaml` + `from_yaml_safe`.
11. What's the kill switch reset schedule? Handled inline by `core.portfolio.update_equity` auto-resetting `_daily_pnl_start` on UTC day boundary (B034); no scheduler needed.

## Operational

12. How does `cryptobot` service's `8080/health` HTTP endpoint get built? `cli serve` starts `utils.health_server.HealthServer` (stdlib `ThreadingHTTPServer`); Dockerfile `HEALTHCHECK` hits it.
13. Does live mode actually connect to Binance? `execution/venue/binance.py` (`BinanceVenue`) supports it via `ccxt.async_support` with sandbox/credentials configured via env. Needs real or testnet keys to actually run.
14. Does `cargo build` work? ✅ Yes — resolved 2026-08-04: workspace fleshed out to 7 real crates (core/features/risk/stats/orderbook/backtest/py) with PyO3 0.29. `cargo build` + `cargo test` green; fmt/clippy clean in CI. (Supersedes the earlier trim-to-1-crate workaround.)

## Confidence

- High: questions above are open by inspection.
- Medium: each will shrink as code is filled in.
