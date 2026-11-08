"""WSGI API tests proving dashboard operations use persisted experiment records."""

from __future__ import annotations

import io
import json
from urllib.parse import urlsplit
from datetime import datetime, timezone

from research.platform.api import DASHBOARD_HTML, ResearchAPI
from research.platform.storage import ExperimentStore


UTC = timezone.utc


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
        "oos_start": "2018-01-01T00:00:00+00:00",
        "oos_end": "2020-01-01T00:00:00+00:00",
        "final_holdout_start": "2020-01-01T00:00:00+00:00",
        "final_holdout_end": "2022-01-01T00:00:00+00:00",
        "cost_model_id": "nse-delivery-test",
        "execution_model_id": "next-open-test",
        "objectives": ["net_return", "max_drawdown"],
        "parameters": {"budget": 20},
        "compute_backend": "numpy",
        "compute_device": "test-cpu",
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
