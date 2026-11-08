"""End-to-end API tests for queued, inspected and cancelled research jobs."""

from __future__ import annotations

import io
import json
from dataclasses import replace
from datetime import datetime, timezone
from threading import Event
from urllib.parse import urlsplit

from research.platform.api import ResearchAPI
from research.platform.domain import AlgorithmFamily, DataResolution, Market, ResearchTrack
from research.platform.experiments import ExperimentSpec
from research.platform.jobs import ResearchJobManager
from research.platform.storage import ExperimentStore


UTC = timezone.utc


def _experiment() -> ExperimentSpec:
    # The experiment is an immutable NSE existing-strategy record with sealed holdout dates.
    return ExperimentSpec(
        experiment_id="api-job-experiment",
        market=Market.NSE,
        track=ResearchTrack.NSE_INDIVIDUAL,
        algorithm_family=AlgorithmFamily.EXISTING_STRATEGY,
        resolution=DataResolution.ONE_DAY,
        dataset_ids=("registered-but-not-loaded",),
        random_seed=12,
        git_commit="0123456789abcdef0123456789abcdef01234567",
        code_version="api-job-test",
        training_start=datetime(2010, 1, 1, tzinfo=UTC),
        training_end=datetime(2014, 1, 1, tzinfo=UTC),
        validation_start=datetime(2014, 1, 1, tzinfo=UTC),
        validation_end=datetime(2016, 1, 1, tzinfo=UTC),
        oos_start=datetime(2026, 10, 2, tzinfo=UTC),
        oos_end=datetime(2026, 10, 16, tzinfo=UTC),
        final_holdout_start=datetime(2026, 10, 16, tzinfo=UTC),
        final_holdout_end=datetime(2026, 11, 8, tzinfo=UTC),
        cost_model_id="nse-delivery-cost-model",
        execution_model_id="next-open-participation-impact-v1",
        objectives=("net_return", "max_drawdown"),
        parameters={"strategy_name": "absolute_momentum"},
        created_at=datetime(2026, 11, 8, tzinfo=UTC),
    )


def _request(app: ResearchAPI, method: str, path: str, payload: object | None = None):
    # Exercise the WSGI API without opening a TCP socket.
    parsed = urlsplit(path)
    body = b"" if payload is None else json.dumps(payload).encode("utf-8")
    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": parsed.path,
        "QUERY_STRING": parsed.query,
        "CONTENT_TYPE": "application/json" if payload is not None else "",
        "CONTENT_LENGTH": str(len(body)),
        "wsgi.input": io.BytesIO(body),
    }
    result: dict[str, object] = {}

    def start_response(status: str, headers: list[tuple[str, str]]) -> None:
        # Capture the WSGI result status for assertions.
        result["status"] = status

    response = b"".join(app(environ, start_response))
    return int(str(result["status"]).split(" ", 1)[0]), json.loads(response)


def _app(tmp_path, *, runner, experiment: ExperimentSpec | None = None):
    # Each test gets an isolated worker manager and SQLite database.
    store = ExperimentStore(tmp_path / "jobs.sqlite3")
    store.create_experiment(experiment or _experiment())
    manager = ResearchJobManager(store, max_workers=1, max_queued=2)
    manager.register_runner("test_evaluation", runner)
    return store, manager, ResearchAPI(store, manager)


def test_jobs_api_lists_runners_queues_jobs_and_returns_details(tmp_path) -> None:
    # A registered runner can be invoked only by its stable allow-listed identifier.
    def runner(context, experiment, parameters):
        context.log("test run started")
        context.check_cancelled()
        return {"market": experiment["market"], "value": parameters["value"] + 1}

    store, manager, app = _app(tmp_path, runner=runner)
    try:
        status, payload = _request(app, "GET", "/api/runners")
        assert status == 200
        assert payload["runners"] == ["test_evaluation"]

        status, payload = _request(
            app,
            "POST",
            "/api/jobs",
            {
                "experiment_id": "api-job-experiment",
                "runner_name": "test_evaluation",
                "parameters": {"value": 41},
            },
        )
        assert status == 202
        job_id = payload["job_id"]
        completed = manager.wait(job_id, timeout=5)
        assert completed["status"] == "succeeded"
        assert completed["result"]["value"] == 42

        status, payload = _request(app, "GET", "/api/jobs?limit=10")
        assert status == 200
        assert payload["jobs"][0]["job_id"] == job_id

        status, payload = _request(app, "GET", f"/api/jobs/{job_id}")
        assert status == 200
        assert payload["job"]["events"]

        status, payload = _request(app, "GET", "/api/jobs?experiment_id=unknown")
        assert status == 200
        assert payload["jobs"] == []
    finally:
        app.shutdown()


def test_jobs_api_cancellation_route_requests_cooperative_stop(tmp_path) -> None:
    # The route sets the same cancellation event polled by the trusted runner.
    started = Event()

    def runner(context, experiment, parameters):
        started.set()
        while True:
            context.check_cancelled()

    _, manager, app = _app(tmp_path, runner=runner)
    try:
        status, queued = _request(
            app,
            "POST",
            "/api/jobs",
            {
                "experiment_id": "api-job-experiment",
                "runner_name": "test_evaluation",
                "parameters": {},
            },
        )
        assert status == 202
        job_id = queued["job_id"]
        assert started.wait(timeout=5)

        status, response = _request(app, "POST", f"/api/jobs/{job_id}/cancel")
        assert status == 200
        assert response["cancellation_requested"] is True
        assert manager.wait(job_id, timeout=5)["status"] == "cancelled"
    finally:
        app.shutdown()


def test_jobs_api_rejects_unknown_runner_and_non_object_parameters(tmp_path) -> None:
    # Client payloads cannot execute arbitrary module names or pass list-shaped arguments.
    def runner(context, experiment, parameters):
        return {"ok": True}

    _, manager, app = _app(tmp_path, runner=runner)
    try:
        status, payload = _request(
            app,
            "POST",
            "/api/jobs",
            {
                "experiment_id": "api-job-experiment",
                "runner_name": "arbitrary_python",
                "parameters": {},
            },
        )
        assert status == 400
        assert "requires runner existing_strategy_evaluation" in payload["error"]

        status, payload = _request(
            app,
            "POST",
            "/api/jobs",
            {
                "experiment_id": "api-job-experiment",
                "runner_name": "test_evaluation",
                "parameters": [],
            },
        )
        assert status == 400
        assert "JSON object" in payload["error"]
    finally:
        app.shutdown()


def test_jobs_api_returns_service_unavailable_without_manager(tmp_path) -> None:
    # Metadata-only API instances remain usable but cannot pretend they launch jobs.
    app = ResearchAPI(ExperimentStore(tmp_path / "metadata-only.sqlite3"))
    status, payload = _request(
        app,
        "POST",
        "/api/jobs",
        {
            "experiment_id": "api-job-experiment",
            "runner_name": "test_evaluation",
            "parameters": {},
        },
    )
    assert status == 503
    assert "no research worker manager" in payload["error"]



def test_jobs_api_routes_optimizer_family_to_optimizer_runner_only(tmp_path) -> None:
    # Random-search experiments must use the matching allow-listed optimizer runner.
    base = _experiment()
    parameters = dict(base.parameters)
    parameters["execution_assumptions"] = {
        "slippage_bps": 5,
        "impact_coefficient_bps": 10,
        "max_participation": 0.05,
        "max_gross_exposure": 1.0,
        "periods_per_year": 252,
    }
    parameters["optimization"] = {
        "budget": 8,
        "validation_candidates": 2,
        "objective": "sharpe",
    }
    spec = replace(
        base,
        experiment_id="api-random-search",
        algorithm_family=AlgorithmFamily.RANDOM_SEARCH,
        parameters=parameters,
    )

    def runner(context, experiment, parameters):
        return {"family": experiment["spec"]["algorithm_family"], "selected": True}

    store, manager, app = _app(tmp_path, runner=runner, experiment=spec)
    manager.register_runner("existing_strategy_optimization", runner)
    try:
        status, result = _request(
            app,
            "POST",
            "/api/jobs",
            {
                "experiment_id": spec.experiment_id,
                "runner_name": "existing_strategy_optimization",
                "parameters": {},
            },
        )
        assert status == 202
        job = manager.wait(result["job_id"], timeout=5)
        assert job["status"] == "succeeded"
        assert job["result"]["family"] == "random_search"

        status, result = _request(
            app,
            "POST",
            "/api/jobs",
            {
                "experiment_id": spec.experiment_id,
                "runner_name": "existing_strategy_evaluation",
                "parameters": {},
            },
        )
        assert status == 400
        assert "requires runner existing_strategy_optimization" in result["error"]
    finally:
        app.shutdown()



def test_jobs_api_routes_genetic_programming_to_registered_gp_runner(tmp_path) -> None:
    # A GP experiment must invoke the dedicated bounded expression-evolution worker.
    base = _experiment()
    gp_parameters = dict(base.parameters)
    gp_parameters["genetic_programming"] = {
        "population_size": 4,
        "generations": 1,
        "max_depth": 3,
        "max_nodes": 15,
        "mutation_rate": 0.2,
        "validation_candidates": 2,
        "objective": "sharpe",
        "feature_windows": [3],
    }
    spec = replace(
        base,
        experiment_id="api-gp-experiment",
        algorithm_family=AlgorithmFamily.GENETIC_PROGRAMMING,
        parameters=gp_parameters,
    )

    def runner(context, experiment, parameters):
        return {"algorithm_family": experiment["spec"]["algorithm_family"]}

    store, manager, app = _app(tmp_path, runner=runner, experiment=spec)
    manager.register_runner("genetic_programming", runner)
    try:
        status, payload = _request(
            app,
            "POST",
            "/api/jobs",
            {
                "experiment_id": spec.experiment_id,
                "runner_name": "genetic_programming",
                "parameters": {},
            },
        )
        assert status == 202
        job = manager.wait(payload["job_id"], timeout=5)
        assert job["status"] == "succeeded"
        assert job["result"]["algorithm_family"] == "genetic_programming"

        status, rejected = _request(
            app,
            "POST",
            "/api/jobs",
            {
                "experiment_id": spec.experiment_id,
                "runner_name": "existing_strategy_optimization",
                "parameters": {},
            },
        )
        assert status == 400
        assert "requires runner genetic_programming" in rejected["error"]
    finally:
        app.shutdown()
