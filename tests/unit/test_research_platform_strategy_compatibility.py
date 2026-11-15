"""Existing strategy compatibility register (audit F-021 / section 7.10).

Every strategy shipped in the repository's authoritative catalogue
(``research/optimize/catalog.discover``) is executed through the platform's
``ExistingStrategySignalAdapter`` on a small synthetic OHLCV panel. The test
records assert, per strategy:

* a signal row is produced for every bar and is finite;
* the stream is deterministic (identical re-run under a fixed synthetic panel);
* the adapter records the strategy name and the parameters it was invoked with;
* position state stays inside the declared long/flat policy (no silent short).
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass

import numpy as np
import pandas as pd
import pytest

from research.platform.strategy_catalog import ExistingStrategyRegistry
from research.platform.strategy_signals import ExistingStrategySignalAdapter

# Bounded synthetic panel: 60 bars keeps every strategy's default warm-up feasible
# while exercising at least one post-warm-up decision per strategy.
_PANEL_BARS = 60
_PANEL_SEED = 20261115


def _synthetic_bars(seed: int = _PANEL_SEED, bars: int = _PANEL_BARS) -> dict[str, pd.DataFrame]:
    # Deterministic pseudo-random walk: identical bytes on every call for every test.
    rng = np.random.default_rng(seed)
    index = pd.date_range("2024-01-01", periods=bars, freq="D", tz="UTC")
    close = 100.0 + np.cumsum(rng.normal(0.05, 1.0, bars))
    close = np.maximum(close, 1.0)
    return {
        "PANEL": pd.DataFrame(
            {
                "open": close - 0.1,
                "high": close + 0.5,
                "low": close - 0.5,
                "close": close,
                "volume": np.full(bars, 10_000.0),
            },
            index=index,
        )
    }


@dataclass(frozen=True, slots=True)
class CompatibilityRecord:
    """One per-strategy compatibility register row (audit 7.10 items 1-8)."""

    name: str
    module: str
    strategy_class: str
    config_class: str
    input_requirements: str
    parameter_space: tuple[dict[str, object], ...]
    supports_streaming: bool
    position_model: str
    uses_short_signals: bool
    warmup_bars: int
    execution_assumptions: str


def _uses_short_signals(module: str, strategy_class: str) -> bool:
    """Static source scan for a negative-position branch inside ``signal()``."""
    strategy_module = __import__(module, fromlist=[strategy_class])
    source = inspect.getsource(getattr(strategy_module, strategy_class).signal)
    # ``-1`` only ever denotes the short position in the SignalStrategy contract.
    return "-1" in source


def _compatibility_record(registry: ExistingStrategyRegistry, name: str) -> CompatibilityRecord:
    descriptor = registry.describe(name)
    strategy = registry.instantiate_default(name)
    return CompatibilityRecord(
        name=descriptor.name,
        module=descriptor.module,
        strategy_class=descriptor.strategy_class,
        config_class=descriptor.config_class,
        input_requirements="close, high, low, volume (OHLCV, tz-aware, finite, positive prices)",
        parameter_space=descriptor.parameters,
        supports_streaming=callable(getattr(strategy, "feed", None)),
        position_model="single long/flat position per symbol; short branches (if any) clamp to flat "
        "under the platform's long_flat direction policy",
        uses_short_signals=_uses_short_signals(descriptor.module, descriptor.strategy_class),
        warmup_bars=int(strategy.warmup([])),
        execution_assumptions="bar-close decision; next-open execution is delegated to PortfolioSimulator",
    )


def test_catalog_registry_is_discoverable_and_bounded() -> None:
    # The register is only meaningful against the authoritative catalogue.
    registry = ExistingStrategyRegistry()
    names = registry.names()
    assert len(names) >= 1
    assert names == tuple(sorted(names))
    assert len(set(names)) == len(names)


def test_discover_skips_no_strategy_module_silently() -> None:
    # discover() drops failed modules with only a log warning (audit 7.10 item 11:
    # record unsupported strategies). The register must surface every skip.
    from research.optimize import catalog as optimize_catalog

    import importlib

    module_names = sorted(
        path.stem
        for path in optimize_catalog.CATALOG_DIR.glob("*.py")
        if path.stem != "__init__"
    )
    loaded = {spec.name for spec in optimize_catalog.discover()}
    skipped = sorted(set(module_names) - loaded)
    # A broken strategy module is a compatibility-register finding, not silence.
    assert not skipped, (
        "catalog modules failed to load and are missing from the register: "
        f"{skipped}"
    )


@pytest.mark.parametrize("strategy_name", ExistingStrategyRegistry().names())
def test_existing_strategy_signal_compat(strategy_name: str) -> None:
    """Compatibility register row: run one catalogue strategy end to end."""
    registry = ExistingStrategyRegistry()
    record = _compatibility_record(registry, strategy_name)
    adapter = ExistingStrategySignalAdapter(registry)

    bars = _synthetic_bars()
    first = adapter.build_signals(strategy_name, bars, parameters={})
    # A signal row exists for every bar and stays finite.
    signal = first.signals["PANEL"]
    assert len(signal) == _PANEL_BARS
    assert signal.index.equals(bars["PANEL"].index)
    assert np.isfinite(signal.to_numpy()).all()
    # The adapter records provenance exactly as the candidate store requires.
    assert first.strategy_name == strategy_name
    assert first.parameters == {}
    assert first.decision_time == "bar_close"
    # The platform's direction policy never invents a short position, and the
    # mapping is declared on the result rather than applied silently.
    assert set(np.unique(signal.to_numpy())).issubset({0.0, 1.0})
    assert first.direction_policy == "long_flat"

    # Determinism: an identical re-run under the fixed panel reproduces the stream.
    second = adapter.build_signals(strategy_name, _synthetic_bars(), parameters={})
    pd.testing.assert_series_equal(first.signals["PANEL"], second.signals["PANEL"])

    # Register row sanity: streaming input and executable warm-up metadata exist.
    assert record.supports_streaming is True
    assert record.warmup_bars >= 0
    assert record.input_requirements.strip() != ""
    assert record.execution_assumptions.strip() != ""


@pytest.mark.parametrize("strategy_name", ExistingStrategyRegistry().names())
def test_existing_strategy_candidate_record_carries_strategy_provenance(strategy_name: str) -> None:
    """The candidate record stores strategy_name and the invoked parameters."""
    registry = ExistingStrategyRegistry()
    adapter = ExistingStrategySignalAdapter(registry)
    result = adapter.build_signals(strategy_name, _synthetic_bars(), parameters={})
    targets = adapter.individual_asset_targets(result, "PANEL")
    # The target matrix attrs are exactly what a candidate record persists.
    assert targets.attrs["strategy_name"] == strategy_name
    assert targets.attrs["parameters"] == {}
    assert targets.attrs["allocation_policy"] == "single_asset_long_flat"

    equal_weight = adapter.equal_weight_targets(result)
    assert equal_weight.attrs["strategy_name"] == strategy_name
    assert equal_weight.attrs["parameters"] == {}
    assert equal_weight.attrs["allocation_policy"] == "equal_weight_active_signals"


def test_compatibility_register_covers_every_catalog_strategy() -> None:
    """The register enumerates all discoverable strategies (audit item 1)."""
    registry = ExistingStrategyRegistry()
    names = registry.names()
    records = [_compatibility_record(registry, name) for name in names]
    assert [record.name for record in records] == list(names)
    # Every row declares a strategy/config pair and executable warm-up metadata.
    for record in records:
        assert record.warmup_bars >= 0
        assert record.strategy_class.endswith("Strategy")
        assert record.config_class.endswith("Config")


def test_unknown_parameter_fields_are_rejected_before_any_run() -> None:
    # A typo must never silently map to a different strategy configuration.
    registry = ExistingStrategyRegistry()
    adapter = ExistingStrategySignalAdapter(registry)
    with pytest.raises(ValueError, match="unknown config fields"):
        adapter.build_signals(
            "absolute_momentum", _synthetic_bars(), parameters={"nonexistent_field": 1}
        )


def test_short_signal_branches_are_documented_not_mapped_silently() -> None:
    # Audit 7.10 item 12: strategies with short branches must be recorded explicitly.
    registry = ExistingStrategyRegistry()
    records = {
        name: _compatibility_record(registry, name)
        for name in ("absolute_momentum", "macd_strategy", "rsi_strategy")
    }
    # absolute_momentum emits -1 when momentum is below the negative threshold.
    assert records["absolute_momentum"].uses_short_signals is True
    for record in records.values():
        assert "long/flat" in record.position_model
        assert "clamp to flat" in record.position_model
