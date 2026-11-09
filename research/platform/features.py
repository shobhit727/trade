"""Causal price/volume features and separately timestamped forward labels."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np
import pandas as pd


@dataclass(frozen=True, slots=True)
class FeatureMetadata:
    """Availability and lookback policy for one generated feature matrix."""

    available_at: str
    max_lookback: int
    windows: tuple[int, ...]
    uses_future_data: bool = False
    source_fields: tuple[str, ...] = ("close", "high", "low", "volume")


class PointInTimeFeatureEngine:
    """Compute trailing indicators whose values exist at the bar's close timestamp."""

    REQUIRED_COLUMNS = frozenset({"close", "high", "low", "volume"})

    def __init__(self, windows: Sequence[int] = (5, 20, 60)) -> None:
        # Validate and freeze the lookback set so it can be hashed into an experiment.
        normalised = tuple(sorted(set(int(value) for value in windows)))
        if not normalised or any(value < 2 for value in normalised):
            raise ValueError("feature windows must be unique integers >= 2")
        self.windows = normalised

    def build(self, bars: pd.DataFrame) -> pd.DataFrame:
        """Build trailing features without forward filling or using future rows."""
        # Require ordered aware timestamps to make point-in-time joins unambiguous.
        if not self.REQUIRED_COLUMNS.issubset(bars.columns):
            raise ValueError(f"bars must include {sorted(self.REQUIRED_COLUMNS)}")
        index = pd.DatetimeIndex(bars.index)
        if index.tz is None or not index.is_monotonic_increasing or index.has_duplicates:
            raise ValueError("bar index must be timezone-aware, unique and increasing")
        values = bars[["close", "high", "low", "volume"]].to_numpy(dtype=np.float64)
        if not np.isfinite(values).all():
            raise ValueError("OHLCV feature inputs must be finite; missing values are not filled")
        if (bars[["close", "high", "low"]] <= 0).any().any() or (bars["volume"] < 0).any():
            raise ValueError("prices must be positive and volume non-negative")
        if (bars["high"] < bars[["close", "low"]].max(axis=1)).any():
            raise ValueError("high is below close or low")
        if (bars["low"] > bars[["close", "high"]].min(axis=1)).any():
            raise ValueError("low is above close or high")

        # Use only current and historical observations; no negative shifts are used here.
        close = bars["close"].astype("float64")
        high = bars["high"].astype("float64")
        low = bars["low"].astype("float64")
        volume = bars["volume"].astype("float64")
        one_bar_return = close.pct_change()
        previous_close = close.shift(1)
        true_range = pd.concat(
            (
                high - low,
                (high - previous_close).abs(),
                (low - previous_close).abs(),
            ),
            axis=1,
        ).max(axis=1, skipna=False)
        output = pd.DataFrame(index=index)
        output["return_1"] = one_bar_return
        output["range_pct"] = (high - low) / close
        for window in self.windows:
            # Rolling momentum and volatility stop at the current bar close.
            output[f"momentum_{window}"] = close.pct_change(window)
            output[f"volatility_{window}"] = one_bar_return.rolling(
                window, min_periods=window
            ).std(ddof=0)
            output[f"atr_pct_{window}"] = (
                true_range.rolling(window, min_periods=window).mean() / close
            )
            rolling_volume_mean = volume.rolling(window, min_periods=window).mean()
            rolling_volume_std = volume.rolling(window, min_periods=window).std(ddof=0)
            volume_z = (
                (volume - rolling_volume_mean) / rolling_volume_std.where(rolling_volume_std > 0)
            )
            # A fully formed zero-variance window has a well-defined z-score of zero.
            # Keep warm-up rows as NaN so they cannot bypass causal lookback requirements.
            output[f"volume_z_{window}"] = volume_z.mask(rolling_volume_std.eq(0), 0.0)
            output[f"close_to_sma_{window}"] = (
                close / close.rolling(window, min_periods=window).mean() - 1.0
            )

        # Metadata accompanies the matrix; warm-up NaNs are intentionally not imputed.
        metadata = FeatureMetadata(
            available_at="bar_close",
            max_lookback=max(self.windows),
            windows=self.windows,
            uses_future_data=False,
        )
        output.attrs["feature_metadata"] = {
            "available_at": metadata.available_at,
            "max_lookback": metadata.max_lookback,
            "windows": list(metadata.windows),
            "uses_future_data": metadata.uses_future_data,
            "source_fields": list(metadata.source_fields),
        }
        return output

    @staticmethod
    def build_next_bar_labels(bars: pd.DataFrame) -> pd.DataFrame:
        """Create one-bar forward-return labels with explicit label end timestamps.

        These labels intentionally use the next close and must remain separate from the
        feature matrix. Any training/validation splitter must purge windows whose label
        intervals overlap a protected partition.
        """
        # Keep the label timestamp separate so purging can use the true information interval.
        if "close" not in bars.columns:
            raise ValueError("close column required for forward labels")
        index = pd.DatetimeIndex(bars.index)
        if index.tz is None or not index.is_monotonic_increasing or index.has_duplicates:
            raise ValueError("bar index must be timezone-aware, unique and increasing")
        close = pd.to_numeric(bars["close"], errors="coerce").astype("float64")
        if not np.isfinite(close.to_numpy()).all() or (close <= 0).any():
            raise ValueError("close labels require finite positive prices")
        labels = pd.DataFrame(index=index)
        labels["forward_return_1"] = close.shift(-1) / close - 1.0
        labels["label_start_timestamp"] = index
        labels["label_end_timestamp"] = pd.Series(index, index=index).shift(-1)
        labels.attrs["label_horizon_bars"] = 1
        labels.attrs["uses_future_data"] = True
        return labels
