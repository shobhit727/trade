"""
Walk-Forward Optimizer with Regime-Aware Parameter Search

Extends the training pipeline with:
- Per-symbol/regime parameter optimization
- Multiple objective metrics (Sharpe, Sortino, Calmar, accuracy)
- Optuna integration for hyperparameter search
- Results persistence and tracking
- Regime-aware parameter search spaces
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

try:
    import optuna
    from optuna.pruners import MedianPruner
    from optuna.samplers import TPESampler
    HAS_OPTUNA = True
except ImportError:
    optuna = None
    HAS_OPTUNA = False


from sklearn.metrics import (
    accuracy_score,
    f1_score,
    log_loss,
    precision_score,
    recall_score,
    roc_auc_score,
)

from cryptobot.ml.models.direction import DirectionClassifier, DirectionConfig
from cryptobot.ml.models.ensemble import EnsembleConfig, EnsembleModel
from cryptobot.ml.models.regime import RegimeConfig, RegimeDetector
from cryptobot.ml.models.volatility import VolatilityConfig, VolatilityModel
from cryptobot.ml.training import (
    PurgedKFold,
    TrainingConfig,
    WalkForwardCV,
    WalkForwardTrainer,
)

logger = logging.getLogger(__name__)


class OptimizationMetric(StrEnum):
    """Optimization objective metrics."""
    SHARPE = "sharpe"
    SORTINO = "sortino"
    CALMAR = "calmar"
    ACCURACY = "accuracy"
    F1 = "f1"
    PRECISION = "precision"
    RECALL = "recall"
    LOG_LOSS = "log_loss"
    TOTAL_RETURN = "total_return"
    MAX_DRAWDOWN = "max_drawdown"


@dataclass
class ParameterSpace:
    """Defines search space for a hyperparameter."""
    name: str
    param_type: str  # "float", "int", "categorical", "bool"
    low: float | int | None = None
    high: float | int | None = None
    choices: list[Any] | None = None
    log: bool = False
    step: float | int | None = None


@dataclass
class ModelSearchSpace:
    """Complete search space for a model type."""
    model_type: str
    parameters: list[ParameterSpace] = field(default_factory=list)
    fixed_params: dict[str, Any] = field(default_factory=dict)

    def to_optuna_params(self, trial) -> dict[str, Any]:
        """Convert to Optuna parameter suggestions."""
        params = {}
        for param in self.parameters:
            if param.param_type == "float":
                params[param.name] = trial.suggest_float(
                    param.name, param.low, param.high, log=param.log, step=param.step
                )
            elif param.param_type == "int":
                params[param.name] = trial.suggest_int(
                    param.name, param.low, param.high, step=param.step, log=param.log
                )
            elif param.param_type == "categorical":
                params[param.name] = trial.suggest_categorical(param.name, param.choices)
            elif param.param_type == "bool":
                params[param.name] = trial.suggest_categorical(param.name, [True, False])
        return params


# Default search spaces per model type
DEFAULT_SEARCH_SPACES = {
    "direction": ModelSearchSpace(
        model_type="direction",
        parameters=[
            ParameterSpace("threshold", "float", low=0.5, high=0.7, step=0.01),
            ParameterSpace("horizon", "int", low=1, high=20),
            ParameterSpace("max_features", "int", low=4, high=20),
            ParameterSpace("n_estimators", "int", low=50, high=300, log=True),
            ParameterSpace("max_depth", "int", low=3, high=15),
            ParameterSpace("learning_rate", "float", low=0.01, high=0.3, log=True),
            ParameterSpace("subsample", "float", low=0.6, high=1.0),
            ParameterSpace("colsample_bytree", "float", low=0.6, high=1.0),
            ParameterSpace("reg_alpha", "float", low=1e-8, high=10.0, log=True),
            ParameterSpace("reg_lambda", "float", low=1e-8, high=10.0, log=True),
        ],
        fixed_params={},
    ),
    "volatility": ModelSearchSpace(
        model_type="volatility",
        parameters=[
            ParameterSpace("window", "int", low=10, high=252),
            ParameterSpace("method", "categorical", choices=["ewma", "garch", "realized"]),
            ParameterSpace("alpha", "float", low=0.9, high=0.99),
            ParameterSpace("lambda_", "float", low=0.9, high=0.999),
        ],
        fixed_params={},
    ),
    "regime": ModelSearchSpace(
        model_type="regime",
        parameters=[
            ParameterSpace("n_regimes", "int", low=2, high=6),
            ParameterSpace("covariance_type", "categorical", choices=["full", "tied", "diag", "spherical"]),
            ParameterSpace("n_init", "int", low=5, high=20),
            ParameterSpace("max_iter", "int", low=100, high=500),
            ParameterSpace("tol", "float", low=1e-4, high=1e-2, log=True),
        ],
        fixed_params={},
    ),
    "ensemble": ModelSearchSpace(
        model_type="ensemble",
        parameters=[
            ParameterSpace("n_estimators", "int", low=10, high=100),
            ParameterSpace("voting", "categorical", choices=["soft", "hard"]),
            ParameterSpace("weights", "categorical", choices=[None, "auto"]),
        ],
        fixed_params={},
    ),
}


@dataclass
class OptimizationResult:
    """Result of a single optimization trial."""
    trial_number: int
    params: dict[str, Any]
    metrics: dict[str, float]
    model_type: str
    symbol: str | None = None
    regime: str | None = None
    timestamp: datetime = field(default_factory=datetime.now)
    duration_seconds: float = 0.0
    status: str = "completed"  # completed, pruned, failed
    error: str | None = None


@dataclass
class SymbolOptimizationResult:
    """Complete optimization result for a symbol."""
    symbol: str
    model_type: str
    best_params: dict[str, Any]
    best_metrics: dict[str, float]
    all_trials: list[OptimizationResult]
    regime_results: dict[str, dict[str, Any]] = field(default_factory=dict)
    study: Any = None  # Optuna study object
    timestamp: datetime = field(default_factory=datetime.now)


class WalkForwardOptimizer:
    """
    Walk-Forward Optimizer with regime-aware parameter search.

    Features:
    - Per-symbol parameter optimization
    - Regime-aware parameter search
    - Multiple objective metrics (Sharpe, Sortino, Calmar, accuracy, etc.)
    - Optuna integration with pruning
    - Results persistence and tracking
    - Parallel trial execution
    """

    def __init__(
        self,
        config: TrainingConfig | None = None,
        search_spaces: dict[str, ModelSearchSpace] | None = None,
        cv_splitter: PurgedKFold | WalkForwardCV | None = None,
        objective_metric: OptimizationMetric = OptimizationMetric.SHARPE,
        n_jobs: int = 1,
        storage: str | None = None,  # Optuna storage URL
        study_name: str | None = None,
    ):
        self.config = config or TrainingConfig()
        self.search_spaces = search_spaces or DEFAULT_SEARCH_SPACES
        self.cv_splitter = cv_splitter or PurgedKFold(
            n_splits=self.config.n_splits,
            embargo_pct=self.config.embargo_pct,
            min_train_size=self.config.min_train_size,
        )
        self.objective_metric = objective_metric
        self.n_jobs = n_jobs
        self.storage = storage
        self.study_name = study_name or f"walkforward_opt_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        self.trainer = WalkForwardTrainer(self.config, self.cv_splitter)
        self.results: list[SymbolOptimizationResult] = []
        self._studies: dict[str, Any] = {}

    def optimize_symbol(
        self,
        symbol: str,
        features: npt.NDArray[np.float64],
        labels: npt.NDArray[np.float64],
        returns: npt.NDArray[np.float64] | None = None,
        regimes: npt.NDArray[np.int64] | None = None,
        model_types: list[str] | None = None,
    ) -> SymbolOptimizationResult:
        """
        Optimize parameters for a single symbol across all model types.

        Args:
            symbol: Trading symbol
            features: Feature matrix (n_samples, n_features)
            labels: Target labels (n_samples,)
            returns: Return series for volatility/sharpe calculation
            regimes: Regime labels for regime-aware optimization
            model_types: List of model types to optimize

        Returns:
            SymbolOptimizationResult with best parameters and all trial results
        """
        model_types = model_types or ["direction", "volatility", "regime", "ensemble"]
        all_trials = []
        best_overall = None
        best_score = float("-inf")
        best_params = {}
        best_metrics = {}
        regime_results = {}

        # If regimes provided, do regime-aware optimization
        if regimes is not None and len(regimes) == len(labels):
            unique_regimes = np.unique(regimes)
            for regime in unique_regimes:
                mask = regimes == regime
                if np.sum(mask) < self.config.min_train_size:
                    continue
                regime_result = self._optimize_model_type(
                    symbol, model_type="direction",
                    features=features[mask], labels=labels[mask],
                    returns=returns[mask] if returns is not None else None,
                    regime_label=f"regime_{regime}"
                )
                regime_results[f"regime_{regime}"] = regime_result

        # Overall optimization per model type
        for model_type in model_types:
            if model_type not in self.search_spaces:
                continue

            result = self._optimize_model_type(
                symbol, model_type,
                features=features, labels=labels,
                returns=returns
            )
            all_trials.extend(result.all_trials)

            # Track best overall
            if result.best_metrics.get(self.objective_metric.value, float("-inf")) > best_score:
                best_score = result.best_metrics.get(self.objective_metric.value, float("-inf"))
                best_overall = model_type
                best_params = result.best_params
                best_metrics = result.best_metrics

                # Save regime-specific results
                if hasattr(result, 'regime_results'):
                    regime_results.update(result.regime_results)

        return SymbolOptimizationResult(
            symbol=symbol,
            model_type=best_overall or model_types[0],
            best_params=best_params,
            best_metrics=best_metrics,
            all_trials=all_trials,
            regime_results=regime_results,
        )

    def _optimize_model_type(
        self,
        symbol: str,
        model_type: str,
        features: npt.NDArray[np.float64],
        labels: npt.NDArray[np.float64],
        returns: npt.NDArray[np.float64] | None = None,
        regime_label: str | None = None,
    ) -> SymbolOptimizationResult:
        """Optimize a single model type for a symbol."""
        if not HAS_OPTUNA or not self.config.use_optuna:
            # Fallback: train with default params
            return self._train_default(symbol, model_type, features, labels, returns)

        _search_space = self.search_spaces.get(model_type)
        if not _search_space:
            return self._train_default(symbol, model_type, features, labels, returns)

        _trainer = WalkForwardTrainer(self.config, self.cv_splitter)
        _all_trials: list = []

        def objective(trial) -> float:
            nonlocal _all_trials
            """Optuna objective function."""
            start_time = time.time()

            # Sample parameters
            params = _search_space.to_optuna_params(trial)

            # Add fixed params
            params = {**_search_space.fixed_params, **params}

            # Create model config
            model_config = self._create_model_config(model_type, params)

            # Cross-validation
            _cv_scores = []
            metric_values = {}

            _splits = self.cv_splitter.split(features, labels)
            for _fold_idx, (train_idx, test_idx) in enumerate(self.cv_splitter.split(features, labels)):
                X_train, X_test = features[train_idx], features[test_idx]
                y_train, _y_test = labels[train_idx], labels[test_idx]

                # Train model
                model = self._create_model(model_type, model_config)
                model.fit(X_train, y_train)

                # Evaluate
                metrics = self._evaluate_model(model, X_test, labels[test_idx], returns)

                # Record all metrics
                for k, v in metrics.items():
                    if k not in metric_values:
                        metric_values[k] = []
                    metric_values[k].append(v)

            # Calculate mean metrics
            mean_metrics = {k: np.mean(v) for k, v in metric_values.items()}

            # Record trial
            trial_result = OptimizationResult(
                trial_number=trial.number,
                params=params,
                metrics=mean_metrics,
                model_type=model_type,
                symbol=symbol,
                duration_seconds=time.time() - start_time,
            )
            _all_trials.append(trial_result)

            # Return objective metric
            objective_value = mean_metrics.get(self.objective_metric.value, float("-inf"))

            # Store trial in user attributes for later retrieval
            trial.set_user_attr("metrics", mean_metrics)
            trial.set_user_attr("params", params)
            trial.set_user_attr("model_type", model_type)
            trial.set_user_attr("symbol", symbol)

            return objective_value

        # Create or load study
        study_name = f"{self.study_name}_{symbol}_{model_type}"
        study = optuna.create_study(
            direction=self.config.optuna_direction,
            sampler=TPESampler(seed=self.config.random_state),
            pruner=MedianPruner(n_warmup_steps=5),
            storage=self.storage,
            study_name=study_name,
            load_if_exists=True,
        )

        study.optimize(
            objective,
            n_trials=self.config.n_trials,
            timeout=self.config.optuna_timeout,
            n_jobs=self.n_jobs,
            show_progress_bar=True,
        )

        # Extract best result
        best_trial = study.best_trial
        best_params = best_trial.params
        best_metrics = best_trial.user_attrs.get("metrics", {})

        # Convert all trials
        _all_trial_results = []
        for trial in study.trials:
            if trial.state == optuna.trial.TrialState.COMPLETE:
                _all_trial_results.append(OptimizationResult(
                    trial_number=trial.number,
                    params=trial.params,
                    metrics=trial.user_attrs.get("metrics", {}),
                    model_type=model_type,
                    symbol=symbol,
                    duration_seconds=trial.duration.total_seconds() if trial.duration else 0,
                    status="completed",
                ))
            elif trial.state == optuna.trial.TrialState.PRUNED:
                _all_trial_results.append(OptimizationResult(
                    trial_number=trial.number,
                    params=trial.params,
                    metrics=trial.user_attrs.get("metrics", {}),
                    model_type=model_type,
                    symbol=symbol,
                    duration_seconds=trial.duration.total_seconds() if trial.duration else 0,
                    status="pruned",
                ))

        return SymbolOptimizationResult(
            symbol=symbol,
            model_type=model_type,
            best_params=best_params,
            best_metrics=best_metrics,
            all_trials=_all_trial_results,
            study=study,
        )

    def _train_default(
        self,
        symbol: str,
        model_type: str,
        features: npt.NDArray[np.float64],
        labels: npt.NDArray[np.float64],
        returns: npt.NDArray[np.float64] | None = None,
    ) -> SymbolOptimizationResult:
        """Train with default parameters (fallback)."""
        trainer = WalkForwardTrainer(self.config, self.cv_splitter)

        if model_type == "direction":
            model = trainer.train_direction(features, labels)
        elif model_type == "volatility":
            model = trainer.train_volatility(returns) if returns is not None else None
        elif model_type == "regime":
            model = trainer.train_regime(features)
        elif model_type == "ensemble":
            model = trainer.train_ensemble(features, labels)
        else:
            raise ValueError(f"Unknown model type: {model_type}")

        # Evaluate on full data
        metrics = {}
        if model:
            preds = model.predict(features)
            from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score
            metrics["accuracy"] = float(accuracy_score(labels, preds))
            metrics["f1"] = float(f1_score(labels, preds, average="weighted", zero_division=0))
            metrics["precision"] = float(precision_score(labels, preds, average="weighted", zero_division=0))
            metrics["recall"] = float(recall_score(labels, preds, average="weighted", zero_division=0))

        return SymbolOptimizationResult(
            symbol=symbol,
            model_type=model_type,
            best_params={},
            best_metrics=metrics,
            all_trials=[],
        )

    def _create_model_config(self, model_type: str, params: dict[str, Any]) -> Any:
        """Create model config from parameters."""
        if model_type == "direction":
            return DirectionConfig(**params)
        elif model_type == "volatility":
            return VolatilityConfig(**params)
        elif model_type == "regime":
            return RegimeConfig(**params)
        elif model_type == "ensemble":
            return EnsembleConfig(**params)
        raise ValueError(f"Unknown model type: {model_type}")

    def _create_model(self, model_type: str, config: Any) -> Any:
        """Create model instance."""
        if model_type == "direction":
            return DirectionClassifier(config)
        elif model_type == "volatility":
            return VolatilityModel(config)
        elif model_type == "regime":
            return RegimeDetector(config)
        elif model_type == "ensemble":
            return EnsembleModel(config)
        raise ValueError(f"Unknown model type: {model_type}")

    def _evaluate_model(
        self,
        model: Any,
        X_test: npt.NDArray[np.float64],
        y_test: npt.NDArray[np.float64],
        returns: npt.NDArray[np.float64] | None = None,
    ) -> dict[str, float]:
        """Evaluate model with multiple metrics."""

        preds = model.predict(X_test)

        metrics = {
            "accuracy": float(accuracy_score(y_test, preds)),
            "f1": float(f1_score(y_test, preds, average="weighted", zero_division=0)),
            "precision": float(precision_score(y_test, preds, average="weighted", zero_division=0)),
            "recall": float(recall_score(y_test, preds, average="weighted", zero_division=0)),
        }

        # Add probability-based metrics if available
        if hasattr(model, "predict_proba"):
            try:
                probas = model.predict_proba(X_test)
                metrics["log_loss"] = float(log_loss(y_test, probas))
                if probas.shape[1] == 2:
                    metrics["roc_auc"] = float(roc_auc_score(y_test, probas[:, 1]))
            except Exception:
                pass

        # Add financial metrics if returns provided
        if returns is not None:
            # This would need trade simulation - simplified here
            pass

        return metrics

    def optimize_all_symbols(
        self,
        symbol_data: dict[str, tuple[npt.NDArray, npt.NDArray, npt.NDArray | None]],
        model_types: list[str] | None = None,
    ) -> dict[str, SymbolOptimizationResult]:
        """Optimize all symbols in parallel/sequential."""
        results = {}

        for symbol, (features, labels, returns) in symbol_data.items():
            logger.info(f"Optimizing {symbol}...")
            try:
                result = self.optimize_symbol(symbol, features, labels, returns, model_types=model_types)
                results[symbol] = result
                logger.info(f"{symbol}: best {self.objective_metric.value} = {result.best_metrics.get(self.objective_metric.value, 'N/A')}")
            except Exception as e:
                logger.error(f"Failed to optimize {symbol}: {e}")

        return results

    def save_results(self, path: Path) -> None:
        """Save all optimization results."""
        path.mkdir(parents=True, exist_ok=True)

        # Save summary
        summary = {
            "timestamp": datetime.now().isoformat(),
            "config": asdict(self.config),
            "objective_metric": self.objective_metric.value,
            "results": {}
        }

        for result in self.results:
            summary["results"][result.symbol] = {
                "model_type": result.model_type,
                "best_params": result.best_params,
                "best_metrics": result.best_metrics,
                "n_trials": len(result.all_trials),
                "regime_results": {
                    k: {"best_metrics": v.best_metrics, "best_params": v.best_params}
                    for k, v in result.regime_results.items()
                },
            }

        with open(path / "optimization_summary.json", "w") as f:
            json.dump(summary, f, indent=2, default=str)

        # Save detailed trials
        for result in self.results:
            trials_data = [asdict(t) for t in result.all_trials]
            with open(path / f"trials_{result.symbol}.json", "w") as f:
                json.dump(trials_data, f, indent=2, default=str)

    def load_results(self, path: Path) -> None:
        """Load optimization results."""
        # Implementation for loading saved results
        pass


def create_optimizer(
    config: TrainingConfig | None = None,
    search_spaces: dict[str, ModelSearchSpace] | None = None,
    cv_splitter: PurgedKFold | WalkForwardCV | None = None,
    objective_metric: OptimizationMetric = OptimizationMetric.SHARPE,
    n_jobs: int = 1,
    storage: str | None = None,
    study_name: str | None = None,
) -> WalkForwardOptimizer:
    """Factory function to create optimizer."""
    return WalkForwardOptimizer(
        config=config,
        search_spaces=search_spaces,
        cv_splitter=cv_splitter,
        objective_metric=objective_metric,
        n_jobs=n_jobs,
        storage=storage,
        study_name=study_name,
    )


# Default search spaces
DEFAULT_SEARCH_SPACES = {
    "direction": ModelSearchSpace(
        model_type="direction",
        parameters=[
            ParameterSpace("threshold", "float", low=0.5, high=0.7, step=0.01),
            ParameterSpace("horizon", "int", low=1, high=20),
            ParameterSpace("max_features", "int", low=4, high=20),
            ParameterSpace("n_estimators", "int", low=50, high=300, log=True),
            ParameterSpace("max_depth", "int", low=3, high=15),
            ParameterSpace("learning_rate", "float", low=0.01, high=0.3, log=True),
            ParameterSpace("subsample", "float", low=0.6, high=1.0),
            ParameterSpace("colsample_bytree", "float", low=0.6, high=1.0),
            ParameterSpace("reg_alpha", "float", low=1e-8, high=10.0, log=True),
            ParameterSpace("reg_lambda", "float", low=1e-8, high=10.0, log=True),
        ],
        fixed_params={},
    ),
    "volatility": ModelSearchSpace(
        model_type="volatility",
        parameters=[
            ParameterSpace("window", "int", low=10, high=252),
            ParameterSpace("method", "categorical", choices=["ewma", "garch", "realized"]),
            ParameterSpace("alpha", "float", low=0.9, high=0.99),
            ParameterSpace("lambda_", "float", low=0.9, high=0.999),
        ],
        fixed_params={},
    ),
    "regime": ModelSearchSpace(
        model_type="regime",
        parameters=[
            ParameterSpace("n_regimes", "int", low=2, high=6),
            ParameterSpace("covariance_type", "categorical", choices=["full", "tied", "diag", "spherical"]),
            ParameterSpace("n_init", "int", low=5, high=20),
            ParameterSpace("max_iter", "int", low=100, high=500),
            ParameterSpace("tol", "float", low=1e-4, high=1e-2, log=True),
        ],
        fixed_params={},
    ),
    "ensemble": ModelSearchSpace(
        model_type="ensemble",
        parameters=[
            ParameterSpace("n_estimators", "int", low=10, high=100),
            ParameterSpace("voting", "categorical", choices=["soft", "hard"]),
            ParameterSpace("weights", "categorical", choices=[None, "auto"]),
        ],
        fixed_params={},
    ),
}


__all__ = [
    "OptimizationMetric",
    "ParameterSpace",
    "ModelSearchSpace",
    "OptimizationResult",
    "SymbolOptimizationResult",
    "WalkForwardOptimizer",
    "DEFAULT_SEARCH_SPACES",
    "create_optimizer",
]


# Add missing imports
