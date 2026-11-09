"""Timestamp-safe quote-currency to INR conversion for historical crypto bars."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

import numpy as np
import pandas as pd


@dataclass(frozen=True, slots=True)
class FXRateSeries:
    """Point-in-time FX rates expressed as INR per one unit of quote currency."""

    rates: pd.Series
    quote_currency: str
    source_id: str
    max_staleness: timedelta = timedelta(minutes=15)

    def __post_init__(self) -> None:
        # Require unique, ordered, timezone-aware FX observations with finite positive rates.
        index = pd.DatetimeIndex(self.rates.index)
        if index.tz is None or not index.is_monotonic_increasing or index.has_duplicates:
            raise ValueError("FX rate timestamps must be timezone-aware, unique and increasing")
        values = self.rates.to_numpy(dtype=np.float64)
        if not np.isfinite(values).all() or (values <= 0).any():
            raise ValueError("FX rates must be finite and positive")
        if not self.quote_currency.strip() or not self.source_id.strip():
            raise ValueError("quote currency and FX source identifier are required")
        if self.max_staleness <= timedelta(0):
            raise ValueError("max_staleness must be positive")


def convert_ohlcv_to_inr(
    bars: pd.DataFrame,
    fx: FXRateSeries,
    *,
    source_quote_currency: str,
) -> pd.DataFrame:
    """Convert quote-denominated OHLC columns to INR with backward-only FX alignment.

    A bar can only use an FX observation available at or before that bar timestamp.
    The function rejects missing/stale FX observations rather than forward-filling beyond
    the declared maximum age or interpolating between future/past observations.
    """
    # Explicitly distinguish quote denomination; never infer it from a symbol suffix.
    quote = source_quote_currency.strip().upper()
    if not quote or quote != fx.quote_currency.strip().upper():
        raise ValueError("source quote currency must match the FX series quote_currency")
    result = bars.copy()
    index = pd.DatetimeIndex(result.index)
    fx_index = pd.DatetimeIndex(fx.rates.index)
    if index.tz is None or fx_index.tz is None:
        raise ValueError("bar and FX timestamps must be timezone-aware")
    if not index.is_monotonic_increasing or index.has_duplicates:
        raise ValueError("bar timestamps must be unique and increasing")
    if not fx_index.is_monotonic_increasing or fx_index.has_duplicates:
        raise ValueError("FX timestamps must be unique and increasing")
    required = {"open", "high", "low", "close"}
    if not required.issubset(result.columns):
        raise ValueError("OHLC columns are required for FX conversion")

    # Merge as-of uses only the latest FX timestamp <= the price-bar timestamp.
    left = pd.DataFrame({"bar_timestamp": index.tz_convert("UTC")}).sort_values("bar_timestamp")
    right = pd.DataFrame({
        "fx_timestamp": fx_index.tz_convert("UTC"),
        "inr_per_quote": fx.rates.to_numpy(dtype=np.float64),
    }).sort_values("fx_timestamp")
    # Resolution shifts can upcast one side (e.g. ms-parsed bars vs us-stamped FX ends);
    # merge_asof requires both keys in the same datetime unit, so normalise to us.
    left["bar_timestamp"] = left["bar_timestamp"].astype("datetime64[us, UTC]")
    right["fx_timestamp"] = right["fx_timestamp"].astype("datetime64[us, UTC]")
    aligned = pd.merge_asof(
        left,
        right,
        left_on="bar_timestamp",
        right_on="fx_timestamp",
        direction="backward",
        tolerance=pd.Timedelta(fx.max_staleness),
        allow_exact_matches=True,
    )
    if aligned["inr_per_quote"].isna().any():
        missing = int(aligned["inr_per_quote"].isna().sum())
        raise ValueError(f"{missing} price bars have no sufficiently recent prior FX rate")
    if (aligned["fx_timestamp"] > aligned["bar_timestamp"]).any():
        raise RuntimeError("future FX observation was joined to a price bar")

    # Reject corrupt source prices before applying the point-in-time FX conversion.
    source_prices = result[["open", "high", "low", "close"]].to_numpy(dtype=np.float64)
    if not np.isfinite(source_prices).all() or (source_prices <= 0).any():
        raise ValueError("source OHLC values must be finite and positive")
    # Convert only prices; volume remains denominated in the exchange's traded units.
    factor = aligned["inr_per_quote"].to_numpy(dtype=np.float64)
    for column in ("open", "high", "low", "close"):
        result[column] = result[column].to_numpy(dtype=np.float64) * factor
    result.attrs["fx_source_id"] = fx.source_id
    result.attrs["source_quote_currency"] = quote
    result.attrs["target_quote_currency"] = "INR"
    result.attrs["fx_alignment"] = "backward_asof_no_future"
    result.attrs["fx_max_staleness_seconds"] = fx.max_staleness.total_seconds()
    result.attrs["fx_observation_timestamps"] = aligned["fx_timestamp"].astype(str).tolist()
    return result
