from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd

if TYPE_CHECKING:
    import asyncpg

from cryptobot.config import settings


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class StorageConfig:
    """Storage configuration."""
    # TimescaleDB
    timescaledb_host: str = "timescaledb"
    timescaledb_port: int = 5432
    timescaledb_name: str = "cryptobot"
    timescaledb_user: str = "cryptobot"
    timescaledb_password: str = ""
    timescaledb_pool_size: int = 10

    # Parquet (local/remote)
    parquet_base_path: str = "/app/data/parquet"
    parquet_compression: str = "zstd"
    parquet_partition_cols: list[str] = field(default_factory=lambda: ["symbol", "year", "month"])

    # General
    batch_size: int = 1000
    flush_interval_seconds: int = 5


class StorageBackend(ABC):
    """Abstract storage backend."""

    @abstractmethod
    async def initialize(self):
        pass

    @abstractmethod
    async def close(self):
        pass

    @abstractmethod
    async def write_klines(self, klines: list[dict]) -> int:
        pass

    @abstractmethod
    async def write_tickers(self, tickers: list[dict]) -> int:
        pass

    @abstractmethod
    async def write_trades(self, trades: list[dict]) -> int:
        pass

    @abstractmethod
    async def write_funding_rates(self, rates: list[dict]) -> int:
        pass

    @abstractmethod
    async def read_klines(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        pass

    @abstractmethod
    async def read_tickers(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        pass


class TimescaleDBStorage(StorageBackend):
    """TimescaleDB storage for time-series data."""

    def __init__(self, config: StorageConfig):
        self.config = config
        self.pool: asyncpg.Pool | None = None

    async def initialize(self):
        import asyncpg
        self.pool = await asyncpg.create_pool(
            host=self.config.timescaledb_host,
            port=self.config.timescaledb_port,
            database=self.config.timescaledb_name,
            user=self.config.timescaledb_user,
            password=self.config.timescaledb_password,
            min_size=2,
            max_size=self.config.timescaledb_pool_size,
        )
        await self._create_tables()

    async def close(self):
        if self.pool:
            await self.pool.close()

    async def _create_tables(self):
        """Create hypertables and indexes."""
        async with self.pool.acquire() as conn:
            # Klines hypertable
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS klines (
                    time TIMESTAMPTZ NOT NULL,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    open_price NUMERIC(20,8) NOT NULL,
                    high_price NUMERIC(20,8) NOT NULL,
                    low_price NUMERIC(20,8) NOT NULL,
                    close_price NUMERIC(20,8) NOT NULL,
                    volume NUMERIC(30,8) NOT NULL,
                    trades INTEGER NOT NULL,
                    is_closed BOOLEAN NOT NULL DEFAULT TRUE,
                    PRIMARY KEY (time, symbol, timeframe)
                );
            """)
            await conn.execute("""
                SELECT create_hypertable('klines', 'time', if_not_exists => TRUE);
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_klines_symbol_timeframe_time
                ON klines (symbol, timeframe, time DESC);
            """)

            # Tickers hypertable
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS tickers (
                    time TIMESTAMPTZ NOT NULL,
                    symbol TEXT NOT NULL,
                    price NUMERIC(20,8) NOT NULL,
                    bid NUMERIC(20,8),
                    ask NUMERIC(20,8),
                    bid_qty NUMERIC(30,8),
                    ask_qty NUMERIC(30,8),
                    high_24h NUMERIC(20,8),
                    low_24h NUMERIC(20,8),
                    volume_24h NUMERIC(30,8),
                    change_24h NUMERIC(10,4),
                    PRIMARY KEY (time, symbol)
                );
            """)
            await conn.execute("""
                SELECT create_hypertable('tickers', 'time', if_not_exists => TRUE);
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_tickers_symbol_time
                ON tickers (symbol, time DESC);
            """)

            # Trades hypertable
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    time TIMESTAMPTZ NOT NULL,
                    symbol TEXT NOT NULL,
                    trade_id TEXT NOT NULL,
                    price NUMERIC(20,8) NOT NULL,
                    quantity NUMERIC(30,8) NOT NULL,
                    side TEXT NOT NULL,
                    is_maker BOOLEAN NOT NULL,
                    PRIMARY KEY (time, symbol, trade_id)
                );
            """)
            await conn.execute("""
                SELECT create_hypertable('trades', 'time', if_not_exists => TRUE);
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_trades_symbol_time
                ON trades (symbol, time DESC);
            """)

            # Funding rates hypertable
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS funding_rates (
                    time TIMESTAMPTZ NOT NULL,
                    symbol TEXT NOT NULL,
                    funding_rate NUMERIC(10,8) NOT NULL,
                    mark_price NUMERIC(20,8) NOT NULL,
                    index_price NUMERIC(20,8) NOT NULL,
                    next_funding_time TIMESTAMPTZ NOT NULL,
                    PRIMARY KEY (time, symbol)
                );
            """)
            await conn.execute("""
                SELECT create_hypertable('funding_rates', 'time', if_not_exists => TRUE);
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_funding_symbol_time
                ON funding_rates (symbol, time DESC);
            """)

    async def _execute_batch(self, query: str, records: list[tuple]):
        async with self.pool.acquire() as conn:
            await conn.executemany(query, records)

    async def write_klines(self, klines: list[dict]) -> int:
        if not klines:
            return 0
        query = """
            INSERT INTO klines (time, symbol, timeframe, open_price, high_price, low_price,
                               close_price, volume, trades, is_closed)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            ON CONFLICT (time, symbol, timeframe) DO UPDATE SET
                open_price = EXCLUDED.open_price,
                high_price = EXCLUDED.high_price,
                low_price = EXCLUDED.low_price,
                close_price = EXCLUDED.close_price,
                volume = EXCLUDED.volume,
                trades = EXCLUDED.trades,
                is_closed = EXCLUDED.is_closed
        """
        records = [
            (
                k["open_time"], k["symbol"], k["interval"],
                str(k["open_price"]), str(k["high_price"]), str(k["low_price"]),
                str(k["close_price"]), str(k["volume"]), k["trades"], k.get("is_closed", True)
            )
            for k in klines
        ]
        await self._execute_batch(query, records)
        return len(records)

    async def write_tickers(self, tickers: list[dict]) -> int:
        if not tickers:
            return 0
        query = """
            INSERT INTO tickers (time, symbol, price, bid, ask, bid_qty, ask_qty,
                               high_24h, low_24h, volume_24h, change_24h)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            ON CONFLICT (time, symbol) DO UPDATE SET
                price = EXCLUDED.price,
                bid = EXCLUDED.bid,
                ask = EXCLUDED.ask,
                bid_qty = EXCLUDED.bid_qty,
                ask_qty = EXCLUDED.ask_qty,
                high_24h = EXCLUDED.high_24h,
                low_24h = EXCLUDED.low_24h,
                volume_24h = EXCLUDED.volume_24h,
                change_24h = EXCLUDED.change_24h
        """
        records = [
            (
                t.get("timestamp", _utcnow()), t["symbol"],
                str(t["price"]), str(t.get("bid", 0)), str(t.get("ask", 0)),
                str(t.get("bid_qty", 0)), str(t.get("ask_qty", 0)),
                str(t.get("high_24h", 0)), str(t.get("low_24h", 0)),
                str(t.get("volume_24h", 0)), t.get("change_24h", 0)
            )
            for t in tickers
        ]
        await self._execute_batch(query, records)
        return len(records)

    async def write_trades(self, trades: list[dict]) -> int:
        if not trades:
            return 0
        query = """
            INSERT INTO trades (time, symbol, trade_id, price, quantity, side, is_maker)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (time, symbol, trade_id) DO NOTHING
        """
        records = [
            (
                t.get("timestamp", _utcnow()), t["symbol"], t["trade_id"],
                str(t["price"]), str(t["quantity"]), t["side"], t.get("is_maker", False)
            )
            for t in trades
        ]
        await self._execute_batch(query, records)
        return len(records)

    async def write_funding_rates(self, rates: list[dict]) -> int:
        if not rates:
            return 0
        query = """
            INSERT INTO funding_rates (time, symbol, funding_rate, mark_price, index_price, next_funding_time)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (time, symbol) DO UPDATE SET
                funding_rate = EXCLUDED.funding_rate,
                mark_price = EXCLUDED.mark_price,
                index_price = EXCLUDED.index_price,
                next_funding_time = EXCLUDED.next_funding_time
        """
        records = [
            (
                r.get("timestamp", _utcnow()), r["symbol"],
                r["funding_rate"], str(r["mark_price"]), str(r["index_price"]),
                r["next_funding_time"]
            )
            for r in rates
        ]
        await self._execute_batch(query, records)
        return len(records)

    async def read_klines(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        query = """
            SELECT time as open_time, symbol, timeframe, open_price, high_price, low_price,
                   close_price, volume, trades, is_closed
            FROM klines
            WHERE symbol = $1 AND timeframe = $2 AND time >= $3 AND time <= $4
            ORDER BY time ASC
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, symbol, timeframe, start, end)
        return pd.DataFrame([dict(r) for r in rows])

    async def read_tickers(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        query = """
            SELECT time, symbol, price, bid, ask, bid_qty, ask_qty,
                   high_24h, low_24h, volume_24h, change_24h
            FROM tickers
            WHERE symbol = $1 AND time >= $2 AND time <= $3
            ORDER BY time ASC
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, symbol, start, end)
        return pd.DataFrame([dict(r) for r in rows])


class ParquetStorage(StorageBackend):
    """Parquet file storage (partitioned by symbol/time)."""

    def __init__(self, config: StorageConfig):
        self.config = config
        self._buffers: dict[str, list[dict]] = defaultdict(list)
        self._flush_tasks: dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()

    async def initialize(self):
        Path(self.config.parquet_base_path).mkdir(parents=True, exist_ok=True)

    async def close(self):
        await self.flush_all()

    def _get_table_path(self, data_type: str, symbol: str, dt: datetime) -> Path:
        """Get partitioned parquet path."""
        year = dt.strftime("%Y")
        month = dt.strftime("%m")
        path = Path(self.config.parquet_base_path) / data_type / symbol / year / month
        path.mkdir(parents=True, exist_ok=True)
        return path / f"{data_type}_{symbol}_{dt.strftime('%Y%m%d')}.parquet"

    async def _flush_buffer(self, data_type: str):
        """Flush buffer to parquet."""
        import pyarrow as pa
        import pyarrow.parquet as pq
        async with self._lock:
            if data_type not in self._buffers or not self._buffers[data_type]:
                return

            buffer = self._buffers[data_type]
            self._buffers[data_type] = []

        if not buffer:
            return

        df = pd.DataFrame(buffer)
        # Normalize columns before deriving the partition date so records are
        # bucketed under their actual timestamp, not the write time.
        if data_type == "klines" and "interval" in df.columns and "timeframe" not in df.columns:
            df = df.rename(columns={"interval": "timeframe"})
        if data_type in ("tickers", "trades") and "timestamp" in df.columns and "time" not in df.columns:
            df = df.rename(columns={"timestamp": "time"})

        df["date"] = pd.to_datetime(df.get("open_time", df.get("time", _utcnow())))
        df["year"] = df["date"].dt.year
        df["month"] = df["date"].dt.month

        # Partition by symbol, year, month
        for (symbol, year, month), group in df.groupby(["symbol", "year", "month"]):
            path = self._get_table_path(data_type, symbol, datetime(year, month, 1))

            # Append or create (with dedup to avoid duplicate rows on re-append)
            if path.exists():
                existing = pq.read_table(path)
                new_table = pa.Table.from_pandas(group.drop(columns=["date", "year", "month"]))
                combined = pa.concat_tables([existing, new_table])
                # Deduplicate on all columns to prevent duplicate rows
                combined = pa.Table.from_pandas(combined.to_pandas().drop_duplicates())
                pq.write_table(combined, path, compression=self.config.parquet_compression)
            else:
                table = pa.Table.from_pandas(group.drop(columns=["date", "year", "month"]))
                pq.write_table(table, path, compression=self.config.parquet_compression)

    def _buffer_data(self, data_type: str, records: list[dict]):
        self._buffers[data_type].extend(records)
        if len(self._buffers[data_type]) >= self.config.batch_size:
            if data_type not in self._flush_tasks or self._flush_tasks[data_type].done():
                self._flush_tasks[data_type] = asyncio.create_task(self._flush_buffer(data_type))

    async def write_klines(self, klines: list[dict]) -> int:
        self._buffer_data("klines", klines)
        return len(klines)

    async def write_tickers(self, tickers: list[dict]) -> int:
        self._buffer_data("tickers", tickers)
        return len(tickers)

    async def write_trades(self, trades: list[dict]) -> int:
        self._buffer_data("trades", trades)
        return len(trades)

    async def write_funding_rates(self, rates: list[dict]) -> int:
        self._buffer_data("funding_rates", rates)
        return len(rates)

    async def flush_all(self):
        for data_type in list(self._buffers.keys()):
            await self._flush_buffer(data_type)

    async def read_klines(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        import pyarrow.parquet as pq
        base = Path(self.config.parquet_base_path) / "klines" / symbol
        if not base.exists():
            return pd.DataFrame()

        all_dfs = []
        for year_dir in base.iterdir():
            if not year_dir.is_dir():
                continue
            year = int(year_dir.name)
            if year < start.year or year > end.year:
                continue
            for month_dir in year_dir.iterdir():
                if not month_dir.is_dir():
                    continue
                month = int(month_dir.name)
                if year == start.year and month < start.month:
                    continue
                if year == end.year and month > end.month:
                    continue

                for file in month_dir.glob("*.parquet"):
                    try:
                        df = pq.read_table(file).to_pandas()
                        df = df[(df["symbol"] == symbol) & (df["timeframe"] == timeframe)]
                        if not df.empty:
                            df["open_time"] = pd.to_datetime(df["open_time"])
                            df = df[(df["open_time"] >= start) & (df["open_time"] <= end)]
                            all_dfs.append(df)
                    except Exception:
                        continue

        if all_dfs:
            result = pd.concat(all_dfs).sort_values("open_time")
            return result.reset_index(drop=True)
        return pd.DataFrame()

    async def read_tickers(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        import pyarrow.parquet as pq
        base = Path(self.config.parquet_base_path) / "tickers" / symbol
        if not base.exists():
            return pd.DataFrame()

        all_dfs = []
        for year_dir in base.iterdir():
            if not year_dir.is_dir():
                continue
            year = int(year_dir.name)
            if year < start.year or year > end.year:
                continue
            for month_dir in year_dir.iterdir():
                if not month_dir.is_dir():
                    continue
                month = int(month_dir.name)
                if year == start.year and month < start.month:
                    continue
                if year == end.year and month > end.month:
                    continue

                for file in month_dir.glob("*.parquet"):
                    try:
                        df = pq.read_table(file).to_pandas()
                        df = df[df["symbol"] == symbol]
                        if not df.empty:
                            df["time"] = pd.to_datetime(df["time"])
                            df = df[(df["time"] >= start) & (df["time"] <= end)]
                            all_dfs.append(df)
                    except Exception:
                        continue

        if all_dfs:
            return pd.concat(all_dfs).sort_values("time").reset_index(drop=True)
        return pd.DataFrame()


TimescaleStorage = TimescaleDBStorage


class ParquetDataFrameStorage:
    """DataFrame-oriented Parquet storage (ohlcv + trades), partitioned by symbol/month."""

    def __init__(self, base_path: str = "/app/data/parquet", compression: str = "zstd"):
        self.base_path = Path(base_path)
        self.compression = compression
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _symbol_dir(self, kind: str, symbol: str) -> Path:
        p = self.base_path / kind / symbol.upper()
        p.mkdir(parents=True, exist_ok=True)
        return p

    def _bar_path(self, symbol: str, ts: Any) -> Path:
        d = self._symbol_dir("ohlcv", symbol)
        return d / f"{symbol.upper()}_{pd.Timestamp(ts).strftime('%Y%m')}.parquet"

    def _trades_path(self, symbol: str, ts: Any) -> Path:
        d = self._symbol_dir("trades", symbol)
        return d / f"{symbol.upper()}_{pd.Timestamp(ts).strftime('%Y%m')}.parquet"

    def store_ohlcv(self, df: pd.DataFrame) -> Path | None:
        if df is None or df.empty:
            return None
        if "symbol" not in df.columns:
            raise ValueError("DataFrame must have a 'symbol' column")
        ts_col = "open_time" if "open_time" in df.columns else df.columns[0]
        df = df.copy()
        df[ts_col] = pd.to_datetime(df[ts_col])
        written: list[Path] = []
        for symbol, group in df.groupby("symbol"):
            group = group.sort_values(ts_col)
            target = self._bar_path(str(symbol), group[ts_col].iloc[0])
            if target.exists():
                existing = pd.read_parquet(target)
                combined = pd.concat([existing, group], ignore_index=True)
                combined = combined.drop_duplicates(subset=[ts_col], keep="last").sort_values(ts_col)
                combined.to_parquet(target, compression=self.compression, index=False)
            else:
                group.to_parquet(target, compression=self.compression, index=False)
            written.append(target)
        return written[-1] if written else None

    def load_ohlcv(
        self,
        symbol: str,
        start: Any | None = None,
        end: Any | None = None,
        timeframe: str | None = None,
    ) -> pd.DataFrame:
        sym_dir = self._symbol_dir("ohlcv", symbol)
        files = sorted(sym_dir.glob("*.parquet"))
        if not files:
            return pd.DataFrame()
        frames = [pd.read_parquet(f) for f in files]
        df = pd.concat(frames, ignore_index=True)
        if "symbol" in df.columns:
            df = df[df["symbol"] == symbol.upper()]
        ts_col = "open_time" if "open_time" in df.columns else df.columns[0]
        df[ts_col] = pd.to_datetime(df[ts_col])
        if start is not None:
            df = df[df[ts_col] >= pd.Timestamp(start)]
        if end is not None:
            df = df[df[ts_col] <= pd.Timestamp(end)]
        if timeframe and "timeframe" in df.columns:
            df = df[df["timeframe"] == timeframe]
        return df.sort_values(ts_col).reset_index(drop=True)

    def store_trades(self, df: pd.DataFrame) -> Path | None:
        if df is None or df.empty:
            return None
        if "symbol" not in df.columns:
            raise ValueError("DataFrame must have a 'symbol' column")
        ts_col = "time" if "time" in df.columns else ("timestamp" if "timestamp" in df.columns else df.columns[0])
        df = df.copy()
        df[ts_col] = pd.to_datetime(df[ts_col])
        written: list[Path] = []
        for symbol, group in df.groupby("symbol"):
            group = group.sort_values(ts_col)
            target = self._trades_path(str(symbol), group[ts_col].iloc[0])
            if target.exists():
                existing = pd.read_parquet(target)
                combined = pd.concat([existing, group], ignore_index=True)
                if "trade_id" in combined.columns:
                    combined = combined.drop_duplicates(subset=["trade_id"], keep="last")
                combined = combined.sort_values(ts_col)
                combined.to_parquet(target, compression=self.compression, index=False)
            else:
                group.to_parquet(target, compression=self.compression, index=False)
            written.append(target)
        return written[-1] if written else None

    def load_trades(
        self,
        symbol: str,
        start: Any | None = None,
        end: Any | None = None,
    ) -> pd.DataFrame:
        sym_dir = self._symbol_dir("trades", symbol)
        files = sorted(sym_dir.glob("*.parquet"))
        if not files:
            return pd.DataFrame()
        df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
        if "symbol" in df.columns:
            df = df[df["symbol"] == symbol.upper()]
        ts_col = "time" if "time" in df.columns else ("timestamp" if "timestamp" in df.columns else df.columns[0])
        df[ts_col] = pd.to_datetime(df[ts_col])
        if start is not None:
            df = df[df[ts_col] >= pd.Timestamp(start)]
        if end is not None:
            df = df[df[ts_col] <= pd.Timestamp(end)]
        return df.sort_values(ts_col).reset_index(drop=True)


class HybridStorage(StorageBackend):
    """Hybrid storage: recent data in TimescaleDB, historical in Parquet."""

    def __init__(self, config: StorageConfig):
        self.config = config
        self.tsdb = TimescaleDBStorage(config)
        self.parquet = ParquetStorage(config)
        self._initialized = False

    async def initialize(self):
        await self.tsdb.initialize()
        await self.parquet.initialize()
        self._initialized = True

    async def close(self):
        await self.tsdb.close()
        await self.parquet.close()

    async def write_klines(self, klines: list[dict]) -> int:
        await self.tsdb.write_klines(klines)
        await self.parquet.write_klines(klines)
        return len(klines)

    async def write_tickers(self, tickers: list[dict]) -> int:
        await self.tsdb.write_tickers(tickers)
        await self.parquet.write_tickers(tickers)
        return len(tickers)

    async def write_trades(self, trades: list[dict]) -> int:
        await self.tsdb.write_trades(trades)
        await self.parquet.write_trades(trades)
        return len(trades)

    async def write_funding_rates(self, rates: list[dict]) -> int:
        await self.tsdb.write_funding_rates(rates)
        await self.parquet.write_funding_rates(rates)
        return len(rates)

    async def read_klines(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        # Recent data (last 30 days) from TimescaleDB, older from Parquet
        cutoff = _utcnow() - timedelta(days=30)
        if start >= cutoff:
            return await self.tsdb.read_klines(symbol, timeframe, start, end)
        elif end <= cutoff:
            return await self.parquet.read_klines(symbol, timeframe, start, end)
        else:
            # Split query
            recent = await self.tsdb.read_klines(symbol, timeframe, cutoff, end)
            historical = await self.parquet.read_klines(symbol, timeframe, start, cutoff)
            return pd.concat([historical, recent]).sort_values("open_time").reset_index(drop=True)

    async def read_tickers(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        cutoff = _utcnow() - timedelta(days=7)
        if start >= cutoff:
            return await self.tsdb.read_tickers(symbol, start, end)
        elif end <= cutoff:
            return await self.parquet.read_tickers(symbol, start, end)
        else:
            recent = await self.tsdb.read_tickers(symbol, cutoff, end)
            historical = await self.parquet.read_tickers(symbol, start, cutoff)
            return pd.concat([historical, recent]).sort_values("time").reset_index(drop=True)


# Global storage instance
_storage: HybridStorage | None = None


def get_storage(config: StorageConfig | None = None) -> HybridStorage:
    global _storage
    if _storage is None:
        if config is None:
            config = StorageConfig(
                timescaledb_host=settings.database.host,
                timescaledb_port=settings.database.port,
                timescaledb_name=settings.database.name,
                timescaledb_user=settings.database.user,
                timescaledb_password=settings.database.password or "",
                timescaledb_pool_size=settings.database.pool_size,
            )
        _storage = HybridStorage(config)
    return _storage


async def init_storage(config: StorageConfig | None = None) -> HybridStorage:
    storage = get_storage(config)
    await storage.initialize()
    return storage


async def shutdown_storage():
    global _storage
    if _storage:
        await _storage.close()
        _storage = None
