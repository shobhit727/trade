"""Safe, bounded genetic programming for numerical trading expressions.

The evaluator interprets an explicit AST. It never executes generated Python, imports
modules, accesses files, or evaluates arbitrary source code.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np


UNARY = ("abs", "neg", "tanh", "sign")
BINARY = ("add", "sub", "mul", "protected_div", "minimum", "maximum")


@dataclass(frozen=True, slots=True)
class Node:
    """Immutable numerical expression node."""

    operation: str
    children: tuple[Node, ...] = ()
    feature_index: int | None = None
    constant: float | None = None

    def __post_init__(self) -> None:
        # Enforce a closed grammar and exact arity before evaluating any candidate.
        arity = 1 if self.operation in UNARY else 2 if self.operation in BINARY else 0
        if self.operation == "feature":
            if self.feature_index is None or self.feature_index < 0 or self.children:
                raise ValueError("feature nodes require a non-negative feature_index")
        elif self.operation == "constant":
            if self.constant is None or not np.isfinite(self.constant) or self.children:
                raise ValueError("constant nodes require a finite constant")
        elif self.operation in UNARY + BINARY:
            if len(self.children) != arity or self.feature_index is not None or self.constant is not None:
                raise ValueError(f"invalid arity or payload for {self.operation}")
        else:
            raise ValueError(f"unsupported expression operation: {self.operation}")

    @property
    def depth(self) -> int:
        # Terminal nodes have depth zero.
        return 0 if not self.children else 1 + max(child.depth for child in self.children)

    @property
    def size(self) -> int:
        # Complexity is the total number of AST nodes.
        return 1 + sum(child.size for child in self.children)

    def evaluate(self, features: np.ndarray) -> np.ndarray:
        """Interpret this expression for a 2D observations × features matrix."""
        # Validate the feature matrix once per expression evaluation.
        matrix = np.asarray(features, dtype=np.float64)
        if matrix.ndim != 2 or not np.isfinite(matrix).all():
            raise ValueError("features must be a finite 2D array")
        return self._evaluate(matrix)

    def _evaluate(self, matrix: np.ndarray) -> np.ndarray:
        # Return a vector with one result per observation.
        if self.operation == "feature":
            if self.feature_index >= matrix.shape[1]:
                raise ValueError("expression references a feature outside the input matrix")
            return matrix[:, self.feature_index]
        if self.operation == "constant":
            return np.full(matrix.shape[0], self.constant, dtype=np.float64)
        values = [child._evaluate(matrix) for child in self.children]
        if self.operation == "abs":
            return np.abs(values[0])
        if self.operation == "neg":
            return -values[0]
        if self.operation == "tanh":
            return np.tanh(values[0])
        if self.operation == "sign":
            return np.sign(values[0])
        if self.operation == "add":
            return values[0] + values[1]
        if self.operation == "sub":
            return values[0] - values[1]
        if self.operation == "mul":
            return np.clip(values[0] * values[1], -1e12, 1e12)
        if self.operation == "protected_div":
            denominator = np.where(np.abs(values[1]) < 1e-9, 1.0, values[1])
            return np.clip(values[0] / denominator, -1e12, 1e12)
        if self.operation == "minimum":
            return np.minimum(values[0], values[1])
        if self.operation == "maximum":
            return np.maximum(values[0], values[1])
        raise RuntimeError(f"unhandled operation: {self.operation}")


def _replace(root: Node, path: tuple[int, ...], replacement: Node) -> Node:
    # Rebuild immutable parent nodes along the selected subtree path.
    if not path:
        return replacement
    index = path[0]
    children = list(root.children)
    children[index] = _replace(children[index], path[1:], replacement)
    return Node(root.operation, tuple(children), root.feature_index, root.constant)


def _paths(root: Node, prefix: tuple[int, ...] = ()) -> list[tuple[int, ...]]:
    # Include the root and every descendant as a possible crossover site.
    output = [prefix]
    for index, child in enumerate(root.children):
        output.extend(_paths(child, prefix + (index,)))
    return output


def _subtree(root: Node, path: tuple[int, ...]) -> Node:
    # Resolve a subtree path without dynamic source evaluation.
    node = root
    for index in path:
        node = node.children[index]
    return node


class GeneticProgrammer:
    """Small tournament-selection GP with bounded trees and deterministic mutation."""

    def __init__(
        self,
        *,
        feature_count: int,
        population_size: int = 64,
        generations: int = 20,
        max_depth: int = 5,
        max_nodes: int = 63,
        mutation_rate: float = 0.2,
        seed: int = 42,
    ) -> None:
        # Reject resource limits that could make generated AST evaluation unbounded.
        if feature_count < 1 or population_size < 4 or generations < 1:
            raise ValueError("feature_count, population_size or generations is invalid")
        if max_depth < 1 or max_nodes < 3 or not 0 <= mutation_rate <= 1:
            raise ValueError("invalid tree complexity or mutation constraints")
        self.feature_count = feature_count
        self.population_size = population_size
        self.generations = generations
        self.max_depth = max_depth
        self.max_nodes = max_nodes
        self.mutation_rate = mutation_rate
        self.rng = np.random.default_rng(seed)
        self.seed = seed

    def _terminal(self) -> Node:
        # Generate a feature reference or small finite constant.
        if self.rng.random() < 0.8:
            return Node("feature", feature_index=int(self.rng.integers(self.feature_count)))
        return Node("constant", constant=float(self.rng.uniform(-2.0, 2.0)))

    def _random_tree(self, depth: int) -> Node:
        # Grow a full or partial tree without exceeding configured depth/node bounds.
        if depth >= self.max_depth or self.rng.random() < 0.35:
            return self._terminal()
        if self.rng.random() < 0.4:
            operation = UNARY[int(self.rng.integers(len(UNARY)))]
            return Node(operation, (self._random_tree(depth + 1),))
        operation = BINARY[int(self.rng.integers(len(BINARY)))]
        return Node(operation, (
            self._random_tree(depth + 1),
            self._random_tree(depth + 1),
        ))

    def _new_individual(self) -> Node:
        # Retry bounded generation before falling back to a guaranteed terminal.
        for _ in range(64):
            candidate = self._random_tree(0)
            if candidate.depth <= self.max_depth and candidate.size <= self.max_nodes:
                return candidate
        return self._terminal()

    def _mutate(self, tree: Node) -> Node:
        # Replace one randomly selected subtree and reject invalid offspring.
        for _ in range(32):
            path = _paths(tree)[int(self.rng.integers(len(_paths(tree))))]
            replacement = self._random_tree(len(path))
            mutant = _replace(tree, path, replacement)
            if mutant.depth <= self.max_depth and mutant.size <= self.max_nodes:
                return mutant
        return tree

    def _crossover(self, left: Node, right: Node) -> Node:
        # Exchange two typed numerical subtrees while enforcing complexity constraints.
        for _ in range(32):
            left_paths = _paths(left)
            right_paths = _paths(right)
            left_path = left_paths[int(self.rng.integers(len(left_paths)))]
            right_path = right_paths[int(self.rng.integers(len(right_paths)))]
            child = _replace(left, left_path, _subtree(right, right_path))
            if child.depth <= self.max_depth and child.size <= self.max_nodes:
                return child
        return left

    def run(self, features: np.ndarray, fitness: Callable[[np.ndarray], float]) -> dict[str, object]:
        """Evolve expressions using caller-supplied train-only fitness."""
        # Caller must pass TRAIN-derived features; this function has no market-data access.
        matrix = np.asarray(features, dtype=np.float64)
        if matrix.ndim != 2 or matrix.shape[1] != self.feature_count:
            raise ValueError("features shape does not match feature_count")
        if not np.isfinite(matrix).all():
            raise ValueError("features must be finite")
        population = [self._new_individual() for _ in range(self.population_size)]
        history: list[dict[str, object]] = []
        failures: list[str] = []
        # Every evolved tree receives a stable per-generation identity and ancestry record.
        population_ids = [f"gp-g0-{index:06d}" for index in range(self.population_size)]
        population_lineage = [
            {
                "operator": "random_initialisation",
                "generation": 0,
                "parent_candidate_ids": [],
                "seed": self.seed,
            }
            for _ in population
        ]

        def score(tree: Node, generation: int, index: int, candidate_id: str) -> float:
            # Penalise expression size to discourage unnecessarily complex formulas.
            try:
                output = tree._evaluate(matrix)
                value = float(fitness(output)) - 1e-4 * tree.size
                if not np.isfinite(value):
                    raise ValueError("fitness returned non-finite score")
                history.append({
                    "generation": generation, "index": index, "candidate_id": candidate_id,
                    "fitness": value, "tree_size": tree.size, "tree_depth": tree.depth,
                })
                return value
            except Exception as exc:  # noqa: BLE001 - retain failed candidate context.
                failures.append(f"generation={generation},candidate={index}: {type(exc).__name__}: {exc}")
                return -np.inf

        scores = [
            score(tree, 0, index, population_ids[index])
            for index, tree in enumerate(population)
        ]
        for generation in range(1, self.generations + 1):
            # Elitism retains the best current expression in the next generation.
            elite = int(np.argmax(scores))
            next_population = [population[elite]]
            next_ids = [f"gp-g{generation:04d}-000000"]
            next_lineage = [{
                "operator": "elitism",
                "generation": generation,
                "parent_candidate_ids": [population_ids[elite]],
                "seed": self.seed,
            }]
            while len(next_population) < self.population_size:
                # Tournament selection uses only current TRAIN fitness scores.
                def tournament() -> tuple[int, Node]:
                    indices = self.rng.integers(0, len(population), size=3)
                    winner = int(max(indices, key=lambda item: scores[int(item)]))
                    return winner, population[winner]

                left_index, left = tournament()
                right_index, right = tournament()
                child = self._crossover(left, right)
                mutated = self.rng.random() < self.mutation_rate
                if mutated:
                    child = self._mutate(child)
                child_index = len(next_population)
                next_population.append(child)
                next_ids.append(f"gp-g{generation:04d}-{child_index:06d}")
                next_lineage.append({
                    "operator": "subtree_crossover_then_mutation" if mutated else "subtree_crossover",
                    "generation": generation,
                    "parent_candidate_ids": [
                        population_ids[left_index],
                        population_ids[right_index],
                    ],
                    "mutation_probability": self.mutation_rate,
                    "mutation_applied": mutated,
                    "seed": self.seed,
                })
            population = next_population
            population_ids = next_ids
            population_lineage = next_lineage
            scores = [
                score(tree, generation, index, population_ids[index])
                for index, tree in enumerate(population)
            ]
        best_index = int(np.argmax(scores))
        return {
            "seed": self.seed,
            "best_expression": population[best_index],
            "best_fitness": float(scores[best_index]),
            "population": tuple(population),
            "population_ids": tuple(population_ids),
            "population_lineage": tuple(population_lineage),
            "fitness": tuple(float(value) for value in scores),
            "history": tuple(history),
            "failures": tuple(failures),
        }
