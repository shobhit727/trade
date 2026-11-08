"""Allow-listed causal feature components for strategy-composition evolution."""

from __future__ import annotations

from typing import Sequence

import numpy as np

from .composition import Component, Composition
from .model_evaluation import ModelFeaturePanel


def default_component_registry(windows: Sequence[int]) -> tuple[Component, ...]:
    """Build a deterministic component catalogue tied to the feature-window set."""
    # The catalogue contains declarative IDs only; each ID maps to a fixed numerical rule.
    normalised = tuple(sorted(set(int(value) for value in windows)))
    if not normalised or any(value < 2 for value in normalised):
        raise ValueError("component registry requires feature windows >= 2")
    registry: list[Component] = []
    for window in normalised:
        registry.extend((
            Component(
                f"momentum_entry_{window}", "entry",
                (("window", float(window)), ("threshold", 0.0)),
            ),
            Component(
                f"trend_entry_{window}", "entry",
                (("window", float(window)), ("threshold", 0.0)),
            ),
            Component(
                f"momentum_exit_{window}", "exit",
                (("window", float(window)), ("threshold", 0.0)),
            ),
            Component(
                f"trend_exit_{window}", "exit",
                (("window", float(window)), ("threshold", 0.0)),
            ),
            Component(
                f"atr_filter_{window}", "filter",
                (("window", float(window)), ("max_value", 0.08)),
            ),
            Component(
                f"volume_filter_{window}", "filter",
                (("window", float(window)), ("min_value", -2.0)),
            ),
            Component(
                f"trend_regime_{window}", "regime",
                (("window", float(window)), ("min_value", 0.0)),
            ),
            Component(
                f"atr_risk_{window}", "risk",
                (("window", float(window)), ("max_value", 0.12)),
            ),
        ))
    return tuple(registry)


def _parameters(component: Component) -> dict[str, float]:
    # Component construction has already validated finite named parameter values.
    return dict(component.parameters)


def composition_scores(
    composition: Composition,
    panel: ModelFeaturePanel,
    feature_windows: Sequence[int],
) -> np.ndarray:
    """Map an immutable composition genome to one signed long/flat score per feature row."""
    # Build the deterministic feature-column map used by PointInTimeFeatureEngine.
    columns = ["return_1", "range_pct"]
    for window in sorted(set(int(value) for value in feature_windows)):
        columns.extend((
            f"momentum_{window}",
            f"volatility_{window}",
            f"atr_pct_{window}",
            f"volume_z_{window}",
            f"close_to_sma_{window}",
        ))
    column_index = {name: index for index, name in enumerate(columns)}
    if panel.features.shape[1] != len(columns):
        raise ValueError("model feature panel does not match composition feature-window schema")

    # The component ID prefixes select only the hard-coded rules in this module.
    components = []
    for component in composition.components:
        parameters = _parameters(component)
        window = int(parameters.get("window", 0))
        prefix = component.component_id.rsplit("_", 1)[0]
        if window not in feature_windows:
            raise ValueError(f"component {component.component_id} references an unconfigured window")
        if prefix in {"momentum_entry", "momentum_exit"}:
            field = f"momentum_{window}"
        elif prefix in {"trend_entry", "trend_exit", "trend_regime"}:
            field = f"close_to_sma_{window}"
        elif prefix in {"atr_filter", "atr_risk"}:
            field = f"atr_pct_{window}"
        elif prefix == "volume_filter":
            field = f"volume_z_{window}"
        else:
            raise ValueError(f"unsupported allow-listed component: {component.component_id}")
        if field not in column_index:
            raise ValueError(f"component feature is absent: {field}")
        components.append((component, parameters, column_index[field], prefix))

    entry_components = [item for item in components if item[0].role == "entry"]
    exit_components = [item for item in components if item[0].role == "exit"]
    if not entry_components or not exit_components:
        raise ValueError("composition requires at least one entry and one exit component")
    gates = [
        item for item in components
        if item[0].role in {"filter", "regime", "risk"}
    ]

    output = np.full(len(panel.features), -1.0, dtype=np.float64)
    offset = 0
    for segment in panel.segments:
        count = len(segment.bar_positions)
        matrix = panel.features[offset:offset + count]
        offset += count
        entries = []
        for component, parameters, feature_index, prefix in entry_components:
            threshold = parameters.get("threshold", 0.0)
            entries.append(matrix[:, feature_index] > threshold)
        exits = []
        for component, parameters, feature_index, prefix in exit_components:
            threshold = parameters.get("threshold", 0.0)
            exits.append(matrix[:, feature_index] < threshold)
        active = np.logical_or.reduce(entries) & ~np.logical_or.reduce(exits)
        for component, parameters, feature_index, prefix in gates:
            values = matrix[:, feature_index]
            if prefix in {"atr_filter", "atr_risk"}:
                active &= values < parameters["max_value"]
            elif prefix == "volume_filter":
                active &= values > parameters["min_value"]
            elif prefix == "trend_regime":
                active &= values > parameters["min_value"]
        output[offset - count:offset] = np.where(active, 1.0, -1.0)

    return output
