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
from .jobs import ResearchJobManager
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
<p>Creates an immutable experiment record. The second action queues the registered existing-strategy worker; it evaluates TRAIN, VALIDATION and OOS only.</p>
<form id="create-form">
<label>Market</label><select id="market"><option value="nse">NSE</option><option value="crypto">Crypto</option></select>
<label>Research track</label><select id="track"></select>
<label>Algorithm family</label><select id="family"></select>
<label>Resolution</label><select id="resolution"></select>
<label>Existing strategy (used when the family is existing_strategy)</label><select id="strategy-name"></select>
<label>Dataset IDs (comma-separated)</label><input id="dataset-ids" value="example-dataset-v1" required>
<label>Experiment ID</label><input id="experiment-id" required>
<label>Git commit</label><input id="git-commit" placeholder="40-character commit SHA" required>
<label>Cost model ID</label><input id="cost-model" value="nse-delivery-cost-model" required>
<label>Execution model ID</label><input id="execution-model" value="next-open-participation-impact-v1" required>
<label>Seed</label><input id="seed" type="number" min="0" value="42" required>
<label>Purging embargo (seconds)</label><input id="embargo-seconds" type="number" min="0" step="1" value="0" required>
<label>Objectives (comma-separated)</label><input id="objectives" value="net_return,max_drawdown,turnover" required>
<label>Strategy parameters JSON</label><textarea id="strategy-parameters" rows="3">{}</textarea>
<label>Optimisation settings JSON (random/grid/DE/Optuna TPE)</label><textarea id="optimization" rows="4">{"budget":24,"validation_candidates":6,"objective":"sharpe","points_per_numeric_dimension":2,"population_size":6,"generations":3,"mutation":0.7,"crossover":0.8,"startup_trials":8}</textarea>
<label>Hybrid search ensemble settings JSON</label><textarea id="hybrid-settings" rows="4">{"methods":["random_search","differential_evolution","bayesian"],"budget_per_method":8,"validation_candidates":6,"objective":"sharpe","de_population_size":4,"de_generations":1,"de_mutation":0.7,"de_crossover":0.8,"tpe_startup_trials":3}</textarea>
<label>Genetic-programming settings JSON</label><textarea id="gp-settings" rows="4">{"population_size":16,"generations":5,"max_depth":4,"max_nodes":31,"mutation_rate":0.2,"validation_candidates":4,"objective":"sharpe","feature_windows":[5,20,60]}</textarea>
<label>Neuroevolution settings JSON</label><textarea id="neuro-settings" rows="4">{"hidden_size":16,"population_size":16,"generations":5,"learning_rate":0.05,"noise_std":0.1,"weight_limit":8,"validation_candidates":4,"objective":"sharpe","feature_windows":[5,20,60]}</textarea>
<label>Strategy-composition settings JSON</label><textarea id="composition-settings" rows="4">{"population_size":16,"generations":5,"max_components":8,"mutation_rate":0.25,"validation_candidates":4,"objective":"sharpe","feature_windows":[5,20,60]}</textarea>
<label>Pareto / NSGA-II settings JSON</label><textarea id="pareto-settings" rows="4">{"population_size":16,"generations":5,"mutation_rate":0.2,"validation_candidates":8,"objectives":["cagr","max_drawdown","turnover"],"directions":["max","max","min"]}</textarea>
<label>Execution assumptions JSON</label><textarea id="execution-assumptions" rows="4">{"slippage_bps":5,"impact_coefficient_bps":10,"max_participation":0.05,"max_gross_exposure":1.0,"periods_per_year":252}</textarea>
<label>Crypto venue (single exchange)</label><input id="crypto-exchange" value="binance">
<label>Crypto maker/taker fee schedule JSON</label><textarea id="fee-schedule" rows="2">{"maker_fee_bps":10,"taker_fee_bps":10}</textarea>
<label>Training start / end (ISO timestamps)</label><input id="train-start" type="datetime-local" value="2016-01-01T00:00" required><input id="train-end" type="datetime-local" value="2020-01-01T00:00" required>
<label>Validation start / end</label><input id="val-start" type="datetime-local" value="2020-01-01T00:00" required><input id="val-end" type="datetime-local" value="2022-01-01T00:00" required>
<label>OOS start / end</label><input id="oos-start" type="datetime-local" value="2022-01-01T00:00" required><input id="oos-end" type="datetime-local" value="2024-01-01T00:00" required>
<label>Final holdout start / end</label><small>NSE holdout data must start after 1 October 2026; the prior 2024–2026 test window is exposed.</small><input id="hold-start" type="datetime-local" value="2026-10-02T00:00" required><input id="hold-end" type="datetime-local" value="2026-11-08T00:00" required>
<button type="submit" name="action" value="create">Create experiment record</button><button type="submit" name="action" value="queue">Create and queue evaluation</button><p id="form-status" class="status"></p>
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
<h2>Experiment comparison</h2>
<p>Compare two to ten experiments from one market. TRAIN, VALIDATION and OOS remain separate.</p>
<label>Experiment IDs (comma-separated)</label><input id="compare-ids" placeholder="experiment-a,experiment-b">
<button type="button" id="compare-button">Compare experiments</button>
<p id="compare-status" class="status"></p>
<table><thead><tr><th>Experiment</th><th>Candidate</th><th>Family</th><th>TRAIN Sharpe</th><th>VALIDATION Sharpe</th><th>OOS Sharpe</th></tr></thead><tbody id="comparison-rows"></tbody></table>
</section>
<section style="margin-top:16px">
<h2>Research jobs</h2>
<p>Persisted worker status and cooperative cancellation between partitions.</p>
<table><thead><tr><th>Job</th><th>Experiment</th><th>Runner</th><th>Status</th><th>Created</th><th>Action</th></tr></thead><tbody id="job-rows"></tbody></table>
</section>
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
const families = ["existing_strategy","random_search","grid_search","bayesian","differential_evolution","genetic_programming","neuroevolution","strategy_composition","pareto_search","hybrid"];
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
  const jobPayload = await api("/api/jobs?limit=100");
  const jobBody = $("job-rows");
  jobBody.replaceChildren();
  jobPayload.jobs.forEach(item => {
    // Render stored job metadata as text and invoke the actual cancel endpoint.
    const row = document.createElement("tr");
    [item.job_id, item.experiment_id, item.runner_name, item.status, item.created_at].forEach(value => {
      const cell = document.createElement("td");
      cell.textContent = value || "";
      row.appendChild(cell);
    });
    const actionCell = document.createElement("td");
    if (["queued", "running"].includes(item.status)) {
      const cancel = document.createElement("button");
      cancel.textContent = "Request cancel";
      cancel.addEventListener("click", async () => {
        try {
          await api("/api/jobs/" + encodeURIComponent(item.job_id) + "/cancel", {method:"POST"});
          await refresh();
        } catch (error) {
          $("form-status").textContent = "Cancellation error: " + error.message;
        }
      });
      actionCell.appendChild(cancel);
    } else {
      const inspect = document.createElement("button");
      inspect.textContent = "Inspect";
      inspect.addEventListener("click", async () => {
        const payload = await api("/api/jobs/" + encodeURIComponent(item.job_id));
        $("detail").textContent = JSON.stringify(payload.job, null, 2);
      });
      actionCell.appendChild(inspect);
    }
    row.appendChild(actionCell);
    jobBody.appendChild(row);
  });
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
$("market").addEventListener("change", () => {
  // Set the sampling calendar explicitly when switching independent markets.
  refreshTrackOptions();
  const assumptions = JSON.parse($("execution-assumptions").value);
  assumptions.periods_per_year = $("market").value === "crypto" ? 365 : 252;
  $("execution-assumptions").value = JSON.stringify(assumptions, null, 2);
  if ($("market").value === "nse") {
    $("cost-model").value = "nse-delivery-cost-model";
  }
});
$("filter-market").addEventListener("change", refresh);
$("compare-button").addEventListener("click", async () => {
  // Submit explicit experiment IDs; the server rejects mixed-market comparisons.
  const ids = $("compare-ids").value.split(",").map(value => value.trim()).filter(Boolean);
  $("compare-status").textContent = "Loading comparison…";
  const body = $("comparison-rows");
  body.replaceChildren();
  try {
    const query = ids.map(id => "experiment_id=" + encodeURIComponent(id)).join("&");
    const result = await api("/api/compare?" + query);
    result.candidates.forEach(candidate => {
      // Display stage metrics separately; never compute a combined market return.
      const metrics = candidate.metrics || {};
      const train = metrics.train || {};
      const validation = metrics.validation || {};
      const oos = metrics.out_of_sample || {};
      const values = [
        candidate.experiment_id,
        candidate.candidate_id,
        candidate.family,
        train.sharpe ?? metrics.train_objective ?? "—",
        validation.sharpe ?? "—",
        oos.sharpe ?? "—"
      ];
      const row = document.createElement("tr");
      values.forEach(value => {
        const cell = document.createElement("td");
        cell.textContent = String(value);
        row.appendChild(cell);
      });
      body.appendChild(row);
    });
    $("compare-status").textContent =
      "Compared " + result.experiment_ids.length + " " + result.market.toUpperCase() +
      " experiments; no cross-market aggregation.";
  } catch (error) {
    $("compare-status").textContent = "Comparison error: " + error.message;
  }
});
$("create-form").addEventListener("submit", async event => {
  event.preventDefault();
  const action = event.submitter ? event.submitter.value : "create";
  $("form-status").textContent = "Saving…";
  try {
    const value = id => $(id).value;
    const parseObject = id => {
      // Parse experiment settings as JSON instead of silently converting malformed text.
      const parsed = JSON.parse(value(id) || "{}");
      if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
        throw new Error(id + " must be a JSON object");
      }
      return parsed;
    };
    const market = value("market");
    const feeSchedule = market === "crypto" ? parseObject("fee-schedule") : null;
    const costModelId = market === "crypto"
      ? "crypto-" + value("crypto-exchange").toLowerCase() + "-taker-maker" +
        feeSchedule.maker_fee_bps + "-taker" + feeSchedule.taker_fee_bps
      : value("cost-model");
    const payload = {
      experiment_id: value("experiment-id"),
      market,
      track: value("track"),
      algorithm_family: value("family"),
      resolution: value("resolution"),
      dataset_ids: value("dataset-ids").split(",").map(x => x.trim()).filter(Boolean),
      random_seed: Number(value("seed")),
      embargo_seconds: Number(value("embargo-seconds")),
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
      cost_model_id: costModelId,
      execution_model_id: value("execution-model"),
      objectives: value("objectives").split(",").map(x => x.trim()).filter(Boolean),
      compute_backend: "auto",
      compute_device: "unverified",
      parameters: (() => {
        // Bind the selected model family and its bounded search settings to the spec fingerprint.
        const family = value("family");
        const common = {
          execution_assumptions: parseObject("execution-assumptions"),
          ...(market === "crypto" ? {fee_schedule: feeSchedule} : {})
        };
        const supportedExisting = ["existing_strategy","random_search","grid_search",
          "differential_evolution","bayesian","hybrid"];
        if (supportedExisting.includes(family)) {
          const result = {
            ...common,
            strategy_name: value("strategy-name"),
            strategy_parameters: parseObject("strategy-parameters")
          };
          if (family === "hybrid") {
            result.hybrid_optimization = parseObject("hybrid-settings");
          } else if (family !== "existing_strategy") {
            result.optimization = parseObject("optimization");
          }
          return result;
        }
        if (family === "genetic_programming") {
          return {...common, genetic_programming: parseObject("gp-settings")};
        }
        if (family === "neuroevolution") {
          return {...common, neuroevolution: parseObject("neuro-settings")};
        }
        if (family === "strategy_composition") {
          return {...common, strategy_composition: parseObject("composition-settings")};
        }
        if (family === "pareto_search") {
          return {
            ...common,
            strategy_name: value("strategy-name"),
            strategy_parameters: parseObject("strategy-parameters"),
            pareto_search: parseObject("pareto-settings")
          };
        }
        return {};
      })()
    };
    const result = await api("/api/experiments", {
      method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(payload)
    });
    $("form-status").textContent = "Created " + result.experiment_id;
    if (action === "queue") {
      const family = value("family");
      const runnerName = family === "existing_strategy"
        ? "existing_strategy_evaluation"
        : ["random_search","grid_search","differential_evolution","bayesian","hybrid"].includes(family)
          ? "existing_strategy_optimization"
          : family === "genetic_programming" ? "genetic_programming"
            : family === "neuroevolution" ? "neuroevolution"
            : family === "strategy_composition" ? "strategy_composition"
            : family === "pareto_search" ? "pareto_search" : null;
      if (!runnerName) {
        throw new Error("No connected worker exists for " + family + " yet.");
      }
      const queued = await api("/api/jobs", {
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({
          experiment_id: result.experiment_id,
          runner_name: runnerName,
          parameters: {}
        })
      });
      $("form-status").textContent = "Queued research job " + queued.job_id;
    }
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
    raw_embargo = payload.get("embargo_seconds", 0)
    if isinstance(raw_embargo, bool) or not isinstance(raw_embargo, int):
        raise ValueError("embargo_seconds must be an integer")
    algorithm_family = AlgorithmFamily(payload["algorithm_family"])
    supported_existing_families = {
        AlgorithmFamily.EXISTING_STRATEGY,
        AlgorithmFamily.RANDOM_SEARCH,
        AlgorithmFamily.GRID_SEARCH,
        AlgorithmFamily.DIFFERENTIAL_EVOLUTION,
        AlgorithmFamily.BAYESIAN,
        AlgorithmFamily.PARETO_SEARCH,
        AlgorithmFamily.HYBRID,
    }
    if algorithm_family in supported_existing_families:
        # Never accept arbitrary strategy names; resolve against the repository catalogue.
        strategy_name = parameters.get("strategy_name")
        if not isinstance(strategy_name, str) or not strategy_name.strip():
            raise ValueError(
                f"{algorithm_family.value} experiments require a registered strategy_name"
            )
        try:
            ExistingStrategyRegistry().describe(strategy_name)
        except KeyError as exc:
            raise ValueError(f"unknown existing strategy: {strategy_name}") from exc
    if algorithm_family is AlgorithmFamily.GENETIC_PROGRAMMING:
        # GP limits and feature windows are immutable inputs to the experiment fingerprint.
        gp = parameters.get("genetic_programming")
        required_gp = {
            "population_size", "generations", "max_depth", "max_nodes",
            "mutation_rate", "validation_candidates", "objective", "feature_windows",
        }
        if not isinstance(gp, dict) or not required_gp.issubset(gp):
            raise ValueError(f"genetic_programming settings require {sorted(required_gp)}")
        for key in ("population_size", "generations", "max_depth", "max_nodes", "validation_candidates"):
            value = gp[key]
            minimum = 4 if key == "population_size" else 3 if key == "max_nodes" else 1
            maximum = 12 if key == "max_depth" else 8191 if key == "max_nodes" else 10000
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or not minimum <= value <= maximum
            ):
                raise ValueError(
                    f"genetic_programming.{key} must be an integer from {minimum} to {maximum}"
                )
        evaluation_count = gp["population_size"] * (gp["generations"] + 1)
        if evaluation_count > 10000:
            raise ValueError("genetic_programming candidate count exceeds the 10000 evaluation limit")
        mutation = gp["mutation_rate"]
        if (
            isinstance(mutation, bool)
            or not isinstance(mutation, int | float)
            or not 0 <= mutation <= 1
        ):
            raise ValueError("genetic_programming.mutation_rate must be between zero and one")
        if gp["objective"] not in {"sharpe", "sortino", "cagr", "calmar", "total_return"}:
            raise ValueError("genetic_programming objective is not supported")
        feature_windows = gp["feature_windows"]
        if (
            not isinstance(feature_windows, list)
            or not feature_windows
            or any(isinstance(value, bool) or not isinstance(value, int) or value < 2
                   for value in feature_windows)
            or len(set(feature_windows)) != len(feature_windows)
        ):
            raise ValueError("genetic_programming.feature_windows must be unique integers >= 2")
    if algorithm_family is AlgorithmFamily.PARETO_SEARCH:
        # Multiobjective definitions are ordered and direction-aware in the experiment hash.
        pareto = parameters.get("pareto_search")
        required_pareto = {
            "population_size", "generations", "mutation_rate",
            "validation_candidates", "objectives", "directions",
        }
        if not isinstance(pareto, dict) or not required_pareto.issubset(pareto):
            raise ValueError(f"pareto_search settings require {sorted(required_pareto)}")
        for key in ("population_size", "generations", "validation_candidates"):
            value = pareto[key]
            minimum = 4 if key == "population_size" else 1
            maximum = 10000 if key != "validation_candidates" else 1000
            if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
                raise ValueError(f"pareto_search.{key} must be an integer from {minimum} to {maximum}")
        if pareto["population_size"] * (pareto["generations"] + 1) > 10000:
            raise ValueError("Pareto candidate count exceeds the 10000 evaluation limit")
        mutation = pareto["mutation_rate"]
        if (
            isinstance(mutation, bool)
            or not isinstance(mutation, int | float)
            or not 0 <= mutation <= 1
        ):
            raise ValueError("pareto_search.mutation_rate must be between zero and one")
        objectives = pareto["objectives"]
        directions = pareto["directions"]
        allowed_objectives = {
            "sharpe", "sortino", "cagr", "calmar", "total_return",
            "max_drawdown", "volatility", "win_rate", "turnover",
        }
        if (
            not isinstance(objectives, list)
            or len(objectives) < 2
            or len(objectives) != len(directions)
            or len(set(objectives)) != len(objectives)
            or any(name not in allowed_objectives for name in objectives)
            or any(direction not in {"min", "max"} for direction in directions)
        ):
            raise ValueError("pareto_search requires 2+ unique objectives with aligned min/max directions")
    if algorithm_family is AlgorithmFamily.STRATEGY_COMPOSITION:
        # Composition candidates are selected only from the fixed allow-listed component registry.
        composition = parameters.get("strategy_composition")
        required_composition = {
            "population_size", "generations", "max_components", "mutation_rate",
            "validation_candidates", "objective", "feature_windows",
        }
        if not isinstance(composition, dict) or not required_composition.issubset(composition):
            raise ValueError(
                f"strategy_composition settings require {sorted(required_composition)}"
            )
        for key in ("population_size", "generations", "max_components", "validation_candidates"):
            value = composition[key]
            minimum = 4 if key == "population_size" else 2 if key == "max_components" else 1
            maximum = 32 if key == "max_components" else 10000
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or not minimum <= value <= maximum
            ):
                raise ValueError(
                    f"strategy_composition.{key} must be an integer from {minimum} to {maximum}"
                )
        if composition["population_size"] * (composition["generations"] + 1) > 10000:
            raise ValueError("strategy_composition candidate count exceeds the 10000 evaluation limit")
        mutation = composition["mutation_rate"]
        if (
            isinstance(mutation, bool)
            or not isinstance(mutation, int | float)
            or not 0 <= mutation <= 1
        ):
            raise ValueError("strategy_composition.mutation_rate must be between zero and one")
        if composition["objective"] not in {"sharpe", "sortino", "cagr", "calmar", "total_return"}:
            raise ValueError("strategy_composition objective is not supported")
        windows = composition["feature_windows"]
        if (
            not isinstance(windows, list)
            or not windows
            or any(isinstance(value, bool) or not isinstance(value, int) or value < 2 for value in windows)
            or len(set(windows)) != len(windows)
        ):
            raise ValueError("strategy_composition.feature_windows must be unique integers >= 2")
    if algorithm_family is AlgorithmFamily.NEUROEVOLUTION:
        # Bound network dimensions, total candidates and numerical search parameters before queueing.
        neural = parameters.get("neuroevolution")
        required_neural = {
            "hidden_size", "population_size", "generations", "learning_rate",
            "noise_std", "weight_limit", "validation_candidates", "objective",
            "feature_windows",
        }
        if not isinstance(neural, dict) or not required_neural.issubset(neural):
            raise ValueError(f"neuroevolution settings require {sorted(required_neural)}")
        for key in ("hidden_size", "population_size", "generations", "validation_candidates"):
            value = neural[key]
            minimum = 4 if key == "population_size" else 1
            maximum = 512 if key == "hidden_size" else 10000
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or not minimum <= value <= maximum
            ):
                raise ValueError(
                    f"neuroevolution.{key} must be an integer from {minimum} to {maximum}"
                )
        if "inference_batch_size" in neural:
            batch_size = neural["inference_batch_size"]
            if isinstance(batch_size, bool) or not isinstance(batch_size, int) or not 1 <= batch_size <= 256:
                raise ValueError("neuroevolution.inference_batch_size must be in 1..256")
        if neural["population_size"] % 2:
            raise ValueError("neuroevolution.population_size must be even")
        if neural["population_size"] * neural["generations"] > 10000:
            raise ValueError("neuroevolution candidate count exceeds the 10000 evaluation limit")
        for key in ("learning_rate", "noise_std", "weight_limit"):
            value = neural[key]
            if (
                isinstance(value, bool)
                or not isinstance(value, int | float)
                or not float("-inf") < value < float("inf")
                or value <= 0
            ):
                raise ValueError(f"neuroevolution.{key} must be finite and positive")
        if neural["objective"] not in {"sharpe", "sortino", "cagr", "calmar", "total_return"}:
            raise ValueError("neuroevolution objective is not supported")
        windows = neural["feature_windows"]
        if (
            not isinstance(windows, list)
            or not windows
            or any(isinstance(value, bool) or not isinstance(value, int) or value < 2 for value in windows)
            or len(set(windows)) != len(windows)
        ):
            raise ValueError("neuroevolution.feature_windows must be unique integers >= 2")
    if algorithm_family is AlgorithmFamily.HYBRID:
        # A hybrid is an ensemble of independently seeded search methods over one strategy.
        hybrid = parameters.get("hybrid_optimization")
        required_hybrid = {
            "methods", "budget_per_method", "validation_candidates", "objective",
        }
        if not isinstance(hybrid, dict) or not required_hybrid.issubset(hybrid):
            raise ValueError(f"hybrid_optimization requires {sorted(required_hybrid)}")
        methods = hybrid["methods"]
        allowed_methods = {
            "random_search", "grid_search", "differential_evolution", "bayesian"
        }
        if (
            not isinstance(methods, list)
            or len(methods) < 2
            or len(set(methods)) != len(methods)
            or any(method not in allowed_methods for method in methods)
        ):
            raise ValueError("hybrid methods must be 2+ unique supported search methods")
        for key in ("budget_per_method", "validation_candidates"):
            value = hybrid[key]
            minimum = 4 if key == "budget_per_method" else 1
            maximum = 10000 if key == "budget_per_method" else 1000
            if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
                raise ValueError(f"hybrid_optimization.{key} must be an integer from {minimum} to {maximum}")
        if hybrid["budget_per_method"] * len(methods) > 10000:
            raise ValueError("hybrid total search budget exceeds 10000 evaluations")
        if hybrid["objective"] not in {"sharpe", "sortino", "cagr", "calmar", "total_return"}:
            raise ValueError("hybrid objective is not supported")
        if "grid_search" in methods:
            points = hybrid.get("points_per_numeric_dimension")
            if isinstance(points, bool) or not isinstance(points, int) or points < 2:
                raise ValueError("hybrid grid_search requires points_per_numeric_dimension >= 2")
        if "differential_evolution" in methods:
            required_de = {"de_population_size", "de_generations", "de_mutation", "de_crossover"}
            if not required_de.issubset(hybrid):
                raise ValueError(f"hybrid differential_evolution requires {sorted(required_de)}")
            population = hybrid["de_population_size"]
            generations = hybrid["de_generations"]
            if (
                isinstance(population, bool) or not isinstance(population, int) or population < 4
                or isinstance(generations, bool) or not isinstance(generations, int) or generations < 1
            ):
                raise ValueError("hybrid DE population/generations are outside valid bounds")
            if population * (generations + 1) != hybrid["budget_per_method"]:
                raise ValueError("hybrid DE population_size * (generations + 1) must equal budget_per_method")
            mutation = float(hybrid["de_mutation"])
            crossover = float(hybrid["de_crossover"])
            if not 0 < mutation <= 2 or not 0 <= crossover <= 1:
                raise ValueError("hybrid DE mutation/crossover are outside valid bounds")
        if "bayesian" in methods:
            startup = hybrid.get("tpe_startup_trials")
            if isinstance(startup, bool) or not isinstance(startup, int) or not 1 <= startup < hybrid["budget_per_method"]:
                raise ValueError("hybrid TPE startup trials must be less than budget_per_method")
    if algorithm_family in {
        AlgorithmFamily.RANDOM_SEARCH,
        AlgorithmFamily.GRID_SEARCH,
        AlgorithmFamily.DIFFERENTIAL_EVOLUTION,
        AlgorithmFamily.BAYESIAN,
    }:
        # Search budget and validation shortlist are first-class immutable experiment inputs.
        optimization = parameters.get("optimization")
        if not isinstance(optimization, dict):
            raise ValueError("optimizer experiments require parameters.optimization")
        required_optimization = {"budget", "validation_candidates", "objective"}
        if not required_optimization.issubset(optimization):
            raise ValueError(
                f"parameters.optimization requires {sorted(required_optimization)}"
            )
        for integer_key in ("budget", "validation_candidates"):
            raw = optimization[integer_key]
            minimum = 4 if integer_key == "budget" else 1
            maximum = 10000 if integer_key == "budget" else 1000
            if (
                isinstance(raw, bool)
                or not isinstance(raw, int)
                or not minimum <= raw <= maximum
            ):
                raise ValueError(
                    f"optimization.{integer_key} must be an integer from {minimum} to {maximum}"
                )
        objective_name = str(optimization["objective"])
        if objective_name not in {"sharpe", "sortino", "cagr", "calmar", "total_return"}:
            raise ValueError("optimization.objective must be sharpe, sortino, cagr, calmar or total_return")
        if algorithm_family is AlgorithmFamily.GRID_SEARCH:
            points = optimization.get("points_per_numeric_dimension")
            if isinstance(points, bool) or not isinstance(points, int) or points < 2:
                raise ValueError("grid_search requires points_per_numeric_dimension >= 2")
        elif algorithm_family is AlgorithmFamily.DIFFERENTIAL_EVOLUTION:
            missing_de = {"population_size", "generations", "mutation", "crossover"} - set(optimization)
            if missing_de:
                raise ValueError(f"differential_evolution settings missing: {sorted(missing_de)}")
            population = optimization.get("population_size")
            generations = optimization.get("generations")
            if (
                isinstance(population, bool) or not isinstance(population, int) or population < 4
                or isinstance(generations, bool) or not isinstance(generations, int) or generations < 1
            ):
                raise ValueError("differential_evolution requires population_size >= 4 and generations >= 1")
            if optimization["budget"] != population * (generations + 1):
                raise ValueError(
                    "differential_evolution budget must equal population_size * (generations + 1)"
                )
            mutation = float(optimization.get("mutation", 0.7))
            crossover = float(optimization.get("crossover", 0.8))
            if not 0 < mutation <= 2 or not 0 <= crossover <= 1:
                raise ValueError("differential_evolution mutation/crossover values are outside valid bounds")
        elif algorithm_family is AlgorithmFamily.BAYESIAN:
            startup = optimization.get("startup_trials")
            if isinstance(startup, bool) or not isinstance(startup, int) or not 1 <= startup < optimization["budget"]:
                raise ValueError("bayesian TPE requires 1 <= startup_trials < budget")
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
        embargo_seconds=raw_embargo,
    )


class ResearchAPI:
    """Minimal local WSGI API for creating and inspecting actual experiment records."""

    def __init__(
        self,
        store: ExperimentStore,
        job_manager: ResearchJobManager | None = None,
    ) -> None:
        # Cache the catalogue and optional trusted runner manager for this local API process.
        self.store = store
        self.job_manager = job_manager
        self.strategy_registry = ExistingStrategyRegistry()

    def shutdown(self) -> None:
        # Release worker threads when the local dashboard server exits.
        if self.job_manager is not None:
            self.job_manager.shutdown(wait=True, cancel_pending=True)

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
            if method == "GET" and path == "/api/runners":
                # Expose only server-registered trusted runner identifiers.
                names = self.job_manager.runner_names() if self.job_manager is not None else ()
                return self._response(start_response, HTTPStatus.OK, {"runners": list(names)})
            if method == "GET" and path == "/api/compare":
                # Only compare experiments within one financial environment.
                query = parse_qs(environ.get("QUERY_STRING", ""))
                experiment_ids = query.get("experiment_id", [])
                if not 2 <= len(experiment_ids) <= 10:
                    raise ValueError("comparison requires between 2 and 10 experiment_id values")
                if len(set(experiment_ids)) != len(experiment_ids):
                    raise ValueError("comparison experiment IDs must be unique")
                records = [self.store.get_experiment(experiment_id) for experiment_id in experiment_ids]
                markets = {record["market"] for record in records}
                if len(markets) != 1:
                    raise ValueError("NSE and crypto experiments cannot be compared in one financial view")
                candidate_rows = []
                for record in records:
                    for candidate in self.store.candidates(record["experiment_id"]):
                        candidate_rows.append({
                            "experiment_id": record["experiment_id"],
                            "market": record["market"],
                            "track": record["track"],
                            "candidate_id": candidate["candidate_id"],
                            "candidate_digest": candidate["candidate_digest"],
                            "family": candidate["family"],
                            "generation": candidate["generation"],
                            "parameters": candidate["parameters"],
                            "metrics": candidate["metrics"],
                            "lineage": candidate["lineage"],
                        })
                return self._response(start_response, HTTPStatus.OK, {
                    "market": next(iter(markets)),
                    "experiment_ids": experiment_ids,
                    "candidate_count": len(candidate_rows),
                    "candidates": candidate_rows,
                    "aggregation": "none; candidate metrics remain partitioned and market-isolated",
                })
            if method == "GET" and path == "/api/jobs":
                # Jobs retain experiment references; no financial results are aggregated here.
                query = parse_qs(environ.get("QUERY_STRING", ""))
                experiment_values = query.get("experiment_id", [])
                limit_values = query.get("limit", ["100"])
                rows = self.store.list_jobs(
                    experiment_id=experiment_values[0] if experiment_values else None,
                    limit=int(limit_values[0]),
                )
                return self._response(start_response, HTTPStatus.OK, {"jobs": rows})
            if method == "POST" and path == "/api/jobs":
                # Only a registered runner name and JSON parameters are accepted.
                if self.job_manager is None:
                    return self._response(start_response, HTTPStatus.SERVICE_UNAVAILABLE,
                                          {"error": "no research worker manager is configured"})
                if environ.get("CONTENT_TYPE", "").split(";")[0].strip() != "application/json":
                    return self._response(start_response, HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                                          {"error": "Content-Type must be application/json"})
                length = int(environ.get("CONTENT_LENGTH") or "0")
                if not 0 < length <= 100_000:
                    return self._response(start_response, HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                                          {"error": "job request must be between 1 byte and 100 KB"})
                payload = json.loads(environ["wsgi.input"].read(length))
                if not isinstance(payload, dict):
                    raise ValueError("job request JSON must be an object")
                experiment_id = str(payload["experiment_id"])
                runner_name = str(payload["runner_name"])
                parameters = payload.get("parameters", {})
                if not isinstance(parameters, dict):
                    raise ValueError("job parameters must be a JSON object")
                record = self.store.get_experiment(experiment_id)
                family = AlgorithmFamily(record["spec"]["algorithm_family"])
                if family is AlgorithmFamily.EXISTING_STRATEGY:
                    expected_runner = "existing_strategy_evaluation"
                elif family in {
                    AlgorithmFamily.RANDOM_SEARCH,
                    AlgorithmFamily.GRID_SEARCH,
                    AlgorithmFamily.DIFFERENTIAL_EVOLUTION,
                    AlgorithmFamily.BAYESIAN,
                    AlgorithmFamily.HYBRID,
                }:
                    expected_runner = "existing_strategy_optimization"
                elif family is AlgorithmFamily.GENETIC_PROGRAMMING:
                    expected_runner = "genetic_programming"
                elif family is AlgorithmFamily.NEUROEVOLUTION:
                    expected_runner = "neuroevolution"
                elif family is AlgorithmFamily.STRATEGY_COMPOSITION:
                    expected_runner = "strategy_composition"
                elif family is AlgorithmFamily.PARETO_SEARCH:
                    expected_runner = "pareto_search"
                else:
                    raise ValueError(
                        "no job runner is registered for this algorithm family yet"
                    )
                if runner_name != expected_runner:
                    raise ValueError(
                        f"algorithm family {family.value} requires runner {expected_runner}"
                    )
                job_id = self.job_manager.submit(experiment_id, runner_name, parameters)
                return self._response(start_response, HTTPStatus.ACCEPTED, {
                    "job_id": job_id,
                    "experiment_id": experiment_id,
                    "runner_name": runner_name,
                    "status": "queued",
                })
            if path.startswith("/api/jobs/"):
                # Job IDs are opaque identifiers and cannot select arbitrary runner code.
                suffix = path.removeprefix("/api/jobs/").strip("/")
                if method == "GET":
                    if not suffix or "/" in suffix:
                        raise KeyError(suffix)
                    return self._response(
                        start_response, HTTPStatus.OK, {"job": self.store.get_job(suffix)}
                    )
                if method == "POST" and suffix.endswith("/cancel"):
                    job_id = suffix.removesuffix("/cancel").strip("/")
                    if not job_id or "/" in job_id:
                        raise KeyError(job_id)
                    if self.job_manager is None:
                        return self._response(start_response, HTTPStatus.SERVICE_UNAVAILABLE,
                                              {"error": "no research worker manager is configured"})
                    cancelled = self.job_manager.cancel(job_id)
                    return self._response(start_response, HTTPStatus.OK, {
                        "job_id": job_id,
                        "cancellation_requested": cancelled,
                        "job": self.store.get_job(job_id),
                    })
                return self._response(start_response, HTTPStatus.METHOD_NOT_ALLOWED,
                                      {"error": "job route does not support this method"})
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
        except KeyError as exc:
            return self._response(start_response, HTTPStatus.NOT_FOUND, {"error": f"not found: {exc}"})
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            return self._response(start_response, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception as exc:  # noqa: BLE001 - hide internal tracebacks from HTTP clients.
            return self._response(start_response, HTTPStatus.INTERNAL_SERVER_ERROR,
                                  {"error": f"internal error: {type(exc).__name__}"})


def create_app(
    database_path: str,
    *,
    crypto_data_root: str | None = None,
    max_workers: int = 1,
    max_queued: int = 8,
) -> ResearchAPI:
    """Create an API with a dedicated store and a bounded allow-listed worker manager."""
    # Do not reuse cryptobot trading state databases for research records.
    from .runners import build_default_job_manager

    store = ExperimentStore(database_path)
    # Jobs from a previous process cannot resume in a ThreadPoolExecutor; mark them failed.
    store.recover_interrupted_jobs()
    manager = build_default_job_manager(
        store,
        crypto_data_root=crypto_data_root,
        max_workers=max_workers,
        max_queued=max_queued,
    )
    return ResearchAPI(store, manager)
