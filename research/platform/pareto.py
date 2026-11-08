"""Deterministic non-dominated sorting and NSGA-II selection utilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np


@dataclass(frozen=True, slots=True)
class ParetoCandidate:
    """Candidate objective vector and stable identifier."""

    candidate_id: str
    objectives: tuple[float, ...]


def _matrix(candidates: Sequence[ParetoCandidate], directions: Sequence[str]) -> np.ndarray:
    # Convert all objectives to minimisation so dominance logic has one definition.
    if not candidates or not directions:
        raise ValueError("candidates and objective directions are required")
    if any(direction not in {"min", "max"} for direction in directions):
        raise ValueError("objective directions must be 'min' or 'max'")
    values = np.asarray([candidate.objectives for candidate in candidates], dtype=np.float64)
    if values.ndim != 2 or values.shape[1] != len(directions):
        raise ValueError("each candidate must provide one value per objective")
    if not np.isfinite(values).all():
        raise ValueError("Pareto objectives must be finite")
    signs = np.asarray([1.0 if direction == "min" else -1.0 for direction in directions])
    return values * signs


def dominates(left: np.ndarray, right: np.ndarray) -> bool:
    """Return true when left is no worse in every objective and better in one."""
    # Strict Pareto dominance does not collapse candidates with equal objective vectors.
    return bool(np.all(left <= right) and np.any(left < right))


def non_dominated_fronts(
    candidates: Sequence[ParetoCandidate], directions: Sequence[str]
) -> tuple[tuple[int, ...], ...]:
    """Return successive non-dominated fronts as indices into candidates."""
    # The quadratic sorter is transparent and suitable for research populations.
    values = _matrix(candidates, directions)
    count = len(candidates)
    dominates_set: list[list[int]] = [[] for _ in range(count)]
    dominated_count = np.zeros(count, dtype=np.int64)
    first: list[int] = []
    for left in range(count):
        for right in range(count):
            if left == right:
                continue
            if dominates(values[left], values[right]):
                dominates_set[left].append(right)
            elif dominates(values[right], values[left]):
                dominated_count[left] += 1
        if dominated_count[left] == 0:
            first.append(left)
    fronts: list[tuple[int, ...]] = []
    current = first
    while current:
        fronts.append(tuple(current))
        following: list[int] = []
        for winner in current:
            for loser in dominates_set[winner]:
                dominated_count[loser] -= 1
                if dominated_count[loser] == 0:
                    following.append(loser)
        current = following
    return tuple(fronts)


def crowding_distance(
    candidates: Sequence[ParetoCandidate], directions: Sequence[str], front: Sequence[int]
) -> dict[int, float]:
    """Calculate NSGA-II crowding distances within one non-dominated front."""
    # Boundary candidates receive infinite distance to preserve objective extremes.
    values = _matrix(candidates, directions)
    distance = {index: 0.0 for index in front}
    if len(front) <= 2:
        return {index: float("inf") for index in front}
    for objective in range(values.shape[1]):
        order = sorted(front, key=lambda index: (values[index, objective], candidates[index].candidate_id))
        low, high = values[order[0], objective], values[order[-1], objective]
        distance[order[0]] = float("inf")
        distance[order[-1]] = float("inf")
        span = high - low
        if span <= 0:
            continue
        for position in range(1, len(order) - 1):
            index = order[position]
            if np.isfinite(distance[index]):
                distance[index] += float(
                    (values[order[position + 1], objective] - values[order[position - 1], objective])
                    / span
                )
    return distance


def select_nsga2(
    candidates: Sequence[ParetoCandidate], directions: Sequence[str], size: int
) -> tuple[ParetoCandidate, ...]:
    """Select a bounded population by front rank then descending crowding distance."""
    # Stable candidate IDs break exact crowding ties for deterministic experiments.
    if size < 1:
        raise ValueError("selection size must be positive")
    selected: list[ParetoCandidate] = []
    for front in non_dominated_fronts(candidates, directions):
        distances = crowding_distance(candidates, directions, front)
        ordered = sorted(
            front, key=lambda index: (-distances[index], candidates[index].candidate_id)
        )
        for index in ordered:
            if len(selected) >= size:
                return tuple(selected)
            selected.append(candidates[index])
    return tuple(selected)



class NSGA2Individual:
    """One NSGA-II genome paired with its immutable objective vector."""

    def __init__(self, candidate_id: str, genome: object, objectives: tuple[float, ...]) -> None:
        # Keep the candidate representation separate from objective ranking metadata.
        self.candidate_id = candidate_id
        self.genome = genome
        self.objectives = objectives
        self.pareto_candidate = ParetoCandidate(candidate_id, objectives)


def nsga2_optimize(
    initializer,
    evaluator,
    crossover,
    mutate,
    *,
    population_size: int,
    generations: int,
    directions: tuple[str, ...],
    seed: int = 42,
) -> dict[str, object]:
    """Run a generic NSGA-II loop using bounded caller-supplied genome operators.

    The evaluator returns one finite objective per direction. The initializer, crossover
    and mutation callbacks receive a seeded NumPy Generator. The function retains a Pareto
    set rather than selecting one winner by an arbitrary scalar score.
    """
    # Import locally to keep the Pareto ranking functions usable without extra dependencies.
    from copy import deepcopy

    import numpy as np

    if population_size < 4 or generations < 1 or not directions:
        raise ValueError("population_size >= 4, generations >= 1 and objectives are required")
    if any(direction not in {"min", "max"} for direction in directions):
        raise ValueError("objective directions must be min or max")
    rng = np.random.default_rng(seed)
    evaluations = 0
    sequence = 0
    failures: list[str] = []

    def evaluate_genome(genome: object, generation: int) -> NSGA2Individual | None:
        # Record failed candidates instead of silently shrinking the search family.
        nonlocal evaluations, sequence
        candidate_id = f"nsga2-{generation:05d}-{sequence:08d}"
        sequence += 1
        evaluations += 1
        try:
            values = tuple(float(value) for value in evaluator(genome))
            if len(values) != len(directions) or not np.isfinite(values).all():
                raise ValueError("evaluator returned wrong objective count or non-finite values")
            return NSGA2Individual(candidate_id, genome, values)
        except Exception as exc:  # noqa: BLE001 - preserve candidate-level failures.
            failures.append(
                f"generation={generation},candidate={candidate_id}: {type(exc).__name__}: {exc}"
            )
            return None

    # Initialise and score one complete population.
    population: list[NSGA2Individual] = []
    for _ in range(population_size):
        individual = evaluate_genome(initializer(rng), generation=0)
        if individual is not None:
            population.append(individual)
    if len(population) < 4:
        raise RuntimeError("NSGA-II initial population has fewer than four valid candidates")

    history: list[dict[str, float]] = []

    def select_survivors(candidates: list[NSGA2Individual]) -> list[NSGA2Individual]:
        # NSGA-II survival uses Pareto rank and crowding distance across parents + offspring.
        selected = select_nsga2(
            [item.pareto_candidate for item in candidates],
            directions,
            size=min(population_size, len(candidates)),
        )
        selected_ids = [item.candidate_id for item in selected]
        by_id = {item.candidate_id: item for item in candidates}
        return [by_id[candidate_id] for candidate_id in selected_ids]

    for generation in range(1, generations + 1):
        offspring: list[NSGA2Individual] = []
        attempts = 0
        max_attempts = population_size * 20
        while len(offspring) < population_size and attempts < max_attempts:
            attempts += 1
            # Parent selection samples from the current nondominated survivors.
            left = population[int(rng.integers(0, len(population)))]
            right = population[int(rng.integers(0, len(population)))]
            try:
                child_genome = crossover(deepcopy(left.genome), deepcopy(right.genome), rng)
                child_genome = mutate(child_genome, rng)
            except Exception as exc:  # noqa: BLE001 - operator failures remain visible.
                failures.append(
                    f"generation={generation},operator: {type(exc).__name__}: {exc}"
                )
                continue
            child = evaluate_genome(child_genome, generation)
            if child is not None:
                offspring.append(child)
            # Prevent a permanently failing operator from creating an infinite loop.
        if len(offspring) < population_size:
            raise RuntimeError(
                f"NSGA-II produced only {len(offspring)} valid offspring after {attempts} attempts"
            )

        population = select_survivors(population + offspring)
        fronts = non_dominated_fronts(
            [item.pareto_candidate for item in population],
            directions,
        )
        first_front = [population[index] for index in fronts[0]] if fronts else []
        objective_values = np.asarray([item.objectives for item in population], dtype=np.float64)
        history.append({
            "generation": float(generation),
            "population_size": float(len(population)),
            "pareto_front_size": float(len(first_front)),
            "genome_diversity": float(len({repr(item.genome) for item in population}) / len(population)),
            "objective_0_min": float(np.min(objective_values[:, 0])),
            "objective_0_max": float(np.max(objective_values[:, 0])),
        })

    # Preserve all final nondominated candidates and the complete run history.
    final_fronts = non_dominated_fronts(
        [item.pareto_candidate for item in population],
        directions,
    )
    final_front = [population[index] for index in final_fronts[0]] if final_fronts else []
    serialise = lambda item: {
        "candidate_id": item.candidate_id,
        "genome": item.genome,
        "objectives": item.objectives,
    }
    return {
        "seed": seed,
        "population": tuple(serialise(item) for item in population),
        "pareto_front": tuple(serialise(item) for item in final_front),
        "history": tuple(history),
        "failures": tuple(failures),
        "evaluations": evaluations,
        "objective_directions": directions,
        "scalar_winner_selected": False,
    }
