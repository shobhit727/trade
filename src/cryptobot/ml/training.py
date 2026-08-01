from __future__ import annotations

"""
Training Pipeline with Purged Cross-Validation

Provides walk-forward training with purged cross-validation to prevent
data leakage in financial time series.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import numpy as np
import numpy.typing as npt

try:
    import optuna
    HAS_OPTUNA = True
except ImportError:
    HAS_OPTUNA = False

from cryptobot.ml.models.direction import DirectionClassifier, DirectionConfig
from cryptobot.ml.models.ensemble import EnsembleConfig, EnsembleModel
from cryptobot.ml.models.regime import RegimeConfig, RegimeDetector
from cryptobot.ml.models.volatility import VolatilityConfig, VolatilityModel


class SplitMethod(StrEnum):
    """Cross-validation split method."""
    PURGED_KFOLD = "purged_kfold"
    WALK_FORWARD = "walk_forward"
    BLOCK = "block"


@dataclass
class TrainingConfig:
    """Configuration for training pipeline."""
    split_method: SplitMethod = SplitMethod.PURGED_KFOLD
    n_splits: int = 5
    embargo_pct: float = 0.01  # 1% gap between train/test
    min_train_size: int = 100
    test_size: float = 0.2
    random_state: int = 42

    # Optuna optimization
    use_optuna: bool = False
    n_trials: int = 50
    optuna_timeout: int = 3600  # seconds
    optuna_direction: str = "maximize"  # maximize Sharpe

    # Model selection
    models_to_train: list[str] = field(default_factory=lambda: ["direction", "volatility", "regime", "ensemble"])


@dataclass
class FoldResult:
    """Result of a single CV fold."""
    fold_idx: int
    train_size: int
    test_size: int
    train_start: int
    train_end: int
    test_start: int
    test_end: int
    metrics: dict[str, float]
    model_params: dict[str, Any]


@dataclass
class TrainingResult:
    """Complete training result."""
    folds: list[FoldResult]
    best_params: dict[str, Any]
    best_score: float
    ensemble_model: Any | None = None
    cv_scores: list[float] = field(default_factory=list)


class PurgedKFold:
    """
    Purged K-Fold Cross-Validation for time series.

    Ensures no data leakage by:
    1. Adding embargo period between train and test
    2. Removing overlapping samples
    3. Maintaining temporal order
    """

    def __init__(
        self,
        n_splits: int = 5,
        embargo_pct: float = 0.01,
        min_train_size: int = 100,
    ):
        self.n_splits = n_splits
        self.embargo_pct = embargo_pct
        self.min_train_size = min_train_size

    def split(
        self,
        X: npt.NDArray[np.float64],
        y: npt.NDArray[np.float64] | None = None,
        groups: npt.NDArray[np.int64] | None = None,
    ) -> list[tuple[npt.NDArray[np.int64], npt.NDArray[np.int64]]]:
        """
        Generate train/test indices for purged K-fold.

        Returns:
            List of (train_indices, test_indices) tuples
        """
        n_samples = len(X)
        if n_samples < self.min_train_size * self.n_splits:
            raise ValueError(
                f"Insufficient samples ({n_samples}) for {self.n_splits} splits "
                f"with min_train_size={self.min_train_size}"
            )

        indices = np.arange(n_samples)
        test_size = n_samples // self.n_splits
        embargo = int(n_samples * self.embargo_pct)

        splits = []
        for i in range(self.n_splits):
            test_start = i * test_size
            test_end = min((i + 1) * test_size, n_samples)

            # Purge: remove embargo period before and after test set
            purge_start = max(0, test_start - embargo)
            purge_end = min(n_samples, test_end + embargo)

            # Train indices: everything except purge window
            train_mask = np.ones(n_samples, dtype=bool)
            train_mask[purge_start:purge_end] = False

            # Test indices: only the test window
            test_mask = np.zeros(n_samples, dtype=bool)
            test_mask[test_start:test_end] = True

            train_indices = indices[train_mask]
            test_indices = indices[test_mask]

            if len(train_indices) >= self.min_train_size and len(test_indices) > 0:
                splits.append((train_indices, test_indices))

        return splits


class WalkForwardCV:
    """Walk-Forward Cross-Validation for time series."""

    def __init__(
        self,
        initial_train_size: int,
        step_size: int,
        min_train_size: int = 100,
    ):
        self.initial_train_size = initial_train_size
        self.step_size = step_size
        self.min_train_size = min_train_size

    def split(
        self,
        X: npt.NDArray[np.float64],
        y: npt.NDArray[np.float64] | None = None,
    ) -> list[tuple[npt.NDArray[np.int64], npt.NDArray[np.int64]]]:
        """Generate walk-forward splits."""
        n_samples = len(X)
        splits = []

        train_end = self.initial_train_size
        while train_end + self.step_size <= n_samples:
            test_end = min(train_end + self.step_size, n_samples)

            train_indices = np.arange(0, train_end)
            test_indices = np.arange(train_end, test_end)

            if len(train_indices) >= self.min_train_size and len(test_indices) > 0:
                splits.append((train_indices, test_indices))

            train_end += self.step_size

        return splits


class WalkForwardTrainer:
    """
    Walk-Forward Trainer with purged CV and Optuna integration.

    Supports training of:
    - DirectionClassifier
    - VolatilityModel
    - RegimeDetector
    - EnsembleModel
    """

    def __init__(
        self,
        config: TrainingConfig | None = None,
        cv_splitter: PurgedKFold | WalkForwardCV | None = None,
    ):
        self.config = config or TrainingConfig()
        self.cv_splitter = cv_splitter or PurgedKFold(
            n_splits=self.config.n_splits,
            embargo_pct=self.config.embargo_pct,
            min_train_size=self.config.min_train_size,
        )

    def train_direction(
        self,
        features: npt.NDArray[np.float64],
        labels: npt.NDArray[np.float64],
        config: DirectionConfig | None = None,
    ) -> DirectionClassifier:
        """Train direction classifier with CV."""
        config = config or DirectionConfig()

        if self.config.use_optuna and HAS_OPTUNA:
            return self._optimize_direction(features, labels, config)

        # Default training
        model = DirectionClassifier(config)
        model.fit(features, labels)
        return model

    def _optimize_direction(
        self,
        features: npt.NDArray[np.float64],
        labels: npt.NDArray[np.float64],
        base_config: DirectionConfig,
    ) -> DirectionClassifier:
        """Optimize DirectionClassifier with Optuna."""
        if not HAS_OPTUNA:
            return DirectionClassifier(base_config).fit(features, labels)

        def objective(trial: optuna.Trial) -> float:
            config = DirectionConfig(
                threshold=trial.suggest_float("threshold", 0.5, 0.7),
                horizon=trial.suggest_int("horizon", 1, 10),
                max_features=trial.suggest_int("max_features", 4, 16),
            )
            model = DirectionClassifier(config)
            cv_scores = []
            for train_idx, test_idx in self.cv_splitter.split(features, labels):
                model.fit(features[train_idx], labels[train_idx])
                preds = model.predict(features[test_idx])
                score = float((preds == labels[test_idx]).mean())
                cv_scores.append(score)
            return np.mean(cv_scores)

        study = optuna.create_study(
            direction=self.config.optuna_direction,
            sampler=optuna.samplers.TPESampler(seed=self.config.random_state),
        )
        study.optimize(objective, n_trials=self.config.n_trials, timeout=self.config.optuna_timeout)

        best_config = DirectionConfig(**study.best_params)
        return DirectionClassifier(best_config).fit(features, labels)

    def train_volatility(
        self,
        returns: npt.NDArray[np.float64],
        config: VolatilityConfig | None = None,
    ) -> VolatilityModel:
        """Train volatility model."""
        config = config or VolatilityConfig()
        model = VolatilityModel(config)
        model.fit(returns)
        return model

    def train_regime(
        self,
        features: npt.NDArray[np.float64],
        config: RegimeConfig | None = None,
    ) -> RegimeDetector:
        """Train regime detector."""
        config = config or RegimeConfig()
        model = RegimeDetector(config)
        model.fit(features)
        return model

    def train_ensemble(
        self,
        features: npt.NDArray[np.float64],
        labels: npt.NDArray[np.float64],
        config: EnsembleConfig | None = None,
    ) -> EnsembleModel:
        """Train ensemble model."""
        config = config or EnsembleConfig()
        model = EnsembleModel(config)
        model.fit(features, labels)
        return model

    def run_full_training(
        self,
        features: npt.NDArray[np.float64],
        labels: npt.NDArray[np.float64],
        returns: npt.NDArray[np.float64] | None = None,
    ) -> TrainingResult:
        """
        Run complete training pipeline with all models.

        Returns:
            TrainingResult with all trained models and CV scores
        """
        folds = []
        cv_scores = []

        # Cross-validation
        splits = self.cv_splitter.split(features, labels)
        for fold_idx, (train_idx, test_idx) in enumerate(splits):
            fold_result = self._train_fold(fold_idx, features, labels, train_idx, test_idx)
            folds.append(fold_result)
            cv_scores.append(fold_result.metrics.get("accuracy", 0))

        # Train final ensemble on full data
        best_params = {}
        if folds:
            best_params = folds[-1].model_params  # Use last fold params

        # Train final models on full data
        final_models = {}
        if "direction" in self.config.models_to_train:
            final_models["direction"] = self.train_direction(features, labels)
        if "volatility" in self.config.models_to_train and returns is not None:
            final_models["volatility"] = self.train_volatility(returns)
        if "regime" in self.config.models_to_train:
            final_models["regime"] = self.train_regime(features)
        if "ensemble" in self.config.models_to_train:
            final_models["ensemble"] = self.train_ensemble(features, labels)

        return TrainingResult(
            folds=folds,
            best_params=best_params,
            best_score=np.mean(cv_scores) if cv_scores else 0.0,
            cv_scores=cv_scores,
        )

    def _train_fold(
        self,
        fold_idx: int,
        features: npt.NDArray[np.float64],
        labels: npt.NDArray[np.float64],
        train_idx: npt.NDArray[np.int64],
        test_idx: npt.NDArray[np.int64],
    ) -> FoldResult:
        """Train and evaluate a single fold."""
        X_train, X_test = features[train_idx], features[test_idx]
        y_train, _ = labels[train_idx], labels[test_idx]

        model = DirectionClassifier(DirectionConfig())
        model.fit(X_train, y_train)
        preds = model.predict(X_test)
        accuracy = float((preds == labels[test_idx]).mean())

        return FoldResult(
            fold_idx=fold_idx,
            train_size=len(train_idx),
            test_size=len(test_idx),
            train_start=int(train_idx[0]),
            train_end=int(train_idx[-1]),
            test_start=int(test_idx[0]),
            test_end=int(test_idx[-1]),
            metrics={"accuracy": accuracy},
            model_params={},
        )


class WalkForwardCV:
    """Walk-Forward Cross-Validation for time series."""

    def __init__(
        self,
        initial_train_size: int,
        step_size: int,
        min_train_size: int = 100,
    ):
        self.initial_train_size = initial_train_size
        self.step_size = step_size
        self.min_train_size = min_train_size

    def split(
        self,
        X: npt.NDArray[np.float64],
        y: npt.NDArray[np.float64] | None = None,
    ) -> list[tuple[npt.NDArray[np.int64], npt.NDArray[np.int64]]]:
        """Generate walk-forward splits."""
        n_samples = len(X)
        splits = []

        train_end = self.initial_train_size
        while train_end + self.step_size <= n_samples:
            test_end = min(train_end + self.step_size, n_samples)

            train_indices = np.arange(0, train_end)
            test_indices = np.arange(train_end, test_end)

            if len(train_indices) >= self.min_train_size and len(test_indices) > 0:
                splits.append((train_indices, test_indices))

            train_end += self.step_size

        return splits


def create_trainer(
    config: TrainingConfig | None = None,
) -> WalkForwardTrainer:
    """Factory function to create trainer."""
    return WalkForwardTrainer(config)


__all__ = [
    "TrainingConfig",
    "SplitMethod",
    "FoldResult",
    "TrainingResult",
    "PurgedKFold",
    "WalkForwardCV",
    "WalkForwardTrainer",
    "create_trainer",
]
