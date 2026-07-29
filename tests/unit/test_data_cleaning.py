from __future__ import annotations

from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from cryptobot.data.cleaning import DataCleaner, validate_ohlcv


def test_validate_ohlcv_handles_none_and_missing_columns():
    ok, issues = validate_ohlcv(None)
    assert ok is False
    assert any("empty" in i for i in issues)
    df = pd.DataFrame({"open": [1, 2], "high": [2, 3], "low": [0, 1], "close": [1.5, 2.5], "open_time": pd.to_datetime(["2024-01-01", "2024-01-02"])})
    ok, issues = validate_ohlcv(df)
    assert ok is True
    assert issues == []


def test_validate_ohlcv_flags_unparseable_time():
    df = pd.DataFrame({"open": [1], "high": [2], "low": [0], "close": [1], "open_time": ["notadate"]})
    ok, issues = validate_ohlcv(df)
    assert ok is False


def test_data_cleaner_clean_trades_drops_nonnumeric_and_negative():
    cleaner = DataCleaner()
    df = pd.DataFrame({
        "time": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"]),
        "price": [100.0, 0.0, -50.0, "garbage"],
        "quantity": [1.0, 2.0, 3.0, 4.0],
        "trade_id": ["t1", "t2", "t3", "t4"],
    })
    cleaned, report = cleaner.clean_trades(df, symbol="BTCUSDT")
    assert len(cleaned) == 1
    assert report.issue_count > 0


def test_clean_klines_short_circuits_on_empty_df():
    cleaner = DataCleaner()
    df = pd.DataFrame(columns=["open_time"])
    cleaned, report = cleaner.clean_klines(df, symbol="X", timeframe="1m")
    assert len(cleaned) == 0
    assert report.total_rows == 0


def test_clean_klines_detects_missing_columns():
    cleaner = DataCleaner()
    df = pd.DataFrame({"open_time": pd.to_datetime(["2024-01-01"]), "open": [1.0]})
    cleaned, report = cleaner.clean_klines(df, symbol="X", timeframe="1m")
    assert any(v == "missing_columns" for v in report.details.values()) or report.issue_count > 0


def test_clean_tickers_handles_empty():
    cleaner = DataCleaner()
    df = pd.DataFrame(columns=["time"])
    cleaned, report = cleaner.clean_tickers(df, symbol="X")
    assert len(cleaned) == 0
    assert report.total_rows == 0


def test_clean_tickers_rejects_bid_above_ask():
    cleaner = DataCleaner()
    df = pd.DataFrame({"time": pd.to_datetime(["2024-01-01", "2024-01-02"]), "price": [100, 102], "bid": [99, 105], "ask": [101, 101]})
    cleaned, report = cleaner.clean_tickers(df, symbol="X")
    assert report.issue_count > 0
