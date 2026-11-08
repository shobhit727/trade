"""Adapters for existing repository data and strategy catalogues.

These adapters read local historical files only. They do not scrape sources, use API keys,
or infer licensing permission from public accessibility.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .data_catalog import DatasetManifest, LicenseStatus, ValueOrigin
from .domain import DataResolution, Market


RESOLUTION_MAP = {
    DataResolution.ONE_MINUTE: "1m",
    DataResolution.FIVE_MINUTES: "5m",
    DataResolution.FIFTEEN_MINUTES: "15m",
    DataResolution.THIRTY_MINUTES: "30m",
    DataResolution.ONE_HOUR: "1h",
    DataResolution.FOUR_HOURS: "4h",
    DataResolution.ONE_DAY: "1d",
    DataResolution.ONE_WEEK: "1w",
    DataResolution.ONE_MONTH: "1mo",
}


def _normalise_ohlcv(frame: pd.DataFrame, *, timezone_name: str) -> pd.DataFrame:
    # Standardise schema without filling gaps or fabricating observations.
    result = frame.copy()
    result.columns = [str(column).strip().lower() for column in result.columns]
    timestamp_column = next(
        (column for column in ("timestamp", "datetime", "date", "ts", "_ts", "time") if column in result.columns),
        None,
    )
    if timestamp_column is None:
        if isinstance(result.index, pd.DatetimeIndex):
            index = result.index
        else:
            raise ValueError("data source needs a recognised timestamp column or DatetimeIndex")
    else:
        raw_time = result.pop(timestamp_column)
        if pd.api.types.is_numeric_dtype(raw_time):
            # Numeric timestamps are milliseconds only when the source explicitly uses ms.
            index = pd.to_datetime(raw_time, unit="ms", utc=True, errors="coerce")
        else:
            index = pd.to_datetime(raw_time, utc=True, errors="coerce")
    if index.isna().any():
        raise ValueError("data source contains invalid timestamps")
    if index.tz is None:
        index = index.tz_localize(timezone_name)
    else:
        index = index.tz_convert(timezone_name)
    result.index = pd.DatetimeIndex(index)
    result.index.name = "timestamp"
    result = result.sort_index()
    if result.index.has_duplicates:
        raise ValueError("duplicate timestamps must be resolved by a source-specific audit")
    if not result.index.is_monotonic_increasing:
        raise ValueError("timestamps must be chronological")
    for column in ("open", "high", "low", "close", "volume"):
        if column in result:
            result[column] = pd.to_numeric(result[column], errors="coerce")
    required = {"open", "high", "low", "close", "volume"}
    if not required.issubset(result.columns):
        raise ValueError(f"OHLCV source missing columns: {sorted(required - set(result.columns))}")
    prices = result[["open", "high", "low", "close"]].to_numpy(dtype="float64")
    volume = result["volume"].to_numpy(dtype="float64")
    # Reject corruption; do not coerce missing values into synthetic prices.
    if not np.isfinite(prices).all() or not np.isfinite(volume).all():
        raise ValueError("OHLCV source has missing or non-finite values")
    if (prices <= 0).any() or (volume < 0).any():
        raise ValueError("prices must be positive and volume non-negative")
    if (result["high"] < result[["open", "close", "low"]].max(axis=1)).any():
        raise ValueError("high is below an OHLC value")
    if (result["low"] > result[["open", "close", "high"]].min(axis=1)).any():
        raise ValueError("low is above an OHLC value")
    return result


class NSELegacyAdapter:
    """Read NSE symbol histories through the repository's audited optimizer splitter."""

    def __init__(self, *, timezone_name: str = "Asia/Kolkata") -> None:
        # The existing splitter uses the audited per-symbol loader and cleaning policy.
        self.timezone_name = timezone_name

    def available_symbols(self, resolution: DataResolution = DataResolution.ONE_DAY) -> tuple[str, ...]:
        """List local symbols available to the legacy NSE data loader."""
        # Import lazily so platform metadata can be used without all research dependencies.
        from research.optimize.splitter import available_symbols

        timeframe = RESOLUTION_MAP.get(resolution)
        if timeframe is None:
            raise ValueError(f"NSE legacy loader does not support resolution {resolution.value}")
        return tuple(available_symbols(timeframe=timeframe, include_excluded=False))

    def load(self, symbol: str, resolution: DataResolution = DataResolution.ONE_DAY) -> pd.DataFrame:
        """Load an audited symbol history; return only observed rows."""
        # Reuse the existing splitter and its current cleaning rules instead of duplicating them.
        from research.optimize.splitter import FULL, bars

        timeframe = RESOLUTION_MAP.get(resolution)
        if timeframe is None:
            raise ValueError(f"NSE legacy loader does not support resolution {resolution.value}")
        available = self.available_symbols(resolution)
        if symbol not in available:
            raise KeyError(f"symbol {symbol!r} not in the local NSE data inventory")
        frame = bars(symbol, window=FULL, timeframe=timeframe)
        if frame.empty:
            raise ValueError(f"no usable {timeframe} bars for symbol {symbol}")
        return _normalise_ohlcv(frame.reset_index(), timezone_name=self.timezone_name)

    def manifest(self, symbol: str, resolution: DataResolution = DataResolution.ONE_DAY) -> DatasetManifest:
        """Create an unapproved local-data manifest; user must review data licence."""
        # The adapter does not claim that the historical vendor licence permits reuse.
        frame = self.load(symbol, resolution)
        return DatasetManifest(
            dataset_id=f"nse-local-{symbol}-{resolution.value}",
            market=Market.NSE,
            provider="local-repository",
            source=f"data/nse/{symbol}_{RESOLUTION_MAP[resolution]}.csv via research.optimize.splitter",
            instrument=symbol,
            exchange="NSE",
            category="ohlcv",
            resolution=resolution,
            coverage_start=frame.index[0].to_pydatetime(),
            coverage_end=frame.index[-1].to_pydatetime(),
            timezone=self.timezone_name,
            timestamp_convention="bar timestamp normalised by the legacy NSE splitter",
            acquired_at=datetime.now(timezone.utc),
            update_frequency="unknown",
            license_status=LicenseStatus.REVIEW_REQUIRED,
            license_reference="legacy data licence must be reviewed before use",
            value_origin=ValueOrigin.OBSERVED,
            quality_score=None,
            processing_history=("research.optimize.splitter.bars", "OHLCV schema validation"),
        )


class CryptoLocalAdapter:
    """Load local crypto OHLCV CSV/Parquet files from an exchange-scoped directory."""

    def __init__(self, data_root: str | Path, exchange: str, *, timezone_name: str = "UTC") -> None:
        # Keep every venue rooted inside its own local data directory.
        self.data_root = Path(data_root).resolve()
        self.exchange = exchange.strip().lower()
        self.timezone_name = timezone_name
        if not self.exchange or any(part in self.exchange for part in ("/", "\\", "..")):
            raise ValueError("exchange must be a simple venue identifier")
        self.exchange_root = (self.data_root / self.exchange).resolve()
        if self.data_root not in self.exchange_root.parents:
            raise ValueError("exchange data path escapes configured root")

    def _candidate_paths(self, symbol: str, resolution: DataResolution) -> tuple[Path, ...]:
        # Symbol identifiers are rejected if they could traverse outside the exchange folder.
        if not symbol or any(part in symbol for part in ("/", "\\", "..")):
            raise ValueError("symbol must be a simple instrument identifier")
        label = resolution.value
        return (
            self.exchange_root / f"{symbol}_{label}.parquet",
            self.exchange_root / f"{symbol}_{label}.csv",
            self.exchange_root / symbol / f"{label}.parquet",
            self.exchange_root / symbol / f"{label}.csv",
        )

    def load(self, symbol: str, resolution: DataResolution) -> pd.DataFrame:
        """Read CSV or Parquet; no network requests or automatic gap filling occur."""
        # Resolve only supported local files under the exchange folder.
        path = next((candidate for candidate in self._candidate_paths(symbol, resolution)
                     if candidate.is_file()), None)
        if path is None:
            raise FileNotFoundError(f"no local {symbol} {resolution.value} file for {self.exchange}")
        if path.suffix == ".parquet":
            frame = pd.read_parquet(path)
        else:
            frame = pd.read_csv(path)
        return _normalise_ohlcv(frame, timezone_name=self.timezone_name)

    def load_inr(
        self,
        symbol: str,
        resolution: DataResolution,
        *,
        fx_rates,
        source_quote_currency: str,
    ) -> pd.DataFrame:
        """Load quote-denominated bars and convert them with point-in-time FX rates."""
        # Require an explicit FX series; never infer quote currency from the symbol text.
        from .fx import FXRateSeries, convert_ohlcv_to_inr

        if not isinstance(fx_rates, FXRateSeries):
            raise TypeError("fx_rates must be an FXRateSeries with explicit provenance")
        frame = self.load(symbol, resolution)
        return convert_ohlcv_to_inr(
            frame,
            fx_rates,
            source_quote_currency=source_quote_currency,
        )

    def manifest(self, symbol: str, resolution: DataResolution) -> DatasetManifest:
        """Create a manifest fingerprinted by source-file bytes and coverage."""
        # Local possession is not proof of data redistribution or derivative-use rights.
        path = next((candidate for candidate in self._candidate_paths(symbol, resolution)
                     if candidate.is_file()), None)
        if path is None:
            raise FileNotFoundError(f"no local data file for {symbol} at {resolution.value}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        frame = self.load(symbol, resolution)
        return DatasetManifest(
            dataset_id=f"crypto-{self.exchange}-{symbol}-{resolution.value}-{digest[:12]}",
            market=Market.CRYPTO,
            provider="local-repository",
            source=f"{path.relative_to(self.data_root)} sha256={digest}",
            instrument=symbol,
            exchange=self.exchange,
            category="ohlcv",
            resolution=resolution,
            coverage_start=frame.index[0].to_pydatetime(),
            coverage_end=frame.index[-1].to_pydatetime(),
            timezone=self.timezone_name,
            timestamp_convention="source timestamp; converted to configured timezone",
            acquired_at=datetime.now(timezone.utc),
            update_frequency="unknown",
            license_status=LicenseStatus.REVIEW_REQUIRED,
            license_reference="source licence must be reviewed before use",
            value_origin=ValueOrigin.OBSERVED,
            processing_history=("local CSV/Parquet import", "OHLCV schema validation"),
            extra_metadata={"file_sha256": digest},
        )


class ExistingStrategyCatalogueAdapter:
    """Expose existing crypto catalog strategies using their typed Config search spaces."""

    def discover(self) -> tuple[object, ...]:
        # Keep the existing registry implementation as the authoritative catalogue.
        from research.optimize.catalog import discover

        return tuple(discover())
