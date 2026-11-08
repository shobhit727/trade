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
