"""WSGI API tests proving dashboard operations use persisted experiment records."""

from __future__ import annotations

import io
import json
from urllib.parse import urlsplit

from research.platform.api import DASHBOARD_HTML, ResearchAPI
from research.platform.storage import ExperimentStore
from tests.unit.test_research_platform import make_experiment


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


def test_f030_experiment_compare_returns_complete_comparable_records(tmp_path) -> None:
    # F-030: the comparison endpoint returns every comparable field from the same
    # stored record types, with explicit nulls where a record was never stored.
    store = ExperimentStore(tmp_path / "f030-compare.sqlite3")
    app = ResearchAPI(store)
    assert _request(app, "POST", "/api/datasets", _dataset_payload())[0] == 201

    first = _payload(experiment_id="f030-nse-one", random_seed=42)
    second = _payload(experiment_id="f030-nse-two", random_seed=43)
    assert _request(app, "POST", "/api/experiments", first)[0] == 201
    assert _request(app, "POST", "/api/experiments", second)[0] == 201

    # Candidate rows in two generations with one failure and a mixed family set.
    for experiment_id, digest_prefix in (
        (first["experiment_id"], "1"),
        (second["experiment_id"], "2"),
    ):
        for generation in range(2):
            for index in range(2):
                if (generation + index) % 2 == 0:
                    metrics = {"train_fitness": 0.25 * (generation + 1), "train": {"sharpe": 0.1}}
                else:
                    metrics = {"status": "failed"}
                store.append_candidate(
                    candidate_id=f"{experiment_id}-g{generation}-{index}",
                    experiment_id=experiment_id,
                    candidate_digest=f"{digest_prefix}{generation}{index}".ljust(16, "0") * 4,
                    family="genetic_programming",
                    generation=generation,
                    parameters={"expression": {"op": f"tree-{index}"}, "feature_windows": [5]},
                    metrics=metrics,
                    lineage={
                        "operator": "subtree_crossover_then_mutation" if index == 0 else "elitism",
                        "parent_candidate_ids": [],
                    },
                )
        store.append_event(
            experiment_id,
            "genetic_programming_oos_recorded",
            {"oos_metrics": {"sharpe": 0.2}, "final_holdout_accessed": False},
        )

    status, _, body = _request(
        app,
        "GET",
        "/api/experiments/compare?ids=f030-nse-one,f030-nse-two",
    )
    assert status == 200
    result = json.loads(body)
    assert result["market"] == "nse"
    assert result["experiment_ids"] == ["f030-nse-one", "f030-nse-two"]
    assert len(result["comparisons"]) == 2

    for comparison in result["comparisons"]:
        # Every comparison field comes from one stored record type; the provenance
        # list names those record types explicitly.
        assert comparison["source_record_types"] == [
            "experiments", "experiment_events", "candidates",
        ]
        assert comparison["spec"]["experiment_id"] == comparison["experiment_id"]
        assert comparison["candidate_count"] == 4
        assert comparison["generation_count"] == 1
        assert comparison["families"] == ["genetic_programming"]
        # No OOS acceptance policy event was stored, so the field is an explicit
        # null rather than a fabricated pass/fail.
        assert comparison["oos_acceptance"] is None
        assert comparison["environment"] is None
        assert comparison["classification_distribution"] == {}

    first_record = result["comparisons"][0]
    second_record = result["comparisons"][1]
    assert first_record["fingerprint"] != second_record["fingerprint"]
    assert first_record["market"] == second_record["market"] == "nse"

    # F-030 fallback: GP-family verdicts live only in job result_json, so the
    # compare record falls back to the latest stored job result for both the
    # classification distribution and the OOS acceptance, and names the source.
    assert _request(app, "POST", "/api/experiments", _payload(experiment_id="f030-gp"))[0] == 201
    store.create_job(
        job_id="f030-gp-job",
        experiment_id="f030-gp",
        runner_name="genetic_programming",
        parameters={},
    )
    store.update_job_status("f030-gp-job", "running")
    store.update_job_status("f030-gp-job", "succeeded", result={
        "classification": "requires_independent_confirmation",
        "oos_acceptance": {"outcome": "pass", "policy_version": "v1-2026-11-10", "reasons": []},
    })
    status, _, body = _request(app, "GET", "/api/experiments/compare?ids=f030-gp,f030-nse-one")
    assert status == 200
    comparisons = json.loads(body)["comparisons"]
    gp_record = next(item for item in comparisons if item["experiment_id"] == "f030-gp")
    assert gp_record["classification_distribution"] == {"requires_independent_confirmation": 1}
    assert gp_record["oos_acceptance"]["source"] == "job_result"
    assert gp_record["oos_acceptance"]["payload"]["outcome"] == "pass"
    assert "jobs.result_json" in gp_record["source_record_types"]
    # The event-backed record keeps its event-sourced values and stays null-free
    # in the fields the events never stored (environment: no jobs ran either).
    event_record = next(item for item in comparisons if item["experiment_id"] == "f030-nse-one")
    assert event_record["oos_acceptance"] is None
    assert event_record["classification_distribution"] == {}
    assert "jobs.result_json" not in event_record["source_record_types"]

    # Validation: fewer than two ids, duplicate ids, and mixed markets all fail.
    status, _, body = _request(app, "GET", "/api/experiments/compare?ids=f030-nse-one")
    assert status == 400
    assert "between 2 and 10" in json.loads(body)["error"]

    status, _, body = _request(
        app, "GET", "/api/experiments/compare?ids=f030-nse-one,f030-nse-one",
    )
    assert status == 400
    assert "must be unique" in json.loads(body)["error"]

    status, _, body = _request(app, "GET", "/api/experiments/compare?ids=f030-gp,f030-nse-one")
    assert status == 200  # same-market sanity before the mixed-market check below

    # Mixed-market comparison must fail on the new route too (the legacy
    # /api/compare guard has its own test; this one is route-specific).
    assert _request(app, "POST", "/api/datasets", _dataset_payload(
        dataset_id="f030-crypto-fixture-v1",
        market="crypto",
        exchange="BINANCE",
        instrument="BTCINR",
    ))[0] == 201
    assert _request(app, "POST", "/api/experiments", _payload(
        experiment_id="f030-crypto",
        market="crypto",
        track="crypto_individual",
        dataset_ids=["f030-crypto-fixture-v1"],
    ))[0] == 201
    status, _, body = _request(
        app, "GET", "/api/experiments/compare?ids=f030-nse-one,f030-crypto",
    )
    assert status == 400
    assert "cannot be compared in one financial view" in json.loads(body)["error"]


def test_f030_experiment_compare_environment_record_surfaces_when_stored(tmp_path) -> None:
    # A stored environment record flows into the comparison instead of staying null.
    store = ExperimentStore(tmp_path / "f030-env.sqlite3")
    app = ResearchAPI(store)
    assert _request(app, "POST", "/api/datasets", _dataset_payload())[0] == 201
    assert _request(app, "POST", "/api/experiments", _payload(experiment_id="f030-env-a"))[0] == 201
    assert _request(app, "POST", "/api/experiments", _payload(experiment_id="f030-env-b"))[0] == 201
    environment = {"python_version": "3.13.0", "platform": "linux", "numpy_version": "2.0.0"}
    store.append_event("f030-env-a", "environment_recorded", environment)

    status, _, body = _request(
        app, "GET", "/api/experiments/compare?ids=f030-env-a,f030-env-b",
    )
    assert status == 200
    comparisons = json.loads(body)["comparisons"]
    assert comparisons[0]["environment"] == environment
    # The record was never stored for the second experiment: explicit null.
    assert comparisons[1]["environment"] is None


def test_f031_evolution_endpoint_aggregates_stored_generation_state(tmp_path) -> None:
    # F-031: live worker state is aggregated from stored candidates and events,
    # so the monitor works even when no worker is running.
    store = ExperimentStore(tmp_path / "f031-evolution.sqlite3")
    app = ResearchAPI(store)
    assert _request(app, "POST", "/api/datasets", _dataset_payload())[0] == 201
    assert _request(app, "POST", "/api/experiments", _payload(experiment_id="f031-gp"))[0] == 201

    rows = [
        (0, "random_initialisation", {"train_fitness": 0.5}),
        (0, "subtree_crossover", {"train_fitness": 0.3}),
        (1, "subtree_crossover_then_mutation", {"train_fitness": 0.9}),
        (1, "subtree_crossover", {"status": "failed"}),
    ]
    for index, (generation, operator, metrics) in enumerate(rows):
        store.append_candidate(
            candidate_id=f"f031-candidate-{index}",
            experiment_id="f031-gp",
            candidate_digest=f"{index:016d}" * 4,
            family="genetic_programming",
            generation=generation,
            parameters={"expression": {"op": f"tree-{index}"}, "feature_windows": [5]},
            metrics=metrics,
            lineage={"operator": operator, "parent_candidate_ids": []},
        )
    store.append_event(
        "f031-gp",
        "genetic_programming_candidate_frozen",
        {"selected_candidate_id": "f031-candidate-2", "population_size": 2},
    )
    store.append_event(
        "f031-gp",
        "genetic_programming_oos_recorded",
        {"oos_metrics": {"sharpe": 0.4}, "final_holdout_accessed": False},
    )

    status, _, body = _request(app, "GET", "/api/evolution/f031-gp")
    assert status == 200
    evolution = json.loads(body)["evolution"]
    assert evolution["experiment_id"] == "f031-gp"
    assert evolution["candidate_count"] == 4
    assert evolution["generation_count"] == 2
    assert evolution["mutation_count"] == 1
    assert evolution["crossover_count"] == 3
    assert evolution["latest_freeze_event"]["event_type"] == "genetic_programming_candidate_frozen"
    assert evolution["latest_freeze_event"]["payload"]["selected_candidate_id"] == "f031-candidate-2"
    assert [event["event_type"] for event in evolution["oos_events"]] == [
        "genetic_programming_oos_recorded",
    ]

    generation_zero = evolution["generations"][0]
    assert generation_zero == {
        "generation": 0,
        "population_size": 2,
        "best_fitness": 0.5,
        # statistics.median midpoint of [0.3, 0.5], not an upper-mid element pick.
        "median_fitness": 0.4,
        "worst_fitness": 0.3,
        "diversity": 1.0,
        "evaluated_count": 2,
        "failed_count": 0,
    }
    generation_one = evolution["generations"][1]
    assert generation_one["population_size"] == 2
    assert generation_one["best_fitness"] == 0.9
    assert generation_one["median_fitness"] == 0.9
    assert generation_one["worst_fitness"] == 0.9
    assert generation_one["evaluated_count"] == 1
    assert generation_one["failed_count"] == 1

    status, _, body = _request(app, "GET", "/api/evolution/unknown-experiment")
    assert status == 404
    assert "not found" in json.loads(body)["error"]


def test_f032_job_detail_exposes_recorded_resource_snapshots(tmp_path) -> None:
    # F-032: resource snapshots recorded as job events are queryable through the
    # job detail endpoint in append order, alongside the ordinary event stream.
    store = ExperimentStore(tmp_path / "f032-telemetry.sqlite3")
    spec = make_experiment(experiment_id="f032-telemetry-experiment")
    store.create_experiment(spec)
    store.create_job(
        job_id="f032-job",
        experiment_id=spec.experiment_id,
        runner_name="existing_strategy_evaluation",
        parameters={},
    )
    store.append_job_event("f032-job", "job_started", {})
    store.append_job_event("f032-job", "resource_snapshot", {
        "phase": "job_start",
        "rss_bytes": 84_500_992,
        "user_cpu_seconds": 1.25,
        "system_cpu_seconds": 0.5,
        "thread_count": 4,
        "elapsed_seconds": 0.0,
    })
    store.append_job_event("f032-job", "log", {"level": "info", "message": "checkpoint"})
    store.append_job_event("f032-job", "resource_snapshot", {
        "phase": "job_end",
        "rss_bytes": 91_880_448,
        "user_cpu_seconds": 4.75,
        "system_cpu_seconds": 1.25,
        "thread_count": 4,
        "elapsed_seconds": 12.5,
    })

    app = ResearchAPI(store)
    status, _, body = _request(app, "GET", "/api/jobs/f032-job")
    assert status == 200
    job = json.loads(body)["job"]
    snapshots = job["resource_snapshots"]
    assert [snapshot["payload"]["phase"] for snapshot in snapshots] == ["job_start", "job_end"]
    assert snapshots[0]["payload"]["rss_bytes"] == 84_500_992
    assert snapshots[0]["payload"]["user_cpu_seconds"] == 1.25
    assert snapshots[0]["payload"]["thread_count"] == 4
    assert snapshots[1]["payload"]["rss_bytes"] == 91_880_448
    assert snapshots[1]["payload"]["elapsed_seconds"] == 12.5
    # The ordinary event stream is unchanged: snapshots are events, not a side table.
    event_types = [event["event_type"] for event in job["events"]]
    assert event_types.count("resource_snapshot") == 2
    assert "log" in event_types

    status, _, body = _request(app, "GET", "/api/jobs/unknown-job")
    assert status == 404


def test_f033_experiment_export_returns_roundtrippable_bundle(tmp_path) -> None:
    # F-033: one JSON bundle contains every stored record type for the experiment;
    # a nonexistent id yields the standard explicit 404 error payload.
    store = ExperimentStore(tmp_path / "f033-export.sqlite3")
    app = ResearchAPI(store)
    assert _request(app, "POST", "/api/datasets", _dataset_payload())[0] == 201
    assert _request(app, "POST", "/api/experiments", _payload(experiment_id="f033-export"))[0] == 201

    store.append_event("f033-export", "environment_recorded", {
        "python_version": "3.13.0",
        "platform": "linux",
        "numpy_version": "2.0.0",
    })
    # Real GP runner payload shape (runners.py genetic_programming_oos_recorded):
    # selected ids + oos_metrics + final_holdout_accessed; no oos_acceptance key.
    store.append_event("f033-export", "genetic_programming_oos_recorded", {
        "selected_candidate_id": "f033-candidate-0",
        "selected_candidate_digest": "a" * 64,
        "oos_metrics": {"sharpe": 0.35},
        "final_holdout_accessed": False,
    })
    # The existing_strategy_evaluated event is the production carrier of the
    # versioned OOS acceptance verdict plus the classification report
    # (evaluation.py evaluate_existing_strategy persistence).
    store.append_event("f033-export", "existing_strategy_evaluated", {
        "classification": "requires_independent_confirmation",
        "classification_evidence": {"train_evaluated": True, "oos_evaluated": True},
        "oos_acceptance": {"outcome": "fail", "policy_version": "v1-2026-11-10",
                           "reasons": ["oos_sharpe=-0.1 is below the required minimum 0.0"]},
        "oos_policy_version": "v1-2026-11-10",
    })
    store.create_job(
        job_id="f033-gp-job",
        experiment_id="f033-export",
        runner_name="genetic_programming",
        parameters={},
    )
    store.update_job_status("f033-gp-job", "running")
    store.update_job_status("f033-gp-job", "succeeded", result={
        "classification": "requires_independent_confirmation",
        "oos_acceptance": {"outcome": "fail", "policy_version": "v1-2026-11-10",
                           "reasons": ["oos_sharpe=-0.1 is below the required minimum 0.0"]},
    })
    store.append_job_event("f033-gp-job", "job_started", {})
    store.append_job_event("f033-gp-job", "log", {"level": "info", "message": "checkpoint"})
    store.append_job_event("f033-gp-job", "job_succeeded", {"result_keys": ["classification"]})
    store.append_candidate(
        candidate_id="f033-candidate-0",
        experiment_id="f033-export",
        candidate_digest="a" * 64,
        family="genetic_programming",
        generation=0,
        parameters={"expression": {"op": "tree"}, "feature_windows": [5]},
        metrics={"train_fitness": 0.6},
        lineage={"operator": "random_initialisation", "parent_candidate_ids": []},
    )

    status, _, body = _request(app, "GET", "/api/experiments/f033-export/export")
    assert status == 200
    bundle = json.loads(body)["export"]
    assert bundle["experiment_id"] == "f033-export"
    assert bundle["experiment"]["fingerprint"]
    assert bundle["experiment"]["spec"]["experiment_id"] == "f033-export"
    # Environment record: the latest stored one is surfaced at the top level too.
    assert bundle["environment"]["python_version"] == "3.13.0"
    # Every lifecycle event roundtrips with its payload decoded.
    event_types = [event["event_type"] for event in bundle["events"]]
    assert event_types == [
        "experiment_created",
        "environment_recorded",
        "genetic_programming_oos_recorded",
        "existing_strategy_evaluated",
    ]
    environment_events = [event for event in bundle["events"] if event["event_type"] == "environment_recorded"]
    assert environment_events[0]["payload"]["numpy_version"] == "2.0.0"
    # Candidates keep lineage and fitness.
    assert bundle["candidate_count"] == 1
    assert bundle["candidates"][0]["lineage"]["operator"] == "random_initialisation"
    assert bundle["candidates"][0]["metrics"]["train_fitness"] == 0.6
    # OOS acceptance records are collected by payload key, not event-type suffix:
    # the GP oos_recorded event carries no verdict (matching the real runner), while
    # existing_strategy_evaluated — the production F-001 carrier for the
    # existing-strategy/optimizer/DE/bayesian/hybrid families — does and must roundtrip.
    assert len(bundle["oos_acceptances"]) == 1
    verdict = bundle["oos_acceptances"][0]
    assert verdict["oos_acceptance"]["outcome"] == "fail"
    assert verdict["oos_acceptance"]["policy_version"] == "v1-2026-11-10"
    assert verdict["oos_acceptance"]["reasons"] == [
        "oos_sharpe=-0.1 is below the required minimum 0.0",
    ]
    assert verdict["_occurred_at"]
    # Classification reports keep the label and the evidence.
    assert bundle["classification_reports"][0]["classification"] == "requires_independent_confirmation"
    assert bundle["classification_reports"][0]["classification_evidence"]["train_evaluated"] is True
    assert bundle["event_count"] == 4
    # Job records roundtrip with results and logs so the bundle is complete
    # enough to re-analyse offline (audit F-033: specification, candidates,
    # results, and logs).
    assert bundle["job_count"] == 1
    job_record = bundle["jobs"][0]
    assert job_record["job_id"] == "f033-gp-job"
    assert job_record["result"]["classification"] == "requires_independent_confirmation"
    assert job_record["result"]["oos_acceptance"]["policy_version"] == "v1-2026-11-10"
    assert [event["event_type"] for event in job_record["events"]] == [
        "job_started", "log", "job_succeeded",
    ]

    status, _, body = _request(app, "GET", "/api/experiments/ghost-experiment/export")
    assert status == 404
    assert "not found" in json.loads(body)["error"]

    status, _, body = _request(app, "GET", "/api/experiments//export")
    assert status == 404
