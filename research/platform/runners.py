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
from .jobs import JobContext
from .optimizers import (
    Candidate as SearchCandidate,
    Parameter as SearchParameter,
    differential_evolution,
    grid_search,
    optuna_tpe_search,
    random_search,
)
from .portfolio import PortfolioConfig
from .storage import ExperimentStore
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
        # Every optimiser receives the same finite search space and caller-declared budget.
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

        settings = spec.parameters.get("optimization")
        required = {"budget", "validation_candidates", "objective"}
        if not isinstance(settings, dict) or not required.issubset(settings):
            raise ValueError(
                "parameters.optimization must declare budget, validation_candidates and objective"
            )
        objective_name = str(settings["objective"])
        if objective_name not in self.OBJECTIVES:
            raise ValueError(f"objective must be one of {sorted(self.OBJECTIVES)}")
        budget = int(settings["budget"])
        validation_count = int(settings["validation_candidates"])
        if budget < 4 or validation_count < 1:
            raise ValueError("budget must be >= 4 and validation_candidates must be positive")

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
        search_candidates = (shipped_baseline, user_baseline, *search.candidates)

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
        if not successful_candidates:
            raise RuntimeError("no valid baseline or search candidate completed TRAIN")
        # Validation may select only a bounded TRAIN shortlist; it never feeds back into search.
        shortlist = sorted(
            candidate_rows,
            key=lambda item: (-item["train_score"], item["candidate_digest"]),
        )[:min(validation_count, len(candidate_rows))]
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
            validation_rows.append({
                "candidate_digest": candidate["candidate_digest"],
                "candidate_id": candidate["candidate_id"],
                "parameters": candidate["parameters"],
                "train_score": candidate["train_score"],
                "validation_score": validation_score,
                "validation_metrics": partition.metrics,
            })

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
                "successful_train_candidates": len(search.candidates),
                "search_failures": list(search.failures),
                "validation_shortlist_count": len(validation_rows),
                "objective": objective_name,
                "selected_candidate_id": selected["candidate_id"],
                "selected_candidate_digest": selected["candidate_digest"],
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
        )
        return {
            "experiment_id": spec.experiment_id,
            "search_family": spec.algorithm_family.value,
            "search_method": search.method,
            "objective": objective_name,
            "budget": budget,
            "candidate_count": len(candidate_rows),
            "successful_train_candidates": len(search.candidates),
            "failed_candidates": len(search.failures),
            "validation_shortlist": validation_rows,
            "selected_candidate": selected,
            "bars_sha256": bars_digest,
            "final_holdout_accessed": False,
            "final_evaluation": final_evaluation.to_dict(),
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
    return manager
