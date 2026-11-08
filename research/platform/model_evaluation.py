"""Shared point-in-time feature and portfolio evaluation for evolved numerical policies."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

import numpy as np
import pandas as pd

from .domain import ResearchTrack
from .features import PointInTimeFeatureEngine
from .metrics import compute_portfolio_metrics
from .portfolio import PortfolioConfig, PortfolioResult, PortfolioSimulator


@dataclass(frozen=True, slots=True)
class FeatureSegment:
    """Map a contiguous prediction block back to its instrument and bar positions."""

    symbol: str
    column_position: int
    bar_positions: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class ModelPartitionResult:
    """Metrics and fills from one model-expression portfolio partition."""

    partition: str
    start: datetime
    end: datetime
    result: PortfolioResult
    metrics: dict[str, float | int]
    sample_count: int


@dataclass(frozen=True, slots=True)
class ModelFeaturePanel:
    """Causal features, source bars and row mapping for one time partition."""

    bars: dict[str, pd.DataFrame]
    features: np.ndarray
    segments: tuple[FeatureSegment, ...]
    index: pd.DatetimeIndex
    start_position: int
    track: ResearchTrack

    def targets_from_scores(self, scores: np.ndarray) -> pd.DataFrame:
        """Convert model scores to long/flat target weights without using future values."""
        # Shape checks ensure that a model cannot omit or add prediction rows silently.
        values = np.asarray(scores, dtype=np.float64).reshape(-1)
        if len(values) != len(self.features) or not np.isfinite(values).all():
            raise ValueError("model scores must be finite and match the feature panel row count")
        targets = pd.DataFrame(0.0, index=self.index, columns=list(self.bars))
        for segment in self.segments:
            # Positive policy scores indicate active long exposure; all other rows stay cash.
            active = (values[:len(segment.bar_positions)] > 0.0).astype(np.float64)
            values = values[len(segment.bar_positions):]
            targets.iloc[list(segment.bar_positions), segment.column_position] = active

        if self.track in {ResearchTrack.NSE_INDIVIDUAL, ResearchTrack.CRYPTO_INDIVIDUAL}:
            if len(self.bars) != 1:
                raise ValueError("individual-asset model track requires exactly one instrument")
        else:
            # Active symbols share the same gross exposure; no cross-market mixing is possible.
            active_count = targets.sum(axis=1).replace(0.0, np.nan)
            targets = targets.div(active_count, axis=0).fillna(0.0)
        targets.attrs["decision_time"] = "bar_close"
        targets.attrs["allocation_policy"] = (
            "single_asset_long_flat"
            if len(self.bars) == 1 else "equal_weight_active_signals"
        )
        return targets


def build_model_feature_panel(
    bars_by_symbol: Mapping[str, pd.DataFrame],
    engine: PointInTimeFeatureEngine,
    track: ResearchTrack,
    *,
    start: datetime,
    end: datetime,
) -> ModelFeaturePanel:
    """Build trailing features for rows inside [start, end), retaining pre-window warm-up."""
    # The data map is clipped at end before the model receives any observations.
    if not bars_by_symbol:
        raise ValueError("bars_by_symbol cannot be empty")
    if end <= start:
        raise ValueError("partition end must follow start")
    ordered = sorted(bars_by_symbol)
    truncated: dict[str, pd.DataFrame] = {}
    common_index: pd.DatetimeIndex | None = None
    for symbol in ordered:
        frame = bars_by_symbol[symbol]
        index = pd.DatetimeIndex(frame.index)
        if index.tz is None or not index.is_monotonic_increasing or index.has_duplicates:
            raise ValueError(f"{symbol}: bars require an aware, increasing and unique index")
        utc_index = index.tz_convert("UTC")
        selected = frame.loc[utc_index < end].copy()
        if selected.empty:
            raise ValueError(f"{symbol}: no bars before partition end")
        selected_index = pd.DatetimeIndex(selected.index)
        if common_index is None:
            common_index = selected_index
        elif not selected_index.equals(common_index):
            raise ValueError("model portfolio requires the same chronological bar calendar")
        truncated[symbol] = selected

    assert common_index is not None
    utc_common = common_index.tz_convert("UTC")
    start_position = int(utc_common.searchsorted(start, side="left"))
    if start_position >= len(common_index):
        raise ValueError("no bars are available inside the requested model partition")

    feature_blocks: list[np.ndarray] = []
    segments: list[FeatureSegment] = []
    for column_position, symbol in enumerate(ordered):
        # Features use all available history before start but stop strictly before end.
        features = engine.build(truncated[symbol])
        matrix = features.to_numpy(dtype=np.float64)
        finite = np.isfinite(matrix).all(axis=1)
        in_window = (utc_common >= start) & (utc_common < end)
        positions = np.flatnonzero(finite & in_window)
        if not len(positions):
            raise ValueError(f"{symbol}: no finite causal features inside {start}..{end}")
        feature_blocks.append(matrix[positions])
        segments.append(
            FeatureSegment(symbol, column_position, tuple(int(value) for value in positions))
        )

    combined = np.concatenate(feature_blocks, axis=0)
    if not np.isfinite(combined).all():
        raise ValueError("combined model feature matrix contains non-finite values")
    return ModelFeaturePanel(
        bars=truncated,
        features=combined,
        segments=tuple(segments),
        index=common_index,
        start_position=start_position,
        track=track,
    )


def evaluate_model_scores(
    panel: ModelFeaturePanel,
    scores: np.ndarray,
    config: PortfolioConfig,
    *,
    partition: str,
    start: datetime,
    end: datetime,
    periods_per_year: int,
) -> ModelPartitionResult:
    """Simulate one model's close-time scores with next-open fills in one partition."""
    # The same portfolio simulator and accounting rules apply to evolved and hand-coded models.
    targets = panel.targets_from_scores(scores)
    result = PortfolioSimulator(config).run(panel.bars, targets)
    metric_start = max(panel.start_position - 1, 0)
    curve = result.equity_curve.iloc[metric_start:].copy()
    utc_curve = pd.DatetimeIndex(curve.index).tz_convert("UTC")
    curve = curve.loc[utc_curve < end]
    if len(curve) < 2:
        raise ValueError(f"{partition}: insufficient equity observations for risk metrics")
    metrics = compute_portfolio_metrics(
        curve,
        periods_per_year=periods_per_year,
    ).to_dict()
    return ModelPartitionResult(
        partition=partition,
        start=start,
        end=end,
        result=result,
        metrics=metrics,
        sample_count=len(panel.features),
    )
