"""Bayesian strategy-parameter optimization via Optuna.

Bridges the grid `--algorithms` sweep with a search-space-aware optimizer:
suggest integer/float/categorical strategy config params, run backtests,
score by Sharpe (or returns), track best params. Optuna is optional —
a deterministic grid fallback over a coarse space runs when it is absent.

Selection is WALK-FORWARD (issue #51-M7): candidates are scored on the train
segment only; the winner's score on the untouched test segment is reported
alongside, so the caller sees honest out-of-sample expectations instead of an
in-sample upper bound.
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


async def _score(
    strategy_name: str,
    params: dict[str, Any],
    bars,
    symbol: str,
    metric: str,
    *,
    slippage_bps: int = 3,
    commission_bps: int = 5,
    risk_fraction: float = 0.0,
) -> float:
    strategy = make_strategy(strategy_name, **params)
    result = await run_backtest(
        bars,
        strategy,
        symbol=symbol,
        slippage_bps=slippage_bps,
        commission_bps=commission_bps,
        risk_fraction=risk_fraction,
    )
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


@dataclass
class OptimizationResult:
    best_params: dict[str, Any]
    best_score: float          # in-sample (train-segment) score of the winner
    n_trials: int
    method: str  # "optuna" | "grid"
    oos_score: float | None = None   # same params scored on the held-out segment
    oos_return: float | None = None  # net total return on the held-out segment

    def to_dict(self) -> dict[str, Any]:
        return {
            "best_params": self.best_params,
            "best_score": self.best_score,
            "n_trials": self.n_trials,
            "method": self.method,
            "oos_score": self.oos_score,
            "oos_return": self.oos_return,
        }


def optimize_strategy(
    bars,
    params: list[ParamSpec],
    symbol: str = "BTCUSDT",
    metric: str = "sharpe",
    n_trials: int = 30,
    random_seed: int = 42,
    progress: Callable[[int, int, float], None] | None = None,
    strategy_name: str = "mean_reversion",
    oos_fraction: float = 0.3,
    slippage_bps: int = 3,
    commission_bps: int = 5,
    risk_fraction: float = 0.0,
) -> OptimizationResult:
    """Optimize any registered strategy's config params, walk-forward.

    Candidates are scored on the leading ``(1 - oos_fraction)`` of the bars;
    the winning parameter set is then evaluated once on the held-out tail so
    ``oos_score``/``oos_return`` reflect unseen data (#51-M7).
    """
    if not params:
        raise ValueError("at least one ParamSpec required")

    split = len(bars)
    if oos_fraction > 0 and len(bars) >= 50:
        split = max(int(len(bars) * (1.0 - oos_fraction)), 10)
    train_bars, test_bars = bars[:split], bars[split:]

    async def _train_score(combo: dict[str, Any]) -> float:
        return await _score(
            strategy_name, combo, train_bars, symbol, metric,
            slippage_bps=slippage_bps, commission_bps=commission_bps,
            risk_fraction=risk_fraction,
        )

    if HAS_OPTUNA and n_trials > 1:
        def _objective(trial):
            kwargs = {}
            for p in params:
                if p.kind == "categorical":
                    kwargs[p.name] = trial.suggest_categorical(p.name, p.choices)
                elif p.kind == "int":
                    kwargs[p.name] = trial.suggest_int(p.name, int(p.low), int(p.high))
                else:
                    kwargs[p.name] = trial.suggest_float(p.name, p.low, p.high)
            return asyncio.run(_train_score(kwargs))

        study = optuna.create_study(direction="maximize")
        study.optimize(_objective, n_trials=n_trials, show_progress_bar=False)
        best_params = dict(study.best_params)
        best_score = float(study.best_value)
        n_done = len(study.trials)
        method = "optuna"
    else:
        grid = _coarse_grid(params)
        best_params, best_score = {}, -1e18
        for i, combo in enumerate(grid):
            score = asyncio.run(_train_score(combo))
            if progress is not None:
                progress(i + 1, len(grid), score)
            if score > best_score:
                best_score, best_params = score, combo
        n_done = len(grid)
        method = "grid"

    oos_score = oos_return = None
    if test_bars:
        oos_score = asyncio.run(_score(
            strategy_name, best_params, test_bars, symbol, metric,
            slippage_bps=slippage_bps, commission_bps=commission_bps,
            risk_fraction=risk_fraction,
        ))
        res = asyncio.run(run_backtest(
            test_bars, make_strategy(strategy_name, **best_params), symbol=symbol,
            slippage_bps=slippage_bps, commission_bps=commission_bps,
            risk_fraction=risk_fraction,
        ))
        oos_return = float(res.total_return)

    return OptimizationResult(
        best_params=best_params,
        best_score=float(best_score),
        n_trials=n_done,
        method=method,
        oos_score=oos_score,
        oos_return=oos_return,
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
