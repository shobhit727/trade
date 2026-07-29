# 09. External Dependencies

> **Last Updated**: 2026-07-29 (audit pass)
> **Confidence**: High (verified files).

## Production requirements (`requirements/prod.txt`)

Verified contents (current = `>=` lower bounds):

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
lightgbm>=4.5
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

Removed: `monero-rpc==0.3.0` (no PyPI wheel for Python 3.11+, not used in source).

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

Used by `docker compose --profile test`.

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
| `numpy` | No | Yes (data.cleaning, backtest.metrics) |
| `pyarrow` | No | Yes (data.storage) |
| `asyncpg` | No | Yes (data.storage) |
| `lightgbm` / `scikit-learn` | No | Future (ML) |
| `ccxt` | No | Future (live exchange) |

## Rust

- `Cargo.toml` (root): no `[dependencies]`, no `members`.
- `crates/cryptobot-core/Cargo.toml`: manifest only, no `src/`.

## Docker base

- `python:3.14-slim` per `Dockerfile`.

## External services

- Binance public WS: default `wss://testnet.binance.vision`.
- TimescaleDB: `docker-compose.yml` service, port 5432.
- Redis: `docker-compose.yml` service, port 6379.
- Prometheus: `docker-compose.yml` service, port 9090.
- Grafana: `docker-compose.yml` service, port 3000.
- Alertmanager: `docker-compose.yml` service, port 9093.
- Loki: `docker-compose.yml` service, port 3100.
- Promtail: `docker-compose.yml` service.

## Confidence

- High: `requirements/prod.txt`, `requirements/test.txt`, Dockerfile, compose services.
- Low: cargo contents (no crate members).
