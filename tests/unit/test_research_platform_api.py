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
        "parameters": {
            "strategy_name": "absolute_momentum",
            "strategy_parameters": {"period": 10, "threshold": 0.0},
            "execution_assumptions": {
                "slippage_bps": 5,
                "impact_coefficient_bps": 10,
                "max_participation": 0.05,
                "max_gross_exposure": 1.0,
                "periods_per_year": 252,
            },
            "optimization": {
                "budget": 20,
                "validation_candidates": 5,
                "objective": "sharpe",
                "points_per_numeric_dimension": 2,
                "population_size": 4,
                "generations": 4,
                "mutation": 0.7,
                "crossover": 0.8,
                "startup_trials": 5,
                "good_fraction": 0.2,
            },
        },
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
    assert "Purging embargo (seconds)" in DASHBOARD_HTML
    assert "Loading experiments" in DASHBOARD_HTML
    # Resolution choices and annualisation are explicit for both market calendars.
    assert "const resolutionsByMarket = {" in DASHBOARD_HTML
    assert 'nse: [' in DASHBOARD_HTML and 'crypto: [' in DASHBOARD_HTML
    assert "function updatePeriodsPerYear()" in DASHBOARD_HTML
    assert '["1d", 252]' in DASHBOARD_HTML and '["1d", 365]' in DASHBOARD_HTML
    assert '["1s", 31536000]' in DASHBOARD_HTML
    assert '["order_book_event"' not in DASHBOARD_HTML
    # The default NSE OOS and holdout windows must respect the exposed historical TEST boundary.
    assert 'id="oos-start" type="datetime-local" value="2026-10-02T00:00"' in DASHBOARD_HTML
    assert 'id="oos-end" type="datetime-local" value="2026-10-16T00:00"' in DASHBOARD_HTML
    assert 'id="hold-start" type="datetime-local" value="2026-10-16T00:00"' in DASHBOARD_HTML


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



def test_research_api_rejects_embargo_that_partitions_do_not_respect(tmp_path) -> None:
    # API callers cannot declare an embargo that the chronological partition dates violate.
    app = ResearchAPI(ExperimentStore(tmp_path / "research.sqlite3"))
    assert _request(app, "POST", "/api/datasets", _dataset_payload())[0] == 201
    status, _, body = _request(
        app,
        "POST",
        "/api/experiments",
        _payload(embargo_seconds=60),
    )
    assert status == 400
    assert "respect embargo" in json.loads(body)["error"]



def test_api_creates_validated_genetic_programming_experiment(tmp_path) -> None:
    # GP settings are stored with the experiment and protected by its immutable fingerprint.
    app = ResearchAPI(ExperimentStore(tmp_path / "gp-api.sqlite3"))
    status, _, _ = _request(app, "POST", "/api/datasets", _dataset_payload())
    assert status == 201
    parameters = {
        "execution_assumptions": {
            "slippage_bps": 5,
            "impact_coefficient_bps": 10,
            "max_participation": 0.05,
            "max_gross_exposure": 1.0,
            "periods_per_year": 252,
        },
        "genetic_programming": {
            "population_size": 4,
            "generations": 1,
            "max_depth": 3,
            "max_nodes": 15,
            "mutation_rate": 0.2,
            "validation_candidates": 2,
            "objective": "sharpe",
            "feature_windows": [3, 5],
        },
    }
    status, _, body = _request(
        app,
        "POST",
        "/api/experiments",
        _payload(
            experiment_id="api-genetic-programming",
            algorithm_family="genetic_programming",
            parameters=parameters,
        ),
    )
    assert status == 201
    payload = json.loads(body)
    assert payload["experiment_id"] == "api-genetic-programming"
    stored = app.store.get_experiment(payload["experiment_id"])
    assert stored["spec"]["algorithm_family"] == "genetic_programming"
    assert stored["spec"]["parameters"]["genetic_programming"]["feature_windows"] == [3, 5]


def test_api_rejects_unbounded_genetic_programming_budget(tmp_path) -> None:
    # Candidate count is bounded before a worker can allocate an excessive GP population.
    app = ResearchAPI(ExperimentStore(tmp_path / "gp-budget-api.sqlite3"))
    status, _, _ = _request(app, "POST", "/api/datasets", _dataset_payload())
    assert status == 201
    parameters = {
        "genetic_programming": {
            "population_size": 1000,
            "generations": 20,
            "max_depth": 3,
            "max_nodes": 15,
            "mutation_rate": 0.2,
            "validation_candidates": 2,
            "objective": "sharpe",
            "feature_windows": [3],
        }
    }
    status, _, body = _request(
        app,
        "POST",
        "/api/experiments",
        _payload(
            experiment_id="api-genetic-programming-too-large",
            algorithm_family="genetic_programming",
            parameters=parameters,
        ),
    )
    assert status == 400
    assert "10000 evaluation limit" in json.loads(body)["error"]


def test_experiment_comparison_is_market_scoped_and_keeps_partition_metrics_separate(tmp_path) -> None:
    # The comparison endpoint presents candidate records without combining portfolios.
    from research.platform.api import ResearchAPI
    from research.platform.storage import ExperimentStore

    store = ExperimentStore(tmp_path / "compare.sqlite3")
    app = ResearchAPI(store)
    assert _request(app, "POST", "/api/datasets", _dataset_payload())[0] == 201

    first = _payload(experiment_id="compare-nse-one")
    second = _payload(experiment_id="compare-nse-two", random_seed=43)
    assert _request(app, "POST", "/api/experiments", first)[0] == 201
    assert _request(app, "POST", "/api/experiments", second)[0] == 201

    for experiment_id, suffix in ((first["experiment_id"], "a"), (second["experiment_id"], "b")):
        store.append_candidate(
            candidate_id=f"candidate-{suffix}",
            experiment_id=experiment_id,
            candidate_digest=(suffix * 64),
            family="random_search_selected_oos",
            generation=0,
            parameters={"strategy_name": "absolute_momentum"},
            metrics={
                "train": {"sharpe": 0.2},
                "validation": {"sharpe": 0.1},
                "out_of_sample": {"sharpe": -0.05},
            },
            lineage={"parent_candidate_ids": []},
        )

    status, _, body = _request(
        app,
        "GET",
        f"/api/compare?experiment_id={first['experiment_id']}&experiment_id={second['experiment_id']}",
    )
    result = json.loads(body)
    assert status == 200
    assert result["market"] == "nse"
    assert result["candidate_count"] == 2
    assert result["aggregation"].startswith("none")
    assert result["candidates"][0]["metrics"]["out_of_sample"]["sharpe"] == -0.05


def test_experiment_comparison_rejects_mixed_market_ids(tmp_path) -> None:
    # NSE and crypto remain separate even when candidate metrics share the same schema.
    from research.platform.api import ResearchAPI
    from research.platform.storage import ExperimentStore

    store = ExperimentStore(tmp_path / "compare-markets.sqlite3")
    app = ResearchAPI(store)
    nse_manifest = _dataset_payload()
    crypto_manifest = _dataset_payload(
        dataset_id="api-crypto-fixture-v1",
        market="crypto",
        exchange="BINANCE",
        instrument="BTCINR",
    )
    assert _request(app, "POST", "/api/datasets", nse_manifest)[0] == 201
    assert _request(app, "POST", "/api/datasets", crypto_manifest)[0] == 201

    nse = _payload(experiment_id="compare-market-nse")
    crypto = _payload(
        experiment_id="compare-market-crypto",
        market="crypto",
        track="crypto_individual",
        dataset_ids=["api-crypto-fixture-v1"],
    )
    assert _request(app, "POST", "/api/experiments", nse)[0] == 201
    assert _request(app, "POST", "/api/experiments", crypto)[0] == 201

    status, _, body = _request(
        app,
        "GET",
        f"/api/compare?experiment_id={nse['experiment_id']}&experiment_id={crypto['experiment_id']}",
    )
    result = json.loads(body)
    assert status == 400
    assert "cannot be compared in one financial view" in result["error"]



def test_api_creates_validated_pareto_search_experiment(tmp_path) -> None:
    # Pareto objectives and directions are part of the immutable experiment specification.
    app = ResearchAPI(ExperimentStore(tmp_path / "pareto-api.sqlite3"))
    status, _, _ = _request(app, "POST", "/api/datasets", _dataset_payload())
    assert status == 201
    parameters = {
        "strategy_name": "absolute_momentum",
        "strategy_parameters": {"period": 10, "threshold": 0.0},
        "execution_assumptions": {
            "slippage_bps": 5,
            "impact_coefficient_bps": 10,
            "max_participation": 0.05,
            "max_gross_exposure": 1.0,
            "periods_per_year": 252,
        },
        "pareto_search": {
            "population_size": 4,
            "generations": 1,
            "mutation_rate": 0.2,
            "validation_candidates": 3,
            "objectives": ["cagr", "max_drawdown", "turnover"],
            "directions": ["max", "max", "min"],
        },
    }
    status, _, body = _request(
        app,
        "POST",
        "/api/experiments",
        _payload(
            experiment_id="api-pareto-search",
            algorithm_family="pareto_search",
            parameters=parameters,
        ),
    )
    assert status == 201
    payload = json.loads(body)
    assert payload["experiment_id"] == "api-pareto-search"
    stored = app.store.get_experiment(payload["experiment_id"])
    assert stored["spec"]["algorithm_family"] == "pareto_search"
    assert stored["spec"]["parameters"]["pareto_search"]["objectives"] == [
        "cagr", "max_drawdown", "turnover"
    ]


def test_api_rejects_single_objective_pareto_experiment(tmp_path) -> None:
    # The API refuses scalar optimisation disguised as Pareto search.
    app = ResearchAPI(ExperimentStore(tmp_path / "pareto-invalid-api.sqlite3"))
    status, _, _ = _request(app, "POST", "/api/datasets", _dataset_payload())
    assert status == 201
    parameters = {
        "strategy_name": "absolute_momentum",
        "execution_assumptions": {
            "slippage_bps": 5,
            "impact_coefficient_bps": 10,
            "max_participation": 0.05,
            "max_gross_exposure": 1.0,
            "periods_per_year": 252,
        },
        "pareto_search": {
            "population_size": 4,
            "generations": 1,
            "mutation_rate": 0.2,
            "validation_candidates": 2,
            "objectives": ["cagr"],
            "directions": ["max"],
        },
    }
    status, _, body = _request(
        app,
        "POST",
        "/api/experiments",
        _payload(
            experiment_id="api-pareto-single-objective",
            algorithm_family="pareto_search",
            parameters=parameters,
        ),
    )
    assert status == 400
    assert "2+ unique objectives" in json.loads(body)["error"]



def test_api_creates_hybrid_optimizer_experiment_with_method_budgets(tmp_path) -> None:
    # The method list and sub-budgets are frozen as part of the hybrid experiment spec.
    app = ResearchAPI(ExperimentStore(tmp_path / "hybrid-api.sqlite3"))
    status, _, _ = _request(app, "POST", "/api/datasets", _dataset_payload())
    assert status == 201
    parameters = {
        "strategy_name": "absolute_momentum",
        "strategy_parameters": {"period": 10, "threshold": 0.0},
        "execution_assumptions": {
            "slippage_bps": 5,
            "impact_coefficient_bps": 10,
            "max_participation": 0.05,
            "max_gross_exposure": 1.0,
            "periods_per_year": 252,
        },
        "hybrid_optimization": {
            "methods": ["random_search", "differential_evolution", "bayesian"],
            "budget_per_method": 8,
            "validation_candidates": 4,
            "objective": "sharpe",
            "de_population_size": 4,
            "de_generations": 1,
            "de_mutation": 0.7,
            "de_crossover": 0.8,
            "tpe_startup_trials": 3,
        },
    }
    status, _, body = _request(
        app,
        "POST",
        "/api/experiments",
        _payload(
            experiment_id="api-hybrid-ensemble",
            algorithm_family="hybrid",
            parameters=parameters,
        ),
    )
    assert status == 201
    payload = json.loads(body)
    assert payload["experiment_id"] == "api-hybrid-ensemble"
    stored = app.store.get_experiment(payload["experiment_id"])
    assert stored["spec"]["algorithm_family"] == "hybrid"
    assert stored["spec"]["parameters"]["hybrid_optimization"]["methods"] == [
        "random_search", "differential_evolution", "bayesian"
    ]


def test_api_rejects_hybrid_de_budget_mismatch(tmp_path) -> None:
    # DE population/generation settings must consume exactly the declared per-method budget.
    app = ResearchAPI(ExperimentStore(tmp_path / "hybrid-invalid-api.sqlite3"))
    status, _, _ = _request(app, "POST", "/api/datasets", _dataset_payload())
    assert status == 201
    parameters = {
        "strategy_name": "absolute_momentum",
        "execution_assumptions": {
            "slippage_bps": 5,
            "impact_coefficient_bps": 10,
            "max_participation": 0.05,
            "max_gross_exposure": 1.0,
            "periods_per_year": 252,
        },
        "hybrid_optimization": {
            "methods": ["random_search", "differential_evolution"],
            "budget_per_method": 8,
            "validation_candidates": 3,
            "objective": "sharpe",
            "de_population_size": 4,
            "de_generations": 2,
            "de_mutation": 0.7,
            "de_crossover": 0.8,
        },
    }
    status, _, body = _request(
        app,
        "POST",
        "/api/experiments",
        _payload(
            experiment_id="api-hybrid-bad-de-budget",
            algorithm_family="hybrid",
            parameters=parameters,
        ),
    )
    assert status == 400
    assert "must equal budget_per_method" in json.loads(body)["error"]
