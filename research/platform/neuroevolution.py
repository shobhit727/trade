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
    candidate_archive: tuple[dict[str, object], ...] = ()


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
        batch_predictor: Callable[[np.ndarray, np.ndarray], np.ndarray] | None = None,
        batch_size: int = 16,
    ) -> EvolutionTrace:
        """Evolve network parameters against the supplied training-only fitness function."""
        # Inputs are copied so caller mutation cannot modify an active search.
        matrix = np.asarray(features, dtype=np.float64)
        if matrix.ndim != 2 or matrix.shape[1] != self.network.input_size:
            raise ValueError("feature shape does not match network input_size")
        if not np.isfinite(matrix).all():
            raise ValueError("features must be finite")
        if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size < 1:
            raise ValueError("batch_size must be a positive integer")
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
        candidate_archive: list[dict[str, object]] = []
        evaluations = 0
        half = self.population_size // 2
        mean_parent_ids: list[str] = []

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
            candidate_ids = [
                f"es-g{generation:04d}-c{index:06d}"
                for index in range(self.population_size)
            ]
            # Process network predictions in bounded chunks to cap host/device memory.
            for batch_start in range(0, self.population_size, batch_size):
                batch_end = min(batch_start + batch_size, self.population_size)
                prediction_batch = None
                if batch_predictor is not None:
                    prediction_batch = np.asarray(
                        batch_predictor(matrix, population[batch_start:batch_end]),
                        dtype=np.float64,
                    )
                    expected_shape = (
                        batch_end - batch_start, len(matrix), self.network.output_size
                    )
                    if (
                        prediction_batch.shape != expected_shape
                        or not np.isfinite(prediction_batch).all()
                    ):
                        raise ValueError(
                            f"batch_predictor must return finite scores with shape {expected_shape}"
                        )
                for index in range(batch_start, batch_end):
                    parameters = population[index]
                    status = "succeeded"
                    failure_reason = None
                    try:
                        predictions = (
                            prediction_batch[index - batch_start]
                            if prediction_batch is not None
                            else self.network.predict(matrix, parameters)
                        )
                        score = float(fitness(predictions))
                        if not np.isfinite(score):
                            raise ValueError("fitness returned a non-finite score")
                        scores[index] = score
                    except Exception as exc:  # noqa: BLE001 - keep failed evaluations in the trace.
                        status = "failed"
                        failure_reason = (
                            f"generation={generation},candidate={index}: {type(exc).__name__}: {exc}"
                        )
                        failures.append(failure_reason)
                    lineage = {
                        "operator": "mirrored_noise_evolution_strategy",
                        "generation": generation,
                        "parent_candidate_ids": list(mean_parent_ids),
                        "noise_pair_index": index if index < half else index - half,
                        "perturbation_sign": 1 if index < half else -1,
                        "noise_std": self.noise_std,
                        "learning_rate": self.learning_rate,
                        "seed": self.seed,
                        "prediction_backend": "batch" if batch_predictor is not None else "scalar",
                        "prediction_batch_index": batch_start // batch_size,
                    }
                    candidate_archive.append({
                        "candidate_id": candidate_ids[index],
                        "generation": generation,
                        "index": index,
                        "parameters": parameters.copy(),
                        "fitness": float(scores[index]),
                        "status": status,
                        "failure_reason": failure_reason,
                        "lineage": lineage,
                    })
                    evaluations += 1

            # Convert valid population scores into centred rank utilities.
            valid = np.flatnonzero(np.isfinite(scores))
            if len(valid):
                ordered = valid[np.argsort(scores[valid], kind="stable")]
                # The next mean is a function of the full valid ranked population.
                mean_parent_ids = [candidate_ids[int(index)] for index in ordered]
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
            candidate_archive=tuple(candidate_archive),
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


# ---------------------------------------------------------------------------
# Bounded topology evolution (audit F-019)
# ---------------------------------------------------------------------------

TOPOLOGY_ACTIVATIONS = ("tanh", "relu", "sigmoid")
# Hard bounds for the bounded architecture search space.
MIN_HIDDEN_LAYERS = 1
MAX_HIDDEN_LAYERS = 4
MIN_HIDDEN_WIDTH = 4
MAX_HIDDEN_WIDTH = 128
# Documented parameter cap for any evolved topology (weights + biases).
TOPOLOGY_MAX_PARAMETERS = 120_000
# Topology mutations are recorded per candidate and replayed from (seed, log).
TOPOLOGY_MUTATIONS = ("widen", "narrow", "add_layer", "remove_layer", "add_skip", "remove_skip")


@dataclass(frozen=True, slots=True)
class TopologyNetwork:
    """Bounded multi-layer dense network with optional adjacent-layer skips.

    Layout: input -> hidden_0 -> ... -> hidden_{n-1} -> output, where each hidden
    layer has its own activation and any adjacent pair (hidden_i, hidden_{i+1})
    may carry a residual skip connection. One shared skip may also bridge the last
    hidden layer to the output.
    """

    input_size: int
    hidden_sizes: tuple[int, ...]
    activations: tuple[str, ...]
    skips: tuple[tuple[int, int], ...] = ()
    output_size: int = 1

    def __post_init__(self) -> None:
        if min(self.input_size, self.output_size) < 1:
            raise ValueError("network dimensions must be positive")
        if not MIN_HIDDEN_LAYERS <= len(self.hidden_sizes) <= MAX_HIDDEN_LAYERS:
            raise ValueError(
                f"hidden layer count must be within [{MIN_HIDDEN_LAYERS}, {MAX_HIDDEN_LAYERS}]"
            )
        if any(not MIN_HIDDEN_WIDTH <= width <= MAX_HIDDEN_WIDTH for width in self.hidden_sizes):
            raise ValueError(
                f"hidden width must be within [{MIN_HIDDEN_WIDTH}, {MAX_HIDDEN_WIDTH}]"
            )
        if len(self.activations) != len(self.hidden_sizes) or any(
            activation not in TOPOLOGY_ACTIVATIONS for activation in self.activations
        ):
            raise ValueError("every hidden layer needs one known activation")
        # A skip (source, target) feeds hidden layer ``source``'s output into layer
        # ``target``'s pre-activation input; ``target`` may be the output layer.
        for source, target in self.skips:
            if not 0 <= source < len(self.hidden_sizes) or target != source + 1:
                raise ValueError("skip connections must link adjacent layers")
        if self.parameter_count > TOPOLOGY_MAX_PARAMETERS:
            raise ValueError("topology parameter count exceeds the documented cap")

    @property
    def parameter_count(self) -> int:
        # Dense weights and biases for every adjacent pair, plus one row per skip.
        previous = self.input_size
        total = 0
        for width in self.hidden_sizes:
            total += previous * width + width
            previous = width
        total += previous * self.output_size + self.output_size
        for source, target in self.skips:
            # Skip blocks are rectangular: layer ``source`` output width feeds the
            # target layer input, which may differ after width mutations.
            total += self._skip_shape(source, target)[0] * self._skip_shape(source, target)[1]
        return total

    def _skip_shape(self, source: int, target: int) -> tuple[int, int]:
        # (rows, columns) of the skip block: source output width x target input width.
        rows = self.hidden_sizes[source]
        columns = (
            self.output_size if target == len(self.hidden_sizes) else self.hidden_sizes[target]
        )
        return rows, columns

    def parameter_layout(self) -> tuple[tuple[str, int, int, int], ...]:
        """Return the deterministic flat-parameter layout as named segments.

        Each segment is (name, offset, shape_rows, shape_cols); biases are (rows, 1).
        """
        segments: list[tuple[str, int, int, int]] = []
        offset = 0
        previous = self.input_size
        for index, width in enumerate(self.hidden_sizes):
            segments.append((f"W{index}", offset, previous, width))
            offset += previous * width
            segments.append((f"b{index}", offset, width, 1))
            offset += width
            previous = width
        output_index = len(self.hidden_sizes)
        segments.append((f"W{output_index}", offset, previous, self.output_size))
        offset += previous * self.output_size
        segments.append((f"b{output_index}", offset, self.output_size, 1))
        offset += self.output_size
        for source, target in self.skips:
            rows, columns = self._skip_shape(source, target)
            segments.append((f"S{source}-{target}", offset, rows, columns))
            offset += rows * columns
        return tuple(segments)

    def initial_parameters(self, rng: np.random.Generator) -> np.ndarray:
        # Deterministic, activation-aware initialisation from the supplied generator.
        parameters = np.zeros(self.parameter_count, dtype=np.float64)
        for name, offset, rows, columns in self.parameter_layout():
            count = rows * columns
            if name.startswith("W"):
                bound = np.sqrt(1.0 / rows)
                parameters[offset:offset + count] = rng.uniform(-bound, bound, size=count)
            elif name.startswith("S"):
                # Skips start at zero so a new skip is a no-op until evolution uses it.
                parameters[offset:offset + count] = 0.0
            else:
                parameters[offset:offset + count] = 0.0
        return parameters

    def predict(self, features: np.ndarray, parameters: np.ndarray) -> np.ndarray:
        """Forward finite feature rows through this topology."""
        x = np.asarray(features, dtype=np.float64)
        theta = np.asarray(parameters, dtype=np.float64)
        if x.ndim != 2 or x.shape[1] != self.input_size or not np.isfinite(x).all():
            raise ValueError("features must be finite and match input_size")
        if theta.shape != (self.parameter_count,) or not np.isfinite(theta).all():
            raise ValueError("parameter vector has incorrect shape or non-finite values")
        layout = {name: (offset, rows, columns) for name, offset, rows, columns in self.parameter_layout()}

        def block(name: str) -> np.ndarray:
            offset, rows, columns = layout[name]
            return theta[offset:offset + rows * columns].reshape(rows, columns)

        skip_set = set(self.skips)
        layer_outputs: list[np.ndarray] = []
        hidden = x
        # Hidden layers apply W, b, an optional incoming skip, then their activation.
        for index in range(len(self.hidden_sizes)):
            z = hidden @ block(f"W{index}") + block(f"b{index}")[:, 0]
            if (index - 1, index) in skip_set:
                z = z + layer_outputs[index - 1] @ block(f"S{index - 1}-{index}")
            if self.activations[index] == "relu":
                hidden = np.maximum(z, 0.0)
            elif self.activations[index] == "sigmoid":
                hidden = 1.0 / (1.0 + np.exp(-z))
            else:
                hidden = np.tanh(z)
            layer_outputs.append(hidden)
        # Output layer keeps the bounded tanh policy score of DenseMLP.
        z_out = hidden @ block(f"W{len(self.hidden_sizes)}") + block(f"b{len(self.hidden_sizes)}")[:, 0]
        output_index = len(self.hidden_sizes)
        if (output_index - 1, output_index) in skip_set:
            z_out = z_out + layer_outputs[output_index - 1] @ block(f"S{output_index - 1}-{output_index}")
        return np.tanh(z_out)

    def sample_mutation(self, rng: np.random.Generator) -> dict[str, object]:
        """Draw one bounded topology mutation with its arguments from ``rng``.

        The returned entry is a complete, serialisable record: replaying
        ``apply_mutation_args(entry)`` from the root topology reproduces the exact
        mutated topology without any random state.
        """
        mutation = TOPOLOGY_MUTATIONS[int(rng.integers(len(TOPOLOGY_MUTATIONS)))]
        sizes = self.hidden_sizes
        skips = self.skips
        entry: dict[str, object] = {"op": mutation}
        if mutation in {"widen", "narrow"}:
            entry["index"] = int(rng.integers(len(sizes)))
        elif mutation == "add_layer":
            entry["index"] = int(rng.integers(len(sizes) + 1))
            entry["width"] = int(rng.integers(MIN_HIDDEN_WIDTH, MAX_HIDDEN_WIDTH + 1))
            entry["activation"] = TOPOLOGY_ACTIVATIONS[int(rng.integers(len(TOPOLOGY_ACTIVATIONS)))]
        elif mutation == "remove_layer":
            entry["index"] = int(rng.integers(len(sizes)))
        elif mutation == "add_skip":
            pairs = [
                (index, index + 1)
                for index in range(len(sizes))
                if (index, index + 1) not in skips
            ]
            entry["skip"] = pairs[int(rng.integers(len(pairs)))] if pairs else None
        elif mutation == "remove_skip":
            entry["index"] = int(rng.integers(len(skips))) if skips else None
        return entry

    def apply_mutation_args(self, entry: dict[str, object]) -> "TopologyNetwork":
        """Apply one recorded mutation entry; the pure replay half of ``sample_mutation``."""
        mutation = entry.get("op")
        if mutation not in TOPOLOGY_MUTATIONS:
            raise ValueError(f"unknown topology mutation: {mutation}")
        sizes = list(self.hidden_sizes)
        activations = list(self.activations)
        skips = list(self.skips)
        rejected = False
        if mutation == "widen":
            index = int(entry["index"]) % len(sizes)
            candidate = min(sizes[index] * 2, MAX_HIDDEN_WIDTH)
            rejected = candidate == sizes[index]
            if not rejected:
                sizes[index] = candidate
        elif mutation == "narrow":
            index = int(entry["index"]) % len(sizes)
            candidate = max(sizes[index] // 2, MIN_HIDDEN_WIDTH)
            rejected = candidate == sizes[index]
            if not rejected:
                sizes[index] = candidate
        elif mutation == "add_layer":
            if len(sizes) >= MAX_HIDDEN_LAYERS:
                rejected = True
            else:
                index = int(entry["index"]) % (len(sizes) + 1)
                sizes.insert(index, int(entry["width"]))
                activations.insert(index, str(entry["activation"]))
        elif mutation == "remove_layer":
            if len(sizes) <= MIN_HIDDEN_LAYERS:
                rejected = True
            else:
                index = int(entry["index"]) % len(sizes)
                sizes.pop(index)
                activations.pop(index)
                skips = [
                    (
                        source - 1 if source > index else source,
                        target - 1 if target > index else target,
                    )
                    for source, target in skips
                    if source != index and target != index
                ]
        elif mutation == "add_skip":
            skip = entry.get("skip")
            if skip is None:
                rejected = True
            else:
                skips.append((int(skip[0]), int(skip[1])))
                skips.sort()
        elif mutation == "remove_skip":
            index = entry.get("index")
            if index is None or not skips:
                rejected = True
            else:
                skips.pop(int(index) % len(skips))
        try:
            return TopologyNetwork(
                input_size=self.input_size,
                hidden_sizes=tuple(sizes),
                activations=tuple(activations),
                skips=tuple(skips),
                output_size=self.output_size,
            )
        except ValueError:
            # Parameter cap or structural bound violated: reject the mutation and
            # keep the parent topology unchanged.
            return self

    def with_mutation(self, entry: dict[str, object]) -> "TopologyNetwork":
        """Replay one recorded mutation entry (seed, log reproducibility)."""
        return self.apply_mutation_args(entry)


class TopologyEvolutionStrategy:
    """Evolve bounded network topologies and weights under one shared fitness path.

    Every topology change is recorded as a named mutation in the candidate lineage and
    is reproducible by replaying the recorded mutation log from the same seed. There is
    no preference for larger networks: fitness alone selects candidates, and every
    topology travels with the candidate in the archive.
    """

    def __init__(
        self,
        *,
        input_size: int,
        output_size: int = 1,
        population_size: int = 8,
        generations: int = 10,
        weight_steps: int = 3,
        learning_rate: float = 0.05,
        noise_std: float = 0.1,
        weight_limit: float = 8.0,
        seed: int = 42,
    ) -> None:
        if input_size < 1 or output_size < 1:
            raise ValueError("network dimensions must be positive")
        if population_size < 2 or generations < 1 or weight_steps < 1:
            raise ValueError("invalid topology evolution bounds")
        if learning_rate <= 0 or noise_std <= 0 or weight_limit <= 0:
            raise ValueError("invalid topology evolution hyperparameters")
        self.input_size = input_size
        self.output_size = output_size
        self.population_size = population_size
        self.generations = generations
        self.weight_steps = weight_steps
        self.learning_rate = learning_rate
        self.noise_std = noise_std
        self.weight_limit = weight_limit
        self.seed = seed
        # Total fitness evaluations; incremented inside _fitness_of.
        self.fitness_calls = 0

    def _fitness_of(
        self,
        network: TopologyNetwork,
        parameters: np.ndarray,
        matrix: np.ndarray,
        fitness: Callable[[np.ndarray], float],
        batch_predictor: Callable[[np.ndarray, np.ndarray, "TopologyNetwork"], np.ndarray] | None,
    ) -> float:
        # Every fitness call is counted, including mirrored weight-perturbation probes.
        self.fitness_calls += 1
        if batch_predictor is not None:
            predictions = np.asarray(batch_predictor(matrix, parameters, network), dtype=np.float64)
            expected = (len(matrix), self.output_size)
            if predictions.shape != expected or not np.isfinite(predictions).all():
                raise ValueError(
                    f"batch_predictor must return finite scores with shape {expected}"
                )
        else:
            predictions = network.predict(matrix, parameters)
            expected = (len(matrix), self.output_size)
            if predictions.shape != expected or not np.isfinite(predictions).all():
                raise ValueError(
                    f"predictions must be finite with shape {expected}"
                )
        score = float(fitness(predictions))
        if not np.isfinite(score):
            raise ValueError("fitness returned a non-finite score")
        return score

    def run(
        self,
        features: np.ndarray,
        fitness: Callable[[np.ndarray], float],
        *,
        batch_predictor: Callable[[np.ndarray, np.ndarray, "TopologyNetwork"], np.ndarray] | None = None,
    ) -> dict[str, object]:
        """Search bounded topologies with the same train-only fitness contract as ES."""
        matrix = np.asarray(features, dtype=np.float64)
        if matrix.ndim != 2 or matrix.shape[1] != self.input_size:
            raise ValueError("feature shape does not match input_size")
        if not np.isfinite(matrix).all():
            raise ValueError("features must be finite")
        rng = np.random.default_rng(self.seed)
        root = TopologyNetwork(
            input_size=self.input_size,
            hidden_sizes=(16,),
            activations=("tanh",),
        )
        root_parameters = root.initial_parameters(rng)
        best = {
            "fitness": -np.inf,
            "network": root,
            "parameters": root_parameters,
            "mutation_log": (),
            "candidate_id": "topo-root",
        }
        archive: list[dict[str, object]] = []
        history: list[dict[str, float]] = []
        failures: list[str] = []
        candidate_ids = [f"topo-g0000-c{index:06d}" for index in range(self.population_size)]

        def evaluate(
            network: TopologyNetwork,
            parameters: np.ndarray,
            mutations: tuple[str, ...],
            candidate_id: str,
            generation: int,
            parent_ids: list[str],
        ) -> float:
            try:
                score = self._fitness_of(network, parameters, matrix, fitness, batch_predictor)
                archive.append({
                    "candidate_id": candidate_id,
                    "generation": generation,
                    "topology": network,
                    "parameters": parameters.copy(),
                    "mutation_log": list(mutations),
                    "parameter_count": network.parameter_count,
                    "hidden_layers": len(network.hidden_sizes),
                    "hidden_widths": tuple(network.hidden_sizes),
                    "activations": tuple(network.activations),
                    "skips": list(network.skips),
                    "fitness": score,
                    "status": "succeeded",
                    "lineage": {
                        "operator": "bounded_topology_evolution",
                        "generation": generation,
                        "parent_candidate_ids": list(parent_ids),
                        "mutation_log": list(mutations),
                        "seed": self.seed,
                    },
                })
                return score
            except Exception as exc:  # noqa: BLE001 - retain failed topology evaluations.
                failures.append(
                    f"generation={generation},candidate={candidate_id}: {type(exc).__name__}: {exc}"
                )
                archive.append({
                    "candidate_id": candidate_id,
                    "generation": generation,
                    "topology": network,
                    "parameters": np.zeros(0),
                    "mutation_log": list(mutations),
                    "parameter_count": network.parameter_count,
                    "hidden_layers": len(network.hidden_sizes),
                    "hidden_widths": tuple(network.hidden_sizes),
                    "activations": tuple(network.activations),
                    "skips": list(network.skips),
                    "fitness": -np.inf,
                    "status": "failed",
                    "failure_reason": failures[-1],
                    "lineage": {
                        "operator": "bounded_topology_evolution",
                        "generation": generation,
                        "parent_candidate_ids": list(parent_ids),
                        "mutation_log": list(mutations),
                        "seed": self.seed,
                    },
                })
                return -np.inf

        parent_ids: list[str] = []
        for generation in range(self.generations):
            scores = []
            for index in range(self.population_size):
                candidate_id = (
                    candidate_ids[index] if generation == 0 else f"topo-g{generation:04d}-c{index:06d}"
                )
                if generation == 0 and index == 0:
                    # Generation zero starts from the deterministic root topology.
                    network = root
                    parameters = root_parameters
                    mutations: tuple[str, ...] = ()
                else:
                    # Each candidate is one deterministic mutation log of the root
                    # lineage; entries carry their sampled arguments so the exact
                    # topology is reproducible from (seed, log) alone.
                    network = root
                    mutations = tuple(
                        root.sample_mutation(rng) for _ in range(int(rng.integers(1, 4)))
                    )
                    for entry in mutations:
                        network = network.with_mutation(entry)
                    parameters = network.initial_parameters(rng)
                    for _ in range(self.weight_steps):
                        noise = rng.normal(0.0, self.noise_std, size=parameters.shape)
                        # Mirrored pair: evaluate plus/minus perturbations, keep the better.
                        plus = np.clip(parameters + noise, -self.weight_limit, self.weight_limit)
                        minus = np.clip(parameters - noise, -self.weight_limit, self.weight_limit)
                        try:
                            plus_score = self._fitness_of(network, plus, matrix, fitness, batch_predictor)
                            minus_score = self._fitness_of(network, minus, matrix, fitness, batch_predictor)
                        except Exception:  # noqa: BLE001 - fall back to unperturbed weights.
                            continue
                        parameters = plus if plus_score >= minus_score else minus
                    weight_probe_scores = (plus_score, minus_score)
                score = evaluate(
                    network, parameters, mutations, candidate_id, generation, list(parent_ids)
                )
                scores.append(score)
                if score > best["fitness"]:
                    best = {
                        "fitness": score,
                        "network": network,
                        "parameters": parameters.copy(),
                        "mutation_log": mutations,
                        "candidate_id": candidate_id,
                    }
            valid = [value for value in scores if np.isfinite(value)]
            history.append({
                "generation": float(generation),
                "best_fitness": float(max(valid)) if valid else -np.inf,
                "median_fitness": float(np.median(valid)) if valid else -np.inf,
                "mean_parameter_count": float(
                    np.mean([item["parameter_count"] for item in archive if item["generation"] == generation])
                ),
            })
            # Elitist lineage: next generation descends from the current best candidate.
            parent_ids = [best["candidate_id"]]
            candidate_ids = [
                f"topo-g{generation + 1:04d}-c{index:06d}" for index in range(self.population_size)
            ]
        if not np.isfinite(best["fitness"]):
            raise RuntimeError("topology evolution produced no valid candidate")
        return {
            "seed": self.seed,
            "best_network": best["network"],
            "best_parameters": best["parameters"],
            "best_fitness": float(best["fitness"]),
            "best_mutation_log": tuple(best["mutation_log"]),
            "candidate_archive": tuple(archive),
            "history": tuple(history),
            "failures": tuple(failures),
            "evaluations": self.fitness_calls,
        }


def evolve_topology(
    features: np.ndarray,
    fitness: Callable[[np.ndarray], float],
    *,
    population_size: int = 8,
    generations: int = 10,
    seed: int = 42,
) -> dict[str, object]:
    """Convenience wrapper for a bounded topology-evolution experiment."""
    matrix = np.asarray(features, dtype=np.float64)
    if matrix.ndim != 2:
        raise ValueError("features must be a 2D matrix")
    return TopologyEvolutionStrategy(
        input_size=matrix.shape[1],
        population_size=population_size,
        generations=generations,
        seed=seed,
    ).run(matrix, fitness)
