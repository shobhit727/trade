"""Adapters for existing repository data and strategy catalogues.

These adapters read local historical files only. They do not scrape sources, use API keys,
or infer licensing permission from public accessibility.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import replace
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


def validate_ohlcv_quality(
    frame: pd.DataFrame,
    *,
    max_abs_close_return: float | None = None,
) -> dict[str, float | int | None]:
    """Apply hard OHLCV assertions and return a small provenance-ready quality summary."""
    # Caller supplies an already timestamp-normalised frame; no repair or interpolation occurs.
    required = {"open", "high", "low", "close", "volume"}
    if not required.issubset(frame.columns):
        raise ValueError(f"OHLCV source missing columns: {sorted(required - set(frame.columns))}")
    prices = frame[["open", "high", "low", "close"]].to_numpy(dtype="float64")
    volume = frame["volume"].to_numpy(dtype="float64")
    if not np.isfinite(prices).all() or not np.isfinite(volume).all():
        raise ValueError("OHLCV source has missing or non-finite values")
    if (prices <= 0).any() or (volume < 0).any():
        raise ValueError("prices must be positive and volume non-negative")

    # Assert the open lies inside the observed intrabar range.
    open_values = frame["open"].to_numpy(dtype="float64")
    high_values = frame["high"].to_numpy(dtype="float64")
    low_values = frame["low"].to_numpy(dtype="float64")
    open_violations = int(((open_values < low_values) | (open_values > high_values)).sum())
    if open_violations:
        raise ValueError(f"OHLCV open is outside [low, high] on {open_violations} bars")

    if (high_values < np.maximum.reduce([
        open_values,
        frame["close"].to_numpy(dtype="float64"),
        low_values,
    ])).any():
        raise ValueError("high is below an OHLC value")
    if (low_values > np.minimum.reduce([
        open_values,
        frame["close"].to_numpy(dtype="float64"),
        high_values,
    ])).any():
        raise ValueError("low is above an OHLC value")

    # The close-return guard is market/resolution-specific; crypto can legitimately move >20%.
    close_returns = frame["close"].pct_change().dropna().abs()
    max_observed = float(close_returns.max()) if not close_returns.empty else 0.0
    outliers = 0
    if max_abs_close_return is not None:
        if (
            isinstance(max_abs_close_return, bool)
            or not np.isfinite(max_abs_close_return)
            or not 0 < max_abs_close_return < 1
        ):
            raise ValueError("max_abs_close_return must be between zero and one")
        outliers = int((close_returns >= max_abs_close_return).sum())
        if outliers:
            first_bad = close_returns[close_returns >= max_abs_close_return].index[0]
            raise ValueError(
                f"absolute close return must be < {max_abs_close_return:.1%}; "
                f"{outliers} bars failed, first at {first_bad.isoformat()}"
            )

    return {
        "bars_checked": int(len(frame)),
        "open_range_violations": open_violations,
        "close_return_outliers": outliers,
        "max_abs_close_return": max_observed,
        "max_abs_close_return_limit": max_abs_close_return,
        "negative_volume_count": 0,
    }


def _normalise_ohlcv(
    frame: pd.DataFrame,
    *,
    timezone_name: str,
    numeric_timestamp_unit: str | None = None,
    max_abs_close_return: float | None = None,
) -> pd.DataFrame:
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
            # Numeric timestamp units must come from the provider's documented convention.
            if numeric_timestamp_unit not in {"s", "ms", "us", "ns"}:
                raise ValueError("numeric timestamps require an explicit s/ms/us/ns unit")
            index = pd.to_datetime(raw_time, unit=numeric_timestamp_unit, utc=True, errors="coerce")
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
    quality_report = validate_ohlcv_quality(
        result,
        max_abs_close_return=max_abs_close_return,
    )
    # Keep the checks performed with the imported rows for downstream immutable manifests.
    result.attrs["quality_report"] = quality_report
    return result


def materialize_non_holdout_partition(
    manifest: DatasetManifest,
    frame: pd.DataFrame,
    *,
    root: str | Path,
    final_holdout_start: datetime,
    max_abs_close_return: float | None = None,
) -> DatasetManifest:
    """Write a physical non-holdout CSV and return a manifest for that safe copy.

    This preparation function is intended for a trusted ingestion process. Research workers
    should receive the returned manifest and a partition-store root, not the original combined
    source file. Rows at or after final_holdout_start are never written to the safe copy.
    """
    # Validate identity and cutoff before creating any path or writing any rows.
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,160}", manifest.dataset_id) or ".." in manifest.dataset_id:
        raise ValueError("dataset_id must be a simple, non-traversing identifier")
    if (
        final_holdout_start.tzinfo is None
        or final_holdout_start.utcoffset() is None
    ):
        raise ValueError("final_holdout_start must be timezone-aware")
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise ValueError("partition source must have a DatetimeIndex")
    if (
        frame.index.tz is None
        or not frame.index.is_monotonic_increasing
        or frame.index.has_duplicates
    ):
        raise ValueError("partition source index must be aware, increasing and unique")
    if not {"open", "high", "low", "close", "volume"}.issubset(frame.columns):
        raise ValueError("partition source must contain complete OHLCV columns")
    if frame.empty:
        raise ValueError("partition source is empty")

    # Carry forward a configured source quality threshold when the caller already validated it.
    source_quality = frame.attrs.get("quality_report", {})
    quality_limit = (
        max_abs_close_return
        if max_abs_close_return is not None
        else source_quality.get("max_abs_close_return_limit")
    )

    # Apply a half-open boundary in UTC and discard every final-holdout row before serialization.
    boundary = pd.Timestamp(final_holdout_start).tz_convert("UTC")
    utc_index = frame.index.tz_convert("UTC")
    safe_frame = frame.loc[utc_index < boundary].copy()
    if safe_frame.empty:
        raise ValueError("no non-holdout rows exist before final_holdout_start")
    if safe_frame.index.tz_convert("UTC").max() >= boundary:
        raise AssertionError("non-holdout partition contains a protected timestamp")
    quality_report = validate_ohlcv_quality(
        safe_frame,
        max_abs_close_return=quality_limit,
    )

    # Write beneath one dataset-specific directory and replace the file atomically.
    data_root = Path(root).resolve()
    dataset_dir = (data_root / manifest.dataset_id).resolve()
    try:
        dataset_dir.relative_to(data_root)
    except ValueError as exc:
        raise ValueError("partition destination escapes the configured root") from exc
    dataset_dir.mkdir(parents=True, exist_ok=True)
    destination = (dataset_dir / "non_holdout.csv").resolve()
    destination.relative_to(data_root)
    temporary = destination.with_suffix(".csv.tmp")
    safe_frame.to_csv(
        temporary,
        index=True,
        index_label="timestamp",
        date_format="%Y-%m-%dT%H:%M:%S%z",
    )
    os.replace(temporary, destination)
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    relative_path = destination.relative_to(data_root).as_posix()
    cutoff_iso = boundary.isoformat()

    # Return a new immutable manifest whose coverage excludes the protected final period.
    extra = dict(manifest.extra_metadata)
    extra.update({
        "research_partition_path": relative_path,
        "research_partition_sha256": digest,
        "research_partition_before": cutoff_iso,
        "research_partition_schema": "ohlcv-csv-v1",
        "research_partition_bars": str(len(safe_frame)),
        "quality_report_json": json.dumps(
            quality_report, sort_keys=True, separators=(",", ":"), allow_nan=False
        ),
    })
    history = tuple(manifest.processing_history) + (
        f"materialized non-holdout partition before {cutoff_iso}",
        "final-holdout rows excluded from research worker data copy",
    )
    return replace(
        manifest,
        coverage_start=safe_frame.index[0].to_pydatetime(),
        coverage_end=safe_frame.index[-1].to_pydatetime(),
        extra_metadata=extra,
        processing_history=history,
    )


def load_non_holdout_partition(
    manifest: DatasetManifest | dict[str, object],
    *,
    root: str | Path,
    final_holdout_start: datetime,
    end: datetime,
) -> pd.DataFrame:
    """Load only a checksum-verified pre-materialised non-holdout file."""
    # Accept the immutable dataclass or the JSON mapping returned by ExperimentStore.
    if isinstance(manifest, DatasetManifest):
        metadata = manifest.extra_metadata
        timezone_name = manifest.timezone
    else:
        metadata = dict(manifest["extra_metadata"])
        timezone_name = str(manifest["timezone"])
    # No combined source-file fallback exists in this function.
    if final_holdout_start.tzinfo is None or final_holdout_start.utcoffset() is None:
        raise ValueError("final_holdout_start must be timezone-aware")
    if end.tzinfo is None or end.utcoffset() is None:
        raise ValueError("end must be timezone-aware")
    relative = metadata.get("research_partition_path")
    expected_hash = metadata.get("research_partition_sha256")
    boundary_text = metadata.get("research_partition_before")
    if (
        not relative
        or not expected_hash
        or not boundary_text
        or metadata.get("research_partition_schema") != "ohlcv-csv-v1"
    ):
        raise ValueError("dataset manifest has no valid pre-materialised non-holdout partition")

    data_root = Path(root).resolve()
    path = (data_root / relative).resolve()
    try:
        path.relative_to(data_root)
    except ValueError as exc:
        raise ValueError("partition source path escapes the configured root") from exc
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected_hash:
        raise ValueError("partition source is missing or its checksum does not match the manifest")

    # The partition cutoff must be no later than the protected boundary for this experiment.
    cutoff = pd.Timestamp(boundary_text)
    if cutoff.tzinfo is None:
        raise ValueError("partition manifest cutoff must include a timezone")
    final_boundary = pd.Timestamp(final_holdout_start).tz_convert("UTC")
    if cutoff.tz_convert("UTC") > final_boundary:
        raise ValueError("partition file includes a period beyond the final-holdout boundary")

    # Parse only the physically safe file and verify every materialised row is before the cut.
    frame = pd.read_csv(path)
    frame = _normalise_ohlcv(frame, timezone_name=timezone_name)
    frame_utc = frame.index.tz_convert("UTC")
    if len(frame) != int(metadata.get("research_partition_bars", "-1")):
        raise ValueError("partition row count differs from the manifest")
    if frame_utc.empty or frame_utc.max() >= cutoff.tz_convert("UTC"):
        raise ValueError("partition file contains rows at or after its declared cutoff")
    if frame_utc.max() >= final_boundary:
        raise ValueError("partition file contains a final-holdout row")
    end_utc = pd.Timestamp(end).tz_convert("UTC")
    clipped = frame.loc[frame_utc < end_utc].copy()
    if clipped.empty:
        raise ValueError("no bars remain before the requested evaluation end")
    clipped.attrs["partition_source_sha256"] = expected_hash
    clipped.attrs["partition_source_path"] = relative
    clipped.attrs["final_holdout_accessed"] = False
    return clipped


class NSELegacyAdapter:
    """Read NSE symbol histories through the repository's audited optimizer splitter."""

    def __init__(
        self,
        *,
        timezone_name: str = "Asia/Kolkata",
        max_daily_close_return: float | None = 0.20,
    ) -> None:
        # The daily NSE guard rejects suspicious split-adjustment jumps without dropping rows.
        if (
            max_daily_close_return is not None
            and (not np.isfinite(max_daily_close_return) or not 0 < max_daily_close_return < 1)
        ):
            raise ValueError("max_daily_close_return must be between zero and one or None")
        self.timezone_name = timezone_name
        self.max_daily_close_return = max_daily_close_return

    def available_symbols(self, resolution: DataResolution = DataResolution.ONE_DAY) -> tuple[str, ...]:
        """List local symbols available to the legacy NSE data loader."""
        # Import lazily so platform metadata can be used without all research dependencies.
        from research.optimize.splitter import available_symbols

        timeframe = RESOLUTION_MAP.get(resolution)
        if timeframe is None:
            raise ValueError(f"NSE legacy loader does not support resolution {resolution.value}")
        return tuple(available_symbols(timeframe=timeframe, include_excluded=False))

    def load(
        self,
        symbol: str,
        resolution: DataResolution = DataResolution.ONE_DAY,
        *,
        end: datetime | None = None,
    ) -> pd.DataFrame:
        """Load an audited symbol history, optionally clipped before a protected boundary."""
        # Reuse the existing splitter and its cleaning rules; a caller may cap the end date.
        from research.optimize.splitter import FULL, Window, bars

        timeframe = RESOLUTION_MAP.get(resolution)
        if timeframe is None:
            raise ValueError(f"NSE legacy loader does not support resolution {resolution.value}")
        available = self.available_symbols(resolution)
        if symbol not in available:
            raise KeyError(f"symbol {symbol!r} not in the local NSE data inventory")
        window = Window(FULL.start, end.isoformat()) if end is not None else FULL
        frame = bars(symbol, window=window, timeframe=timeframe)
        if end is not None:
            # The end boundary is half-open; no observation at/after it enters the caller.
            frame = frame.loc[frame.index < pd.Timestamp(end)]
        if frame.empty:
            raise ValueError(f"no usable {timeframe} bars for symbol {symbol}")
        return _normalise_ohlcv(
            frame.reset_index(),
            timezone_name=self.timezone_name,
            max_abs_close_return=(
                self.max_daily_close_return
                if resolution is DataResolution.ONE_DAY else None
            ),
        )

    def manifest(
        self,
        symbol: str,
        resolution: DataResolution = DataResolution.ONE_DAY,
        *,
        end: datetime | None = None,
    ) -> DatasetManifest:
        """Create an unapproved local-data manifest fingerprinted to source bytes."""
        # The adapter does not claim that the historical vendor licence permits reuse.
        from research.optimize import config as optimizer_config

        timeframe = RESOLUTION_MAP.get(resolution)
        if timeframe is None:
            raise ValueError(f"NSE legacy loader does not support resolution {resolution.value}")
        path = optimizer_config.DATA_DIR / f"{symbol}_{timeframe}.csv"
        if not path.is_file():
            raise FileNotFoundError(f"no local NSE source file for {symbol} at {timeframe}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        frame = self.load(symbol, resolution, end=end)
        return DatasetManifest(
            dataset_id=f"nse-local-{symbol}-{resolution.value}-{digest[:12]}",
            market=Market.NSE,
            provider="local-repository",
            source=f"{path.name} sha256={digest} via research.optimize.splitter",
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
            processing_history=(
                "research.optimize.splitter.bars",
                "OHLCV schema/positive-price/open-range assertions",
                "daily absolute close return < 20% or configured override",
            ),
            extra_metadata={
                "file_sha256": digest,
                "numeric_timestamp_unit": "ms",
                "quality_report_json": json.dumps(
                    frame.attrs.get("quality_report", {}),
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ),
            },
        )


class CryptoLocalAdapter:
    """Load local crypto OHLCV CSV/Parquet files from an exchange-scoped directory."""

    def __init__(
        self,
        data_root: str | Path,
        exchange: str,
        *,
        timezone_name: str = "UTC",
        numeric_timestamp_unit: str | None = None,
        quote_currency: str | None = None,
        fx_dataset_id: str | None = None,
        timestamp_position: str | None = None,
    ) -> None:
        # Keep every venue rooted inside its own local data directory and timestamp convention.
        self.data_root = Path(data_root).resolve()
        self.exchange = exchange.strip().lower()
        self.timezone_name = timezone_name
        self.numeric_timestamp_unit = numeric_timestamp_unit
        self.quote_currency = quote_currency.upper() if quote_currency else None
        self.fx_dataset_id = fx_dataset_id
        self.timestamp_position = timestamp_position
        if timestamp_position not in {None, "bar_open", "bar_close"}:
            raise ValueError("timestamp_position must be bar_open or bar_close")
        if numeric_timestamp_unit not in {None, "s", "ms", "us", "ns"}:
            raise ValueError("numeric_timestamp_unit must be s, ms, us, ns or None")
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
        candidates = (
            self.exchange_root / f"{symbol}_{label}.parquet",
            self.exchange_root / f"{symbol}_{label}.csv",
            self.exchange_root / symbol / f"{label}.parquet",
            self.exchange_root / symbol / f"{label}.csv",
        )
        # Reject symlinked files/directories that resolve outside the exchange boundary.
        for candidate in candidates:
            resolved = candidate.resolve()
            try:
                resolved.relative_to(self.exchange_root)
            except ValueError as exc:
                raise ValueError("data source path escapes the exchange directory") from exc
        return candidates

    def load(
        self,
        symbol: str,
        resolution: DataResolution,
        *,
        end: datetime | None = None,
    ) -> pd.DataFrame:
        """Read local CSV/Parquet and optionally clip observations before an end boundary."""
        # Resolve only supported local files under the exchange folder.
        path = next((candidate for candidate in self._candidate_paths(symbol, resolution)
                     if candidate.is_file()), None)
        if path is None:
            raise FileNotFoundError(f"no local {symbol} {resolution.value} file for {self.exchange}")
        if path.suffix == ".parquet":
            frame = pd.read_parquet(path)
        else:
            frame = pd.read_csv(path)
        normalised = _normalise_ohlcv(
            frame,
            timezone_name=self.timezone_name,
            numeric_timestamp_unit=self.numeric_timestamp_unit,
        )
        if end is not None:
            # Exclude the boundary and every later observation before returning the frame.
            end_utc = end.astimezone(timezone.utc)
            normalised = normalised.loc[
                pd.DatetimeIndex(normalised.index).tz_convert("UTC") < end_utc
            ]
        return normalised

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
            timestamp_convention=(
                f"source timestamp; numeric_unit={self.numeric_timestamp_unit or 'none'}; "
                "converted to configured timezone"
            ),
            acquired_at=datetime.now(timezone.utc),
            update_frequency="unknown",
            license_status=LicenseStatus.REVIEW_REQUIRED,
            license_reference="source licence must be reviewed before use",
            value_origin=ValueOrigin.OBSERVED,
            processing_history=(
                "local CSV/Parquet import",
                "OHLCV schema/positive-price/open-range assertions",
                "no universal crypto close-return ceiling applied",
            ),
            extra_metadata={
                "file_sha256": digest,
                "numeric_timestamp_unit": self.numeric_timestamp_unit or "",
                "quote_currency": self.quote_currency or "",
                "fx_dataset_id": self.fx_dataset_id or "",
                "timestamp_position": self.timestamp_position or "",
                "quality_report": str(frame.attrs.get("quality_report", {})),
            },
        )


class ExistingStrategyCatalogueAdapter:
    """Expose existing crypto catalog strategies using their typed Config search spaces."""

    def discover(self) -> tuple[object, ...]:
        # Keep the existing registry implementation as the authoritative catalogue.
        from research.optimize.catalog import discover

        return tuple(discover())
