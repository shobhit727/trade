"""Trusted allow-listed research runners for the persistent job manager."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Mapping

import numpy as np
import pandas as pd

from .adapters import CryptoLocalAdapter, NSELegacyAdapter, RESOLUTION_MAP
from .composition import Composition, StrategyComposer
from .compute import ComputeEngine
from .composition_policy import composition_scores, default_component_registry
from .costs import CryptoVenueFeeCalculator, NSEDeliveryFeeCalculator
from .data_catalog import LicenseStatus
from .domain import AlgorithmFamily, DataResolution, Market, ResearchTrack
from .evaluation import (
    ExistingStrategyEvaluation,
    _bars_fingerprint,
    _partition_target_frame,
    evaluate_existing_strategy,
)
from .experiments import ExperimentSpec
from .fx import FXRateSeries, convert_ohlcv_to_inr
from .features import PointInTimeFeatureEngine
from .genetic_programming import GeneticProgrammer, Node
from .jobs import JobContext
from .model_evaluation import build_model_feature_panel, evaluate_model_scores
from .neuroevolution import DenseMLP, EvolutionStrategy
from .optimizers import (
    Candidate as SearchCandidate,
    Parameter as SearchParameter,
    SearchResult,
    differential_evolution,
    grid_search,
    optuna_tpe_search,
    random_search,
)
from .pareto import ParetoCandidate, non_dominated_fronts, nsga2_optimize, select_nsga2
from .portfolio import PortfolioConfig
from .storage import ExperimentStore
from .statistics import candidate_family_report_from_returns
from .strategy_catalog import ExistingStrategyRegistry


D = Decimal


def _parse_timestamp(value: str) -> datetime:
    # Persisted ExperimentSpec timestamps are offset-aware ISO-8601 strings.
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("stored experiment timestamp is timezone-naive")
    return parsed


def experiment_spec_from_record(record: Mapping[str, Any]) -> ExperimentSpec:
    """Reconstruct the exact immutable experiment definition from SQLite JSON."""
    # Reject schema drift instead of silently running a partial experiment definition.
    data = record["spec"]
    windows = data["windows"]
    return ExperimentSpec(
        experiment_id=data["experiment_id"],
        market=Market(data["market"]),
        track=ResearchTrack(data["track"]),
        algorithm_family=AlgorithmFamily(data["algorithm_family"]),
        resolution=DataResolution(data["resolution"]),
        dataset_ids=tuple(data["dataset_ids"]),
        random_seed=int(data["random_seed"]),
        git_commit=data["git_commit"],
        code_version=data["code_version"],
        training_start=_parse_timestamp(windows["training"][0]),
        training_end=_parse_timestamp(windows["training"][1]),
        validation_start=_parse_timestamp(windows["validation"][0]),
        validation_end=_parse_timestamp(windows["validation"][1]),
        oos_start=_parse_timestamp(windows["oos"][0]),
        oos_end=_parse_timestamp(windows["oos"][1]),
        final_holdout_start=_parse_timestamp(windows["final_holdout"][0]),
        final_holdout_end=_parse_timestamp(windows["final_holdout"][1]),
        cost_model_id=data["cost_model_id"],
        execution_model_id=data["execution_model_id"],
        objectives=tuple(data["objectives"]),
        compute_backend=data["compute_backend"],
        compute_device=data["compute_device"],
        parameters=dict(data["parameters"]),
        embargo_seconds=int(data.get("embargo_seconds", 0)),
        created_at=_parse_timestamp(data["created_at"]),
    )


def _sha256(path: Path) -> str:
    # Read in chunks to avoid duplicating large historical files in memory.
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolution_delta(resolution: DataResolution) -> pd.Timedelta:
    # FX close observations from open-stamped bars become available after this interval.
    durations = {
        DataResolution.ONE_SECOND: "1s",
        DataResolution.ONE_MINUTE: "1min",
        DataResolution.FIVE_MINUTES: "5min",
        DataResolution.FIFTEEN_MINUTES: "15min",
        DataResolution.THIRTY_MINUTES: "30min",
        DataResolution.ONE_HOUR: "1h",
        DataResolution.FOUR_HOURS: "4h",
        DataResolution.ONE_DAY: "1d",
        DataResolution.ONE_WEEK: "7d",
        DataResolution.ONE_MONTH: "30d",
    }
    if resolution not in durations:
        raise ValueError(f"{resolution.value} does not have a supported fixed FX bar duration")
    return pd.Timedelta(durations[resolution])


def _crypto_adapter(manifest: Mapping[str, Any], data_root: Path) -> CryptoLocalAdapter:
    # Timestamp and quote conventions are explicit manifest fields, not symbol guesses.
    metadata = manifest["extra_metadata"]
    return CryptoLocalAdapter(
        data_root,
        str(manifest["exchange"]).lower(),
        timezone_name=str(manifest["timezone"]),
        numeric_timestamp_unit=metadata.get("numeric_timestamp_unit") or None,
        quote_currency=metadata.get("quote_currency") or None,
        fx_dataset_id=metadata.get("fx_dataset_id") or None,
        timestamp_position=metadata.get("timestamp_position") or None,
    )


def _verified_crypto_raw_frame(
    manifest: Mapping[str, Any],
    *,
    data_root: Path,
    resolution: DataResolution,
    max_time: datetime,
) -> tuple[pd.DataFrame, CryptoLocalAdapter]:
    # Resolve the registered instrument against its exchange folder and verify its hash.
    adapter = _crypto_adapter(manifest, data_root)
    instrument = str(manifest["instrument"])
    source = next(
        (candidate.resolve() for candidate in adapter._candidate_paths(instrument, resolution)
         if candidate.is_file()),
        None,
    )
    if source is None:
        raise FileNotFoundError(
            f"registered crypto source missing for {manifest['exchange']}:{instrument}"
        )
    try:
        source.relative_to(adapter.exchange_root)
    except ValueError as exc:
        raise ValueError("registered crypto source escapes its exchange directory") from exc
    expected_hash = manifest["extra_metadata"].get("file_sha256")
    if not expected_hash or _sha256(source) != expected_hash:
        raise ValueError(
            f"crypto source checksum mismatch for {manifest['exchange']}:{instrument}"
        )
    # The adapter returns a half-open panel ending before the locked OOS boundary.
    frame = adapter.load(instrument, resolution, end=max_time)
    if frame.empty:
        raise ValueError(f"no observations before OOS boundary for {instrument}")
    return frame, adapter


def _verified_crypto_frame(
    store: ExperimentStore,
    manifest: Mapping[str, Any],
    *,
    data_root: Path,
    resolution: DataResolution,
    max_time: datetime,
) -> pd.DataFrame:
    """Load an INR-normalised crypto frame, clipped before the protected OOS boundary."""
    # Only spot OHLCV data is handled; derivatives require their own margin accounting.
    metadata = manifest["extra_metadata"]
    quote_currency = str(metadata.get("quote_currency") or "").upper()
    timestamp_position = str(metadata.get("timestamp_position") or "")
    if not quote_currency:
        raise ValueError(
            f"{manifest['instrument']} must explicitly declare quote_currency in its manifest"
        )
    if timestamp_position != "bar_open":
        raise ValueError(
            f"{manifest['instrument']} portfolio simulation requires timestamp_position='bar_open'"
        )
    raw_frame, adapter = _verified_crypto_raw_frame(
        manifest,
        data_root=data_root,
        resolution=resolution,
        max_time=max_time,
    )
    if quote_currency == "INR":
        return raw_frame

    # Non-INR spot pairs require a separate, licensed FX dataset with an explicit pair.
    fx_dataset_id = str(metadata.get("fx_dataset_id") or "")
    if not fx_dataset_id:
        raise ValueError(
            f"{manifest['instrument']} is quoted in {quote_currency}; register fx_dataset_id"
        )
    fx_row = store.get_dataset(fx_dataset_id)
    fx_manifest = fx_row["manifest"]
    fx_metadata = fx_manifest["extra_metadata"]
    if fx_row["market"] != Market.CRYPTO.value:
        raise ValueError("FX dataset must belong to the crypto data environment")
    if fx_manifest["license_status"] != LicenseStatus.APPROVED.value:
        raise ValueError("FX dataset licence is not approved")
    if fx_manifest["resolution"] != resolution.value:
        raise ValueError("FX dataset resolution must match the crypto price dataset")
    if fx_manifest["category"] not in {"fx", "ohlcv"}:
        raise ValueError("registered FX source must be category fx or ohlcv")
    if str(fx_metadata.get("base_currency") or "").upper() != quote_currency:
        raise ValueError("FX dataset base_currency must match the asset quote currency")
    if str(fx_metadata.get("quote_currency") or "").upper() != "INR":
        raise ValueError("FX dataset quote_currency must be INR")
    fx_position = str(fx_metadata.get("timestamp_position") or "")
    if fx_position not in {"bar_open", "bar_close"}:
        raise ValueError("FX dataset must declare timestamp_position")
    fx_frame, _ = _verified_crypto_raw_frame(
        fx_manifest,
        data_root=data_root,
        resolution=resolution,
        max_time=max_time,
    )
    rates = fx_frame["close"].copy()
    if fx_position == "bar_open":
        # The close of an open-stamped FX candle becomes available only after its interval.
        rates.index = rates.index + _resolution_delta(resolution)
    staleness_seconds = metadata.get("max_fx_staleness_seconds")
    if staleness_seconds is None:
        raise ValueError("crypto manifest must declare max_fx_staleness_seconds")
    fx_rates = FXRateSeries(
        rates=rates,
        quote_currency=quote_currency,
        source_id=fx_dataset_id,
        max_staleness=timedelta(seconds=float(staleness_seconds)),
    )
    # Backward-as-of alignment prevents future FX values from entering the crypto price panel.
    # Convert the already-clipped price frame; do not reload rows from the locked holdout.
    return convert_ohlcv_to_inr(
        raw_frame,
        fx_rates,
        source_quote_currency=quote_currency,
    )


def load_registered_bars(
    store: ExperimentStore,
    spec: ExperimentSpec,
    *,
    crypto_data_root: str | Path | None = None,
) -> dict[str, pd.DataFrame]:
    """Load approved registered sources and verify their checksums before evaluation."""
    # Each dataset must be same-market, same-resolution and locally available.
    root = Path(
        crypto_data_root or os.getenv("RESEARCH_CRYPTO_DATA_ROOT", "data/crypto")
    ).resolve()
    output: dict[str, pd.DataFrame] = {}
    for dataset_id in spec.dataset_ids:
        row = store.get_dataset(dataset_id)
        manifest = row["manifest"]
        if row["market"] != spec.market.value:
            raise ValueError(f"cross-market dataset rejected: {dataset_id}")
        if row["resolution"] != spec.resolution.value:
            raise ValueError(f"dataset {dataset_id} resolution differs from experiment")
        if manifest["license_status"] != LicenseStatus.APPROVED.value:
            raise ValueError(f"dataset {dataset_id} licence is not approved")
        if manifest["category"] != "ohlcv":
            raise ValueError(f"dataset {dataset_id} is not a tradable OHLCV dataset")
        instrument = str(manifest["instrument"])
        if instrument in output:
            raise ValueError(f"duplicate instrument dataset in experiment: {instrument}")

        if spec.market is Market.NSE:
            from research.optimize import config as optimizer_config

            timeframe = RESOLUTION_MAP.get(spec.resolution)
            if timeframe is None:
                raise ValueError(f"NSE adapter does not support {spec.resolution.value}")
            path = optimizer_config.DATA_DIR / f"{instrument}_{timeframe}.csv"
            expected_hash = manifest["extra_metadata"].get("file_sha256")
            if not path.is_file() or not expected_hash or _sha256(path) != expected_hash:
                raise ValueError(f"NSE source missing or checksum mismatch for {instrument}")
            frame = NSELegacyAdapter(timezone_name=manifest["timezone"]).load(
                instrument, spec.resolution, end=spec.oos_end
            )
        else:
            frame = _verified_crypto_frame(
                store,
                manifest,
                data_root=root,
                resolution=spec.resolution,
                max_time=spec.oos_end,
            )
        if frame.empty:
            raise ValueError(f"dataset {dataset_id} has no usable OHLCV rows")
        output[instrument] = frame

    if not output:
        raise ValueError("experiment has no loadable registered OHLCV datasets")
    return output


def _build_portfolio_config(
    spec: ExperimentSpec,
    manifests: list[Mapping[str, Any]],
) -> tuple[PortfolioConfig, int]:
    # Execution assumptions are experiment parameters, never hidden runner defaults.
    assumptions = spec.parameters.get("execution_assumptions")
    if not isinstance(assumptions, dict):
        raise ValueError("parameters.execution_assumptions must declare fill assumptions")
    required = {
        "slippage_bps",
        "impact_coefficient_bps",
        "max_participation",
        "max_gross_exposure",
        "periods_per_year",
    }
    missing = required - set(assumptions)
    if missing:
        raise ValueError(f"execution_assumptions missing: {sorted(missing)}")
    periods_per_year = int(assumptions["periods_per_year"])
    if periods_per_year < 1:
        raise ValueError("periods_per_year must be positive")
    fee_calculator = None
    if spec.market is Market.NSE:
        fee_calculator = NSEDeliveryFeeCalculator()
        if spec.cost_model_id != fee_calculator.model_id:
            raise ValueError(
                "NSE cost_model_id must match the existing statutory delivery calculator "
                f"{fee_calculator.model_id}"
            )
    else:
        exchanges = {str(item["exchange"]).lower() for item in manifests}
        if len(exchanges) != 1:
            raise ValueError("one crypto portfolio experiment currently requires a single exchange")
        schedule = spec.parameters.get("fee_schedule")
        if not isinstance(schedule, dict):
            raise ValueError("crypto parameters.fee_schedule must declare maker_fee_bps and taker_fee_bps")
        if "maker_fee_bps" not in schedule or "taker_fee_bps" not in schedule:
            raise ValueError("crypto fee_schedule requires maker_fee_bps and taker_fee_bps")
        fee_calculator = CryptoVenueFeeCalculator(
            exchange=next(iter(exchanges)),
            maker_fee_bps=D(str(schedule["maker_fee_bps"])),
            taker_fee_bps=D(str(schedule["taker_fee_bps"])),
            liquidity_role="taker",
        )
        if spec.cost_model_id != fee_calculator.model_id:
            raise ValueError(
                "cost_model_id must equal the exchange maker/taker fee schedule fingerprint "
                f"{fee_calculator.model_id}"
            )

    config = PortfolioConfig(
        market=spec.market,
        fee_bps=D("0"),
        slippage_bps=D(str(assumptions["slippage_bps"])),
        impact_coefficient_bps=D(str(assumptions["impact_coefficient_bps"])),
        max_participation=D(str(assumptions["max_participation"])),
        max_gross_exposure=D(str(assumptions["max_gross_exposure"])),
        assumed_timezone="UTC",
        cost_model_id=spec.cost_model_id,
        execution_model_id=spec.execution_model_id,
        fee_calculator=fee_calculator,
    )
    return config, periods_per_year


class ExistingStrategyJobRunner:
    """Trusted job runner for one frozen existing-strategy experiment."""

    def __init__(
        self,
        *,
        crypto_data_root: str | Path | None = None,
        bar_loader: Callable[[ExperimentStore, ExperimentSpec], dict[str, pd.DataFrame]] | None = None,
    ) -> None:
        # A loader injection point makes orchestration testable without real market files.
        self.crypto_data_root = crypto_data_root
        self.bar_loader = bar_loader or (
            lambda store, spec: load_registered_bars(
                store, spec, crypto_data_root=self.crypto_data_root
            )
        )

    def __call__(
        self,
        context: JobContext,
        experiment_record: dict[str, Any],
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        # Worker arguments may tune no hidden parameters; immutable spec is authoritative.
        if parameters:
            raise ValueError("this runner accepts no job-time overrides; create a new experiment spec")
        context.check_cancelled()
        spec = experiment_spec_from_record(experiment_record)
        if spec.algorithm_family is not AlgorithmFamily.EXISTING_STRATEGY:
            raise ValueError("existing_strategy_evaluation runner requires existing_strategy family")
        manifests = [context.store.get_dataset(dataset_id)["manifest"] for dataset_id in spec.dataset_ids]
        bars = self.bar_loader(context.store, spec)
        context.log(f"loaded {len(bars)} registered instruments for {spec.market.value}")
        config, periods_per_year = _build_portfolio_config(spec, manifests)
        context.log("starting TRAIN, VALIDATION and OOS evaluation; final holdout remains sealed")
        result: ExistingStrategyEvaluation = evaluate_existing_strategy(
            spec,
            bars,
            config,
            periods_per_year=periods_per_year,
            store=context.store,
            check_cancelled=context.check_cancelled,
            progress_callback=lambda stage, completed, total: context.log(
                f"{stage}: {completed}/{total} partitions complete"
            ),
        )
        context.log("evaluation completed; final holdout was not accessed")
        return result.to_dict()


class ExistingStrategyOptimizerJobRunner:
    """Optimise an existing strategy on TRAIN, select on VALIDATION, then evaluate OOS."""

    OBJECTIVES = frozenset({"sharpe", "sortino", "cagr", "calmar", "total_return"})

    def __init__(
        self,
        *,
        crypto_data_root: str | Path | None = None,
        bar_loader: Callable[[ExperimentStore, ExperimentSpec], dict[str, pd.DataFrame]] | None = None,
    ) -> None:
        # Keep the same verified local data path as the frozen-strategy evaluator.
        self.crypto_data_root = crypto_data_root
        self.bar_loader = bar_loader or (
            lambda store, spec: load_registered_bars(
                store, spec, crypto_data_root=self.crypto_data_root
            )
        )
        self.registry = ExistingStrategyRegistry()

    @staticmethod
    def _search_parameters(descriptor) -> tuple[SearchParameter, ...]:
        # Convert the repository's original typed parameter catalogue without duplicating it.
        parameters: list[SearchParameter] = []
        for item in descriptor.parameters:
            kind = item["kind"]
            if kind in {"int", "float"}:
                parameters.append(SearchParameter(
                    name=item["name"],
                    low=float(item["low"]),
                    high=float(item["high"]),
                    kind=kind,
                ))
            elif kind == "bool":
                parameters.append(SearchParameter(
                    name=item["name"],
                    kind="categorical",
                    choices=(False, True),
                ))
            elif kind == "choice":
                parameters.append(SearchParameter(
                    name=item["name"],
                    kind="categorical",
                    choices=tuple(item["choices"]),
                ))
            else:
                raise ValueError(f"unsupported existing strategy parameter kind: {kind}")
        if not parameters:
            raise ValueError("selected strategy has no searchable parameters")
        return tuple(parameters)

    @staticmethod
    def _config_key(parameters: Mapping[str, Any]) -> str:
        # Canonical JSON ensures candidate ordering and deduplication are reproducible.
        return json.dumps(parameters, sort_keys=True, separators=(",", ":"), default=str)

    def _run_search(
        self,
        family: AlgorithmFamily,
        space: tuple[SearchParameter, ...],
        objective: Callable[[Mapping[str, object]], float],
        settings: Mapping[str, Any],
        seed: int,
    ):
        # Each optimiser receives the same finite search space and its own seeded sub-budget.
        if family is AlgorithmFamily.HYBRID:
            methods = tuple(settings["methods"])
            budget_each = int(settings["budget_per_method"])
            if (
                len(methods) < 2
                or len(set(methods)) != len(methods)
                or any(method not in {
                    "random_search", "grid_search", "differential_evolution", "bayesian"
                } for method in methods)
            ):
                raise ValueError("hybrid methods must be 2+ unique supported search methods")
            if budget_each < 4 or len(methods) * budget_each > 10000:
                raise ValueError("hybrid budget_per_method must be >=4 and total budget <=10000")

            # The same objective callback and strategy space are shared by every method.
            all_candidates: list[SearchCandidate] = []
            all_attempts: list[SearchCandidate] = []
            all_failures: list[str] = []
            offset = 0
            for method_index, method in enumerate(methods):
                method_seed = seed + 104729 * method_index
                if method == "random_search":
                    result = random_search(
                        space, objective, budget=budget_each, seed=method_seed
                    )
                elif method == "grid_search":
                    result = grid_search(
                        space,
                        objective,
                        points_per_numeric_dimension=int(settings["points_per_numeric_dimension"]),
                        max_evaluations=budget_each,
                        seed=method_seed,
                    )
                elif method == "differential_evolution":
                    population = int(settings["de_population_size"])
                    generations = int(settings["de_generations"])
                    if population * (generations + 1) != budget_each:
                        raise ValueError(
                            "hybrid DE budget_per_method must equal "
                            "de_population_size * (de_generations + 1)"
                        )
                    result = differential_evolution(
                        space,
                        objective,
                        population_size=population,
                        generations=generations,
                        mutation=float(settings["de_mutation"]),
                        crossover=float(settings["de_crossover"]),
                        seed=method_seed,
                    )
                else:
                    result = optuna_tpe_search(
                        space,
                        objective,
                        budget=budget_each,
                        startup_trials=int(settings["tpe_startup_trials"]),
                        seed=method_seed,
                    )

                # Rewrite method-local IDs before merging the different search traces.
                local_attempts = result.attempts or result.candidates
                local_id_map = {
                    item.candidate_id: f"{method}:{item.candidate_id}"
                    for item in local_attempts
                }
                local_failure_by_index: dict[int, str] = {}
                for failure in result.failures:
                    prefix = failure.split(":", 1)[0]
                    if "=" not in prefix:
                        continue
                    try:
                        local_failure_by_index[int(prefix.split("=", 1)[1])] = failure
                    except ValueError:
                        continue
                for attempt in local_attempts:
                    local_index = int(attempt.evaluation_index)
                    global_index = offset + local_index
                    lineage = dict(attempt.lineage)
                    raw_parents = lineage.get("parent_candidate_ids", [])
                    lineage["parent_candidate_ids"] = [
                        local_id_map.get(str(parent), str(parent))
                        for parent in raw_parents
                    ] if isinstance(raw_parents, list) else []
                    lineage.update({
                        "operator": f"hybrid_{method}_{lineage.get('operator', method)}",
                        "search_method": method,
                        "method_index": method_index,
                        "method_seed": method_seed,
                        "method_local_candidate_id": attempt.candidate_id,
                    })
                    if not np.isfinite(attempt.score):
                        failure_reason = (
                            str(lineage.get("failure_reason"))
                            or local_failure_by_index.get(local_index)
                            or "search method produced a non-finite candidate"
                        )
                        lineage["evaluation_failed"] = True
                        lineage["failure_reason"] = failure_reason[:500]
                        all_failures.append(f"candidate={global_index}: {method}: {failure_reason}")
                    candidate = SearchCandidate(
                        candidate_id=f"{method}:{attempt.candidate_id}",
                        parameters=dict(attempt.parameters),
                        score=float(attempt.score),
                        evaluation_index=global_index,
                        lineage=lineage,
                    )
                    all_attempts.append(candidate)
                    if np.isfinite(candidate.score):
                        all_candidates.append(candidate)
                offset += len(local_attempts)

            return SearchResult(
                method="hybrid_ensemble",
                seed=seed,
                candidates=tuple(all_candidates),
                failures=tuple(all_failures),
                attempts=tuple(all_attempts),
            )

        budget = int(settings["budget"])
        if budget < 4:
            raise ValueError("optimization budget must be at least four evaluations")
        if family is AlgorithmFamily.RANDOM_SEARCH:
            return random_search(space, objective, budget=budget, seed=seed)
        if family is AlgorithmFamily.GRID_SEARCH:
            points = int(settings["points_per_numeric_dimension"])
            return grid_search(
                space,
                objective,
                points_per_numeric_dimension=points,
                max_evaluations=budget,
                seed=seed,
            )
        if family is AlgorithmFamily.DIFFERENTIAL_EVOLUTION:
            population = int(settings["population_size"])
            generations = int(settings["generations"])
            expected = population * (generations + 1)
            if expected != budget:
                raise ValueError(
                    f"differential evolution budget must equal population_size "
                    f"* (generations + 1); expected {expected}, got {budget}"
                )
            return differential_evolution(
                space,
                objective,
                population_size=population,
                generations=generations,
                mutation=float(settings["mutation"]),
                crossover=float(settings["crossover"]),
                seed=seed,
            )
        if family is AlgorithmFamily.BAYESIAN:
            # This is an explicitly labelled Parzen-style heuristic, not canonical TPE.
            return optuna_tpe_search(
                space,
                objective,
                budget=budget,
                startup_trials=int(settings["startup_trials"]),
                seed=seed,
            )
        raise ValueError(f"unsupported existing-strategy optimisation family: {family.value}")

    def __call__(
        self,
        context: JobContext,
        experiment_record: dict[str, Any],
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        # Job arguments cannot override an immutable research specification.
        if parameters:
            raise ValueError("optimizer runner accepts no job-time overrides; update the experiment spec")
        context.check_cancelled()
        spec = experiment_spec_from_record(experiment_record)
        supported = {
            AlgorithmFamily.RANDOM_SEARCH,
            AlgorithmFamily.GRID_SEARCH,
            AlgorithmFamily.DIFFERENTIAL_EVOLUTION,
            AlgorithmFamily.BAYESIAN,
            AlgorithmFamily.HYBRID,
        }
        if spec.algorithm_family not in supported:
            raise ValueError("existing_strategy_optimization requires a supported search family")

        strategy_name = spec.parameters.get("strategy_name")
        if not isinstance(strategy_name, str) or not strategy_name.strip():
            raise ValueError("optimization experiment requires parameters.strategy_name")
        descriptor = self.registry.describe(strategy_name)
        strategy_parameters = spec.parameters.get("strategy_parameters", {})
        if not isinstance(strategy_parameters, dict):
            raise ValueError("strategy_parameters must be a JSON object")
        self.registry.validate_parameter_payload(strategy_name, strategy_parameters)

        settings_key = "hybrid_optimization" if spec.algorithm_family is AlgorithmFamily.HYBRID else "optimization"
        settings = spec.parameters.get(settings_key)
        required = (
            {"budget_per_method", "methods", "validation_candidates", "objective"}
            if spec.algorithm_family is AlgorithmFamily.HYBRID
            else {"budget", "validation_candidates", "objective"}
        )
        if not isinstance(settings, dict) or not required.issubset(settings):
            raise ValueError(f"parameters.{settings_key} must declare {sorted(required)}")
        objective_name = str(settings["objective"])
        if objective_name not in self.OBJECTIVES:
            raise ValueError(f"objective must be one of {sorted(self.OBJECTIVES)}")
        validation_count = int(settings["validation_candidates"])
        if not 1 <= validation_count <= 1000:
            raise ValueError("validation_candidates must be 1..1000")
        if spec.algorithm_family is AlgorithmFamily.HYBRID:
            methods = settings["methods"]
            if not isinstance(methods, list) or len(methods) < 2 or len(set(methods)) != len(methods):
                raise ValueError("hybrid_optimization.methods must be 2+ unique method IDs")
            budget_each = settings["budget_per_method"]
            if isinstance(budget_each, bool) or not isinstance(budget_each, int) or not 4 <= budget_each <= 10000:
                raise ValueError("hybrid_optimization.budget_per_method must be 4..10000")
            budget = budget_each * len(methods)
            if budget > 10000:
                raise ValueError("hybrid total search budget exceeds 10000 evaluations")
            if "grid_search" in methods and int(settings.get("points_per_numeric_dimension", 0)) < 2:
                raise ValueError("hybrid grid_search requires points_per_numeric_dimension >= 2")
            if "differential_evolution" in methods:
                population = int(settings.get("de_population_size", 0))
                generations = int(settings.get("de_generations", 0))
                if population < 4 or generations < 1 or population * (generations + 1) != budget_each:
                    raise ValueError("hybrid DE parameters must exactly match budget_per_method")
            if "bayesian" in methods:
                startup = int(settings.get("tpe_startup_trials", 0))
                if not 1 <= startup < budget_each:
                    raise ValueError("hybrid TPE startup trials must be less than budget_per_method")
        else:
            budget = int(settings["budget"])
            if not 4 <= budget <= 10000:
                raise ValueError("budget must be 4..10000")

        manifests = [
            context.store.get_dataset(dataset_id)["manifest"]
            for dataset_id in spec.dataset_ids
        ]
        bars = self.bar_loader(context.store, spec)
        config, periods_per_year = _build_portfolio_config(spec, manifests)
        space = self._search_parameters(descriptor)
        shipped_defaults = dict(descriptor.defaults)
        defaults = dict(shipped_defaults)
        defaults.update(strategy_parameters)

        context.log(
            f"optimising {strategy_name} with {spec.algorithm_family.value}; "
            f"budget={budget}, objective={objective_name}"
        )
        bars_digest = _bars_fingerprint(bars)
        train_metrics: dict[str, dict[str, float | int]] = {}
        train_return_vectors: dict[str, np.ndarray] = {}
        train_calls = 0

        def train_objective(candidate_values: Mapping[str, object]) -> float:
            # Each candidate is assessed only on TRAIN; no VALIDATION/OOS data is used here.
            nonlocal train_calls
            context.check_cancelled()
            train_calls += 1
            if train_calls % max(1, budget // 10) == 0:
                context.log(f"TRAIN candidate evaluations: {train_calls}")
            current = dict(defaults)
            current.update(candidate_values)
            key = self._config_key(current)
            partition = _partition_target_frame(
                spec,
                strategy_name,
                current,
                bars,
                config,
                partition_name="train",
                start=spec.training_start,
                end=spec.training_end,
                periods_per_year=periods_per_year,
            )
            train_metrics[key] = partition.metrics
            train_return_vectors[key] = (
                partition.result.equity_curve.pct_change().dropna().to_numpy(dtype=np.float64)
            )
            score = float(partition.metrics[objective_name])
            if not np.isfinite(score):
                raise ValueError("TRAIN objective is non-finite")
            return score

        search = self._run_search(
            spec.algorithm_family,
            space,
            train_objective,
            settings,
            spec.random_seed,
        )
        if not search.candidates:
            raise RuntimeError(
                f"all {spec.algorithm_family.value} candidates failed: {search.failures[:5]}"
            )

        # Compare both the shipped Config defaults and any caller-supplied starting config.
        shipped_score = train_objective(shipped_defaults)
        shipped_baseline = SearchCandidate(
            candidate_id="shipped-default",
            parameters=shipped_defaults,
            score=shipped_score,
            evaluation_index=-2,
            lineage={"operator": "shipped_default", "parent_candidate_ids": []},
        )
        user_baseline_score = train_objective({})
        user_baseline = SearchCandidate(
            candidate_id="user-configured-baseline",
            parameters=defaults,
            score=user_baseline_score,
            evaluation_index=-1,
            lineage={"operator": "user_configured_baseline", "parent_candidate_ids": []},
        )
        # Persist every attempted trial, including failures carried separately from valid winners.
        attempted_trials = search.attempts or search.candidates
        search_candidates = (shipped_baseline, user_baseline, *attempted_trials)

        # Prepare all attempted candidates before writing lineage so parent IDs can be resolved.
        candidate_rows: list[dict[str, Any]] = []
        candidate_id_map: dict[str, str] = {}
        failure_by_index: dict[int, str] = {}
        for failure in search.failures:
            # Random/grid/Optuna failure messages identify their attempted trial index.
            prefix = failure.split(":", 1)[0]
            for label in ("candidate=", "trial=", "evaluation="):
                if prefix.startswith(label):
                    try:
                        failure_by_index[int(prefix.removeprefix(label))] = failure
                    except ValueError:
                        pass
                    break

        for candidate in search_candidates:
            context.check_cancelled()
            candidate_config = dict(defaults)
            candidate_config.update(candidate.parameters)
            key = self._config_key(candidate_config)
            metrics = train_metrics.get(key)
            succeeded = metrics is not None and np.isfinite(candidate.score)
            digest_payload = {
                "experiment_fingerprint": spec.fingerprint,
                "bars_sha256": bars_digest,
                "strategy_name": strategy_name,
                "strategy_parameters": candidate_config,
                "search_family": spec.algorithm_family.value,
                "source_candidate_id": candidate.candidate_id,
                "evaluation_index": candidate.evaluation_index,
                "status": "succeeded" if succeeded else "failed",
            }
            candidate_digest = hashlib.sha256(
                json.dumps(
                    digest_payload,
                    sort_keys=True,
                    separators=(",", ":"),
                    default=str,
                ).encode("utf-8")
            ).hexdigest()
            candidate_id = f"{spec.experiment_id}-{candidate_digest[:16]}"
            candidate_id_map[candidate.candidate_id] = candidate_id
            candidate_rows.append({
                "source_candidate_id": candidate.candidate_id,
                "candidate_id": candidate_id,
                "candidate_digest": candidate_digest,
                "parameters": candidate_config,
                "train_score": float(candidate.score) if succeeded else None,
                "train_metrics": metrics or {},
                "status": "succeeded" if succeeded else "failed",
                "evaluation_index": candidate.evaluation_index,
                "lineage": dict(candidate.lineage),
                "failure_reason": failure_by_index.get(candidate.evaluation_index),
            })

        # Persist every attempted DE genome (including failed offspring) and every successful
        # random/grid/TPE evaluation. Parent candidate references are resolved to SQLite IDs.
        for candidate in candidate_rows:
            if context.store.has_candidate(spec.experiment_id, candidate["candidate_digest"]):
                continue
            lineage = dict(candidate["lineage"])
            raw_parents = lineage.get("parent_candidate_ids", [])
            mapped_parents = [
                candidate_id_map.get(str(parent), str(parent))
                for parent in raw_parents
            ] if isinstance(raw_parents, list) else []
            lineage.update({
                "origin": "existing_strategy_parameter_search",
                "parent_candidate_ids": mapped_parents,
                "source_candidate_id": candidate["source_candidate_id"],
                "selection": "train_objective",
            })
            if candidate["status"] == "succeeded":
                metric_payload = {
                    "status": "succeeded",
                    "train": candidate["train_metrics"],
                    "train_objective": candidate["train_score"],
                }
            else:
                metric_payload = {
                    "status": "failed",
                    "failure_reason": candidate["failure_reason"] or "candidate evaluation failed",
                }
            context.store.append_candidate(
                candidate_id=candidate["candidate_id"],
                experiment_id=spec.experiment_id,
                candidate_digest=candidate["candidate_digest"],
                family=spec.algorithm_family.value,
                generation=max(int(lineage.get("generation", 0)), 0),
                parameters={
                    "strategy_name": strategy_name,
                    "strategy_parameters": candidate["parameters"],
                    "search_family": spec.algorithm_family.value,
                },
                metrics=metric_payload,
                lineage=lineage,
            )

        successful_candidates = [
            candidate for candidate in candidate_rows
            if candidate["status"] == "succeeded"
        ]
        # Statistical diagnostics use only TRAIN returns and never affect validation ranking.
        statistical_rows = [
            candidate for candidate in successful_candidates
            if self._config_key(candidate["parameters"]) in train_return_vectors
        ]
        statistical_report: dict[str, Any]
        if len(statistical_rows) >= 1:
            return_map = {
                candidate["candidate_id"]: train_return_vectors[
                    self._config_key(candidate["parameters"])
                ]
                for candidate in statistical_rows
            }
            statistical_report = candidate_family_report_from_returns(
                [candidate["candidate_id"] for candidate in statistical_rows],
                return_map,
                periods_per_year=periods_per_year,
                pbo_blocks=8,
                pbo_candidate_limit=128,
            )
            # Keep the full candidate-level p-values in the job result; persist a compact event.
            context.store.append_event(
                spec.experiment_id,
                "training_candidate_family_diagnostics",
                {
                    "candidate_family_size": statistical_report["candidate_family_size"],
                    "fdr": {
                        "hypotheses": statistical_report["fdr"]["hypotheses"],
                        "rejections": statistical_report["fdr"].get("rejections", 0),
                        "alpha": statistical_report["fdr"]["alpha"],
                    },
                    "deflated_sharpe": statistical_report["deflated_sharpe"],
                    "pbo_cscv": statistical_report["pbo_cscv"],
                    "sampling_frequency": statistical_report["sampling_frequency"],
                    "selection_effect": "diagnostic_only_not_used_for_candidate_selection",
                },
            )
        else:
            statistical_report = {
                "classification": "not_computed",
                "reason": "no successful TRAIN candidate return vectors",
                "candidate_family_size": 0,
            }
        if not successful_candidates:
            raise RuntimeError("no valid baseline or search candidate completed TRAIN")
        # Keep failed attempts in the immutable search trace, but never send them to VALIDATION.
        successful_candidate_rows = [
            candidate for candidate in candidate_rows
            if candidate["status"] == "succeeded"
        ]
        if not successful_candidate_rows:
            raise RuntimeError("no candidate survived TRAIN evaluation")
        # Deduplicate identical parameter sets before validation to avoid wasting its budget.
        validation_pool: dict[str, dict[str, Any]] = {}
        for candidate in successful_candidate_rows:
            key = self._config_key(candidate["parameters"])
            current = validation_pool.get(key)
            if current is None or candidate["train_score"] > current["train_score"]:
                validation_pool[key] = candidate
        shortlist = sorted(
            validation_pool.values(),
            key=lambda item: (-float(item["train_score"]), item["candidate_digest"]),
        )[:min(validation_count, len(validation_pool))]
        validation_rows: list[dict[str, Any]] = []
        for index, candidate in enumerate(shortlist, start=1):
            context.check_cancelled()
            context.log(f"validation shortlist {index}/{len(shortlist)}")
            partition = _partition_target_frame(
                spec,
                strategy_name,
                candidate["parameters"],
                bars,
                config,
                partition_name="validation",
                start=spec.validation_start,
                end=spec.validation_end,
                periods_per_year=periods_per_year,
            )
            validation_score = float(partition.metrics[objective_name])
            validation_definition = {
                "experiment_fingerprint": spec.fingerprint,
                "train_candidate_digest": candidate["candidate_digest"],
                "strategy_name": strategy_name,
                "strategy_parameters": candidate["parameters"],
                "validation_metrics": partition.metrics,
                "validation_objective": validation_score,
                "bars_sha256": bars_digest,
            }
            validation_digest = hashlib.sha256(
                json.dumps(
                    validation_definition,
                    sort_keys=True,
                    separators=(",", ":"),
                    default=str,
                ).encode("utf-8")
            ).hexdigest()
            validation_candidate_id = f"{spec.experiment_id}-validation-{validation_digest[:16]}"
            validation_rows.append({
                "candidate_digest": validation_digest,
                "candidate_id": validation_candidate_id,
                "train_candidate_digest": candidate["candidate_digest"],
                "train_candidate_id": candidate["candidate_id"],
                "parameters": candidate["parameters"],
                "train_score": candidate["train_score"],
                "validation_score": validation_score,
                "validation_metrics": partition.metrics,
            })
            # The validation-selected candidate is a child of its TRAIN-ranked parent.
            if not context.store.has_candidate(spec.experiment_id, validation_digest):
                context.store.append_candidate(
                    candidate_id=validation_candidate_id,
                    experiment_id=spec.experiment_id,
                    candidate_digest=validation_digest,
                    family=f"{spec.algorithm_family.value}_validation",
                    generation=1,
                    parameters={
                        "strategy_name": strategy_name,
                        "strategy_parameters": candidate["parameters"],
                    },
                    metrics={
                        "train": candidate["train_metrics"],
                        "validation": partition.metrics,
                        "validation_objective": validation_score,
                    },
                    lineage={
                        "origin": "validation_shortlist",
                        "parent_candidate_ids": [candidate["candidate_id"]],
                        "mutation": None,
                        "crossover": None,
                        "selection": "validation_objective",
                        "train_candidate_digest": candidate["candidate_digest"],
                    },
                )

        if not validation_rows:
            raise RuntimeError("no candidate survived TRAIN/VALIDATION evaluation")
        selected = max(
            validation_rows,
            key=lambda item: (
                item["validation_score"],
                item["train_score"],
                item["candidate_digest"],
            ),
        )
        context.store.append_event(
            spec.experiment_id,
            "existing_strategy_optimization_selected",
            {
                "search_family": spec.algorithm_family.value,
                "budget": budget,
                "successful_train_candidates": sum(
                    candidate["status"] == "succeeded"
                    and candidate["evaluation_index"] >= 0
                    for candidate in candidate_rows
                ),
                "search_attempted_candidates": (len(search.attempts) if search.attempts else len(search.candidates) + len(search.failures)),
                "search_failures": list(search.failures),
                "validation_shortlist_count": len(validation_rows),
                "objective": objective_name,
                "selected_candidate_id": selected["candidate_id"],
                "selected_candidate_digest": selected["candidate_digest"],
                "train_parent_candidate_id": selected["train_candidate_id"],
                "train_parent_candidate_digest": selected["train_candidate_digest"],
                "train_score": selected["train_score"],
                "validation_score": selected["validation_score"],
                "bars_sha256": bars_digest,
                "final_holdout_accessed": False,
            },
        )
        context.check_cancelled()

        # Freeze the selected configuration and send it through the established OOS-only path.
        frozen_parameters = dict(spec.parameters)
        frozen_parameters["strategy_parameters"] = selected["parameters"]
        frozen_spec = replace(spec, parameters=frozen_parameters)
        context.log(
            f"selected {selected['candidate_id']} on VALIDATION; evaluating frozen OOS candidate"
        )
        final_evaluation = evaluate_existing_strategy(
            frozen_spec,
            bars,
            config,
            periods_per_year=periods_per_year,
            store=context.store,
            check_cancelled=context.check_cancelled,
            progress_callback=lambda stage, completed, total: context.log(
                f"frozen candidate {stage}: {completed}/{total}"
            ),
            candidate_family=f"{spec.algorithm_family.value}_selected_oos",
            lineage_metadata={
                "origin": "frozen_after_validation",
                "parent_candidate_ids": [selected["candidate_id"]],
                "selection": "validation_objective",
                "train_parent_candidate_id": selected["train_candidate_id"],
            },
        )
        return {
            "experiment_id": spec.experiment_id,
            "search_family": spec.algorithm_family.value,
            "search_method": search.method,
            "objective": objective_name,
            "budget": budget,
            "candidate_count": len(candidate_rows),
            "successful_train_candidates": sum(
                candidate["status"] == "succeeded"
                and candidate["evaluation_index"] >= 0
                for candidate in candidate_rows
            ),
            "search_attempted_candidates": (len(search.candidates) if search.method == "differential_evolution" else len(search.candidates) + len(search.failures)),
            "failed_candidates": len(search.failures),
            "total_train_evaluations": train_calls,
            "validation_shortlist": validation_rows,
            "selected_candidate": selected,
            "bars_sha256": bars_digest,
            "final_holdout_accessed": False,
            "final_evaluation": final_evaluation.to_dict(),
        }


def _node_to_payload(node: Node) -> dict[str, Any]:
    """Convert a closed GP AST to a canonical JSON-compatible tree."""
    # The tree grammar contains no executable source, imports or dynamic object references.
    return {
        "operation": node.operation,
        "feature_index": node.feature_index,
        "constant": node.constant,
        "children": [_node_to_payload(child) for child in node.children],
    }


def _prediction_digest(values: np.ndarray) -> str:
    # Hash exact float64 prediction bytes for reproducible TRAIN fitness caching.
    return hashlib.sha256(
        np.ascontiguousarray(values, dtype=np.float64).tobytes()
    ).hexdigest()


def _record_train_family_diagnostics(
    context: JobContext,
    spec: ExperimentSpec,
    report: dict[str, Any],
) -> None:
    """Persist a compact TRAIN-only statistical summary without changing candidate selection."""
    # Full candidate-level p-values remain in the job result; the event stores bounded summaries.
    fdr = report.get("fdr", {})
    context.store.append_event(
        spec.experiment_id,
        "training_candidate_family_diagnostics",
        {
            "algorithm_family": spec.algorithm_family.value,
            "candidate_family_size": report.get("candidate_family_size", 0),
            "fdr": {
                "hypotheses": fdr.get("hypotheses", 0),
                "rejections": fdr.get("rejections", 0),
                "alpha": fdr.get("alpha", 0.05),
            },
            "deflated_sharpe": report.get("deflated_sharpe"),
            "pbo_cscv": report.get("pbo_cscv"),
            "sampling_frequency": report.get("sampling_frequency"),
            "selection_effect": "diagnostic_only_not_used_for_candidate_selection",
        },
    )


class GeneticProgrammingJobRunner:
    """Evolve a numerical long/flat policy on TRAIN, select on VALIDATION and freeze OOS."""

    OBJECTIVES = frozenset({"sharpe", "sortino", "cagr", "calmar", "total_return"})

    def __init__(
        self,
        *,
        crypto_data_root: str | Path | None = None,
        bar_loader: Callable[[ExperimentStore, ExperimentSpec], dict[str, pd.DataFrame]] | None = None,
    ) -> None:
        # Reuse the approved-manifest, checksum-verification and OOS-clipped data path.
        self.crypto_data_root = crypto_data_root
        self.bar_loader = bar_loader or (
            lambda store, spec: load_registered_bars(
                store, spec, crypto_data_root=self.crypto_data_root
            )
        )

    def __call__(
        self,
        context: JobContext,
        experiment_record: dict[str, Any],
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        # All model settings are part of the immutable ExperimentSpec, not queue-time overrides.
        if parameters:
            raise ValueError("GP runner accepts no job-time overrides; update the experiment spec")
        context.check_cancelled()
        spec = experiment_spec_from_record(experiment_record)
        if spec.algorithm_family is not AlgorithmFamily.GENETIC_PROGRAMMING:
            raise ValueError("genetic_programming runner requires genetic_programming family")

        settings = spec.parameters.get("genetic_programming")
        required = {
            "population_size", "generations", "max_depth", "max_nodes",
            "mutation_rate", "validation_candidates", "objective", "feature_windows",
        }
        if not isinstance(settings, dict) or not required.issubset(settings):
            raise ValueError(
                f"parameters.genetic_programming requires {sorted(required)}"
            )
        integer_settings = (
            "population_size", "generations", "max_depth",
            "max_nodes", "validation_candidates",
        )
        for name in integer_settings:
            value = settings[name]
            minimum = 4 if name == "population_size" else 1 if name in {
                "generations", "max_depth", "validation_candidates"
            } else 3
            maximum = 12 if name == "max_depth" else 8191 if name == "max_nodes" else 10000
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or not minimum <= value <= maximum
            ):
                raise ValueError(
                    f"genetic_programming.{name} must be an integer from {minimum} to {maximum}"
                )
        mutation_rate = settings["mutation_rate"]
        if (
            isinstance(mutation_rate, bool)
            or not isinstance(mutation_rate, int | float)
            or not np.isfinite(mutation_rate)
            or not 0 <= mutation_rate <= 1
        ):
            raise ValueError("genetic_programming.mutation_rate must be between zero and one")
        objective_name = str(settings["objective"])
        if objective_name not in self.OBJECTIVES:
            raise ValueError(f"objective must be one of {sorted(self.OBJECTIVES)}")
        windows = settings["feature_windows"]
        if (
            not isinstance(windows, list)
            or not windows
            or any(isinstance(value, bool) or not isinstance(value, int) or value < 2 for value in windows)
        ):
            raise ValueError("feature_windows must be a non-empty array of integers >= 2")
        if len(set(windows)) != len(windows):
            raise ValueError("feature_windows must not contain duplicates")

        manifests = [
            context.store.get_dataset(dataset_id)["manifest"]
            for dataset_id in spec.dataset_ids
        ]
        bars = self.bar_loader(context.store, spec)
        config, periods_per_year = _build_portfolio_config(spec, manifests)
        feature_engine = PointInTimeFeatureEngine(windows=tuple(windows))
        train_panel = build_model_feature_panel(
            bars, feature_engine, spec.track,
            start=spec.training_start, end=spec.training_end,
        )
        context.log(
            f"GP TRAIN start: population={settings['population_size']}, "
            f"generations={settings['generations']}, samples={len(train_panel.features)}"
        )

        train_cache: dict[str, dict[str, float | int]] = {}
        train_return_cache: dict[str, np.ndarray] = {}

        def train_fitness(predictions: np.ndarray) -> float:
            # Every expression is measured only on the frozen TRAIN partition.
            context.check_cancelled()
            digest = _prediction_digest(predictions)
            if digest not in train_cache:
                result = evaluate_model_scores(
                    train_panel, predictions, config,
                    partition="train",
                    start=spec.training_start, end=spec.training_end,
                    periods_per_year=periods_per_year,
                )
                train_cache[digest] = result.metrics
                train_return_cache[digest] = (
                    result.result.equity_curve.pct_change().dropna().to_numpy(dtype=np.float64)
                )
            value = float(train_cache[digest][objective_name])
            if not np.isfinite(value):
                raise ValueError("GP TRAIN objective is non-finite")
            return value

        programmer = GeneticProgrammer(
            feature_count=train_panel.features.shape[1],
            population_size=settings["population_size"],
            generations=settings["generations"],
            max_depth=settings["max_depth"],
            max_nodes=settings["max_nodes"],
            mutation_rate=float(mutation_rate),
            seed=spec.random_seed,
        )
        trace = programmer.run(train_panel.features, train_fitness)
        context.log(
            f"GP TRAIN completed: {len(trace['candidate_archive'])} candidate evaluations"
        )
        bars_digest = _bars_fingerprint(bars)
        archive = list(trace["candidate_archive"])
        candidate_rows: list[dict[str, Any]] = []
        candidate_id_map: dict[str, str] = {}

        # Persist the complete generation trace so every parent ID resolves to a stored row.
        for item in archive:
            context.check_cancelled()
            tree = item["tree"]
            tree_payload = _node_to_payload(tree)
            predictions = tree.evaluate(train_panel.features)
            prediction_key = _prediction_digest(predictions)
            metrics = train_cache.get(prediction_key)
            succeeded = item["status"] == "succeeded" and metrics is not None
            digest_payload = {
                "experiment_fingerprint": spec.fingerprint,
                "bars_sha256": bars_digest,
                "tree": tree_payload,
                "candidate_id": item["candidate_id"],
                "generation": item["generation"],
                "seed": spec.random_seed,
                "feature_windows": windows,
            }
            candidate_digest = hashlib.sha256(
                json.dumps(
                    digest_payload, sort_keys=True, separators=(",", ":"), allow_nan=False
                ).encode("utf-8")
            ).hexdigest()
            candidate_id = f"{spec.experiment_id}-{candidate_digest[:16]}"
            candidate_id_map[str(item["candidate_id"])] = candidate_id
            candidate_rows.append({
                "source_candidate_id": item["candidate_id"],
                "candidate_id": candidate_id,
                "candidate_digest": candidate_digest,
                "tree": tree,
                "tree_payload": tree_payload,
                "generation": int(item["generation"]),
                "index": int(item["index"]),
                "train_score": float(item["fitness"]) if succeeded else None,
                "train_metrics": metrics or {},
                "prediction_key": prediction_key,
                "status": "succeeded" if succeeded else "failed",
                "failure_reason": item.get("failure_reason"),
                "lineage": dict(item["lineage"]),
            })

        for candidate in candidate_rows:
            if context.store.has_candidate(spec.experiment_id, candidate["candidate_digest"]):
                continue
            lineage = dict(candidate["lineage"])
            raw_parents = lineage.get("parent_candidate_ids", [])
            lineage["parent_candidate_ids"] = [
                candidate_id_map.get(str(parent), str(parent))
                for parent in raw_parents
            ] if isinstance(raw_parents, list) else []
            lineage.update({
                "origin": "bounded_numerical_genetic_programming",
                "source_candidate_id": candidate["source_candidate_id"],
                "feature_windows": windows,
                "selection": "train_objective",
            })
            if candidate["status"] == "succeeded":
                metric_payload = {
                    "status": "succeeded",
                    "train": candidate["train_metrics"],
                    "train_fitness": candidate["train_score"],
                }
            else:
                metric_payload = {
                    "status": "failed",
                    "failure_reason": candidate["failure_reason"] or "GP candidate evaluation failed",
                }
            context.store.append_candidate(
                candidate_id=candidate["candidate_id"],
                experiment_id=spec.experiment_id,
                candidate_digest=candidate["candidate_digest"],
                family=AlgorithmFamily.GENETIC_PROGRAMMING.value,
                generation=candidate["generation"],
                parameters={
                    "expression": candidate["tree_payload"],
                    "feature_windows": windows,
                },
                metrics=metric_payload,
                lineage=lineage,
            )

        successful = [item for item in candidate_rows if item["status"] == "succeeded"]
        statistical_candidates = [
            item for item in successful if item["prediction_key"] in train_return_cache
        ]
        if statistical_candidates:
            statistical_report = candidate_family_report_from_returns(
                [item["candidate_id"] for item in statistical_candidates],
                {
                    item["candidate_id"]: train_return_cache[item["prediction_key"]]
                    for item in statistical_candidates
                },
                periods_per_year=periods_per_year,
                pbo_blocks=8,
                pbo_candidate_limit=128,
            )
            _record_train_family_diagnostics(context, spec, statistical_report)
        else:
            statistical_report = {
                "classification": "not_computed",
                "reason": "no successful GP candidate return vectors",
                "candidate_family_size": 0,
            }
        if not successful:
            raise RuntimeError("GP produced no valid TRAIN candidate")
        final_ids = set(str(value) for value in trace["population_ids"])
        final_population = [
            item for item in successful if item["source_candidate_id"] in final_ids
        ]
        shortlist = sorted(
            final_population,
            key=lambda item: (-float(item["train_score"]), item["candidate_digest"]),
        )[:min(settings["validation_candidates"], len(final_population))]
        if not shortlist:
            raise RuntimeError("GP final population has no valid candidate for VALIDATION")

        # VALIDATION is used once to select from the final TRAIN-evolved population.
        validation_panel = build_model_feature_panel(
            bars, feature_engine, spec.track,
            start=spec.validation_start, end=spec.validation_end,
        )
        validation_rows: list[dict[str, Any]] = []
        for index, candidate in enumerate(shortlist, start=1):
            context.check_cancelled()
            context.log(f"GP VALIDATION candidate {index}/{len(shortlist)}")
            predictions = candidate["tree"].evaluate(validation_panel.features)
            result = evaluate_model_scores(
                validation_panel, predictions, config,
                partition="validation",
                start=spec.validation_start, end=spec.validation_end,
                periods_per_year=periods_per_year,
            )
            validation_score = float(result.metrics[objective_name])
            validation_definition = {
                "experiment_fingerprint": spec.fingerprint,
                "train_candidate_digest": candidate["candidate_digest"],
                "expression": candidate["tree_payload"],
                "validation_metrics": result.metrics,
                "validation_objective": validation_score,
                "bars_sha256": bars_digest,
            }
            validation_digest = hashlib.sha256(
                json.dumps(
                    validation_definition, sort_keys=True, separators=(",", ":"), allow_nan=False
                ).encode("utf-8")
            ).hexdigest()
            validation_candidate_id = f"{spec.experiment_id}-gp-validation-{validation_digest[:16]}"
            validation_row = {
                "candidate_id": candidate["candidate_id"],
                "candidate_digest": candidate["candidate_digest"],
                "validation_candidate_id": validation_candidate_id,
                "validation_candidate_digest": validation_digest,
                "expression": candidate["tree_payload"],
                "train_fitness": candidate["train_score"],
                "validation_score": validation_score,
                "validation_metrics": result.metrics,
            }
            validation_rows.append(validation_row)
            # Persist an explicit validation child whose parent is the TRAIN expression.
            if not context.store.has_candidate(spec.experiment_id, validation_digest):
                context.store.append_candidate(
                    candidate_id=validation_candidate_id,
                    experiment_id=spec.experiment_id,
                    candidate_digest=validation_digest,
                    family="genetic_programming_validation",
                    generation=settings["generations"] + 1,
                    parameters={
                        "expression": candidate["tree_payload"],
                        "feature_windows": windows,
                    },
                    metrics={
                        "train_fitness": candidate["train_score"],
                        "validation": result.metrics,
                        "validation_objective": validation_score,
                    },
                    lineage={
                        "origin": "genetic_programming_validation",
                        "parent_candidate_ids": [candidate["candidate_id"]],
                        "selection": "validation_objective",
                        "feature_windows": windows,
                    },
                )
        selected = max(
            validation_rows,
            key=lambda item: (
                item["validation_score"], item["train_fitness"], item["candidate_digest"]
            ),
        )
        context.store.append_event(
            spec.experiment_id,
            "genetic_programming_candidate_frozen",
            {
                "selected_candidate_id": selected["candidate_id"],
                "selected_candidate_digest": selected["candidate_digest"],
                "selected_validation_candidate_id": selected["validation_candidate_id"],
                "selected_validation_candidate_digest": selected["validation_candidate_digest"],
                "objective": objective_name,
                "feature_windows": windows,
                "population_size": settings["population_size"],
                "generations": settings["generations"],
                "candidate_count": len(candidate_rows),
                "successful_train_candidates": len(successful),
                "validation_shortlist_count": len(validation_rows),
                "bars_sha256": bars_digest,
                "final_holdout_accessed": False,
            },
        )
        context.check_cancelled()

        # OOS is evaluated once after selection; no final-holdout frame is created.
        selected_tree = next(
            item["tree"] for item in shortlist
            if item["candidate_id"] == selected["candidate_id"]
        )
        oos_panel = build_model_feature_panel(
            bars, feature_engine, spec.track,
            start=spec.oos_start, end=spec.oos_end,
        )
        oos_predictions = selected_tree.evaluate(oos_panel.features)
        oos_result = evaluate_model_scores(
            oos_panel, oos_predictions, config,
            partition="out_of_sample",
            start=spec.oos_start, end=spec.oos_end,
            periods_per_year=periods_per_year,
        )
        oos_definition = {
            "experiment_fingerprint": spec.fingerprint,
            "validation_candidate_digest": selected["validation_candidate_digest"],
            "expression": selected["expression"],
            "oos_metrics": oos_result.metrics,
            "bars_sha256": bars_digest,
        }
        oos_digest = hashlib.sha256(
            json.dumps(
                oos_definition, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode("utf-8")
        ).hexdigest()
        oos_candidate_id = f"{spec.experiment_id}-gp-oos-{oos_digest[:16]}"
        if not context.store.has_candidate(spec.experiment_id, oos_digest):
            context.store.append_candidate(
                candidate_id=oos_candidate_id,
                experiment_id=spec.experiment_id,
                candidate_digest=oos_digest,
                family="genetic_programming_selected_oos",
                generation=settings["generations"] + 2,
                parameters={
                    "expression": selected["expression"],
                    "feature_windows": windows,
                },
                metrics={
                    "train_fitness": selected["train_fitness"],
                    "validation": selected["validation_metrics"],
                    "out_of_sample": oos_result.metrics,
                },
                lineage={
                    "origin": "genetic_programming_frozen_oos",
                    "parent_candidate_ids": [selected["validation_candidate_id"]],
                    "selection": "validation_objective",
                    "final_holdout_accessed": False,
                },
            )
        context.store.append_event(
            spec.experiment_id,
            "genetic_programming_oos_recorded",
            {
                "selected_candidate_id": selected["candidate_id"],
                "selected_candidate_digest": selected["candidate_digest"],
                "selected_validation_candidate_id": selected["validation_candidate_id"],
                "oos_candidate_id": oos_candidate_id,
                "oos_candidate_digest": oos_digest,
                "oos_metrics": oos_result.metrics,
                "final_holdout_accessed": False,
            },
        )
        return {
            "experiment_id": spec.experiment_id,
            "algorithm_family": AlgorithmFamily.GENETIC_PROGRAMMING.value,
            "objective": objective_name,
            "feature_windows": windows,
            "population_size": settings["population_size"],
            "generations": settings["generations"],
            "candidate_count": len(candidate_rows),
            "successful_train_candidates": len(successful),
            "failed_candidates": len(candidate_rows) - len(successful),
            "validation_shortlist": validation_rows,
            "selected_candidate": selected,
            "training_candidate_family_diagnostics": statistical_report,
            "out_of_sample_candidate_id": oos_candidate_id,
            "out_of_sample": {
                "metrics": oos_result.metrics,
                "portfolio": oos_result.result.to_dict(),
                "sample_count": oos_result.sample_count,
            },
            "bars_sha256": bars_digest,
            "final_holdout_accessed": False,
        }


class NeuroevolutionJobRunner:
    """Evolve a bounded dense policy on TRAIN, select on VALIDATION and freeze OOS."""

    OBJECTIVES = frozenset({"sharpe", "sortino", "cagr", "calmar", "total_return"})

    def __init__(
        self,
        *,
        crypto_data_root: str | Path | None = None,
        bar_loader: Callable[[ExperimentStore, ExperimentSpec], dict[str, pd.DataFrame]] | None = None,
    ) -> None:
        # Reuse approved manifests and checksum-verified, OOS-clipped local bars.
        self.crypto_data_root = crypto_data_root
        self.bar_loader = bar_loader or (
            lambda store, spec: load_registered_bars(
                store, spec, crypto_data_root=self.crypto_data_root
            )
        )

    def __call__(
        self,
        context: JobContext,
        experiment_record: dict[str, Any],
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        # All evolutionary hyperparameters are frozen into the experiment spec.
        if parameters:
            raise ValueError("neuroevolution runner accepts no job-time overrides")
        context.check_cancelled()
        spec = experiment_spec_from_record(experiment_record)
        if spec.algorithm_family is not AlgorithmFamily.NEUROEVOLUTION:
            raise ValueError("neuroevolution runner requires neuroevolution family")

        settings = spec.parameters.get("neuroevolution")
        required = {
            "hidden_size", "population_size", "generations", "learning_rate",
            "noise_std", "weight_limit", "validation_candidates", "objective",
            "feature_windows",
        }
        if not isinstance(settings, dict) or not required.issubset(settings):
            raise ValueError(f"parameters.neuroevolution requires {sorted(required)}")
        for name in ("hidden_size", "population_size", "generations", "validation_candidates"):
            value = settings[name]
            minimum = 4 if name == "population_size" else 1
            if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
                raise ValueError(f"neuroevolution.{name} must be an integer >= {minimum}")
        if settings["population_size"] % 2:
            raise ValueError("neuroevolution.population_size must be even")
        evaluation_count = settings["population_size"] * settings["generations"]
        if evaluation_count > 10000:
            raise ValueError("neuroevolution candidate count exceeds the 10000 evaluation limit")
        if settings["hidden_size"] > 512:
            raise ValueError("neuroevolution.hidden_size exceeds the 512-unit worker limit")
        for name in ("learning_rate", "noise_std", "weight_limit"):
            value = settings[name]
            if (
                isinstance(value, bool)
                or not isinstance(value, int | float)
                or not np.isfinite(value)
                or value <= 0
            ):
                raise ValueError(f"neuroevolution.{name} must be finite and positive")
        objective_name = str(settings["objective"])
        if objective_name not in self.OBJECTIVES:
            raise ValueError(f"objective must be one of {sorted(self.OBJECTIVES)}")
        windows = settings["feature_windows"]
        if (
            not isinstance(windows, list)
            or not windows
            or any(isinstance(value, bool) or not isinstance(value, int) or value < 2 for value in windows)
            or len(set(windows)) != len(windows)
        ):
            raise ValueError("feature_windows must be unique integers >= 2")
        inference_batch_size = settings.get("inference_batch_size", 8)
        if (
            isinstance(inference_batch_size, bool)
            or not isinstance(inference_batch_size, int)
            or not 1 <= inference_batch_size <= 256
        ):
            raise ValueError("neuroevolution.inference_batch_size must be in 1..256")

        manifests = [
            context.store.get_dataset(dataset_id)["manifest"]
            for dataset_id in spec.dataset_ids
        ]
        bars = self.bar_loader(context.store, spec)
        config, periods_per_year = _build_portfolio_config(spec, manifests)
        feature_engine = PointInTimeFeatureEngine(windows=tuple(windows))
        train_panel = build_model_feature_panel(
            bars, feature_engine, spec.track,
            start=spec.training_start, end=spec.training_end,
        )
        network = DenseMLP(
            input_size=train_panel.features.shape[1],
            hidden_size=settings["hidden_size"],
            output_size=1,
        )
        context.log(
            f"neuroevolution TRAIN start: population={settings['population_size']}, "
            f"generations={settings['generations']}, parameters={network.parameter_count}"
        )
        train_cache: dict[str, dict[str, float | int]] = {}
        train_return_cache: dict[str, np.ndarray] = {}

        def train_fitness(predictions: np.ndarray) -> float:
            # Fitness sees TRAIN feature rows only and routes through the shared cash simulator.
            context.check_cancelled()
            digest = _prediction_digest(predictions)
            if digest not in train_cache:
                result = evaluate_model_scores(
                    train_panel, predictions, config,
                    partition="train",
                    start=spec.training_start, end=spec.training_end,
                    periods_per_year=periods_per_year,
                )
                train_cache[digest] = result.metrics
                train_return_cache[digest] = (
                    result.result.equity_curve.pct_change().dropna().to_numpy(dtype=np.float64)
                )
            score = float(train_cache[digest][objective_name])
            if not np.isfinite(score):
                raise ValueError("neuroevolution TRAIN objective is non-finite")
            return score

        # Select the requested backend once and report the actual device/fallback status.
        requested_backend = spec.compute_backend.lower()
        backend_aliases = {"numpy": "cpu", "cpu": "cpu", "auto": "auto", "cupy": "cupy"}
        if requested_backend not in backend_aliases:
            raise ValueError("compute_backend must be auto, numpy, cpu or cupy")
        compute_engine = ComputeEngine(backend=backend_aliases[requested_backend])

        def batch_predictor(
            matrix: np.ndarray, parameter_batch: np.ndarray
        ) -> np.ndarray:
            # A population chunk is transferred once and evaluated by the selected backend.
            return compute_engine.batch_dense_mlp_scores(
                matrix,
                parameter_batch,
                hidden_size=network.hidden_size,
                output_size=network.output_size,
            )

        compute_snapshot = compute_engine.info()
        context.log(
            f"neuroevolution inference backend: {compute_snapshot.backend}; "
            f"device={compute_snapshot.device_name or 'CPU'}; "
            f"fallback={compute_snapshot.fallback_reason or 'none'}"
        )
        evolution = EvolutionStrategy(
            network,
            population_size=settings["population_size"],
            generations=settings["generations"],
            learning_rate=float(settings["learning_rate"]),
            noise_std=float(settings["noise_std"]),
            seed=spec.random_seed,
            weight_limit=float(settings["weight_limit"]),
        )
        trace = evolution.run(
            train_panel.features,
            train_fitness,
            batch_predictor=batch_predictor,
            batch_size=inference_batch_size,
        )
        compute_snapshot = compute_engine.info()
        compute_payload = {
            "backend": compute_snapshot.backend,
            "device_name": compute_snapshot.device_name,
            "total_memory_bytes": compute_snapshot.total_memory_bytes,
            "fallback_reason": compute_snapshot.fallback_reason,
            "requested_backend": requested_backend,
            "inference_batch_size": inference_batch_size,
        }
        bars_digest = _bars_fingerprint(bars)
        candidate_rows: list[dict[str, Any]] = []
        candidate_id_map: dict[str, str] = {}
        archive = list(trace.candidate_archive)

        # Store every mirrored-noise candidate; the archive retains parent references.
        for item in archive:
            context.check_cancelled()
            theta = np.asarray(item["parameters"], dtype=np.float64)
            weights = theta.tolist()
            predictions = network.predict(train_panel.features, theta)
            metrics = train_cache.get(_prediction_digest(predictions))
            succeeded = item["status"] == "succeeded" and metrics is not None
            digest_payload = {
                "experiment_fingerprint": spec.fingerprint,
                "bars_sha256": bars_digest,
                "network": {
                    "input_size": network.input_size,
                    "hidden_size": network.hidden_size,
                    "output_size": network.output_size,
                },
                "weights": weights,
                "candidate_id": item["candidate_id"],
                "generation": item["generation"],
                "seed": spec.random_seed,
                "feature_windows": windows,
            }
            candidate_digest = hashlib.sha256(
                json.dumps(
                    digest_payload, sort_keys=True, separators=(",", ":"), allow_nan=False
                ).encode("utf-8")
            ).hexdigest()
            candidate_id = f"{spec.experiment_id}-{candidate_digest[:16]}"
            candidate_id_map[str(item["candidate_id"])] = candidate_id
            candidate_rows.append({
                "source_candidate_id": item["candidate_id"],
                "candidate_id": candidate_id,
                "candidate_digest": candidate_digest,
                "weights": weights,
                "generation": int(item["generation"]),
                "index": int(item["index"]),
                "train_score": float(item["fitness"]) if succeeded else None,
                "train_metrics": metrics or {},
                "prediction_key": _prediction_digest(predictions),
                "status": "succeeded" if succeeded else "failed",
                "failure_reason": item.get("failure_reason"),
                "lineage": dict(item["lineage"]),
            })

        statistical_candidates = [
            item for item in candidate_rows
            if item["status"] == "succeeded"
            and item["prediction_key"] in train_return_cache
        ]
        if statistical_candidates:
            statistical_report = candidate_family_report_from_returns(
                [item["candidate_id"] for item in statistical_candidates],
                {
                    item["candidate_id"]: train_return_cache[item["prediction_key"]]
                    for item in statistical_candidates
                },
                periods_per_year=periods_per_year,
                pbo_blocks=8,
                pbo_candidate_limit=128,
            )
            _record_train_family_diagnostics(context, spec, statistical_report)
        else:
            statistical_report = {
                "classification": "not_computed",
                "reason": "no successful neuroevolution candidate return vectors",
                "candidate_family_size": 0,
            }

        for candidate in candidate_rows:
            if context.store.has_candidate(spec.experiment_id, candidate["candidate_digest"]):
                continue
            lineage = dict(candidate["lineage"])
            raw_parents = lineage.get("parent_candidate_ids", [])
            lineage["parent_candidate_ids"] = [
                candidate_id_map.get(str(parent), str(parent))
                for parent in raw_parents
            ] if isinstance(raw_parents, list) else []
            lineage.update({
                "origin": "mirrored_noise_neuroevolution",
                "source_candidate_id": candidate["source_candidate_id"],
                "feature_windows": windows,
                "selection": "train_objective",
            })
            if candidate["status"] == "succeeded":
                metric_payload = {
                    "status": "succeeded",
                    "train": candidate["train_metrics"],
                    "train_fitness": candidate["train_score"],
                }
            else:
                metric_payload = {
                    "status": "failed",
                    "failure_reason": candidate["failure_reason"] or "neuroevolution candidate failed",
                }
            context.store.append_candidate(
                candidate_id=candidate["candidate_id"],
                experiment_id=spec.experiment_id,
                candidate_digest=candidate["candidate_digest"],
                family=AlgorithmFamily.NEUROEVOLUTION.value,
                generation=candidate["generation"],
                parameters={
                    "network": {
                        "input_size": network.input_size,
                        "hidden_size": network.hidden_size,
                        "output_size": network.output_size,
                    },
                    "weights": candidate["weights"],
                    "feature_windows": windows,
                },
                metrics=metric_payload,
                lineage=lineage,
            )

        successful = [item for item in candidate_rows if item["status"] == "succeeded"]
        if not successful:
            raise RuntimeError("neuroevolution produced no valid TRAIN candidate")
        final_generation = settings["generations"] - 1
        final_population = [
            item for item in successful if item["generation"] == final_generation
        ]
        shortlist = sorted(
            final_population,
            key=lambda item: (-float(item["train_score"]), item["candidate_digest"]),
        )[:min(settings["validation_candidates"], len(final_population))]
        if not shortlist:
            raise RuntimeError("neuroevolution final population has no valid VALIDATION candidate")

        validation_panel = build_model_feature_panel(
            bars, feature_engine, spec.track,
            start=spec.validation_start, end=spec.validation_end,
        )
        validation_rows: list[dict[str, Any]] = []
        for index, candidate in enumerate(shortlist, start=1):
            context.check_cancelled()
            context.log(f"neuroevolution VALIDATION candidate {index}/{len(shortlist)}")
            predictions = network.predict(
                validation_panel.features,
                np.asarray(candidate["weights"], dtype=np.float64),
            )
            result = evaluate_model_scores(
                validation_panel, predictions, config,
                partition="validation",
                start=spec.validation_start, end=spec.validation_end,
                periods_per_year=periods_per_year,
            )
            # Persist validation as a child record; the train genome remains immutable.
            validation_definition = {
                "experiment_fingerprint": spec.fingerprint,
                "train_candidate_digest": candidate["candidate_digest"],
                "network": {
                    "input_size": network.input_size,
                    "hidden_size": network.hidden_size,
                    "output_size": network.output_size,
                },
                "weights": candidate["weights"],
                "validation_metrics": result.metrics,
                "bars_sha256": bars_digest,
                "objective": objective_name,
            }
            validation_digest = hashlib.sha256(
                json.dumps(
                    validation_definition, sort_keys=True, separators=(",", ":"), allow_nan=False
                ).encode("utf-8")
            ).hexdigest()
            validation_candidate_id = (
                f"{spec.experiment_id}-validation-{validation_digest[:16]}"
            )
            validation_score = float(result.metrics[objective_name])
            validation_rows.append({
                "candidate_id": candidate["candidate_id"],
                "candidate_digest": candidate["candidate_digest"],
                "validation_candidate_id": validation_candidate_id,
                "validation_candidate_digest": validation_digest,
                "weights": candidate["weights"],
                "train_fitness": candidate["train_score"],
                "validation_score": validation_score,
                "validation_metrics": result.metrics,
            })
            if not context.store.has_candidate(spec.experiment_id, validation_digest):
                context.store.append_candidate(
                    candidate_id=validation_candidate_id,
                    experiment_id=spec.experiment_id,
                    candidate_digest=validation_digest,
                    family="neuroevolution_validation",
                    generation=settings["generations"],
                    parameters={
                        "network": {
                            "input_size": network.input_size,
                            "hidden_size": network.hidden_size,
                            "output_size": network.output_size,
                        },
                        "weights": candidate["weights"],
                        "feature_windows": windows,
                    },
                    metrics={
                        "train_fitness": candidate["train_score"],
                        "train": candidate["train_metrics"],
                        "validation_objective": validation_score,
                        "validation": result.metrics,
                    },
                    lineage={
                        "origin": "neuroevolution_validation_shortlist",
                        "parent_candidate_ids": [candidate["candidate_id"]],
                        "selection": "validation_objective",
                        "train_candidate_digest": candidate["candidate_digest"],
                        "objective": objective_name,
                        "final_holdout_accessed": False,
                    },
                )
        selected = max(
            validation_rows,
            key=lambda item: (
                item["validation_score"], item["train_fitness"], item["candidate_digest"]
            ),
        )
        context.store.append_event(
            spec.experiment_id,
            "neuroevolution_candidate_frozen",
            {
                "selected_candidate_id": selected["candidate_id"],
                "selected_candidate_digest": selected["candidate_digest"],
                "selected_validation_candidate_id": selected["validation_candidate_id"],
                "selected_validation_candidate_digest": selected["validation_candidate_digest"],
                "objective": objective_name,
                "feature_windows": windows,
                "hidden_size": settings["hidden_size"],
                "population_size": settings["population_size"],
                "generations": settings["generations"],
                "candidate_count": len(candidate_rows),
                "successful_train_candidates": len(successful),
                "validation_shortlist_count": len(validation_rows),
                "bars_sha256": bars_digest,
                "compute": compute_payload,
                "final_holdout_accessed": False,
            },
        )
        context.check_cancelled()

        # The selected frozen weight vector is evaluated once on OOS; no final holdout is loaded.
        oos_panel = build_model_feature_panel(
            bars, feature_engine, spec.track,
            start=spec.oos_start, end=spec.oos_end,
        )
        oos_predictions = network.predict(
            oos_panel.features,
            np.asarray(selected["weights"], dtype=np.float64),
        )
        oos_result = evaluate_model_scores(
            oos_panel, oos_predictions, config,
            partition="out_of_sample",
            start=spec.oos_start, end=spec.oos_end,
            periods_per_year=periods_per_year,
        )
        # OOS is a child of the validation-selected candidate, never a new selection input.
        oos_definition = {
            "experiment_fingerprint": spec.fingerprint,
            "validation_candidate_digest": selected["validation_candidate_digest"],
            "weights": selected["weights"],
            "oos_metrics": oos_result.metrics,
            "portfolio": oos_result.result.to_dict(),
            "bars_sha256": bars_digest,
        }
        oos_digest = hashlib.sha256(
            json.dumps(
                oos_definition, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode("utf-8")
        ).hexdigest()
        oos_candidate_id = f"{spec.experiment_id}-oos-{oos_digest[:16]}"
        if not context.store.has_candidate(spec.experiment_id, oos_digest):
            context.store.append_candidate(
                candidate_id=oos_candidate_id,
                experiment_id=spec.experiment_id,
                candidate_digest=oos_digest,
                family="neuroevolution_selected_oos",
                generation=settings["generations"] + 1,
                parameters={
                    "network": {
                        "input_size": network.input_size,
                        "hidden_size": network.hidden_size,
                        "output_size": network.output_size,
                    },
                    "weights": selected["weights"],
                    "feature_windows": windows,
                },
                metrics={
                    "train_fitness": selected["train_fitness"],
                    "validation": selected["validation_metrics"],
                    "out_of_sample": oos_result.metrics,
                    "portfolio": oos_result.result.to_dict(),
                },
                lineage={
                    "origin": "neuroevolution_frozen_oos",
                    "parent_candidate_ids": [selected["validation_candidate_id"]],
                    "train_parent_candidate_id": selected["candidate_id"],
                    "selection": "validation_objective",
                    "objective": objective_name,
                    "final_holdout_accessed": False,
                },
            )
        context.store.append_event(
            spec.experiment_id,
            "neuroevolution_oos_recorded",
            {
                "selected_candidate_id": selected["candidate_id"],
                "selected_candidate_digest": selected["candidate_digest"],
                "selected_validation_candidate_id": selected["validation_candidate_id"],
                "oos_candidate_id": oos_candidate_id,
                "oos_candidate_digest": oos_digest,
                "oos_metrics": oos_result.metrics,
                "final_holdout_accessed": False,
            },
        )
        return {
            "experiment_id": spec.experiment_id,
            "algorithm_family": AlgorithmFamily.NEUROEVOLUTION.value,
            "objective": objective_name,
            "feature_windows": windows,
            "network": {
                "input_size": network.input_size,
                "hidden_size": network.hidden_size,
                "output_size": network.output_size,
                "parameter_count": network.parameter_count,
            },
            "population_size": settings["population_size"],
            "generations": settings["generations"],
            "candidate_count": len(candidate_rows),
            "successful_train_candidates": len(successful),
            "failed_candidates": len(candidate_rows) - len(successful),
            "validation_shortlist": validation_rows,
            "selected_candidate": selected,
            "training_candidate_family_diagnostics": statistical_report,
            "out_of_sample_candidate_id": oos_candidate_id,
            "out_of_sample": {
                "metrics": oos_result.metrics,
                "portfolio": oos_result.result.to_dict(),
                "sample_count": oos_result.sample_count,
            },
            "bars_sha256": bars_digest,
            "compute": compute_payload,
            "final_holdout_accessed": False,
        }


def _composition_to_payload(composition: Composition) -> list[dict[str, Any]]:
    """Serialize one declarative composition genome with deterministic ordering."""
    # Components contain IDs, roles and finite numeric parameters, never callable code.
    return [
        {
            "component_id": item.component_id,
            "role": item.role,
            "parameters": dict(item.parameters),
        }
        for item in composition.components
    ]


class StrategyCompositionJobRunner:
    """Evolve allow-listed component compositions using TRAIN/VALIDATION/OOS partitions."""

    OBJECTIVES = frozenset({"sharpe", "sortino", "cagr", "calmar", "total_return"})

    def __init__(
        self,
        *,
        crypto_data_root: str | Path | None = None,
        bar_loader: Callable[[ExperimentStore, ExperimentSpec], dict[str, pd.DataFrame]] | None = None,
    ) -> None:
        # All data comes through the same licence-approved, OOS-clipped local adapter.
        self.crypto_data_root = crypto_data_root
        self.bar_loader = bar_loader or (
            lambda store, spec: load_registered_bars(
                store, spec, crypto_data_root=self.crypto_data_root
            )
        )

    def __call__(
        self,
        context: JobContext,
        experiment_record: dict[str, Any],
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        # Composition settings are immutable experiment inputs, not queue-time overrides.
        if parameters:
            raise ValueError("composition runner accepts no job-time overrides")
        context.check_cancelled()
        spec = experiment_spec_from_record(experiment_record)
        if spec.algorithm_family is not AlgorithmFamily.STRATEGY_COMPOSITION:
            raise ValueError("strategy_composition runner requires strategy_composition family")
        settings = spec.parameters.get("strategy_composition")
        required = {
            "population_size", "generations", "max_components", "mutation_rate",
            "validation_candidates", "objective", "feature_windows",
        }
        if not isinstance(settings, dict) or not required.issubset(settings):
            raise ValueError(f"strategy_composition requires settings {sorted(required)}")
        for name in ("population_size", "generations", "max_components", "validation_candidates"):
            value = settings[name]
            minimum = 4 if name == "population_size" else 2 if name == "max_components" else 1
            maximum = 32 if name == "max_components" else 10000
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or not minimum <= value <= maximum
            ):
                raise ValueError(
                    f"strategy_composition.{name} must be an integer from {minimum} to {maximum}"
                )
        if settings["population_size"] * (settings["generations"] + 1) > 10000:
            raise ValueError("strategy_composition candidate count exceeds the 10000 evaluation limit")
        mutation = settings["mutation_rate"]
        if (
            isinstance(mutation, bool)
            or not isinstance(mutation, int | float)
            or not np.isfinite(mutation)
            or not 0 <= mutation <= 1
        ):
            raise ValueError("strategy_composition.mutation_rate must be between zero and one")
        objective_name = str(settings["objective"])
        if objective_name not in self.OBJECTIVES:
            raise ValueError(f"objective must be one of {sorted(self.OBJECTIVES)}")
        windows = settings["feature_windows"]
        if (
            not isinstance(windows, list)
            or not windows
            or any(isinstance(value, bool) or not isinstance(value, int) or value < 2 for value in windows)
            or len(set(windows)) != len(windows)
        ):
            raise ValueError("feature_windows must be unique integers >= 2")

        manifests = [
            context.store.get_dataset(dataset_id)["manifest"]
            for dataset_id in spec.dataset_ids
        ]
        bars = self.bar_loader(context.store, spec)
        config, periods_per_year = _build_portfolio_config(spec, manifests)
        engine = PointInTimeFeatureEngine(windows=tuple(windows))
        train_panel = build_model_feature_panel(
            bars, engine, spec.track,
            start=spec.training_start, end=spec.training_end,
        )
        registry = default_component_registry(windows)
        composer = StrategyComposer(
            registry,
            population_size=settings["population_size"],
            generations=settings["generations"],
            max_components=settings["max_components"],
            mutation_rate=float(mutation),
            seed=spec.random_seed,
        )
        train_cache: dict[str, dict[str, float | int]] = {}
        train_return_cache: dict[str, np.ndarray] = {}

        def train_fitness(composition: Composition) -> float:
            # The callback receives TRAIN only; component IDs resolve through the closed registry.
            context.check_cancelled()
            payload = _composition_to_payload(composition)
            key = json.dumps(payload, sort_keys=True, separators=(",", ":"))
            if key not in train_cache:
                scores = composition_scores(composition, train_panel, windows)
                result = evaluate_model_scores(
                    train_panel, scores, config,
                    partition="train",
                    start=spec.training_start, end=spec.training_end,
                    periods_per_year=periods_per_year,
                )
                train_cache[key] = result.metrics
                train_return_cache[key] = (
                    result.result.equity_curve.pct_change().dropna().to_numpy(dtype=np.float64)
                )
            score = float(train_cache[key][objective_name])
            if not np.isfinite(score):
                raise ValueError("strategy-composition TRAIN objective is non-finite")
            return score

        context.log(
            f"composition TRAIN start: population={settings['population_size']}, "
            f"generations={settings['generations']}, components={len(registry)}"
        )
        trace = composer.run(train_fitness)
        bars_digest = _bars_fingerprint(bars)
        archive = list(trace.candidate_archive)
        candidate_rows: list[dict[str, Any]] = []
        candidate_id_map: dict[str, str] = {}

        # Persist every attempted composition and resolve ancestry to stored candidate IDs.
        for item in archive:
            context.check_cancelled()
            composition = item["composition"]
            payload = _composition_to_payload(composition)
            key = json.dumps(payload, sort_keys=True, separators=(",", ":"))
            metrics = train_cache.get(key)
            succeeded = item["status"] == "succeeded" and metrics is not None
            digest_payload = {
                "experiment_fingerprint": spec.fingerprint,
                "bars_sha256": bars_digest,
                "composition": payload,
                "candidate_id": item["candidate_id"],
                "generation": item["generation"],
                "seed": spec.random_seed,
                "feature_windows": windows,
            }
            candidate_digest = hashlib.sha256(
                json.dumps(
                    digest_payload, sort_keys=True, separators=(",", ":"), allow_nan=False
                ).encode("utf-8")
            ).hexdigest()
            candidate_id = f"{spec.experiment_id}-{candidate_digest[:16]}"
            candidate_id_map[str(item["candidate_id"])] = candidate_id
            candidate_rows.append({
                "source_candidate_id": item["candidate_id"],
                "candidate_id": candidate_id,
                "candidate_digest": candidate_digest,
                "composition": composition,
                "composition_payload": payload,
                "generation": int(item["generation"]),
                "index": int(item["index"]),
                "train_score": float(item["fitness"]) if succeeded else None,
                "train_metrics": metrics or {},
                "train_key": key,
                "status": "succeeded" if succeeded else "failed",
                "failure_reason": item.get("failure_reason"),
                "lineage": dict(item["lineage"]),
            })

        statistical_candidates = [
            item for item in candidate_rows
            if item["status"] == "succeeded" and item["train_key"] in train_return_cache
        ]
        if statistical_candidates:
            statistical_report = candidate_family_report_from_returns(
                [item["candidate_id"] for item in statistical_candidates],
                {
                    item["candidate_id"]: train_return_cache[item["train_key"]]
                    for item in statistical_candidates
                },
                periods_per_year=periods_per_year,
                pbo_blocks=8,
                pbo_candidate_limit=128,
            )
            _record_train_family_diagnostics(context, spec, statistical_report)
        else:
            statistical_report = {
                "classification": "not_computed",
                "reason": "no successful composition candidate return vectors",
                "candidate_family_size": 0,
            }

        for candidate in candidate_rows:
            if context.store.has_candidate(spec.experiment_id, candidate["candidate_digest"]):
                continue
            lineage = dict(candidate["lineage"])
            raw_parents = lineage.get("parent_candidate_ids", [])
            lineage["parent_candidate_ids"] = [
                candidate_id_map.get(str(parent), str(parent))
                for parent in raw_parents
            ] if isinstance(raw_parents, list) else []
            lineage.update({
                "origin": "allow_listed_strategy_component_evolution",
                "source_candidate_id": candidate["source_candidate_id"],
                "feature_windows": windows,
                "selection": "train_objective",
            })
            metric_payload = (
                {
                    "status": "succeeded",
                    "train": candidate["train_metrics"],
                    "train_fitness": candidate["train_score"],
                }
                if candidate["status"] == "succeeded"
                else {
                    "status": "failed",
                    "failure_reason": candidate["failure_reason"] or "composition fitness failed",
                }
            )
            context.store.append_candidate(
                candidate_id=candidate["candidate_id"],
                experiment_id=spec.experiment_id,
                candidate_digest=candidate["candidate_digest"],
                family=AlgorithmFamily.STRATEGY_COMPOSITION.value,
                generation=candidate["generation"],
                parameters={
                    "composition": candidate["composition_payload"],
                    "feature_windows": windows,
                },
                metrics=metric_payload,
                lineage=lineage,
            )

        successful = [item for item in candidate_rows if item["status"] == "succeeded"]
        if not successful:
            raise RuntimeError("strategy composition produced no valid TRAIN candidate")
        final_generation = settings["generations"]
        final_population = [
            item for item in successful if item["generation"] == final_generation
        ]
        shortlist = sorted(
            final_population,
            key=lambda item: (-float(item["train_score"]), item["candidate_digest"]),
        )[:min(settings["validation_candidates"], len(final_population))]
        if not shortlist:
            raise RuntimeError("final composition population has no valid candidate for VALIDATION")

        validation_panel = build_model_feature_panel(
            bars, engine, spec.track,
            start=spec.validation_start, end=spec.validation_end,
        )
        validation_rows: list[dict[str, Any]] = []
        for index, candidate in enumerate(shortlist, start=1):
            context.check_cancelled()
            context.log(f"composition VALIDATION candidate {index}/{len(shortlist)}")
            scores = composition_scores(candidate["composition"], validation_panel, windows)
            result = evaluate_model_scores(
                validation_panel, scores, config,
                partition="validation",
                start=spec.validation_start, end=spec.validation_end,
                periods_per_year=periods_per_year,
            )
            # Validation is persisted as a child record of the immutable TRAIN genome.
            validation_definition = {
                "experiment_fingerprint": spec.fingerprint,
                "train_candidate_digest": candidate["candidate_digest"],
                "composition": candidate["composition_payload"],
                "validation_metrics": result.metrics,
                "bars_sha256": bars_digest,
                "objective": objective_name,
            }
            validation_digest = hashlib.sha256(
                json.dumps(
                    validation_definition, sort_keys=True, separators=(",", ":"), allow_nan=False
                ).encode("utf-8")
            ).hexdigest()
            validation_candidate_id = (
                f"{spec.experiment_id}-validation-{validation_digest[:16]}"
            )
            validation_score = float(result.metrics[objective_name])
            validation_rows.append({
                "candidate_id": candidate["candidate_id"],
                "candidate_digest": candidate["candidate_digest"],
                "validation_candidate_id": validation_candidate_id,
                "validation_candidate_digest": validation_digest,
                "composition": candidate["composition_payload"],
                "train_fitness": candidate["train_score"],
                "validation_score": validation_score,
                "validation_metrics": result.metrics,
            })
            if not context.store.has_candidate(spec.experiment_id, validation_digest):
                context.store.append_candidate(
                    candidate_id=validation_candidate_id,
                    experiment_id=spec.experiment_id,
                    candidate_digest=validation_digest,
                    family="strategy_composition_validation",
                    generation=settings["generations"] + 1,
                    parameters={
                        "composition": candidate["composition_payload"],
                        "feature_windows": windows,
                    },
                    metrics={
                        "train_fitness": candidate["train_score"],
                        "train": candidate["train_metrics"],
                        "validation_objective": validation_score,
                        "validation": result.metrics,
                    },
                    lineage={
                        "origin": "strategy_composition_validation_shortlist",
                        "parent_candidate_ids": [candidate["candidate_id"]],
                        "selection": "validation_objective",
                        "train_candidate_digest": candidate["candidate_digest"],
                        "objective": objective_name,
                        "final_holdout_accessed": False,
                    },
                )
        selected = max(
            validation_rows,
            key=lambda item: (
                item["validation_score"], item["train_fitness"], item["candidate_digest"]
            ),
        )
        context.store.append_event(
            spec.experiment_id,
            "strategy_composition_candidate_frozen",
            {
                "selected_candidate_id": selected["candidate_id"],
                "selected_candidate_digest": selected["candidate_digest"],
                "objective": objective_name,
                "feature_windows": windows,
                "population_size": settings["population_size"],
                "generations": settings["generations"],
                "candidate_count": len(candidate_rows),
                "successful_train_candidates": len(successful),
                "validation_shortlist_count": len(validation_rows),
                "bars_sha256": bars_digest,
                "final_holdout_accessed": False,
            },
        )
        context.check_cancelled()

        # The selected immutable component genome is evaluated once on OOS and never retuned.
        selected_composition = next(
            item["composition"] for item in shortlist
            if item["candidate_id"] == selected["candidate_id"]
        )
        oos_panel = build_model_feature_panel(
            bars, engine, spec.track,
            start=spec.oos_start, end=spec.oos_end,
        )
        oos_scores = composition_scores(selected_composition, oos_panel, windows)
        oos_result = evaluate_model_scores(
            oos_panel, oos_scores, config,
            partition="out_of_sample",
            start=spec.oos_start, end=spec.oos_end,
            periods_per_year=periods_per_year,
        )
        # Preserve the frozen OOS assessment as a child of the validation-selected genome.
        oos_definition = {
            "experiment_fingerprint": spec.fingerprint,
            "validation_candidate_digest": selected["validation_candidate_digest"],
            "composition": selected["composition"],
            "oos_metrics": oos_result.metrics,
            "portfolio": oos_result.result.to_dict(),
            "bars_sha256": bars_digest,
        }
        oos_digest = hashlib.sha256(
            json.dumps(
                oos_definition, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode("utf-8")
        ).hexdigest()
        oos_candidate_id = f"{spec.experiment_id}-oos-{oos_digest[:16]}"
        if not context.store.has_candidate(spec.experiment_id, oos_digest):
            context.store.append_candidate(
                candidate_id=oos_candidate_id,
                experiment_id=spec.experiment_id,
                candidate_digest=oos_digest,
                family="strategy_composition_selected_oos",
                generation=settings["generations"] + 2,
                parameters={
                    "composition": selected["composition"],
                    "feature_windows": windows,
                },
                metrics={
                    "train_fitness": selected["train_fitness"],
                    "validation": selected["validation_metrics"],
                    "out_of_sample": oos_result.metrics,
                    "portfolio": oos_result.result.to_dict(),
                },
                lineage={
                    "origin": "strategy_composition_frozen_oos",
                    "parent_candidate_ids": [selected["validation_candidate_id"]],
                    "train_parent_candidate_id": selected["candidate_id"],
                    "selection": "validation_objective",
                    "objective": objective_name,
                    "final_holdout_accessed": False,
                },
            )
        context.store.append_event(
            spec.experiment_id,
            "strategy_composition_oos_recorded",
            {
                "selected_candidate_id": selected["candidate_id"],
                "selected_candidate_digest": selected["candidate_digest"],
                "selected_validation_candidate_id": selected["validation_candidate_id"],
                "oos_candidate_id": oos_candidate_id,
                "oos_candidate_digest": oos_digest,
                "oos_metrics": oos_result.metrics,
                "final_holdout_accessed": False,
            },
        )
        return {
            "experiment_id": spec.experiment_id,
            "algorithm_family": AlgorithmFamily.STRATEGY_COMPOSITION.value,
            "objective": objective_name,
            "feature_windows": windows,
            "registry_component_count": len(registry),
            "population_size": settings["population_size"],
            "generations": settings["generations"],
            "candidate_count": len(candidate_rows),
            "successful_train_candidates": len(successful),
            "failed_candidates": len(candidate_rows) - len(successful),
            "validation_shortlist": validation_rows,
            "selected_candidate": selected,
            "training_candidate_family_diagnostics": statistical_report,
            "out_of_sample_candidate_id": oos_candidate_id,
            "out_of_sample": {
                "metrics": oos_result.metrics,
                "portfolio": oos_result.result.to_dict(),
                "sample_count": oos_result.sample_count,
            },
            "bars_sha256": bars_digest,
            "final_holdout_accessed": False,
        }


class ParetoStrategySearchJobRunner:
    """Run NSGA-II over existing-strategy parameters using isolated portfolio simulations."""

    OBJECTIVES = frozenset({
        "sharpe", "sortino", "cagr", "calmar", "total_return",
        "max_drawdown", "volatility", "win_rate", "turnover",
    })

    def __init__(
        self,
        *,
        crypto_data_root: str | Path | None = None,
        bar_loader: Callable[[ExperimentStore, ExperimentSpec], dict[str, pd.DataFrame]] | None = None,
    ) -> None:
        # Data access is identical to the other research workers and stops at OOS end.
        self.crypto_data_root = crypto_data_root
        self.bar_loader = bar_loader or (
            lambda store, spec: load_registered_bars(
                store, spec, crypto_data_root=self.crypto_data_root
            )
        )
        self.registry = ExistingStrategyRegistry()

    @staticmethod
    def _config_key(values: Mapping[str, Any]) -> str:
        # Use canonical JSON for genome deduplication and fitness caching.
        return json.dumps(values, sort_keys=True, separators=(",", ":"), default=str)

    def __call__(
        self,
        context: JobContext,
        experiment_record: dict[str, Any],
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        # Multi-objective search inputs are fixed in the experiment fingerprint.
        if parameters:
            raise ValueError("Pareto runner accepts no job-time overrides")
        context.check_cancelled()
        spec = experiment_spec_from_record(experiment_record)
        if spec.algorithm_family is not AlgorithmFamily.PARETO_SEARCH:
            raise ValueError("pareto_search runner requires pareto_search family")
        strategy_name = spec.parameters.get("strategy_name")
        if not isinstance(strategy_name, str) or not strategy_name.strip():
            raise ValueError("Pareto search requires a registered strategy_name")
        descriptor = self.registry.describe(strategy_name)
        base_parameters = spec.parameters.get("strategy_parameters", {})
        if not isinstance(base_parameters, dict):
            raise ValueError("strategy_parameters must be a JSON object")
        self.registry.validate_parameter_payload(strategy_name, base_parameters)
        space = ExistingStrategyOptimizerJobRunner._search_parameters(descriptor)

        settings = spec.parameters.get("pareto_search")
        required = {
            "population_size", "generations", "mutation_rate",
            "validation_candidates", "objectives", "directions",
        }
        if not isinstance(settings, dict) or not required.issubset(settings):
            raise ValueError(f"pareto_search settings require {sorted(required)}")
        for name in ("population_size", "generations", "validation_candidates"):
            value = settings[name]
            minimum = 4 if name == "population_size" else 1
            maximum = 10000 if name != "validation_candidates" else 1000
            if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
                raise ValueError(f"pareto_search.{name} must be an integer from {minimum} to {maximum}")
        if settings["population_size"] * (settings["generations"] + 1) > 10000:
            raise ValueError("Pareto candidate count exceeds the 10000 evaluation limit")
        mutation_rate = settings["mutation_rate"]
        if (
            isinstance(mutation_rate, bool)
            or not isinstance(mutation_rate, int | float)
            or not np.isfinite(mutation_rate)
            or not 0 <= mutation_rate <= 1
        ):
            raise ValueError("pareto_search.mutation_rate must be between zero and one")
        raw_objectives = settings["objectives"]
        raw_directions = settings["directions"]
        if not isinstance(raw_objectives, (list, tuple)) or not isinstance(raw_directions, (list, tuple)):
            raise ValueError("Pareto objectives and directions must be arrays")
        objectives = tuple(raw_objectives)
        directions = tuple(raw_directions)
        if (
            len(objectives) < 2
            or len(objectives) != len(directions)
            or len(set(objectives)) != len(objectives)
            or any(name not in self.OBJECTIVES for name in objectives)
            or any(direction not in {"min", "max"} for direction in directions)
        ):
            raise ValueError("Pareto search requires 2+ unique objectives with aligned min/max directions")

        manifests = [
            context.store.get_dataset(dataset_id)["manifest"]
            for dataset_id in spec.dataset_ids
        ]
        bars = self.bar_loader(context.store, spec)
        config, periods_per_year = _build_portfolio_config(spec, manifests)
        defaults = dict(descriptor.defaults)
        defaults.update(base_parameters)
        bars_digest = _bars_fingerprint(bars)
        train_metrics: dict[str, dict[str, float | int]] = {}
        train_calls = 0

        def metrics_vector(genome: Mapping[str, Any]) -> tuple[float, ...]:
            # Every objective is calculated from the same TRAIN-only cash portfolio result.
            nonlocal train_calls
            context.check_cancelled()
            current = dict(defaults)
            current.update(genome)
            key = self._config_key(current)
            if key not in train_metrics:
                partition = _partition_target_frame(
                    spec,
                    strategy_name,
                    current,
                    bars,
                    config,
                    partition_name="train",
                    start=spec.training_start,
                    end=spec.training_end,
                    periods_per_year=int(spec.parameters["execution_assumptions"]["periods_per_year"]),
                )
                metrics = dict(partition.metrics)
                metrics["turnover"] = float(partition.result.turnover)
                train_metrics[key] = metrics
                train_calls += 1
                if train_calls % max(1, int(settings["population_size"])) == 0:
                    context.log(f"Pareto TRAIN distinct genome evaluations: {train_calls}")
            values = tuple(float(train_metrics[key][name]) for name in objectives)
            if not np.isfinite(values).all():
                raise ValueError("Pareto TRAIN objective vector is non-finite")
            return values

        def initialise(rng: np.random.Generator) -> dict[str, object]:
            # Sample every parameter from the existing strategy's typed registry bounds.
            return {parameter.name: parameter.sample(rng) for parameter in space}

        def crossover(
            left: dict[str, object],
            right: dict[str, object],
            rng: np.random.Generator,
        ) -> dict[str, object]:
            # Select one parent's gene per dimension; no parameter escapes its declared domain.
            return {
                parameter.name: (
                    left[parameter.name]
                    if rng.random() < 0.5 else right[parameter.name]
                )
                for parameter in space
            }

        def mutate(
            genome: dict[str, object],
            rng: np.random.Generator,
        ) -> dict[str, object]:
            # Mutate each bounded dimension independently using its registered sampler.
            result = dict(genome)
            for parameter in space:
                if rng.random() < float(mutation_rate):
                    result[parameter.name] = parameter.sample(rng)
            return result

        context.log(
            f"NSGA-II TRAIN start: strategy={strategy_name}, objectives={objectives}, "
            f"population={settings['population_size']}, generations={settings['generations']}"
        )
        result = nsga2_optimize(
            initialise,
            metrics_vector,
            crossover,
            mutate,
            population_size=settings["population_size"],
            generations=settings["generations"],
            directions=directions,
            seed=spec.random_seed,
        )

        archive = list(result["candidate_archive"])
        candidate_rows: list[dict[str, Any]] = []
        candidate_id_map: dict[str, str] = {}
        for item in archive:
            context.check_cancelled()
            genome = dict(item["genome"])
            current = dict(defaults)
            current.update(genome)
            key = self._config_key(current)
            metrics = train_metrics.get(key)
            succeeded = item["status"] == "succeeded" and metrics is not None
            digest_payload = {
                "experiment_fingerprint": spec.fingerprint,
                "bars_sha256": bars_digest,
                "strategy_name": strategy_name,
                "genome": genome,
                "candidate_id": item["candidate_id"],
                "generation": item["generation"],
                "objectives": item["objectives"],
                "directions": directions,
            }
            candidate_digest = hashlib.sha256(
                json.dumps(
                    digest_payload, sort_keys=True, separators=(",", ":"), default=str,
                    allow_nan=False,
                ).encode("utf-8")
            ).hexdigest()
            candidate_id = f"{spec.experiment_id}-{candidate_digest[:16]}"
            candidate_id_map[str(item["candidate_id"])] = candidate_id
            candidate_rows.append({
                "source_candidate_id": item["candidate_id"],
                "candidate_id": candidate_id,
                "candidate_digest": candidate_digest,
                "parameters": current,
                "genome": genome,
                "generation": int(item["generation"]),
                "objectives": list(item["objectives"]) if succeeded else [],
                "train_metrics": metrics or {},
                "status": "succeeded" if succeeded else "failed",
                "failure_reason": item.get("failure_reason"),
                "lineage": dict(item["lineage"]),
            })

        # Persist all tried candidates, not just the final nondominated set.
        for candidate in candidate_rows:
            if context.store.has_candidate(spec.experiment_id, candidate["candidate_digest"]):
                continue
            lineage = dict(candidate["lineage"])
            raw_parents = lineage.get("parent_candidate_ids", [])
            lineage["parent_candidate_ids"] = [
                candidate_id_map.get(str(parent), str(parent))
                for parent in raw_parents
            ] if isinstance(raw_parents, list) else []
            lineage.update({
                "origin": "nsga2_existing_strategy_parameter_search",
                "source_candidate_id": candidate["source_candidate_id"],
                "objectives": list(objectives),
                "directions": list(directions),
                "selection": "pareto_rank_and_crowding_distance",
            })
            if candidate["status"] == "succeeded":
                metric_payload = {
                    "status": "succeeded",
                    "train": candidate["train_metrics"],
                    "objective_vector": candidate["objectives"],
                }
            else:
                metric_payload = {
                    "status": "failed",
                    "failure_reason": candidate["failure_reason"] or "NSGA-II fitness failed",
                }
            context.store.append_candidate(
                candidate_id=candidate["candidate_id"],
                experiment_id=spec.experiment_id,
                candidate_digest=candidate["candidate_digest"],
                family=AlgorithmFamily.PARETO_SEARCH.value,
                generation=candidate["generation"],
                parameters={
                    "strategy_name": strategy_name,
                    "strategy_parameters": candidate["parameters"],
                },
                metrics=metric_payload,
                lineage=lineage,
            )

        # Validation shortlist is drawn only from the final TRAIN Pareto front.
        train_front = list(result["pareto_front"])
        if not train_front:
            raise RuntimeError("NSGA-II produced no final TRAIN Pareto front")
        pareto_candidates = [
            ParetoCandidate(
                candidate_id=str(item["candidate_id"]),
                objectives=tuple(float(value) for value in item["objectives"]),
            )
            for item in train_front
        ]
        shortlist_ids = {
            candidate.candidate_id
            for candidate in select_nsga2(
                pareto_candidates,
                directions,
                size=min(settings["validation_candidates"], len(pareto_candidates)),
            )
        }
        by_source_id = {item["source_candidate_id"]: item for item in candidate_rows}
        shortlist = [
            by_source_id[str(item["candidate_id"])]
            for item in train_front
            if str(item["candidate_id"]) in shortlist_ids
        ]

        validation_rows: list[dict[str, Any]] = []
        for index, candidate in enumerate(shortlist, start=1):
            context.check_cancelled()
            context.log(f"Pareto VALIDATION candidate {index}/{len(shortlist)}")
            partition = _partition_target_frame(
                spec,
                strategy_name,
                candidate["parameters"],
                bars,
                config,
                partition_name="validation",
                start=spec.validation_start,
                end=spec.validation_end,
                periods_per_year=int(spec.parameters["execution_assumptions"]["periods_per_year"]),
            )
            metrics = dict(partition.metrics)
            metrics["turnover"] = float(partition.result.turnover)
            vector = tuple(float(metrics[name]) for name in objectives)
            validation_rows.append({
                "candidate_id": candidate["candidate_id"],
                "candidate_digest": candidate["candidate_digest"],
                "parameters": candidate["parameters"],
                "train_objectives": candidate["objectives"],
                "validation_objectives": vector,
                "validation_metrics": metrics,
            })
        validation_pareto = [
            ParetoCandidate(
                candidate_id=item["candidate_id"],
                objectives=tuple(item["validation_objectives"]),
            )
            for item in validation_rows
        ]
        validation_fronts = non_dominated_fronts(validation_pareto, directions)
        if not validation_fronts:
            raise RuntimeError("no candidate survived Pareto VALIDATION evaluation")
        first_front = [validation_pareto[index] for index in validation_fronts[0]]
        # The final selection policy is explicitly NSGA-II crowding within the VALIDATION front.
        selected_candidate = select_nsga2(
            first_front,
            directions,
            size=1,
        )[0]
        selected = next(
            item for item in validation_rows
            if item["candidate_id"] == selected_candidate.candidate_id
        )
        context.store.append_event(
            spec.experiment_id,
            "pareto_search_candidate_frozen",
            {
                "strategy_name": strategy_name,
                "objectives": list(objectives),
                "directions": list(directions),
                "train_pareto_front_size": len(result["pareto_front"]),
                "validation_pareto_front_size": len(validation_fronts[0]),
                "validation_shortlist_count": len(validation_rows),
                "selection_policy": "nsga2_crowding_within_validation_front",
                "selected_candidate_id": selected["candidate_id"],
                "selected_candidate_digest": selected["candidate_digest"],
                "bars_sha256": bars_digest,
                "final_holdout_accessed": False,
            },
        )
        context.check_cancelled()

        # Evaluate the chosen validation-Pareto candidate once on OOS after freezing it.
        frozen_parameters = dict(spec.parameters)
        frozen_parameters["strategy_parameters"] = selected["parameters"]
        frozen_spec = replace(spec, parameters=frozen_parameters)
        oos_evaluation = evaluate_existing_strategy(
            frozen_spec,
            bars,
            config,
            periods_per_year=int(spec.parameters["execution_assumptions"]["periods_per_year"]),
            store=context.store,
            check_cancelled=context.check_cancelled,
            progress_callback=lambda stage, completed, total: context.log(
                f"frozen Pareto candidate {stage}: {completed}/{total}"
            ),
            candidate_family=AlgorithmFamily.PARETO_SEARCH.value,
            lineage_metadata={
                "origin": "nsga2_validation_pareto_selection",
                "parent_candidate_ids": [],
                "selected_pareto_candidate_id": selected["candidate_id"],
                "objectives": list(objectives),
                "directions": list(directions),
            },
        )
        return {
            "experiment_id": spec.experiment_id,
            "algorithm_family": AlgorithmFamily.PARETO_SEARCH.value,
            "strategy_name": strategy_name,
            "objectives": list(objectives),
            "directions": list(directions),
            "objective_directions": result["objective_directions"],
            "evaluations": result["evaluations"],
            "candidate_count": len(candidate_rows),
            "failed_candidates": len(result["failures"]),
            "train_pareto_front": result["pareto_front"],
            "validation_shortlist": validation_rows,
            "validation_pareto_front_size": len(validation_fronts[0]),
            "selection_policy": "nsga2_crowding_within_validation_front",
            "selected_candidate": selected,
            "final_evaluation": oos_evaluation.to_dict(),
            "final_holdout_accessed": False,
        }


def build_default_job_manager(
    store: ExperimentStore,
    *,
    crypto_data_root: str | Path | None = None,
    max_workers: int = 1,
    max_queued: int = 8,
):
    """Create a bounded manager with allow-listed existing-strategy evaluation and search runners."""
    # One worker is the conservative default until local GPU/RAM throughput is measured.
    from .jobs import ResearchJobManager

    manager = ResearchJobManager(store, max_workers=max_workers, max_queued=max_queued)
    manager.register_runner(
        "existing_strategy_evaluation",
        ExistingStrategyJobRunner(crypto_data_root=crypto_data_root),
    )
    manager.register_runner(
        "existing_strategy_optimization",
        ExistingStrategyOptimizerJobRunner(crypto_data_root=crypto_data_root),
    )
    manager.register_runner(
        "genetic_programming",
        GeneticProgrammingJobRunner(crypto_data_root=crypto_data_root),
    )
    manager.register_runner(
        "neuroevolution",
        NeuroevolutionJobRunner(crypto_data_root=crypto_data_root),
    )
    manager.register_runner(
        "strategy_composition",
        StrategyCompositionJobRunner(crypto_data_root=crypto_data_root),
    )
    manager.register_runner(
        "pareto_search",
        ParetoStrategySearchJobRunner(crypto_data_root=crypto_data_root),
    )
    return manager
