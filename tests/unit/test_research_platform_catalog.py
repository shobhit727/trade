"""Tests for transparent reuse of existing strategy registrations."""


import pytest

from research.platform.strategy_catalog import ExistingStrategyRegistry


def test_existing_strategy_registry_discovers_real_catalogue_entries() -> None:
    # The adapter must preserve existing registrations instead of creating duplicate classes.
    registry = ExistingStrategyRegistry()
    names = registry.names()
    assert len(names) >= 1
    assert "absolute_momentum" in names
    descriptor = registry.describe("absolute_momentum")
    assert descriptor.name == "absolute_momentum"
    assert descriptor.strategy_class
    assert descriptor.config_class
    assert isinstance(descriptor.defaults, dict)
    assert isinstance(descriptor.parameters, tuple)


def test_existing_strategy_registry_builds_shipped_default() -> None:
    # Baseline strategy construction uses the repository's original Config and class.
    registry = ExistingStrategyRegistry()
    strategy = registry.instantiate_default("absolute_momentum")
    assert strategy is not None
    assert strategy.__class__.__name__ == registry.describe("absolute_momentum").strategy_class


def test_existing_strategy_registry_rejects_unknown_parameter_fields() -> None:
    # Unknown config fields must fail rather than being silently ignored by the adapter.
    registry = ExistingStrategyRegistry()
    with pytest.raises(ValueError, match="unknown config fields"):
        registry.instantiate("absolute_momentum", {"not_a_real_parameter": 123})
