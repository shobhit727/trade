"""WSGI API tests proving dashboard operations use persisted experiment records."""

from __future__ import annotations

import io
import json
from urllib.parse import urlsplit

from research.platform.api import DASHBOARD_HTML, ResearchAPI
from research.platform.storage import ExperimentStore


def _payload(**updates: object) -> dict[str, object]:
    # Supply an explicit timezone and chronological windows for the experiment contract.
    value: dict[str, object] = {
        "experiment_id": "api-nse-test-001",
        "market": "nse",
        "track": "nse_individual",
        "algorithm_family": "random_search",
        "resolution": "1d",
        "dataset_ids": ["api-fixture-data-v1"],
        "random_seed": 42,
        "git_commit": "0123456789abcdef0123456789abcdef01234567",
        "code_version": "api-test",
        "training_start": "2010-01-01T00:00:00+00:00",
        "training_end": "2015-01-01T00:00:00+00:00",
        "validation_start": "2015-01-01T00:00:00+00:00",
        "validation_end": "2018-01-01T00:00:00+00:00",
        "oos_start": "2026-10-02T00:00:00+00:00",
        "oos_end": "2026-10-16T00:00:00+00:00",
        "final_holdout_start": "2026-10-16T00:00:00+00:00",
        "final_holdout_end": "2026-11-08T00:00:00+00:00",
        "cost_model_id": "nse-delivery-test",
        "execution_model_id": "next-open-test",
        "objectives": ["net_return", "max_drawdown"],
        "parameters": {"budget": 20},
        "compute_backend": "numpy",
        "compute_device": "test-cpu",
    }
    value.update(updates)
    return value


def _dataset_payload(**updates: object) -> dict[str, object]:
    # This synthetic manifest has explicit provenance and a declared approved test licence.
    value: dict[str, object] = {
        "dataset_id": "api-fixture-data-v1",
        "market": "nse",
        "provider": "synthetic-test-provider",
        "source": "synthetic-test-fixture",
        "instrument": "TEST",
        "exchange": "NSE",
        "category": "ohlcv",
        "resolution": "1d",
        "coverage_start": "2010-01-01T00:00:00+00:00",
        "coverage_end": "2026-11-09T00:00:00+00:00",
        "timezone": "UTC",
        "timestamp_convention": "bar-close-time",
        "acquired_at": "2026-11-08T00:00:00+00:00",
        "update_frequency": "daily",
        "license_status": "approved",
        "license_reference": "test-only-approved-licence",
        "value_origin": "observed",
        "quality_score": 1.0,
        "known_gaps": [],
        "adjustment_method": "none",
        "processing_history": ["synthetic unit-test fixture"],
        "schema_version": "1",
        "extra_metadata": {"synthetic": "true"},
    }
    value.update(updates)
    return value


def _request(app: ResearchAPI, method: str, path: str, payload: object | None = None):
    # Call the WSGI app directly without binding a network socket in the test suite.
    body = b"" if payload is None else json.dumps(payload).encode("utf-8")
    parsed_path = urlsplit(path)
    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": parsed_path.path,
        "QUERY_STRING": parsed_path.query,
        "CONTENT_TYPE": "application/json" if payload is not None else "",
        "CONTENT_LENGTH": str(len(body)),
        "wsgi.input": io.BytesIO(body),
    }
    captured: dict[str, object] = {}

    def start_response(status: str, headers: list[tuple[str, str]]) -> None:
        # Save the HTTP status and response headers for assertions.
        captured["status"] = status
        captured["headers"] = dict(headers)

    response = b"".join(app(environ, start_response))
    return int(str(captured["status"]).split(" ", 1)[0]), dict(captured["headers"]), response


def test_research_api_health_markets_and_dashboard(tmp_path) -> None:
    # The API uses a dedicated research SQLite database.
    app = ResearchAPI(ExperimentStore(tmp_path / "research.sqlite3"))
    status, headers, body = _request(app, "GET", "/api/health")
    assert status == 200
    assert json.loads(body) == {"status": "ok"}
    assert headers["Cache-Control"] == "no-store"

    status, _, body = _request(app, "GET", "/api/markets")
    assert status == 200
    markets = json.loads(body)["markets"]
    assert [item["market"] for item in markets] == ["nse", "crypto"]
    assert markets[0]["initial_simulated_capital"] == "2100000.00"
    assert markets[1]["initial_simulated_capital"] == "2100000.00"

    status, headers, body = _request(app, "GET", "/")
    assert status == 200
    assert "text/html" in headers["Content-Type"]
    assert b"Create experiment" in body
    assert "Loading experiments" in DASHBOARD_HTML


def test_research_api_creates_and_lists_real_experiment_records(tmp_path) -> None:
    # Creating an experiment persists immutable metadata and an audit event.
    store = ExperimentStore(tmp_path / "research.sqlite3")
    app = ResearchAPI(store)
    status, _, body = _request(app, "POST", "/api/datasets", _dataset_payload())
    assert status == 201
    registered = json.loads(body)
    assert registered["status"] == "manifest_registered_not_data_uploaded"

    status, _, body = _request(app, "GET", "/api/datasets?market=nse")
    assert status == 200
    datasets = json.loads(body)["datasets"]
    assert len(datasets) == 1
    assert datasets[0]["coverage_start"] == "2010-01-01T00:00:00+00:00"
    assert datasets[0]["license_status"] == "approved"
    assert datasets[0]["provider"] == "synthetic-test-provider"

    status, _, body = _request(app, "POST", "/api/experiments", _payload())
    assert status == 201
    created = json.loads(body)
    assert created["status"] == "created_not_started"

    status, _, body = _request(app, "GET", "/api/experiments")
    assert status == 200
    experiments = json.loads(body)["experiments"]
    assert len(experiments) == 1
    assert experiments[0]["market"] == "nse"

    status, _, body = _request(app, "GET", "/api/experiments/api-nse-test-001")
    assert status == 200
    detail = json.loads(body)
    assert detail["experiment"]["fingerprint"] == created["fingerprint"]
    assert detail["events"][0]["event_type"] == "experiment_created"


def test_research_api_market_filter_and_cross_market_rejection(tmp_path) -> None:
    # Market filters keep financial records separate and track validation rejects mixing.
    store = ExperimentStore(tmp_path / "research.sqlite3")
    app = ResearchAPI(store)
    assert _request(app, "POST", "/api/datasets", _dataset_payload())[0] == 201
    _request(app, "POST", "/api/experiments", _payload())
    status, _, body = _request(app, "GET", "/api/experiments")
    assert status == 200
    assert len(json.loads(body)["experiments"]) == 1

    status, _, body = _request(app, "GET", "/api/experiments?market=crypto")
    assert status == 200
    assert json.loads(body)["experiments"] == []

    status, _, body = _request(app, "GET", "/api/experiments?market=invalid")
    assert status == 400
    assert "market must be" in json.loads(body)["error"]

    bad = _payload(market="crypto")
    status, _, body = _request(app, "POST", "/api/experiments", bad)
    assert status == 400
    assert "does not belong" in json.loads(body)["error"]


def test_research_api_duplicate_record_returns_conflict(tmp_path) -> None:
    # Duplicate experiment IDs are conflicts, not silent overwrites.
    app = ResearchAPI(ExperimentStore(tmp_path / "research.sqlite3"))
    payload = _payload()
    assert _request(app, "POST", "/api/datasets", _dataset_payload())[0] == 201
    assert _request(app, "POST", "/api/experiments", payload)[0] == 201
    status, _, body = _request(app, "POST", "/api/experiments", payload)
    assert status == 409
    assert "record conflict" in json.loads(body)["error"]


def test_research_api_rejects_invalid_timezones_and_non_json_content(tmp_path) -> None:
    # API inputs without timezone offsets are rejected to avoid ambiguous timestamp joins.
    app = ResearchAPI(ExperimentStore(tmp_path / "research.sqlite3"))
    payload = _payload(training_start="2010-01-01T00:00:00")
    status, _, body = _request(app, "POST", "/api/experiments", payload)
    assert status == 400
    assert "timezone offset" in json.loads(body)["error"]

    environ = {
        "REQUEST_METHOD": "POST",
        "PATH_INFO": "/api/experiments",
        "QUERY_STRING": "",
        "CONTENT_TYPE": "text/plain",
        "CONTENT_LENGTH": "2",
        "wsgi.input": io.BytesIO(b"{}"),
    }
    captured: dict[str, str] = {}

    def start_response(status: str, headers: list[tuple[str, str]]) -> None:
        # Save status for the unsupported media-type assertion.
        captured["status"] = status

    b"".join(app(environ, start_response))
    assert captured["status"].startswith("415")



def test_research_api_blocks_unapproved_and_insufficient_dataset_coverage(tmp_path) -> None:
    # Research jobs cannot silently consume unlicensed or temporally incomplete datasets.
    app = ResearchAPI(ExperimentStore(tmp_path / "research.sqlite3"))
    unapproved = _dataset_payload(
        dataset_id="review-required-v1",
        license_status="review_required",
        license_reference="pending-review",
    )
    assert _request(app, "POST", "/api/datasets", unapproved)[0] == 201
    status, _, body = _request(
        app,
        "POST",
        "/api/experiments",
        _payload(dataset_ids=["review-required-v1"]),
    )
    assert status == 400
    assert "licence must be approved" in json.loads(body)["error"]

    insufficient = _dataset_payload(
        dataset_id="short-history-v1",
        coverage_end="2025-01-01T00:00:00+00:00",
    )
    assert _request(app, "POST", "/api/datasets", insufficient)[0] == 201
    status, _, body = _request(
        app,
        "POST",
        "/api/experiments",
        _payload(dataset_ids=["short-history-v1"]),
    )
    assert status == 400
    assert "does not cover requested window" in json.loads(body)["error"]


def test_research_api_rejects_cross_market_dataset_reference(tmp_path) -> None:
    # Even an approved crypto manifest cannot be attached to an NSE experiment.
    app = ResearchAPI(ExperimentStore(tmp_path / "research.sqlite3"))
    crypto_manifest = _dataset_payload(
        dataset_id="crypto-fixture-v1",
        market="crypto",
        exchange="BINANCE",
        instrument="BTCUSDT",
    )
    assert _request(app, "POST", "/api/datasets", crypto_manifest)[0] == 201
    status, _, body = _request(
        app,
        "POST",
        "/api/experiments",
        _payload(dataset_ids=["crypto-fixture-v1"]),
    )
    assert status == 400
    assert "cross-market dataset rejected" in json.loads(body)["error"]



def test_research_api_exposes_registered_existing_strategy_catalogue(tmp_path) -> None:
    # The dashboard receives actual strategy implementations and typed search metadata.
    app = ResearchAPI(ExperimentStore(tmp_path / "research.sqlite3"))
    status, _, body = _request(app, "GET", "/api/strategies?limit=500")
    assert status == 200
    payload = json.loads(body)
    assert payload["strategy_count"] >= 1
    strategies = payload["strategies"]
    assert any(item["name"] == "absolute_momentum" for item in strategies)
    absolute = next(item for item in strategies if item["name"] == "absolute_momentum")
    assert absolute["strategy_class"]
    assert isinstance(absolute["parameters"], list)


def test_research_api_validates_selected_existing_strategy_name(tmp_path) -> None:
    # Existing-strategy experiment metadata must name a real registered catalogue entry.
    app = ResearchAPI(ExperimentStore(tmp_path / "research.sqlite3"))
    assert _request(app, "POST", "/api/datasets", _dataset_payload())[0] == 201
    valid = _payload(
        algorithm_family="existing_strategy",
        parameters={"strategy_name": "absolute_momentum"},
    )
    status, _, body = _request(app, "POST", "/api/experiments", valid)
    assert status == 201
    assert json.loads(body)["status"] == "created_not_started"

    invalid = _payload(
        experiment_id="api-invalid-strategy",
        algorithm_family="existing_strategy",
        parameters={"strategy_name": "not-registered"},
    )
    status, _, body = _request(app, "POST", "/api/experiments", invalid)
    assert status == 400
    assert "unknown existing strategy" in json.loads(body)["error"]
