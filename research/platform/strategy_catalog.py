"""Compatibility adapters for the repository's existing strategy catalogue."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Iterable


def _json_value(value: Any) -> Any:
    # Convert common config defaults into stable JSON values without losing Decimal precision.
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_json_value(item) for item in value]
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)


@dataclass(frozen=True, slots=True)
class StrategyDescriptor:
    """Serializable view of one existing strategy and its bounded typed parameters."""

    name: str
    module: str
    strategy_class: str
    config_class: str
    defaults: dict[str, Any]
    parameters: tuple[dict[str, Any], ...]
    held_fixed: tuple[str, ...]


class ExistingStrategyRegistry:
    """Lazy adapter over research.optimize.catalog without copying its registrations."""

    def __init__(self, include: tuple[str, ...] = ()) -> None:
        # Catalog imports are delayed until discovery is requested.
        self.include = include
        self._specs: dict[str, Any] | None = None

    def _load(self) -> dict[str, Any]:
        # Let the repository's authoritative catalogue apply its module and type guards.
        if self._specs is None:
            from research.optimize.catalog import discover

            specs = discover(include=self.include)
            self._specs = {spec.name: spec for spec in specs}
        return self._specs

    def names(self) -> tuple[str, ...]:
        """Return stable sorted strategy names."""
        return tuple(sorted(self._load()))

    def describe(self, name: str) -> StrategyDescriptor:
        """Return typed parameter bounds, defaults and fixed fields for one strategy."""
        spec = self._get(name)
        parameters = tuple(_json_value(parameter.to_dict()) for parameter in spec.params)
        defaults = _json_value(spec.default)
        return StrategyDescriptor(
            name=spec.name,
            module=spec.module,
            strategy_class=spec.strategy_cls.__name__,
            config_class=spec.config_cls.__name__,
            defaults=defaults,
            parameters=parameters,
            held_fixed=tuple(sorted(spec.held_fixed)),
        )

    def instantiate(self, name: str, parameters: dict[str, Any] | None = None):
        """Build an existing strategy using its original typed Config constructor."""
        spec = self._get(name)
        supplied = dict(parameters or {})
        allowed = {item.name for item in dataclasses.fields(spec.config_cls)}
        unknown = set(supplied) - allowed
        if unknown:
            raise ValueError(f"unknown config fields for {name}: {sorted(unknown)}")
        # StrategySpec.build restores serialised Decimal and other supported config values.
        return spec.build(supplied)

    def instantiate_default(self, name: str):
        """Construct the exact shipped default implementation for baseline comparisons."""
        spec = self._get(name)
        return spec.build(dict(spec.default))

    def search_space(self, name: str) -> tuple[dict[str, Any], ...]:
        """Return only parameters which the existing catalogue considers searchable."""
        return tuple(_json_value(parameter.to_dict()) for parameter in self._get(name).params)

    def _get(self, name: str):
        # Exact lookup avoids silently mapping a typo to a different strategy.
        try:
            return self._load()[name]
        except KeyError as exc:
            raise KeyError(f"unknown existing strategy: {name}") from exc

    def validate_parameter_payload(self, name: str, parameters: dict[str, Any]) -> None:
        """Validate config field names without constructing or executing a strategy."""
        spec = self._get(name)
        allowed = {item.name for item in dataclasses.fields(spec.config_cls)}
        unknown = set(parameters) - allowed
        if unknown:
            raise ValueError(f"unknown config fields for {name}: {sorted(unknown)}")
