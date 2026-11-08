"""Trusted allow-listed research runners for the persistent job manager."""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Mapping

import pandas as pd

from .adapters import CryptoLocalAdapter, NSELegacyAdapter, RESOLUTION_MAP
from .costs import CryptoVenueFeeCalculator, NSEDeliveryFeeCalculator
from .data_catalog import LicenseStatus
from .domain import AlgorithmFamily, DataResolution, Market, ResearchTrack
from .evaluation import ExistingStrategyEvaluation, evaluate_existing_strategy
from .experiments import ExperimentSpec
from .fx import FXRateSeries, convert_ohlcv_to_inr
from .jobs import JobContext
from .portfolio import PortfolioConfig
from .storage import ExperimentStore


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
    frame = adapter.load(instrument, resolution)
    # The runner never receives rows at or beyond the OOS end/locked holdout boundary.
    frame = frame.loc[pd.DatetimeIndex(frame.index).tz_convert("UTC") < max_time]
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


def build_default_job_manager(
    store: ExperimentStore,
    *,
    crypto_data_root: str | Path | None = None,
    max_workers: int = 1,
    max_queued: int = 8,
):
    """Create a bounded manager with only the safe existing-strategy runner registered."""
    # One worker is the conservative default until local GPU/RAM throughput is measured.
    from .jobs import ResearchJobManager

    manager = ResearchJobManager(store, max_workers=max_workers, max_queued=max_queued)
    manager.register_runner(
        "existing_strategy_evaluation",
        ExistingStrategyJobRunner(crypto_data_root=crypto_data_root),
    )
    return manager
