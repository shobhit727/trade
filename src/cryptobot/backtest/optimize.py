"""Bayesian strategy-parameter optimization via Optuna.

Bridges the grid `--algorithms` sweep with a search-space-aware optimizer:
suggest integer/float/categorical strategy config params, run a backtest,
score by Sharpe (or returns), track best params. Optuna is optional —
a deterministic grid fallback over a coarse space runs when it is absent.
"""

from __future__ import annotations

import asyncio
import itertools
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from cryptobot.backtest.metrics import PerformanceMetrics
from cryptobot.backtest.runner import make_strategy, run_backtest

try:
    import optuna

    HAS_OPTUNA = True
except ImportError:
    optuna = None
    HAS_OPTUNA = False

logger = logging.getLogger(__name__)


@dataclass
class ParamSpec:
    """One strategy-parameter search dimension."""

    name: str
    low: float
    high: float
    kind: str = "float"  # float | int | categorical
    choices: list[Any] = field(default_factory=list)


def _sample(param: ParamSpec, rng, value: float) -> Any:
    if param.kind == "categorical":
        return rng.choice(param.choices)
    if param.kind == "int":
        return int(round(value))
    return value


def _coarse_grid(params: list[ParamSpec]) -> list[dict[str, Any]]:
    """Deterministic grid fallback (3 points per dim, capped)."""
    dims = []
    for p in params:
        if p.kind == "categorical":
            dims.append(p.choices)
        else:
            lo, hi = p.low, p.high
            pts = [lo, (lo + hi) / 2.0, hi] if hi > lo else [lo]
            if p.kind == "int":
                pts = [int(round(x)) for x in pts]
            dims.append(pts)
    total = 1
    for d in dims:
        total *= len(d)
        if total > 64:
            # Coarse only: 2 points per dim beyond the first few.
            dims = [d[:2] if len(d) > 2 else d for d in dims]
            break
    return [dict(zip([p.name for p in params], combo, strict=True)) for combo in itertools.product(*dims)]


async def _score(params: dict[str, Any], bars, symbol: str, metric: str) -> float:
    strategy = make_strategy("mean_reversion", **{k: v for k, v in params.items()})
    result = await run_backtest(bars, strategy, symbol=symbol)
    curve = result.equity_curve
    values = [float(v) for _t, v in curve]
    if not values or len(values) < 2:
        return -1e9
    pm = PerformanceMetrics()
    pm.add_value(float(values[0]))
    for v in values[1:]:
        pm.add_value(v)
    returns = [values[i] / values[i - 1] - 1.0 for i in range(1, len(values))]
    if metric == "sharpe":
        return float(pm.calculate_sharpe_ratio(returns))
    if metric == "sortino":
        return float(pm.calculate_sortino_ratio(returns))
    if metric == "max_drawdown":
        return float(-pm.calculate_drawdown(_pd_series(values)))
    return float(values[-1] / values[0] - 1.0)


def _pd_series(values: list[float]):
    import pandas as pd

    return pd.Series(values)


def _optuna_objective(trial, params, bars, symbol, metric):
    kwargs = {}
    for p in params:
        if p.kind == "categorical":
            kwargs[p.name] = trial.suggest_categorical(p.name, p.choices)
        elif p.kind == "int":
            kwargs[p.name] = trial.suggest_int(p.name, int(p.low), int(p.high))
        else:
            kwargs[p.name] = trial.suggest_float(p.name, p.low, p.high)
    return asyncio.run(_score(kwargs, bars, symbol, metric))


@dataclass
class OptimizationResult:
    best_params: dict[str, Any]
    best_score: float
    n_trials: int
    method: str  # "optuna" | "grid"

    def to_dict(self) -> dict[str, Any]:
        return {
            "best_params": self.best_params,
            "best_score": self.best_score,
            "n_trials": self.n_trials,
            "method": self.method,
        }


def optimize_strategy(
    bars,
    params: list[ParamSpec],
    symbol: str = "BTCUSDT",
    metric: str = "sharpe",
    n_trials: int = 30,
    random_seed: int = 42,
    progress: Callable[[int, int, float], None] | None = None,
) -> OptimizationResult:
    """Optimize a mean-reversion strategy's config params on synthetic/real bars."""
    if not params:
        raise ValueError("at least one ParamSpec required")

    if HAS_OPTUNA and n_trials > 1:
        study = optuna.create_study(direction="maximize")
        study.optimize(
            lambda trial: _optuna_objective(trial, params, bars, symbol, metric),
            n_trials=n_trials,
            show_progress_bar=False,
        )
        return OptimizationResult(
            best_params=dict(study.best_params),
            best_score=float(study.best_value),
            n_trials=len(study.trials),
            method="optuna",
        )

    grid = _coarse_grid(params)
    best_params, best_score = {}, -1e18
    for i, combo in enumerate(grid):
        score = asyncio.run(_score(combo, bars, symbol, metric))
        if progress is not None:
            progress(i + 1, len(grid), score)
        if score > best_score:
            best_score, best_params = score, combo
    return OptimizationResult(
        best_params=best_params,
        best_score=float(best_score),
        n_trials=len(grid),
        method="grid",
    )


DEFAULT_PARAMS: list[ParamSpec] = [
    ParamSpec(name="lookback", low=10, high=50, kind="int"),
    ParamSpec(name="z_entry", low=1.0, high=3.0),
    ParamSpec(name="z_exit", low=0.0, high=1.0),
    ParamSpec(name="rsi_period", low=7, high=30, kind="int"),
]


__all__ = [
    "DEFAULT_PARAMS",
    "OptimizationResult",
    "ParamSpec",
    "optimize_strategy",
]
