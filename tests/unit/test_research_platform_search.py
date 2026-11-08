"""Focused tests for optimiser, evolutionary, Pareto, statistics and portfolio modules."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from research.platform.adapters import CryptoLocalAdapter
from research.platform.composition import Component, StrategyComposer
from research.platform.domain import DataResolution, Market
from research.platform.genetic_programming import GeneticProgrammer, Node
from research.platform.neuroevolution import DenseMLP, EvolutionStrategy
from research.platform.optimizers import (
    Parameter,
    differential_evolution,
    grid_search,
    parzen_heuristic_search,
    random_search,
)
from research.platform.pareto import ParetoCandidate, non_dominated_fronts, select_nsga2
from research.platform.portfolio import PortfolioConfig, PortfolioSimulator
from research.platform.statistics import benjamini_hochberg, moving_block_bootstrap, pbo_cscv


UTC = timezone.utc


def test_random_grid_and_parzen_search_are_seeded_and_budgeted() -> None:
    # A convex objective with a known optimum tests sampling and result recording.
    space = (Parameter("x", -2.0, 2.0), Parameter("n", 1, 5, kind="int"))
    objective = lambda config: -((float(config["x"]) - 0.25) ** 2) - (int(config["n"]) - 3) ** 2

    random_a = random_search(space, objective, budget=30, seed=17)
    random_b = random_search(space, objective, budget=30, seed=17)
    assert [item.parameters for item in random_a.candidates] == [item.parameters for item in random_b.candidates]
    assert len(random_a.candidates) == 30

    grid = grid_search(space, objective, points_per_numeric_dimension=3, max_evaluations=20)
    assert len(grid.candidates) == 9
    with pytest.raises(ValueError, match="above max_evaluations"):
        grid_search(space, objective, points_per_numeric_dimension=5, max_evaluations=5)

    parzen = parzen_heuristic_search(space, objective, budget=25, startup_trials=5, seed=4)
    assert len(parzen.candidates) <= 25
    assert parzen.best.score == max(item.score for item in parzen.candidates)


def test_differential_evolution_does_not_replay_objective() -> None:
    # The objective call count must equal initial population plus every generation trial.
    calls = 0

    def objective(config: dict[str, object]) -> float:
        nonlocal calls
        calls += 1
        return -((float(config["x"]) - 0.4) ** 2)

    result = differential_evolution(
        (Parameter("x", -1.0, 1.0),),
        objective,
        population_size=8,
        generations=4,
        seed=21,
    )
    assert calls == 8 * 5
    assert len(result.candidates) == calls
    assert result.best.score >= -0.2


def test_optimizer_records_failures_without_silent_candidate_loss() -> None:
    # Non-finite fitness is a recorded failure rather than a plausible score.
    result = random_search(
        (Parameter("x", 0.0, 1.0),),
        lambda config: float("nan"),
        budget=5,
        seed=1,
    )
    assert not result.candidates
    assert len(result.failures) == 5
    with pytest.raises(RuntimeError, match="no valid candidates"):
        _ = result.best


def test_genetic_programming_interpreter_and_bounded_evolution() -> None:
    # The safe expression tree computes 2 * feature[0] without evaluating Python code.
    features = np.column_stack((np.linspace(-1, 1, 32), np.ones(32)))
    expression = Node(
        "mul",
        (Node("feature", feature_index=0), Node("constant", constant=2.0)),
    )
    np.testing.assert_allclose(expression.evaluate(features), features[:, 0] * 2.0)

    gp = GeneticProgrammer(
        feature_count=features.shape[1],
        population_size=12,
        generations=3,
        max_depth=4,
        max_nodes=31,
        mutation_rate=0.3,
        seed=3,
    )
    result = gp.run(features, lambda output: -float(np.mean((output - features[:, 0]) ** 2)))
    assert result["best_expression"].depth <= 4
    assert result["best_expression"].size <= 31
    assert len(result["population"]) == 12


def test_genetic_programming_rejects_unknown_or_invalid_feature_nodes() -> None:
    # The AST grammar rejects unknown operations and invalid feature references.
    with pytest.raises(ValueError, match="unsupported"):
        Node("python_eval")
    with pytest.raises(ValueError, match="outside"):
        Node("feature", feature_index=9).evaluate(np.ones((4, 2)))


def test_neuroevolution_runs_bounded_dense_network_candidates() -> None:
    # A tiny deterministic regression target checks shape, finite output and tracing.
    rng = np.random.default_rng(4)
    features = rng.normal(size=(40, 3))
    network = DenseMLP(input_size=3, hidden_size=5, output_size=1)
    evolution = EvolutionStrategy(
        network,
        population_size=8,
        generations=4,
        seed=5,
        weight_limit=4.0,
    )
    result = evolution.run(
        features,
        lambda predictions: -float(np.mean((predictions[:, 0] - np.tanh(features[:, 0])) ** 2)),
    )
    assert result.best_parameters.shape == (network.parameter_count,)
    assert np.isfinite(result.best_fitness)
    assert result.evaluations == 8 * 4
    assert len(result.generations) == 4


def test_strategy_composition_requires_entry_exit_and_evolves_registry_components() -> None:
    # Only declarative component IDs from the supplied registry may enter a genome.
    registry = (
        Component("rsi_entry", "entry", (("threshold", 30.0),)),
        Component("ma_exit", "exit", (("period", 10.0),)),
        Component("volume_filter", "filter", (("minimum", 1.0),)),
        Component("risk_cap", "risk", (("max_weight", 0.1),)),
    )
    with pytest.raises(ValueError, match="entry"):
        from research.platform.composition import Composition
        Composition((registry[1],))

    composer = StrategyComposer(registry, population_size=8, generations=3, seed=9)
    result = composer.run(lambda genome: float(len(genome.components)))
    assert any(item.role == "entry" for item in result.best.components)
    assert any(item.role == "exit" for item in result.best.components)
    assert len(result.history) == 3


def test_pareto_fronts_and_nsga2_selection_keep_tradeoffs() -> None:
    # Candidate A is best for return; B has less drawdown; C is dominated by both.
    candidates = (
        ParetoCandidate("A", (-0.20, 0.25)),
        ParetoCandidate("B", (-0.15, 0.10)),
        ParetoCandidate("C", (-0.10, 0.30)),
        ParetoCandidate("D", (-0.05, 0.05)),
    )
    fronts = non_dominated_fronts(candidates, directions=("min", "min"))
    assert set(fronts[0]) == {0, 1, 3}
    selected = select_nsga2(candidates, ("min", "min"), size=2)
    assert len(selected) == 2
    assert {candidate.candidate_id for candidate in selected}.issubset({"A", "B", "D"})


def test_benjamini_hochberg_and_bootstrap_are_reproducible() -> None:
    # FDR correction and block bootstrap retain input ordering and fixed-seed reproducibility.
    result = benjamini_hochberg([0.001, 0.01, 0.2, 0.8], alpha=0.05)
    assert result["hypotheses"] == 4
    assert result["rejections"] == 2
    returns = np.asarray([0.01, -0.02, 0.015, 0.004, -0.01, 0.02] * 8)
    first = moving_block_bootstrap(returns, block_size=4, samples=300, seed=8)
    second = moving_block_bootstrap(returns, block_size=4, samples=300, seed=8)
    assert first == second
    assert first["ci_low"] <= first["ci_high"]


def test_pbo_cscv_returns_valid_probability_and_split_count() -> None:
    # Synthetic candidate returns exercise the full CSCV split family.
    rng = np.random.default_rng(11)
    returns = rng.normal(0.0005, 0.01, size=(6, 160))
    result = pbo_cscv(returns, blocks=8)
    assert 0.0 <= result["pbo"] <= 1.0
    assert result["splits"] == 70
    assert result["strategies"] == 6


def test_portfolio_simulator_executes_next_open_with_costs_and_separate_capital() -> None:
    # A decision made on day one executes at the following day's open, not its close.
    dates = pd.date_range("2025-01-01", periods=4, freq="D", tz="UTC")
    bars = {
        "AAA": pd.DataFrame(
            {
                "open": [100.0, 110.0, 112.0, 115.0],
                "high": [101.0, 111.0, 113.0, 116.0],
                "low": [99.0, 109.0, 111.0, 114.0],
                "close": [100.0, 111.0, 113.0, 115.0],
                "volume": [100000.0] * 4,
            },
            index=dates,
        )
    }
    targets = pd.DataFrame({"AAA": [0.5, 0.5, 0.5, 0.0]}, index=dates)
    simulator = PortfolioSimulator(PortfolioConfig(
        market=Market.NSE,
        fee_bps=Decimal("10"),
        slippage_bps=Decimal("5"),
        impact_coefficient_bps=Decimal("2"),
        max_participation=Decimal("0.5"),
        max_gross_exposure=Decimal("0.8"),
        assumed_timezone="UTC",
        cost_model_id="nse-test-costs",
    ))
    result = simulator.run(bars, targets)
    assert result.initial_capital_inr == Decimal("2100000.00")
    assert result.market is Market.NSE
    assert len(result.fills) >= 1
    assert result.fills[0].fill.timestamp == dates[1].to_pydatetime()
    assert result.fills[0].fill.price_inr > result.fills[0].reference_price
    assert result.fees_paid_inr > 0
    assert result.equity_curve.index.equals(dates)
    assert result.final_positions.get("AAA", Decimal("0")) > 0


def test_portfolio_simulator_rejects_cross_market_or_bad_target_weights() -> None:
    # The simulator is permanently bound to one market and a long-only cash constraint.
    dates = pd.date_range("2025-01-01", periods=2, freq="D", tz="UTC")
    frame = pd.DataFrame(
        {
            "open": [100.0, 100.0], "high": [100.0, 100.0],
            "low": [100.0, 100.0], "close": [100.0, 100.0],
            "volume": [1000.0, 1000.0],
        },
        index=dates,
    )
    with pytest.raises(ValueError, match="exposure"):
        PortfolioSimulator(PortfolioConfig(
            Market.CRYPTO, Decimal("10"), assumed_timezone="UTC"
        )).run({"BTCUSDT": frame}, pd.DataFrame({"BTCUSDT": [1.2, 0.0]}, index=dates))


def test_crypto_local_adapter_records_licence_review_and_file_hash(tmp_path: Path) -> None:
    # A locally imported CSV is catalogued as licence-review-required, not open by default.
    exchange_root = tmp_path / "binance"
    exchange_root.mkdir()
    path = exchange_root / "BTCUSDT_1d.csv"
    path.write_text(
        "timestamp,open,high,low,close,volume\n"
        "1735689600000,100,102,99,101,1000\n"
        "1735776000000,101,103,100,102,1200\n",
        encoding="utf-8",
    )
    adapter = CryptoLocalAdapter(tmp_path, "binance")
    frame = adapter.load("BTCUSDT", DataResolution.ONE_DAY)
    manifest = adapter.manifest("BTCUSDT", DataResolution.ONE_DAY)
    assert len(frame) == 2
    assert manifest.market is Market.CRYPTO
    assert manifest.license_status.value == "review_required"
    assert manifest.extra_metadata["file_sha256"]



def test_batch_population_fitness_matches_manual_long_flat_accounting() -> None:
    # A tiny feature panel makes one-step decisions and per-transition costs explicit.
    from research.platform.compute import ComputeEngine

    features = np.asarray([[1.0], [-1.0], [2.0], [0.5]], dtype=np.float64)
    weights = np.asarray([[1.0], [-1.0]], dtype=np.float64)
    forward = np.asarray([0.10, -0.20, 0.05, 0.00], dtype=np.float64)
    result = ComputeEngine(backend="cpu").batch_long_flat_fitness(
        features, weights, forward, fee_bps=10.0, periods_per_year=4
    )
    # Candidate zero is long on rows 0, 2 and 3, paying entry, exit and re-entry.
    expected = (1.0 + 0.099) * (1.0 - 0.001) * (1.0 + 0.049) - 1.0
    assert result["total_return"].shape == (2,)
    assert result["total_return"][0] == pytest.approx(expected)
    assert result["trade_transitions"][0] == pytest.approx(3.0)
    assert result["mean_turnover"][0] == pytest.approx(0.75)
    assert np.isfinite(result["sharpe"]).all()


def test_batch_population_fitness_rejects_misaligned_forward_returns() -> None:
    # Future return labels must align exactly with the decision-time feature rows.
    from research.platform.compute import ComputeEngine

    engine = ComputeEngine(backend="cpu")
    with pytest.raises(ValueError, match="one value per feature row"):
        engine.batch_long_flat_fitness(
            np.ones((4, 2)), np.ones((3, 2)), np.ones(3)
        )
