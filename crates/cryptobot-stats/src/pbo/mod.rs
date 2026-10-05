//! Probability of Backtest Overfitting (Bailey, Borwein, López de Prado, Zhu).

use std::collections::BTreeSet;

/// Sharpe ratio of a return series.
fn sharpe(returns: &[f64]) -> f64 {
    if returns.len() < 2 {
        return 0.0;
    }
    let m = returns.iter().sum::<f64>() / returns.len() as f64;
    let var = returns.iter().map(|r| (r - m).powi(2)).sum::<f64>() / (returns.len() - 1) as f64;
    if var <= 0.0 {
        return f64::INFINITY;
    }
    m / var.sqrt()
}

/// Rank (1 = best) of `value` within `scores` (higher score = better).
fn rank_of(value: f64, scores: &[f64]) -> usize {
    let mut sorted = scores.to_vec();
    sorted.sort_by(|a, b| b.partial_cmp(a).unwrap_or(std::cmp::Ordering::Equal));
    sorted
        .iter()
        .position(|&s| (s - value).abs() < f64::EPSILON)
        .map(|i| i + 1)
        .unwrap_or(sorted.len() + 1)
}

/// Probability of Backtest Overfitting via CSCV with S=2 blocks.
///
/// `strategies`: each row is one strategy's full return series. Block size `s` splits
/// the series into `N = len / s` contiguous blocks; all C(N, N/2) training splits
/// are evaluated (capped at `max_splits` for tractability).
pub fn probability_of_backtest_overfitting(strategies: &[&[f64]], s: usize) -> f64 {
    if strategies.is_empty() || s == 0 {
        return 0.0;
    }
    let n = strategies[0].len();
    if strategies.iter().any(|st| st.len() != n) {
        return f64::NAN;
    }
    let n_blocks = n / s;
    if n_blocks < 2 {
        return f64::NAN;
    }
    let half = n_blocks / 2;
    if half == 0 {
        return f64::NAN;
    }

    // Enumerate C(n_blocks, half) training subsets (cap for tractability).
    let mut combos: Vec<Vec<usize>> = Vec::new();
    let mut stack = vec![(0usize, Vec::<usize>::new())];
    while let Some((start, chosen)) = stack.pop() {
        if chosen.len() == half {
            combos.push(chosen);
            continue;
        }
        for idx in (start..n_blocks).rev() {
            let mut next = chosen.clone();
            next.push(idx);
            if combos.len() < 256 {
                stack.push((idx + 1, next));
            }
        }
    }
    if combos.is_empty() {
        return 0.0;
    }

    let mut negative_logits = 0usize;
    for train_blocks in &combos {
        let train_set: BTreeSet<usize> = train_blocks.iter().copied().collect();
        // Aggregate train/test return vectors per strategy.
        let train_returns: Vec<Vec<f64>> = strategies
            .iter()
            .map(|st| {
                (0..n_blocks)
                    .filter(|b| train_set.contains(b))
                    .flat_map(|b| st[b * s..(b * s + s).min(n)].to_vec())
                    .collect()
            })
            .collect();
        let test_returns: Vec<Vec<f64>> = strategies
            .iter()
            .map(|st| {
                (0..n_blocks)
                    .filter(|b| !train_set.contains(b))
                    .flat_map(|b| st[b * s..(b * s + s).min(n)].to_vec())
                    .collect()
            })
            .collect();

        let train_scores: Vec<f64> = train_returns.iter().map(|r| sharpe(r)).collect();
        let test_scores: Vec<f64> = test_returns.iter().map(|r| sharpe(r)).collect();

        let best_train_idx = train_scores
            .iter()
            .enumerate()
            .max_by(|a, b| a.1.partial_cmp(b.1).unwrap_or(std::cmp::Ordering::Equal))
            .map(|(i, _)| i)
            .unwrap_or(0);
        let best_train_rank_in_test = rank_of(test_scores[best_train_idx], &test_scores);
        let w = best_train_rank_in_test as f64 / strategies.len() as f64;
        let logit = (w / (1.0 - w).max(f64::EPSILON)).ln();
        if logit < 0.0 {
            negative_logits += 1;
        }
    }
    negative_logits as f64 / combos.len() as f64
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn empty_input() {
        assert_eq!(probability_of_backtest_overfitting(&[], 10), 0.0);
    }

    #[test]
    fn identical_strategies_are_random() {
        let a = vec![0.01, 0.02, 0.01, 0.02, 0.01, 0.02, 0.01, 0.02];
        let b = vec![0.01, 0.02, 0.01, 0.02, 0.01, 0.02, 0.01, 0.02];
        let p = probability_of_backtest_overfitting(&[&a, &b], 2);
        assert!((0.0..=1.0).contains(&p));
    }

    #[test]
    fn shorter_series_nan() {
        let a = vec![0.1];
        let b = vec![0.2, 0.3];
        let p = probability_of_backtest_overfitting(&[&a, &b], 2);
        assert!(p.is_nan());
    }

    #[test]
    fn sharpe_sanity() {
        let rising = vec![0.01, 0.012, 0.009, 0.011, 0.013];
        let falling = vec![-0.01, -0.012, -0.009, -0.011, -0.013];
        assert!(sharpe(&rising) > 0.0);
        assert!(sharpe(&falling) < 0.0);
    }
}
