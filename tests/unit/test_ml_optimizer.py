"""Tests for cryptobot.ml.optimizer (Walk-Forward Optimizer)."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from cryptobot.ml.optimizer import (
    DEFAULT_SEARCH_SPACES,
    ModelSearchSpace,
    OptimizationMetric,
    OptimizationResult,
    ParameterSpace,
    SymbolOptimizationResult,
    WalkForwardOptimizer,
    create_optimizer,
)
from cryptobot.ml.training import PurgedKFold, TrainingConfig, WalkForwardCV


def _data(n: int = 600, n_features: int = 6) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Synthetic feature matrix, labels and return series."""
    rng = np.random.default_rng(42)
    features = rng.normal(0, 1, (n, n_features))
    labels = (rng.normal(0, 1, n) > 0).astype(int)
    returns = rng.normal(0.001, 0.02, n)
    returns[:25] = 0.0
    return features, labels, returns


def _small_config() -> TrainingConfig:
    return TrainingConfig(
        n_splits=3,
        embargo_pct=0.01,
        min_train_size=40,
        n_trials=3,
        optuna_timeout=5,
    )


class _FakeTrialState:
    COMPLETE = "COMPLETE"
    PRUNED = "PRUNED"


class _FakeTrial:
    """Minimal optuna.trial.Trial stand-in for suggest_* + user attrs."""

    state = _FakeTrialState.COMPLETE
    duration = None

    def __init__(self, number: int = 0):
        self.number = number
        self.params: dict = {}
        self._attrs: dict = {}

    def suggest_float(self, name, low, high, *, log=False, step=None):
        val = low if step is None else low + step
        self.params[name] = val
        return val

    def suggest_int(self, name, low, high, *, step=None, log=False):
        val = low if step is None else low + step
        self.params[name] = val
        return val

    def suggest_categorical(self, name, choices):
        self.params[name] = choices[0]
        return choices[0]

    def set_user_attr(self, key, value):
        self._attrs[key] = value

    @property
    def user_attrs(self) -> dict:
        return self._attrs


class _FakeStudy:
    """Minimal study that runs the objective once per trial."""

    def __init__(self):
        self.trials: list[_FakeTrial] = []

    def optimize(self, objective, n_trials=1, timeout=None, n_jobs=1, show_progress_bar=False):
        for i in range(n_trials):
            trial = _FakeTrial(number=i)
            objective(trial)
            self.trials.append(trial)

    @property
    def best_trial(self) -> _FakeTrial:
        return max(
            self.trials,
            key=lambda t: t._attrs.get("metrics", {}).get("accuracy", -1),
        )


class _FakeOptuna:
    """Stand-in for the optuna module used by the optimizer."""

    class samplers:
        @staticmethod
        def TPESampler(seed):
            return object()

    class pruners:
        @staticmethod
        def MedianPruner(n_warmup_steps):
            return object()

    class trial:
        TrialState = _FakeTrialState

    @staticmethod
    def create_study(**kwargs) -> _FakeStudy:
        return _FakeStudy()


# --- enum + dataclasses -----------------------------------------------------


def test_optimization_metric_values():
    assert OptimizationMetric.SHARPE.value == "sharpe"
    assert OptimizationMetric.SORTINO.value == "sortino"
    assert OptimizationMetric.CALMAR.value == "calmar"
    assert OptimizationMetric.ACCURACY.value == "accuracy"
    assert OptimizationMetric.F1.value == "f1"
    assert OptimizationMetric.PRECISION.value == "precision"
    assert OptimizationMetric.RECALL.value == "recall"
    assert OptimizationMetric.LOG_LOSS.value == "log_loss"
    assert OptimizationMetric.TOTAL_RETURN.value == "total_return"
    assert OptimizationMetric.MAX_DRAWDOWN.value == "max_drawdown"


def test_parameter_space_defaults():
    ps = ParameterSpace("window", "int")
    assert ps.low is None
    assert ps.high is None
    assert ps.choices is None
    assert ps.log is False
    assert ps.step is None


def test_model_search_space_to_optuna_params_all_types():
    space = ModelSearchSpace(
        model_type="test",
        parameters=[
            ParameterSpace("f", "float", low=0.5, high=0.7, step=0.05),
            ParameterSpace("i", "int", low=2, high=10),
            ParameterSpace("c", "categorical", choices=["a", "b", "c"]),
            ParameterSpace("b", "bool"),
        ],
    )
    trial = _FakeTrial()
    params = space.to_optuna_params(trial)
    assert params["f"] == 0.55
    assert params["i"] == 2
    assert params["c"] == "a"
    assert params["b"] in (True, False)


def test_model_search_space_log_and_no_step():
    space = ModelSearchSpace(
        model_type="test",
        parameters=[
            ParameterSpace("lr", "float", low=0.01, high=0.3, log=True),
            ParameterSpace("n", "int", low=50, high=300, log=True),
        ],
    )
    trial = _FakeTrial()
    params = space.to_optuna_params(trial)
    assert params["lr"] == 0.01
    assert params["n"] == 50


def test_default_search_spaces_contain_all_model_types():
    assert set(DEFAULT_SEARCH_SPACES) == {"direction", "volatility", "regime", "ensemble"}
    for name, space in DEFAULT_SEARCH_SPACES.items():
        assert space.model_type == name
        assert space.parameters


def test_optimization_result_creation():
    res = OptimizationResult(
        trial_number=0,
        params={"lr": 0.1},
        metrics={"accuracy": 0.7},
        model_type="direction",
        status="completed",
    )
    assert res.trial_number == 0
    assert res.params["lr"] == 0.1
    assert res.status == "completed"


def test_symbol_optimization_result_creation():
    res = SymbolOptimizationResult(
        symbol="BTCUSDT",
        model_type="direction",
        best_params={"threshold": 0.6},
        best_metrics={"accuracy": 0.8},
        all_trials=[],
    )
    assert res.symbol == "BTCUSDT"
    assert res.best_params["threshold"] == 0.6


# --- optimizer construction -------------------------------------------------


def test_optimizer_defaults():
    opt = WalkForwardOptimizer()
    assert isinstance(opt.config, TrainingConfig)
    assert opt.n_jobs == 1
    assert opt.storage is None
    assert opt.study_name.startswith("walkforward_opt_")
    assert opt.results == []
    assert isinstance(opt.cv_splitter, PurgedKFold)


def test_optimizer_custom_splitters():
    opt = WalkForwardOptimizer(
        config=_small_config(),
        cv_splitter=WalkForwardCV(initial_train_size=80, step_size=40, min_train_size=40),
        storage="sqlite:///tmp/opt.db",
        study_name="my_study",
    )
    assert opt.study_name == "my_study"
    assert isinstance(opt.cv_splitter, WalkForwardCV)
    assert opt.storage == "sqlite:///tmp/opt.db"


def test_create_optimizer_factory():
    opt = create_optimizer(
        config=_small_config(),
        objective_metric=OptimizationMetric.ACCURACY,
        study_name="factory_study",
    )
    assert isinstance(opt, WalkForwardOptimizer)
    assert opt.objective_metric == OptimizationMetric.ACCURACY


# --- optimize_symbol / fallback training -----------------------------------


def test_optimize_symbol_default_path():
    """Fallback training (no optuna installed / use_optuna=False)."""
    opt = WalkForwardOptimizer(config=_small_config())
    features, labels, returns = _data()
    result = opt.optimize_symbol("BTCUSDT", features, labels, returns)
    assert isinstance(result, SymbolOptimizationResult)
    assert result.symbol == "BTCUSDT"
    assert result.model_type in {"direction", "volatility", "regime", "ensemble"}
    assert result.all_trials == []
    assert "accuracy" in result.best_metrics


def test_optimize_symbol_single_model_type():
    opt = WalkForwardOptimizer(config=_small_config())
    features, labels, returns = _data()
    result = opt.optimize_symbol(
        "BTCUSDT", features, labels, returns, model_types=["direction"]
    )
    assert result.model_type == "direction"
    assert result.best_metrics["accuracy"] > 0


def test_optimize_symbol_with_regimes():
    """Regime-aware path: masks split by regime label."""
    opt = WalkForwardOptimizer(config=_small_config())
    features, labels, returns = _data()
    regimes = (np.arange(len(labels)) % 2).astype(int)
    result = opt.optimize_symbol("BTCUSDT", features, labels, returns, regimes)
    assert isinstance(result, SymbolOptimizationResult)
    assert any(k.startswith("regime_") for k in result.regime_results)


def test_optimize_symbol_regime_mask_too_small_skipped():
    """Regime with too few samples is skipped (below min_train_size)."""
    opt = WalkForwardOptimizer(config=_small_config())
    features, labels, returns = _data()
    regimes = np.zeros(len(labels), dtype=int)
    regimes[:5] = 1  # second regime too small -> skipped
    result = opt.optimize_symbol("BTCUSDT", features, labels, returns, regimes)
    assert isinstance(result, SymbolOptimizationResult)


def test_optimize_symbol_unknown_model_type_falls_back():
    opt = WalkForwardOptimizer(config=_small_config())
    features, labels, returns = _data()
    result = opt.optimize_symbol(
        "BTCUSDT", features, labels, returns, model_types=["unknown_type"]
    )
    assert result.model_type == "unknown_type"


def test_optimize_symbol_unknown_search_space_model():
    """Model type present but absent from search spaces -> default training."""
    opt = WalkForwardOptimizer(config=_small_config(), search_spaces={})
    features, labels, returns = _data()
    result = opt.optimize_symbol(
        "BTCUSDT", features, labels, returns, model_types=["direction"]
    )
    assert result.model_type == "direction"


def test_optimize_symbol_optuna_path(monkeypatch):
    """Exercises the real optuna branch with a fake optuna module."""
    import cryptobot.ml.optimizer as opt_mod

    fake = _FakeOptuna()
    # The real module only defines these names when optuna is importable, so
    # expose them explicitly for the optuna branch.
    fake.TPESampler = fake.samplers.TPESampler
    fake.MedianPruner = fake.pruners.MedianPruner
    monkeypatch.setattr(opt_mod, "optuna", fake)
    monkeypatch.setattr(opt_mod, "HAS_OPTUNA", True)
    monkeypatch.setattr(opt_mod, "TPESampler", fake.samplers.TPESampler, raising=False)
    monkeypatch.setattr(opt_mod, "MedianPruner", fake.pruners.MedianPruner, raising=False)

    search_spaces = {
        "direction": ModelSearchSpace(
            model_type="direction",
            parameters=[ParameterSpace("threshold", "float", low=0.5, high=0.7, step=0.05)],
        )
    }
    config = _small_config()
    config.use_optuna = True
    opt = WalkForwardOptimizer(
        config=config,
        search_spaces=search_spaces,
        cv_splitter=WalkForwardCV(initial_train_size=200, step_size=100, min_train_size=40),
    )
    features, labels, returns = _data()
    result = opt.optimize_symbol(
        "BTCUSDT", features, labels, returns, model_types=["direction"]
    )
    assert isinstance(result, SymbolOptimizationResult)
    assert result.model_type == "direction"
    assert "threshold" in result.best_params
    assert result.all_trials, "expected trials recorded from fake study"
    assert all(t.status == "completed" for t in result.all_trials)


# --- optimize_all_symbols ---------------------------------------------------


def test_optimize_all_symbols_multiple_symbols():
    opt = WalkForwardOptimizer(config=_small_config())
    features, labels, returns = _data()
    symbol_data = {
        "BTCUSDT": (features, labels, returns),
        "ETHUSDT": (features, labels, returns),
    }
    results = opt.optimize_all_symbols(symbol_data, model_types=["direction"])
    assert set(results) == {"BTCUSDT", "ETHUSDT"}
    assert all(isinstance(r, SymbolOptimizationResult) for r in results.values())


def test_optimize_all_symbols_error_is_logged_not_raised(monkeypatch):
    opt = WalkForwardOptimizer(config=_small_config())
    features, labels, returns = _data()

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(opt, "optimize_symbol", boom)
    results = opt.optimize_all_symbols({"BTCUSDT": (features, labels, returns)})
    assert results == {}


# --- save / load ------------------------------------------------------------


def test_optimizer_save_results_writes_files(tmp_path: Path):
    opt = WalkForwardOptimizer(config=_small_config())
    features, labels, returns = _data()
    result = opt.optimize_symbol("BTCUSDT", features, labels, returns)
    opt.results.append(result)
    out = tmp_path / "results"
    opt.save_results(out)
    assert (out / "optimization_summary.json").exists()
    assert (out / "trials_BTCUSDT.json").exists()


def test_optimizer_save_results_empty(tmp_path: Path):
    opt = WalkForwardOptimizer(config=_small_config())
    out = tmp_path / "empty"
    opt.save_results(out)
    assert (out / "optimization_summary.json").exists()


def test_optimizer_load_results_noop():
    opt = WalkForwardOptimizer(config=_small_config())
    assert opt.load_results(Path("/nonexistent")) is None
