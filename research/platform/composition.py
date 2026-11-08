"""Evolution of safe, declarative strategy-component compositions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

import numpy as np


ALLOWED_ROLES = frozenset({"entry", "exit", "filter", "sizing", "risk", "regime", "allocation"})


@dataclass(frozen=True, slots=True)
class Component:
    """Named declarative strategy component; implementation is provided by a registry."""

    component_id: str
    role: str
    parameters: tuple[tuple[str, float], ...] = ()

    def __post_init__(self) -> None:
        # Only allow known component roles and finite, JSON-friendly numeric parameters.
        if not self.component_id.strip() or self.role not in ALLOWED_ROLES:
            raise ValueError("component id or role is invalid")
        if any(not key.strip() or not np.isfinite(value) for key, value in self.parameters):
            raise ValueError("component parameters must have names and finite values")


@dataclass(frozen=True, slots=True)
class Composition:
    """One immutable composition genome."""

    components: tuple[Component, ...]

    def __post_init__(self) -> None:
        # Require entry and exit logic and prevent duplicate component-role pairs.
        if not any(item.role == "entry" for item in self.components):
            raise ValueError("composition requires an entry component")
        if not any(item.role == "exit" for item in self.components):
            raise ValueError("composition requires an exit component")
        keys = [(item.component_id, item.role) for item in self.components]
        if len(keys) != len(set(keys)):
            raise ValueError("composition contains duplicate component-role pairs")
        if len(self.components) > 32:
            raise ValueError("composition exceeds maximum component count")

    @property
    def complexity(self) -> int:
        # Complexity reflects component count and parameter count.
        return len(self.components) + sum(len(item.parameters) for item in self.components)


@dataclass(frozen=True, slots=True)
class CompositionResult:
    """Best genome and evolution history."""

    best: Composition
    best_fitness: float
    history: tuple[dict[str, float], ...]
    failures: tuple[str, ...]


class StrategyComposer:
    """Tournament-based component composition evolution with deterministic operators."""

    def __init__(
        self,
        registry: Sequence[Component],
        *,
        population_size: int = 40,
        generations: int = 25,
        max_components: int = 12,
        mutation_rate: float = 0.25,
        seed: int = 42,
    ) -> None:
        # Registry is explicit; evolved genomes cannot invent callable code.
        if population_size < 4 or generations < 1 or not 2 <= max_components <= 32:
            raise ValueError("invalid strategy-composition bounds")
        if not 0 <= mutation_rate <= 1:
            raise ValueError("mutation_rate must be in [0,1]")
        if not any(c.role == "entry" for c in registry) or not any(c.role == "exit" for c in registry):
            raise ValueError("registry must contain entry and exit components")
        self.registry = tuple(registry)
        self.population_size = population_size
        self.generations = generations
        self.max_components = max_components
        self.mutation_rate = mutation_rate
        self.rng = np.random.default_rng(seed)
        self.seed = seed

    def _initial(self) -> Composition:
        # Seed every genome with one entry and one exit component.
        entry = self.registry[int(self.rng.choice([i for i, c in enumerate(self.registry) if c.role == "entry"]))]
        exit_ = self.registry[int(self.rng.choice([i for i, c in enumerate(self.registry) if c.role == "exit"]))]
        return Composition((entry, exit_))

    def _mutate(self, genome: Composition) -> Composition:
        # Add, remove or replace a declarative component without losing entry/exit.
        components = list(genome.components)
        operation = int(self.rng.integers(3))
        candidate = self.registry[int(self.rng.integers(len(self.registry)))]
        if operation == 0 and len(components) < self.max_components:
            if candidate not in components:
                components.append(candidate)
        elif operation == 1:
            removable = [i for i, item in enumerate(components) if item.role not in {"entry", "exit"}]
            if removable:
                components.pop(removable[int(self.rng.integers(len(removable)))])
        else:
            replaceable = [i for i, item in enumerate(components) if item.role == candidate.role]
            if replaceable:
                components[replaceable[int(self.rng.integers(len(replaceable)))]] = candidate
        # If mutation creates an invalid duplicate, preserve the parent genome.
        try:
            unique = []
            seen = set()
            for component in components:
                key = (component.component_id, component.role)
                if key not in seen:
                    unique.append(component)
                    seen.add(key)
            return Composition(tuple(unique))
        except ValueError:
            return genome

    def _crossover(self, left: Composition, right: Composition) -> Composition:
        # Union distinct components from both parents under the configured cap.
        merged = []
        seen = set()
        for component in left.components + right.components:
            key = (component.component_id, component.role)
            if key not in seen:
                merged.append(component)
                seen.add(key)
        self.rng.shuffle(merged)
        entries = [c for c in left.components + right.components if c.role == "entry"]
        exits = [c for c in left.components + right.components if c.role == "exit"]
        chosen = [entries[0], exits[0]]
        for component in merged:
            if component.role in {"entry", "exit"} or len(chosen) >= self.max_components:
                continue
            chosen.append(component)
        return Composition(tuple(chosen))

    def run(self, fitness: Callable[[Composition], float]) -> CompositionResult:
        """Evolve composition genomes with an explicit fitness callback."""
        # Fitness callback must evaluate TRAIN-only data and record its data provenance.
        population = [self._initial() for _ in range(self.population_size)]
        failures: list[str] = []
        history: list[dict[str, float]] = []

        def evaluate(genome: Composition, generation: int, index: int) -> float:
            # Penalise complexity to discourage gratuitous component accumulation.
            try:
                value = float(fitness(genome)) - 1e-4 * genome.complexity
                if not np.isfinite(value):
                    raise ValueError("fitness returned non-finite value")
                return value
            except Exception as exc:  # noqa: BLE001 - retain fitness failures.
                failures.append(f"generation={generation},candidate={index}: {type(exc).__name__}: {exc}")
                return -np.inf

        scores = [evaluate(genome, 0, i) for i, genome in enumerate(population)]
        for generation in range(1, self.generations + 1):
            # Keep the best genome; breed the rest from three-member tournaments.
            elite = int(np.argmax(scores))
            next_population = [population[elite]]
            while len(next_population) < self.population_size:
                def tournament() -> Composition:
                    indices = self.rng.integers(0, len(population), size=3)
                    return population[int(max(indices, key=lambda idx: scores[int(idx)]))]
                child = self._crossover(tournament(), tournament())
                if self.rng.random() < self.mutation_rate:
                    child = self._mutate(child)
                next_population.append(child)
            population = next_population
            scores = [evaluate(genome, generation, i) for i, genome in enumerate(population)]
            valid = np.asarray([score for score in scores if np.isfinite(score)])
            history.append({
                "generation": float(generation),
                "best_fitness": float(np.max(valid)) if len(valid) else -np.inf,
                "median_fitness": float(np.median(valid)) if len(valid) else -np.inf,
                "population_diversity": float(len({genome.components for genome in population}) / len(population)),
            })
        best_index = int(np.argmax(scores))
        if not np.isfinite(scores[best_index]):
            raise RuntimeError("strategy composition evolution produced no valid candidate")
        return CompositionResult(population[best_index], float(scores[best_index]),
                                 tuple(history), tuple(failures))
