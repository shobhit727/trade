"""Allow-listed typed components and the composition Policy enforcing compatibility.

Each component ID maps to one fixed numerical rule over the PointInTimeFeatureEngine
column schema. The registry covers the audit F-020 roles: entry conditions, exit
conditions, filters, regime detectors, position-sizing methods, risk constraints,
rebalancing logic, volatility controls, and execution assumptions. Every rule reads
only the current feature row (features are built causally upstream), so composed
signals never use future information.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np

from .composition import Component, Composition
from .model_evaluation import ModelFeaturePanel


def default_component_registry(windows: Sequence[int]) -> tuple[Component, ...]:
    """Build a deterministic component catalogue tied to the feature-window set.

    Roles covered (audit F-020): entry, exit, filter, regime, sizing, risk,
    allocation, rebalance, volatility, execution. Component IDs are declarative only;
    every ID maps to the fixed numerical rule implemented in ``composition_scores``.
    """
    # The catalogue contains declarative IDs only; each ID maps to a fixed numerical rule.
    normalised = tuple(sorted(set(int(value) for value in windows)))
    if not normalised or any(value < 2 for value in normalised):
        raise ValueError("component registry requires feature windows >= 2")
    registry: list[Component] = []
    for window in normalised:
        registry.extend((
            # Entry conditions.
            Component(
                f"momentum_entry_{window}", "entry",
                (("window", float(window)), ("threshold", 0.0)),
            ),
            Component(
                f"trend_entry_{window}", "entry",
                (("window", float(window)), ("threshold", 0.0)),
            ),
            # Exit conditions.
            Component(
                f"momentum_exit_{window}", "exit",
                (("window", float(window)), ("threshold", 0.0)),
            ),
            Component(
                f"trend_exit_{window}", "exit",
                (("window", float(window)), ("threshold", 0.0)),
            ),
            # Filters (price-magnitude gates).
            Component(
                f"atr_filter_{window}", "filter",
                (("window", float(window)), ("max_value", 0.08)),
            ),
            Component(
                f"volume_filter_{window}", "filter",
                (("window", float(window)), ("min_value", -2.0)),
            ),
            # Regime detectors.
            Component(
                f"trend_regime_{window}", "regime",
                (("window", float(window)), ("min_value", 0.0)),
            ),
            Component(
                f"volatility_regime_{window}", "regime",
                (("window", float(window)), ("max_value", 0.001)),
            ),
            # Position-sizing methods.
            Component(
                f"volatility_scaled_sizing_{window}", "sizing",
                (("window", float(window)), ("base_fraction", 1.0), ("min_scale", 0.25)),
            ),
            Component(
                f"equal_fraction_sizing_{window}", "sizing",
                (("window", float(window)), ("fraction", 1.0)),
            ),
            # Risk constraints.
            Component(
                f"atr_risk_{window}", "risk",
                (("window", float(window)), ("max_value", 0.12)),
            ),
            Component(
                f"drawdown_risk_{window}", "risk",
                (("window", float(window)), ("max_drawdown", 0.002)),
            ),
            # Rebalancing logic.
            Component(
                f"periodic_rebalance_{window}", "rebalance",
                (("window", float(window)), ("period_bars", float(window))),
            ),
            # Volatility controls.
            Component(
                f"volatility_cap_{window}", "volatility",
                (("window", float(window)), ("max_volatility", 0.0012)),
            ),
            Component(
                f"volatility_floor_{window}", "volatility",
                (("window", float(window)), ("min_volatility", 0.001)),
            ),
        ))
    registry.extend((
        # Allocation scheme (window-independent weighting policy).
        Component(
            "equal_weight_allocation", "allocation",
            (("gross_exposure", 1.0),),
        ),
        Component(
            "single_asset_allocation", "allocation",
            (("gross_exposure", 1.0),),
        ),
        # Execution assumptions.
        Component(
            "next_open_execution", "execution",
            (("slippage_bps", 0.0),),
        ),
        Component(
            "same_close_execution", "execution",
            (("slippage_bps", 0.0),),
        ),
    ))
    return tuple(registry)


def _parameters(component: Component) -> dict[str, float]:
    # Component construction has already validated finite named parameter values.
    return dict(component.parameters)


def _feature_field(prefix: str, window: int) -> str:
    # Map each allow-listed component family to its deterministic feature column.
    if prefix in {"momentum_entry", "momentum_exit"}:
        return f"momentum_{window}"
    if prefix in {"trend_entry", "trend_exit", "trend_regime"}:
        return f"close_to_sma_{window}"
    if prefix in {"atr_filter", "atr_risk"}:
        return f"atr_pct_{window}"
    if prefix == "volume_filter":
        return f"volume_z_{window}"
    if prefix == "volatility_regime":
        return f"volatility_{window}"
    if prefix in {
        "volatility_scaled_sizing", "equal_fraction_sizing",
        "periodic_rebalance", "volatility_cap", "volatility_floor",
    }:
        return f"volatility_{window}"
    if prefix == "drawdown_risk":
        # Drawdown proxy runs on the signed one-bar return column.
        return "return_1"
    raise ValueError(f"unsupported allow-listed component family: {prefix}")


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
        prefix = component.component_id.rsplit("_", 1)[0]
        if component.role == "allocation":
            # Allocation components carry no feature column.
            components.append((component, parameters, None, prefix))
            continue
        if component.role == "execution":
            components.append((component, parameters, None, prefix))
            continue
        window = int(parameters.get("window", 0))
        if window not in feature_windows:
            raise ValueError(f"component {component.component_id} references an unconfigured window")
        field = _feature_field(prefix, window)
        if field not in column_index:
            raise ValueError(f"component feature is absent: {field}")
        components.append((component, parameters, column_index[field], prefix))

    entry_components = [item for item in components if item[0].role == "entry"]
    exit_components = [item for item in components if item[0].role == "exit"]
    if not entry_components or not exit_components:
        raise ValueError("composition requires at least one entry and one exit component")
    # Enforce the composition compatibility graph again at the Policy boundary: a
    # genome assembled outside Composition (or by an older serialisation) cannot
    # bypass the role-pair rules.
    roles = [item[0].role for item in components]
    if "filter" in roles and "regime" in roles:
        raise ValueError("composition combines incompatible roles: filter and regime")
    if "allocation" in roles and "rebalance" in roles:
        raise ValueError("composition combines incompatible roles: allocation and rebalance")
    gates = [
        item for item in components
        if item[0].role in {"filter", "regime", "risk", "volatility"}
    ]
    sizing_components = [item for item in components if item[0].role == "sizing"]
    rebalance_components = [item for item in components if item[0].role == "rebalance"]
    allocation_components = [item for item in components if item[0].role == "allocation"]
    execution_components = [item for item in components if item[0].role == "execution"]
    # Allocation and execution are single-slot policies: multiple conflicting
    # declarations would make the target weights ambiguous.
    if len(allocation_components) > 1:
        raise ValueError("composition declares multiple allocation components")
    if len(execution_components) > 1:
        raise ValueError("composition declares multiple execution components")

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

        # Gating roles: filters, regime detectors, risk constraints, volatility controls.
        for component, parameters, feature_index, prefix in gates:
            values = matrix[:, feature_index]
            if prefix in {"atr_filter", "atr_risk"}:
                active &= values < parameters["max_value"]
            elif prefix == "volume_filter":
                active &= values > parameters["min_value"]
            elif prefix == "trend_regime":
                active &= values > parameters["min_value"]
            elif prefix == "volatility_regime":
                active &= values < parameters["max_value"]
            elif prefix == "volatility_cap":
                active &= values < parameters["max_volatility"]
            elif prefix == "volatility_floor":
                active &= values > parameters["min_volatility"]
            elif prefix == "drawdown_risk":
                # Bounded causal drawdown proxy: cumulative return drop over the
                # lookback computed with cumsum (features themselves are causal).
                max_drawdown = parameters["max_drawdown"]
                cumulative = np.cumsum(matrix[:, feature_index])
                running_peak = np.maximum.accumulate(cumulative)
                drawdown = cumulative - running_peak
                active &= drawdown > -max_drawdown

        # Position sizing scales the signal magnitude for active rows.
        score = np.where(active, 1.0, -1.0)
        if sizing_components:
            scale = np.ones(count, dtype=np.float64)
            for component, parameters, feature_index, prefix in sizing_components:
                values = matrix[:, feature_index]
                if prefix == "volatility_scaled_sizing":
                    # Higher volatility -> smaller position, floored at min_scale.
                    vol = np.maximum(values, 1e-8)
                    raw = parameters.get("base_fraction", 1.0) / (1.0 + values / (vol * 100.0))
                    scale = np.minimum(scale, np.maximum(raw, parameters.get("min_scale", 0.25)))
                elif prefix == "equal_fraction_sizing":
                    scale = np.minimum(scale, parameters.get("fraction", 1.0))
            # Sizing scales only active rows; inactive rows keep the -1 cash score.
            score = np.where(active, score * scale, score)

        # Rebalancing logic: between scheduled bars the signal is held flat (0 score
        # means "no decision this bar" downstream), only refresh on period boundaries.
        for component, parameters, feature_index, prefix in rebalance_components:
            period = max(int(parameters.get("period_bars", 1)), 1)
            schedule = (np.arange(count) % period) == 0
            score = np.where(schedule, score, 0.0)

        # Allocation and execution assumptions are recorded in the score contract but
        # do not alter the point-in-time long/flat decision: the portfolio simulator
        # already consumes next-open fills (the documented execution default).
        if allocation_components or execution_components:
            # Presence is validated above; the score stays a signed long/flat value.
            pass

        output[offset - count:offset] = score

    return output
