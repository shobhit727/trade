"""Audit F-025 tests: mixed-genome co-evolution with controlled component exchange.

Covers: one bounded population holding all three genome families; family-specific
operator dispatch (no cross-family crossover); migration of components between
families ONLY through the composition genome under the documented bounded policy;
no budget domination (equal slots and equal per-family evaluation counts);
independent-vs-cooperative comparison under identical budget with two recorded
Pareto fronts.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from research.platform.coevolution import (
    COMPOSITION_COMPLEXITY_CAP,
    EmbeddedComponent,
    FamilyFitness,
    GenomeFamily,
    MixedGenome,
    OperatorDispatch,
    CoevolutionEngine,
    run_coevolution_comparison,
)
from research.platform.composition import Component, Composition
from research.platform.composition_policy import default_component_registry
from research.platform.features import PointInTimeFeatureEngine
from research.platform.genetic_programming import Node
from research.platform.model_evaluation import build_model_feature_panel
from research.platform.neuroevolution import TopologyNetwork
from research.platform.pareto import ParetoCandidate, non_dominated_fronts

UTC = timezone.utc


def _registry() -> tuple[Component, ...]:
    return default_component_registry((3,))


def _features() -> np.ndarray:
    # Deterministic synthetic feature matrix shared by all three families.
    rng = np.random.default_rng(11)
    return rng.normal(size=(64, 3))


def _target() -> np.ndarray:
    # Long when the first feature is above zero (causal reference rule).
    return np.where(_features()[:, 0] > 0.0, 1.0, -1.0)


def _fitness() -> FamilyFitness:
    features = _features()
    target = _target()
    return FamilyFitness(
        genetic_programming=lambda tree: -float(
            np.mean((tree.evaluate(features) - target) ** 2)
        ),
        neuroevolution=lambda network, parameters: -float(
            np.mean((network.predict(features, np.asarray(parameters))[:, 0] - target) ** 2)
        ),
        strategy_composition=lambda composition, embedded: float(
            len(composition.components)
        ),
    )


def _panel():
    index = pd.date_range("2025-01-01", periods=48, freq="D", tz=UTC)
    step = np.arange(len(index), dtype=np.float64)
    close = 100.0 + step * 0.2 + np.sin(step / 2.0)
    bars = {
        "AAA": pd.DataFrame(
            {
                "open": close - 0.05,
                "high": close + 0.5,
                "low": close - 0.5,
                "close": close,
                "volume": np.full(len(index), 10000.0),
            },
            index=index,
        )
    }
    return build_model_feature_panel(
        bars,
        PointInTimeFeatureEngine(windows=(3,)),
        ResearchTrack.NSE_INDIVIDUAL,
        start=datetime(2025, 1, 10, tzinfo=UTC),
        end=datetime(2025, 2, 5, tzinfo=UTC),
    )


def _engine(
    *,
    population_mode: str = "mixed",
    slots: int = 4,
    generations: int = 2,
    seed: int = 7,
    initial_genomes: list[MixedGenome] | None = None,
    migrant_fraction: float = 0.5,
) -> CoevolutionEngine:
    return CoevolutionEngine(
        fitness=_fitness(),
        registry=_registry(),
        feature_count=3,
        slots_per_family=slots,
        generations=generations,
        seed=seed,
        migrant_fraction=migrant_fraction,
        population_mode=population_mode,
        initial_genomes=initial_genomes,
    )


def _gp_genome(feature_index: int = 0) -> MixedGenome:
    # Deterministic small tree: feature[0] + 0.5 (numeric root, within default bounds).
    tree = Node(
        "add",
        (Node("feature", feature_index=feature_index), Node("constant", constant=0.5)),
    )
    return MixedGenome(GenomeFamily.GENETIC_PROGRAMMING, tree)


def _neuro_genome() -> MixedGenome:
    network = TopologyNetwork(input_size=3, hidden_sizes=(8,), activations=("tanh",))
    parameters = network.initial_parameters(np.random.default_rng(5))
    return MixedGenome(
        GenomeFamily.NEUROEVOLUTION, network, tuple(float(v) for v in parameters)
    )


def _composition_genome() -> MixedGenome:
    registry = _registry()
    entry = next(c for c in registry if c.role == "entry")
    exit_ = next(c for c in registry if c.role == "exit")
    return MixedGenome(
        GenomeFamily.STRATEGY_COMPOSITION, Composition((entry, exit_))
    )


# ---------------------------------------------------------------------------
# Genome record validation
# ---------------------------------------------------------------------------


def test_mixed_genome_rejects_family_payload_mismatches() -> None:
    with pytest.raises(ValueError, match="Node payload"):
        MixedGenome(GenomeFamily.GENETIC_PROGRAMMING, _neuro_genome().payload)
    with pytest.raises(ValueError, match="TopologyNetwork payload"):
        MixedGenome(GenomeFamily.NEUROEVOLUTION, _gp_genome().payload)
    with pytest.raises(ValueError, match="Composition payload"):
        MixedGenome(GenomeFamily.STRATEGY_COMPOSITION, "not-a-genome")
    boolean_root = Node("gt", (Node("feature", feature_index=0), Node("constant", constant=0.0)))
    with pytest.raises(ValueError, match="numeric root"):
        MixedGenome(GenomeFamily.GENETIC_PROGRAMMING, boolean_root)
    network = TopologyNetwork(input_size=3, hidden_sizes=(8,), activations=("tanh",))
    with pytest.raises(ValueError, match="one parameter per topology weight"):
        MixedGenome(GenomeFamily.NEUROEVOLUTION, network, (0.0,))


def test_embedded_component_validates_source_family_and_payload() -> None:
    with pytest.raises(ValueError, match="only genetic_programming and neuroevolution"):
        EmbeddedComponent(
            GenomeFamily.STRATEGY_COMPOSITION,
            "filter",
            gp_expression=_gp_genome().payload,
        )
    with pytest.raises(ValueError, match="Node payload"):
        EmbeddedComponent(GenomeFamily.GENETIC_PROGRAMMING, "filter")
    with pytest.raises(ValueError, match="TopologyNetwork payload"):
        EmbeddedComponent(GenomeFamily.NEUROEVOLUTION, "filter")
    network = TopologyNetwork(input_size=3, hidden_sizes=(8,), activations=("tanh",))
    with pytest.raises(ValueError, match="parameters must match"):
        EmbeddedComponent(
            GenomeFamily.NEUROEVOLUTION, "filter", neuro_topology=network, neuro_parameters=(0.0,)
        )
    with pytest.raises(ValueError, match="not a composition role"):
        EmbeddedComponent(
            GenomeFamily.GENETIC_PROGRAMMING,
            "portfolio",
            gp_expression=_gp_genome().payload,
        )


# ---------------------------------------------------------------------------
# Family-aware operator dispatch
# ---------------------------------------------------------------------------


def test_operator_dispatch_never_crosses_families() -> None:
    # Crossover between different families is structurally impossible: dispatch
    # raises before any family operator runs.
    dispatch = OperatorDispatch.default(
        np.random.default_rng(3), feature_count=3, registry=_registry()
    )
    with pytest.raises(ValueError, match="cross-family crossover"):
        dispatch.crossover(_gp_genome(), _neuro_genome())
    with pytest.raises(ValueError, match="cross-family crossover"):
        dispatch.crossover(_neuro_genome(), _composition_genome())
    # Same-family crossover routes to the family suite and stays within family.
    left = dispatch.crossover(_gp_genome(), _gp_genome(feature_index=1))
    assert left.family is GenomeFamily.GENETIC_PROGRAMMING
    assert isinstance(left.payload, Node)
    neuro_child = dispatch.crossover(_neuro_genome(), _neuro_genome())
    assert isinstance(neuro_child.payload, TopologyNetwork)
    composition_child = dispatch.crossover(_composition_genome(), _composition_genome())
    assert isinstance(composition_child.payload, Composition)


def test_family_mutations_stay_within_family_and_bounds() -> None:
    dispatch = OperatorDispatch.default(
        np.random.default_rng(9), feature_count=3, registry=_registry()
    )
    gp_child = dispatch.mutate(_gp_genome())
    assert gp_child.family is GenomeFamily.GENETIC_PROGRAMMING
    assert isinstance(gp_child.payload, Node)
    neuro_child = dispatch.mutate(_neuro_genome())
    assert isinstance(neuro_child.payload, TopologyNetwork)
    assert len(neuro_child.parameters) == neuro_child.payload.parameter_count
    composition_child = dispatch.mutate(_composition_genome())
    assert isinstance(composition_child.payload, Composition)
    # Bounded topology mutation keeps the parameter vector aligned with the topology.
    assert neuro_child.payload.parameter_count <= 120_000


# ---------------------------------------------------------------------------
# Mixed population holds and keeps all three families
# ---------------------------------------------------------------------------


def test_mixed_population_holds_all_three_families_after_evolution() -> None:
    engine = _engine(slots=4, generations=2)
    result = engine.run()
    families = {candidate.genome.family for candidate in result.population}
    assert families == set(GenomeFamily)
    assert len(result.population) == 12  # 3 families x 4 slots, strictly bounded
    counts = {family: 0 for family in GenomeFamily}
    for candidate in result.population:
        counts[candidate.genome.family] += 1
    assert counts == {family: 4 for family in GenomeFamily}
    # Every candidate carries the comparison mandate fields.
    assert all(
        candidate.population_mode == "mixed"
        and candidate.genome.family.value in {f.value for f in GenomeFamily}
        for candidate in result.population
    )
    assert len(result.history) == 2


def test_mixed_population_is_deterministic_for_same_seed() -> None:
    first = _engine(seed=13).run()
    second = _engine(seed=13).run()
    assert first.evaluations == second.evaluations
    assert [c.candidate_id for c in first.population] == [c.candidate_id for c in second.population]
    assert [
        (a.fitness, a.complexity_ratio) for a in first.population
    ] == [(b.fitness, b.complexity_ratio) for b in second.population]
    assert [dict(h) for h in first.history] == [dict(h) for h in second.history]


def test_seeded_initial_population_survives_and_drives_evolution() -> None:
    seeds = [_gp_genome(0), _neuro_genome(), _composition_genome()]
    engine = _engine(seed=21, initial_genomes=seeds)
    result = engine.run()
    # One seeded genome per family anchors the population; families remain present.
    families = {candidate.genome.family for candidate in result.population}
    assert families == set(GenomeFamily)
    assert result.evaluations_by_family == {
        "gp": 12, "neuro": 12, "composition": 12,
    }
    with pytest.raises(ValueError, match="outside feature_count"):
        CoevolutionEngine(
            fitness=_fitness(),
            registry=_registry(),
            feature_count=2,
            slots_per_family=4,
            generations=1,
            seed=1,
            initial_genomes=[_gp_genome(2)],
        )


# ---------------------------------------------------------------------------
# Migration through the composition genome only
# ---------------------------------------------------------------------------


def test_migration_embeds_foreign_component_inside_composition_only() -> None:
    engine = _engine(slots=4, generations=2)  # migrant_fraction 0.5 -> 2 contested slots
    result = engine.run()
    embedded_candidates = [
        record for record in result.candidate_archive
        if record["genome"].embedded is not None
    ]
    # The maximum-pressure run must exercise the migration channel.
    assert embedded_candidates, "migration channel never activated"
    created = [
        record for record in embedded_candidates
        if str(record["lineage"]["operator"]).startswith("composition_migration_from_")
    ]
    assert created, "no embedding was ever created by the migration channel"
    for record in embedded_candidates:
        genome = record["genome"]
        # Only composition genomes ever carry an embedded payload, whether created
        # by migration or inherited through family-internal crossover.
        assert genome.family is GenomeFamily.STRATEGY_COMPOSITION
        assert genome.embedded.source_family in {
            GenomeFamily.GENETIC_PROGRAMMING, GenomeFamily.NEUROEVOLUTION,
        }
        # The foreign payload type matches its declared source family.
        if genome.embedded.source_family is GenomeFamily.GENETIC_PROGRAMMING:
            assert isinstance(genome.embedded.gp_expression, Node)
        else:
            assert isinstance(genome.embedded.neuro_topology, TopologyNetwork)
    # Only migration-operator events CREATE embeddings; every one of them is a
    # composition genome embedding a foreign component.
    for record in created:
        assert record["genome"].family is GenomeFamily.STRATEGY_COMPOSITION
        assert record["genome"].embedded is not None
    # The run counter counts created embeddings plus emigration events.
    emigration = [
        record for record in result.candidate_archive
        if record["lineage"]["operator"] == "emigration_from_composition"
    ]
    assert len(created) + len(emigration) == result.migrations


def test_migration_is_bounded_by_documented_policy() -> None:
    # migrant_fraction 0.5, quota 4 -> exactly 2 contested slots per family per
    # generation; at most 2 embeddings can be created per generation.
    slots, generations = 4, 2
    engine = _engine(slots=slots, generations=generations)
    result = engine.run()
    contested_per_generation = int(np.floor(0.5 * slots))
    assert contested_per_generation == 2
    embedding_events = [
        record for record in result.candidate_archive
        if record["lineage"]["operator"].startswith("composition_migration_from_")
    ]
    # Created embeddings are bounded: at most one per contested composition slot.
    assert len(embedding_events) <= contested_per_generation * generations
    # GP and neuro genomes NEVER carry embedded payloads.
    for record in result.candidate_archive:
        genome = record["genome"]
        if genome.family is not GenomeFamily.STRATEGY_COMPOSITION:
            assert genome.embedded is None
    # The documented default is 10% of slots.
    from research.platform.coevolution import MIGRANT_FRACTION_DEFAULT

    assert MIGRANT_FRACTION_DEFAULT == 0.1
    default_engine = _engine(slots=10, migrant_fraction=0.1)
    # 10% of 10 slots = exactly 1 contested slot per family per generation.
    assert default_engine._contested_slots() == 1
    with pytest.raises(ValueError, match="migrant_fraction"):
        _engine(slots=4, migrant_fraction=0.6)


def test_migration_counter_aligns_with_recorded_operator_events() -> None:
    engine = _engine(slots=4, generations=2)
    result = engine.run()
    emigration_events = [
        record for record in result.candidate_archive
        if record["lineage"]["operator"] == "emigration_from_composition"
    ]
    embedding_events = [
        record for record in result.candidate_archive
        if record["lineage"]["operator"].startswith("composition_migration_from_")
    ]
    # Each recorded event maps 1:1 into the run counter (embedding + emigration).
    assert result.migrations == len(embedding_events) + len(emigration_events)


def test_composition_crossover_keeps_left_parent_embedding_never_creates() -> None:
    # Mutation drops embeddings (op 3) but never creates them; crossover keeps the
    # left parent's payload. Creation happens only in the engine migration channel.
    dispatch = OperatorDispatch.default(
        np.random.default_rng(31), feature_count=3, registry=_registry()
    )
    registry = _registry()
    entry = next(c for c in registry if c.role == "entry")
    exit_ = next(c for c in registry if c.role == "exit")
    carrier = MixedGenome(
        GenomeFamily.STRATEGY_COMPOSITION,
        Composition((entry, exit_)),
        embedded=EmbeddedComponent(
            GenomeFamily.GENETIC_PROGRAMMING, "filter", gp_expression=_gp_genome().payload
        ),
    )
    plain = _composition_genome()
    for _ in range(12):
        child = dispatch.crossover(carrier, plain)
        assert child.embedded is not None  # left-parent embedding preserved
        child = dispatch.crossover(plain, carrier)
        assert child.embedded is None  # right-parent payload is never adopted
    # Mutation without the drop branch keeps the payload; with it, embedding is lost.
    dropped = False
    for _ in range(64):
        child = dispatch.mutate(carrier)
        if child.embedded is None:
            dropped = True
            break
    assert dropped


def test_mixed_genome_embedding_respects_carrier_compatibility_graph() -> None:
    registry = _registry()
    entry = next(c for c in registry if c.role == "entry")
    exit_ = next(c for c in registry if c.role == "exit")
    regime = next(c for c in registry if c.role == "regime")
    carrier = Composition((entry, exit_, regime))
    with pytest.raises(ValueError, match="incompatible"):
        MixedGenome(
            GenomeFamily.STRATEGY_COMPOSITION,
            carrier,
            embedded=EmbeddedComponent(
                GenomeFamily.GENETIC_PROGRAMMING, "filter", gp_expression=_gp_genome().payload
            ),
        )
    # A filter embedding is accepted on a plain entry/exit carrier.
    MixedGenome(
        GenomeFamily.STRATEGY_COMPOSITION,
        Composition((entry, exit_)),
        embedded=EmbeddedComponent(
            GenomeFamily.GENETIC_PROGRAMMING, "filter", gp_expression=_gp_genome().payload
        ),
    )


# ---------------------------------------------------------------------------
# No budget domination: equal slots and equal evaluation counts
# ---------------------------------------------------------------------------


def test_no_family_dominates_budget_after_generations() -> None:
    slots, generations = 5, 3
    result = _engine(slots=slots, generations=generations).run()
    # Equal population slots per family at every measured point.
    counts = {family: 0 for family in GenomeFamily}
    for candidate in result.population:
        counts[candidate.genome.family] += 1
    assert counts == {family: slots for family in GenomeFamily}
    # Equal evaluation budget per family: every candidate costs exactly one
    # evaluation regardless of family, for every generation including generation 0.
    expected_per_family = slots * (generations + 1)
    assert result.evaluations_by_family == {
        "gp": expected_per_family,
        "neuro": expected_per_family,
        "composition": expected_per_family,
    }
    assert result.evaluations == 3 * expected_per_family
    # History rows restate the measured equality per generation: cumulative
    # per-family evaluations grow by exactly `slots` each generation, for every
    # family identically (the no-domination invariant over time).
    for row in result.history:
        generation = int(row["generation"])
        cumulative = slots * (generation + 1)
        assert row["population_genetic_programming"] == slots
        assert row["population_neuroevolution"] == slots
        assert row["population_strategy_composition"] == slots
        assert row["evaluations_genetic_programming"] == cumulative
        assert row["evaluations_neuroevolution"] == cumulative
        assert row["evaluations_strategy_composition"] == cumulative
        assert (
            row["evaluations_genetic_programming"]
            == row["evaluations_neuroevolution"]
            == row["evaluations_strategy_composition"]
        )
    # Migration copies payloads; it cannot shift the per-family budget shares.
    assert set(result.evaluations_by_family.values()) == {expected_per_family}


def test_engine_rejects_invalid_bounds() -> None:
    with pytest.raises(ValueError, match="slots_per_family"):
        _engine(slots=1)
    with pytest.raises(ValueError, match="population_mode"):
        _engine(population_mode="hybrid")
    with pytest.raises(ValueError, match="feature_count"):
        CoevolutionEngine(
            fitness=_fitness(),
            registry=_registry(),
            feature_count=0,
            slots_per_family=4,
            generations=1,
            seed=1,
        )
    with pytest.raises(ValueError, match="registry must contain entry"):
        CoevolutionEngine(
            fitness=_fitness(),
            registry=(Component("orphan", "filter", (("window", 3.0),)),),
            feature_count=3,
            slots_per_family=4,
            generations=1,
            seed=1,
        )


# ---------------------------------------------------------------------------
# Comparison mode: independent vs cooperative under identical budget
# ---------------------------------------------------------------------------


def test_comparison_produces_two_fronts_under_identical_budget() -> None:
    comparison = run_coevolution_comparison(
        fitness=_fitness(),
        registry=_registry(),
        feature_count=3,
        slots_per_family=4,
        generations=2,
        seed=17,
        migrant_fraction=0.5,
    )
    # slots x families x (generations + 1) evaluations per mode; per family it is
    # slots x (generations + 1) for every family identically.
    assert comparison["budget"]["evaluations_per_mode"] == 4 * 3 * 3
    assert comparison["budget"]["evaluations_by_family"] == {
        "gp": 12, "neuro": 12, "composition": 12,
    }
    independent = comparison["independent"]
    mixed = comparison["mixed"]
    # Both modes report a Pareto front over their final population.
    assert len(independent["pareto_front"]) >= 1
    assert len(mixed["pareto_front"]) >= 1
    assert all(isinstance(item, ParetoCandidate) for item in mixed["pareto_front"])
    assert all(isinstance(item, ParetoCandidate) for item in independent["pareto_front"])
    # Recorded fronts are genuinely non-dominated first fronts of their populations.
    for payload in (independent, mixed):
        fronts = non_dominated_fronts(payload["pareto_front"], ("max", "min"))
        assert len(fronts) == 1  # the reported front is fully non-dominated
    # Mode separation is recorded on every candidate and archive entry.
    assert all(
        c.population_mode == "independent" for c in independent["population"]
    )
    assert all(c.population_mode == "mixed" for c in mixed["population"])
    assert all(
        record["population_mode"] == "independent"
        for record in independent["candidate_archive"]
    )
    assert all(
        record["population_mode"] == "mixed" for record in mixed["candidate_archive"]
    )
    # Independent mode disables migration entirely.
    assert independent["migrations"] == 0
    assert mixed["migrations"] >= 0
    assert independent["history"][0]["migrations"] == 0.0
    assert independent["history"][0]["contested_slots"] == 0.0


def test_comparison_budget_equality_is_enforced_at_runtime() -> None:
    # The documented runtime guard: unequal budgets abort the comparison.
    from research.platform import coevolution as module

    original = module.CoevolutionEngine

    class UnequalEngine(original):
        def run(self):
            result = super().run()
            # Simulate one extra evaluation in the mixed mode.
            if self.population_mode == "mixed":
                object.__setattr__(result, "evaluations", result.evaluations + 1)
            return result

    module.CoevolutionEngine = UnequalEngine
    try:
        with pytest.raises(RuntimeError, match="unequal total budgets"):
            run_coevolution_comparison(
                fitness=_fitness(),
                registry=_registry(),
                feature_count=3,
                slots_per_family=4,
                generations=1,
                seed=5,
            )
    finally:
        module.CoevolutionEngine = original


def test_pareto_objectives_respect_documented_caps() -> None:
    # The family-agnostic ranking works over (fitness max, complexity min) for all
    # families; complexity ratios stay within their documented caps.
    result = _engine(slots=4, generations=2).run()
    for candidate in result.population:
        assert 0.0 <= candidate.complexity_ratio <= 1.0
        if candidate.genome.family is GenomeFamily.STRATEGY_COMPOSITION:
            assert candidate.complexity_ratio == min(
                1.0, candidate.genome.payload.complexity / COMPOSITION_COMPLEXITY_CAP
            )
        if candidate.genome.family is GenomeFamily.GENETIC_PROGRAMMING:
            assert candidate.genome.payload.size <= 31  # gp_max_nodes default
    # The reported front mixes objectives, not families: it is computed on
    # (fitness, complexity) and contains at least one candidate.
    front = result.pareto_front
    assert front
    assert all(len(item.objectives) == 2 for item in front)


def test_independent_mode_selection_never_mixes_families() -> None:
    # In independent mode each family is ranked only against itself: a weak
    # composition candidate cannot be crowded out by strong GP candidates.
    result = _engine(population_mode="independent", slots=4, generations=2).run()
    counts = {family: 0 for family in GenomeFamily}
    for candidate in result.population:
        counts[candidate.genome.family] += 1
    assert counts == {family: 4 for family in GenomeFamily}
    assert result.migrations == 0
    assert result.migrant_fraction == 0.0
