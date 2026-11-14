"""Acquisition clients for approved public market-data providers.

Audit F-011 requires provider clients for the platform's data pipeline. This
package holds one module per approved provider; a provider is added here only
after its licence has been reviewed. Current clients:

- :mod:`.binance`: Binance public REST market-data endpoints (no API key,
  no trading endpoints, sleep-based backoff on rate-limit responses).

Every acquired frame carries provider/endpoint/params/fetch-timestamp
provenance metadata compatible with ``DatasetManifest.extra_metadata``, and
OHLCV acquisitions must pass through :func:`ingest_acquired_ohlcv` (the
platform's existing adapters validation) before they can be registered as
research data. Acquisition never bypasses the quality gate.
"""

from __future__ import annotations

import pandas as pd

from ..adapters import normalise_acquired_ohlcv
from .binance import (
    AcquiredDataset,
    AcquisitionError,
    BinancePublicClient,
    FUNDING_RATE_ENDPOINT,
    KLINES_ENDPOINT,
    OPEN_INTEREST_ENDPOINT,
    build_ohlcv_manifest,
    write_csv,
)

__all__ = [
    "AcquiredDataset",
    "AcquisitionError",
    "BinancePublicClient",
    "FUNDING_RATE_ENDPOINT",
    "KLINES_ENDPOINT",
    "OPEN_INTEREST_ENDPOINT",
    "build_ohlcv_manifest",
    "ingest_acquired_ohlcv",
    "normalise_acquired_ohlcv",
    "write_csv",
]


def ingest_acquired_ohlcv(frame: pd.DataFrame, *, timezone_name: str = "UTC") -> pd.DataFrame:
    """Run an acquired OHLCV frame through the existing adapters quality gate.

    The acquired CSV schema must be exactly ``timestamp, open, high, low,
    close, volume``; an already-normalised frame carrying its timestamp as a
    DatetimeIndex is also accepted. The returned frame is timestamp-normalised
    and sorted, carries the adapters' ``quality_report`` in ``attrs``, and any
    failed platform assertion (missing or non-finite data, non-positive
    prices, open outside [low, high], duplicate or non-chronological
    timestamps) raises. Re-parsing a persisted acquisition through this
    function is the supported path from CSV back into the platform.
    """
    return normalise_acquired_ohlcv(frame, timezone_name=timezone_name)
