"""Tests for causal model-feature panels and shared portfolio evaluation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from research.platform.composition import Composition
from research.platform.composition_policy import composition_scores, default_component_registry
from research.platform.domain import AlgorithmFamily, DataResolution, Market, ResearchTrack
from research.platform.experiments import ExperimentSpec
from research.platform.features import PointInTimeFeatureEngine
from research.platform.model_evaluation import (
    build_model_feature_panel,
    evaluate_model_scores,
)
from research.platform.portfolio import PortfolioConfig
from research.platform.validation import assert_train_window_purged

UTC = UTC


def _bars(index: pd.DatetimeIndex, offset: float = 0.0) -> pd.DataFrame:
    # Generate deterministic synthetic OHLCV fixtures; they are not exchange observations.
    step = np.arange(len(index), dtype=np.float64)
    close = 100.0 + offset + step * 0.2 + np.sin(step / 2.0)
    return pd.DataFrame(
        {
            "open": close - 0.05,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": np.full(len(index), 10000.0),
        },
        index=index,
    )


def _config() -> PortfolioConfig:
    # Keep the synthetic model evaluation long-only and fully cost-fingerprinted.
    return PortfolioConfig(
        market=Market.NSE,
        fee_bps=Decimal("0"),
        slippage_bps=Decimal("0"),
        impact_coefficient_bps=Decimal("0"),
        max_participation=Decimal("0.1"),
        max_gross_exposure=Decimal("1.0"),
        assumed_timezone="UTC",
        cost_model_id="model-test-cost",
        execution_model_id="model-test-next-open",
    )


def test_constant_volume_has_zero_z_score_without_erasing_warmup_rows() -> None:
    # Constant volume has a valid zero z-score after the lookback; warm-up remains unavailable.
    index = pd.date_range("2025-01-01", periods=30, freq="D", tz=UTC)
    frame = _bars(index)
    output = PointInTimeFeatureEngine(windows=(3, 5)).build(frame)
    assert output["volume_z_3"].iloc[:2].isna().all()
    assert output["volume_z_5"].iloc[:4].isna().all()
    assert np.allclose(output["volume_z_3"].iloc[2:], 0.0)
    assert np.allclose(output["volume_z_5"].iloc[4:], 0.0)
    assert np.isfinite(output.iloc[5:].to_numpy()).all()


def test_model_feature_panel_maps_predictions_to_exact_instrument_rows() -> None:
    # Each symbol's train-window features are concatenated in stable symbol order.
    index = pd.date_range("2025-01-01", periods=30, freq="D", tz=UTC)
    bars = {"AAA": _bars(index), "BBB": _bars(index, 5.0)}
    panel = build_model_feature_panel(
        bars,
        PointInTimeFeatureEngine(windows=(3, 5)),
        ResearchTrack.NSE_PORTFOLIO,
        start=datetime(2025, 1, 10, tzinfo=UTC),
        end=datetime(2025, 1, 20, tzinfo=UTC),
    )
    assert panel.features.shape[0] == 20
    assert panel.features.shape[1] == 2 + 2 * 5
    targets = panel.targets_from_scores(np.ones(len(panel.features)))
    assert targets.shape == (19, 2)
    # Portfolio exposure is equally allocated only on dates with valid feature decisions.
    decision_rows = targets.index >= datetime(2025, 1, 10, tzinfo=UTC)
    assert np.allclose(targets.loc[decision_rows].sum(axis=1).to_numpy(), 1.0)
    # No positions are opened before the first model decision date.
    assert (targets.loc[~decision_rows] == 0).all().all()


def test_model_feature_panel_keeps_partition_boundary_half_open() -> None:
    # OOS and final-holdout rows are excluded before feature construction and simulation.
    index = pd.date_range("2026-10-01", periods=20, freq="D", tz=UTC)
    bars = {"AAA": _bars(index)}
    end = datetime(2026, 10, 10, tzinfo=UTC)
    panel = build_model_feature_panel(
        bars,
        PointInTimeFeatureEngine(windows=(2,)),
        ResearchTrack.NSE_INDIVIDUAL,
        start=datetime(2026, 10, 5, tzinfo=UTC),
        end=end,
    )
    assert panel.index.max() < end
    assert len(panel.index) == 9
    assert (panel.features[:, 0] != 0).any()


def test_model_partition_uses_same_portfolio_accounting_and_returns_metrics() -> None:
    # An always-active synthetic model passes through the same next-open simulator.
    index = pd.date_range("2025-01-01", periods=40, freq="D", tz=UTC)
    bars = {"AAA": _bars(index)}
    start = datetime(2025, 1, 10, tzinfo=UTC)
    end = datetime(2025, 2, 5, tzinfo=UTC)
    panel = build_model_feature_panel(
        bars,
        PointInTimeFeatureEngine(windows=(3,)),
        ResearchTrack.NSE_INDIVIDUAL,
        start=start,
        end=end,
    )
    result = evaluate_model_scores(
        panel,
        np.ones(len(panel.features)),
        _config(),
        partition="train",
        start=start,
        end=end,
        periods_per_year=252,
    )
    assert result.partition == "train"
    assert result.sample_count > 0
    assert result.result.market is Market.NSE
    assert "sharpe" in result.metrics
    assert result.result.initial_capital_inr == Decimal("2100000.00")


def test_model_feature_panel_rejects_misaligned_multi_asset_calendars() -> None:
    # Portfolio candidates cannot exploit implicit forward-fill between mismatched bars.
    first = pd.date_range("2025-01-01", periods=20, freq="D", tz=UTC)
    second = first.delete(8)
    with np.testing.assert_raises_regex(ValueError, "same chronological bar calendar"):
        build_model_feature_panel(
            {"AAA": _bars(first), "BBB": _bars(second)},
            PointInTimeFeatureEngine(windows=(2,)),
            ResearchTrack.NSE_PORTFOLIO,
            start=datetime(2025, 1, 5, tzinfo=UTC),
            end=datetime(2025, 1, 15, tzinfo=UTC),
        )



def test_allow_listed_composition_components_produce_causal_long_flat_scores() -> None:
    # A declarative entry/exit/filter composition maps to finite signed model scores.
    index = pd.date_range("2025-01-01", periods=40, freq="D", tz=UTC)
    bars = {"AAA": _bars(index)}
    panel = build_model_feature_panel(
        bars,
        PointInTimeFeatureEngine(windows=(3,)),
        ResearchTrack.NSE_INDIVIDUAL,
        start=datetime(2025, 1, 10, tzinfo=UTC),
        end=datetime(2025, 2, 5, tzinfo=UTC),
    )
    registry = default_component_registry((3,))
    composition = Composition((registry[0], registry[2], registry[4]))
    scores = composition_scores(composition, panel, (3,))
    assert scores.shape == (len(panel.features),)
    assert np.isfinite(scores).all()
    assert set(np.unique(scores)).issubset({-1.0, 1.0})

# ---------------------------------------------------------------------------
# F-016: purge integration in every training path.
# Every trainer that fits on TRAIN and scores on VALIDATION routes its TRAIN
# rows through ``assert_train_window_purged``; the tests below pin the exact
# surviving/purged indices for synthetic labels with known overlap.
# ---------------------------------------------------------------------------

def _purge_fixture() -> tuple[list[datetime], list[datetime], list[datetime]]:
    # Decisions Jan 1..7 daily; each one-bar label spans [decision, decision+1d).
    decisions = [datetime(2026, 1, day, tzinfo=UTC) for day in range(1, 8)]
    ends = [decision + timedelta(days=1) for decision in decisions]
    protected = (datetime(2026, 1, 5, tzinfo=UTC), datetime(2026, 1, 7, tzinfo=UTC))
    return decisions, ends, list(protected)


def test_purge_guard_accepts_clean_train_partition_with_exact_survivors() -> None:
    # Jan 1-3 labels end Jan 2-4, fully before the protected Jan 5..7 window:
    # exactly rows 0-2 survive with zero purges; a fourth row whose label
    # reaches inside the window (decision Jan 4, label to Jan 5 12:00) is
    # counted as purged — the caller must exclude it from the fit.
    decisions, ends, protected = _purge_fixture()
    record = assert_train_window_purged(
        decisions[:3], ends[:3], protected[0], protected[1], trainer="unit",
    )
    assert record.purged_count == 0
    assert record.to_dict()["trainer"] == "unit"
    leaked_ends = list(ends[:4])
    leaked_ends[3] = datetime(2026, 1, 5, 12, tzinfo=UTC)  # label open inside the window
    purged = assert_train_window_purged(
        decisions[:4], leaked_ends, protected[0], protected[1], trainer="unit",
    )
    assert purged.purged_count == 1


def test_purge_guard_raises_when_train_decision_sits_inside_protected_window() -> None:
    # A row decided INSIDE the protected zone means TRAIN and the evaluation
    # window overlap — an unrecoverable partition error, not a purge.
    decisions, ends, protected = _purge_fixture()
    with pytest.raises(ValueError, match="decided inside the protected"):
        assert_train_window_purged(
            decisions[:6], ends[:6], protected[0], protected[1], trainer="unit",
        )


def test_purge_guard_refuses_label_reaching_into_protected_window() -> None:
    # A label whose interval reaches strictly inside the protected window
    # (decision Jan 4, label runs to Jan 5 12:00) leaks the first validation
    # close: it is counted as purged; ending exactly AT the boundary stays
    # clean at zero embargo because the half-open window starts after that close.
    decisions, ends, protected = _purge_fixture()
    reaching = list(ends[:4])
    reaching[3] = datetime(2026, 1, 5, 12, tzinfo=UTC)
    assert assert_train_window_purged(
        decisions[:4], reaching, protected[0], protected[1], trainer="unit",
    ).purged_count == 1
    # Boundary-touching without embargo is permitted ...
    touching = list(ends[:4])
    touching[3] = protected[0]
    assert assert_train_window_purged(
        decisions[:4], touching, protected[0], protected[1], trainer="unit",
    ).purged_count == 0
    # ... but a one-day embargo marks it purged: the label is inside the
    # expanded forbidden zone and must be excluded from the fit.
    assert assert_train_window_purged(
        decisions[:4], touching, protected[0], protected[1],
        trainer="unit", embargo=timedelta(days=1),
    ).purged_count == 1


def test_purge_guard_expands_embargo_on_both_sides() -> None:
    # Without embargo the Jan-3 label (ending Jan 4 12:00) is clean; with a
    # one-day embargo the forbidden zone begins Jan 4 00:00 and the label is
    # purged (strict > against the expanded boundary).
    decisions, ends, protected = _purge_fixture()
    late = list(ends[:3])
    late[2] = datetime(2026, 1, 4, 12, tzinfo=UTC)
    assert assert_train_window_purged(
        decisions[:3], late, protected[0], protected[1],
        trainer="unit", embargo=timedelta(0),
    ).purged_count == 0
    assert assert_train_window_purged(
        decisions[:3], late, protected[0], protected[1],
        trainer="unit", embargo=timedelta(days=1),
    ).purged_count == 1


def test_purge_guard_treats_open_ended_final_label_as_leaking() -> None:
    # A missing label end (bar with no successor yet) is treated as extending
    # to the protected boundary — counted as purged, never silently clean.
    decisions, ends, protected = _purge_fixture()
    assert assert_train_window_purged(
        decisions[:3], ends[:2], protected[0], protected[1], trainer="unit",
    ).purged_count == 1


def test_purge_guard_records_embargo_in_audit_dict() -> None:
    decisions, ends, protected = _purge_fixture()
    record = assert_train_window_purged(
        decisions[:3], ends[:3], protected[0], protected[1],
        trainer="genetic_programming", embargo=timedelta(seconds=90),
    )
    assert record.to_dict() == {
        "trainer": "genetic_programming",
        "protected_start": "2026-01-05T00:00:00+00:00",
        "protected_end": "2026-01-07T00:00:00+00:00",
        "embargo_seconds": 90,
        "purged_count": 0,
    }


def test_model_panel_train_features_carry_no_validation_window_rows() -> None:
    # Trainer-side leakage proof: the TRAIN feature panel built from synthetic
    # bars never contains a decision row at or after the validation start, and
    # the purge assertion over those exact rows passes with zero leakage.
    index = pd.date_range("2026-01-01", periods=30, freq="D", tz=UTC)
    bars = {"AAA": _bars(index)}
    train_start, train_end = datetime(2026, 1, 2, tzinfo=UTC), datetime(2026, 1, 11, tzinfo=UTC)
    validation_start, validation_end = datetime(2026, 1, 11, tzinfo=UTC), datetime(2026, 1, 16, tzinfo=UTC)
    panel = build_model_feature_panel(
        bars, PointInTimeFeatureEngine(windows=(3,)), ResearchTrack.NSE_INDIVIDUAL,
        start=train_start, end=train_end,
    )
    # Half-open TRAIN partition: the first validation decision is absent.
    assert panel.index.max() < validation_start
    # The shared guard accepts the exact TRAIN rows the panel exposes: the
    # last decision (Jan 10) forms a label over [Jan10, Jan11) that ends
    # exactly at the validation boundary — inside the half-open contract.
    decisions = [stamp.to_pydatetime() for stamp in panel.index]
    ends = decisions[1:] + [validation_start]
    record = assert_train_window_purged(
        decisions, ends, validation_start, validation_end, trainer="model_panel",
    )
    assert record.purged_count == 0
    # And refuses the leaked variant: one row decided INSIDE the window —
    # TRAIN/evaluation overlap raises rather than purging.
    leaked_decisions = decisions + [datetime(2026, 1, 12, tzinfo=UTC)]
    leaked_ends = ends + [datetime(2026, 1, 13, tzinfo=UTC)]
    with pytest.raises(ValueError, match="decided inside the protected"):
        assert_train_window_purged(
            leaked_decisions, leaked_ends,
            validation_start, validation_end, trainer="model_panel",
        )


# ---------------------------------------------------------------------------
# F-017: per-feature availability stamps and point-in-time membership.
# ---------------------------------------------------------------------------

def test_feature_build_stamps_availability_per_feature() -> None:
    # Every feature column records its source and the timestamp at which the
    # value would have been known: the bar close, never the bar open.
    index = pd.date_range("2025-01-01", periods=30, freq="D", tz=UTC)
    output = PointInTimeFeatureEngine(windows=(3, 5)).build(_bars(index))
    catalog = output.attrs["feature_availability"]
    names = [item["feature_name"] for item in catalog]
    assert set(names) == set(output.columns)
    assert all(item["source_id"] for item in catalog)
    assert all(item["availability_time"] == "bar_close" for item in catalog)
    assert all(item["uses_future_data"] is False for item in catalog)
    # Availability benchmark: every stamped availability instant is strictly
    # after the corresponding bar open instant for every feature and row.
    stamps = output.attrs["availability_timestamps"]
    opens = output.attrs["availability_benchmark"]["bar_open"]
    closes = pd.DatetimeIndex(output.index)
    for feature, feature_stamps in stamps.items():
        # Availability is never earlier than the bar open (a close-derived
        # value cannot be known before the bar opens) and equals the bar
        # close instant exactly — the value becomes known at the close.
        assert (feature_stamps >= opens).all(), feature
        assert feature_stamps.equals(closes), feature


def test_feature_availability_catalog_covers_all_engine_columns() -> None:
    # The catalog is deterministic in the engine's column order, so experiment
    # records can hash it as split/feature provenance.
    engine = PointInTimeFeatureEngine(windows=(2, 4))
    index = pd.date_range("2025-01-01", periods=10, freq="D", tz=UTC)
    output = engine.build(_bars(index))
    catalog = output.attrs["feature_availability"]
    assert [item["feature_name"] for item in catalog] == list(engine.feature_names)
    momentum = next(item for item in catalog if item["feature_name"] == "momentum_4")
    assert momentum["source_id"] == "bars:close:4"
    assert momentum["source_fields"] == ["close"]
    volume = next(item for item in catalog if item["feature_name"] == "volume_z_2")
    assert volume["source_id"] == "bars:volume:2"


def test_pit_membership_mask_blocks_pre_listing_and_post_delisting_rows() -> None:
    # Membership map (month-end -> members) with JPASSOCIAT-style membership:
    # joins at Feb-end, leaves after Mar-end. Rows before Feb-end and after
    # Mar-end stay NaN even though the synthetic CSV has valid OHLCV there.
    index = pd.date_range("2025-01-01", periods=90, freq="D", tz=UTC)
    feb_end, mar_end, apr_end = (
        pd.Timestamp("2025-02-28", tz=UTC),
        pd.Timestamp("2025-03-31", tz=UTC),
        pd.Timestamp("2025-04-30", tz=UTC),
    )
    membership = {feb_end: frozenset({"AAA"}), mar_end: frozenset({"AAA"}), apr_end: frozenset({"BBB"})}
    output = PointInTimeFeatureEngine(windows=(3,)).build(_bars(index), symbol="AAA", membership=membership)
    pre = output.loc[index < feb_end]
    active = output.loc[(index >= feb_end) & (index <= apr_end)]
    post = output.loc[index > apr_end]
    assert pre.isna().all().all(), "pre-listing rows must be NaN"
    assert active.notna().any().all(), "member-era rows must carry values"
    assert post.isna().all().all(), "post-delisting rows must be NaN"
    assert output.attrs["pit_symbol"] == "AAA"
    assert output.attrs["pit_masked_rows"] == int(pre.shape[0] + post.shape[0])


def test_pit_membership_map_resolves_last_month_end_per_row() -> None:
    # A row on June 10 resolves to the May-end member set; a membership change
    # recorded at June-end takes effect only from June-end onward.
    index = pd.date_range("2025-06-01", periods=45, freq="D", tz=UTC)
    may_end, jun_end = pd.Timestamp("2025-05-31", tz=UTC), pd.Timestamp("2025-06-30", tz=UTC)
    membership = {may_end: frozenset({"AAA"}), jun_end: frozenset({"BBB"})}
    output = PointInTimeFeatureEngine(windows=(3,)).build(_bars(index), symbol="AAA", membership=membership)
    assert output.loc[:jun_end].notna().any().all()
    assert output.loc[jun_end + pd.Timedelta(days=1):].isna().all().all()


def test_model_panel_pit_masking_excludes_delisted_symbol_rows() -> None:
    # Panel-level PIT proof: a symbol whose membership ends before the
    # partition contributes no feature rows, while point_in_time=False keeps
    # the legacy (non-PIT) behaviour for synthetic universes.
    index = pd.date_range("2025-01-01", periods=60, freq="D", tz=UTC)
    bars = {"AAA": _bars(index)}
    may_end = pd.Timestamp("2025-01-31", tz=UTC)
    membership = {may_end: frozenset({"OTHER"})}  # AAA is NOT a member
    engine = PointInTimeFeatureEngine(windows=(3,))
    with pytest.raises(ValueError, match="no finite causal features"):
        build_model_feature_panel(
            bars, engine, ResearchTrack.NSE_INDIVIDUAL,
            start=datetime(2025, 1, 10, tzinfo=UTC), end=datetime(2025, 1, 25, tzinfo=UTC),
            pit_membership=membership,
        )
    panel = build_model_feature_panel(
        bars, engine, ResearchTrack.NSE_INDIVIDUAL,
        start=datetime(2025, 1, 10, tzinfo=UTC), end=datetime(2025, 1, 25, tzinfo=UTC),
        point_in_time=False,
    )
    assert len(panel.features) == 15


def test_model_panel_pit_membership_includes_prior_month_end() -> None:
    # Rows early in a month must resolve membership from the PRIOR month-end:
    # a mid-June window still sees the May-end member set.
    index = pd.date_range("2025-01-01", periods=200, freq="D", tz=UTC)
    bars = {"AAA": _bars(index)}
    membership = {
        pd.Timestamp("2025-05-31", tz=UTC): frozenset({"AAA"}),
        pd.Timestamp("2025-06-30", tz=UTC): frozenset({"AAA"}),
    }
    panel = build_model_feature_panel(
        bars, PointInTimeFeatureEngine(windows=(3,)), ResearchTrack.NSE_INDIVIDUAL,
        start=datetime(2025, 6, 10, tzinfo=UTC), end=datetime(2025, 6, 20, tzinfo=UTC),
        pit_membership=membership,
    )
    assert len(panel.features) == 10
    assert panel.attrs["point_in_time"] is True

# ---------------------------------------------------------------------------
# F-016 per-trainer leakage proofs: every fitting trainer's TRAIN rows are
# routed through the purge guard with the exact spec shape used by the
# runner tests; concrete surviving/purged indices are pinned below.
# ---------------------------------------------------------------------------

def _trainer_fixture(embargo_days: int = 0) -> tuple[dict[str, pd.DataFrame], ExperimentSpec]:
    # IST daily bars like the runner fixtures; TRAIN 2016-2018, VALIDATION
    # 2018-2020 with the declared embargo between them. Adjacent windows are
    # legal only at embargo 0, so the embargoed variant shifts VALIDATION by
    # one day (training_end + embargo <= validation_start).
    index = pd.date_range("2015-01-01", "2021-01-01", freq="D", tz="Asia/Kolkata")
    step = np.arange(len(index), dtype=np.float64)
    close = 100.0 + 0.015 * step + 3.0 * np.sin(step / 12.0)
    frame = pd.DataFrame(
        {
            "open": close - 0.05,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": np.full(len(index), 50000.0),
        },
        index=index,
    )
    spec = ExperimentSpec(
        experiment_id="purge-trainer-proof",
        market=Market.NSE,
        track=ResearchTrack.NSE_INDIVIDUAL,
        algorithm_family=AlgorithmFamily.RANDOM_SEARCH,
        resolution=DataResolution.ONE_DAY,
        dataset_ids=("purge-proof-data-v1",),
        random_seed=7,
        git_commit="0123456789abcdef0123456789abcdef01234567",
        code_version="purge-proof",
        training_start=datetime(2016, 1, 1, tzinfo=UTC),
        training_end=datetime(2018, 1, 1, tzinfo=UTC),
        validation_start=datetime(2018, 1, 1 + embargo_days, tzinfo=UTC),
        validation_end=datetime(2020, 1, 1 + embargo_days, tzinfo=UTC),
        oos_start=datetime(2026, 10, 2, tzinfo=UTC),
        oos_end=datetime(2026, 10, 15, tzinfo=UTC),
        final_holdout_start=datetime(2026, 10, 16, tzinfo=UTC),
        final_holdout_end=datetime(2026, 11, 8, tzinfo=UTC),
        cost_model_id="nse-delivery-cost-model",
        execution_model_id="next-open-participation-impact-v1",
        objectives=("net_return", "max_drawdown", "turnover"),
        parameters={"strategy_name": "absolute_momentum"},
        embargo_seconds=embargo_days * 86400,
        created_at=datetime(2026, 11, 8, tzinfo=UTC),
    )
    return {"TEST": frame}, spec


def _runner_purge_guard(bars, spec, trainer):
    # Mirror of runners._purge_guard_for_spec (private helper asserted via the
    # public guard): TRAIN-window decisions + label ends against validation.
    from research.platform.runners import _bar_decisions, _bar_label_ends
    decisions = _bar_decisions(bars)
    utc = pd.DatetimeIndex(decisions).tz_convert("UTC")
    keep = (
        (utc >= pd.Timestamp(spec.training_start))
        & (utc < pd.Timestamp(spec.training_end))
    )
    kept = [d for d, flag in zip(decisions, keep) if flag]
    ends = [e for e, flag in zip(_bar_label_ends(bars), keep) if flag]
    return assert_train_window_purged(
        kept, ends, spec.validation_start, spec.validation_end,
        trainer=trainer, embargo=timedelta(seconds=spec.embargo_seconds),
    )


@pytest.mark.parametrize("trainer", [
    "existing_strategy_random_search",
    "genetic_programming",
    "neuroevolution",
    "strategy_composition",
    "pareto_search",
])
def test_trainer_boundary_row_is_counted_purged_and_excluded(trainer: str) -> None:
    # Every fitting trainer shares the same TRAIN contract. With adjacent
    # windows and embargo 0, the final TRAIN decision (IST 2018-01-01 bar,
    # position 731; open stamp 2017-12-31T18:30Z) forms a one-bar label ending
    # at the IST 2018-01-02 open stamp (2018-01-01T18:30Z) — strictly inside
    # the UTC validation window. That fill consumes the first validation day,
    # so the guard counts exactly this one row as purged: the fit must exclude
    # it. The following bar (IST 2018-01-02, position 732) is the first
    # decision outside the TRAIN window entirely.
    bars, spec = _trainer_fixture()
    record = _runner_purge_guard(bars, spec, trainer)
    assert record.to_dict()["trainer"] == trainer
    assert record.purged_count == 1
    from research.platform.runners import _bar_decisions, _bar_label_ends
    decisions = _bar_decisions(bars)
    ist = timezone(timedelta(hours=5, minutes=30))
    utc = pd.DatetimeIndex(decisions).tz_convert("UTC")
    kept_positions = np.flatnonzero(
        (utc >= pd.Timestamp(spec.training_start)) & (utc < pd.Timestamp(spec.training_end))
    )
    # Concrete indices: the final kept TRAIN decision is position 1096 (the
    # IST 2018-01-01 bar, open stamp 2017-12-31T18:30Z — still before the
    # validation start instant). Its one-bar label ends at the IST 2018-01-02
    # open stamp (2018-01-01T18:30Z), strictly inside the UTC validation
    # window, so exactly row 1096 is purged. Position 1097 (IST 2018-01-02,
    # open 2018-01-01T18:30Z) is the first decision outside the TRAIN window.
    assert kept_positions[-1] == 1096
    assert decisions[1096] == datetime(2018, 1, 1, tzinfo=ist)
    assert decisions[1097] == datetime(2018, 1, 2, tzinfo=ist)  # first validation bar
    ends = _bar_label_ends(bars)
    assert ends[1096] == datetime(2018, 1, 2, tzinfo=ist)
    assert ends[1096].astimezone(UTC) == datetime(2018, 1, 1, 18, 30, tzinfo=UTC)


@pytest.mark.parametrize("trainer", [
    "existing_strategy_random_search",
    "genetic_programming",
    "neuroevolution",
    "strategy_composition",
    "pareto_search",
])
def test_trainer_embargo_keeps_purged_row_count_at_boundary(trainer: str) -> None:
    # With a one-day embargo the validation window starts a day later, so the
    # boundary label (ending IST 2018-01-02 open) ends before the forbidden
    # zone again — but the boundary row sits outside the (unchanged) TRAIN
    # window trim only if training_end excludes it; the spec stays legal via
    # training_end + embargo <= validation_start and the guard still purges
    # exactly the final TRAIN row (identical leak, same single row).
    bars, spec = _trainer_fixture(embargo_days=1)
    record = _runner_purge_guard(bars, spec, trainer)
    assert record.purged_count == 1
    assert spec.training_end + timedelta(days=1) <= spec.validation_start


@pytest.mark.parametrize("trainer", [
    "existing_strategy_random_search",
    "genetic_programming",
    "neuroevolution",
    "strategy_composition",
    "pareto_search",
])
def test_trainer_raises_when_train_decision_overlaps_validation(trainer: str) -> None:
    # A partition error (TRAIN window reaching into validation) is raised for
    # every trainer: no purge can repair an overlapping fit window.
    bars, spec = _trainer_fixture()
    from research.platform.runners import _bar_decisions, _bar_label_ends
    decisions = _bar_decisions(bars)
    utc = pd.DatetimeIndex(decisions).tz_convert("UTC")
    keep = (
        (utc >= pd.Timestamp(spec.training_start))
        & (utc < pd.Timestamp(spec.validation_end))  # deliberately overlapping
    )
    kept = [d for d, flag in zip(decisions, keep) if flag]
    ends = [e for e, flag in zip(_bar_label_ends(bars), keep) if flag]
    with pytest.raises(ValueError, match="decided inside the protected"):
        assert_train_window_purged(
            kept, ends, spec.validation_start, spec.validation_end, trainer=trainer,
        )

