"""Tests for causal model-feature panels and shared portfolio evaluation."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import numpy as np
import pandas as pd

from research.platform.domain import Market, ResearchTrack
from research.platform.features import PointInTimeFeatureEngine
from research.platform.model_evaluation import (
    build_model_feature_panel,
    evaluate_model_scores,
)
from research.platform.composition import Composition
from research.platform.composition_policy import composition_scores, default_component_registry
from research.platform.portfolio import PortfolioConfig


UTC = timezone.utc


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
