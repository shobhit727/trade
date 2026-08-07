from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

FloatArray = npt.NDArray[np.float64]


@dataclass(frozen=True)
class PortfolioOptimizerResult:
    """Asset weights summing to ~1.0 for a given optimization method."""

    method: str
    weights: dict[str, float]


@dataclass
class _Cluster:
    """Cluster of asset indices for hierarchical clustering."""

    assets: list[int]
    children: list[_Cluster]

    @property
    def is_leaf(self) -> bool:
        return not self.children


def _covariance(returns: FloatArray) -> FloatArray:
    if returns.ndim != 2 or returns.shape[1] < 2:
        raise ValueError("returns must be 2-D with at least 2 assets")
    if returns.shape[0] < 2:
        raise ValueError("returns must have at least 2 observations")
    return np.cov(returns, rowvar=False)


def _cluster_cov(cluster: _Cluster, cov: FloatArray) -> FloatArray:
    return cov[np.ix_(cluster.assets, cluster.assets)]


def _inv_vol_weights(cov: FloatArray) -> FloatArray:
    std = np.sqrt(np.diag(cov))
    inv = np.where(std > 0, 1.0 / std, 0.0)
    total = inv.sum()
    if total <= 0:
        return np.full(cov.shape[0], 1.0 / cov.shape[0])
    return inv / total


def _cluster_dist(a: _Cluster, b: _Cluster, distance: FloatArray) -> float:
    return float(min(distance[i, j] for i in a.assets for j in b.assets))


def _single_linkage(distance: FloatArray) -> _Cluster:
    """Agglomerative single-linkage clustering; returns root cluster tree."""
    clusters = [_Cluster(assets=[i], children=[]) for i in range(distance.shape[0])]
    while len(clusters) > 1:
        best_i, best_j, best_d = 0, 1, np.inf
        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                d = _cluster_dist(clusters[i], clusters[j], distance)
                if d < best_d:
                    best_i, best_j, best_d = i, j, d
        new = _Cluster(
            assets=clusters[best_i].assets + clusters[best_j].assets,
            children=[clusters[best_i], clusters[best_j]],
        )
        clusters = [c for idx, c in enumerate(clusters) if idx not in (best_i, best_j)]
        clusters.append(new)
    return clusters[0]


def _hrp_weights(cov: FloatArray) -> FloatArray:
    n = cov.shape[0]
    if n == 1:
        return np.array([1.0])
    std = np.sqrt(np.diag(cov))
    corr = cov / np.outer(std, std)
    np.fill_diagonal(corr, 1.0)
    dist = np.sqrt(np.maximum(0.0, 2.0 * (1.0 - corr)))
    root = _single_linkage(dist)
    weights = np.zeros(n)

    def split(cluster: _Cluster, weight: float) -> None:
        if cluster.is_leaf:
            weights[cluster.assets[0]] = weight
            return
        left, right = cluster.children
        left_w = float(_inv_vol_weights(_cluster_cov(left, cov)).sum())
        right_w = float(_inv_vol_weights(_cluster_cov(right, cov)).sum())
        denom = left_w + right_w
        alpha = left_w / denom if denom > 0 else 0.5
        split(left, weight * alpha)
        split(right, weight * (1.0 - alpha))

    split(root, 1.0)
    return weights / weights.sum()


def _per_asset_cvar(returns: FloatArray, alpha: float) -> FloatArray:
    """Per-asset CVaR (mean return below the alpha quantile)."""
    var = np.quantile(returns, alpha, axis=0)
    tails = returns <= var
    counts = tails.sum(axis=0)
    sums = (returns * tails).sum(axis=0)
    return np.where(counts > 0, sums / np.maximum(counts, 1), var)


def _mean_cvar_weights(returns: FloatArray, alpha: float) -> FloatArray:
    """Weights inversely proportional to per-asset CVaR (tail-risk penalty)."""
    cvar = _per_asset_cvar(returns, alpha)
    w = np.where(cvar < 0, 1.0 / -cvar, 0.0)
    total = w.sum()
    if total <= 0:
        return _inv_vol_weights(_covariance(returns))
    return w / total


def hrp_weights(returns: FloatArray, asset_names: list[str]) -> PortfolioOptimizerResult:
    """Hierarchical Risk Parity weights from a return matrix (rows=obs, cols=assets)."""
    _check_shape(returns, asset_names)
    if returns.shape[1] == 1:
        return PortfolioOptimizerResult(method="hrp", weights={asset_names[0]: 1.0})
    w = _hrp_weights(_covariance(returns))
    return PortfolioOptimizerResult(method="hrp", weights=dict(zip(asset_names, w, strict=True)))


def mean_cvar_weights(
    returns: FloatArray, asset_names: list[str], alpha: float = 0.05
) -> PortfolioOptimizerResult:
    """Tail-risk-aware weights: inversely proportional to per-asset CVaR."""
    if not 0 < alpha < 1:
        raise ValueError("alpha must be in (0, 1)")
    _check_shape(returns, asset_names)
    if returns.shape[1] == 1:
        return PortfolioOptimizerResult(method="mean_cvar", weights={asset_names[0]: 1.0})
    w = _mean_cvar_weights(returns, alpha)
    return PortfolioOptimizerResult(method="mean_cvar", weights=dict(zip(asset_names, w, strict=True)))


def _check_shape(returns: FloatArray, asset_names: list[str]) -> None:
    if returns.ndim != 2:
        raise ValueError("returns must be a 2-D matrix (obs x assets)")
    if returns.shape[1] != len(asset_names):
        raise ValueError("len(asset_names) must equal number of return columns")


__all__ = ["PortfolioOptimizerResult", "hrp_weights", "mean_cvar_weights"]
