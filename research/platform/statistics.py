"""Multiple-testing and resampling utilities for candidate research."""

from __future__ import annotations

from itertools import combinations
from statistics import NormalDist
from typing import Mapping, Sequence

import numpy as np



def probabilistic_sharpe_ratio(
    observed_sharpe: float,
    *,
    observations: int,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
    benchmark_sharpe: float = 0.0,
) -> float:
    """Estimate the probability that true per-period Sharpe exceeds a benchmark.

    Sharpe inputs are per-period, not annualised. Kurtosis uses the Pearson convention
    (normal distribution = 3). This approximation assumes a sufficiently stationary
    return sample and is not a substitute for resampling or leakage checks.
    """
    # Apply the finite-sample PSR variance correction for skew and kurtosis.
    values = (observed_sharpe, skewness, kurtosis, benchmark_sharpe)
    if not all(np.isfinite(value) for value in values):
        raise ValueError("Sharpe inputs must be finite")
    if observations < 2 or kurtosis <= 0:
        raise ValueError("observations must be >= 2 and Pearson kurtosis must be positive")
    variance_factor = (
        1.0 - skewness * observed_sharpe
        + ((kurtosis - 1.0) / 4.0) * observed_sharpe * observed_sharpe
    )
    if variance_factor <= 0:
        raise ValueError("Sharpe variance correction is non-positive")
    z_score = (
        (observed_sharpe - benchmark_sharpe)
        * np.sqrt(observations - 1)
        / np.sqrt(variance_factor)
    )
    return float(NormalDist().cdf(float(z_score)))


def deflated_sharpe_ratio(
    observed_sharpe: float,
    trial_sharpes: Sequence[float],
    *,
    observations: int,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
) -> dict[str, float | int | str]:
    """Estimate DSR using the expected maximum Sharpe across the supplied trial family.

    Trial Sharpe values must use the same sampling frequency and comparable validation
    data. The expected maximum uses the Euler-constant approximation for independent
    Gaussian estimates. Dependence between strategies reduces the effective trial count;
    callers must report this assumption and should run sensitivity analysis.
    """
    # Validate the complete trial family instead of silently replacing invalid values.
    trials = np.asarray(trial_sharpes, dtype=np.float64)
    if trials.ndim != 1 or not len(trials) or not np.isfinite(trials).all():
        raise ValueError("trial_sharpes must be a non-empty finite one-dimensional sequence")
    if not np.isfinite(observed_sharpe) or observations < 2:
        raise ValueError("observed_sharpe must be finite and observations must be >= 2")
    trial_count = len(trials)
    if trial_count <= 1:
        expected_max = 0.0
        trial_std = 0.0
    else:
        trial_std = float(np.std(trials, ddof=1))
        euler_gamma = 0.5772156649015329
        p1 = 1.0 - 1.0 / trial_count
        p2 = 1.0 - 1.0 / (trial_count * np.e)
        normal = NormalDist()
        expected_max = trial_std * (
            (1.0 - euler_gamma) * normal.inv_cdf(p1)
            + euler_gamma * normal.inv_cdf(p2)
        )
    probability = probabilistic_sharpe_ratio(
        observed_sharpe,
        observations=observations,
        skewness=skewness,
        kurtosis=kurtosis,
        benchmark_sharpe=expected_max,
    )
    return {
        "deflated_sharpe_probability": probability,
        "observed_sharpe_per_period": float(observed_sharpe),
        "expected_max_sharpe_per_period": float(expected_max),
        "trial_sharpe_std": float(trial_std),
        "trial_count": int(trial_count),
        "observations": int(observations),
        "skewness": float(skewness),
        "pearson_kurtosis": float(kurtosis),
        "assumption": "independent_gaussian_trial_sharpes_approximation",
    }


def benjamini_hochberg(p_values: Sequence[float], alpha: float = 0.05) -> dict[str, object]:
    """Apply Benjamini-Hochberg false-discovery-rate correction."""
    # The correction family is exactly the supplied candidate hypothesis set.
    values = np.asarray(p_values, dtype=np.float64)
    if values.ndim != 1 or not np.isfinite(values).all():
        raise ValueError("p_values must be a finite one-dimensional sequence")
    if np.any((values < 0) | (values > 1)) or not 0 < alpha < 1:
        raise ValueError("p-values must be in [0,1] and alpha in (0,1)")
    count = len(values)
    if count == 0:
        return {"adjusted_p_values": [], "reject": [], "alpha": alpha, "hypotheses": 0}
    order = np.argsort(values, kind="stable")
    ranked = values[order] * count / np.arange(1, count + 1)
    adjusted_sorted = np.minimum.accumulate(ranked[::-1])[::-1]
    adjusted_sorted = np.clip(adjusted_sorted, 0.0, 1.0)
    adjusted = np.empty(count, dtype=np.float64)
    adjusted[order] = adjusted_sorted
    return {
        "adjusted_p_values": adjusted.tolist(),
        "reject": (adjusted <= alpha).tolist(),
        "alpha": float(alpha),
        "hypotheses": int(count),
        "rejections": int(np.sum(adjusted <= alpha)),
    }


def moving_block_bootstrap(
    returns: Sequence[float],
    *,
    block_size: int = 10,
    samples: int = 2000,
    confidence: float = 0.95,
    seed: int = 42,
) -> dict[str, float | int]:
    """Circular moving-block bootstrap interval for mean periodic return."""
    # Resample contiguous circular blocks to retain some short-horizon dependence.
    values = np.asarray(returns, dtype=np.float64)
    if values.ndim != 1 or len(values) < 2 or not np.isfinite(values).all():
        raise ValueError("returns must be a finite one-dimensional sequence")
    if not 1 <= block_size <= len(values) or samples < 100 or not 0 < confidence < 1:
        raise ValueError("invalid bootstrap configuration")
    rng = np.random.default_rng(seed)
    blocks_needed = int(np.ceil(len(values) / block_size))
    starts = np.arange(len(values))
    means = np.empty(samples, dtype=np.float64)
    for sample in range(samples):
        chosen = rng.choice(starts, size=blocks_needed, replace=True)
        draw = np.concatenate([
            values[(start + np.arange(block_size)) % len(values)] for start in chosen
        ])[:len(values)]
        means[sample] = float(np.mean(draw))
    tail = (1.0 - confidence) / 2.0
    low, high = np.quantile(means, [tail, 1.0 - tail])
    return {
        "mean_return": float(np.mean(values)),
        "ci_low": float(low),
        "ci_high": float(high),
        "confidence": float(confidence),
        "samples": int(samples),
        "block_size": int(block_size),
        "seed": int(seed),
    }


def pbo_cscv(
    strategy_returns: Sequence[Sequence[float]], *, blocks: int = 8
) -> dict[str, float | int]:
    """Estimate PBO from combinatorially symmetric cross-validation rank reversals.

    Returns the fraction of train-selected best strategies that rank below the OOS
    median. This is a diagnostic over the supplied candidate family, not a correction
    for data leakage or biased universe construction.
    """
    # Each strategy must cover the same finite timeline.
    matrix = np.asarray(strategy_returns, dtype=np.float64)
    if matrix.ndim != 2 or matrix.shape[0] < 2 or not np.isfinite(matrix).all():
        raise ValueError("strategy_returns must be a finite strategies-by-time matrix")
    if blocks < 4 or blocks % 2 or matrix.shape[1] < blocks:
        raise ValueError("CSCV requires an even block count of at least four")
    chunks = np.array_split(np.arange(matrix.shape[1]), blocks)
    half = blocks // 2
    under_median: list[bool] = []
    for train_blocks in combinations(range(blocks), half):
        # Use complementary block combinations for train and test.
        train_set = set(train_blocks)
        test_blocks = [index for index in range(blocks) if index not in train_set]
        train_indices = np.concatenate([chunks[index] for index in train_blocks])
        test_indices = np.concatenate([chunks[index] for index in test_blocks])

        def sharpe(series: np.ndarray) -> np.ndarray:
            # Zero-volatility series score zero rather than NaN or infinity.
            deviation = np.std(series, axis=1, ddof=1)
            mean = np.mean(series, axis=1)
            return np.divide(mean, deviation, out=np.zeros_like(mean), where=deviation > 0)

        train_scores = sharpe(matrix[:, train_indices])
        test_scores = sharpe(matrix[:, test_indices])
        selected = int(np.argmax(train_scores))
        # Rank 0 is the best OOS result; ties use stable original candidate order.
        descending_order = np.argsort(-test_scores, kind="stable")
        rank = np.empty(len(test_scores), dtype=np.int64)
        rank[descending_order] = np.arange(len(test_scores))
        percentile = (float(rank[selected]) + 0.5) / len(test_scores)
        under_median.append(percentile > 0.5)
    return {
        "pbo": float(np.mean(under_median)),
        "splits": len(under_median),
        "strategies": int(matrix.shape[0]),
        "blocks": int(blocks),
    }



def candidate_family_report_from_returns(
    candidate_ids: Sequence[str],
    candidate_returns: Mapping[str, Sequence[float]],
    *,
    periods_per_year: int,
    alpha: float = 0.05,
    pbo_blocks: int = 8,
    pbo_candidate_limit: int = 128,
) -> dict[str, object]:
    """Derive PSR p-values and multiple-testing diagnostics from TRAIN return vectors.

    FDR and DSR use the full candidate family. CSCV/PBO uses a deterministic evenly
    spaced subset to bound runtime and memory for large candidate populations.
    """
    # Preserve the caller's candidate ordering so all family-level arrays remain aligned.
    ids = tuple(str(value) for value in candidate_ids)
    if not ids or len(set(ids)) != len(ids):
        raise ValueError("candidate_ids must be non-empty and unique")
    if (
        isinstance(periods_per_year, bool)
        or not isinstance(periods_per_year, int)
        or periods_per_year < 1
    ):
        raise ValueError("periods_per_year must be a positive integer")
    if (
        isinstance(pbo_blocks, bool)
        or not isinstance(pbo_blocks, int)
        or pbo_blocks < 4
        or pbo_blocks % 2
    ):
        raise ValueError("pbo_blocks must be an even integer of at least four")
    if (
        isinstance(pbo_candidate_limit, bool)
        or not isinstance(pbo_candidate_limit, int)
        or pbo_candidate_limit < 2
    ):
        raise ValueError("pbo_candidate_limit must be an integer of at least two")
    if not 0 < alpha < 1:
        raise ValueError("alpha must be between zero and one")
    if set(ids) - set(candidate_returns):
        raise ValueError("candidate return vectors are missing for one or more candidates")

    vectors = [np.asarray(candidate_returns[candidate_id], dtype=np.float64) for candidate_id in ids]
    if any(vector.ndim != 1 or not np.isfinite(vector).all() for vector in vectors):
        raise ValueError("each candidate return vector must be finite and one-dimensional")
    observation_counts = {len(vector) for vector in vectors}
    if len(observation_counts) != 1 or next(iter(observation_counts)) < 2:
        raise ValueError("candidate return vectors must have equal lengths of at least two")
    observations = next(iter(observation_counts))

    # Estimate each candidate's per-period Sharpe and PSR-derived one-sided p-value.
    sharpes: list[float] = []
    p_values: list[float] = []
    shape_parameters: list[tuple[float, float]] = []
    for vector in vectors:
        deviation = float(np.std(vector, ddof=1))
        if deviation > 0:
            per_period_sharpe = float(np.mean(vector) / deviation)
            standardised = (vector - float(np.mean(vector))) / deviation
            skewness = float(np.mean(standardised ** 3))
            pearson_kurtosis = float(np.mean(standardised ** 4))
            pearson_kurtosis = max(pearson_kurtosis, 1e-12)
        else:
            per_period_sharpe = 0.0
            skewness = 0.0
            pearson_kurtosis = 3.0
        probability = probabilistic_sharpe_ratio(
            per_period_sharpe,
            observations=observations,
            skewness=skewness,
            kurtosis=pearson_kurtosis,
            benchmark_sharpe=0.0,
        )
        sharpes.append(per_period_sharpe)
        p_values.append(float(np.clip(1.0 - probability, 0.0, 1.0)))
        shape_parameters.append((skewness, pearson_kurtosis))

    # Select the best candidate's higher moments only as DSR's common-family approximation.
    best_index = int(np.argmax(sharpes))
    pbo_indices = (
        np.linspace(0, len(ids) - 1, num=min(len(ids), pbo_candidate_limit), dtype=np.int64)
    )
    pbo_matrix = np.vstack([vectors[int(index)] for index in pbo_indices])
    skewness, kurtosis = shape_parameters[best_index]
    report = candidate_family_report(
        ids,
        p_values,
        sharpes,
        pbo_matrix,
        observations=observations,
        alpha=alpha,
        skewness=skewness,
        kurtosis=kurtosis,
        pbo_blocks=pbo_blocks,
        pbo_candidate_limit=pbo_candidate_limit,
        pbo_candidate_indices=pbo_indices,
    )
    report["sampling_frequency"] = {
        "periods_per_year": int(periods_per_year),
        "sharpe_scale": "per_period",
    }
    report["p_value_method"] = "one_minus_probabilistic_sharpe_ratio_vs_zero"
    report["dsr_shape_source"] = "best_candidate_by_observed_per_period_sharpe"
    return report


def candidate_family_report(
    candidate_ids: Sequence[str],
    p_values: Sequence[float],
    trial_sharpes: Sequence[float],
    candidate_returns: Sequence[Sequence[float]],
    *,
    observations: int,
    alpha: float = 0.05,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
    pbo_blocks: int = 8,
    pbo_candidate_limit: int = 128,
    pbo_candidate_indices: Sequence[int] | None = None,
) -> dict[str, object]:
    """Combine FDR, DSR and CSCV PBO diagnostics for one declared search family.

    Each candidate ID must appear once, p-values and per-period Sharpe values must be
    aligned to that order, and candidate_returns must contain one row per candidate.
    This function reports diagnostics only; it does not declare a strategy deployable.
    """
    # Reject family misalignment rather than allowing a correction to use the wrong trial count.
    ids = tuple(str(candidate_id) for candidate_id in candidate_ids)
    if not ids or any(not candidate_id.strip() for candidate_id in ids):
        raise ValueError("candidate_ids must be non-empty strings")
    if len(set(ids)) != len(ids):
        raise ValueError("candidate_ids must be unique within a search family")
    if len(p_values) != len(ids) or len(trial_sharpes) != len(ids):
        raise ValueError("candidate IDs, p-values and trial Sharpes must have equal length")
    returns = np.asarray(candidate_returns, dtype=np.float64)
    if returns.ndim != 2 or returns.shape[0] < 1 or not np.isfinite(returns).all():
        raise ValueError("candidate_returns must be a non-empty finite two-dimensional matrix")
    if returns.shape[1] != observations:
        raise ValueError("observations must match the candidate return-matrix width")
    if (
        isinstance(pbo_candidate_limit, bool)
        or not isinstance(pbo_candidate_limit, int)
        or pbo_candidate_limit < 2
    ):
        raise ValueError("pbo_candidate_limit must be an integer of at least two")
    if (
        isinstance(pbo_blocks, bool)
        or not isinstance(pbo_blocks, int)
        or pbo_blocks < 4
        or pbo_blocks % 2
    ):
        raise ValueError("pbo_blocks must be an even integer of at least four")
    if pbo_candidate_indices is None:
        if returns.shape[0] != len(ids):
            raise ValueError("candidate_returns must have one row per candidate when indices are omitted")
        mapped_indices = np.arange(len(ids), dtype=np.int64)
    else:
        mapped_indices = np.asarray(pbo_candidate_indices, dtype=np.int64)
        if (
            mapped_indices.ndim != 1
            or len(mapped_indices) != returns.shape[0]
            or len(set(mapped_indices.tolist())) != len(mapped_indices)
            or np.any(mapped_indices < 0)
            or np.any(mapped_indices >= len(ids))
        ):
            raise ValueError("pbo_candidate_indices must uniquely map each return row to a candidate")
    if returns.shape[0] < 2 and observations >= pbo_blocks:
        # One series cannot produce cross-strategy ranking reversals; the other tests remain valid.
        pbo_available = False
    else:
        pbo_available = True

    # Apply FDR/DSR to the complete family; bound only the more expensive CSCV diagnostic.
    fdr = benjamini_hochberg(p_values, alpha=alpha)
    sharpes = np.asarray(trial_sharpes, dtype=np.float64)
    if not np.isfinite(sharpes).all():
        raise ValueError("trial Sharpes must be finite")
    best_index = int(np.argmax(sharpes))
    dsr = deflated_sharpe_ratio(
        float(sharpes[best_index]),
        sharpes,
        observations=observations,
        skewness=skewness,
        kurtosis=kurtosis,
    )
    if not pbo_available or observations < pbo_blocks:
        pbo: dict[str, object] = {
            "status": "not_computed",
            "reason": (
                "at least two candidates and eight observations are required for CSCV"
                if pbo_blocks == 8 else
                f"at least two candidates and {pbo_blocks} observations are required for CSCV"
            ),
            "candidate_family_size": len(ids),
            "observations": observations,
            "blocks": pbo_blocks,
        }
    else:
        # Use evenly spaced input-order candidates, not score-ranked candidates, for bounded CSCV.
        subset_positions = (
            np.linspace(0, len(mapped_indices) - 1, num=pbo_candidate_limit, dtype=np.int64)
            if len(mapped_indices) > pbo_candidate_limit
            else np.arange(len(mapped_indices), dtype=np.int64)
        )
        subset_matrix = returns[subset_positions]
        subset_ids = mapped_indices[subset_positions]
        pbo = dict(pbo_cscv(subset_matrix, blocks=pbo_blocks))
        pbo.update({
            "status": "computed",
            "candidate_family_size": len(ids),
            "candidate_subset_size": len(subset_positions),
            "candidate_subset_policy": "evenly_spaced_input_order",
            "candidate_ids": [ids[int(index)] for index in subset_ids],
        })
    adjusted = fdr["adjusted_p_values"]
    rejected = fdr["reject"]
    candidate_rows = [
        {
            "candidate_id": candidate_id,
            "p_value": float(p_values[index]),
            "adjusted_p_value": float(adjusted[index]),
            "fdr_rejected": bool(rejected[index]),
            "sharpe_per_period": float(sharpes[index]),
        }
        for index, candidate_id in enumerate(ids)
    ]
    return {
        "candidate_family_size": len(ids),
        "candidate_rows": candidate_rows,
        "fdr": fdr,
        "deflated_sharpe": dsr,
        "pbo_cscv": pbo,
        "best_candidate_by_observed_sharpe": ids[best_index],
        "classification": "diagnostic_only_requires_methodological_review",
    }
