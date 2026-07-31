from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class DriftConfig:
    baseline_size: int = 100
    recent_size: int = 50
    threshold: float = 0.1


class DriftDetector:
    """Compares baseline distribution to recent observations.

    Returns a drift score in [0, 1]; high score signals probable covariate
    shift. Naive metric: relative change of mean + relative change of
    std, both normalized by baseline magnitude.
    """

    def __init__(self, config: DriftConfig | None = None):
        self.config = config or DriftConfig()
        self._baseline: list[float] = []
        self._recent: list[float] = []

    def update(self, value: float) -> None:
        self._recent.append(value)
        if len(self._recent) > self.config.recent_size:
            self._recent.pop(0)
        if len(self._baseline) < self.config.baseline_size:
            self._baseline.append(value)

    def drift_score(self) -> float:
        cfg = self.config
        if len(self._baseline) < cfg.baseline_size or len(self._recent) < cfg.recent_size:
            return 0.0
        baseline = np.asarray(self._baseline, dtype=float)
        recent = np.asarray(self._recent[-cfg.recent_size :], dtype=float)
        denom = max(abs(baseline.mean()), 1e-9)
        mean_shift = abs(recent.mean() - baseline.mean()) / denom
        std_shift = (
            abs(recent.std(ddof=0) - baseline.std(ddof=0)) / max(abs(baseline.std(ddof=0)), 1e-9)
            if baseline.std(ddof=0) > 0 else 0
        )
        score = 0.5 * mean_shift + 0.5 * std_shift
        return min(1.0, float(score))


class WalkForwardTrainer:
    """Purged K-fold CV training scaffold.

    Trains one estimator per fold on time-respecting splits with embargo.
    Returns per-fold metrics (accuracy for direction classifier).
    """

    def __init__(self, n_splits: int = 5, embargo: int = 5):
        self.n_splits = n_splits
        self.embargo = embargo

    def splits(
        self,
        n: int,
        min_train: int = 60,
    ) -> list[tuple[int, int, int, int]]:
        if n < min_train + self.n_splits:
            return []
        fold = (n - min_train) // self.n_splits
        out = []
        for k in range(self.n_splits):
            train_end = min_train + k * fold
            test_end = train_end + fold
            if test_end > n:
                test_end = n
            if train_end >= test_end:
                continue
            out.append((0, train_end, train_end + self.embargo, test_end))
        return out


__all__ = ["DriftConfig", "DriftDetector", "WalkForwardTrainer"]
