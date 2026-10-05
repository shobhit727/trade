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


from dataclasses import fields

import pandas as pd
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
from cryptobot.ml.models.regime import RegimeConfig, RegimeDetector, RegimeMethod
from cryptobot.ml.models.volatility import VolatilityConfig, VolatilityMethod, VolatilityModel
from cryptobot.ml.training import (
    PurgedKFold,
    TrainingConfig,
    WalkForwardCV,
    WalkForwardTrainer,
)

HAS_PANDAS = True

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


# Default search spaces per model type.
#
# Issue #27: the previous spaces suggested fields that do not exist on the model
# configs (n_estimators/max_depth/learning_rate/... for direction; alpha/tol/... for
# volatility/regime), so every Optuna trial raised TypeError on config construction.
# These spaces match the actual dataclass fields exactly.
DEFAULT_SEARCH_SPACES = {
    "direction": ModelSearchSpace(
        model_type="direction",
        parameters=[
            ParameterSpace("threshold", "float", low=0.50, high=0.70, step=0.01),
            ParameterSpace("horizon", "int", low=1, high=20),
            ParameterSpace("max_features", "int", low=2, high=16),
        ],
        fixed_params={},
    ),
    "volatility": ModelSearchSpace(
        model_type="volatility",
        parameters=[
            ParameterSpace("method", "categorical", choices=["ewma", "realized", "garch", "quantile"]),
            ParameterSpace("window", "int", low=10, high=120),
            ParameterSpace("lambda_", "float", low=0.90, high=0.99, step=0.005),
            ParameterSpace("horizon", "int", low=1, high=20),
        ],
        fixed_params={},
    ),
    "regime": ModelSearchSpace(
        model_type="regime",
        parameters=[
            ParameterSpace("method", "categorical", choices=["hmm", "kmeans", "gmm", "threshold"]),
            ParameterSpace("n_regimes", "int", low=2, high=5),
            ParameterSpace("window", "int", low=20, high=120),
            ParameterSpace("min_duration", "int", low=1, high=10),
        ],
        fixed_params={},
    ),
    "ensemble": ModelSearchSpace(
        model_type="ensemble",
        parameters=[
            ParameterSpace("meta_learner", "categorical", choices=["weighted_vote", "logistic_regression"]),
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

        # Overall optimization per model type. Only types whose evaluator produces
        # the configured objective metric are comparable for best_overall — e.g.
        # SHARPE exists only for signal models (direction/ensemble), while
        # volatility/regime report their own unsupervised proxies (#27).
        for model_type in model_types:
            if model_type not in self.search_spaces:
                continue

            result = self._optimize_model_type(
                symbol, model_type,
                features=features, labels=labels,
                returns=returns
            )
            all_trials.extend(result.all_trials)

            score = result.best_metrics.get(self.objective_metric.value)
            if score is None:
                continue
            if best_overall is None or score > best_score:
                best_score = score
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

        def objective(trial) -> float:
            """Optuna objective function."""
            # Sample parameters
            params = _search_space.to_optuna_params(trial)

            # Add fixed params
            params = {**_search_space.fixed_params, **params}

            # Create model config
            model_config = self._create_model_config(model_type, params)

            # Cross-validation
            metric_values = {}

            for _fold_idx, (train_idx, test_idx) in enumerate(self.cv_splitter.split(features, labels)):
                X_train, X_test = features[train_idx], features[test_idx]
                y_train = labels[train_idx]

                # Train model — fit signature differs per model type (issue #27):
                # VolatilityModel.fit(returns), RegimeDetector.fit(features),
                # DirectionClassifier/EnsembleModel.fit(X, y).
                model = self._create_model(model_type, model_config)
                if model_type == "volatility":
                    if returns is None:
                        if HAS_OPTUNA:
                            raise optuna.TrialPruned()
                        raise ValueError("volatility optimization requires `returns`")
                    model.fit(returns[train_idx])
                elif model_type == "regime":
                    model.fit(X_train)
                else:
                    model.fit(X_train, y_train)

                # Evaluate on the held-out fold only
                metrics = self._evaluate_model(
                    model,
                    model_type,
                    X_test,
                    labels[test_idx],
                    returns[test_idx] if returns is not None else None,
                )

                # Record all metrics
                for k, v in metrics.items():
                    if k not in metric_values:
                        metric_values[k] = []
                    metric_values[k].append(v)

            # Calculate mean metrics
            mean_metrics = {k: np.mean(v) for k, v in metric_values.items()}

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
            show_progress_bar=False,
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
        """Train with default parameters, evaluated OUT-OF-SAMPLE (issue #27).

        The previous fallback scored predictions on the training data itself —
        in-sample numbers drove best_overall selection. Now every fold's test
        segment is scored via the same evaluator used by the Optuna path.
        """
        model_config = self._create_model_config(model_type, {})
        fold_metrics: list[dict[str, float]] = []

        for _train_idx, test_idx in self.cv_splitter.split(features, labels):
            X_test = features[test_idx]
            y_test = labels[test_idx]
            returns_test = returns[test_idx] if returns is not None else None

            try:
                train_idx_full = self._fold_train_indices(features, test_idx)
                model = self._create_model(model_type, model_config)
                if model_type == "volatility":
                    if returns is None:
                        continue
                    model.fit(returns[train_idx_full])
                elif model_type == "regime":
                    model.fit(features[train_idx_full])
                else:
                    model.fit(features[train_idx_full], labels[train_idx_full])
            except Exception as e:  # noqa: BLE001 - skip degenerate folds
                logger.debug("default-path fold skipped (%s): %s", model_type, e)
                continue

            fold_metrics.append(self._evaluate_model(model, model_type, X_test, y_test, returns_test))

        metrics: dict[str, float] = {}
        if fold_metrics:
            keys = fold_metrics[0].keys()
            metrics = {
                k: float(np.mean([m.get(k, 0.0) for m in fold_metrics]))
                for k in keys
            }

        return SymbolOptimizationResult(
            symbol=symbol,
            model_type=model_type,
            best_params={},
            best_metrics=metrics,
            all_trials=[],
        )

    def _fold_train_indices(
        self,
        features: npt.NDArray[np.float64],
        test_idx: npt.NDArray[np.int64],
    ) -> npt.NDArray[np.int64]:
        """All indices before the test fold start (walk-forward style fallback)."""
        start = int(np.min(test_idx)) if len(test_idx) else len(features)
        return np.arange(0, max(start, 1))

    def _create_model_config(self, model_type: str, params: dict[str, Any]) -> Any:
        """Create model config from parameters.

        Filters sampled params down to fields the dataclass actually defines and
        coerces string choices into the StrEnum types the models compare against
        (issue #27 — unknown kwargs used to raise TypeError on every trial).
        """
        config_cls = {
            "direction": DirectionConfig,
            "volatility": VolatilityConfig,
            "regime": RegimeConfig,
            "ensemble": EnsembleConfig,
        }.get(model_type)
        if config_cls is None:
            raise ValueError(f"Unknown model type: {model_type}")

        valid = {f.name for f in fields(config_cls)}
        kwargs = {k: v for k, v in params.items() if k in valid}

        if model_type == "volatility" and "method" in kwargs:
            kwargs["method"] = VolatilityMethod(str(kwargs["method"]).lower())
        if model_type == "regime" and "method" in kwargs:
            kwargs["method"] = RegimeMethod(str(kwargs["method"]).lower())

        return config_cls(**kwargs)

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
        model_type: str,
        X_test: npt.NDArray[np.float64],
        y_test: npt.NDArray[np.float64],
        returns_test: npt.NDArray[np.float64] | None = None,
    ) -> dict[str, float]:
        """Evaluate a fitted model on its held-out fold (issue #27).

        Signal models (direction / ensemble) get classification plus TRADING
        metrics computed from the signals applied to the fold's realized returns
        — previously the SHARPE objective was never produced at all. Volatility
        is scored by forecast RMSE vs realized rolling vol; regimes by label
        persistence.
        """
        if model_type == "volatility":
            return self._evaluate_volatility(model, returns_test)
        if model_type == "regime":
            return self._evaluate_regime(model, X_test)

        preds = np.asarray(model.predict(X_test)).ravel()
        y_true = np.asarray(y_test).ravel()
        n = min(len(preds), len(y_true))
        preds, y_true = preds[:n], y_true[:n]

        metrics: dict[str, float] = {
            "accuracy": float(accuracy_score(y_true, preds)),
            "f1": float(f1_score(y_true, preds, average="weighted", zero_division=0)),
            "precision": float(precision_score(y_true, preds, average="weighted", zero_division=0)),
            "recall": float(recall_score(y_true, preds, average="weighted", zero_division=0)),
        }

        if hasattr(model, "predict_proba"):
            try:
                probas = np.asarray(model.predict_proba(X_test))
                if probas.ndim == 2 and probas.shape[1] >= 2:
                    metrics["log_loss"] = float(log_loss(y_true[: len(probas)], probas))
                    metrics["roc_auc"] = float(roc_auc_score(y_true[: len(probas)], probas[:, 1]))
            except Exception:
                pass

        # Trading performance of the signal on this fold's realized returns
        r = np.zeros(n) if returns_test is None else np.asarray(returns_test, dtype=float).ravel()[:n]
        position = np.where(preds > 0, 1.0, 0.0)  # long-if-signal / flat
        strat = position * r

        mean_ret = float(np.mean(strat)) if n else 0.0
        std_ret = float(np.std(strat, ddof=1)) if n > 1 else 0.0
        downside_dev = float(np.sqrt(np.mean(np.minimum(strat, 0.0) ** 2))) if n else 0.0

        equity = np.cumprod(1.0 + strat)
        peak = np.maximum.accumulate(equity)
        drawdowns = (peak - equity) / np.where(peak > 0, peak, 1.0)
        max_dd = float(np.max(drawdowns)) if n else 0.0
        total_return = float(equity[-1] - 1.0) if n else 0.0

        metrics.update({
            "sharpe": mean_ret / std_ret * (252 ** 0.5) if std_ret > 0 else 0.0,   # daily-bar assumption
            "sortino": mean_ret / downside_dev * (252 ** 0.5) if downside_dev > 0 else 0.0,
            "calmar": total_return / max_dd if max_dd > 0 else 0.0,
            "max_drawdown": max_dd,
            "total_return": total_return,
        })
        return metrics

    def _evaluate_volatility(
        self,
        model: Any,
        returns_test: npt.NDArray[np.float64] | None,
    ) -> dict[str, float]:
        """Score volatility forecasts by RMSE against realized rolling vol."""
        empty = {"vol_rmse": float("inf"), "objective": float("-inf")}
        if returns_test is None or len(returns_test) < 3:
            return empty
        try:
            forecasts = np.asarray(model.forecast_series(returns_test), dtype=float)
        except Exception:
            return empty
        window = max(int(getattr(model.config, "window", 20)), 2)
        realized = (
            pd.Series(returns_test).rolling(window).std().bfill().to_numpy()
            if HAS_PANDAS
            else np.full(len(returns_test), float(np.std(returns_test)))
        )
        mask = np.isfinite(forecasts) & np.isfinite(realized)
        if not mask.any():
            return empty
        rmse = float(np.sqrt(np.mean((forecasts[mask] - realized[mask]) ** 2)))
        return {"vol_rmse": rmse, "objective": -rmse}

    def _evaluate_regime(
        self,
        model: Any,
        X_test: npt.NDArray[np.float64],
    ) -> dict[str, float]:
        """Score regime labels by persistence (fraction of unchanged transitions)."""
        try:
            labels = np.asarray(model.predict(X_test)).ravel()
        except Exception:
            return {"regime_persistence": 0.0, "objective": 0.0}
        if len(labels) < 2:
            return {"regime_persistence": 0.0, "objective": 0.0}
        changes = int(np.sum(labels[1:] != labels[:-1]))
        persistence = 1.0 - changes / (len(labels) - 1)
        return {"regime_persistence": float(persistence), "objective": float(persistence)}

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


