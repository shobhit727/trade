# 09. External Dependencies

> **Last Updated**: 2026-07-31 (audit v2)
> **Confidence**: High (verified files).

## Production requirements (`requirements/prod.txt`)

Current `>=` lower bounds (verified 2026-07-31, post-B055 `lightgbm` removal):

```
pydantic>=2.10
pydantic-settings>=2.7
pyyaml>=6.0
python-dotenv>=1.0
aiohttp>=3.11
websockets>=14.0
redis>=5.2
ccxt>=4.4
pandas>=2.2
numpy>=2.2
scikit-learn>=1.6
joblib>=1.4
prometheus-client>=0.21
structlog>=24.4
click>=8.1
rich>=13.9
orjson>=3.10
requests>=2.32
pytest>=8.3
pytest-asyncio>=0.24
pytest-cov>=6.0
```

Removed: `monero-rpc==0.3.0` (no PyPI wheel for Python 3.11+, not used in source); `lightgbm>=4.5` (heavy native build, current `ml/models/direction.py` uses sklearn/numpy fallback only).

## Test requirements (`requirements/test.txt`)

```
pydantic>=2.10
pydantic-settings>=2.7
pyyaml>=6.0
python-dotenv>=1.0
structlog>=24.4
pytest>=8.3
pytest-asyncio>=0.24
```

Used by `docker compose --profile test run --rm cryptobot-test`.

## Optional vs required

| Package | Required for tests? | Required for app? |
|---------|---------------------|-------------------|
| `pydantic` | Yes | Yes |
| `pydantic-settings` | Yes | Yes |
| `pyyaml` | Yes | Yes |
| `python-dotenv` | Yes | Yes |
| `structlog` | Yes | Yes |
| `pytest` / `pytest-asyncio` | Yes | No |
| `prometheus-client` | No | Yes (monitoring) |
| `aiohttp` | No | Yes (market_data, data.ingestion) |
| `redis` | No | Yes (market_data) |
| `pandas` | No | Yes (data.cleaning, data.storage) |
| `numpy` | No | Yes (data.cleaning, backtest.metrics, ml) |
| `pyarrow` | No | Yes (data.storage parquet) |
| `asyncpg` | No | Yes (data.storage timescale) |
| `ccxt` | No | Yes (execution.venue.binance) |
| `scikit-learn` | No | Yes (ml.models.direction preferred path; numpy fallback also works) |

## Rust

- `Cargo.toml` (root): workspace with 1 member (`cryptobot-core`) + populated `[workspace.dependencies]`. `cargo build` + `cargo test` verified (rustup stable 1.97.1, 2026-07-31).
- `crates/cryptobot-core/src/lib.rs`: stub `pub fn placeholder() -> &'static str` + 1 unit test.
- `crates/cryptobot-core/src/{events,math,time,types}/`: empty subdirs preserved for future surface.
- `.cargo/config.toml`: per-target `rustflags = ["-C", "target-cpu=native"]` for x86_64 / aarch64 Linux.

## Docker base

- `python:3.14-slim` per `Dockerfile`.

## External services

- Binance public WS: default `wss://testnet.binance.vision`; fallback symbols from `settings.exchange.default_symbol` (B044).
- `ccxt.async_support` for Binance REST + WS in live/testnet mode (`execution/venue/binance.py`).
- TimescaleDB: compose service, port 5432; migrations mounted from `./migrations/`.
- Redis: compose service, port 6379 (used by `market_data.manager`).
- Prometheus: compose service, port 9090; scrape configs under `monitoring/prometheus/`.
- Grafana: compose service, port 3000; dashboards under `monitoring/grafana/` and `docker/grafana/dashboards/`.
- Alertmanager: compose service, port 9093; config under `monitoring/alertmanager/alertmanager.yml`.
- Loki: compose service, port 3100; config under `monitoring/loki/local-config.yaml` (scaffolded).
- Promtail: compose service; config under `monitoring/promtail/config.yml` (scaffolded).
- Nginx: compose service; config under `monitoring/nginx/nginx.conf` + `conf.d/` (scaffolded).

## Confidence

- High: `requirements/prod.txt`, `requirements/test.txt`, Dockerfile, compose services + monitoring subdirs.
- Low: cargo contents buildability (Rust layer not realizable without crate manifests).
