from __future__ import annotations

from collections.abc import Sequence
from math import erf, sqrt
from typing import Any

import numpy as np


def walk_forward_returns(
    returns: Sequence[float],
    n_splits: int = 5,
    min_train: int = 30,
    embargo: int = 5,
) -> dict[str, Any]:
    if not returns:
        return {"splits": 0, "oos_mean": 0.0, "oos_sharpe": 0.0, "passed": False}
    arr = np.asarray(returns, dtype=float)
    n = len(arr)
    if n < min_train + embargo + 2:
        return {"splits": 0, "oos_mean": 0.0, "oos_sharpe": 0.0, "passed": False, "reason": "insufficient data"}
    fold_size = (n - min_train) // n_splits
    oos: list[float] = []
    stability_scores: list[float] = []
    for k in range(n_splits):
        train_end = min_train + k * fold_size
        test_end = train_end + fold_size + embargo
        if test_end > n:
            test_end = n
        if train_end >= test_end:
            continue
        oos.extend(arr[train_end + embargo : test_end].tolist())
        train_segment = arr[max(0, train_end - min_train) : train_end]
        if train_segment.size > 1 and train_segment.std(ddof=0) > 0:
            z = (train_segment.mean() - oos_mean_so_far(oos)) / max(train_segment.std(ddof=0), 1e-9)
            stability_scores.append(float(np.clip(1.0 - abs(z) / 4.0, 0.0, 1.0)))
    oos_arr = np.asarray(oos, dtype=float)
    if oos_arr.size < 5:
        return {"splits": 0, "oos_mean": 0.0, "oos_sharpe": 0.0, "passed": False, "reason": "too few oos samples"}
    mu = float(oos_arr.mean())
    sd = float(oos_arr.std(ddof=0))
    sharpe = 0.0 if sd <= 0 else float(mu / sd * sqrt(252))
    stability = float(np.mean(stability_scores)) if stability_scores else 0.0
    return {
        "splits": int(len(stability_scores)),
        "oos_mean": mu,
        "oos_sharpe": sharpe,
        "oos_std": sd,
        "stability": stability,
        "passed": sharpe > 0.0 and stability >= 0.5,
    }


def oos_mean_so_far(values: Sequence[float]) -> float:
    return float(np.mean(values)) if values else 0.0


def monte_carlo_significance(
    returns: Sequence[float],
    n_permutations: int = 1000,
    block_size: int = 5,
    seed: int | None = 42,
) -> dict[str, Any]:
    if not returns:
        return {"p_value": 1.0, "passed": False, "reason": "no returns"}
    rng = np.random.default_rng(seed)
    arr = np.asarray(returns, dtype=float)
    n = len(arr)
    blocks: list[np.ndarray] = []
    i = 0
    while i < n:
        end = min(i + block_size, n)
        blocks.append(arr[i:end])
        i += block_size
    if not blocks:
        return {"p_value": 1.0, "passed": False, "reason": "no blocks"}
    observed_sharpe = _sharpe(arr)
    permuted_sharpes = np.empty(n_permutations, dtype=float)
    for k in range(n_permutations):
        idx = rng.integers(0, len(blocks), size=len(blocks))
        shuffled = np.concatenate([blocks[i] for i in idx])
        shuffled = shuffled[:n]
        permuted_sharpes[k] = _sharpe(shuffled)
    if permuted_sharpes.std(ddof=0) <= 0:
        p_value = 1.0
    else:
        denom = permuted_sharpes.std(ddof=0)
        center = permuted_sharpes.mean()
        z = (observed_sharpe - center) / denom if denom > 0 else 0.0
        p_value = float(1.0 - _normal_cdf(z))
    return {
        "p_value": float(p_value),
        "observed_sharpe": float(observed_sharpe),
        "permutations": int(n_permutations),
        "passed": p_value < 0.05 and observed_sharpe > 0,
    }


def _normal_cdf(z: float) -> float:
    return 0.5 * (1.0 + float(erf(z / sqrt(2.0))))


def _sharpe(returns: np.ndarray) -> float:
    if returns.size < 2:
        return 0.0
    sd = float(returns.std(ddof=0))
    if sd <= 0:
        return 0.0
    return float(returns.mean() / sd * sqrt(252))


def deflated_sharpe(
    returns: Sequence[float],
    n_trials: int = 1,
    benchmark_sharpe: float = 0.0,
) -> dict[str, Any]:
    arr = np.asarray(returns, dtype=float)
    observed = _sharpe(arr)
    if arr.size < 2:
        return {"observed_sharpe": 0.0, "deflated_sharpe": 0.0, "passed": False}
    e_max = observed * (1.0 - 1.0 / max(n_trials, 1)) + benchmark_sharpe / max(n_trials, 1)
    variance = (1.0 / max(arr.size - 1, 1)) * (1.0 + 0.5 * observed ** 2)
    psr = float(_normal_cdf((observed - benchmark_sharpe) / sqrt(max(variance, 1e-12))))
    return {
        "observed_sharpe": float(observed),
        "expected_max_sharpe": float(e_max),
        "probabilistic_sharpe_ratio": psr,
        "deflated_sharpe": float(observed - e_max),
        "passed": psr > 0.95,
    }


def run_validation(
    returns: Sequence[float],
    n_splits: int = 5,
    n_permutations: int = 1000,
    n_trials: int = 1,
) -> dict[str, Any]:
    walk = walk_forward_returns(returns, n_splits=n_splits)
    mc = monte_carlo_significance(returns, n_permutations=n_permutations)
    ds = deflated_sharpe(returns, n_trials=n_trials)
    return {
        "walk_forward": walk,
        "monte_carlo": mc,
        "deflated_sharpe": ds,
        "passed": bool(walk.get("passed") and mc.get("passed")),
    }
