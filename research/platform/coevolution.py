"""Mixed-genome co-evolution: one bounded population across genome families (audit F-025).

The platform's evolutionary workers (``genetic_programming.py``, ``neuroevolution.py``,
``composition.py``) each evolve one family in isolation. This module places all three
supported genome families into ONE bounded population so they can be compared and, in a
strictly controlled way, exchange useful components.

Contracts (audit section 7.6):

1. Common candidate interface: :class:`MixedCandidate` (identity, lineage, objectives).
2. Common immutable genome record: :class:`MixedGenome` (family, frozen payload,
   frozen parameters, optional embedded component). Payloads reuse the immutable
   genome types of each family module; nothing here mutates a genome.
3. Genome validation rules: ``MixedGenome.__post_init__`` type-checks payload against
   family, requires numeric GP roots, exact neuro parameter counts, and validates an
   embedded component against the carrier composition's compatibility graph.
4. Common fitness contract: :class:`FamilyFitness` supplies one callable per family;
   all callables must return scores on ONE common scale because selection is
   family-agnostic. Callers remain responsible for train-only data access.
5. Common lineage contract: every candidate records ``operator``,
   ``parent_candidate_ids``, ``generation`` and ``seed``.
6. Shared candidate budget: every candidate costs exactly ONE evaluation, regardless
   of family. Total evaluations = ``3 * slots_per_family * (generations + 1)``.
7. Equal-cost comparisons: both population modes (independent families vs one mixed
   population) use identical population layout, generations, seed and fitness
   callables, so evaluation counts are identical by construction and verified at
   runtime by :func:`run_coevolution_comparison`.
8. Cross-family mutation rules: NONE. Mutation stays family-specific. The only
   cross-family pathway is the migration channel (item below).
9. Cross-family crossover rules: crossover between different families raises
   ``ValueError`` in :class:`OperatorDispatch` before any family operator runs
   (a GP tree never crosses with a neuro net).
10. Selection across genome types: family-agnostic Pareto ranking over the two
    objectives ``(fitness, max)`` and ``(complexity_ratio, min)`` using the public
    ``pareto.non_dominated_fronts``/``crowding_distance`` machinery. Anti-domination
    guardrail: every family always keeps exactly ``slots_per_family`` slots, so no
    family can grow its share of the population or its evaluation budget.
11. Population diversity: NSGA-II crowding distance preserves objective extremes
    (including each family's best-fitness candidate) within fronts.
12. Archive and duplicate rules: every evaluated candidate is appended to
    ``candidate_archive`` with a globally unique sequence id; genomes are immutable so
    archived records cannot drift.
13. Stopping rules: a fixed, caller-chosen generation count (reproducible; no
    wall-clock or convergence early stopping).
14. CPU/RAM limits: inherited from each family's documented bounds (GP depth/node
    caps, ``TopologyNetwork`` parameter cap, composition component cap). No GPU/VRAM
    is used; everything is a CPU reference implementation.
15. Reproducible tests: ``tests/unit/test_research_platform_coevolution.py`` runs the
    engine with fixed seeds and asserts family survival, operator dispatch, migration
    bounds, budget equality and comparison-front parity.

Migration policy (documented bounds):

- Each generation ``contested = floor(migrant_fraction * slots_per_family)`` slots of
  EVERY family are contested (``migrant_fraction`` in ``[0, 0.5]``; default 0.1).
  Migration activates only when ``contested >= 1``. Contested slots are filled from
  the migration channel instead of normal family breeding; uncontested slots are
  always filled by family-internal breeding.
- A foreign component may enter another family ONLY as an embedded component inside
  a COMPOSITION genome (the composition family is the sole carrier). A composition
  candidate can embed at most ``MAX_EMBEDDED_PER_GENOME`` foreign payloads; embedding
  happens exclusively through the migration channel (composition mutation can drop
  but never create an embedding; crossover preserves the left parent's embedding).
- The reverse direction (emigration) extracts an embedded payload from the
  best-ranking composition carrier and installs it as a pure GP or neuro genome in
  that family's contested slots.
- Migration copies payloads; it never removes the donor from its own family, so
  family slot counts and per-family evaluation counts are unchanged by migration.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Callable, Sequence

import numpy as np

from .composition import (
    ALLOWED_ROLES,
    SINGLETON_ROLES,
    Component,
    Composition,
    roles_compatible,
)
from .genetic_programming import (
    BOOLEAN_BINARY,
    BOOLEAN_UNARY,
    COMPARISON_BINARY,
    COMPARISON_FOLDS,
    MAX_LAG,
    NUMERIC_BINARY,
    NUMERIC_TERNARY,
    NUMERIC_UNARY,
    STATE_OPERATION,
    Node,
)
from .neuroevolution import TOPOLOGY_MAX_PARAMETERS, TopologyNetwork
from .pareto import ParetoCandidate, crowding_distance, non_dominated_fronts

__all__ = [
    "COMPOSITION_COMPLEXITY_CAP",
    "MAX_EMBEDDED_PER_GENOME",
    "MAX_MIGRANT_FRACTION",
    "MIGRANT_FRACTION_DEFAULT",
    "CompositionOperators",
    "CoevolutionEngine",
    "CoevolutionResult",
    "EmbeddedComponent",
    "FamilyFitness",
    "GeneticProgrammingOperators",
    "GenomeFamily",
    "MixedCandidate",
    "MixedGenome",
    "NeuroevolutionOperators",
    "OperatorDispatch",
    "run_coevolution_comparison",
]

#: Documented default migration pressure: 10% of each family's slots per generation.
MIGRANT_FRACTION_DEFAULT = 0.1
#: Migration stays a bounded minority channel: at most half of a family's slots.
MAX_MIGRANT_FRACTION = 0.5
#: A composition genome may carry at most this many foreign embedded payloads.
MAX_EMBEDDED_PER_GENOME = 1
#: Composition complexity cap: at most 32 components with up to 4 parameters each
#: (mirrors ``Composition``'s 32-component bound and the registry's parameter arity).
COMPOSITION_COMPLEXITY_CAP = 128.0

_PARETO_DIRECTIONS = ("max", "min")


class GenomeFamily(StrEnum):
    """Genome families sharing one mixed population; values match AlgorithmFamily."""

    GENETIC_PROGRAMMING = "genetic_programming"
    NEUROEVOLUTION = "neuroevolution"
    STRATEGY_COMPOSITION = "strategy_composition"

    @property
    def slug(self) -> str:
        """Short identifier used in candidate ids and evaluation counters."""
        if self is GenomeFamily.GENETIC_PROGRAMMING:
            return "gp"
        if self is GenomeFamily.NEUROEVOLUTION:
            return "neuro"
        return "composition"


ALL_FAMILIES: tuple[GenomeFamily, ...] = (
    GenomeFamily.GENETIC_PROGRAMMING,
    GenomeFamily.NEUROEVOLUTION,
    GenomeFamily.STRATEGY_COMPOSITION,
)


@dataclass(frozen=True, slots=True)
class EmbeddedComponent:
    """One foreign-family payload carried inside a composition genome (F-025).

    This is the controlled exchange channel: a GP expression or a neuro topology
    becomes a declarative, role-typed component of a composition genome. The payload
    is copied whole - no subtree surgery crosses the family boundary.
    """

    source_family: GenomeFamily
    role: str
    gp_expression: Node | None = None
    neuro_topology: TopologyNetwork | None = None
    neuro_parameters: tuple[float, ...] = ()

    def __post_init__(self) -> None:
        if self.role not in ALLOWED_ROLES:
            raise ValueError(f"embedded component role is not a composition role: {self.role}")
        if self.source_family is GenomeFamily.GENETIC_PROGRAMMING:
            if not isinstance(self.gp_expression, Node):
                raise ValueError("embedded GP component requires a genetic_programming.Node payload")
            if self.gp_expression.infer_type() != "numeric":
                raise ValueError("embedded GP component must have a numeric root expression")
            if self.neuro_topology is not None or self.neuro_parameters:
                raise ValueError("embedded GP component must not carry neuro payload")
            return
        if self.source_family is GenomeFamily.NEUROEVOLUTION:
            if not isinstance(self.neuro_topology, TopologyNetwork):
                raise ValueError(
                    "embedded neuro component requires a neuroevolution.TopologyNetwork payload"
                )
            if len(self.neuro_parameters) != self.neuro_topology.parameter_count:
                raise ValueError("embedded neuro component parameters must match the topology")
            if self.gp_expression is not None:
                raise ValueError("embedded neuro component must not carry a GP payload")
            return
        raise ValueError(
            f"only genetic_programming and neuroevolution payloads can migrate: {self.source_family}"
        )


@dataclass(frozen=True, slots=True)
class MixedGenome:
    """One immutable genome record valid in the mixed population.

    ``payload`` is the family's own immutable genome type; ``parameters`` carries the
    neuro weight vector (empty for GP and composition); ``embedded`` is reserved for
    composition carriers that absorbed a migrated foreign component.
    """

    family: GenomeFamily
    payload: Node | TopologyNetwork | Composition
    parameters: tuple[float, ...] = ()
    embedded: EmbeddedComponent | None = None

    def __post_init__(self) -> None:
        if self.family is GenomeFamily.GENETIC_PROGRAMMING:
            if not isinstance(self.payload, Node):
                raise ValueError("genetic_programming genomes require a Node payload")
            if self.payload.infer_type() != "numeric":
                raise ValueError("genetic_programming genomes must have a numeric root expression")
            if self.parameters or self.embedded is not None:
                raise ValueError("genetic_programming genomes carry neither parameters nor embedded payloads")
            return
        if self.family is GenomeFamily.NEUROEVOLUTION:
            if not isinstance(self.payload, TopologyNetwork):
                raise ValueError("neuroevolution genomes require a TopologyNetwork payload")
            if self.embedded is not None:
                raise ValueError("neuroevolution genomes cannot carry embedded payloads")
            if len(self.parameters) != self.payload.parameter_count:
                raise ValueError("neuroevolution genomes require one parameter per topology weight")
            return
        if self.family is GenomeFamily.STRATEGY_COMPOSITION:
            if not isinstance(self.payload, Composition):
                raise ValueError("strategy_composition genomes require a Composition payload")
            if self.parameters:
                raise ValueError("strategy_composition genomes carry no parameters")
            if self.embedded is not None:
                # The embedded payload must respect the carrier's compatibility graph:
                # pairwise role exclusions and the singleton-role rule.
                for component in self.payload.components:
                    if not roles_compatible(self.embedded.role, component.role):
                        raise ValueError(
                            f"embedded {self.embedded.role} component is incompatible with "
                            f"carrier role {component.role}"
                        )
                if self.embedded.role in SINGLETON_ROLES and any(
                    component.role == self.embedded.role for component in self.payload.components
                ):
                    raise ValueError(
                        f"embedded {self.embedded.role} component duplicates a singleton carrier role"
                    )
            return
        raise ValueError(f"unknown genome family: {self.family}")


@dataclass(frozen=True, slots=True)
class MixedCandidate:
    """One evaluated member of the mixed population (common candidate interface)."""

    candidate_id: str
    genome: MixedGenome
    generation: int
    parent_candidate_ids: tuple[str, ...]
    operator: str
    fitness: float
    complexity_ratio: float
    population_mode: str


@dataclass(frozen=True, slots=True)
class FamilyFitness:
    """The common fitness contract: one caller-supplied callable per family.

    All three callables must return finite scores on ONE common scale - selection is
    family-agnostic, so a family whose callable returns a different scale would
    dominate the ranking spuriously. Callables receive immutable genomes only and
    must implement the caller's train-only evaluation protocol.
    """

    genetic_programming: Callable[[Node], float]
    neuroevolution: Callable[[TopologyNetwork, tuple[float, ...]], float]
    strategy_composition: Callable[[Composition, EmbeddedComponent | None], float]


# ---------------------------------------------------------------------------
# Family-specific operators (public implementations over public genome surfaces)
# ---------------------------------------------------------------------------


def _gp_paths(root: Node, prefix: tuple[int, ...] = ()) -> list[tuple[int, ...]]:
    # Local reimplementation of the GP module's private path utility: root + descendants.
    output = [prefix]
    for index, child in enumerate(root.children):
        output.extend(_gp_paths(child, prefix + (index,)))
    return output


def _gp_subtree(root: Node, path: tuple[int, ...]) -> Node:
    node = root
    for index in path:
        node = node.children[index]
    return node


def _gp_slot_type(root: Node, path: tuple[int, ...]) -> str:
    if not path:
        return root.infer_type()
    anchor = _gp_subtree(root, path[:-1])
    return anchor.children[path[-1]].infer_type()


def _gp_replace(root: Node, path: tuple[int, ...], replacement: Node) -> Node:
    if not path:
        return replacement
    children = list(root.children)
    children[path[0]] = _gp_replace(children[path[0]], path[1:], replacement)
    return Node(root.operation, tuple(children), root.feature_index, root.constant, root.lag)


def _gp_feature_indices(node: Node) -> frozenset[int]:
    indices: set[int] = set()
    if node.feature_index is not None:
        indices.add(node.feature_index)
    for child in node.children:
        indices.update(_gp_feature_indices(child))
    return frozenset(indices)


class GeneticProgrammingOperators:
    """Family-specific GP operators rebuilt over the public F-018 grammar surface.

    The GP module's own operator helpers are private, so this suite re-implements the
    documented bounded operators (same-typed subtree crossover/mutation, depth and
    node caps, bounded lag) using only public grammar constants and the frozen
    ``Node`` constructor. Generated trees obey exactly the same bounds contract.
    """

    def __init__(
        self,
        rng: np.random.Generator,
        *,
        feature_count: int,
        max_depth: int = 4,
        max_nodes: int = 31,
        max_lag: int = 4,
    ) -> None:
        if feature_count < 1 or max_depth < 1 or max_nodes < 3:
            raise ValueError("invalid GP operator bounds")
        self.rng = rng
        self.feature_count = feature_count
        self.max_depth = max_depth
        self.max_nodes = max_nodes
        self.max_lag = int(min(max(int(max_lag), 1), MAX_LAG))

    def within_bounds(self, tree: Node) -> bool:
        return tree.depth <= self.max_depth and tree.size <= self.max_nodes

    def _terminal(self) -> Node:
        if self.rng.random() < 0.8:
            return Node("feature", feature_index=int(self.rng.integers(self.feature_count)))
        return Node("constant", constant=float(self.rng.uniform(-2.0, 2.0)))

    def _lagged_terminal(self) -> Node:
        lag = int(self.rng.integers(1, self.max_lag + 1))
        return Node(STATE_OPERATION, (self._terminal(),), lag=lag)

    def _comparison(self, depth: int) -> Node:
        operation = COMPARISON_FOLDS[int(self.rng.integers(len(COMPARISON_FOLDS)))]
        return Node(operation, (self._random_numeric(depth), self._random_numeric(depth)))

    def _boolean_terminal(self, depth: int) -> Node:
        draw = self.rng.random()
        if draw < 0.6 and depth < self.max_depth:
            return self._comparison(depth + 1)
        if draw < 0.8:
            return Node("constant_true")
        return Node("constant_false")

    def _random_bool(self, depth: int) -> Node:
        if depth >= self.max_depth:
            return Node("constant_true") if self.rng.random() < 0.5 else Node("constant_false")
        if self.rng.random() < 0.3:
            return self._boolean_terminal(depth)
        draw = self.rng.random()
        if draw < 0.45:
            operation = BOOLEAN_BINARY[int(self.rng.integers(len(BOOLEAN_BINARY)))]
            return Node(operation, (self._random_bool(depth + 1), self._random_bool(depth + 1)))
        if draw < 0.6:
            return Node(BOOLEAN_UNARY[0], (self._random_bool(depth + 1),))
        return self._comparison(depth + 1)

    def _random_numeric(self, depth: int) -> Node:
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
            return Node(NUMERIC_TERNARY[0], (
                self._random_bool(depth + 1),
                self._random_numeric(depth + 1),
                self._random_numeric(depth + 1),
            ))
        operation = NUMERIC_BINARY[int(self.rng.integers(len(NUMERIC_BINARY)))]
        return Node(operation, (
            self._random_numeric(depth + 1),
            self._random_numeric(depth + 1),
        ))

    def new_tree(self) -> Node:
        # Bounded retry, then fall back to a guaranteed-valid terminal (GP contract).
        for _ in range(64):
            candidate = self._random_numeric(0)
            if self.within_bounds(candidate):
                return candidate
        return self._terminal()

    def random_genome(self) -> MixedGenome:
        return MixedGenome(GenomeFamily.GENETIC_PROGRAMMING, self.new_tree())

    def mutate_tree(self, tree: Node) -> Node:
        for _ in range(32):
            paths = _gp_paths(tree)
            path = paths[int(self.rng.integers(len(paths)))]
            target_type = _gp_slot_type(tree, path)
            replacement = (
                self._random_numeric(len(path))
                if target_type == "numeric"
                else self._random_bool(len(path))
            )
            mutant = _gp_replace(tree, path, replacement)
            if self.within_bounds(mutant):
                return mutant
        return tree

    def crossover_trees(self, left: Node, right: Node) -> Node:
        for _ in range(32):
            left_paths = _gp_paths(left)
            right_paths = _gp_paths(right)
            left_path = left_paths[int(self.rng.integers(len(left_paths)))]
            right_path = right_paths[int(self.rng.integers(len(right_paths)))]
            donor = _gp_subtree(right, right_path)
            if donor.infer_type() != _gp_slot_type(left, left_path):
                continue
            child = _gp_replace(left, left_path, donor)
            if self.within_bounds(child):
                return child
        return left

    def crossover(self, left: MixedGenome, right: MixedGenome) -> MixedGenome:
        return MixedGenome(
            GenomeFamily.GENETIC_PROGRAMMING,
            self.crossover_trees(left.payload, right.payload),
        )

    def mutate(self, genome: MixedGenome) -> MixedGenome:
        return MixedGenome(
            GenomeFamily.GENETIC_PROGRAMMING,
            self.mutate_tree(genome.payload),
        )


class NeuroevolutionOperators:
    """Family-specific neuro operators over the public F-019 topology surface.

    Topology changes use the public ``TopologyNetwork.sample_mutation`` /
    ``with_mutation`` replay pair (self-repairing: rejected mutations keep the
    parent topology). Weight vectors drift with clipped Gaussian noise. Crossover
    splices two parents' hidden-layer stacks; weight vectors are inherited when the
    spliced layout keeps the donor's parameter count, else re-initialised.
    """

    def __init__(
        self,
        rng: np.random.Generator,
        *,
        input_size: int,
        topology_mutation_rate: float = 0.5,
        noise_std: float = 0.1,
        weight_limit: float = 8.0,
    ) -> None:
        if input_size < 1 or not 0 <= topology_mutation_rate <= 1:
            raise ValueError("invalid neuro operator bounds")
        if noise_std <= 0 or weight_limit <= 0:
            raise ValueError("invalid neuro operator hyperparameters")
        self.rng = rng
        self.input_size = input_size
        self.topology_mutation_rate = topology_mutation_rate
        self.noise_std = noise_std
        self.weight_limit = weight_limit

    def random_genome(self) -> MixedGenome:
        network = TopologyNetwork(
            input_size=self.input_size, hidden_sizes=(16,), activations=("tanh",)
        )
        parameters = network.initial_parameters(self.rng)
        return MixedGenome(
            GenomeFamily.NEUROEVOLUTION, network, tuple(float(value) for value in parameters)
        )

    def crossover(self, left: MixedGenome, right: MixedGenome) -> MixedGenome:
        left_topology = left.payload
        right_topology = right.payload
        if left_topology.input_size != right_topology.input_size:
            raise ValueError("neuro crossover requires matching input sizes")
        # Splice hidden stacks at a shared boundary; both sides keep >= 1 layer.
        split = int(self.rng.integers(
            1, min(len(left_topology.hidden_sizes), len(right_topology.hidden_sizes)) + 1
        ))
        sizes = left_topology.hidden_sizes[:split] + right_topology.hidden_sizes[split:]
        activations = left_topology.activations[:split] + right_topology.activations[split:]
        # Only skips that remain adjacent within the spliced layout survive.
        skips = tuple(skip for skip in left_topology.skips if skip[0] < len(sizes))
        try:
            network = TopologyNetwork(
                input_size=left_topology.input_size,
                hidden_sizes=sizes,
                activations=activations,
                skips=skips,
                output_size=left_topology.output_size,
            )
        except ValueError:
            network = left_topology
        if len(left.parameters) == network.parameter_count:
            parameters = left.parameters
        elif len(right.parameters) == network.parameter_count:
            parameters = right.parameters
        else:
            parameters = tuple(
                float(value) for value in network.initial_parameters(self.rng)
            )
        return MixedGenome(GenomeFamily.NEUROEVOLUTION, network, parameters)

    def mutate(self, genome: MixedGenome) -> MixedGenome:
        network = genome.payload
        if self.rng.random() < self.topology_mutation_rate:
            entry = network.sample_mutation(self.rng)
            network = network.with_mutation(entry)
        if network is genome.payload:
            drifted = np.asarray(genome.parameters, dtype=np.float64) + self.rng.normal(
                0.0, self.noise_std, size=len(genome.parameters)
            )
            parameters = np.clip(drifted, -self.weight_limit, self.weight_limit)
        else:
            # The topology changed: the weight layout no longer matches the parent
            # vector, so the child starts from a deterministic fresh initialisation.
            parameters = network.initial_parameters(self.rng)
        return MixedGenome(
            GenomeFamily.NEUROEVOLUTION,
            network,
            tuple(float(value) for value in parameters),
        )


def _composition_dedupe(components: Sequence[Component]) -> tuple[Component, ...]:
    unique: list[Component] = []
    seen: set[tuple[str, str]] = set()
    for component in components:
        key = (component.component_id, component.role)
        if key not in seen:
            unique.append(component)
            seen.add(key)
    return tuple(unique)


class CompositionOperators:
    """Family-specific composition operators over the public F-020 surface.

    Mirrors the documented StrategyComposer semantics: compatibility-preserving union
    crossover under the component cap, and add/remove/replace mutations that keep the
    parent genome whenever the mutated genome would violate the compatibility graph.
    Embedded foreign payloads survive crossover from the left parent and may be
    DROPPED by mutation but are never CREATED here - embedding happens only through
    the engine's migration channel.
    """

    def __init__(
        self,
        rng: np.random.Generator,
        *,
        registry: Sequence[Component],
        max_components: int = 8,
    ) -> None:
        if not 2 <= max_components <= 32:
            raise ValueError("invalid composition operator bounds")
        if not any(component.role == "entry" for component in registry) or not any(
            component.role == "exit" for component in registry
        ):
            raise ValueError("registry must contain entry and exit components")
        # Every registry entry must be a valid Component (mirrors StrategyComposer).
        for component in registry:
            Component(component.component_id, component.role, component.parameters)
        self.rng = rng
        self.registry = tuple(registry)
        self.max_components = max_components

    def random_genome(self) -> MixedGenome:
        entries = [c for c in self.registry if c.role == "entry"]
        exits = [c for c in self.registry if c.role == "exit"]
        genome = Composition((
            entries[int(self.rng.integers(len(entries)))],
            exits[int(self.rng.integers(len(exits)))],
        ))
        return MixedGenome(GenomeFamily.STRATEGY_COMPOSITION, genome)

    def crossover(self, left: MixedGenome, right: MixedGenome) -> MixedGenome:
        left_genome = left.payload
        right_genome = right.payload
        entries = [c for c in left_genome.components if c.role == "entry"]
        exits = [c for c in left_genome.components if c.role == "exit"]
        merged: list[Component] = []
        for component in left_genome.components + right_genome.components:
            if component.role in {"entry", "exit"}:
                continue
            merged.append(component)
        self.rng.shuffle(merged)
        chosen = [entries[0], exits[0]]
        for component in merged:
            if len(chosen) >= self.max_components:
                break
            chosen.append(component)
        try:
            genome = Composition(_composition_dedupe(chosen))
        except ValueError:
            genome = left_genome
        # Crossover never creates embeddings; the left parent's payload travels whole.
        return MixedGenome(
            GenomeFamily.STRATEGY_COMPOSITION, genome, embedded=left.embedded
        )

    def mutate(self, genome: MixedGenome) -> MixedGenome:
        composition = genome.payload
        operation = int(self.rng.integers(4))
        if operation == 3:
            # Drop an embedded payload (removal only; creation is migration-only).
            if genome.embedded is not None:
                return MixedGenome(GenomeFamily.STRATEGY_COMPOSITION, composition)
            return genome
        components = list(composition.components)
        candidate = self.registry[int(self.rng.integers(len(self.registry)))]
        if operation == 0:
            if len(components) < self.max_components and candidate not in components:
                components.append(candidate)
        elif operation == 1:
            removable = [
                index for index, item in enumerate(components)
                if item.role not in {"entry", "exit"}
            ]
            if removable:
                components.pop(removable[int(self.rng.integers(len(removable)))])
        else:
            replaceable = [
                index for index, item in enumerate(components)
                if item.role == candidate.role
            ]
            if replaceable:
                components[replaceable[int(self.rng.integers(len(replaceable)))]] = candidate
        try:
            payload = Composition(_composition_dedupe(components))
        except ValueError:
            return genome
        return MixedGenome(
            GenomeFamily.STRATEGY_COMPOSITION, payload, embedded=genome.embedded
        )


class OperatorDispatch:
    """The family-aware operator table.

    Crossover and mutation are routed to the genome's OWN family suite. Crossover
    between different families is structurally impossible: it raises ValueError
    before any family operator runs, so a GP tree can never cross with a neuro net.
    """

    def __init__(
        self,
        *,
        genetic_programming: GeneticProgrammingOperators,
        neuroevolution: NeuroevolutionOperators,
        strategy_composition: CompositionOperators,
    ) -> None:
        self._suites = {
            GenomeFamily.GENETIC_PROGRAMMING: genetic_programming,
            GenomeFamily.NEUROEVOLUTION: neuroevolution,
            GenomeFamily.STRATEGY_COMPOSITION: strategy_composition,
        }

    @classmethod
    def default(
        cls,
        rng: np.random.Generator,
        *,
        feature_count: int,
        registry: Sequence[Component],
        gp_max_depth: int = 4,
        gp_max_nodes: int = 31,
        gp_max_lag: int = 4,
        neuro_topology_mutation_rate: float = 0.5,
        neuro_noise_std: float = 0.1,
        neuro_weight_limit: float = 8.0,
        composition_max_components: int = 8,
    ) -> "OperatorDispatch":
        return cls(
            genetic_programming=GeneticProgrammingOperators(
                rng,
                feature_count=feature_count,
                max_depth=gp_max_depth,
                max_nodes=gp_max_nodes,
                max_lag=gp_max_lag,
            ),
            neuroevolution=NeuroevolutionOperators(
                rng,
                input_size=feature_count,
                topology_mutation_rate=neuro_topology_mutation_rate,
                noise_std=neuro_noise_std,
                weight_limit=neuro_weight_limit,
            ),
            strategy_composition=CompositionOperators(
                rng,
                registry=registry,
                max_components=composition_max_components,
            ),
        )

    def crossover(self, left: MixedGenome, right: MixedGenome) -> MixedGenome:
        if left.family is not right.family:
            raise ValueError(
                "cross-family crossover is not permitted in the mixed population: "
                f"{left.family.value} vs {right.family.value}"
            )
        return self._suites[left.family].crossover(left, right)

    def mutate(self, genome: MixedGenome) -> MixedGenome:
        return self._suites[genome.family].mutate(genome)

    def random_genome(self, family: GenomeFamily) -> MixedGenome:
        return self._suites[family].random_genome()


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CoevolutionResult:
    """Full record of one mixed-population run."""

    population_mode: str
    slot_quota: int
    migrant_fraction: float
    seed: int
    population: tuple[MixedCandidate, ...]
    pareto_front: tuple[ParetoCandidate, ...]
    history: tuple[dict[str, float], ...]
    evaluations: int
    evaluations_by_family: dict[str, int]
    migrations: int
    failures: tuple[str, ...]
    candidate_archive: tuple[dict[str, object], ...]


class CoevolutionEngine:
    """Evolves GP, neuro and composition genomes in ONE bounded population.

    ``population_mode="mixed"`` ranks every candidate family-agnostically (Pareto
    front, then crowding distance) and runs the migration channel over contested
    slots. ``population_mode="independent"`` ranks each family only against itself
    and disables migration - the comparison baseline with identical layout and
    budget. Both modes keep exactly ``slots_per_family`` members per family at all
    times, so neither budget nor population share can be dominated by one family.
    """

    def __init__(
        self,
        *,
        fitness: FamilyFitness,
        registry: Sequence[Component],
        feature_count: int,
        slots_per_family: int,
        generations: int,
        seed: int,
        migrant_fraction: float = MIGRANT_FRACTION_DEFAULT,
        population_mode: str = "mixed",
        initial_genomes: Sequence[MixedGenome] | None = None,
        operator_dispatch: OperatorDispatch | None = None,
        gp_max_depth: int = 4,
        gp_max_nodes: int = 31,
        gp_max_lag: int = 4,
        gp_mutation_rate: float = 0.25,
        neuroevolution_mutation_rate: float = 0.25,
        neuro_topology_mutation_rate: float = 0.5,
        neuro_noise_std: float = 0.1,
        neuro_weight_limit: float = 8.0,
        composition_max_components: int = 8,
        composition_mutation_rate: float = 0.25,
    ) -> None:
        if slots_per_family < 2 or generations < 1:
            raise ValueError("slots_per_family must be >= 2 and generations >= 1")
        if feature_count < 1:
            raise ValueError("feature_count must be positive")
        if population_mode not in {"mixed", "independent"}:
            raise ValueError("population_mode must be 'mixed' or 'independent'")
        if not 0 <= migrant_fraction <= MAX_MIGRANT_FRACTION:
            raise ValueError(
                f"migrant_fraction must be in [0, {MAX_MIGRANT_FRACTION}] (documented bound)"
            )
        if not any(component.role == "entry" for component in registry) or not any(
            component.role == "exit" for component in registry
        ):
            raise ValueError("registry must contain entry and exit components")
        for component in registry:
            Component(component.component_id, component.role, component.parameters)
        self.fitness = fitness
        self.registry = tuple(registry)
        self.feature_count = feature_count
        self.slots_per_family = slots_per_family
        self.generations = generations
        self.seed = seed
        self.population_mode = population_mode
        # Independent families never migrate; the fraction is recorded for the record.
        self.migrant_fraction = 0.0 if population_mode == "independent" else migrant_fraction
        self.rng = np.random.default_rng(seed)
        self.dispatch = operator_dispatch or OperatorDispatch.default(
            self.rng,
            feature_count=feature_count,
            registry=registry,
            gp_max_depth=gp_max_depth,
            gp_max_nodes=gp_max_nodes,
            gp_max_lag=gp_max_lag,
            neuro_topology_mutation_rate=neuro_topology_mutation_rate,
            neuro_noise_std=neuro_noise_std,
            neuro_weight_limit=neuro_weight_limit,
            composition_max_components=composition_max_components,
        )
        self.gp_max_depth = gp_max_depth
        self.gp_max_nodes = gp_max_nodes
        self._mutation_rates = {
            GenomeFamily.GENETIC_PROGRAMMING: gp_mutation_rate,
            GenomeFamily.NEUROEVOLUTION: neuroevolution_mutation_rate,
            GenomeFamily.STRATEGY_COMPOSITION: composition_mutation_rate,
        }
        for rate in self._mutation_rates.values():
            if not 0 <= rate <= 1:
                raise ValueError("family mutation rates must be in [0, 1]")
        self._initial_genomes = self._validated_initial_genomes(initial_genomes)
        self._sequence = 0
        self.evaluations = 0
        self.migrations = 0
        self._evaluations_by_family = {family.slug: 0 for family in ALL_FAMILIES}
        self._failures: list[str] = []
        self._archive: list[dict[str, object]] = []

    # -- validation ---------------------------------------------------------

    def _validated_initial_genomes(
        self, initial_genomes: Sequence[MixedGenome] | None
    ) -> dict[GenomeFamily, list[MixedGenome]]:
        seeds: dict[GenomeFamily, list[MixedGenome]] = {family: [] for family in ALL_FAMILIES}
        for genome in initial_genomes or ():
            seeds[genome.family].append(genome)
            if genome.family is GenomeFamily.GENETIC_PROGRAMMING:
                tree = genome.payload
                if tree.depth > self.gp_max_depth or tree.size > self.gp_max_nodes:
                    raise ValueError("seeded GP genome exceeds the configured complexity bounds")
                if any(index >= self.feature_count for index in _gp_feature_indices(tree)):
                    raise ValueError("seeded GP genome references a feature outside feature_count")
            if genome.family is GenomeFamily.NEUROEVOLUTION:
                if genome.payload.input_size != self.feature_count:
                    raise ValueError("seeded neuro genome input_size must match feature_count")
        return seeds

    # -- evaluation ---------------------------------------------------------

    def _complexity_ratio(self, genome: MixedGenome) -> float:
        """Family-agnostic cost objective: complexity over the family's documented cap."""
        if genome.family is GenomeFamily.GENETIC_PROGRAMMING:
            return min(1.0, genome.payload.size / float(self.gp_max_nodes))
        if genome.family is GenomeFamily.NEUROEVOLUTION:
            return min(1.0, genome.payload.parameter_count / float(TOPOLOGY_MAX_PARAMETERS))
        return min(1.0, genome.payload.complexity / COMPOSITION_COMPLEXITY_CAP)

    def _new_candidate(
        self,
        genome: MixedGenome,
        *,
        generation: int,
        parent_candidate_ids: tuple[str, ...],
        operator: str,
    ) -> MixedCandidate:
        # Exactly ONE evaluation per candidate - the shared budget contract.
        self._sequence += 1
        candidate_id = f"coev-{genome.family.slug}-g{generation:04d}-{self._sequence:08d}"
        try:
            if genome.family is GenomeFamily.GENETIC_PROGRAMMING:
                value = float(self.fitness.genetic_programming(genome.payload))
            elif genome.family is GenomeFamily.NEUROEVOLUTION:
                value = float(
                    self.fitness.neuroevolution(genome.payload, genome.parameters)
                )
            else:
                value = float(
                    self.fitness.strategy_composition(genome.payload, genome.embedded)
                )
            if not np.isfinite(value):
                raise ValueError("fitness returned a non-finite score")
        except Exception as exc:  # noqa: BLE001 - candidate-level failures stay recorded.
            failure = (
                f"generation={generation},candidate={candidate_id}: {type(exc).__name__}: {exc}"
            )
            self._failures.append(failure)
            fitness_value = -np.inf
            status = "failed"
            failure_reason: object = failure
        else:
            fitness_value = value
            status = "succeeded"
            failure_reason = None
        self.evaluations += 1
        self._evaluations_by_family[genome.family.slug] += 1
        complexity_ratio = self._complexity_ratio(genome)
        lineage = {
            "operator": operator,
            "generation": generation,
            "parent_candidate_ids": list(parent_candidate_ids),
            "seed": self.seed,
            "population_mode": self.population_mode,
            "family": genome.family.value,
        }
        self._archive.append({
            "candidate_id": candidate_id,
            "generation": generation,
            "index": self._sequence,
            "family": genome.family.value,
            "population_mode": self.population_mode,
            "genome": genome,
            "fitness": fitness_value,
            "complexity_ratio": complexity_ratio,
            "status": status,
            "failure_reason": failure_reason,
            "lineage": lineage,
        })
        return MixedCandidate(
            candidate_id=candidate_id,
            genome=genome,
            generation=generation,
            parent_candidate_ids=parent_candidate_ids,
            operator=operator,
            fitness=fitness_value,
            complexity_ratio=complexity_ratio,
            population_mode=self.population_mode,
        )

    # -- selection ----------------------------------------------------------

    @staticmethod
    def _ranking(candidates: Sequence[MixedCandidate]) -> list[MixedCandidate]:
        """Family-agnostic ordering: Pareto fronts, then crowding distance.

        Candidates with failed evaluations never enter the Pareto computation; they
        are appended after every valid candidate (id-ordered) so quotas can always
        be filled.
        """
        valid = [c for c in candidates if np.isfinite(c.fitness)]
        valid_ids = {c.candidate_id for c in valid}
        invalid = sorted(
            (c for c in candidates if c.candidate_id not in valid_ids),
            key=lambda c: c.candidate_id,
        )
        if not valid:
            return list(invalid)
        pareto = [
            ParetoCandidate(c.candidate_id, (float(c.fitness), float(c.complexity_ratio)))
            for c in valid
        ]
        ordered: list[MixedCandidate] = []
        for front in non_dominated_fronts(pareto, _PARETO_DIRECTIONS):
            distances = crowding_distance(pareto, _PARETO_DIRECTIONS, front)
            for index in sorted(front, key=lambda i: (-distances[i], pareto[i].candidate_id)):
                ordered.append(valid[index])
        return ordered + list(invalid)

    def _survivors(self, pool: Sequence[MixedCandidate]) -> tuple[list[MixedCandidate], int]:
        # Mixed mode ranks all families together (family-agnostic selection);
        # independent mode ranks each family against itself only.
        if self.population_mode == "mixed":
            ranked = self._ranking(pool)
        else:
            ranked = []
            for family in ALL_FAMILIES:
                ranked.extend(self._ranking([c for c in pool if c.genome.family is family]))
        population: list[MixedCandidate] = []
        for family in ALL_FAMILIES:
            members = [c for c in ranked if c.genome.family is family]
            population.extend(members[: self.slots_per_family])
        valid = [c for c in population if np.isfinite(c.fitness)]
        if valid:
            pareto = [
                ParetoCandidate(c.candidate_id, (float(c.fitness), float(c.complexity_ratio)))
                for c in valid
            ]
            front_size = len(non_dominated_fronts(pareto, _PARETO_DIRECTIONS)[0])
        else:
            front_size = 0
        return population, front_size

    def _tournament(self, members: Sequence[MixedCandidate]) -> MixedCandidate:
        # Fitness-based selection inside the mixed population; family never gates
        # tournament preference, only the operator suite does.
        indices = self.rng.integers(0, len(members), size=3)
        winner = max(
            (members[int(index)] for index in indices),
            key=lambda c: (float(c.fitness), c.candidate_id),
        )
        return winner

    # -- breeding -----------------------------------------------------------

    def _breed_genome(
        self, parents: Sequence[MixedCandidate], family: GenomeFamily
    ) -> tuple[MixedGenome, tuple[str, ...], str]:
        members = [c for c in parents if c.genome.family is family]
        left = self._tournament(members)
        right = self._tournament(members)
        genome = self.dispatch.crossover(left.genome, right.genome)
        operator = "family_crossover"
        if self.rng.random() < self._mutation_rates[family]:
            genome = self.dispatch.mutate(genome)
            operator = "family_crossover_then_mutation"
        return genome, (left.candidate_id, right.candidate_id), operator

    def _contested_slots(self) -> int:
        # Documented migration policy: floor(fraction * quota) contested slots per
        # family per generation; zero in independent mode.
        return int(np.floor(self.migrant_fraction * self.slots_per_family))

    def _best_of_family(
        self, parents: Sequence[MixedCandidate], family: GenomeFamily
    ) -> MixedCandidate | None:
        members = [
            c for c in parents
            if c.genome.family is family and np.isfinite(c.fitness)
        ]
        if not members:
            return None
        return max(members, key=lambda c: (float(c.fitness), c.candidate_id))

    def _embeddable_roles(self, carrier: Composition) -> list[str]:
        # Deterministic ordering: sorted roles compatible with every carrier role,
        # respecting the singleton rule against the declarative components.
        roles = []
        for role in sorted(ALLOWED_ROLES):
            if not all(roles_compatible(role, component.role) for component in carrier.components):
                continue
            if role in SINGLETON_ROLES and any(
                component.role == role for component in carrier.components
            ):
                continue
            roles.append(role)
        return roles

    def _make_embedded(
        self, source_family: GenomeFamily, donor: MixedCandidate, carrier: Composition
    ) -> EmbeddedComponent | None:
        roles = self._embeddable_roles(carrier)
        if not roles:
            return None
        role = roles[int(self.rng.integers(len(roles)))]
        if source_family is GenomeFamily.GENETIC_PROGRAMMING:
            return EmbeddedComponent(
                source_family, role, gp_expression=donor.genome.payload
            )
        return EmbeddedComponent(
            source_family,
            role,
            neuro_topology=donor.genome.payload,
            neuro_parameters=donor.genome.parameters,
        )

    def _migrant(
        self,
        parents: Sequence[MixedCandidate],
        donors: dict[GenomeFamily, MixedCandidate | None],
        generation: int,
    ) -> tuple[tuple[MixedGenome, tuple[str, ...], str], GenomeFamily | None]:
        genome, parent_ids, operator = self._breed_genome(
            parents, GenomeFamily.STRATEGY_COMPOSITION
        )
        available = [
            family for family in (GenomeFamily.GENETIC_PROGRAMMING, GenomeFamily.NEUROEVOLUTION)
            if donors[family] is not None
        ]
        if not available:
            return (genome, parent_ids, operator), None
        source_family = available[int(self.rng.integers(len(available)))]
        donor = donors[source_family]
        embedded = self._make_embedded(source_family, donor, genome.payload)
        if embedded is None:
            return (genome, parent_ids, operator), None
        migrant_genome = MixedGenome(
            GenomeFamily.STRATEGY_COMPOSITION, genome.payload, embedded=embedded
        )
        operator = f"composition_migration_from_{source_family.slug}"
        parent_ids = parent_ids + (donor.candidate_id,)
        return (migrant_genome, parent_ids, operator), source_family

    def _emigrant(
        self, parents: Sequence[MixedCandidate], family: GenomeFamily
    ) -> tuple[MixedGenome, tuple[str, ...], str] | None:
        carriers = [
            c for c in parents
            if c.genome.family is GenomeFamily.STRATEGY_COMPOSITION
            and c.genome.embedded is not None
            and c.genome.embedded.source_family is family
            and np.isfinite(c.fitness)
        ]
        if not carriers:
            return None
        carrier = max(carriers, key=lambda c: (float(c.fitness), c.candidate_id))
        embedded = carrier.genome.embedded
        if family is GenomeFamily.GENETIC_PROGRAMMING:
            genome = MixedGenome(GenomeFamily.GENETIC_PROGRAMMING, embedded.gp_expression)
        else:
            genome = MixedGenome(
                GenomeFamily.NEUROEVOLUTION,
                embedded.neuro_topology,
                embedded.neuro_parameters,
            )
        return genome, (carrier.candidate_id,), "emigration_from_composition"

    # -- generations --------------------------------------------------------

    def _initial_population(self) -> list[MixedCandidate]:
        population: list[MixedCandidate] = []
        for family in ALL_FAMILIES:
            seeds = self._initial_genomes[family] or [self.dispatch.random_genome(family)]
            for index in range(self.slots_per_family):
                genome = seeds[index % len(seeds)]
                population.append(
                    self._new_candidate(
                        genome,
                        generation=0,
                        parent_candidate_ids=(),
                        operator=(
                            "seeded_initialisation" if self._initial_genomes[family]
                            else "random_initialisation"
                        ),
                    )
                )
        return population

    def _evolve_generation(
        self, parents: Sequence[MixedCandidate], generation: int
    ) -> tuple[list[MixedCandidate], dict[str, float]]:
        contested = self._contested_slots()
        donors = {
            GenomeFamily.GENETIC_PROGRAMMING: self._best_of_family(
                parents, GenomeFamily.GENETIC_PROGRAMMING
            ),
            GenomeFamily.NEUROEVOLUTION: self._best_of_family(
                parents, GenomeFamily.NEUROEVOLUTION
            ),
        }
        offspring: list[MixedCandidate] = []
        migrations = 0
        for family in ALL_FAMILIES:
            base_count = self.slots_per_family - contested
            for _ in range(base_count):
                genome, parent_ids, operator = self._breed_genome(parents, family)
                offspring.append(
                    self._new_candidate(
                        genome,
                        generation=generation,
                        parent_candidate_ids=parent_ids,
                        operator=operator,
                    )
                )
            for _ in range(contested):
                if family is GenomeFamily.STRATEGY_COMPOSITION:
                    (genome, parent_ids, operator), source = self._migrant(parents, donors, generation)
                    if source is not None:
                        migrations += 1
                else:
                    moved = self._emigrant(parents, family)
                    if moved is not None:
                        genome, parent_ids, operator = moved
                        migrations += 1
                    else:
                        genome, parent_ids, operator = self._breed_genome(parents, family)
                offspring.append(
                    self._new_candidate(
                        genome,
                        generation=generation,
                        parent_candidate_ids=parent_ids,
                        operator=operator,
                    )
                )
        pool = list(parents) + offspring
        population, front_size = self._survivors(pool)
        stats: dict[str, float] = {
            "generation": float(generation),
            "evaluations_total": float(self.evaluations),
            "evaluations_genetic_programming": float(
                self._evaluations_by_family[GenomeFamily.GENETIC_PROGRAMMING.slug]
            ),
            "evaluations_neuroevolution": float(
                self._evaluations_by_family[GenomeFamily.NEUROEVOLUTION.slug]
            ),
            "evaluations_strategy_composition": float(
                self._evaluations_by_family[GenomeFamily.STRATEGY_COMPOSITION.slug]
            ),
            "population_genetic_programming": float(self.slots_per_family),
            "population_neuroevolution": float(self.slots_per_family),
            "population_strategy_composition": float(self.slots_per_family),
            "contested_slots": float(contested * len(ALL_FAMILIES)),
            "migrations": float(migrations),
            "pareto_front_size": float(front_size),
        }
        for family in ALL_FAMILIES:
            scores = [
                float(c.fitness) for c in population
                if c.genome.family is family and np.isfinite(c.fitness)
            ]
            stats[f"best_fitness_{family.slug}"] = max(scores) if scores else -np.inf
        self.migrations += migrations
        return population, stats

    def _pareto_front(
        self, population: Sequence[MixedCandidate]
    ) -> tuple[ParetoCandidate, ...]:
        valid = [c for c in population if np.isfinite(c.fitness)]
        if not valid:
            return ()
        pareto = [
            ParetoCandidate(c.candidate_id, (float(c.fitness), float(c.complexity_ratio)))
            for c in valid
        ]
        fronts = non_dominated_fronts(pareto, _PARETO_DIRECTIONS)
        return tuple(pareto[index] for index in fronts[0])

    def run(self) -> CoevolutionResult:
        """Evolve the mixed (or independent) population to the configured generation count."""
        population = self._initial_population()
        history: list[dict[str, float]] = []
        for generation in range(1, self.generations + 1):
            population, stats = self._evolve_generation(population, generation)
            history.append(stats)
        return CoevolutionResult(
            population_mode=self.population_mode,
            slot_quota=self.slots_per_family,
            migrant_fraction=self.migrant_fraction,
            seed=self.seed,
            population=tuple(population),
            pareto_front=self._pareto_front(population),
            history=tuple(history),
            evaluations=self.evaluations,
            evaluations_by_family=dict(self._evaluations_by_family),
            migrations=self.migrations,
            failures=tuple(self._failures),
            candidate_archive=tuple(self._archive),
        )


def _result_payload(result: CoevolutionResult) -> dict[str, object]:
    return {
        "population_mode": result.population_mode,
        "pareto_front": result.pareto_front,
        "population": result.population,
        "history": result.history,
        "evaluations": result.evaluations,
        "evaluations_by_family": result.evaluations_by_family,
        "migrations": result.migrations,
        "failures": result.failures,
        "candidate_archive": result.candidate_archive,
    }


def run_coevolution_comparison(
    *,
    fitness: FamilyFitness,
    registry: Sequence[Component],
    feature_count: int,
    slots_per_family: int,
    generations: int,
    seed: int,
    migrant_fraction: float = MIGRANT_FRACTION_DEFAULT,
    initial_genomes: Sequence[MixedGenome] | None = None,
    gp_max_depth: int = 4,
    gp_max_nodes: int = 31,
    gp_max_lag: int = 4,
    gp_mutation_rate: float = 0.25,
    neuroevolution_mutation_rate: float = 0.25,
    neuro_topology_mutation_rate: float = 0.5,
    neuro_noise_std: float = 0.1,
    neuro_weight_limit: float = 8.0,
    composition_max_components: int = 8,
    composition_mutation_rate: float = 0.25,
) -> dict[str, object]:
    """Run independent-family vs mixed-population evolution under IDENTICAL budget.

    Both modes share population layout (``slots_per_family`` per family), generation
    count, seed, fitness callables and operator configuration; only the selection
    scope (family-agnostic global ranking vs per-family ranking) and the migration
    channel differ. The function verifies equal total and per-family evaluation
    counts at runtime and reports each mode's Pareto front over its final
    population, so the experiment record can compare independent vs cooperative
    evolution like-for-like.
    """
    def build(mode: str) -> CoevolutionEngine:
        return CoevolutionEngine(
            fitness=fitness,
            registry=registry,
            feature_count=feature_count,
            slots_per_family=slots_per_family,
            generations=generations,
            seed=seed,
            migrant_fraction=migrant_fraction,
            population_mode=mode,
            initial_genomes=initial_genomes,
            gp_max_depth=gp_max_depth,
            gp_max_nodes=gp_max_nodes,
            gp_max_lag=gp_max_lag,
            gp_mutation_rate=gp_mutation_rate,
            neuroevolution_mutation_rate=neuroevolution_mutation_rate,
            neuro_topology_mutation_rate=neuro_topology_mutation_rate,
            neuro_noise_std=neuro_noise_std,
            neuro_weight_limit=neuro_weight_limit,
            composition_max_components=composition_max_components,
            composition_mutation_rate=composition_mutation_rate,
        )

    independent = build("independent").run()
    mixed = build("mixed").run()
    if independent.evaluations != mixed.evaluations:
        raise RuntimeError("co-evolution comparison ran under unequal total budgets")
    if independent.evaluations_by_family != mixed.evaluations_by_family:
        raise RuntimeError("co-evolution comparison ran under unequal per-family budgets")
    return {
        "budget": {
            "evaluations_per_mode": mixed.evaluations,
            "evaluations_by_family": dict(mixed.evaluations_by_family),
            "slots_per_family": slots_per_family,
            "generations": generations,
            "seed": seed,
            "migrant_fraction_mixed": mixed.migrant_fraction,
        },
        "independent": _result_payload(independent),
        "mixed": _result_payload(mixed),
    }
