"""Multiple-testing and resampling utilities for candidate research."""

from __future__ import annotations

from itertools import combinations
from typing import Sequence

import numpy as np


def benjamini_hochberg(p_values: Sequence[float], alpha: float = 0.05) -> dict[str, object]:
    """Apply Benjamini-Hochberg false-discovery-rate correction."""
    # The correction family is exactly the supplied candidate hypothesis set.
    values = np.asarray(p_values, dtype=np.float64)
    if values.ndim != 1 or not np.isfinite(values).all():
        raise ValueError("p_values must be a finite one-dimensional sequence")
    if np.any((values < 0) | (values > 1)) or not 0 < alpha < 1:
        raise ValueError("p-values must be in [0,1] and alpha in (0,1)")
    count = len(values)
    if count == 0:
        return {"adjusted_p_values": [], "reject": [], "alpha": alpha, "hypotheses": 0}
    order = np.argsort(values, kind="stable")
    ranked = values[order] * count / np.arange(1, count + 1)
    adjusted_sorted = np.minimum.accumulate(ranked[::-1])[::-1]
    adjusted_sorted = np.clip(adjusted_sorted, 0.0, 1.0)
    adjusted = np.empty(count, dtype=np.float64)
    adjusted[order] = adjusted_sorted
    return {
        "adjusted_p_values": adjusted.tolist(),
        "reject": (adjusted <= alpha).tolist(),
        "alpha": float(alpha),
        "hypotheses": int(count),
        "rejections": int(np.sum(adjusted <= alpha)),
    }


def moving_block_bootstrap(
    returns: Sequence[float],
    *,
    block_size: int = 10,
    samples: int = 2000,
    confidence: float = 0.95,
    seed: int = 42,
) -> dict[str, float | int]:
    """Circular moving-block bootstrap interval for mean periodic return."""
    # Resample contiguous circular blocks to retain some short-horizon dependence.
    values = np.asarray(returns, dtype=np.float64)
    if values.ndim != 1 or len(values) < 2 or not np.isfinite(values).all():
        raise ValueError("returns must be a finite one-dimensional sequence")
    if not 1 <= block_size <= len(values) or samples < 100 or not 0 < confidence < 1:
        raise ValueError("invalid bootstrap configuration")
    rng = np.random.default_rng(seed)
    blocks_needed = int(np.ceil(len(values) / block_size))
    starts = np.arange(len(values))
    means = np.empty(samples, dtype=np.float64)
    for sample in range(samples):
        chosen = rng.choice(starts, size=blocks_needed, replace=True)
        draw = np.concatenate([
            values[(start + np.arange(block_size)) % len(values)] for start in chosen
        ])[:len(values)]
        means[sample] = float(np.mean(draw))
    tail = (1.0 - confidence) / 2.0
    low, high = np.quantile(means, [tail, 1.0 - tail])
    return {
        "mean_return": float(np.mean(values)),
        "ci_low": float(low),
        "ci_high": float(high),
        "confidence": float(confidence),
        "samples": int(samples),
        "block_size": int(block_size),
        "seed": int(seed),
    }


def pbo_cscv(
    strategy_returns: Sequence[Sequence[float]], *, blocks: int = 8
) -> dict[str, float | int]:
    """Estimate PBO from combinatorially symmetric cross-validation rank reversals.

    Returns the fraction of train-selected best strategies that rank below the OOS
    median. This is a diagnostic over the supplied candidate family, not a correction
    for data leakage or biased universe construction.
    """
    # Each strategy must cover the same finite timeline.
    matrix = np.asarray(strategy_returns, dtype=np.float64)
    if matrix.ndim != 2 or matrix.shape[0] < 2 or not np.isfinite(matrix).all():
        raise ValueError("strategy_returns must be a finite strategies-by-time matrix")
    if blocks < 4 or blocks % 2 or matrix.shape[1] < blocks:
        raise ValueError("CSCV requires an even block count of at least four")
    chunks = np.array_split(np.arange(matrix.shape[1]), blocks)
    half = blocks // 2
    under_median: list[bool] = []
    for train_blocks in combinations(range(blocks), half):
        # Use complementary block combinations for train and test.
        train_set = set(train_blocks)
        test_blocks = [index for index in range(blocks) if index not in train_set]
        train_indices = np.concatenate([chunks[index] for index in train_blocks])
        test_indices = np.concatenate([chunks[index] for index in test_blocks])

        def sharpe(series: np.ndarray) -> np.ndarray:
            # Zero-volatility series score zero rather than NaN or infinity.
            deviation = np.std(series, axis=1, ddof=1)
            mean = np.mean(series, axis=1)
            return np.divide(mean, deviation, out=np.zeros_like(mean), where=deviation > 0)

        train_scores = sharpe(matrix[:, train_indices])
        test_scores = sharpe(matrix[:, test_indices])
        selected = int(np.argmax(train_scores))
        # Rank 0 is the best OOS result; ties use stable original candidate order.
        descending_order = np.argsort(-test_scores, kind="stable")
        rank = np.empty(len(test_scores), dtype=np.int64)
        rank[descending_order] = np.arange(len(test_scores))
        percentile = (float(rank[selected]) + 0.5) / len(test_scores)
        under_median.append(percentile > 0.5)
    return {
        "pbo": float(np.mean(under_median)),
        "splits": len(under_median),
        "strategies": int(matrix.shape[0]),
        "blocks": int(blocks),
    }
