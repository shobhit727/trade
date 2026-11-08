"""CPU reference neuroevolution for compact dense neural trading models.

The implementation optimises a bounded flat parameter vector. It has no broker or
exchange connections; fitness must be computed from permitted training partitions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np


@dataclass(frozen=True, slots=True)
class DenseMLP:
    """One-hidden-layer tanh network with a deterministic flat-weight layout."""

    input_size: int
    hidden_size: int
    output_size: int = 1

    def __post_init__(self) -> None:
        # Bound network dimensions to prevent untrusted configurations allocating huge arrays.
        if min(self.input_size, self.hidden_size, self.output_size) < 1:
            raise ValueError("network dimensions must be positive")
        if self.input_size * self.hidden_size + self.hidden_size * self.output_size > 2_000_000:
            raise ValueError("network parameter count exceeds safety limit")

    @property
    def parameter_count(self) -> int:
        # Layout: W1, b1, W2, b2.
        return (
            self.input_size * self.hidden_size
            + self.hidden_size
            + self.hidden_size * self.output_size
            + self.output_size
        )

    def predict(self, features: np.ndarray, parameters: np.ndarray) -> np.ndarray:
        """Forward-pass finite feature rows through the dense network."""
        # Validate dimensions and numerical values before matrix operations.
        x = np.asarray(features, dtype=np.float64)
        theta = np.asarray(parameters, dtype=np.float64)
        if x.ndim != 2 or x.shape[1] != self.input_size or not np.isfinite(x).all():
            raise ValueError("features must be finite and match input_size")
        if theta.shape != (self.parameter_count,) or not np.isfinite(theta).all():
            raise ValueError("parameter vector has incorrect shape or non-finite values")
        offset = 0
        w1_count = self.input_size * self.hidden_size
        w1 = theta[offset:offset + w1_count].reshape(self.input_size, self.hidden_size)
        offset += w1_count
        b1 = theta[offset:offset + self.hidden_size]
        offset += self.hidden_size
        w2_count = self.hidden_size * self.output_size
        w2 = theta[offset:offset + w2_count].reshape(self.hidden_size, self.output_size)
        offset += w2_count
        b2 = theta[offset:offset + self.output_size]
        hidden = np.tanh(x @ w1 + b1)
        # Tanh output keeps policy scores bounded and avoids unstable unbounded logits.
        return np.tanh(hidden @ w2 + b2)


@dataclass(frozen=True, slots=True)
class EvolutionTrace:
    """Best candidate and per-generation diagnostics."""

    best_parameters: np.ndarray
    best_fitness: float
    generations: tuple[dict[str, float], ...]
    failures: tuple[str, ...]
    evaluations: int


class EvolutionStrategy:
    """Mirrored-noise evolution strategy with rank-normalised utilities."""

    def __init__(
        self,
        network: DenseMLP,
        *,
        population_size: int = 32,
        generations: int = 50,
        learning_rate: float = 0.05,
        noise_std: float = 0.1,
        seed: int = 42,
        weight_limit: float = 8.0,
    ) -> None:
        # Require an even number of genomes for antithetic perturbations.
        if population_size < 4 or population_size % 2:
            raise ValueError("population_size must be an even integer >= 4")
        if generations < 1 or learning_rate <= 0 or noise_std <= 0 or weight_limit <= 0:
            raise ValueError("invalid evolution strategy hyperparameters")
        self.network = network
        self.population_size = population_size
        self.generations = generations
        self.learning_rate = learning_rate
        self.noise_std = noise_std
        self.seed = seed
        self.weight_limit = weight_limit

    def run(
        self,
        features: np.ndarray,
        fitness: Callable[[np.ndarray], float],
        *,
        initial_parameters: np.ndarray | None = None,
    ) -> EvolutionTrace:
        """Evolve network parameters against the supplied training-only fitness function."""
        # Inputs are copied so caller mutation cannot modify an active search.
        matrix = np.asarray(features, dtype=np.float64)
        if matrix.ndim != 2 or matrix.shape[1] != self.network.input_size:
            raise ValueError("feature shape does not match network input_size")
        if not np.isfinite(matrix).all():
            raise ValueError("features must be finite")
        rng = np.random.default_rng(self.seed)
        dimension = self.network.parameter_count
        mean = (
            np.asarray(initial_parameters, dtype=np.float64).copy()
            if initial_parameters is not None
            else rng.normal(0.0, 0.1, size=dimension)
        )
        if mean.shape != (dimension,) or not np.isfinite(mean).all():
            raise ValueError("initial parameter vector has incorrect shape or non-finite values")
        mean = np.clip(mean, -self.weight_limit, self.weight_limit)
        best_parameters = mean.copy()
        best_fitness = -np.inf
        traces: list[dict[str, float]] = []
        failures: list[str] = []
        evaluations = 0
        half = self.population_size // 2

        for generation in range(self.generations):
            # Antithetic perturbations reduce variance of the search-direction estimate.
            noise = rng.normal(0.0, 1.0, size=(half, dimension))
            perturbations = np.concatenate((noise, -noise), axis=0)
            population = np.clip(
                mean[None, :] + self.noise_std * perturbations,
                -self.weight_limit,
                self.weight_limit,
            )
            scores = np.full(self.population_size, -np.inf, dtype=np.float64)
            for index, parameters in enumerate(population):
                try:
                    predictions = self.network.predict(matrix, parameters)
                    score = float(fitness(predictions))
                    if not np.isfinite(score):
                        raise ValueError("fitness returned a non-finite score")
                    scores[index] = score
                except Exception as exc:  # noqa: BLE001 - keep failed evaluations in the trace.
                    failures.append(
                        f"generation={generation},candidate={index}: {type(exc).__name__}: {exc}"
                    )
                evaluations += 1

            # Convert valid population scores into centred rank utilities.
            valid = np.flatnonzero(np.isfinite(scores))
            if len(valid):
                ordered = valid[np.argsort(scores[valid], kind="stable")]
                utilities = np.zeros(self.population_size, dtype=np.float64)
                utilities[ordered] = np.linspace(-0.5, 0.5, len(ordered))
                utilities[valid] -= float(np.mean(utilities[valid]))
                gradient = (utilities[:, None] * perturbations).mean(axis=0) / self.noise_std
                mean = np.clip(
                    mean + self.learning_rate * gradient,
                    -self.weight_limit,
                    self.weight_limit,
                )
                winner = int(valid[np.argmax(scores[valid])])
                if scores[winner] > best_fitness:
                    best_fitness = float(scores[winner])
                    best_parameters = population[winner].copy()
                traces.append({
                    "generation": float(generation),
                    "best_fitness": float(np.max(scores[valid])),
                    "median_fitness": float(np.median(scores[valid])),
                    "population_std": float(np.std(scores[valid])),
                    "valid_candidates": float(len(valid)),
                })
            else:
                traces.append({
                    "generation": float(generation),
                    "best_fitness": -np.inf,
                    "median_fitness": -np.inf,
                    "population_std": 0.0,
                    "valid_candidates": 0.0,
                })

        if not np.isfinite(best_fitness):
            raise RuntimeError("neuroevolution produced no valid candidate")
        return EvolutionTrace(
            best_parameters=best_parameters,
            best_fitness=best_fitness,
            generations=tuple(traces),
            failures=tuple(failures),
            evaluations=evaluations,
        )


def evolve_network(
    features: np.ndarray,
    fitness: Callable[[np.ndarray], float],
    *,
    hidden_size: int = 16,
    population_size: int = 32,
    generations: int = 50,
    seed: int = 42,
) -> EvolutionTrace:
    """Convenience function for a bounded dense-network evolution experiment."""
    # Infer input dimension only; label and target semantics stay with the caller.
    matrix = np.asarray(features, dtype=np.float64)
    if matrix.ndim != 2:
        raise ValueError("features must be a 2D matrix")
    network = DenseMLP(matrix.shape[1], hidden_size)
    return EvolutionStrategy(
        network,
        population_size=population_size,
        generations=generations,
        seed=seed,
    ).run(matrix, fitness)
