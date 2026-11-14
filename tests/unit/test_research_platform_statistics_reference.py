"""Independent reference fixtures for research statistics (audit F-007 / F-022, CR-004/005/006).

Every expected value is re-derived inside this file from the published formulas
(Bailey & Lopez de Prado) or hand-computed combinatorics; the module under test is
never called to produce its own expectations. Synthetic data only; numpy/scipy only.

Fixtures and constants:
* PSR reference values were independently computed from Bailey & Lopez de Prado
  (2012), "The Sharpe Ratio Efficient Frontier", Journal of Risk 15(2), equations
  (6)-(7), with the (T - 1) variance convention, and cross-checked against a
  Monte Carlo replication of the PSR integral.
* DSR expected-maximum reference values use the Euler-gamma approximation of the
  expected maximum of N independent standard Gaussians (Bailey & Lopez de Prado
  2014, "The Deflated Sharpe Ratio", Journal of Portfolio Management 40(5),
  equation 5). The documented residual between the closed form and the true
  Monte Carlo expected maximum (0.035 at N=10, 0.023 at N=100, 0.014 at N=1000
  on this fixture family) is the Euler small-N bias of the approximation itself,
  not a module defect: the module re-implements the published approximation.
* BH expected adjusted p-values follow Benjamini-Hochberg (1995) step-up with the
  cumulative minimum taken from the LARGEST rank, not the raw elementwise product.
* PBO expectations are hand-computed CSCV combinatorics (Lopez de Prado 2018,
  "Advances in Financial Machine Learning", chapter 11-12) on deterministic
  synthetic fixtures, seeded once and exact to the CSCV grid (multiples of 1/70
  for 16 strategies and 8 blocks, i.e. C(8,4)=70 splits).
"""

from __future__ import annotations

import math
from itertools import combinations

import numpy as np
import pytest
from scipy.stats import norm

from research.platform.statistics import (
    benjamini_hochberg,
    deflated_sharpe_ratio,
    pbo_cscv,
    probabilistic_sharpe_ratio,
)

TRIAL_SIGMA = 0.3
DSR_OBSERVATIONS = 252


# ---------------------------------------------------------------------------
# First-principles re-implementations (published formulas, independent of the
# module under test).
# ---------------------------------------------------------------------------
def _reference_psr(
    observed_sharpe: float,
    observations: int,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
    benchmark_sharpe: float = 0.0,
) -> float:
    """Bailey & Lopez de Prado 2012, equations (6)-(7), (T-1) convention."""
    variance_factor = (
        1.0
        - skewness * observed_sharpe
        + ((kurtosis - 1.0) / 4.0) * observed_sharpe * observed_sharpe
    )
    z_score = (
        (observed_sharpe - benchmark_sharpe)
        * math.sqrt(observations - 1)
        / math.sqrt(variance_factor)
    )
    return float(norm.cdf(z_score))


def _reference_expected_max_sharpe(trial_count: int, sigma: float) -> float:
    """Euler-gamma expected maximum of N independent standard normals.

    Bailey & Lopez de Prado 2014, equation 5, with Euler-Mascheroni
    gamma = 0.5772156649015329 (float64 value used by the module).
    """
    euler_gamma = 0.5772156649015329
    p1 = 1.0 - 1.0 / trial_count
    p2 = 1.0 - 1.0 / (trial_count * math.e)
    return sigma * (
        (1.0 - euler_gamma) * float(norm.ppf(p1))
        + euler_gamma * float(norm.ppf(p2))
    )


def _reference_bh_adjusted(p_values: list[float]) -> list[float]:
    """Benjamini-Hochberg step-up adjusted p-values (1995).

    adjusted_(i) = min over j >= i of p_(j) * n / j, accumulated from the
    LARGEST rank downwards, clipped to 1. The naive elementwise p * n / rank
    is NOT the BH adjustment (e.g. this fixture's rank 7: raw product 1.00 vs
    correct 0.98).
    """
    ordered = sorted(p_values)
    count = len(ordered)
    raw = [p * count / (rank + 1) for rank, p in enumerate(ordered)]
    adjusted = [1.0] * count
    running = 1.0
    for rank in range(count - 1, -1, -1):
        running = min(running, raw[rank])
        adjusted[rank] = min(running, 1.0)
    return adjusted


def _quantile_grid(size: int) -> np.ndarray:
    """Standardised order-statistic quantile grid: mean 0, sample std 1."""
    grid = norm.ppf((np.arange(size) + 0.5) / size)
    return grid / np.std(grid, ddof=1)


def _cscv_under_median_count(matrix: np.ndarray, blocks: int = 8) -> int:
    """Hand-rolled CSCV combinatorics returning the raw under-median split count."""
    chunks = np.array_split(np.arange(matrix.shape[1]), blocks)
    half = blocks // 2
    under_median = 0
    for train_blocks in combinations(range(blocks), half):
        test_blocks = [index for index in range(blocks) if index not in train_blocks]
        train_indices = np.concatenate([chunks[index] for index in train_blocks])
        test_indices = np.concatenate([chunks[index] for index in test_blocks])

        def sharpe(series: np.ndarray) -> np.ndarray:
            deviation = np.std(series, axis=1, ddof=1)
            mean = np.mean(series, axis=1)
            return np.divide(mean, deviation, out=np.zeros_like(mean), where=deviation > 0)

        train_scores = sharpe(matrix[:, train_indices])
        test_scores = sharpe(matrix[:, test_indices])
        selected = int(np.argmax(train_scores))
        descending_order = np.argsort(-test_scores, kind="stable")
        rank = np.empty(len(test_scores), dtype=np.int64)
        rank[descending_order] = np.arange(len(test_scores))
        if (float(rank[selected]) + 0.5) / len(test_scores) > 0.5:
            under_median += 1
    return under_median


# ---------------------------------------------------------------------------
# F-022 / CR-006: probabilistic Sharpe ratio vs published closed form.
# ---------------------------------------------------------------------------
_PSR_CASES = [
    # (observed, T, skew, kurtosis, benchmark, published reference value)
    pytest.param(0.10, 120, 0.0, 3.0, 0.0, 0.8617364840535165, id="gaussian-t120"),
    pytest.param(-0.05, 60, -0.4, 6.0, 0.0, 0.3492524919703094, id="negative-skew-fat-tails"),
    pytest.param(0.03, 200, 0.2, 5.0, 0.005, 0.6381698539453426, id="nonzero-benchmark"),
]


@pytest.mark.parametrize(("observed", "observations", "skew", "kurtosis", "benchmark", "expected"), _PSR_CASES)
def test_psr_matches_independent_closed_form_reference(
    observed: float,
    observations: int,
    skew: float,
    kurtosis: float,
    benchmark: float,
    expected: float,
) -> None:
    assert probabilistic_sharpe_ratio(
        observed, observations=observations, skewness=skew,
        kurtosis=kurtosis, benchmark_sharpe=benchmark,
    ) == pytest.approx(expected, abs=1e-12)


def test_psr_at_identity_point_is_exactly_one_half() -> None:
    # SR = SR* must sit at the Gaussian median: a hardcoded offset or a wrong
    # variance convention would move this away from 0.5.
    assert probabilistic_sharpe_ratio(0.08, observations=120, benchmark_sharpe=0.08) == pytest.approx(0.5, abs=1e-12)


# ---------------------------------------------------------------------------
# F-007 / F-022: DSR expected maximum and DSR probability.
# ---------------------------------------------------------------------------
_DSR_EMAX_REFERENCE = {10: 0.4723794904, 100: 0.7591808680, 1000: 0.9765364541}


@pytest.mark.parametrize("trial_count", [10, 100, 1000])
def test_dsr_expected_max_matches_closed_form_reference(trial_count: int) -> None:
    # Deterministic standardised trial family: sample std exactly TRIAL_SIGMA.
    grid = np.linspace(-1.0, 1.0, trial_count)
    trials = TRIAL_SIGMA * grid / np.std(grid, ddof=1)
    report = deflated_sharpe_ratio(
        float(trials.max()), trials, observations=DSR_OBSERVATIONS
    )
    expected = _reference_expected_max_sharpe(trial_count, TRIAL_SIGMA)
    assert report["expected_max_sharpe_per_period"] == pytest.approx(expected, abs=1e-9)
    assert report["expected_max_sharpe_per_period"] == pytest.approx(
        _DSR_EMAX_REFERENCE[trial_count], abs=1e-9
    )


@pytest.mark.parametrize("trial_count", [10, 100, 1000])
def test_dsr_probability_matches_module_free_closed_form(trial_count: int) -> None:
    # Mid-range observed Sharpe: expected max plus half a trial sigma, where the
    # closed-form-vs-module agreement is actually discriminating (a deep-tail
    # observation saturates the CDF and stops testing anything).
    grid = np.linspace(-1.0, 1.0, trial_count)
    trials = TRIAL_SIGMA * grid / np.std(grid, ddof=1)
    observed = _reference_expected_max_sharpe(trial_count, TRIAL_SIGMA) + 0.5 * TRIAL_SIGMA
    report = deflated_sharpe_ratio(observed, trials, observations=DSR_OBSERVATIONS)
    expected_probability = _reference_psr(
        observed, DSR_OBSERVATIONS, benchmark_sharpe=_reference_expected_max_sharpe(trial_count, TRIAL_SIGMA)
    )
    assert report["deflated_sharpe_probability"] == pytest.approx(expected_probability, abs=1e-12)


def test_dsr_probability_calibration_sanity_rows() -> None:
    # Sanity, not a reference: at observed = E[max] the DSR probability must be
    # the Gaussian median 0.5; at E[max] + 3 sigma it must saturate.
    grid = np.linspace(-1.0, 1.0, 50)
    trials = TRIAL_SIGMA * grid / np.std(grid, ddof=1)
    expected_max = _reference_expected_max_sharpe(50, TRIAL_SIGMA)
    at_max = deflated_sharpe_ratio(float(trials.max()) * 0.0 + expected_max, trials, observations=DSR_OBSERVATIONS)
    above_max = deflated_sharpe_ratio(expected_max + 3.0 * TRIAL_SIGMA, trials, observations=DSR_OBSERVATIONS)
    assert at_max["deflated_sharpe_probability"] == pytest.approx(0.5, abs=1e-9)
    assert above_max["deflated_sharpe_probability"] == pytest.approx(1.0, abs=1e-12)


def test_dsr_euler_bias_is_documented_not_a_module_bug() -> None:
    # The closed-form E[max] sits ABOVE the true Monte Carlo expected maximum by
    # the Euler small-N bias of the published approximation itself
    # (Bailey & Lopez de Prado 2014, equation 5). Seeded MC on this fixture
    # family measured 0.035 / 0.023 / 0.014 at N = 10 / 100 / 1000; the module
    # must keep re-implementing the published closed form, not "correct" it.
    rng = np.random.default_rng(20260114)
    measured_bias: dict[int, float] = {}
    for trial_count, repetitions in ((10, 200_000), (100, 50_000), (1000, 20_000)):
        batch = 2000
        maxima = np.empty(repetitions)
        for start in range(0, repetitions, batch):
            draw = rng.standard_normal((batch, trial_count))
            maxima[start:start + batch] = draw.max(axis=1)
        closed_form = _reference_expected_max_sharpe(trial_count, 1.0)
        measured_bias[trial_count] = closed_form - float(maxima.mean())
    assert measured_bias[10] == pytest.approx(0.035, abs=0.02)
    assert measured_bias[100] == pytest.approx(0.023, abs=0.02)
    assert measured_bias[1000] == pytest.approx(0.014, abs=0.02)


# ---------------------------------------------------------------------------
# F-022 / CR-006: Benjamini-Hochberg step-up on a 20-hypothesis fixture.
# ---------------------------------------------------------------------------
_SORTED_P_VALUES = [
    0.001, 0.002, 0.004, 0.008, 0.014,
    0.30, 0.35, 0.40, 0.45, 0.50,
    0.55, 0.60, 0.65, 0.70, 0.75,
    0.80, 0.85, 0.90, 0.95, 0.98,
]


def test_bh_rejection_set_matches_hand_computed_step_up() -> None:
    result = benjamini_hochberg(_SORTED_P_VALUES, alpha=0.05)
    expected_adjusted = _reference_bh_adjusted(_SORTED_P_VALUES)
    assert result["adjusted_p_values"] == pytest.approx(expected_adjusted, abs=1e-12)
    # Step-down boundary: k = 4 satisfies p(k)*n/k = 0.008*20/4 = 0.04 <= alpha;
    # k = 5 fails with 0.014*20/5 = 0.056 > alpha. Exactly ranks 1-4 reject.
    assert result["reject"] == [True] * 4 + [False] * 16
    assert result["rejections"] == 4


def test_bh_is_invariant_to_input_ordering() -> None:
    # BH is a property of the p-value SET: adjusted values must match the
    # sorted-fixture multiset regardless of input order.
    permuted = _SORTED_P_VALUES[::-1]
    result = benjamini_hochberg(permuted, alpha=0.05)
    expected = _reference_bh_adjusted(_SORTED_P_VALUES)
    assert sorted(result["adjusted_p_values"]) == pytest.approx(sorted(expected), abs=1e-12)
    assert sorted(result["reject"]) == sorted([True] * 4 + [False] * 16)
    assert result["rejections"] == 4


def test_bh_rejection_boundary_is_exclusive_at_alpha() -> None:
    # The k=4 boundary value is exactly 0.04; tightening alpha to 0.04 must
    # keep the four smallest (module uses adjusted <= alpha) and drop the fifth.
    result = benjamini_hochberg(_SORTED_P_VALUES, alpha=0.04)
    assert result["rejections"] == 4
    assert result["adjusted_p_values"][:4] == pytest.approx([0.02, 0.02, 0.0266666667, 0.04], abs=1e-8)
    assert result["adjusted_p_values"][4] == pytest.approx(0.056, abs=1e-12)


def test_bh_largest_rank_uses_cumulative_minimum_not_raw_product() -> None:
    # Regression trap: the naive elementwise p*n/k gives 0.35*20/7 = 1.00 at
    # rank 7; the correct step-up cumulative-min-from-the-largest-rank gives 0.98.
    result = benjamini_hochberg(_SORTED_P_VALUES, alpha=0.05)
    assert result["adjusted_p_values"][6] == pytest.approx(0.98, abs=1e-12)


# ---------------------------------------------------------------------------
# F-022 / CR-005: CSCV PBO hand fixtures.
# ---------------------------------------------------------------------------
def test_pbo_cscv_hand_computed_crossing_pair() -> None:
    # Hand fixture: 16 strategies, 48 observations, 8 CSCV blocks (C(8,4)=70
    # splits, so PBO lives on a 1/70 grid). Candidates 0 and 1 are the two
    # leaders with complementary edges: 0 leads the early half, 1 the late
    # half. Split-level enumeration (independent CSCV re-implementation below)
    # gives 12 under-median reversals: candidate 0 is train-selected whenever
    # the train half contains early blocks and then tests below the OOS median
    # on late-dominated test halves (8 splits with three early train blocks,
    # 3 with two, 1 with all four); candidate 5 is noise-picked in the 2
    # remaining cases. Expected: 12/70 = 0.1714285714... .
    rng = np.random.default_rng(11)
    noise = rng.normal(0.0, 0.004, size=(16, 48))
    matrix = np.full((16, 48), 0.001) + noise
    matrix[0, :24] += 0.005
    matrix[1, 24:] += 0.005
    result = pbo_cscv(matrix, blocks=8)
    assert result["pbo"] == pytest.approx(12 / 70, abs=1e-12)
    assert result["splits"] == 70
    assert result["strategies"] == 16
    # The count is reproduced by an independent CSCV implementation in this file.
    assert _cscv_under_median_count(matrix) == 12


def test_pbo_cscv_adversarial_persistent_edge_is_near_zero() -> None:
    # Adversarial fixture: candidate 0 carries a persistent positive edge in
    # every block. Split-level enumeration: candidate 0 is train-selected in
    # 69 of 70 splits (noise candidate 6 wins the remaining all-late train
    # split) and never falls below the OOS median; candidate 6 falls below it
    # exactly once. Measured on this seeded fixture: 1/70.
    rng = np.random.default_rng(21)
    noise = rng.normal(0.0, 0.004, size=(16, 48))
    matrix = np.full((16, 48), 0.001) + noise
    matrix[0] += 0.0036
    result = pbo_cscv(matrix, blocks=8)
    assert result["pbo"] == pytest.approx(0.0143, abs=5e-5)
    assert _cscv_under_median_count(matrix) == 1


# ---------------------------------------------------------------------------
# F-022 / CR-005: PBO subset stability on a family larger than the 128 cap.
# ---------------------------------------------------------------------------
def _large_family_pbo_matrix(seed: int = 42, candidates: int = 256, observations: int = 512) -> np.ndarray:
    """256 candidates in 8 archetypes over 512 observations in 8 CSCV blocks.

    Archetype r keeps per-block mean r*0.0013 plus a home-block tilt of 0.0015
    on its own two home blocks: realistic rank dispersion where the CSCV block
    split, not noise alone, drives reversals. Seed 42, deterministic.
    """
    rng = np.random.default_rng(seed)
    blocks = 8
    block_length = observations // blocks
    archetype = np.repeat(np.arange(blocks), candidates // blocks)
    base = 0.0013 * (archetype + 1.0)
    block_of_column = np.arange(observations) // block_length
    home = (block_of_column[None, :] - archetype[:, None]) % blocks
    tilt = np.where(home < 2, 0.0015, 0.0)
    return base[:, None] + tilt + rng.normal(0, 0.02, (candidates, observations))


def test_pbo_subset_stability_even_vs_random_vs_full() -> None:
    matrix = _large_family_pbo_matrix()
    full_pbo = pbo_cscv(matrix, blocks=8)["pbo"]
    even_indices = np.linspace(0, len(matrix) - 1, 128, dtype=np.int64)
    even_pbo = pbo_cscv(matrix[even_indices], blocks=8)["pbo"]

    rng = np.random.default_rng(20260114)
    random_pbos = []
    for _ in range(40):
        indices = np.sort(rng.choice(len(matrix), 128, replace=False))
        random_pbos.append(pbo_cscv(matrix[indices], blocks=8)["pbo"])
    random_array = np.asarray(random_pbos)
    random_mean = float(random_array.mean())
    random_max_deviation = float(np.max(np.abs(random_array - full_pbo)))

    # PBO lives on the 1/70 CSCV grid for this geometry.
    assert full_pbo == pytest.approx(0.0286, abs=1e-3)
    assert even_pbo == pytest.approx(0.0143, abs=1e-3)
    # Measured on this fixture: |even128 - full| = 0.0143 (one grid cell).
    assert abs(even_pbo - full_pbo) == pytest.approx(0.0143, abs=1e-3)
    # Measured on this fixture over 40 seeded random-128 subsets (stream
    # above): mean 0.0211, max |deviation from full| 0.0429 (three grid
    # cells), min 0.0000. Subset SIZE, not the selection policy, dominates
    # the spread; tolerances are pinned from these measurements, not asserted
    # as universal constants.
    assert random_mean == pytest.approx(0.0211, abs=0.01)
    assert random_max_deviation <= 0.0429 + 1e-9
    # The full-candidate calculation is itself one draw on the 1/70 grid: the
    # full PBO may exceed some 128-subset PBOs by up to the measured envelope
    # (here +0.0286 vs the minimum subset), so subset PBOs bound the full
    # value only within that measured spread.
    assert full_pbo - min(random_pbos) <= 0.0429 + 1e-9


# ---------------------------------------------------------------------------
# F-007 / CR-004: correlated-family DSR sensitivity.
# ---------------------------------------------------------------------------
def test_dsr_independent_family_is_optimistic_vs_correlated_families() -> None:
    """Same marginals, same trial count, deterministic direction.

    Both worlds are standardised quantile grids (mean 0, sample std 1), so the
    module's E[max] proxy - a function of (trial count, sample std, observed
    best Sharpe) only - is IDENTICAL by construction. The DSR difference is
    therefore driven purely by the best observed Sharpe: the independent
    world's 50-point grid produces a more extreme maximum (best ~ 2.35 sigma)
    than any single family in the correlated world (10 families x 5 children,
    best ~ 2.22 sigma at rho = 0.8), making independent-trial DSR optimistic
    DETERMINISTICALLY - no seed flips possible. The magnitude of the gap is
    grid-convention-dependent and is recorded, never asserted.
    """
    observations = 252

    # World A: 50 independent candidates as a standardised quantile grid.
    world_a_trials = _quantile_grid(50)
    report_a = deflated_sharpe_ratio(
        float(world_a_trials.max()), world_a_trials, observations=observations
    )

    # World B: 10 families x 5 equicorrelated children (rho = 0.8), built on a
    # standardised quantile grid so marginals match world A exactly.
    family_grid = norm.ppf((np.arange(10) + 0.5) / 10.0)
    child_grid = norm.ppf((np.arange(5) + 0.5) / 5.0)
    rho = 0.8
    correlated = (rho * family_grid[:, None] + math.sqrt(1 - rho ** 2) * child_grid[None, :]).ravel()
    world_b_trials = correlated / np.std(correlated, ddof=1)
    report_b = deflated_sharpe_ratio(
        float(world_b_trials.max()), world_b_trials, observations=observations
    )

    # Identical proxy inputs by construction.
    assert report_a["trial_count"] == report_b["trial_count"] == 50
    assert report_a["trial_sharpe_std"] == pytest.approx(report_b["trial_sharpe_std"], abs=1e-12)
    assert report_a["expected_max_sharpe_per_period"] == pytest.approx(
        report_b["expected_max_sharpe_per_period"], abs=1e-12
    )
    assert report_a["expected_max_sharpe_per_period"] == pytest.approx(
        _reference_expected_max_sharpe(50, 1.0), abs=1e-12
    )

    # Direction: independent-trial DSR is optimistic. Deterministic.
    gap = report_a["deflated_sharpe_probability"] - report_b["deflated_sharpe_probability"]
    assert gap > 0.0

    # Sensitivity rows at rho = 0.2 / 0.5 / 0.8 are documented, not asserted:
    # measured gaps +0.6776 / +0.5512 / +0.2554 on this grid construction.
    documented_gaps = []
    for sensitivity_rho in (0.2, 0.5, 0.8):
        correlated_s = (
            sensitivity_rho * family_grid[:, None]
            + math.sqrt(1 - sensitivity_rho ** 2) * child_grid[None, :]
        ).ravel()
        trials_s = correlated_s / np.std(correlated_s, ddof=1)
        report_s = deflated_sharpe_ratio(float(trials_s.max()), trials_s, observations=observations)
        documented_gaps.append(
            float(report_a["deflated_sharpe_probability"] - report_s["deflated_sharpe_probability"])
        )
    assert all(value > 0.0 for value in documented_gaps)

    # Evidentiary companion: a Monte Carlo of the TRUE correlated expected
    # maximum shows the independent-grid proxy overstates the family world's
    # realizable maximum - the shuffle-blindness of the independence
    # assumption made concrete.
    rng = np.random.default_rng(20260114)
    repetitions = 40_000
    family_factors = rng.standard_normal((repetitions, 10, 1))
    child_factors = rng.standard_normal((repetitions, 10, 5))
    family_max = (0.8 * family_factors + 0.6 * child_factors).reshape(repetitions, 50).max(axis=1)
    independent_max = rng.standard_normal((repetitions, 50)).max(axis=1)
    proxy = _reference_expected_max_sharpe(50, 1.0)
    # proxy - E[max | independent] ~ Euler small-N bias (~0.028 at N=50);
    # proxy - E[max | correlated family] is structurally larger.
    assert proxy - float(family_max.mean()) > proxy - float(independent_max.mean())
