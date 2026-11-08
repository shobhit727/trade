"""Focused tests for optimiser, evolutionary, Pareto, statistics and portfolio modules."""

from __future__ import annotations

from datetime import timezone
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
    repeated = simulator.run(bars, targets)
    pd.testing.assert_series_equal(result.equity_curve, repeated.equity_curve)
    pd.testing.assert_series_equal(result.cash_curve, repeated.cash_curve)
    assert result.fees_paid_inr == repeated.fees_paid_inr
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
    with pytest.raises(ValueError, match="explicit s/ms/us/ns unit"):
        CryptoLocalAdapter(tmp_path, "binance").load("BTCUSDT", DataResolution.ONE_DAY)

    adapter = CryptoLocalAdapter(tmp_path, "binance", numeric_timestamp_unit="ms")
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



def test_market_specific_fee_calculators_keep_nse_and_crypto_costs_separate() -> None:
    # NSE delegates to the repository's itemised statutory model.
    from research.platform.costs import CryptoVenueFeeCalculator, NSEDeliveryFeeCalculator
    from research.platform.market import Side

    nse_fees = NSEDeliveryFeeCalculator()
    nse_charge = nse_fees.fee(Side.BUY, Decimal("10"), Decimal("100"))
    assert nse_charge > 0
    assert nse_fees.market is Market.NSE

    crypto_fees = CryptoVenueFeeCalculator(
        exchange="binance",
        maker_fee_bps=Decimal("1"),
        taker_fee_bps=Decimal("5"),
    )
    assert crypto_fees.fee(Side.BUY, Decimal("2"), Decimal("100")) == Decimal("0.10")
    assert crypto_fees.market is Market.CRYPTO

    # A venue fee calculator must not be attached to the other market's account.
    with pytest.raises(ValueError, match="different market"):
        PortfolioConfig(
            market=Market.CRYPTO,
            fee_bps=Decimal("0"),
            fee_calculator=nse_fees,
            cost_model_id=nse_fees.model_id,
        )



def test_fx_conversion_uses_only_prior_rates_and_normalises_timezones() -> None:
    # Bars in Asia/Kolkata align to UTC FX observations without using future data.
    from datetime import timedelta

    from research.platform.fx import FXRateSeries, convert_ohlcv_to_inr

    fx_index = pd.date_range("2025-01-01T00:00:00Z", periods=2, freq="1h")
    rates = pd.Series([85.0, 86.0], index=fx_index)
    fx = FXRateSeries(
        rates=rates,
        quote_currency="USDT",
        source_id="test-fx-feed-v1",
        max_staleness=timedelta(minutes=20),
    )
    bar_index = pd.DatetimeIndex([
        pd.Timestamp("2025-01-01T05:35:00", tz="Asia/Kolkata"),
        pd.Timestamp("2025-01-01T06:35:00", tz="Asia/Kolkata"),
    ])
    bars = pd.DataFrame(
        {
            "open": [100.0, 200.0],
            "high": [101.0, 201.0],
            "low": [99.0, 199.0],
            "close": [100.5, 200.5],
            "volume": [10.0, 20.0],
        },
        index=bar_index,
    )
    converted = convert_ohlcv_to_inr(bars, fx, source_quote_currency="USDT")
    assert converted["open"].tolist() == [8500.0, 17200.0]
    assert converted["volume"].tolist() == [10.0, 20.0]
    assert converted.attrs["fx_source_id"] == "test-fx-feed-v1"
    assert converted.attrs["fx_alignment"] == "backward_asof_no_future"


def test_fx_conversion_rejects_future_stale_or_mismatched_rates() -> None:
    # A price bar cannot consume future FX information or rates older than the declared cap.
    from datetime import timedelta

    from research.platform.fx import FXRateSeries, convert_ohlcv_to_inr

    bar_index = pd.date_range("2025-01-01T00:20:00Z", periods=1, freq="1min")
    bars = pd.DataFrame(
        {"open": [1.0], "high": [1.1], "low": [0.9], "close": [1.0], "volume": [1.0]},
        index=bar_index,
    )
    future_fx = FXRateSeries(
        pd.Series([80.0], index=pd.date_range("2025-01-01T00:30:00Z", periods=1)),
        "USDT", "future-rate", timedelta(minutes=15),
    )
    with pytest.raises(ValueError, match="no sufficiently recent prior FX"):
        convert_ohlcv_to_inr(bars, future_fx, source_quote_currency="USDT")

    stale_fx = FXRateSeries(
        pd.Series([80.0], index=pd.date_range("2025-01-01T00:00:00Z", periods=1)),
        "USDT", "stale-rate", timedelta(minutes=15),
    )
    with pytest.raises(ValueError, match="no sufficiently recent prior FX"):
        convert_ohlcv_to_inr(bars, stale_fx, source_quote_currency="USDT")
    with pytest.raises(ValueError, match="must match"):
        convert_ohlcv_to_inr(bars, stale_fx, source_quote_currency="USD")



def test_point_in_time_features_are_invariant_to_future_price_changes() -> None:
    # Mutating bars after a cutoff must not alter any features available before it.
    from research.platform.features import PointInTimeFeatureEngine

    dates = pd.date_range("2020-01-01", periods=100, freq="D", tz="UTC")
    close = 100.0 + np.arange(100, dtype=np.float64) * 0.2 + np.sin(np.arange(100))
    bars = pd.DataFrame(
        {
            "close": close,
            "high": close * 1.01,
            "low": close * 0.99,
            "volume": 1000.0 + np.arange(100, dtype=np.float64) * 3.0,
        },
        index=dates,
    )
    engine = PointInTimeFeatureEngine(windows=(5, 20))
    original = engine.build(bars)
    changed = bars.copy()
    changed.loc[dates[70]:, "close"] *= 1.5
    changed.loc[dates[70]:, "high"] *= 1.5
    changed.loc[dates[70]:, "low"] *= 1.5
    revised = engine.build(changed)
    pd.testing.assert_frame_equal(original.loc[:dates[69]], revised.loc[:dates[69]])
    assert original.attrs["feature_metadata"]["uses_future_data"] is False
    assert original.attrs["feature_metadata"]["max_lookback"] == 20


def test_forward_labels_have_explicit_end_timestamps_and_are_separate() -> None:
    # Forward labels are purposefully future-dependent and expose their label interval.
    from research.platform.features import PointInTimeFeatureEngine

    dates = pd.date_range("2024-01-01", periods=4, freq="D", tz="UTC")
    bars = pd.DataFrame({"close": [100.0, 101.0, 99.0, 102.0]}, index=dates)
    labels = PointInTimeFeatureEngine.build_next_bar_labels(bars)
    assert labels.loc[dates[0], "forward_return_1"] == pytest.approx(0.01)
    assert labels.loc[dates[0], "label_start_timestamp"] == dates[0]
    assert labels.loc[dates[0], "label_end_timestamp"] == dates[1]
    assert pd.isna(labels.loc[dates[-1], "forward_return_1"])
    assert labels.attrs["uses_future_data"] is True



def test_probabilistic_and_deflated_sharpe_adjust_for_trial_family() -> None:
    # The same observed Sharpe must clear a higher benchmark after many trials.
    from research.platform.statistics import deflated_sharpe_ratio, probabilistic_sharpe_ratio

    observed = 0.08
    psr = probabilistic_sharpe_ratio(observed, observations=500, kurtosis=3.0)
    dsr_small = deflated_sharpe_ratio(
        observed, [-0.02, 0.00, 0.03, 0.05], observations=500
    )
    dsr_large = deflated_sharpe_ratio(
        observed, [-0.02, 0.00, 0.03, 0.05] * 25, observations=500
    )
    assert 0.0 <= dsr_small["deflated_sharpe_probability"] <= 1.0
    assert dsr_small["deflated_sharpe_probability"] < psr
    assert dsr_large["expected_max_sharpe_per_period"] >= dsr_small["expected_max_sharpe_per_period"]
    assert dsr_large["trial_count"] == 100


def test_sharpe_diagnostics_reject_invalid_sampling_inputs() -> None:
    # Undefined periods or invalid moments cannot produce an optimistic confidence score.
    from research.platform.statistics import deflated_sharpe_ratio, probabilistic_sharpe_ratio

    with pytest.raises(ValueError, match="observations"):
        probabilistic_sharpe_ratio(0.2, observations=1)
    with pytest.raises(ValueError, match="finite"):
        deflated_sharpe_ratio(0.2, [0.1, float("nan")], observations=100)



def test_candidate_family_report_records_fdr_dsr_and_pbo_together() -> None:
    # The report binds every correction to the same explicitly named search family.
    from research.platform.statistics import candidate_family_report

    rng = np.random.default_rng(99)
    returns = rng.normal(0.0002, 0.01, size=(6, 160))
    report = candidate_family_report(
        [f"candidate-{index}" for index in range(6)],
        [0.001, 0.01, 0.02, 0.2, 0.4, 0.8],
        [0.02, 0.01, 0.03, -0.01, 0.0, 0.01],
        returns,
        observations=160,
        pbo_blocks=8,
    )
    assert report["candidate_family_size"] == 6
    assert len(report["candidate_rows"]) == 6
    assert report["fdr"]["hypotheses"] == 6
    assert report["deflated_sharpe"]["trial_count"] == 6
    assert report["pbo_cscv"]["strategies"] == 6
    assert report["classification"] == "diagnostic_only_requires_methodological_review"


def test_candidate_family_report_rejects_misaligned_search_records() -> None:
    # Missing candidate results must never shrink the multiple-testing family silently.
    from research.platform.statistics import candidate_family_report

    with pytest.raises(ValueError, match="equal length"):
        candidate_family_report(
            ["candidate-a", "candidate-b"],
            [0.01],
            [0.1, 0.2],
            np.ones((2, 80)),
            observations=80,
        )
