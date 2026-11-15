"""Four-track end-to-end validation (audit F-024 / section 7.22).

Each intended research track — NSE individual, NSE portfolio, crypto individual
and crypto portfolio — is exercised end to end on synthetic data:

    spec created -> candidate evaluated through the correct worker ->
    OOS classified under the approved F-001 policy -> results persisted ->
    cross-market isolation held.

The tests ARE the per-track report: every test prints the persisted experiment
record contents so the captured pytest output documents each track's artifacts.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from research.platform.data_catalog import DatasetManifest, LicenseStatus, ValueOrigin
from research.platform.domain import AlgorithmFamily, DataResolution, Market, ResearchTrack
from research.platform.evaluation import evaluate_existing_strategy
from research.platform.experiments import ExperimentSpec
from research.platform.jobs import ResearchJobManager
from research.platform.market import Fill, MarketLedger, Side
from research.platform.runners import (
    ExistingStrategyJobRunner,
    _build_portfolio_config,
    experiment_spec_from_record,
)
from research.platform.storage import ExperimentStore

UTC = timezone.utc

#: Per-track declaration: synthetic instrument, window shape and annualisation.
TRACK_SETUP: dict[ResearchTrack, dict[str, object]] = {
    ResearchTrack.NSE_INDIVIDUAL: {
        "symbols": ("TCS",),
        "exchange": "NSE",
        "resolution": DataResolution.ONE_DAY,
        "periods_per_year": 252,
        "cost_model_id": "nse-delivery-cost-model",
        "oos": (datetime(2026, 10, 2, tzinfo=UTC), datetime(2026, 10, 16, tzinfo=UTC)),
        "final_holdout": (datetime(2026, 10, 16, tzinfo=UTC), datetime(2026, 11, 8, tzinfo=UTC)),
    },
    ResearchTrack.NSE_PORTFOLIO: {
        "symbols": ("TCS", "INFY"),
        "exchange": "NSE",
        "resolution": DataResolution.ONE_DAY,
        "periods_per_year": 252,
        "cost_model_id": "nse-delivery-cost-model",
        "oos": (datetime(2026, 10, 2, tzinfo=UTC), datetime(2026, 10, 16, tzinfo=UTC)),
        "final_holdout": (datetime(2026, 10, 16, tzinfo=UTC), datetime(2026, 11, 8, tzinfo=UTC)),
    },
    ResearchTrack.CRYPTO_INDIVIDUAL: {
        "symbols": ("BTC",),
        "exchange": "BINANCE",
        "resolution": DataResolution.ONE_HOUR,
        "periods_per_year": 365 * 24,
        "cost_model_id": "crypto-binance-taker-maker1-taker5",
        "oos": (datetime(2025, 1, 1, 2, tzinfo=UTC), datetime(2025, 1, 1, 3, tzinfo=UTC)),
        "final_holdout": (datetime(2025, 1, 1, 3, tzinfo=UTC), datetime(2025, 1, 1, 4, tzinfo=UTC)),
    },
    ResearchTrack.CRYPTO_PORTFOLIO: {
        "symbols": ("BTC", "ETH"),
        "exchange": "BINANCE",
        "resolution": DataResolution.ONE_HOUR,
        "periods_per_year": 365 * 24,
        "cost_model_id": "crypto-binance-taker-maker1-taker5",
        "oos": (datetime(2025, 1, 1, 2, tzinfo=UTC), datetime(2025, 1, 1, 3, tzinfo=UTC)),
        "final_holdout": (datetime(2025, 1, 1, 3, tzinfo=UTC), datetime(2025, 1, 1, 4, tzinfo=UTC)),
    },
}

NSE_WINDOWS = {
    "training": (datetime(2016, 1, 1, tzinfo=UTC), datetime(2018, 1, 1, tzinfo=UTC)),
    "validation": (datetime(2018, 1, 1, tzinfo=UTC), datetime(2020, 1, 1, tzinfo=UTC)),
}
CRYPTO_WINDOWS = {
    "training": (datetime(2025, 1, 1, tzinfo=UTC), datetime(2025, 1, 1, 1, tzinfo=UTC)),
    "validation": (datetime(2025, 1, 1, 1, tzinfo=UTC), datetime(2025, 1, 1, 2, tzinfo=UTC)),
}


def _track_spec(track: ResearchTrack, *, negative: bool = False) -> ExperimentSpec:
    """Build one immutable spec bound to exactly the track's own market."""
    setup = TRACK_SETUP[track]
    market = ResearchTrack_track_market(track)
    windows = NSE_WINDOWS if market is Market.NSE else CRYPTO_WINDOWS
    parameters: dict[str, object] = {
        "strategy_name": "absolute_momentum",
        "strategy_parameters": {"period": 10, "threshold": 0.0},
        "execution_assumptions": {
            "slippage_bps": 5,
            "impact_coefficient_bps": 10,
            "max_participation": 0.05,
            "max_gross_exposure": 1.0,
            "periods_per_year": setup["periods_per_year"],
        },
    }
    if market is Market.CRYPTO:
        parameters["fee_schedule"] = {"maker_fee_bps": 1, "taker_fee_bps": 5}
    if negative:
        # The declared strategy does not exist in the catalogue: the negative
        # control must fail the worker, never silently produce metrics.
        parameters["strategy_name"] = "nonexistent_strategy_for_negative_control"
    return ExperimentSpec(
        experiment_id=f"four-track-{track.value}" + ("-negative" if negative else ""),
        market=market,
        track=track,
        algorithm_family=AlgorithmFamily.EXISTING_STRATEGY,
        resolution=setup["resolution"],
        dataset_ids=tuple(f"four-track-{track.value}-{symbol.lower()}-v1" for symbol in setup["symbols"]),
        random_seed=37,
        git_commit="0123456789abcdef0123456789abcdef01234567",
        code_version="four-track-validation",
        training_start=windows["training"][0],
        training_end=windows["training"][1],
        validation_start=windows["validation"][0],
        validation_end=windows["validation"][1],
        oos_start=setup["oos"][0],
        oos_end=setup["oos"][1],
        final_holdout_start=setup["final_holdout"][0],
        final_holdout_end=setup["final_holdout"][1],
        cost_model_id=setup["cost_model_id"],
        execution_model_id="next-open-participation-impact-v1",
        objectives=("net_return", "max_drawdown", "turnover"),
        parameters=parameters,
        created_at=datetime(2026, 11, 8, tzinfo=UTC),
    )


def ResearchTrack_track_market(track: ResearchTrack) -> Market:
    from research.platform.domain import TRACK_MARKET

    return TRACK_MARKET[track]


def _synthetic_bars(track: ResearchTrack) -> dict[str, pd.DataFrame]:
    """One deterministic OHLCV panel per symbol on the track's own calendar."""
    setup = TRACK_SETUP[track]
    if ResearchTrack_track_market(track) is Market.NSE:
        index = pd.date_range("2015-01-01", "2026-11-09", freq="D", tz="Asia/Kolkata")
        drift, amplitude = 0.015, 3.0
    else:
        index = pd.date_range("2024-12-01", "2025-01-01 12:00", freq="h", tz="UTC")
        drift, amplitude = 0.0004, 6.0
    bars: dict[str, pd.DataFrame] = {}
    for position, symbol in enumerate(setup["symbols"]):
        step = np.arange(len(index), dtype=np.float64)
        close = 100.0 + position * 20.0 + drift * step + amplitude * np.sin(step / 12.0 + position)
        bars[symbol] = pd.DataFrame(
            {
                "open": close - 0.05,
                "high": close + 0.5,
                "low": close - 0.5,
                "close": close,
                "volume": np.full(len(index), 50000.0),
            },
            index=index,
        )
    return bars


def _register_datasets(store: ExperimentStore, spec: ExperimentSpec) -> None:
    for dataset_id, symbol in zip(spec.dataset_ids, TRACK_SETUP[spec.track]["symbols"], strict=True):
        store.register_dataset(DatasetManifest(
            dataset_id=dataset_id,
            market=spec.market,
            provider="unit-test",
            source="synthetic-bars-not-market-data",
            instrument=symbol,
            exchange=TRACK_SETUP[spec.track]["exchange"],
            category="ohlcv",
            resolution=spec.resolution,
            coverage_start=min(
                NSE_WINDOWS["training"][0] if spec.market is Market.NSE else CRYPTO_WINDOWS["training"][0],
                datetime(2015, 1, 1, tzinfo=UTC) if spec.market is Market.NSE else datetime(2024, 12, 1, tzinfo=UTC),
            ),
            coverage_end=datetime(2026, 11, 9, tzinfo=UTC) if spec.market is Market.NSE else datetime(2025, 1, 1, 12, tzinfo=UTC),
            timezone="Asia/Kolkata" if spec.market is Market.NSE else "UTC",
            timestamp_convention="synthetic-bar-index",
            acquired_at=datetime(2026, 11, 8, tzinfo=UTC),
            update_frequency="daily" if spec.market is Market.NSE else "hourly",
            license_status=LicenseStatus.APPROVED,
            license_reference="synthetic-test-fixture-only",
            value_origin=ValueOrigin.OBSERVED,
            quality_score=1.0,
            processing_history=("generated inside unit test",),
        ))


def _run_track_job(store: ExperimentStore, spec: ExperimentSpec) -> dict[str, object]:
    """Execute the correct worker for one track through the job manager."""
    _register_datasets(store, spec)
    manager = ResearchJobManager(store, max_workers=1, max_queued=1)
    runner = ExistingStrategyJobRunner(
        bar_loader=lambda current_store, current_spec: _synthetic_bars(current_spec.track)
    )
    manager.register_runner("existing_strategy_evaluation", runner)
    try:
        job = manager.wait(manager.submit(spec.experiment_id, "existing_strategy_evaluation"), timeout=40)
        assert job["status"] == "succeeded", job["error_message"]
        return job["result"]
    finally:
        manager.shutdown(wait=True, cancel_pending=True)


@pytest.mark.parametrize("track", list(TRACK_SETUP), ids=lambda track: track.value)
def test_track_end_to_end(track: ResearchTrack, tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    """Spec -> worker -> F-001 OOS classification -> persistence, per track."""
    spec = _track_spec(track)
    store = ExperimentStore(tmp_path / f"{track.value}.sqlite3")
    store.create_experiment(spec)
    result = _run_track_job(store, spec)

    # 1. The immutable spec round-trips from the persisted record byte-for-byte.
    persisted = store.get_experiment(spec.experiment_id)
    restored = experiment_spec_from_record(persisted)
    assert restored.fingerprint == spec.fingerprint
    assert restored.market is spec.market and restored.track is spec.track

    # 2. Exactly one candidate was frozen through the correct worker path.
    candidates = store.candidates(spec.experiment_id)
    assert len(candidates) == 1
    assert candidates[0]["family"] == "existing_strategy"

    # 3. OOS was evaluated and classified under the approved F-001 policy.
    assert result["final_holdout_accessed"] is False
    assert result["oos_policy_version"] == "v1-2026-11-10"
    assert result["oos_acceptance"]["outcome"] in {"pass", "fail"}
    partitions = [item["partition"] for item in result["partitions"]]
    assert partitions == ["train", "validation", "out_of_sample"]
    # Every partition ran in this track's own market.
    partition_markets = {item["market"] for item in result["partitions"]}
    assert partition_markets == {spec.market.value}

    # 4. Results persisted: evaluation event, lifecycle state, environment record.
    events = store.events(spec.experiment_id)
    event_types = [event["event_type"] for event in events]
    assert "existing_strategy_evaluated" in event_types
    assert "environment_recorded" in event_types
    lifecycle_events = [
        event for event in events
        if event["event_type"].startswith("validation_lifecycle_")
    ]
    assert lifecycle_events, "validation lifecycle transitions must be persisted"
    lifecycle_states = [event["event_type"] for event in lifecycle_events]
    assert "validation_lifecycle_candidate_frozen" in lifecycle_states
    assert "validation_lifecycle_oos_recorded" in lifecycle_states

    # The report for this track is the printed persisted record contents.
    print(f"\n=== TRACK REPORT: {track.value} ===")
    print("experiment_id:", persisted["experiment_id"])
    print("market:", persisted["market"], "track:", persisted["track"])
    print("fingerprint:", persisted["fingerprint"])
    print("candidate_digest:", result["candidate_digest"])
    print("classification:", result["classification"])
    print("oos_acceptance:", result["oos_acceptance"])
    print("partitions:", [
        {"partition": item["partition"], "market": item["market"],
         "total_return": item["portfolio"]["total_return"]}
        for item in result["partitions"]
    ])
    print("final_holdout_accessed:", result["final_holdout_accessed"])
    print("environment_backend:", result["environment"]["compute_backend"])
    print("events:", event_types)


@pytest.mark.parametrize("track", list(TRACK_SETUP), ids=lambda track: track.value)
def test_track_cross_market_isolation(track: ResearchTrack) -> None:
    """Each track's ledger never touches the other market's capital."""
    other = Market.CRYPTO if spec_market(track) is Market.NSE else Market.NSE
    own_ledger = MarketLedger(spec_market(track))
    other_ledger = MarketLedger(other)
    own_before = own_ledger.cash_inr
    other_before = other_ledger.cash_inr
    # A fill from the other market must be rejected on this track's ledger.
    cross_fill = Fill(
        fill_id="cross-market-probe",
        market=other,
        instrument="PROBE",
        side=Side.BUY,
        quantity=Decimal("1"),
        price_inr=Decimal("100"),
        fee_inr=Decimal("0"),
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        cost_model_id="probe-cost-model",
    )
    with pytest.raises(ValueError, match="cross-market fill rejected"):
        own_ledger.apply_fill(cross_fill)
    assert own_ledger.cash_inr == own_before
    assert other_ledger.cash_inr == other_before
    # The markets' seed capital allocations are separate objects, both intact.
    assert own_before == other_before  # both start at 2,100,000.00 INR
    assert own_ledger is not other_ledger


def spec_market(track: ResearchTrack) -> Market:
    return ResearchTrack_track_market(track)


def test_nse_spec_rejects_crypto_dataset_reference(tmp_path) -> None:
    """An NSE experiment cannot validate against a crypto-registered catalog."""
    from research.platform.data_catalog import DataAvailabilityCatalog

    catalog_store_path = tmp_path
    nse_spec = _track_spec(ResearchTrack.NSE_INDIVIDUAL)
    crypto_spec = _track_spec(ResearchTrack.CRYPTO_INDIVIDUAL)
    crypto_store = ExperimentStore(catalog_store_path / "crypto.sqlite3")
    crypto_store.create_experiment(crypto_spec)
    _register_datasets(crypto_store, crypto_spec)

    class _StoreCatalog(DataAvailabilityCatalog):
        def get(self, dataset_id: str) -> DatasetManifest:
            manifest = crypto_store.get_dataset(dataset_id)["manifest"]
            # Stored manifests round-trip as JSON; restore the typed dataclass.
            return DatasetManifest(
                dataset_id=manifest["dataset_id"],
                market=Market(manifest["market"]),
                provider=manifest["provider"],
                source=manifest["source"],
                instrument=manifest["instrument"],
                exchange=manifest["exchange"],
                category=manifest["category"],
                resolution=DataResolution(manifest["resolution"]),
                coverage_start=datetime.fromisoformat(manifest["coverage_start"]),
                coverage_end=datetime.fromisoformat(manifest["coverage_end"]),
                timezone=manifest["timezone"],
                timestamp_convention=manifest["timestamp_convention"],
                acquired_at=datetime.fromisoformat(manifest["acquired_at"]),
                update_frequency=manifest["update_frequency"],
                license_status=LicenseStatus(manifest["license_status"]),
                license_reference=manifest["license_reference"],
                value_origin=ValueOrigin(manifest["value_origin"]),
                quality_score=manifest["quality_score"],
                processing_history=tuple(manifest["processing_history"]),
            )

    # Resolve the NSE spec's dataset ids against the crypto-only catalog: the
    # catalog must serve those ids from the crypto store, and the market check
    # in validate_datasets must then reject the crypto manifest.
    catalog = _StoreCatalog()
    crypto_ids = list(crypto_spec.dataset_ids)
    # Point the NSE spec at the crypto store's dataset ids via a derived spec.
    from dataclasses import replace as dataclass_replace

    cross_spec = dataclass_replace(nse_spec, dataset_ids=tuple(crypto_ids))
    with pytest.raises(ValueError, match="cross-market dataset rejected"):
        cross_spec.validate_datasets(catalog)


def test_negative_control_rejected_before_any_metric_is_produced(tmp_path) -> None:
    """Audit 7.22: the tests must include negative results.

    A spec naming an unregistered strategy must fail loudly; no metrics,
    candidate or evaluation event may exist afterwards.
    """
    spec = _track_spec(ResearchTrack.NSE_PORTFOLIO, negative=True)
    store = ExperimentStore(str(tmp_path / "negative.sqlite3"))
    store.create_experiment(spec)
    _register_datasets(store, spec)
    manager = ResearchJobManager(store, max_workers=1, max_queued=1)
    runner = ExistingStrategyJobRunner(
        bar_loader=lambda current_store, current_spec: _synthetic_bars(current_spec.track)
    )
    manager.register_runner("existing_strategy_evaluation", runner)
    try:
        job = manager.wait(manager.submit(spec.experiment_id, "existing_strategy_evaluation"), timeout=40)
        assert job["status"] == "failed"
        assert "unknown existing strategy" in job["error_message"]
        # No candidate was frozen and no evaluation event was persisted.
        assert store.candidates(spec.experiment_id) == ()
        event_types = [event["event_type"] for event in store.events(spec.experiment_id)]
        assert "existing_strategy_evaluated" not in event_types
    finally:
        manager.shutdown(wait=True, cancel_pending=True)
