# 07. Database Model

> **Last Updated**: 2026-07-29 (audit pass)
> **Confidence**: High for schema found in code; Low for SQL DDL files (none exist).

## What exists

- `src/cryptobot/core/state.py` defines SQLite tables inline.
- `src/cryptobot/data/storage.py` defines TimescaleDB and Parquet backends.
- No SQL migration files in `migrations/`.

## SQLite schema (from `core/state.py`)

```sql
CREATE TABLE IF NOT EXISTS orders (
  order_id TEXT PRIMARY KEY,
  client_order_id TEXT,
  symbol TEXT,
  side TEXT,
  type TEXT,
  quantity TEXT,
  price TEXT,
  stop_price TEXT,
  status TEXT,
  filled_quantity TEXT,
  avg_fill_price TEXT,
  commission TEXT,
  commission_asset TEXT,
  time_in_force TEXT,
  reduce_only INTEGER,
  position_side TEXT,
  strategy TEXT,
  created_at TEXT,
  updated_at TEXT
);

CREATE TABLE IF NOT EXISTS positions (
  symbol TEXT PRIMARY KEY,
  side TEXT,
  quantity TEXT,
  entry_price TEXT,
  mark_price TEXT,
  unrealized_pnl TEXT,
  realized_pnl TEXT,
  leverage INTEGER,
  margin_type TEXT,
  isolated_margin TEXT,
  liquidation_price TEXT,
  strategy TEXT,
  opened_at TEXT,
  updated_at TEXT
);

CREATE TABLE IF NOT EXISTS account_state (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  total_equity TEXT,
  available_balance TEXT,
  used_margin TEXT,
  total_unrealized_pnl TEXT,
  total_realized_pnl TEXT,
  daily_pnl TEXT,
  max_drawdown TEXT,
  peak_equity TEXT,
  updated_at TEXT
);

CREATE TABLE IF NOT EXISTS events (
  id TEXT PRIMARY KEY,
  type TEXT,
  timestamp TEXT,
  source TEXT,
  correlation_id TEXT,
  payload TEXT
);

CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(type);
```

All money/decimal values stored as `TEXT` to avoid SQLite dynamic typing.

## Fallback behavior

If `_sqlite3` is unavailable, `StateManager` does not call `_init_db()` and every `save_*` method early-returns. `load()` is also a no-op. State lives only in memory.

## TimescaleDB / Parquet (planned)

`src/cryptobot/data/storage.py` declares `TimescaleDBStorage` and `ParquetStorage` with async write/read methods. Neither is exercised by smoke tests. Code paths require `asyncpg` and `pyarrow`, both missing from the test image.

## Migrations

- `migrations/` directory exists but contains no files.
- `docker-compose.yml` mounts `./migrations` into `timescaledb` at `/docker-entrypoint-initdb.d`, so empty mounts do nothing.

## Parquet / TimescaleDB schema (sketched in code)

`storage.py` writes row-shaped dicts:
- `write_klines(klines: List[Dict])`
- `write_tickers(tickers: List[Dict])`
- `write_trades(trades: List[Dict])`
- `write_funding_rates(rates: List[Dict])`

The exact column names are not enforced; consumption is JSON dict. No schema validation.

## Confidence

- High: SQLite path.
- Medium: Parquet path (no test coverage).
- Low: TimescaleDB path (no connectivity, no tests).
