from __future__ import annotations

import numpy as np
import pandas as pd
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum


class DataQualityIssue(str, Enum):
    MISSING_TIMESTAMPS = "missing_timestamps"
    DUPLICATE_TIMESTAMPS = "duplicate_timestamps"
    OUT_OF_ORDER = "out_of_order"
    PRICE_OUTLIER = "price_outlier"
    VOLUME_OUTLIER = "volume_outlier"
    ZERO_VOLUME = "zero_volume"
    NEGATIVE_PRICE = "negative_price"
    GAP_TOO_LARGE = "gap_too_large"
    MISSING_COLUMNS = "missing_columns"
    STALE_DATA = "stale_data"


@dataclass
class QualityReport:
    """Data quality assessment report."""
    symbol: str
    timeframe: str
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    total_rows: int = 0
    issues: Dict[DataQualityIssue, int] = None
    details: Dict[str, Any] = None

    def __post_init__(self):
        if self.issues is None:
            self.issues = {}
        if self.details is None:
            self.details = {}

    @property
    def is_clean(self) -> bool:
        return len(self.issues) == 0

    @property
    def issue_count(self) -> int:
        return sum(self.issues.values())

    def add_issue(self, issue: DataQualityIssue, count: int = 1, detail: str = ""):
        self.issues[issue] = self.issues.get(issue, 0) + count
        if detail:
            self.details[issue.value] = detail


class DataCleaner:
    """
    Comprehensive data cleaning and validation for market data.

    Handles:
    - Missing/duplicate timestamps
    - Price/volume outliers
    - Gap detection and filling
    - Cross-validation between data types
    """

    def __init__(
        self,
        max_price_deviation_pct: float = 0.10,  # 10% max single-bar move
        max_volume_zscore: float = 5.0,
        max_gap_multiplier: float = 3.0,  # 3x expected interval
        min_volume: float = 0.0,
    ):
        self.max_price_deviation_pct = max_price_deviation_pct
        self.max_volume_zscore = max_volume_zscore
        self.max_gap_multiplier = max_gap_multiplier
        self.min_volume = min_volume

    def clean_klines(self, df: pd.DataFrame, symbol: str, timeframe: str) -> Tuple[pd.DataFrame, QualityReport]:
        """Clean and validate kline data."""
        if df is None:
            df = pd.DataFrame()
        required = ["open_time", "close_time", "open_price", "high_price", "low_price", "close_price", "volume"]
        missing = [c for c in required if c not in df.columns]
        
        start_time = None
        end_time = None
        if not df.empty and "open_time" in df.columns:
            start_time = df["open_time"].min()
            end_time = df["open_time"].max()
        
        report = QualityReport(
            symbol=symbol,
            timeframe=timeframe,
            start=start_time,
            end=end_time,
            total_rows=len(df),
        )

        if df.empty:
            return df, report

        original_len = len(df)

        if missing:
            report.add_issue(DataQualityIssue.MISSING_COLUMNS, len(missing), f"Missing: {missing}")
            return df, report

        # Sort by time
        df = df.sort_values("open_time").reset_index(drop=True)

        # Remove duplicates (keep last)
        dup_mask = df.duplicated(subset=["open_time"], keep="last")
        if dup_mask.any():
            report.add_issue(DataQualityIssue.DUPLICATE_TIMESTAMPS, int(dup_mask.sum()))
            df = df[~dup_mask].reset_index(drop=True)

        # Check for gaps
        expected_interval = self._get_interval_timedelta(timeframe)
        if expected_interval:
            time_diffs = df["open_time"].diff().dt.total_seconds()
            expected_seconds = expected_interval.total_seconds()
            gap_mask = time_diffs > expected_seconds * self.max_gap_multiplier
            if gap_mask.any():
                gap_count = int(gap_mask.sum())
                max_gap = time_diffs[gap_mask].max()
                report.add_issue(DataQualityIssue.GAP_TOO_LARGE, gap_count,
                               f"Max gap: {max_gap/expected_seconds:.1f}x expected")

        # Validate OHLC relationships
        ohlc_invalid = (
            (df["high_price"] < df["low_price"]) |
            (df["high_price"] < df["open_price"]) |
            (df["high_price"] < df["close_price"]) |
            (df["low_price"] > df["open_price"]) |
            (df["low_price"] > df["close_price"])
        )
        if ohlc_invalid.any():
            report.add_issue(DataQualityIssue.PRICE_OUTLIER, int(ohlc_invalid.sum()), "Invalid OHLC relationships")
            df = df[~ohlc_invalid].reset_index(drop=True)

        # Negative or zero prices
        price_cols = ["open_price", "high_price", "low_price", "close_price"]
        for col in price_cols:
            invalid = df[col] <= 0
            if invalid.any():
                report.add_issue(DataQualityIssue.NEGATIVE_PRICE, int(invalid.sum()), f"Column: {col}")
                df = df[~invalid].reset_index(drop=True)

        # Price outlier detection (returns-based)
        returns = df["close_price"].pct_change()
        outlier_mask = returns.abs() > self.max_price_deviation_pct
        if outlier_mask.any():
            report.add_issue(DataQualityIssue.PRICE_OUTLIER, int(outlier_mask.sum()),
                           f"Returns > {self.max_price_deviation_pct:.1%}")

        # Volume validation
        zero_vol = df["volume"] <= self.min_volume
        if zero_vol.any():
            report.add_issue(DataQualityIssue.ZERO_VOLUME, int(zero_vol.sum()))

        # Volume outlier (z-score)
        if len(df) > 10:
            vol_mean = df["volume"].mean()
            vol_std = df["volume"].std()
            if vol_std > 0:
                vol_zscore = (df["volume"] - vol_mean) / vol_std
                vol_outlier = vol_zscore.abs() > self.max_volume_zscore
                if vol_outlier.any():
                    report.add_issue(DataQualityIssue.VOLUME_OUTLIER, int(vol_outlier.sum()))

        report.total_rows = len(df)
        report.details["rows_removed"] = original_len - len(df)
        report.details["clean_pct"] = len(df) / original_len if original_len > 0 else 0

        return df, report

    def clean_tickers(self, df: pd.DataFrame, symbol: str) -> Tuple[pd.DataFrame, QualityReport]:
        """Clean and validate ticker data."""
        if df is None:
            df = pd.DataFrame()
        report = QualityReport(
            symbol=symbol,
            timeframe="tick",
            start=df["time"].min() if not df.empty and "time" in df.columns else datetime.utcnow(),
            end=df["time"].max() if not df.empty and "time" in df.columns else datetime.utcnow(),
            total_rows=len(df),
        )

        if df.empty:
            return df, report
        if "time" not in df.columns:
            report.add_issue(DataQualityIssue.MISSING_COLUMNS, 1, "Missing: ['time']")
            return df, report

        df = df.sort_values("time").reset_index(drop=True)

        # Remove duplicates
        dup_mask = df.duplicated(subset=["time"], keep="last")
        if dup_mask.any():
            report.add_issue(DataQualityIssue.DUPLICATE_TIMESTAMPS, int(dup_mask.sum()))
            df = df[~dup_mask].reset_index(drop=True)

        # Validate prices
        price_cols = ["price", "bid", "ask"]
        for col in price_cols:
            if col in df.columns:
                invalid = df[col] <= 0
                if invalid.any():
                    report.add_issue(DataQualityIssue.NEGATIVE_PRICE, int(invalid.sum()), f"Column: {col}")
                    df = df[~invalid].reset_index(drop=True)

        # Bid <= Ask validation
        if "bid" in df.columns and "ask" in df.columns:
            invalid = df["bid"] > df["ask"]
            if invalid.any():
                report.add_issue(DataQualityIssue.PRICE_OUTLIER, int(invalid.sum()), "Bid > Ask")

        report.total_rows = len(df)
        return df, report

    def clean_trades(self, df: pd.DataFrame, symbol: str) -> Tuple[pd.DataFrame, QualityReport]:
        """Clean and validate trade data."""
        if df is None:
            df = pd.DataFrame()
        report = QualityReport(
            symbol=symbol,
            timeframe="trade",
            start=df["time"].min() if not df.empty and "time" in df.columns else datetime.utcnow(),
            end=df["time"].max() if not df.empty and "time" in df.columns else datetime.utcnow(),
            total_rows=len(df),
        )

        if df.empty:
            return df, report
        if "time" not in df.columns:
            report.add_issue(DataQualityIssue.MISSING_COLUMNS, 1, "Missing: ['time']")
            return df, report

        df = df.sort_values("time").reset_index(drop=True)

        # Remove duplicates by trade_id
        if "trade_id" in df.columns:
            dup_mask = df.duplicated(subset=["trade_id"], keep="first")
            if dup_mask.any():
                report.add_issue(DataQualityIssue.DUPLICATE_TIMESTAMPS, int(dup_mask.sum()))
                df = df[~dup_mask].reset_index(drop=True)

        # Validate price and quantity; coerce non-numeric values to NaN then drop them.
        for col in ["price", "quantity"]:
            if col in df.columns:
                coerced = pd.to_numeric(df[col], errors="coerce")
                invalid_numeric = coerced.isna()
                non_positive = coerced <= 0
                invalid = invalid_numeric | non_positive.fillna(False)
                if invalid.any():
                    report.add_issue(DataQualityIssue.NEGATIVE_PRICE if col == "price" else DataQualityIssue.ZERO_VOLUME,
                                   int(invalid.sum()), f"Column: {col}")
                    df = df.loc[~invalid].reset_index(drop=True)

        report.total_rows = len(df)
        return df, report

    def fill_gaps(
        self,
        df: pd.DataFrame,
        timeframe: str,
        method: str = "forward_fill",
    ) -> pd.DataFrame:
        """Fill gaps in time series data."""
        if df.empty:
            return df

        expected_interval = self._get_interval_timedelta(timeframe)
        if not expected_interval:
            return df

        df = df.set_index("open_time").sort_index()

        # Create complete range
        full_range = pd.date_range(
            start=df.index.min(),
            end=df.index.max(),
            freq=pd.Timedelta(expected_interval),
        )

        df = df.reindex(full_range)

        if method == "forward_fill":
            # Forward fill OHLC, zero fill volume
            price_cols = ["open_price", "high_price", "low_price", "close_price"]
            for col in price_cols:
                if col in df.columns:
                    df[col] = df[col].ffill()
            if "volume" in df.columns:
                df["volume"] = df["volume"].fillna(0)
            if "trades" in df.columns:
                df["trades"] = df["trades"].fillna(0)
        elif method == "interpolate":
            df = df.interpolate(method="time")

        df = df.reset_index().rename(columns={"index": "open_time"})
        return df

    def resample_klines(
        self,
        df: pd.DataFrame,
        target_timeframe: str,
    ) -> pd.DataFrame:
        """Resample klines to a different timeframe."""
        if df.empty:
            return df

        # Map timeframe to pandas frequency
        tf_map = {
            "1m": "1T", "3m": "3T", "5m": "5T", "15m": "15T", "30m": "30T",
            "1h": "1H", "2h": "2H", "4h": "4H", "6h": "6H", "8h": "8H", "12h": "12H",
            "1d": "1D", "3d": "3D", "1w": "1W",
        }
        freq = tf_map.get(target_timeframe)
        if not freq:
            raise ValueError(f"Unsupported timeframe: {target_timeframe}")

        df = df.set_index("open_time").sort_index()

        agg = {
            "open_price": "first",
            "high_price": "max",
            "low_price": "min",
            "close_price": "last",
            "volume": "sum",
            "trades": "sum",
        }
        # Only aggregate columns that exist
        agg = {k: v for k, v in agg.items() if k in df.columns}

        resampled = df.resample(freq).agg(agg).dropna(subset=["open_price", "close_price"])

        resampled = resampled.reset_index()
        resampled["timeframe"] = target_timeframe
        resampled["is_closed"] = True

        return resampled

    def _get_interval_timedelta(self, timeframe: str) -> Optional[timedelta]:
        """Convert timeframe string to timedelta."""
        tf_map = {
            "1m": timedelta(minutes=1), "3m": timedelta(minutes=3), "5m": timedelta(minutes=5),
            "15m": timedelta(minutes=15), "30m": timedelta(minutes=30),
            "1h": timedelta(hours=1), "2h": timedelta(hours=2), "4h": timedelta(hours=4),
            "6h": timedelta(hours=6), "8h": timedelta(hours=8), "12h": timedelta(hours=12),
            "1d": timedelta(days=1), "3d": timedelta(days=3), "1w": timedelta(weeks=1),
        }
        return tf_map.get(timeframe)

    def cross_validate(
        self,
        klines: pd.DataFrame,
        tickers: pd.DataFrame,
        symbol: str,
    ) -> QualityReport:
        """Cross-validate klines against tickers."""
        report = QualityReport(
            symbol=symbol,
            timeframe="cross_val",
            start=datetime.utcnow(),
            end=datetime.utcnow(),
            total_rows=0,
        )

        if klines.empty or tickers.empty:
            return report

        # For each kline, check if ticker price is within high/low
        klines = klines.set_index("open_time")
        tickers = tickers.set_index("time")

        mismatches = 0
        for idx, row in klines.iterrows():
            # Find tickers within this kline period
            next_idx = klines.index.get_loc(idx) + 1
            end_time = klines.index[next_idx] if next_idx < len(klines) else idx + pd.Timedelta(hours=1)

            period_tickers = tickers[(tickers.index >= idx) & (tickers.index < end_time)]
            if not period_tickers.empty:
                ticker_prices = period_tickers["price"]
                if (ticker_prices > row["high_price"]).any() or (ticker_prices < row["low_price"]).any():
                    mismatches += 1

        if mismatches > 0:
            report.add_issue(DataQualityIssue.PRICE_OUTLIER, mismatches,
                           "Ticker prices outside kline high/low")

        return report


# Convenience functions
def clean_klines(df: pd.DataFrame, symbol: str, timeframe: str) -> Tuple[pd.DataFrame, QualityReport]:
    cleaner = DataCleaner()
    return cleaner.clean_klines(df, symbol, timeframe)


def clean_tickers(df: pd.DataFrame, symbol: str) -> Tuple[pd.DataFrame, QualityReport]:
    cleaner = DataCleaner()
    return cleaner.clean_tickers(df, symbol)


def clean_trades(df: pd.DataFrame, symbol: str) -> Tuple[pd.DataFrame, QualityReport]:
    cleaner = DataCleaner()
    return cleaner.clean_trades(df, symbol)


def validate_ohlcv(df: pd.DataFrame) -> Tuple[bool, List[str]]:
    """Validate OHLCV data: required columns, no NaN, monotonic time, OHLC relationships."""
    issues: List[str] = []
    required = ["open", "high", "low", "close"]
    if df is None or df.empty:
        return False, ["empty dataframe"]
    ts_col = "open_time" if "open_time" in df.columns else df.columns[0] if len(df.columns) else None
    if ts_col is None:
        return False, ["no time column"]
    for col in required:
        if col not in df.columns:
            issues.append(f"missing column: {col}")
    if issues:
        return False, issues
    if df[required + [ts_col]].isna().any().any():
        issues.append("NaN values present in OHLCV columns")
    try:
        times = pd.to_datetime(df[ts_col])
        if not times.is_monotonic_increasing:
            issues.append("timestamps not monotonically increasing")
    except Exception as e:
        issues.append(f"unparseable timestamps: {e}")
    if not df.empty:
        bad = (
            (df["high"] < df["low"])
            | (df["high"] < df["open"])
            | (df["high"] < df["close"])
            | (df["low"] > df["open"])
            | (df["low"] > df["close"])
        )
        if bad.any():
            issues.append(f"invalid OHLC relationships on {int(bad.sum())} rows")
    return len(issues) == 0, issues


def detect_outliers_zscore(series: pd.Series, threshold: float = 3.0) -> pd.Series:
    """Return boolean mask where |z-score| > threshold."""
    s = pd.Series(series).astype(float)
    if s.empty:
        return pd.Series(dtype=bool)
    mean = s.mean()
    std = s.std()
    if std == 0 or pd.isna(std):
        return pd.Series([False] * len(s), index=s.index)
    z = (s - mean) / std
    return z.abs() > threshold


def fill_missing_bars(df: pd.DataFrame, freq: str = "1min") -> pd.DataFrame:
    """Reindex to a complete time grid and forward-fill price columns, zero-fill volume."""
    if df is None or df.empty:
        return df
    ts_col = "open_time" if "open_time" in df.columns else df.columns[0]
    out = df.copy()
    out[ts_col] = pd.to_datetime(out[ts_col])
    out = out.set_index(ts_col).sort_index()
    full_idx = pd.date_range(out.index.min(), out.index.max(), freq=freq)
    out = out.reindex(full_idx)
    price_cols = [c for c in ["open", "high", "low", "close", "open_price", "high_price", "low_price", "close_price"] if c in out.columns]
    for col in price_cols:
        out[col] = out[col].ffill()
    for col in [c for c in ["volume", "trades"] if c in out.columns]:
        out[col] = out[col].fillna(0)
    return out.reset_index().rename(columns={"index": ts_col})
