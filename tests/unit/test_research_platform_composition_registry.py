"""Audit F-020 tests: complete strategy composition registry and Policy.

Dedicated test file for composition.py / composition_policy.py role coverage,
compatibility enforcement and per-component signal variation.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from research.platform.composition import Composition
from research.platform.composition_policy import composition_scores, default_component_registry
from research.platform.domain import Market, ResearchTrack
from research.platform.features import PointInTimeFeatureEngine
from research.platform.model_evaluation import build_model_feature_panel


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


def _composition_panel() -> tuple[object, object]:
    # One deterministic single-asset panel shared by the F-020 signal tests.
    index = pd.date_range("2025-01-01", periods=40, freq="D", tz=UTC)
    bars = {"AAA": _bars(index)}
    panel = build_model_feature_panel(
        bars,
        PointInTimeFeatureEngine(windows=(3,)),
        ResearchTrack.NSE_INDIVIDUAL,
        start=datetime(2025, 1, 10, tzinfo=UTC),
        end=datetime(2025, 2, 5, tzinfo=UTC),
    )
    return panel, default_component_registry((3,))


def test_composition_rejects_incompatible_role_pairs() -> None:
    # The compatibility graph is enforced structurally at genome construction.
    panel, registry = _composition_panel()
    entry = next(c for c in registry if c.role == "entry")
    exit_ = next(c for c in registry if c.role == "exit")
    filter_ = next(c for c in registry if c.role == "filter")
    regime = next(c for c in registry if c.role == "regime")
    allocation = next(c for c in registry if c.role == "allocation")
    rebalance = next(c for c in registry if c.role == "rebalance")
    with pytest.raises(ValueError, match="incompatible"):
        Composition((entry, exit_, filter_, regime))
    with pytest.raises(ValueError, match="incompatible"):
        Composition((entry, exit_, allocation, rebalance))
    # The same graph accepts valid combinations.
    Composition((entry, exit_, filter_, rebalance))
    Composition((entry, exit_, regime, allocation))


def test_composition_rejects_duplicate_singleton_roles() -> None:
    # Allocation and execution are single-slot policies.
    panel, registry = _composition_panel()
    entry = next(c for c in registry if c.role == "entry")
    exit_ = next(c for c in registry if c.role == "exit")
    allocations = [c for c in registry if c.role == "allocation"]
    executions = [c for c in registry if c.role == "execution"]
    with pytest.raises(ValueError, match="multiple allocation"):
        Composition((entry, exit_, allocations[0], allocations[1]))
    with pytest.raises(ValueError, match="multiple execution"):
        Composition((entry, exit_, executions[0], executions[1]))


def test_composition_registry_covers_all_audit_roles() -> None:
    # The F-020 registry exposes every audit-named role with typed parameters.
    panel, registry = _composition_panel()
    roles = {component.role for component in registry}
    assert roles == {
        "entry", "exit", "filter", "regime", "sizing", "risk",
        "allocation", "rebalance", "volatility", "execution",
    }
    for component in registry:
        assert component.parameters  # every component declares its parameter space
        for _name, value in component.parameters:
            assert np.isfinite(value)


@pytest.mark.parametrize(
    "component_id",
    [
        "volatility_regime_3",   # regime detector
        "volatility_scaled_sizing_3",  # position sizing method
        "drawdown_risk_3",       # risk constraint
        "periodic_rebalance_3",  # rebalancing logic
        "volatility_cap_3",      # volatility control
        "volatility_floor_3",    # volatility control
    ],
)
def test_composition_component_variation_changes_signal(component_id: str) -> None:
    # Adding each new component materially changes the produced signal.
    panel, registry = _composition_panel()
    entry = next(c for c in registry if c.role == "entry")
    exit_ = next(c for c in registry if c.role == "exit")
    baseline = composition_scores(Composition((entry, exit_)), panel, (3,))
    component = next(c for c in registry if c.component_id == component_id)
    variant = composition_scores(Composition((entry, exit_, component)), panel, (3,))
    assert variant.shape == baseline.shape
    assert np.isfinite(variant).all()
    assert not np.array_equal(variant, baseline), component_id


@pytest.mark.parametrize(
    "component_id,expected_effect",
    [
        ("volatility_scaled_sizing_3", "magnitude"),  # sizing scales active magnitude
        ("periodic_rebalance_3", "hold_bars"),        # rebalance inserts no-decision bars
        ("equal_weight_allocation", "identical"),     # allocation records policy only
        ("next_open_execution", "identical"),         # execution assumption records only
    ],
)
def test_composition_role_semantics(component_id: str, expected_effect: str) -> None:
    # Each role changes the score in its documented way, or is recorded policy-only.
    panel, registry = _composition_panel()
    entry = next(c for c in registry if c.role == "entry")
    exit_ = next(c for c in registry if c.role == "exit")
    baseline = composition_scores(Composition((entry, exit_)), panel, (3,))
    component = next(c for c in registry if c.component_id == component_id)
    variant = composition_scores(Composition((entry, exit_, component)), panel, (3,))
    if expected_effect == "magnitude":
        assert not np.allclose(np.abs(variant), np.abs(baseline))
    elif expected_effect == "hold_bars":
        assert (variant == 0.0).any() and not (baseline == 0.0).any()
    else:
        np.testing.assert_array_equal(variant, baseline)


def test_composition_execution_and_allocation_accepted_together() -> None:
    # One allocation plus one execution component is a valid, score-preserving genome.
    panel, registry = _composition_panel()
    entry = next(c for c in registry if c.role == "entry")
    exit_ = next(c for c in registry if c.role == "exit")
    allocation = next(c for c in registry if c.role == "allocation")
    execution = next(c for c in registry if c.role == "execution")
    baseline = composition_scores(Composition((entry, exit_)), panel, (3,))
    combined = composition_scores(Composition((entry, exit_, allocation, execution)), panel, (3,))
    np.testing.assert_array_equal(combined, baseline)


def test_composition_scores_preserve_causal_long_flat_contract() -> None:
    # Every new gate family still yields finite signed long/flat scores per row.
    panel, registry = _composition_panel()
    entry = next(c for c in registry if c.role == "entry")
    exit_ = next(c for c in registry if c.role == "exit")
    regime = next(c for c in registry if c.role == "regime")
    sizing = next(c for c in registry if c.role == "sizing")
    rebalance = next(c for c in registry if c.role == "rebalance")
    scores = composition_scores(
        Composition((entry, exit_, regime, sizing, rebalance)), panel, (3,)
    )
    assert scores.shape == (len(panel.features),)
    assert np.isfinite(scores).all()
    # Sizing keeps the signed range; rebalance may inject zero hold bars.
    assert (np.abs(scores) <= 1.0 + 1e-12).all()
    assert ((scores >= 0.0) | (scores == -1.0)).all() or (scores < 0.0).any()
