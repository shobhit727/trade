"""Safe, bounded genetic programming for typed trading expressions.

The evaluator interprets an explicit AST. It never executes generated Python, imports
modules, accesses files, or evaluates arbitrary source code.

The grammar is typed: every node is either NUMERIC or BOOLEAN. Comparison nodes map
two numeric children to a Boolean result; conditional (``cond``) nodes map one Boolean
child and two numeric children to a numeric result; Boolean operators combine Boolean
children. Type violations are rejected structurally by ``Node.__post_init__``, so a
Boolean subtree can never occupy a numeric slot and vice versa.

The bounded loop-free state node (``lag``) references the value of its own child
expression from ``lag`` observations in the past (documented bound: ``MAX_LAG``;
``0 < lag <= MAX_LAG``). Evaluation at time ``t`` reads child rows ``<= t`` only:
rows with ``t >= lag`` read exactly ``t - lag``, and warm-up rows (``t < lag``)
clamp to the earliest available observation (index 0). Future information can
never leak into any node.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np


NUMERIC_UNARY = ("abs", "neg", "tanh", "sign")
NUMERIC_BINARY = ("add", "sub", "mul", "protected_div", "minimum", "maximum")
COMPARISON_BINARY = ("lt", "le", "gt", "ge", "eq")
BOOLEAN_BINARY = ("and", "or")
BOOLEAN_UNARY = ("not",)
NUMERIC_TERNARY = ("cond",)
STATE_OPERATION = "lag"
# Bounded loop-free lookback: a lag node may reference at most MAX_LAG past values.
MAX_LAG = 8
# Boolean leaves are comparisons or constant truth values; eq is valid but not sampled
# during initialisation because float equality is rarely useful in generated formulas.
COMPARISON_FOLDS = ("lt", "le", "gt", "ge")

NUMERIC_OPERATIONS = frozenset(
    ("feature", "constant") + NUMERIC_UNARY + NUMERIC_BINARY + NUMERIC_TERNARY + (STATE_OPERATION,)
)
BOOLEAN_OPERATIONS = frozenset(
    COMPARISON_BINARY + BOOLEAN_BINARY + BOOLEAN_UNARY + ("constant_true", "constant_false")
)


def _type_of_operation(operation: str) -> str:
    # Closed mapping from operation name to declared result type.
    if operation in NUMERIC_OPERATIONS:
        return "numeric"
    if operation in BOOLEAN_OPERATIONS:
        return "boolean"
    return "unknown"


@dataclass(frozen=True, slots=True)
class Node:
    """Immutable typed expression node (numeric or Boolean)."""

    operation: str
    children: tuple[Node, ...] = ()
    feature_index: int | None = None
    constant: float | None = None
    lag: int | None = None

    def __post_init__(self) -> None:
        # Enforce a closed grammar and exact arity before evaluating any candidate.
        if self.operation == "feature":
            if self.feature_index is None or self.feature_index < 0 or self.children:
                raise ValueError("feature nodes require a non-negative feature_index")
        elif self.operation == "constant":
            if self.constant is None or not np.isfinite(self.constant) or self.children:
                raise ValueError("constant nodes require a finite constant")
        elif self.operation == "constant_true" or self.operation == "constant_false":
            if self.children or self.feature_index is not None or self.constant is not None:
                raise ValueError(f"invalid payload for {self.operation}")
        elif self.operation == STATE_OPERATION:
            if self.lag is None or not 1 <= self.lag <= MAX_LAG or len(self.children) != 1:
                raise ValueError(
                    f"{STATE_OPERATION} nodes require 1 child and 1 <= lag <= {MAX_LAG}"
                )
        elif self.operation in NUMERIC_UNARY or self.operation in BOOLEAN_UNARY:
            if len(self.children) != 1 or self.feature_index is not None or self.constant is not None:
                raise ValueError(f"invalid arity or payload for {self.operation}")
        elif self.operation in NUMERIC_BINARY + COMPARISON_BINARY + BOOLEAN_BINARY:
            if len(self.children) != 2 or self.feature_index is not None or self.constant is not None:
                raise ValueError(f"invalid arity or payload for {self.operation}")
        elif self.operation in NUMERIC_TERNARY:
            if len(self.children) != 3 or self.feature_index is not None or self.constant is not None:
                raise ValueError(f"invalid arity or payload for {self.operation}")
        else:
            raise ValueError(f"unsupported expression operation: {self.operation}")
        # Structural typing rule: child types must satisfy the operator's signature.
        self._validate_child_types()

    def _validate_child_types(self) -> None:
        # Numeric operators need numeric children; comparisons need numeric children and
        # produce Boolean; Boolean operators need Boolean children.
        for child in self.children:
            if child.infer_type() == "unknown":
                raise ValueError(f"child operation {child.operation} has unknown type")
        if self.operation in COMPARISON_BINARY:
            if not all(child.infer_type() == "numeric" for child in self.children):
                raise ValueError("comparison operators require numeric children")
        elif self.operation in BOOLEAN_BINARY or self.operation in BOOLEAN_UNARY:
            if not all(child.infer_type() == "boolean" for child in self.children):
                raise ValueError("boolean operators require boolean children")
        elif self.operation in NUMERIC_TERNARY:
            condition, branch_true, branch_false = self.children
            if condition.infer_type() != "boolean":
                raise ValueError("conditional nodes require a boolean condition child")
            if branch_true.infer_type() != "numeric" or branch_false.infer_type() != "numeric":
                raise ValueError("conditional branches must be numeric")
        elif self.operation in NUMERIC_UNARY + NUMERIC_BINARY:
            if not all(child.infer_type() == "numeric" for child in self.children):
                raise ValueError("numeric operators require numeric children")
        elif self.operation == STATE_OPERATION:
            if self.children[0].infer_type() != "numeric":
                raise ValueError("state (lag) nodes require a numeric child")

    def infer_type(self) -> str:
        """Return this node's declared result type ('numeric' or 'boolean')."""
        return _type_of_operation(self.operation)

    @property
    def depth(self) -> int:
        # Terminal nodes have depth zero.
        return 0 if not self.children else 1 + max(child.depth for child in self.children)

    @property
    def size(self) -> int:
        # Complexity is the total number of AST nodes.
        return 1 + sum(child.size for child in self.children)

    @staticmethod
    def _validated_matrix(features: np.ndarray) -> np.ndarray:
        matrix = np.asarray(features, dtype=np.float64)
        if matrix.ndim != 2 or not np.isfinite(matrix).all():
            raise ValueError("features must be a finite 2D array")
        return matrix

    def evaluate(self, features: np.ndarray) -> np.ndarray:
        """Interpret this numeric expression for a 2D observations x features matrix."""
        matrix = self._validated_matrix(features)
        if self.infer_type() != "numeric":
            raise ValueError("expression result type is boolean; use evaluate_bool()")
        return self._evaluate(matrix)

    def evaluate_bool(self, features: np.ndarray) -> np.ndarray:
        """Interpret this Boolean expression into one bool per observation."""
        matrix = self._validated_matrix(features)
        if self.infer_type() != "boolean":
            raise ValueError("expression result type is numeric; use evaluate()")
        return self._evaluate_bool(matrix)

    def _evaluate(self, matrix: np.ndarray) -> np.ndarray:
        # Return a vector with one numeric result per observation.
        if self.operation == "feature":
            if self.feature_index >= matrix.shape[1]:
                raise ValueError("expression references a feature outside the input matrix")
            return matrix[:, self.feature_index]
        if self.operation == "constant":
            return np.full(matrix.shape[0], self.constant, dtype=np.float64)
        if self.operation == STATE_OPERATION:
            # The only temporal node: read the child ``lag`` rows back, clamping the
            # warm-up rows (t < lag) to the earliest observation. Every output row t
            # therefore depends only on child rows <= t: causal, never future-looking.
            lagged = self.children[0]._evaluate(matrix)
            shift = int(self.lag)
            output = np.empty_like(lagged)
            output[shift:] = lagged[:-shift] if shift < len(lagged) else lagged[:0]
            output[:shift] = lagged[0]
            return output
        if self.operation in NUMERIC_TERNARY:
            condition = self.children[0]._evaluate_bool(matrix)
            branch_true = self.children[1]._evaluate(matrix)
            branch_false = self.children[2]._evaluate(matrix)
            return np.where(condition, branch_true, branch_false)
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

    def _evaluate_bool(self, matrix: np.ndarray) -> np.ndarray:
        # Return one Boolean result per observation; NaN never becomes a truth value.
        if self.operation == "constant_true":
            return np.ones(matrix.shape[0], dtype=bool)
        if self.operation == "constant_false":
            return np.zeros(matrix.shape[0], dtype=bool)
        if self.operation in COMPARISON_BINARY:
            left = self.children[0]._evaluate(matrix)
            right = self.children[1]._evaluate(matrix)
            if self.operation == "lt":
                return left < right
            if self.operation == "le":
                return left <= right
            if self.operation == "gt":
                return left > right
            if self.operation == "ge":
                return left >= right
            return left == right
        if self.operation in BOOLEAN_BINARY:
            left = self.children[0]._evaluate_bool(matrix)
            right = self.children[1]._evaluate_bool(matrix)
            if self.operation == "and":
                return np.logical_and(left, right)
            return np.logical_or(left, right)
        if self.operation in BOOLEAN_UNARY:
            return np.logical_not(self.children[0]._evaluate_bool(matrix))
        raise RuntimeError(f"unhandled boolean operation: {self.operation}")


def _replace(root: Node, path: tuple[int, ...], replacement: Node) -> Node:
    # Rebuild immutable parent nodes along the selected subtree path.
    if not path:
        return replacement
    index = path[0]
    children = list(root.children)
    children[index] = _replace(children[index], path[1:], replacement)
    return Node(root.operation, tuple(children), root.feature_index, root.constant, root.lag)


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


def _slot_type(root: Node, path: tuple[int, ...]) -> str:
    # The declared type of the slot at ``path``: the root's own type when the path is
    # empty, otherwise the child type selected by the last path element.
    if not path:
        return root.infer_type()
    anchor = _subtree(root, path[:-1])
    return anchor.children[path[-1]].infer_type()


class GeneticProgrammer:
    """Small tournament-selection GP with bounded typed trees and deterministic mutation."""

    def __init__(
        self,
        *,
        feature_count: int,
        population_size: int = 64,
        generations: int = 20,
        max_depth: int = 5,
        max_nodes: int = 63,
        mutation_rate: float = 0.2,
        max_lag: int = 4,
        seed: int = 42,
    ) -> None:
        # Reject resource limits that could make generated AST evaluation unbounded.
        if feature_count < 1 or population_size < 4 or generations < 1:
            raise ValueError("feature_count, population_size or generations is invalid")
        if max_depth < 1 or max_nodes < 3 or not 0 <= mutation_rate <= 1:
            raise ValueError("invalid tree complexity or mutation constraints")
        # The lookback is bounded so temporal references can never walk far back or loop.
        self.max_lag = int(min(max(int(max_lag), 1), MAX_LAG))
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

    def _lagged_terminal(self) -> Node:
        # Typed numeric terminal: a past value of a feature (loop-free, bounded lookback).
        lag = int(self.rng.integers(1, self.max_lag + 1))
        return Node(STATE_OPERATION, (self._terminal(),), lag=lag)

    def _comparison(self, depth: int) -> Node:
        # Build one deterministic typed comparison; children keep the remaining budget.
        operation = COMPARISON_FOLDS[int(self.rng.integers(len(COMPARISON_FOLDS)))]
        return Node(operation, (self._random_numeric(depth), self._random_numeric(depth)))

    def _boolean_terminal(self, depth: int) -> Node:
        # Boolean leaves are either a comparison subtree or a constant truth value.
        # A comparison consumes depth, so it is only sampled while budget remains.
        draw = self.rng.random()
        if draw < 0.6 and depth < self.max_depth:
            return self._comparison(depth + 1)
        if draw < 0.8:
            return Node("constant_true")
        return Node("constant_false")

    def _random_bool(self, depth: int) -> Node:
        # Grow a typed Boolean subtree without exceeding configured depth bounds.
        if depth >= self.max_depth:
            return Node("constant_true") if self.rng.random() < 0.5 else Node("constant_false")
        if self.rng.random() < 0.3:
            return self._boolean_terminal(depth)
        draw = self.rng.random()
        if draw < 0.45:
            operation = BOOLEAN_BINARY[int(self.rng.integers(len(BOOLEAN_BINARY)))]
            return Node(operation, (self._random_bool(depth + 1), self._random_bool(depth + 1)))
        if draw < 0.6:
            return Node("not", (self._random_bool(depth + 1),))
        return self._comparison(depth + 1)

    def _random_numeric(self, depth: int) -> Node:
        # Grow a typed numeric subtree; temporality enters only through the lag terminal.
        if depth >= self.max_depth:
            return self._terminal()
        if self.rng.random() < 0.35:
            if self.rng.random() < 0.25:
                return self._lagged_terminal()
            return self._terminal()
        draw = self.rng.random()
        if draw < 0.25:
            operation = NUMERIC_UNARY[int(self.rng.integers(len(NUMERIC_UNARY)))]
            return Node(operation, (self._random_numeric(depth + 1),))
        if draw < 0.45:
            # Conditional control flow: typed Boolean condition over numeric branches.
            return Node("cond", (
                self._random_bool(depth + 1),
                self._random_numeric(depth + 1),
                self._random_numeric(depth + 1),
            ))
        operation = NUMERIC_BINARY[int(self.rng.integers(len(NUMERIC_BINARY)))]
        return Node(operation, (
            self._random_numeric(depth + 1),
            self._random_numeric(depth + 1),
        ))

    def _random_tree(self, depth: int) -> Node:
        # Roots are numeric: expression output stays a signed policy score.
        return self._random_numeric(depth)

    def _new_individual(self) -> Node:
        # Retry bounded generation before falling back to a guaranteed terminal.
        for _ in range(64):
            candidate = self._random_tree(0)
            if candidate.depth <= self.max_depth and candidate.size <= self.max_nodes:
                return candidate
        return self._terminal()

    def _mutate(self, tree: Node) -> Node:
        # Replace one randomly selected subtree with a same-typed subtree.
        for _ in range(32):
            paths = _paths(tree)
            path = paths[int(self.rng.integers(len(paths)))]
            target_type = _slot_type(tree, path)
            replacement = (
                self._random_numeric(len(path))
                if target_type == "numeric"
                else self._random_bool(len(path))
            )
            mutant = _replace(tree, path, replacement)
            if mutant.depth <= self.max_depth and mutant.size <= self.max_nodes:
                return mutant
        return tree

    def _crossover(self, left: Node, right: Node) -> Node:
        # Exchange two equally typed subtrees while enforcing complexity constraints.
        for _ in range(32):
            left_paths = _paths(left)
            right_paths = _paths(right)
            left_path = left_paths[int(self.rng.integers(len(left_paths)))]
            right_path = right_paths[int(self.rng.integers(len(right_paths)))]
            donor = _subtree(right, right_path)
            if donor.infer_type() != _slot_type(left, left_path):
                continue
            child = _replace(left, left_path, donor)
            if child.depth <= self.max_depth and child.size <= self.max_nodes:
                return child
        return left

    def run(self, features: np.ndarray, fitness: Callable[[np.ndarray], float]) -> dict[str, object]:
        """Evolve typed expressions using caller-supplied train-only fitness."""
        # Caller must pass TRAIN-derived features; this function has no market-data access.
        matrix = np.asarray(features, dtype=np.float64)
        if matrix.ndim != 2 or matrix.shape[1] != self.feature_count:
            raise ValueError("features shape does not match feature_count")
        if not np.isfinite(matrix).all():
            raise ValueError("features must be finite")
        population = [self._new_individual() for _ in range(self.population_size)]
        history: list[dict[str, object]] = []
        failures: list[str] = []
        candidate_archive: list[dict[str, object]] = []
        # Every evolved tree receives a stable per-generation identity and ancestry record.
        population_ids = [f"gp-g0-{index:06d}" for index in range(self.population_size)]
        population_lineage = [
            {
                "operator": "random_initialisation",
                "generation": 0,
                "parent_candidate_ids": [],
                "seed": self.seed,
                "max_lag": self.max_lag,
            }
            for _ in population
        ]

        def score(
            tree: Node,
            generation: int,
            index: int,
            candidate_id: str,
            lineage: dict[str, object],
        ) -> float:
            # Penalise expression size to discourage unnecessarily complex formulas.
            try:
                output = tree._evaluate(matrix)
                if not np.isfinite(output).all():
                    # Guard against any non-finite numeric result; such candidates are
                    # recorded as failures rather than signals.
                    raise ValueError("expression produced non-finite values")
                value = float(fitness(output)) - 1e-4 * tree.size
                if not np.isfinite(value):
                    raise ValueError("fitness returned non-finite score")
                history.append({
                    "generation": generation, "index": index, "candidate_id": candidate_id,
                    "fitness": value, "tree_size": tree.size, "tree_depth": tree.depth,
                })
                candidate_archive.append({
                    "candidate_id": candidate_id,
                    "generation": generation,
                    "index": index,
                    "tree": tree,
                    "fitness": value,
                    "status": "succeeded",
                    "lineage": dict(lineage),
                })
                return value
            except Exception as exc:  # noqa: BLE001 - retain failed candidate context.
                failure = f"generation={generation},candidate={index}: {type(exc).__name__}: {exc}"
                failures.append(failure)
                candidate_archive.append({
                    "candidate_id": candidate_id,
                    "generation": generation,
                    "index": index,
                    "tree": tree,
                    "fitness": -np.inf,
                    "status": "failed",
                    "failure_reason": failure,
                    "lineage": dict(lineage),
                })
                return -np.inf

        scores = [
            score(tree, 0, index, population_ids[index], population_lineage[index])
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
                "max_lag": self.max_lag,
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
                    "max_lag": self.max_lag,
                })
            population = next_population
            population_ids = next_ids
            population_lineage = next_lineage
            scores = [
                score(
                    tree,
                    generation,
                    index,
                    population_ids[index],
                    population_lineage[index],
                )
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
            "candidate_archive": tuple(candidate_archive),
            "fitness": tuple(float(value) for value in scores),
            "history": tuple(history),
            "failures": tuple(failures),
        }
