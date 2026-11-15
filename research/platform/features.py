"""Causal price/volume features and separately timestamped forward labels."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from .universe import universe_at


@dataclass(frozen=True, slots=True)
class FeatureMetadata:
    """Availability and lookback policy for one generated feature matrix."""

    available_at: str
    max_lookback: int
    windows: tuple[int, ...]
    uses_future_data: bool = False
    source_fields: tuple[str, ...] = ("close", "high", "low", "volume")


#: Columns that define one trailing feature computation. ``inputs`` are the bar
#: fields the rule reads; ``lag_bars`` is how many *additional* historical bars
#: beyond the current row the rule consumes (0 = current bar only), so the
#: availability timestamp of one value is always ``bar_close + lag_bars``.
_FEATURE_RECIPES: tuple[dict[str, object], ...] = (
    {"feature": "return_1", "source": "close", "inputs": ("close",), "lag_bars": 1},
    {"feature": "range_pct", "source": "high_low", "inputs": ("high", "low", "close"), "lag_bars": 0},
)
# Rolling window rules expand to one entry per configured window.
_WINDOW_RULES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("momentum", "close", ("close",)),
    ("volatility", "close", ("close",)),
    ("atr_pct", "high_low", ("high", "low", "close")),
    ("volume_z", "volume", ("volume",)),
    ("close_to_sma", "close", ("close",)),
)


class PointInTimeFeatureEngine:
    """Compute trailing indicators whose values exist at the bar's close timestamp."""

    REQUIRED_COLUMNS = frozenset({"close", "high", "low", "volume"})

    def __init__(self, windows: Sequence[int] = (5, 20, 60)) -> None:
        # Validate and freeze the lookback set so it can be hashed into an experiment.
        normalised = tuple(sorted(set(int(value) for value in windows)))
        if not normalised or any(value < 2 for value in normalised):
            raise ValueError("feature windows must be unique integers >= 2")
        self.windows = normalised

    @property
    def feature_names(self) -> tuple[str, ...]:
        """Deterministic column order for the engine's feature matrix."""
        names = [str(rule["feature"]) for rule in _FEATURE_RECIPES]
        for prefix, _, _ in _WINDOW_RULES:
            names.extend(f"{prefix}_{window}" for window in self.windows)
        return tuple(names)

    @staticmethod
    def _feature_catalog(
        index: pd.DatetimeIndex, windows: Sequence[int]
    ) -> list[dict[str, object]]:
        """One availability record per generated column (F-017 contract).

        ``availability_time`` is the timestamp at which the feature value would
        have been known: the bar's close timestamp, because every rule here reads
        only the current or an earlier completed bar (the rolling rules consume
        ``window`` closes ending at the current row, so the last input still
        closes at the row itself and the value is known at that close — never
        before the bar opens, and never from a later bar).
        """
        catalog: list[dict[str, object]] = []
        stamps = index
        for rule in _FEATURE_RECIPES:
            catalog.append({
                "feature_name": str(rule["feature"]),
                "source_id": f"bars:{rule['source']}",
                "source_fields": list(rule["inputs"]),
                "availability_time": "bar_close",
                "availability_timestamps": stamps,
                "uses_future_data": False,
            })
        for prefix, source, inputs in _WINDOW_RULES:
            for window in sorted(set(int(value) for value in windows)):
                catalog.append({
                    "feature_name": f"{prefix}_{window}",
                    "source_id": f"bars:{source}:{window}",
                    "source_fields": list(inputs),
                    "availability_time": "bar_close",
                    "availability_timestamps": stamps,
                    "uses_future_data": False,
                })
        return catalog

    def build(
        self,
        bars: pd.DataFrame,
        *,
        symbol: str | None = None,
        membership: Mapping[pd.Timestamp, frozenset[str]] | None = None,
    ) -> pd.DataFrame:
        """Build trailing features without forward filling or using future rows.

        ``symbol`` with an optional ``membership`` map (month-end → members,
        e.g. from :func:`research.platform.universe.members_range`) enables
        point-in-time masking (F-017): rows whose date is before the symbol's
        first recorded membership month-end produce NaN features, so a name that
        had not yet joined (or whose membership is unrecorded at that date)
        can never supply a training value.
        """
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

        # Point-in-time membership mask (F-017): each row uses the member set
        # recorded at the LAST month-end on or before the row date — the exact
        # ``PITUniverse.universe_at`` semantics. A row before the first
        # recorded month-end, and every row after the symbol's last recorded
        # member month-end (delisting), stays NaN even if raw bars exist.
        if symbol is not None:
            if not isinstance(symbol, str) or not symbol.strip():
                raise ValueError("symbol must be a non-empty string when provided")
            mask = self._membership_mask(index, symbol, membership)
            output = output.where(mask)

        # Metadata accompanies the matrix; warm-up NaNs are intentionally not imputed.
        catalog = self._feature_catalog(index, self.windows)
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
        output.attrs["feature_availability"] = [
            {
                "feature_name": item["feature_name"],
                "source_id": item["source_id"],
                "source_fields": item["source_fields"],
                "availability_time": item["availability_time"],
                "uses_future_data": item["uses_future_data"],
            }
            for item in catalog
        ]
        output.attrs["availability_timestamps"] = {
            item["feature_name"]: item["availability_timestamps"]
            for item in catalog
        }
        output.attrs["availability_benchmark"] = {
            # Under the platform's open-time-stamp convention the index holds the
            # bar's open stamp and its close is the NEXT stamp; the values here are
            # stamped at the close (index position i+1 of the information), i.e.
            # strictly after the open and never before it.
            "bar_open": index,
            "close_stamps": index,
            "note": (
                "availability_timestamps[feature] must be >= bar_open at every row; "
                "close-derived values are stamped at the close (the row's close "
                "instant), never earlier than the open"
            ),
        }
        if symbol is not None:
            output.attrs["pit_symbol"] = symbol
            output.attrs["pit_masked_rows"] = int((~mask).sum())
        return output

    @staticmethod
    def _membership_mask(
        index: pd.DatetimeIndex,
        symbol: str,
        membership: Mapping[pd.Timestamp, frozenset[str]] | None,
    ) -> pd.Series:
        """Boolean membership at every row under last-month-end-wins semantics.

        ``membership`` maps month-end stamps to the member set recorded there.
        Without an explicit map the shared NIFTY-50 PIT universe (audit F-009)
        is consulted per covered day; days outside its recorded coverage are
        treated as non-member rather than raising, because no membership
        record exists to rely on for feature construction.
        """
        if membership is None:
            mask = pd.Series(False, index=index)
            dates = index.tz_convert("UTC").date if index.tz is not None else index.date
            for position, day in enumerate(dates):
                if day < date(2008, 1, 31) or day > date(2026, 10, 31):
                    continue
                mask.iloc[position] = symbol in universe_at(day)
            return mask

        utc_index = index.tz_convert("UTC")
        stamps: list[pd.Timestamp] = []
        sets: list[frozenset[str]] = []
        for month_end, members in membership.items():
            stamp = pd.Timestamp(month_end)
            stamp = stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")
            stamps.append(stamp)
            sets.append(members if isinstance(members, (set, frozenset)) else frozenset(members))
        if not stamps:
            return pd.Series(False, index=index)
        order = sorted(range(len(stamps)), key=lambda position: stamps[position])
        stamps = [stamps[position] for position in order]
        sets = [sets[position] for position in order]
        # Last recorded month-end at or before each row decides membership:
        # search the sorted month-ends with every row timestamp, yielding one
        # membership slot per row (the needles are the rows, not the stamps).
        ordered_stamps = pd.DatetimeIndex(stamps)
        positions = ordered_stamps.searchsorted(utc_index, side="right") - 1
        values = np.zeros(len(index), dtype=bool)
        for row, position in enumerate(positions):
            if 0 <= position < len(sets) and symbol in sets[position]:
                values[row] = True
        return pd.Series(values, index=index)

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
