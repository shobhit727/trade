"""Local research API backed by the immutable SQLite experiment store."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from http import HTTPStatus
from typing import Any
from urllib.parse import parse_qs
from wsgiref.types import StartResponse

from .data_catalog import DatasetManifest, LicenseStatus, TimeGap, ValueOrigin
from .domain import AlgorithmFamily, DataResolution, MARKET_SPECS, Market, ResearchTrack
from .experiments import ExperimentSpec
from .storage import ExperimentStore
from .strategy_catalog import ExistingStrategyRegistry


DASHBOARD_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Quant Research Platform</title>
<style>
:root { color-scheme: dark; font-family: ui-sans-serif, system-ui, sans-serif; }
body { margin: 0; background: #10151d; color: #e5eaf1; }
header { padding: 20px 26px; border-bottom: 1px solid #2a3442; }
main { max-width: 1200px; margin: 0 auto; padding: 24px; }
h1 { margin: 0 0 6px; font-size: 22px; }
p, small { color: #a9b6c7; }
.grid { display: grid; grid-template-columns: repeat(auto-fit,minmax(260px,1fr)); gap: 14px; }
section { background: #171f2a; border: 1px solid #2c394a; border-radius: 10px; padding: 16px; }
label { display:block; margin: 10px 0 5px; color:#a9b6c7; font-size: 13px; }
input, select, button { width:100%; box-sizing:border-box; padding:10px; border-radius:6px; border:1px solid #39495d; background:#101923; color:#e5eaf1; }
button { margin-top:14px; cursor:pointer; background:#234c78; border-color:#396b9e; }
table { width:100%; border-collapse: collapse; margin-top:10px; }
td, th { text-align:left; padding:9px 7px; border-bottom:1px solid #2c394a; font-size:13px; }
.status { font-size:12px; color:#9bc3a7; }
pre { overflow:auto; white-space:pre-wrap; word-break:break-word; color:#c4d3e4; }
</style>
</head>
<body>
<header><h1>Quantitative Research Platform</h1><p>Historical research and simulated portfolios only · No live trading</p></header>
<main>
<div class="grid">
<section><h2>NSE environment</h2><p>Initial simulated capital</p><strong>₹21,00,000</strong><p id="nse-count">Loading experiments…</p></section>
<section><h2>Crypto environment</h2><p>Initial simulated capital</p><strong>₹21,00,000</strong><p id="crypto-count">Loading experiments…</p></section>
</div>
<div class="grid" style="margin-top:16px">
<section>
<h2>Create experiment</h2>
<p>Creates an immutable experiment record. It does not start a research worker.</p>
<form id="create-form">
<label>Market</label><select id="market"><option value="nse">NSE</option><option value="crypto">Crypto</option></select>
<label>Research track</label><select id="track"></select>
<label>Algorithm family</label><select id="family"></select>
<label>Resolution</label><select id="resolution"></select>
<label>Existing strategy (used when the family is existing_strategy)</label><select id="strategy-name"></select>
<label>Dataset IDs (comma-separated)</label><input id="dataset-ids" value="example-dataset-v1" required>
<label>Experiment ID</label><input id="experiment-id" required>
<label>Git commit</label><input id="git-commit" placeholder="40-character commit SHA" required>
<label>Cost model ID</label><input id="cost-model" value="market-cost-v1" required>
<label>Execution model ID</label><input id="execution-model" value="next-open-participation-impact-v1" required>
<label>Seed</label><input id="seed" type="number" min="0" value="42" required>
<label>Objectives (comma-separated)</label><input id="objectives" value="net_return,max_drawdown,turnover" required>
<label>Training start / end (ISO timestamps)</label><input id="train-start" type="datetime-local" value="2016-01-01T00:00" required><input id="train-end" type="datetime-local" value="2020-01-01T00:00" required>
<label>Validation start / end</label><input id="val-start" type="datetime-local" value="2020-01-01T00:00" required><input id="val-end" type="datetime-local" value="2022-01-01T00:00" required>
<label>OOS start / end</label><input id="oos-start" type="datetime-local" value="2022-01-01T00:00" required><input id="oos-end" type="datetime-local" value="2024-01-01T00:00" required>
<label>Final holdout start / end</label><small>NSE holdout data must start after 1 October 2026; the prior 2024–2026 test window is exposed.</small><input id="hold-start" type="datetime-local" value="2026-10-02T00:00" required><input id="hold-end" type="datetime-local" value="2026-11-08T00:00" required>
<button type="submit">Create experiment record</button><p id="form-status" class="status"></p>
</form>
</section>
<section>
<h2>Experiment records</h2>
<label>Environment</label><select id="filter-market"><option value="">All (separate sections)</option><option value="nse">NSE</option><option value="crypto">Crypto</option></select>
<table><thead><tr><th>Experiment</th><th>Market / track</th><th>Created</th></tr></thead><tbody id="experiment-rows"></tbody></table>
<pre id="detail">Select an experiment row to inspect its stored specification.</pre>
</section>
</div>
<section style="margin-top:16px">
<h2>Existing strategy catalogue</h2>
<p>Registered strategy implementations and their typed configuration spaces. Listing does not execute a strategy.</p>
<table><thead><tr><th>Strategy</th><th>Implementation</th><th>Config</th><th>Searchable parameters</th><th>Held fixed</th></tr></thead><tbody id="strategy-rows"></tbody></table>
<pre id="strategy-detail">Select a strategy to inspect its defaults and parameter bounds.</pre>
</section>
<section style="margin-top:16px">
<h2>Data availability and provenance</h2>
<p>Registered dataset manifests only. Registering metadata does not upload market data.</p>
<table><thead><tr><th>Dataset</th><th>Market / exchange</th><th>Category / resolution</th><th>Coverage</th><th>Licence / quality</th><th>Fingerprint</th></tr></thead><tbody id="dataset-rows"></tbody></table>
</section>
</main>
<script>
const tracks = {
  nse: ["nse_individual", "nse_portfolio"],
  crypto: ["crypto_individual", "crypto_portfolio"]
};
const families = ["existing_strategy","random_search","grid_search","bayesian","differential_evolution","genetic_programming","neuroevolution","strategy_composition","hybrid"];
const resolutions = ["tick","order_book_event","order_book_snapshot","1s","1m","5m","15m","30m","1h","4h","1d","1w","1mo"];
const $ = id => document.getElementById(id);
let strategyCache = null;
function refreshTrackOptions() {
  // Keep the selected track consistent with the independently selected market.
  $("track").innerHTML = tracks[$("market").value].map(x => '<option value="' + x + '">' + x + '</option>').join("");
}
function fillSelect(id, values) {
  // Populate a controlled select from the server-supported vocabulary.
  $(id).innerHTML = values.map(x => '<option value="' + x + '">' + x + '</option>').join("");
}
async function api(path, options) {
  // All dashboard data comes from real API records, never embedded sample results.
  const response = await fetch(path, options);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || response.statusText);
  return payload;
}
function utc(id) {
  // datetime-local inputs are interpreted as UTC to keep stored timestamps explicit.
  return document.getElementById(id).value + ":00Z";
}
function utc(id) {
  // datetime-local inputs are interpreted as UTC to keep timestamps explicit.
  return document.getElementById(id).value + ":00Z";
}
async function refresh() {
  // Keep the two financial environments visibly separate.
  const [nse, crypto] = await Promise.all([
    api("/api/experiments?market=nse"), api("/api/experiments?market=crypto")
  ]);
  $("nse-count").textContent = nse.experiments.length + " stored research experiments";
  $("crypto-count").textContent = crypto.experiments.length + " stored research experiments";
  const filter = $("filter-market").value;
  const rows = filter ? await api("/api/experiments?market=" + filter) : {experiments:[...nse.experiments,...crypto.experiments]};
  const body = $("experiment-rows");
  body.replaceChildren();
  rows.experiments.forEach(item => {
    // Render stored identifiers with textContent to prevent HTML/script injection.
    const row = document.createElement("tr");
    row.dataset.id = item.experiment_id;
    row.dataset.market = item.market;
    [item.experiment_id, item.market + " / " + item.track, item.created_at].forEach(value => {
      const cell = document.createElement("td");
      cell.textContent = value;
      row.appendChild(cell);
    });
    body.appendChild(row);
  });
  document.querySelectorAll("#experiment-rows tr").forEach(row => row.addEventListener("click", async () => {
    // A detail request remains scoped to the record selected by its market and ID.
    $("detail").textContent = JSON.stringify(await api("/api/experiments/" +
      encodeURIComponent(row.dataset.id)), null, 2);
  }));
  if (strategyCache === null) strategyCache = await api("/api/strategies?limit=500");
  const strategies = strategyCache;
  const strategySelect = $("strategy-name");
  strategySelect.replaceChildren();
  const strategyBody = $("strategy-rows");
  strategyBody.replaceChildren();
  strategies.strategies.forEach(item => {
    // Render actual discovered catalogue metadata without injecting stored strings as HTML.
    const option = document.createElement("option");
    option.value = item.name;
    option.textContent = item.name;
    strategySelect.appendChild(option);
    const row = document.createElement("tr");
    [
      item.name,
      item.strategy_class,
      item.config_class,
      String(item.parameters.length),
      String(item.held_fixed.length)
    ].forEach(value => {
      const cell = document.createElement("td");
      cell.textContent = value;
      row.appendChild(cell);
    });
    row.addEventListener("click", () => {
      $("strategy-name").value = item.name;
      $("strategy-detail").textContent = JSON.stringify(item, null, 2);
    });
    strategyBody.appendChild(row);
  });
  if (strategySelect.dataset.listenerBound !== "true") {
    // Bind the strategy selector once even when the dashboard refreshes its tables.
    strategySelect.addEventListener("change", () => {
      const selected = strategies.strategies.find(item => item.name === strategySelect.value);
      $("strategy-detail").textContent = selected ? JSON.stringify(selected, null, 2) : "";
    });
    strategySelect.dataset.listenerBound = "true";
  }
  if (strategies.strategies.length) {
    $("strategy-detail").textContent = JSON.stringify(strategies.strategies[0], null, 2);
  }
  const catalogue = await api("/api/datasets");
  const datasetBody = $("dataset-rows");
  datasetBody.replaceChildren();
  catalogue.datasets.forEach(item => {
    // Render manifest fields as text so provider data cannot inject dashboard markup.
    const row = document.createElement("tr");
    [
      item.dataset_id,
      item.market + " / " + item.exchange,
      item.category + " / " + item.resolution,
      item.coverage_start + " → " + item.coverage_end,
      item.license_status + " / " + (item.quality_score === null ? "ungraded" : item.quality_score),
      item.fingerprint.slice(0, 12)
    ].forEach(value => {
      const cell = document.createElement("td");
      cell.textContent = value;
      row.appendChild(cell);
    });
    datasetBody.appendChild(row);
  });
}
$("market").addEventListener("change", refreshTrackOptions);
$("filter-market").addEventListener("change", refresh);
$("create-form").addEventListener("submit", async event => {
  event.preventDefault();
  $("form-status").textContent = "Saving…";
  try {
    const value = id => $(id).value;
    const market = value("market");
    const payload = {
      experiment_id: value("experiment-id"),
      market,
      track: value("track"),
      algorithm_family: value("family"),
      resolution: value("resolution"),
      dataset_ids: value("dataset-ids").split(",").map(x => x.trim()).filter(Boolean),
      random_seed: Number(value("seed")),
      git_commit: value("git-commit"),
      code_version: "dashboard-api-v1",
      training_start: utc("train-start"),
      training_end: utc("train-end"),
      validation_start: utc("val-start"),
      validation_end: utc("val-end"),
      oos_start: utc("oos-start"),
      oos_end: utc("oos-end"),
      final_holdout_start: utc("hold-start"),
      final_holdout_end: utc("hold-end"),
      cost_model_id: value("cost-model"),
      execution_model_id: value("execution-model"),
      objectives: value("objectives").split(",").map(x => x.trim()).filter(Boolean),
      compute_backend: "auto",
      compute_device: "unverified",
      parameters: value("family") === "existing_strategy" ? {strategy_name: value("strategy-name")} : {}
    };
    const result = await api("/api/experiments", {
      method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(payload)
    });
    $("form-status").textContent = "Created " + result.experiment_id;
    await refresh();
  } catch (error) {
    $("form-status").textContent = "Error: " + error.message;
  }
});
fillSelect("family", families);
fillSelect("resolution", resolutions);
refreshTrackOptions();
refresh().catch(error => $("form-status").textContent = "API error: " + error.message);
</script>
</body>
</html>
"""


def _parse_time(value: str) -> datetime:
    # Require an explicit timezone; dashboard local timestamps are interpreted as UTC.
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("all experiment timestamps must include a timezone offset")
    return parsed


def _manifest_from_payload(payload: dict[str, Any]) -> DatasetManifest:
    """Validate and construct an immutable dataset manifest from JSON metadata."""
    # Coverage timestamps and known gaps must carry explicit timezone offsets.
    gaps = tuple(
        TimeGap(
            start=_parse_time(item["start"]),
            end=_parse_time(item["end"]),
            reason=str(item["reason"]),
        )
        for item in payload.get("known_gaps", [])
    )
    return DatasetManifest(
        dataset_id=str(payload["dataset_id"]),
        market=Market(payload["market"]),
        provider=str(payload["provider"]),
        source=str(payload["source"]),
        instrument=str(payload["instrument"]),
        exchange=str(payload["exchange"]),
        category=str(payload["category"]),
        resolution=DataResolution(payload["resolution"]),
        coverage_start=_parse_time(payload["coverage_start"]),
        coverage_end=_parse_time(payload["coverage_end"]),
        timezone=str(payload["timezone"]),
        timestamp_convention=str(payload["timestamp_convention"]),
        acquired_at=_parse_time(payload["acquired_at"]),
        update_frequency=str(payload["update_frequency"]),
        license_status=LicenseStatus(payload["license_status"]),
        license_reference=str(payload["license_reference"]),
        value_origin=ValueOrigin(payload.get("value_origin", "observed")),
        quality_score=payload.get("quality_score"),
        known_gaps=gaps,
        adjustment_method=str(payload.get("adjustment_method", "none")),
        processing_history=tuple(str(item) for item in payload.get("processing_history", [])),
        schema_version=str(payload.get("schema_version", "1")),
        extra_metadata=dict(payload.get("extra_metadata", {})),
    )


def _validate_dataset_coverage(store: ExperimentStore, spec: ExperimentSpec) -> None:
    """Require approved, same-market datasets covering every experiment partition."""
    # Historical coverage is checked before the experiment record can be created.
    windows = (
        (spec.training_start, spec.training_end),
        (spec.validation_start, spec.validation_end),
        (spec.oos_start, spec.oos_end),
        (spec.final_holdout_start, spec.final_holdout_end),
    )
    for dataset_id in spec.dataset_ids:
        row = store.get_dataset(dataset_id)
        manifest = row["manifest"]
        if row["market"] != spec.market.value:
            raise ValueError(
                f"cross-market dataset rejected: {dataset_id} belongs to {row['market']}, not {spec.market.value}"
            )
        if manifest["license_status"] != LicenseStatus.APPROVED.value:
            raise ValueError(
                f"dataset {dataset_id} licence must be approved before research use"
            )
        coverage_start = _parse_time(manifest["coverage_start"])
        coverage_end = _parse_time(manifest["coverage_end"])
        for start, end in windows:
            if coverage_start > start or coverage_end < end:
                raise ValueError(
                    f"dataset {dataset_id} does not cover requested window {start.isoformat()}..{end.isoformat()}"
                )


def _create_spec(payload: dict[str, Any]) -> ExperimentSpec:
    # Construct the immutable experiment definition from API input and validate all fields.
    parameters = dict(payload.get("parameters", {}))
    algorithm_family = AlgorithmFamily(payload["algorithm_family"])
    if algorithm_family is AlgorithmFamily.EXISTING_STRATEGY:
        # Do not accept arbitrary names; the strategy must be registered in the repository.
        strategy_name = parameters.get("strategy_name")
        if not isinstance(strategy_name, str) or not strategy_name.strip():
            raise ValueError("existing_strategy experiments require a registered strategy_name")
        ExistingStrategyRegistry().describe(strategy_name)
    return ExperimentSpec(
        experiment_id=str(payload["experiment_id"]),
        market=Market(payload["market"]),
        track=ResearchTrack(payload["track"]),
        algorithm_family=algorithm_family,
        resolution=DataResolution(payload["resolution"]),
        dataset_ids=tuple(str(item) for item in payload["dataset_ids"]),
        random_seed=int(payload["random_seed"]),
        git_commit=str(payload["git_commit"]),
        code_version=str(payload["code_version"]),
        training_start=_parse_time(payload["training_start"]),
        training_end=_parse_time(payload["training_end"]),
        validation_start=_parse_time(payload["validation_start"]),
        validation_end=_parse_time(payload["validation_end"]),
        oos_start=_parse_time(payload["oos_start"]),
        oos_end=_parse_time(payload["oos_end"]),
        final_holdout_start=_parse_time(payload["final_holdout_start"]),
        final_holdout_end=_parse_time(payload["final_holdout_end"]),
        cost_model_id=str(payload["cost_model_id"]),
        execution_model_id=str(payload["execution_model_id"]),
        objectives=tuple(str(item) for item in payload["objectives"]),
        compute_backend=str(payload.get("compute_backend", "auto")),
        compute_device=str(payload.get("compute_device", "unverified")),
        parameters=parameters,
    )


class ResearchAPI:
    """Minimal local WSGI API for creating and inspecting actual experiment records."""

    def __init__(self, store: ExperimentStore) -> None:
        # Cache the authoritative strategy registry; discovery is lazy and read-only.
        self.store = store
        self.strategy_registry = ExistingStrategyRegistry()

    def _response(self, start_response: StartResponse, status: HTTPStatus, payload: object,
                  content_type: str = "application/json; charset=utf-8") -> list[bytes]:
        # Always return a finite body and explicit content length.
        body = payload.encode("utf-8") if isinstance(payload, str) else json.dumps(
            payload, sort_keys=True, allow_nan=False
        ).encode("utf-8")
        start_response(f"{status.value} {status.phrase}", [
            ("Content-Type", content_type),
            ("Content-Length", str(len(body))),
            ("Cache-Control", "no-store"),
            ("X-Content-Type-Options", "nosniff"),
        ])
        return [body]

    def __call__(self, environ: dict[str, Any], start_response: StartResponse) -> list[bytes]:
        # Catch expected validation/lookup failures and never leak tracebacks to the browser.
        method = environ.get("REQUEST_METHOD", "GET").upper()
        path = environ.get("PATH_INFO", "/")
        try:
            if method == "GET" and path == "/":
                return self._response(start_response, HTTPStatus.OK, DASHBOARD_HTML,
                                      "text/html; charset=utf-8")
            if method == "GET" and path == "/api/health":
                return self._response(start_response, HTTPStatus.OK, {"status": "ok"})
            if method == "GET" and path == "/api/markets":
                # Each environment gets its own capital response; no cross-market sum exists.
                markets = [
                    {
                        "market": market.value,
                        "base_currency": spec.base_currency,
                        "initial_simulated_capital": str(spec.initial_simulated_capital),
                        "account_scope": spec.account_scope,
                    }
                    for market, spec in MARKET_SPECS.items()
                ]
                return self._response(start_response, HTTPStatus.OK, {"markets": markets})
            if method == "GET" and path == "/api/strategies":
                # This endpoint enumerates existing strategy code; it does not execute strategies.
                query = parse_qs(environ.get("QUERY_STRING", ""))
                limit = int(query.get("limit", ["500"])[0])
                if not 1 <= limit <= 500:
                    raise ValueError("limit must be between 1 and 500")
                registry = self.strategy_registry
                names = registry.names()[:limit]
                descriptors = []
                for name in names:
                    item = registry.describe(name)
                    descriptors.append({
                        "name": item.name,
                        "module": item.module,
                        "strategy_class": item.strategy_class,
                        "config_class": item.config_class,
                        "defaults": item.defaults,
                        "parameters": list(item.parameters),
                        "held_fixed": list(item.held_fixed),
                    })
                return self._response(start_response, HTTPStatus.OK, {
                    "strategy_count": len(registry.names()),
                    "returned": len(descriptors),
                    "strategies": descriptors,
                })
            if method == "GET" and path == "/api/datasets":
                # Data coverage is returned as dataset metadata, not as combined financial performance.
                query = parse_qs(environ.get("QUERY_STRING", ""))
                market_values = query.get("market", [])
                market = market_values[0] if market_values else None
                limit_values = query.get("limit", ["1000"])
                rows = self.store.list_datasets(market=market, limit=int(limit_values[0]))
                return self._response(start_response, HTTPStatus.OK, {"datasets": rows})
            if method == "GET" and path == "/api/experiments":
                # Restrict the list filter to one known environment if supplied.
                query = parse_qs(environ.get("QUERY_STRING", ""))
                market_values = query.get("market", [])
                market = market_values[0] if market_values else None
                limit_values = query.get("limit", ["100"])
                rows = self.store.list_experiments(market=market, limit=int(limit_values[0]))
                return self._response(start_response, HTTPStatus.OK, {"experiments": rows})
            if method == "POST" and path == "/api/datasets":
                # Register immutable provenance only; the local source file is not uploaded.
                if environ.get("CONTENT_TYPE", "").split(";")[0].strip() != "application/json":
                    return self._response(start_response, HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                                          {"error": "Content-Type must be application/json"})
                length = int(environ.get("CONTENT_LENGTH") or "0")
                if not 0 < length <= 1_000_000:
                    return self._response(start_response, HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                                          {"error": "request body must be between 1 byte and 1 MB"})
                payload = json.loads(environ["wsgi.input"].read(length))
                if not isinstance(payload, dict):
                    raise ValueError("request JSON must be an object")
                manifest = _manifest_from_payload(payload)
                self.store.register_dataset(manifest)
                return self._response(start_response, HTTPStatus.CREATED, {
                    "dataset_id": manifest.dataset_id,
                    "market": manifest.market.value,
                    "fingerprint": manifest.fingerprint,
                    "license_status": manifest.license_status.value,
                    "status": "manifest_registered_not_data_uploaded",
                })
            if method == "POST" and path == "/api/experiments":
                # Bound input size and accept JSON only; no arbitrary file paths or code.
                if environ.get("CONTENT_TYPE", "").split(";")[0].strip() != "application/json":
                    return self._response(start_response, HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                                          {"error": "Content-Type must be application/json"})
                length = int(environ.get("CONTENT_LENGTH") or "0")
                if not 0 < length <= 1_000_000:
                    return self._response(start_response, HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                                          {"error": "request body must be between 1 byte and 1 MB"})
                payload = json.loads(environ["wsgi.input"].read(length))
                if not isinstance(payload, dict):
                    raise ValueError("request JSON must be an object")
                spec = _create_spec(payload)
                _validate_dataset_coverage(self.store, spec)
                self.store.create_experiment(spec)
                self.store.append_event(spec.experiment_id, "experiment_created", {
                    "market": spec.market.value,
                    "track": spec.track.value,
                    "fingerprint": spec.fingerprint,
                })
                return self._response(start_response, HTTPStatus.CREATED, {
                    "experiment_id": spec.experiment_id,
                    "market": spec.market.value,
                    "track": spec.track.value,
                    "fingerprint": spec.fingerprint,
                    "status": "created_not_started",
                })
            if method == "GET" and path.startswith("/api/experiments/"):
                # Decode only the stable identifier segment; query never chooses a market ledger.
                experiment_id = path.removeprefix("/api/experiments/").strip("/")
                if not experiment_id or "/" in experiment_id:
                    raise KeyError(experiment_id)
                experiment = self.store.get_experiment(experiment_id)
                return self._response(start_response, HTTPStatus.OK, {
                    "experiment": experiment,
                    "events": self.store.events(experiment_id),
                    "candidates": self.store.candidates(experiment_id),
                })
            if method not in {"GET", "POST"}:
                return self._response(start_response, HTTPStatus.METHOD_NOT_ALLOWED,
                                      {"error": "method not allowed"})
            return self._response(start_response, HTTPStatus.NOT_FOUND, {"error": "route not found"})
        except sqlite3.IntegrityError as exc:
            return self._response(start_response, HTTPStatus.CONFLICT, {"error": f"record conflict: {exc}"})
        except sqlite3.IntegrityError as exc:
            return self._response(start_response, HTTPStatus.CONFLICT, {"error": f"record conflict: {exc}"})
        except KeyError as exc:
            return self._response(start_response, HTTPStatus.NOT_FOUND, {"error": f"not found: {exc}"})
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            return self._response(start_response, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception as exc:  # noqa: BLE001 - hide internal tracebacks from HTTP clients.
            return self._response(start_response, HTTPStatus.INTERNAL_SERVER_ERROR,
                                  {"error": f"internal error: {type(exc).__name__}"})


def create_app(database_path: str) -> ResearchAPI:
    """Create an API instance against a dedicated research database."""
    # Do not reuse cryptobot trading state databases for research records.
    return ResearchAPI(ExperimentStore(database_path))
