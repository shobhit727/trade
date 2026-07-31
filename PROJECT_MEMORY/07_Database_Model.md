# 07. Database Model

> **Last Updated**: 2026-07-31 (audit v2)
> **Confidence**: High for SQLite + SQL migrations; Medium for TimescaleDB; Low for live behavior.

## What exists

- `src/cryptobot/core/state.py` defines SQLite tables inline; DB path resolves to `/app/data/cryptobot.db` when that mount exists (B069), else cwd.
- `src/cryptobot/data/storage.py` defines TimescaleDB and Parquet backends.
- `migrations/001_extension.sql` (TimescaleDB extension bootstrap) and `migrations/002_hypertables.sql` (hypertable DDL) are present.
- `docker-compose.yml` mounts `./migrations` into `timescaledb` at `/docker-entrypoint-initdb.d`.

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

If `_sqlite3` is unavailable, `StateManager` does not call `_init_db()` and emits `logging.warning`. Every `save_*` method early-returns. `load()` is also a no-op. State lives only in memory.

## TimescaleDB migrations (`migrations/`)

`001_extension.sql` enables `timescaledb` extension (placeholder; not verified against 2.x yet). `002_hypertables.sql` declares expected hypertable DDL for OHLCV / trades / funding rates / account snapshots. Verify columns match `data/storage.TimescaleDBStorage.write_*` before applying.

## TimescaleDB / Parquet (planned + partially implemented)

`src/cryptobot/data/storage.py` declares `TimescaleDBStorage`, `ParquetStorage`, and `HybridStorage` with async write/read methods. Code paths require `asyncpg` and `pyarrow`. Not exercised by smoke tests; integration tests pending.

## Parquet row shape (sketched in code)

`storage.py` writes row-shaped dicts:
- `write_klines(klines: List[Dict])`
- `write_tickers(tickers: List[Dict])`
- `write_trades(trades: List[Dict])`
- `write_funding_rates(rates: List[Dict])`

The exact column names are not enforced; consumption is JSON dict. No schema validation.

## Confidence

- High: SQLite path + SQL migrations.
- Medium: Parquet path (no test coverage in this env).
- Low: TimescaleDB path against live DB (no connectivity in audit env).
