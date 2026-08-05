from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from cryptobot.backtest.data import (
    OhlcvDataset,
    _freq_to_minutes,
    _freq_to_seconds,
    load_bars,
    load_csv,
    load_timescale,
)


def _write_csv(path: Path, rows) -> None:
    path.write_text(
        "timestamp,open,high,low,close,volume\n"
        + "\n".join(",".join(map(str, r)) for r in rows)
    )


def test_freq_to_minutes_known():
    assert _freq_to_minutes("15m") == 15
    assert _freq_to_minutes("1h") == 60
    assert _freq_to_minutes("1d") == 1440
    assert _freq_to_minutes("xxx") == 15


def test_freq_to_seconds_subsecond():
    assert _freq_to_seconds("100ms") == 0.1
    assert _freq_to_seconds("500ms") == 0.5
    assert _freq_to_seconds("1s") == 1.0
    assert _freq_to_seconds("5s") == 5.0
    assert _freq_to_seconds("30s") == 30.0
    assert _freq_to_seconds("1h") is None
    assert _freq_to_seconds("15m") is None


def test_load_bars_synthetic_subsecond_timestamps():
    ds = load_bars(source="synthetic", timeframe="100ms", n_bars=50)
    assert len(ds) == 50
    deltas = [(ds.bars[i + 1].timestamp - ds.bars[i].timestamp) for i in range(5)]
    assert all(d == timedelta(milliseconds=100) for d in deltas)
    assert ds.bars[0].timestamp.microsecond in (0, 100000)


def test_load_csv_reads_and_sorts(tmp_path: Path):
    p = tmp_path / "bars.csv"
    base = datetime(2024, 1, 1, 0, 0, 0)
    rows = []
    for i in range(5):
        ts = base + timedelta(minutes=15 * (4 - i))
        rows.append((ts.isoformat(), 100 + i, 101 + i, 99 + i, 100 + i, 50))
    _write_csv(p, rows)

    ds = load_csv(p, symbol="ETHUSDT")
    assert len(ds) == 5
    assert ds.symbol == "ETHUSDT"
    assert ds.source.startswith("csv:")
    timestamps = [b.timestamp for b in ds.bars]
    assert timestamps == sorted(timestamps)


def test_load_csv_handles_missing_columns(tmp_path: Path):
    p = tmp_path / "bad.csv"
    p.write_text("timestamp,open\n2024-01-01T00:00:00,100\n")
    ds = load_csv(p)
    assert len(ds) == 0


def test_load_csv_missing_file_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_csv(tmp_path / "nope.csv")


def test_filter_range_bounds(tmp_path: Path):
    p = tmp_path / "bars.csv"
    base = datetime(2024, 1, 1)
    rows = [(base + timedelta(hours=i), 100, 101, 99, 100, 1) for i in range(0, 24, 4)]
    _write_csv(p, rows)
    ds = load_csv(p)
    cut = base + timedelta(hours=12)
    sliced = ds.filter_range(start=cut, end=base + timedelta(hours=20))
    assert all(cut <= b.timestamp <= base + timedelta(hours=20) for b in sliced)


def test_load_bars_synthetic_source(tmp_path: Path):
    ds = load_bars(source="synthetic", symbol="BTCUSDT", timeframe="1h")
    assert ds.source == "synthetic"
    assert len(ds.bars) >= 1


def test_load_bars_csv_source_uses_path(tmp_path: Path):
    p = tmp_path / "bars.csv"
    base = datetime(2024, 1, 1)
    rows = [(base.isoformat(), 100, 101, 99, 100, 1)]
    _write_csv(p, rows)
    ds = load_bars(source="csv", path=p, symbol="BTCUSDT")
    assert len(ds) == 1


def test_load_bars_unknown_source_raises():
    with pytest.raises(ValueError):
        load_bars(source="nope")


def test_load_bars_csv_without_path_raises():
    with pytest.raises(ValueError):
        load_bars(source="csv", path=None)


@pytest.mark.asyncio
async def test_load_timescale_returns_dataset():
    ds = await load_timescale(symbol="BTCUSDT")
    assert isinstance(ds, OhlcvDataset)
    assert ds.symbol == "BTCUSDT"
