"""Binance public market-data acquisition client (no keys, no trading endpoints).

Audit F-011 requires provider clients with rate-limit handling and structured
provenance. This client only calls Binance's public market-data REST
endpoints with ``urllib.request`` (standard library only):

- Spot klines:            ``https://api.binance.com/api/v3/klines``
- Funding rate history:   ``https://fapi.binance.com/fapi/v1/fundingRate``
- Open interest history:  ``https://fapi.binance.com/futures/data/openInterestHist``
  (this endpoint serves only the most recent ~30 days of statistics)

No API key is sent, no signature is computed, and no trading or account
endpoint exists in this module. HTTP 418/429 responses trigger sleep-based
exponential backoff (Binance bans by IP on 418; both codes mean the caller
must wait). Every successful fetch validates the response shape, rejects
non-monotonic timestamps, and records provider, endpoint, request parameters
and fetch timestamp as provenance compatible with
``DatasetManifest.extra_metadata`` (string keys and values only).
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from ..adapters import normalise_acquired_ohlcv
from ..data_catalog import (
    RESOLUTION_PERIOD_SECONDS,
    DatasetManifest,
    LicenseStatus,
    ValueOrigin,
    utc_timestamp,
)
from ..domain import DataResolution, Market

SPOT_BASE_URL = "https://api.binance.com"
FUTURES_BASE_URL = "https://fapi.binance.com"
KLINES_ENDPOINT = "/api/v3/klines"
FUNDING_RATE_ENDPOINT = "/fapi/v1/fundingRate"
OPEN_INTEREST_ENDPOINT = "/futures/data/openInterestHist"

PROVIDER = "binance"

# Backoff policy: sleep before retrying, bounded attempts. Binance public
# endpoints return 418 (IP ban, Retry-After present) and 429 (rate limit).
RATE_LIMIT_STATUS_CODES = (418, 429)
BACKOFF_BASE_SECONDS = 2.0
BACKOFF_CAP_SECONDS = 60.0
MAX_ATTEMPTS = 5

# Hard limit Binance documents for these endpoints (weight-friendly batches).
KLINE_LIMIT_MAX = 1000
FUNDING_LIMIT_MAX = 1000
OPEN_INTEREST_LIMIT_MAX = 500


class AcquisitionError(RuntimeError):
    """A provider response was unusable, or the provider stayed rate-limited."""


@dataclass(frozen=True, slots=True)
class AcquiredDataset:
    """One validated provider response plus its fetch provenance.

    ``rows`` holds the raw provider records exactly as received (after shape
    validation). ``provenance`` is string-valued and safe for
    ``DatasetManifest.extra_metadata``.
    """

    kind: str
    frame: pd.DataFrame
    rows: tuple[tuple[Any, ...], ...]
    provenance: dict[str, str] = field(default_factory=dict)


def _http_get_json(
    url: str,
    params: dict[str, str | int],
    *,
    timeout_seconds: float,
    clock: Any = time,
) -> tuple[Any, dict[str, str]]:
    """GET a JSON document with sleep-based backoff on rate-limit responses.

    Returns the decoded payload and the effective request parameters actually
    sent. Any 418/429 response sleeps exponentially and retries; a non-2xx
    response that is not a rate limit fails immediately. This client performs
    no authentication of any kind.
    """
    effective_params = {key: str(value) for key, value in params.items()}
    query = urllib.parse.urlencode(effective_params)
    request = urllib.request.Request(f"{url}?{query}", method="GET")
    last_error: Exception | None = None
    for attempt in range(MAX_ATTEMPTS):
        if attempt:
            delay = min(BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)), BACKOFF_CAP_SECONDS)
            clock.sleep(delay)
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                body = response.read()
                status = getattr(response, "status", 200)
        except urllib.error.HTTPError as exc:
            if exc.code in RATE_LIMIT_STATUS_CODES:
                last_error = AcquisitionError(
                    f"rate-limited by provider (HTTP {exc.code}); backoff scheduled"
                )
                continue
            raise AcquisitionError(f"provider returned HTTP {exc.code} for {url}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise AcquisitionError(f"provider request to {url} failed: {exc}") from exc
        if status in RATE_LIMIT_STATUS_CODES:
            last_error = AcquisitionError(
                f"rate-limited by provider (HTTP {status}); backoff scheduled"
            )
            continue
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AcquisitionError(f"provider response is not valid JSON: {exc}") from exc
        return payload, effective_params
    raise AcquisitionError(
        f"provider stayed rate-limited after {MAX_ATTEMPTS} attempts with backoff"
    ) from last_error


def _require_list(payload: Any, url: str) -> list[Any]:
    if not isinstance(payload, list):
        raise AcquisitionError(f"expected a JSON array from {url}; got {type(payload).__name__}")
    return payload


def _checked_millisecond_timestamps(values: list[int], url: str) -> list[int]:
    """Reject duplicate, non-finite or non-chronological millisecond stamps."""
    for index, value in enumerate(values):
        if isinstance(value, bool) or not isinstance(value, int):
            raise AcquisitionError(f"{url} row {index} timestamp is not an integer epoch millisecond")
    for earlier, later in zip(values, values[1:]):
        if later <= earlier:
            raise AcquisitionError(
                f"{url} timestamps are not strictly increasing: {earlier} followed by {later}"
            )
    return values


def _provenance(
    *,
    endpoint: str,
    params: dict[str, str],
    fetched_at: datetime,
) -> dict[str, str]:
    """String-valued fetch provenance compatible with extra_metadata."""
    return {
        "acquisition_provider": PROVIDER,
        "acquisition_endpoint": endpoint,
        "acquisition_params_json": json.dumps(
            params, sort_keys=True, separators=(",", ":"), allow_nan=False
        ),
        "acquisition_fetched_at": fetched_at.astimezone(timezone.utc).isoformat(),
        "acquisition_schema": "binance-public-v1",
        "acquisition_auth": "none-public-endpoints",
    }


def _validated_futures_symbol(symbol: str) -> str:
    if not symbol or not symbol.isalnum() or not symbol.isupper():
        raise ValueError("symbol must be an upper-case alphanumeric market identifier")
    return symbol


class BinancePublicClient:
    """Fetch Binance public market data and validate every response shape."""

    def __init__(self, *, timeout_seconds: float = 20.0) -> None:
        if not 0 < timeout_seconds <= 300:
            raise ValueError("timeout_seconds must be between 0 (exclusive) and 300")
        self.timeout_seconds = timeout_seconds

    # -- klines ---------------------------------------------------------

    def fetch_klines(
        self,
        symbol: str,
        interval: str,
        *,
        start_ms: int | None = None,
        end_ms: int | None = None,
        limit: int = KLINE_LIMIT_MAX,
        clock: Any = time,
        now: Any = datetime,
    ) -> AcquiredDataset:
        """Fetch one page of spot klines and return a validated OHLCV frame.

        The frame uses the exact acquired CSV schema (``timestamp, open, high,
        low, close, volume``) with millisecond bar-open timestamps and has
        passed the platform's OHLCV quality gate. ``now`` may be injected in
        tests; ``clock.sleep`` is honoured for rate-limit backoff.
        """
        from .validation import validate_kline_rows

        if not symbol or not symbol.isalnum() or not symbol.isupper():
            raise ValueError("symbol must be an upper-case alphanumeric market identifier")
        allowed_intervals = {
            "1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h",
            "1d", "3d", "1w", "1mo",
        }
        if interval not in allowed_intervals:
            raise ValueError(f"unsupported kline interval: {interval}")
        if not 1 <= limit <= KLINE_LIMIT_MAX:
            raise ValueError(f"limit must be between 1 and {KLINE_LIMIT_MAX}")

        params: dict[str, str | int] = {"symbol": symbol, "interval": interval, "limit": limit}
        if start_ms is not None:
            params["startTime"] = start_ms
        if end_ms is not None:
            params["endTime"] = end_ms
        url = f"{SPOT_BASE_URL}{KLINES_ENDPOINT}"
        payload, effective_params = _http_get_json(
            url, params, timeout_seconds=self.timeout_seconds, clock=clock
        )
        rows = validate_kline_rows(_require_list(payload, url), url)
        fetched_at = now.now(timezone.utc)
        frame = _frame_from_kline_rows(rows)
        return AcquiredDataset(
            kind="klines",
            frame=frame,
            rows=tuple(rows),
            provenance=_provenance(endpoint=KLINES_ENDPOINT, params=effective_params, fetched_at=fetched_at),
        )

    # -- funding rate history ------------------------------------------

    def fetch_funding_rate(
        self,
        symbol: str,
        *,
        start_ms: int | None = None,
        end_ms: int | None = None,
        limit: int = FUNDING_LIMIT_MAX,
        clock: Any = time,
        now: Any = datetime,
    ) -> AcquiredDataset:
        """Fetch USD-M futures funding rate history (public, no key)."""
        from .validation import validate_funding_rows

        params: dict[str, str | int] = {"symbol": _validated_futures_symbol(symbol), "limit": limit}
        if start_ms is not None:
            params["startTime"] = start_ms
        if end_ms is not None:
            params["endTime"] = end_ms
        url = f"{FUTURES_BASE_URL}{FUNDING_RATE_ENDPOINT}"
        payload, effective_params = _http_get_json(
            url, params, timeout_seconds=self.timeout_seconds, clock=clock
        )
        rows = validate_funding_rows(_require_list(payload, url), url)
        fetched_at = now.now(timezone.utc)
        frame = _frame_from_funding_rows(rows)
        return AcquiredDataset(
            kind="funding_rate",
            frame=frame,
            rows=tuple(rows),
            provenance=_provenance(endpoint=FUNDING_RATE_ENDPOINT, params=effective_params, fetched_at=fetched_at),
        )

    # -- open interest history ------------------------------------------

    def fetch_open_interest(
        self,
        symbol: str,
        period: str,
        *,
        start_ms: int | None = None,
        end_ms: int | None = None,
        limit: int = OPEN_INTEREST_LIMIT_MAX,
        clock: Any = time,
        now: Any = datetime,
    ) -> AcquiredDataset:
        """Fetch USD-M futures open-interest statistics history (public, no key)."""
        from .validation import validate_open_interest_rows

        allowed_periods = {"5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d"}
        if period not in allowed_periods:
            raise ValueError(f"unsupported open-interest period: {period}")
        params: dict[str, str | int] = {
            "symbol": _validated_futures_symbol(symbol),
            "period": period,
            "limit": limit,
        }
        if start_ms is not None:
            params["startTime"] = start_ms
        if end_ms is not None:
            params["endTime"] = end_ms
        url = f"{FUTURES_BASE_URL}{OPEN_INTEREST_ENDPOINT}"
        payload, effective_params = _http_get_json(
            url, params, timeout_seconds=self.timeout_seconds, clock=clock
        )
        rows = validate_open_interest_rows(_require_list(payload, url), url)
        fetched_at = now.now(timezone.utc)
        frame = _frame_from_open_interest_rows(rows)
        return AcquiredDataset(
            kind="open_interest",
            frame=frame,
            rows=tuple(rows),
            provenance=_provenance(endpoint=OPEN_INTEREST_ENDPOINT, params=effective_params, fetched_at=fetched_at),
        )


def _frame_from_kline_rows(rows: list[dict[str, Any]]) -> pd.DataFrame:
    """Build the gate-passing OHLCV frame from validated kline rows."""
    frame = pd.DataFrame(
        [
            {
                "timestamp": row["open_time"],
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"]),
            }
            for row in rows
        ],
        columns=["timestamp", "open", "high", "low", "close", "volume"],
    )
    return normalise_acquired_ohlcv(frame, numeric_timestamp_unit="ms")


def _frame_from_funding_rows(rows: list[dict[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame(
        [
            {
                "timestamp": row["fundingTime"],
                "symbol": str(row["symbol"]),
                "funding_rate": float(row["fundingRate"]),
            }
            for row in rows
        ],
        columns=["timestamp", "symbol", "funding_rate"],
    )
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], unit="ms", utc=True)
    frame = frame.set_index(pd.DatetimeIndex(frame.pop("timestamp"), name="timestamp"))
    frame["funding_rate"] = pd.to_numeric(frame["funding_rate"])
    return frame


def _frame_from_open_interest_rows(rows: list[dict[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame(
        [
            {
                "timestamp": row["timestamp"],
                "symbol": str(row["symbol"]),
                "open_interest": float(row["sumOpenInterest"]),
                "open_interest_usd": float(row["sumOpenInterestValue"]),
            }
            for row in rows
        ],
        columns=["timestamp", "symbol", "open_interest", "open_interest_usd"],
    )
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], unit="ms", utc=True)
    frame = frame.set_index(pd.DatetimeIndex(frame.pop("timestamp"), name="timestamp"))
    for column in ("open_interest", "open_interest_usd"):
        frame[column] = pd.to_numeric(frame[column])
    return frame


# -- persistence and manifests ------------------------------------------

def write_csv(dataset: AcquiredDataset, path: str) -> str:
    """Persist an acquired frame as CSV for the local adapters to re-ingest.

    The write is atomic (same idiom as the platform's partition writer). Every
    frame a fetch returns is quality-gated and therefore carries its UTC
    timestamps in a DatetimeIndex named ``timestamp``; the CSV is written with
    that index as the leading ``timestamp`` column so
    ``ingest_acquired_ohlcv`` can re-apply the platform gate after a
    round-trip through disk. Returns the written path.
    """
    if dataset.frame.index.name != "timestamp":
        raise ValueError("acquired frames must carry a 'timestamp' DatetimeIndex before persistence")
    temporary = f"{path}.tmp"
    dataset.frame.to_csv(temporary, index=True, index_label="timestamp")
    os.replace(temporary, path)
    return path


def build_ohlcv_manifest(
    dataset: AcquiredDataset,
    *,
    dataset_id: str,
    symbol: str,
    resolution: DataResolution,
    timezone_name: str,
    license_reference: str,
    license_status: LicenseStatus = LicenseStatus.REVIEW_REQUIRED,
    csv_sha256: str | None = None,
    csv_path: str | None = None,
    now: Any = datetime,
) -> DatasetManifest:
    """Build a manifest for an acquired OHLCV dataset with fetch provenance.

    Kline acquisitions only. The manifest records the acquired frame's
    observed coverage, the platform quality report, and the acquisition
    provenance fields; ownership of the licence decision stays with the
    caller through ``license_status``/``license_reference``.
    """
    if dataset.kind != "klines":
        raise ValueError("build_ohlcv_manifest requires a klines acquisition")
    frame = dataset.frame
    if frame.empty:
        raise ValueError("cannot manifest an empty acquisition")
    utc_index = pd.DatetimeIndex(frame.index).tz_convert("UTC")
    # Half-open coverage convention (matches gap_audit): a bar stamped at open
    # time T covers [T, T + one period), so declared coverage ends one period
    # after the last observation.
    period_seconds = RESOLUTION_PERIOD_SECONDS.get(resolution.value)
    if period_seconds is None:
        raise ValueError(
            f"acquired OHLCV manifests support fixed-cadence resolutions only; "
            f"{resolution.value} has no uniform bar period"
        )
    coverage_end = (utc_index[-1] + pd.Timedelta(seconds=period_seconds)).to_pydatetime()
    extra = dict(dataset.provenance)
    extra["quality_report_json"] = json.dumps(
        frame.attrs.get("quality_report", {}),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    if csv_sha256:
        extra["file_sha256"] = csv_sha256
    if csv_path:
        extra["source_path"] = csv_path
    return DatasetManifest(
        dataset_id=dataset_id,
        market=Market.CRYPTO,
        provider=PROVIDER,
        source=(
            f"binance public REST{KLINES_ENDPOINT}"
            if csv_path is None
            else f"binance public REST{KLINES_ENDPOINT} via {csv_path}"
        ),
        instrument=symbol,
        exchange="BINANCE",
        category="ohlcv",
        resolution=resolution,
        coverage_start=utc_index[0].to_pydatetime(),
        coverage_end=coverage_end,
        timezone=timezone_name,
        timestamp_convention="Binance bar-open time (UTC, epoch ms)",
        acquired_at=utc_timestamp(now.now(timezone.utc)),
        update_frequency="on-demand-public-rest",
        license_status=license_status,
        license_reference=license_reference,
        value_origin=ValueOrigin.OBSERVED,
        processing_history=(
            "Binance public REST klines fetch (no API key)",
            "response shape validation and monotonic-timestamp check",
            "platform OHLCV quality gate (normalise_acquired_ohlcv)",
        ),
        extra_metadata=extra,
    )
