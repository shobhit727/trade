"""Track-aware evaluation of existing strategies through the next-open portfolio simulator."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

import pandas as pd

from .domain import ResearchTrack
from .experiments import ExperimentSpec
from .metrics import compute_portfolio_metrics
from .portfolio import PortfolioConfig, PortfolioResult, PortfolioSimulator
from .storage import ExperimentStore
from .strategy_signals import ExistingStrategySignalAdapter


@dataclass(frozen=True, slots=True)
class PartitionEvaluation:
    """One market-scoped backtest over a declared chronological partition."""

    partition: str
    start: datetime
    end: datetime
    result: PortfolioResult
    metrics: dict[str, float | int]

    def to_dict(self) -> dict[str, object]:
        # Serialize financial fields as strings and include the requested time window.
        return {
            "partition": self.partition,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "market": self.result.market.value,
            "portfolio": self.result.to_dict(),
            "metrics": self.metrics,
        }


@dataclass(frozen=True, slots=True)
class ExistingStrategyEvaluation:
    """Reproducible train/validation/OOS evaluation without final-holdout access."""

    experiment_id: str
    strategy_name: str
    candidate_digest: str
    evaluations: tuple[PartitionEvaluation, ...]
    final_holdout_accessed: bool = False

    def to_dict(self) -> dict[str, object]:
        # Clearly identify the unaccessed final holdout in every returned report.
        return {
            "experiment_id": self.experiment_id,
            "strategy_name": self.strategy_name,
            "candidate_digest": self.candidate_digest,
            "partitions": [item.to_dict() for item in self.evaluations],
            "final_holdout_accessed": self.final_holdout_accessed,
            "classification": "historical_research_candidate_not_deployable",
        }


def _partition_target_frame(
    spec: ExperimentSpec,
    strategy_name: str,
    strategy_parameters: dict[str, object],
    bars_by_symbol: Mapping[str, pd.DataFrame],
    config: PortfolioConfig,
    *,
    partition_name: str,
    start: datetime,
    end: datetime,
    periods_per_year: int,
) -> PartitionEvaluation:
    """Generate signals with pre-window history and execute only the chosen partition."""
    # The end boundary is half-open so one bar cannot belong to two partitions.
    if config.market is not spec.market:
        raise ValueError("portfolio config market differs from experiment market")
    if config.cost_model_id != spec.cost_model_id:
        raise ValueError("portfolio cost model id differs from experiment cost model id")
    if config.execution_model_id != spec.execution_model_id:
        raise ValueError("portfolio execution model id differs from experiment execution model id")
    truncated: dict[str, pd.DataFrame] = {}
    for symbol, frame in bars_by_symbol.items():
        index = pd.DatetimeIndex(frame.index)
        if index.tz is None:
            raise ValueError(f"{symbol}: bars must have timezone-aware timestamps")
        utc_index = index.tz_convert("UTC")
        selected = frame.loc[utc_index < end].copy()
        if selected.empty:
            raise ValueError(f"{symbol}: no bars available before partition end")
        truncated[symbol] = selected

    # Validate that at least one observation occurs in this partition.
    first_index = pd.DatetimeIndex(next(iter(truncated.values())).index)
    first_utc = first_index.tz_convert("UTC")
    start_position = int(first_utc.searchsorted(start, side="left"))
    if start_position >= len(first_index):
        raise ValueError(
            f"no observations in {partition_name} window "
            f"{start.isoformat()}..{end.isoformat()}"
        )

    adapter = ExistingStrategySignalAdapter()
    signals = adapter.build_signals(strategy_name, truncated, parameters=strategy_parameters)
    if spec.track in {ResearchTrack.NSE_INDIVIDUAL, ResearchTrack.CRYPTO_INDIVIDUAL}:
        if len(truncated) != 1:
            raise ValueError("individual-asset track requires exactly one dataset/instrument")
        symbol = next(iter(truncated))
        targets = adapter.individual_asset_targets(signals, symbol)
    else:
        targets = adapter.equal_weight_targets(signals)

    # Suppress positions before the partition's preceding close. That bar's signal
    # is the only pre-window decision eligible to execute at the first in-window open.
    decision_position = max(start_position - 1, 0)
    if decision_position > 0:
        targets.iloc[:decision_position] = 0.0

    # Every partition receives its own market-scoped seed capital and clean ledger.
    result = PortfolioSimulator(config).run(truncated, targets)
    metric_start = max(start_position - 1, 0)
    in_window_curve = result.equity_curve.iloc[metric_start:].copy()
    metric_index = pd.DatetimeIndex(in_window_curve.index).tz_convert("UTC")
    in_window_curve = in_window_curve.loc[metric_index < end]
    if len(in_window_curve) < 2:
        raise ValueError(f"{partition_name}: insufficient equity observations for metrics")

    # Annualisation is explicit; crypto 24/7 and NSE trading calendars must differ.
    metrics = compute_portfolio_metrics(
        in_window_curve,
        periods_per_year=periods_per_year,
    ).to_dict()
    return PartitionEvaluation(partition_name, start, end, result, metrics)


def _bars_fingerprint(bars_by_symbol: Mapping[str, pd.DataFrame]) -> str:
    """Hash the exact in-memory OHLCV panels supplied to the evaluator."""
    # Stable symbol/column ordering binds results to actual rows and timestamp indices.
    digest = hashlib.sha256()
    for symbol in sorted(bars_by_symbol):
        frame = bars_by_symbol[symbol]
        normalized = frame.reindex(sorted(frame.columns), axis=1)
        digest.update(symbol.encode("utf-8"))
        digest.update(pd.util.hash_pandas_object(normalized, index=True).to_numpy(dtype="uint64").tobytes())
    return digest.hexdigest()


def evaluate_existing_strategy(
    spec: ExperimentSpec,
    bars_by_symbol: Mapping[str, pd.DataFrame],
    portfolio_config: PortfolioConfig,
    *,
    periods_per_year: int,
    store: ExperimentStore | None = None,
) -> ExistingStrategyEvaluation:
    """Evaluate a frozen existing strategy on TRAIN, VALIDATION and OOS only.

    The final holdout is deliberately not read or sliced here. The strategy parameters
    are frozen in ExperimentSpec.parameters and the same candidate is used in every
    reported stage. For an optimised candidate, callers must first complete model
    selection using TRAIN/VALIDATION and create a new immutable ExperimentSpec.
    """
    # Validate the single-market and cost-provenance contract before evaluating bars.
    if portfolio_config.market is not spec.market:
        raise ValueError("portfolio config market differs from experiment market")
    if portfolio_config.cost_model_id != spec.cost_model_id:
        raise ValueError("portfolio cost model id differs from experiment cost model id")
    if portfolio_config.execution_model_id != spec.execution_model_id:
        raise ValueError("portfolio execution model id differs from experiment execution model id")
    if periods_per_year < 1:
        raise ValueError("periods_per_year must be positive")
    strategy_name = spec.parameters.get("strategy_name")
    if not isinstance(strategy_name, str) or not strategy_name.strip():
        raise ValueError("existing strategy experiment requires parameters.strategy_name")
    strategy_parameters = spec.parameters.get("strategy_parameters", {})
    if not isinstance(strategy_parameters, dict):
        raise ValueError("strategy_parameters must be an object")

    # Reproducible evaluation requires persisted, approved manifests for each data input.
    if store is None:
        raise ValueError("ExperimentStore with registered approved datasets is required")
    required_windows = (
        (spec.training_start, spec.training_end),
        (spec.validation_start, spec.validation_end),
        (spec.oos_start, spec.oos_end),
        (spec.final_holdout_start, spec.final_holdout_end),
    )
    manifest_instruments: set[str] = set()
    for dataset_id in spec.dataset_ids:
        row = store.get_dataset(dataset_id)
        manifest = row["manifest"]
        if row["market"] != spec.market.value:
            raise ValueError(f"cross-market dataset rejected: {dataset_id}")
        if row["resolution"] != spec.resolution.value:
            raise ValueError(f"dataset {dataset_id} resolution differs from experiment")
        if manifest["license_status"] != "approved":
            raise ValueError(f"dataset {dataset_id} licence is not approved")
        manifest_instruments.add(str(manifest["instrument"]))
        coverage_start = datetime.fromisoformat(manifest["coverage_start"])
        coverage_end = datetime.fromisoformat(manifest["coverage_end"])
        if coverage_start.tzinfo is None or coverage_end.tzinfo is None:
            raise ValueError(f"dataset {dataset_id} has timezone-naive coverage")
        for window_start, window_end in required_windows:
            if coverage_start > window_start or coverage_end < window_end:
                raise ValueError(f"dataset {dataset_id} does not cover every experiment partition")
    if not manifest_instruments.issubset(set(bars_by_symbol)):
        raise ValueError("provided bar symbols do not match registered dataset instruments")

    # Validate parameter field names against the authoritative existing catalogue.
    adapter = ExistingStrategySignalAdapter()
    adapter.registry.validate_parameter_payload(strategy_name, strategy_parameters)
    bars_digest = _bars_fingerprint(bars_by_symbol)
    candidate_definition = {
        "experiment_id": spec.experiment_id,
        "strategy_name": strategy_name,
        "bars_sha256": bars_digest,
        "strategy_parameters": strategy_parameters,
        "dataset_ids": list(spec.dataset_ids),
        "code_version": spec.code_version,
        "git_commit": spec.git_commit,
        "cost_model_id": spec.cost_model_id,
        "execution_model_id": spec.execution_model_id,
    }
    candidate_digest = hashlib.sha256(
        json.dumps(
            candidate_definition,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()

    # The same frozen configuration is evaluated in chronological, non-overlapping stages.
    windows = (
        ("train", spec.training_start, spec.training_end),
        ("validation", spec.validation_start, spec.validation_end),
        ("out_of_sample", spec.oos_start, spec.oos_end),
    )
    evaluations = tuple(
        _partition_target_frame(
            spec,
            strategy_name,
            strategy_parameters,
            bars_by_symbol,
            portfolio_config,
            partition_name=name,
            start=start,
            end=end,
            periods_per_year=periods_per_year,
        )
        for name, start, end in windows
    )
    result = ExistingStrategyEvaluation(
        experiment_id=spec.experiment_id,
        strategy_name=strategy_name,
        candidate_digest=candidate_digest,
        evaluations=evaluations,
        final_holdout_accessed=False,
    )

    if store is not None:
        # Persist stage-level metrics, immutable candidate parameters and no-holdout status.
        stage_metrics = {item.partition: item.metrics for item in evaluations}
        store.append_candidate(
            candidate_id=f"{spec.experiment_id}-existing-baseline",
            experiment_id=spec.experiment_id,
            candidate_digest=candidate_digest,
            family="existing_strategy",
            generation=0,
            parameters=candidate_definition,
            metrics=stage_metrics,
            lineage={
                "parent_candidate_ids": [],
                "origin": "existing_catalogue",
                "strategy_name": strategy_name,
                "mutation": None,
                "crossover": None,
                "selection": "frozen_experiment_spec",
            },
        )
        store.append_event(
            spec.experiment_id,
            "existing_strategy_evaluated",
            {
                "candidate_digest": candidate_digest,
                "bars_sha256": bars_digest,
                "partitions": [item.partition for item in evaluations],
                "final_holdout_accessed": False,
                "cost_model_id": spec.cost_model_id,
                "execution_model_id": spec.execution_model_id,
            },
        )
    return result
