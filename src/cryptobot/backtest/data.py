from __future__ import annotations

import csv
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from cryptobot.backtest.runner import OhlcvBar

logger = logging.getLogger(__name__)


REQUIRED_COLUMNS = ("timestamp", "open", "high", "low", "close")


@dataclass
class OhlcvDataset:
    """Container for historical OHLCV bars."""

    bars: list[OhlcvBar] = field(default_factory=list)
    symbol: str = "BTCUSDT"
    source: str = "memory"

    def __len__(self) -> int:
        return len(self.bars)

    def __iter__(self):
        return iter(self.bars)

    @property
    def close(self) -> np.ndarray:
        return np.array([bar.close for bar in self.bars], dtype=np.float64)

    @property
    def high(self) -> np.ndarray:
        return np.array([bar.high for bar in self.bars], dtype=np.float64)

    @property
    def low(self) -> np.ndarray:
        return np.array([bar.low for bar in self.bars], dtype=np.float64)

    @property
    def volume(self) -> np.ndarray:
        return np.array([bar.volume for bar in self.bars], dtype=np.float64)

    @property
    def timestamps(self) -> np.ndarray:
        return np.array([bar.timestamp for bar in self.bars], dtype=np.datetime64)

    def filter_range(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> OhlcvDataset:
        out: list[OhlcvBar] = []
        for bar in self.bars:
            if start is not None and bar.timestamp < start:
                continue
            if end is not None and bar.timestamp > end:
                continue
            out.append(bar)
        return OhlcvDataset(bars=out, symbol=self.symbol, source=self.source)

    def to_runner_bars(self) -> list[OhlcvBar]:
        return list(self.bars)


def _row_to_bar(row: dict[str, Any], default_symbol: str) -> OhlcvBar:
    ts_raw = row.get("timestamp") or row.get("open_time") or row.get("time") or row.get("datetime")
    if isinstance(ts_raw, str):
        ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
    elif isinstance(ts_raw, int | float):
        ts = datetime.utcfromtimestamp(float(ts_raw))
    elif isinstance(ts_raw, datetime):
        ts = ts_raw
    else:
        raise ValueError(f"unsupported timestamp value: {ts_raw!r}")
    o = row.get("open", row.get("open_price"))
    h = row.get("high", row.get("high_price"))
    low_val = row.get("low", row.get("low_price"))
    c = row.get("close", row.get("close_price"))
    if o is None or h is None or low_val is None or c is None:
        raise KeyError("missing required ohlc column")
    return OhlcvBar(
        timestamp=ts,
        open=float(o),
        high=float(h),
        low=float(low_val),
        close=float(c),
        volume=float(row.get("volume", row.get("vol", 0.0))),
    )


def load_csv(path: str | Path, symbol: str = "BTCUSDT") -> OhlcvDataset:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(p)
    bars: list[OhlcvBar] = []
    with p.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                bars.append(_row_to_bar(row, symbol))
            except (KeyError, ValueError) as exc:
                logger.debug("skipping bad row in %s: %s", p, exc)
    bars.sort(key=lambda b: b.timestamp)
    return OhlcvDataset(bars=bars, symbol=symbol, source=f"csv:{p}")


def load_parquet(
    path: str | Path,
    symbol: str = "BTCUSDT",
    start: datetime | None = None,
    end: datetime | None = None,
) -> OhlcvDataset:
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError("pyarrow required for Parquet support: pip install pyarrow") from exc

    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(p)
    table = pq.read_table(str(p))
    df = table.to_pandas()
    if df.empty:
        return OhlcvDataset(bars=[], symbol=symbol, source=f"parquet:{p}")
    rename = {
        "open_price": "open",
        "high_price": "high",
        "low_price": "low",
        "close_price": "close",
        "open_time": "timestamp",
        "time": "timestamp",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
    for col in REQUIRED_COLUMNS:
        if col not in df.columns:
            raise ValueError(f"parquet missing required column: {col}")
    bars: list[OhlcvBar] = []
    for _, row in df.iterrows():
        row_d = row.to_dict()
        try:
            bars.append(_row_to_bar(row_d, symbol))
        except (KeyError, ValueError) as exc:
            logger.debug("skipping bad row in %s: %s", p, exc)
    bars.sort(key=lambda b: b.timestamp)
    ds = OhlcvDataset(bars=bars, symbol=symbol, source=f"parquet:{p}")
    return ds.filter_range(start=start, end=end)


async def load_timescale(
    symbol: str = "BTCUSDT",
    timeframe: str = "15m",
    start: datetime | None = None,
    end: datetime | None = None,
    settings: Any = None,
) -> OhlcvDataset:
    """Async loader backed by TimescaleDB via the project's storage layer.

    Falls back to an empty dataset when storage is not configured/available.
    """
    try:
        from cryptobot.data.storage import init_storage  # type: ignore
    except Exception as exc:
        logger.debug("timescale loader unavailable: %s", exc)
        return OhlcvDataset(bars=[], symbol=symbol, source="timescale")

    end = end or datetime.utcnow()
    start = start or (end - timedelta(days=30))
    try:
        store = init_storage(settings or _default_settings())
        df = await store.read_klines(symbol, timeframe, start, end)
    except Exception as exc:
        logger.debug("timescale loader error: %s", exc)
        return OhlcvDataset(bars=[], symbol=symbol, source="timescale")

    bars: list[OhlcvBar] = []
    if df is None or df.empty:
        return OhlcvDataset(bars=bars, symbol=symbol, source="timescale")
    for _, row in df.iterrows():
        try:
            bars.append(_row_to_bar(row.to_dict(), symbol))
        except (KeyError, ValueError) as exc:
            logger.debug("skipping bad row: %s", exc)
    bars.sort(key=lambda b: b.timestamp)
    return OhlcvDataset(bars=bars, symbol=symbol, source="timescale")


def _default_settings():
    try:
        from cryptobot.config import settings
    except Exception:
        return None
    return settings


def load_bars(
    source: str,
    path: str | Path | None = None,
    symbol: str = "BTCUSDT",
    start: datetime | None = None,
    end: datetime | None = None,
    timeframe: str = "15m",
    n_bars: int | None = None,
) -> OhlcvDataset:
    s = source.lower()
    if s == "csv":
        if path is None:
            raise ValueError("csv source requires --path")
        return load_csv(path, symbol=symbol).filter_range(start=start, end=end)
    if s == "parquet":
        if path is None:
            raise ValueError("parquet source requires --path")
        return load_parquet(path, symbol=symbol, start=start, end=end)
    if s == "synthetic":
        from cryptobot.backtest.runner import generate_synthetic_ohlcv
        bars = generate_synthetic_ohlcv(
            start or datetime(2024, 1, 1),
            n_bars=n_bars or 200,
            freq_minutes=_freq_to_minutes(timeframe),
            seed=42,
        )
        return OhlcvDataset(bars=bars, symbol=symbol, source="synthetic").filter_range(start=start, end=end)
    raise ValueError(f"unknown source: {source}")


def _freq_to_minutes(tf: str) -> int:
    mapping = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "4h": 240, "1d": 1440}
    return mapping.get(tf, 15)


__all__ = [
    "OhlcvDataset",
    "load_bars",
    "load_csv",
    "load_parquet",
    "load_timescale",
]
