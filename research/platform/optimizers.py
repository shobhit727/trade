"""Budgeted, deterministic optimisation baselines for strategy research."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Callable, Mapping

import numpy as np


@dataclass(frozen=True, slots=True)
class Parameter:
    """One bounded numeric or categorical optimisation dimension."""

    name: str
    low: float | None = None
    high: float | None = None
    kind: str = "float"
    choices: tuple[object, ...] = ()

    def __post_init__(self) -> None:
        # Reject underspecified or unbounded dimensions before an experiment starts.
        if not self.name.strip():
            raise ValueError("parameter name must be non-empty")
        if self.kind == "categorical":
            if not self.choices:
                raise ValueError("categorical parameters require choices")
        elif self.kind in {"float", "int"}:
            if self.low is None or self.high is None or self.high <= self.low:
                raise ValueError("numeric parameters require finite low < high bounds")
        else:
            raise ValueError("kind must be float, int or categorical")

    def sample(self, rng: np.random.Generator) -> object:
        # Use only the experiment's seeded generator for deterministic sampling.
        if self.kind == "categorical":
            return self.choices[int(rng.integers(0, len(self.choices)))]
        if self.kind == "int":
            return int(rng.integers(int(self.low), int(self.high) + 1))
        return float(rng.uniform(float(self.low), float(self.high)))


@dataclass(frozen=True, slots=True)
class Candidate:
    """One evaluated configuration and its objective value."""

    candidate_id: str
    parameters: Mapping[str, object]
    score: float
    evaluation_index: int


@dataclass(frozen=True, slots=True)
class SearchResult:
    """Complete optimisation trace, including failed objective calls."""

    method: str
    seed: int
    candidates: tuple[Candidate, ...]
    failures: tuple[str, ...] = ()

    @property
    def best(self) -> Candidate:
        # Refuse to fabricate a winner when every evaluation failed.
        if not self.candidates:
            raise RuntimeError("optimisation produced no valid candidates")
        return max(self.candidates, key=lambda item: item.score)


def _evaluate(
    method: str,
    objective: Callable[[Mapping[str, object]], float],
    configurations: list[dict[str, object]],
    seed: int,
) -> SearchResult:
    # Keep one result row per attempted config and record failures explicitly.
    candidates: list[Candidate] = []
    failures: list[str] = []
    for index, configuration in enumerate(configurations):
        try:
            score = float(objective(configuration))
            if not np.isfinite(score):
                raise ValueError("objective returned a non-finite score")
            candidates.append(Candidate(f"{method}-{index:08d}", dict(configuration), score, index))
        except Exception as exc:  # noqa: BLE001 - a failed candidate must not vanish.
            failures.append(f"candidate={index}: {type(exc).__name__}: {exc}")
    return SearchResult(method, seed, tuple(candidates), tuple(failures))


def random_search(
    space: tuple[Parameter, ...],
    objective: Callable[[Mapping[str, object]], float],
    *,
    budget: int,
    seed: int = 42,
) -> SearchResult:
    """Evaluate a fixed budget of seeded random configurations."""
    # The declared budget is the number of objective calls.
    if budget < 1 or not space:
        raise ValueError("random search needs a positive budget and non-empty space")
    rng = np.random.default_rng(seed)
    configurations = [
        {parameter.name: parameter.sample(rng) for parameter in space}
        for _ in range(budget)
    ]
    return _evaluate("random", objective, configurations, seed)


def grid_search(
    space: tuple[Parameter, ...],
    objective: Callable[[Mapping[str, object]], float],
    *,
    points_per_numeric_dimension: int = 3,
    max_evaluations: int = 1000,
    seed: int = 42,
) -> SearchResult:
    """Enumerate a coarse deterministic grid under an explicit evaluation cap."""
    # Reject a Cartesian product that exceeds the caller's compute budget.
    if not space or points_per_numeric_dimension < 2 or max_evaluations < 1:
        raise ValueError("invalid grid-search configuration")
    dimensions: list[list[object]] = []
    for parameter in space:
        if parameter.kind == "categorical":
            values = list(parameter.choices)
        elif parameter.kind == "int":
            values = sorted({
                int(round(value))
                for value in np.linspace(
                    int(parameter.low), int(parameter.high), points_per_numeric_dimension
                )
            })
        else:
            values = [
                float(value)
                for value in np.linspace(
                    float(parameter.low), float(parameter.high), points_per_numeric_dimension
                )
            ]
        dimensions.append(values)
    count = int(np.prod([len(values) for values in dimensions], dtype=np.int64))
    if count > max_evaluations:
        raise ValueError(f"grid has {count} configs; cap is {max_evaluations}")
    names = [parameter.name for parameter in space]
    configs = [dict(zip(names, values, strict=True)) for values in product(*dimensions)]
    return _evaluate("grid", objective, configs, seed)


def optuna_tpe_search(
    space: tuple[Parameter, ...],
    objective: Callable[[Mapping[str, object]], float],
    *,
    budget: int,
    seed: int = 42,
    startup_trials: int = 20,
) -> SearchResult:
    """Run seeded Optuna Tree-structured Parzen Estimator search when installed."""
    # Keep Optuna optional so the CPU-only base installation remains lightweight.
    if budget < 1 or not space:
        raise ValueError("TPE search needs a positive budget and non-empty search space")
    try:
        import optuna
        from optuna.samplers import TPESampler
    except ImportError as exc:
        raise RuntimeError(
            "Optuna is optional; install the research extra to use TPE search"
        ) from exc

    sampler = TPESampler(seed=seed, n_startup_trials=max(1, startup_trials))
    study = optuna.create_study(direction="maximize", sampler=sampler)

    def objective_fn(trial):
        # Suggest every dimension using the declared type and bounds.
        parameters: dict[str, object] = {}
        for parameter in space:
            if parameter.kind == "categorical":
                parameters[parameter.name] = trial.suggest_categorical(
                    parameter.name, list(parameter.choices)
                )
            elif parameter.kind == "int":
                parameters[parameter.name] = trial.suggest_int(
                    parameter.name, int(parameter.low), int(parameter.high)
                )
            else:
                parameters[parameter.name] = trial.suggest_float(
                    parameter.name, float(parameter.low), float(parameter.high)
                )
        score = float(objective(parameters))
        if not np.isfinite(score):
            raise ValueError("objective returned a non-finite score")
        trial.set_user_attr("candidate_parameters", parameters)
        return score

    # Failed trials remain in the study and are copied into the returned failure log.
    study.optimize(
        objective_fn,
        n_trials=budget,
        catch=(Exception,),
        show_progress_bar=False,
    )
    candidates: list[Candidate] = []
    failures: list[str] = []
    for trial in study.trials:
        if trial.state.name == "COMPLETE" and trial.value is not None:
            candidates.append(Candidate(
                f"optuna-tpe-{trial.number:08d}",
                dict(trial.params),
                float(trial.value),
                int(trial.number),
            ))
        else:
            failures.append(
                f"trial={trial.number}: {trial.state.name}: "
                f"{trial.user_attrs.get('failure_reason', 'objective failed')}"
            )
    return SearchResult("optuna_tpe", seed, tuple(candidates), tuple(failures))


def differential_evolution(
    space: tuple[Parameter, ...],
    objective: Callable[[Mapping[str, object]], float],
    *,
    population_size: int = 24,
    generations: int = 20,
    mutation: float = 0.7,
    crossover: float = 0.8,
    seed: int = 42,
) -> SearchResult:
    """Differential evolution for bounded numeric parameters.

    Categorical dimensions are deliberately unsupported in this baseline. Use random or
    grid search for mixed/categorical spaces until a mixed-space algorithm is added.
    """
    # Keep all evaluated scores; never replay a strategy objective after selection.
    if not space or any(p.kind not in {"float", "int"} for p in space):
        raise ValueError("differential evolution supports numeric dimensions only")
    if population_size < 4 or generations < 1 or not 0 < mutation <= 2 or not 0 <= crossover <= 1:
        raise ValueError("invalid differential-evolution configuration")
    rng = np.random.default_rng(seed)
    low = np.asarray([float(p.low) for p in space], dtype=np.float64)
    high = np.asarray([float(p.high) for p in space], dtype=np.float64)
    population = rng.uniform(low, high, size=(population_size, len(space)))
    population_scores = np.full(population_size, -np.inf, dtype=np.float64)
    history: list[Candidate] = []
    failures: list[str] = []
    eval_index = 0

    def decode(vector: np.ndarray) -> dict[str, object]:
        # Apply integer conversion only after clipping to the declared parameter bounds.
        return {
            parameter.name: int(np.clip(round(float(value)), int(parameter.low), int(parameter.high)))
            if parameter.kind == "int" else float(value)
            for parameter, value in zip(space, vector, strict=True)
        }

    def evaluate(vector: np.ndarray) -> float:
        # Score exactly once and append the exact score associated with this genome.
        nonlocal eval_index
        configuration = decode(vector)
        current_index = eval_index
        eval_index += 1
        try:
            score = float(objective(configuration))
            if not np.isfinite(score):
                raise ValueError("objective returned a non-finite score")
            history.append(Candidate(
                f"de-{current_index:08d}", configuration, score, current_index
            ))
            return score
        except Exception as exc:  # noqa: BLE001
            failures.append(f"candidate={current_index}: {type(exc).__name__}: {exc}")
            return -np.inf

    # Evaluate the initial population before evolution.
    for index in range(population_size):
        population_scores[index] = evaluate(population[index])

    # Evolve the population using bounded mutation and binomial crossover.
    for _generation in range(generations):
        for target in range(population_size):
            available = np.delete(np.arange(population_size), target)
            a, b, c = rng.choice(available, size=3, replace=False)
            mutant = np.clip(population[a] + mutation * (population[b] - population[c]), low, high)
            mask = rng.random(len(space)) < crossover
            mask[int(rng.integers(0, len(space)))] = True
            trial = np.where(mask, mutant, population[target])
            trial_score = evaluate(trial)
            if trial_score >= population_scores[target]:
                population[target] = trial
                population_scores[target] = trial_score

    return SearchResult("differential_evolution", seed, tuple(history), tuple(failures))


def parzen_heuristic_search(
    space: tuple[Parameter, ...],
    objective: Callable[[Mapping[str, object]], float],
    *,
    budget: int = 100,
    startup_trials: int = 20,
    good_fraction: float = 0.2,
    seed: int = 42,
) -> SearchResult:
    """Simple elite-Parzen-style sampler, explicitly not advertised as Optuna TPE."""
    # Label the approximation accurately; this is a baseline, not canonical TPE.
    if not space or budget < 1 or startup_trials < 1 or not 0 < good_fraction < 1:
        raise ValueError("invalid Parzen-style search configuration")
    rng = np.random.default_rng(seed)
    configurations: list[dict[str, object]] = []
    scores: list[float] = []
    failures: list[str] = []
    for index in range(budget):
        if index < startup_trials or len([score for score in scores if np.isfinite(score)]) < startup_trials:
            configuration = {parameter.name: parameter.sample(rng) for parameter in space}
        else:
            valid = np.flatnonzero(np.isfinite(scores))
            ordered = valid[np.argsort(np.asarray(scores)[valid])[::-1]]
            cutoff = max(2, int(np.ceil(len(ordered) * good_fraction)))
            elite = [configurations[int(position)] for position in ordered[:cutoff]]
            configuration = {}
            for parameter in space:
                if parameter.kind == "categorical":
                    values = [item[parameter.name] for item in elite]
                    configuration[parameter.name] = values[int(rng.integers(len(values)))]
                else:
                    values = np.asarray([float(item[parameter.name]) for item in elite])
                    spread = max(
                        float(np.std(values)),
                        (float(parameter.high) - float(parameter.low)) / 50.0,
                    )
                    sample = float(rng.normal(float(np.mean(values)), spread))
                    sample = float(np.clip(sample, float(parameter.low), float(parameter.high)))
                    configuration[parameter.name] = (
                        int(round(sample)) if parameter.kind == "int" else sample
                    )
        configurations.append(configuration)
        try:
            score = float(objective(configuration))
            if not np.isfinite(score):
                raise ValueError("objective returned a non-finite score")
            scores.append(score)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"candidate={index}: {type(exc).__name__}: {exc}")
            scores.append(-np.inf)
    candidates = tuple(
        Candidate(f"parzen-{index:08d}", configuration, float(score), index)
        for index, (configuration, score) in enumerate(zip(configurations, scores, strict=True))
        if np.isfinite(score)
    )
    return SearchResult("parzen_heuristic", seed, candidates, tuple(failures))
