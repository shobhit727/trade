"""Tests for the F-011 Binance public acquisition client and ingest gate.

Every test monkeypatches ``urllib.request.urlopen``; no test performs network
I/O. Response payloads mirror the providers' documented public schemas
(klines arrive as 12-field arrays with string-encoded numerics; funding and
open-interest arrive as JSON objects).
"""

from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import pytest

from research.platform.acquisition import (
    AcquiredDataset,
    AcquisitionError,
    BinancePublicClient,
    build_ohlcv_manifest,
    ingest_acquired_ohlcv,
    write_csv,
)
from research.platform.data_catalog import LicenseStatus
from research.platform.domain import DataResolution, Market


class _FakeResponse:
    """Minimal urlopen() stand-in carrying one canned payload."""

    def __init__(self, payload: Any, status: int = 200) -> None:
        if isinstance(payload, (bytes, bytearray)):
            self._body = bytes(payload)
        else:
            self._body = json.dumps(payload).encode("utf-8")
        self.status = status

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exception: object) -> bool:
        return False


class _NoSleepClock:
    """Records backoff sleeps instead of waiting."""

    def __init__(self) -> None:
        self.sleeps: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)


class _FrozenClock:
    """Deterministic fetch-timestamp injection."""

    @staticmethod
    def now(tz: timezone | None = None) -> datetime:
        return datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)


KLINES_OK = [
    [1700000000000, "100.0", "110.0", "99.0", "105.0", "12.5", "1700000059999", "1300.5", "42", "6.0", "650.25", "0"],
    [1700000060000, "105.0", "120.0", "104.0", "118.0", "13.5", "1700000119999", "1500.0", "51", "7.0", "735.0", "0"],
    [1700000120000, "118.0", "125.0", "117.0", "122.0", "9.0", "1700000179999", "1100.0", "30", "4.0", "440.0", "0"],
]
KLINES_NON_MONOTONIC = [
    [1700000060000, "1.0", "2.0", "0.5", "1.5", "1.0", "0", "0", "0", "0", "0", "0"],
    [1700000000000, "1.0", "2.0", "0.5", "1.5", "1.0", "0", "0", "0", "0", "0", "0"],
]
FUNDING_OK = [
    {"symbol": "BTCUSDT", "fundingTime": 1700006400000, "fundingRate": "0.0001", "markupRate": "0.00005"},
    {"symbol": "BTCUSDT", "fundingTime": 1700035200000, "fundingRate": "-0.0002", "markupRate": "0.00005"},
]
OPEN_INTEREST_OK = [
    {"symbol": "BTCUSDT", "sumOpenInterest": "100.5", "sumOpenInterestValue": "2000.25", "timestamp": 1700000000000},
    {"symbol": "BTCUSDT", "sumOpenInterest": "101.5", "sumOpenInterestValue": "2100.25", "timestamp": 1700000300000},
]


class _HttpStub:
    """Queued fake-urlopen helper: enqueue payloads or errors, inspect calls."""

    def __init__(self, calls: list[dict[str, Any]], queue: list[_FakeResponse | Exception]) -> None:
        self.calls = calls
        self._queue = queue

    def respond(self, payload: Any, status: int = 200) -> None:
        self._queue.append(_FakeResponse(payload, status))

    def respond_error(self, exception: Exception) -> None:
        self._queue.append(exception)


@pytest.fixture()
def http(monkeypatch: pytest.MonkeyPatch) -> _HttpStub:
    """Install a queued-responding fake urlopen and record every request."""
    calls: list[dict[str, Any]] = []
    queue: list[_FakeResponse | Exception] = []

    def fake_urlopen(request: urllib.request.Request, timeout: float | None = None):
        calls.append({"url": request.full_url, "method": request.get_method()})
        response = queue.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return _HttpStub(calls, queue)


def _fetched_klines(http, clock: _NoSleepClock | None = None):
    clock = clock or _NoSleepClock()
    http.respond(KLINES_OK)
    return BinancePublicClient().fetch_klines("BTCUSDT", "1m", clock=clock, now=_FrozenClock)


def test_fetch_klines_parses_documented_schema_into_ohlcv_frame(http) -> None:
    """Kline arrays parse to the exact acquired CSV schema with UTC index."""
    dataset = _fetched_klines(http)
    frame = dataset.frame
    assert list(frame.columns) == ["open", "high", "low", "close", "volume"]
    assert isinstance(frame.index, pd.DatetimeIndex) and str(frame.index.tz) == "UTC"
    assert [ts.isoformat() for ts in frame.index] == [
        "2023-11-14T22:13:20+00:00", "2023-11-14T22:14:20+00:00", "2023-11-14T22:15:20+00:00",
    ]
    assert frame.iloc[0]["close"] == 105.0 and frame.iloc[2]["volume"] == 9.0
    assert frame.attrs["quality_report"]["bars_checked"] == 3
    assert dataset.rows[0]["open_time"] == 1700000000000
    assert len(dataset.rows) == 3


def test_fetch_records_provider_endpoint_params_and_fetch_time(http) -> None:
    """Provenance metadata is complete, string-valued, and extra_metadata-safe."""
    dataset = _fetched_klines(http)
    provenance = dataset.provenance
    assert provenance["acquisition_provider"] == "binance"
    assert provenance["acquisition_endpoint"] == "/api/v3/klines"
    assert json.loads(provenance["acquisition_params_json"]) == {
        "symbol": "BTCUSDT", "interval": "1m", "limit": "1000",
    }
    assert provenance["acquisition_fetched_at"] == "2026-01-15T12:00:00+00:00"
    assert provenance["acquisition_auth"] == "none-public-endpoints"
    assert all(isinstance(value, str) for value in provenance.values())
    # The request actually went to the public spot host with GET and no auth header.
    assert http.calls[0]["url"].startswith("https://api.binance.com/api/v3/klines?")
    assert http.calls[0]["method"] == "GET"


def test_fetch_funding_rate_parses_object_rows(http) -> None:
    """Funding rows parse with UTC index, symbol and numeric rate."""
    http.respond(FUNDING_OK)
    dataset = BinancePublicClient().fetch_funding_rate("BTCUSDT", clock=_NoSleepClock(), now=_FrozenClock)
    frame = dataset.frame
    assert list(frame.columns) == ["symbol", "funding_rate"]
    assert dataset.provenance["acquisition_endpoint"] == "/fundingRate"
    assert frame.iloc[0]["funding_rate"] == 0.0001
    assert frame.iloc[1]["funding_rate"] == -0.0002
    assert [ts.isoformat() for ts in frame.index] == [
        "2023-11-15T00:00:00+00:00", "2023-11-15T08:00:00+00:00",
    ]


def test_fetch_open_interest_parses_statistics_rows(http) -> None:
    """Open-interest rows parse with both value columns in base and USD."""
    http.respond(OPEN_INTEREST_OK)
    dataset = BinancePublicClient().fetch_open_interest(
        "BTCUSDT", "5m", clock=_NoSleepClock(), now=_FrozenClock
    )
    frame = dataset.frame
    assert list(frame.columns) == ["symbol", "open_interest", "open_interest_usd"]
    assert dataset.provenance["acquisition_endpoint"] == "/futures/data/openInterestHist"
    assert frame.iloc[1]["open_interest"] == 101.5


def test_fetch_rejects_non_monotonic_kline_timestamps(http) -> None:
    """Out-of-order provider timestamps fail the fetch before any frame exists."""
    http.respond(KLINES_NON_MONOTONIC)
    with pytest.raises(AcquisitionError, match="strictly increasing"):
        BinancePublicClient().fetch_klines("BTCUSDT", "1m", clock=_NoSleepClock())


def test_fetch_rejects_non_monotonic_funding_timestamps(http) -> None:
    """The same monotonicity guard protects the object-row endpoints."""
    http.respond([
        {"symbol": "BTCUSDT", "fundingTime": 1700035200000, "fundingRate": "0.0001", "markupRate": "0.0"},
        {"symbol": "BTCUSDT", "fundingTime": 1700006400000, "fundingRate": "0.0002", "markupRate": "0.0"},
    ])
    with pytest.raises(AcquisitionError, match="strictly increasing"):
        BinancePublicClient().fetch_funding_rate("BTCUSDT", clock=_NoSleepClock())


def test_fetch_rejects_malformed_response_shapes(http) -> None:
    """Schema deviations raise instead of producing partial frames."""
    cases = [
        ({"not": "a list"}, "expected a JSON array"),
        ([[1, 2, 3]], "12-field kline array"),
        ([[1700000000000, "x", "1", "1", "1", "1", "0", "0", "0", "0", "0", "0"]], "not a number"),
        ([[1700000000000, "-5.0", "1", "1", "1", "1", "0", "0", "0", "0", "0", "0"]], "must be positive"),
        ([[1700000000000, "2.0", "1.0", "3.0", "1.0", "1.0", "0", "0", "0", "0", "0", "0"]], "inconsistent"),
        (b"<html>gateway error</html>", "not valid JSON"),
    ]
    for payload, message in cases:
        http.respond(payload)
        with pytest.raises(AcquisitionError, match=message.replace("(", "\\(").replace(")", "\\)")):
            BinancePublicClient().fetch_klines("BTCUSDT", "1m", clock=_NoSleepClock())

    # Object-row endpoints enforce their own required fields and timestamp type.
    http.respond([{"fundingTime": 1700006400000}])
    with pytest.raises(AcquisitionError, match="missing field: symbol"):
        BinancePublicClient().fetch_funding_rate("BTCUSDT", clock=_NoSleepClock())
    http.respond([{"symbol": "BTCUSDT", "fundingTime": "not-a-number", "fundingRate": "0.0001", "markupRate": "0.0"}])
    with pytest.raises(AcquisitionError, match="not an integer epoch millisecond"):
        BinancePublicClient().fetch_funding_rate("BTCUSDT", clock=_NoSleepClock())


def test_rate_limit_responses_trigger_sleep_based_backoff(http) -> None:
    """418/429 sleep exponentially and the fetch eventually succeeds."""
    clock = _NoSleepClock()
    http.respond_error(
        urllib.error.HTTPError(
            "https://api.binance.com/api/v3/klines", 429, "too many requests", {}, None
        )
    )
    http.respond_error(
        urllib.error.HTTPError(
            "https://api.binance.com/api/v3/klines", 418, "banned", {}, None
        )
    )
    dataset = _fetched_klines(http, clock)
    assert len(clock.sleeps) == 2
    assert clock.sleeps[0] == 2.0 and clock.sleeps[1] == 4.0
    assert len(dataset.frame) == 3


def test_persistent_rate_limiting_eventually_fails(http) -> None:
    """Continuous 429s exhaust the bounded attempts and raise."""
    clock = _NoSleepClock()
    for _ in range(10):
        http.respond_error(
            urllib.error.HTTPError(
                "https://api.binance.com/api/v3/klines", 429, "too many requests", {}, None
            )
        )
    with pytest.raises(AcquisitionError, match="stayed rate-limited"):
        BinancePublicClient().fetch_klines("BTCUSDT", "1m", clock=clock)
    assert len(clock.sleeps) == 4  # sleeps before attempts 2..5; none before the first


def test_non_rate_limit_http_errors_fail_immediately(http) -> None:
    """A 404 is not retried and surfaces as an acquisition failure."""
    http.respond_error(
        urllib.error.HTTPError(
            "https://api.binance.com/api/v3/klines", 404, "not found", {}, None
        )
    )
    with pytest.raises(AcquisitionError, match="HTTP 404"):
        BinancePublicClient().fetch_klines("BTCUSDT", "1m", clock=_NoSleepClock())
    assert len(http.calls) == 1


def test_fetch_klines_rejects_bad_arguments() -> None:
    """Client-side argument validation needs no network round trip."""
    with pytest.raises(ValueError, match="upper-case alphanumeric"):
        BinancePublicClient().fetch_klines("btc_usdt!", "1m")
    with pytest.raises(ValueError, match="unsupported kline interval"):
        BinancePublicClient().fetch_klines("BTCUSDT", "7m")
    with pytest.raises(ValueError, match="limit must be between"):
        BinancePublicClient().fetch_klines("BTCUSDT", "1m", limit=0)


def test_ingest_acquired_ohlcv_applies_platform_quality_gate(http) -> None:
    """The ingest path runs acquired frames through the adapters' validation."""
    dataset = _fetched_klines(http)
    ingested = ingest_acquired_ohlcv(dataset.frame)
    assert ingested.attrs["quality_report"]["bars_checked"] == 3


def test_ingest_gate_rejects_acquired_bad_row(http) -> None:
    """A corrupted acquired row cannot pass into the research pipeline."""
    dataset = _fetched_klines(http)
    corrupted = dataset.frame.copy()
    corrupted.iloc[1, corrupted.columns.get_loc("low")] = -1.0
    with pytest.raises(ValueError, match="prices must be positive"):
        ingest_acquired_ohlcv(corrupted)


def test_ingest_gate_rejects_duplicate_acquired_timestamps(http) -> None:
    """Duplicated acquisition rows are rejected, never silently repaired."""
    dataset = _fetched_klines(http)
    duplicated = pd.concat([dataset.frame, dataset.frame.iloc[[0]]])
    with pytest.raises(ValueError, match="duplicate timestamps"):
        ingest_acquired_ohlcv(duplicated)


def test_write_csv_round_trip_through_ingest_gate(http, tmp_path) -> None:
    """write_csv → read_csv → ingest is the supported path back into the platform."""
    dataset = _fetched_klines(http)
    path = tmp_path / "btcusdt_1m.csv"
    assert write_csv(dataset, str(path)) == str(path)
    persisted = path.read_text().splitlines()
    assert persisted[0] == "timestamp,open,high,low,close,volume"
    reingested = ingest_acquired_ohlcv(pd.read_csv(path))
    assert len(reingested) == 3
    assert reingested.attrs["quality_report"]["bars_checked"] == 3
    assert [ts.isoformat() for ts in reingested.index] == [ts.isoformat() for ts in dataset.frame.index]


def test_write_csv_requires_timestamp_index() -> None:
    """Persistence refuses frames that would silently lose their timestamps."""
    stripped = AcquiredDataset(
        kind="klines",
        frame=pd.DataFrame({"open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0], "volume": [1.0]}),
        rows=(),
        provenance={},
    )
    with pytest.raises(ValueError, match="timestamp.*DatetimeIndex"):
        write_csv(stripped, "/tmp/should-not-be-written.csv")


def test_build_ohlcv_manifest_carries_provenance_and_quality(http) -> None:
    """The manifest embeds fetch provenance and the gate's quality report."""
    dataset = _fetched_klines(http)
    manifest = build_ohlcv_manifest(
        dataset,
        dataset_id="crypto-binance-BTCUSDT-1m-fixture",
        symbol="BTCUSDT",
        resolution=DataResolution.ONE_MINUTE,
        timezone_name="UTC",
        license_reference="binance terms of use - review pending",
    )
    assert manifest.market is Market.CRYPTO and manifest.exchange == "BINANCE"
    assert manifest.provider == "binance"
    assert manifest.license_status is LicenseStatus.REVIEW_REQUIRED
    assert manifest.coverage_start == datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc)
    assert manifest.coverage_end == datetime(2023, 11, 14, 22, 15, 20, tzinfo=timezone.utc)
    assert manifest.extra_metadata["acquisition_provider"] == "binance"
    assert json.loads(manifest.extra_metadata["acquisition_params_json"])["symbol"] == "BTCUSDT"
    assert json.loads(manifest.extra_metadata["quality_report_json"])["bars_checked"] == 3
    assert all(isinstance(value, str) for value in manifest.extra_metadata.values())
    # Provenance metadata composes with the F-010 gap audit on the same manifest.
    from research.platform.data_catalog import gap_audit, manifest_with_gap_audit

    audited = manifest_with_gap_audit(manifest, dataset.frame)
    gap_record = json.loads(audited.extra_metadata["gap_audit_json"])
    assert gap_record["actual_bars"] == 3
    assert audited.extra_metadata["acquisition_endpoint"] == "/api/v3/klines"


def test_build_ohlcv_manifest_refuses_non_kline_datasets() -> None:
    """OHLCV manifests are only built for kline acquisitions."""
    funding_dataset = AcquiredDataset(
        kind="funding_rate",
        frame=pd.DataFrame(
            {"symbol": ["BTCUSDT"], "funding_rate": [0.0001]},
            index=pd.DatetimeIndex([datetime(2026, 1, 1, tzinfo=timezone.utc)], name="timestamp"),
        ),
        rows=(),
        provenance={},
    )
    with pytest.raises(ValueError, match="klines acquisition"):
        build_ohlcv_manifest(
            funding_dataset,
            dataset_id="x",
            symbol="BTCUSDT",
            resolution=DataResolution.ONE_MINUTE,
            timezone_name="UTC",
            license_reference="ref",
        )
