//! Monte Carlo block-permutation testing for strategy returns.

use std::f64;

/// Re-sample returns by permuting contiguous blocks (block bootstrap).
/// Returns a new series of the same length. `block`: block size, `seed`: RNG seed.
pub fn block_permute(returns: &[f64], block: usize, seed: u64) -> Vec<f64> {
    if returns.is_empty() || block == 0 {
        return Vec::new();
    }
    let n = returns.len();
    let n_blocks = n / block + (n % block != 0) as usize;
    let mut rng = simple_rng(seed);
    let mut out = Vec::with_capacity(n);
    while out.len() < n {
        let b = next_usize(&mut rng) % n_blocks;
        let start = b * block;
        for &r in returns.iter().take((start + block).min(n)).skip(start) {
            out.push(r);
            if out.len() == n {
                break;
            }
        }
    }
    out
}

/// Cumulative return of a series.
pub fn total_return(returns: &[f64]) -> f64 {
    returns.iter().fold(1.0, |acc, r| acc * (1.0 + r)) - 1.0
}

/// Mean return.
pub fn mean(returns: &[f64]) -> f64 {
    if returns.is_empty() {
        return 0.0;
    }
    returns.iter().sum::<f64>() / returns.len() as f64
}

/// Sample standard deviation.
pub fn std_dev(returns: &[f64]) -> f64 {
    let n = returns.len();
    if n < 2 {
        return 0.0;
    }
    let m = mean(returns);
    let var = returns.iter().map(|r| (r - m).powi(2)).sum::<f64>() / (n - 1) as f64;
    var.sqrt()
}

/// Distribution of total returns over `sims` block-permuted trials.
/// Returns sorted outcomes.
pub fn simulate_total_returns(returns: &[f64], block: usize, sims: usize, seed: u64) -> Vec<f64> {
    let mut outcomes = Vec::with_capacity(sims);
    for i in 0..sims {
        let permuted = block_permute(returns, block, seed + i as u64);
        outcomes.push(total_return(&permuted));
    }
    outcomes.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
    outcomes
}

/// Probability of a non-positive return under the null (fraction of outcomes <= 0).
pub fn probability_of_loss(returns: &[f64], block: usize, sims: usize, seed: u64) -> f64 {
    if sims == 0 {
        return 0.0;
    }
    let outcomes = simulate_total_returns(returns, block, sims, seed);
    let losses = outcomes.iter().filter(|&&o| o <= 0.0).count();
    losses as f64 / sims as f64
}

/// Percentile of a sorted series (0..=1). Linear interpolation between neighbors.
pub fn percentile(sorted: &[f64], q: f64) -> f64 {
    if sorted.is_empty() {
        return 0.0;
    }
    if sorted.len() == 1 {
        return sorted[0];
    }
    let pos = q.clamp(0.0, 1.0) * (sorted.len() - 1) as f64;
    let lo = pos.floor() as usize;
    let hi = pos.ceil() as usize;
    let frac = pos - lo as f64;
    sorted[lo] * (1.0 - frac) + sorted[hi] * frac
}

fn simple_rng(seed: u64) -> u64 {
    // xorshift64
    let mut x = seed.wrapping_add(0x9E3779B97F4A7C15);
    x = if x == 0 { 0x1234567890ABCDEF } else { x };
    x
}

fn next_usize(rng: &mut u64) -> usize {
    let mut x = *rng;
    x ^= x >> 12;
    x ^= x << 25;
    x ^= x >> 27;
    *rng = x;
    (x.wrapping_mul(0x2545F4914F6CDD1D) >> 32) as usize
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn block_permute_preserves_length() {
        let r = vec![0.01, -0.02, 0.03, -0.01, 0.02, 0.0];
        assert_eq!(block_permute(&r, 2, 1).len(), r.len());
    }

    #[test]
    fn total_return_compounds() {
        let r = vec![0.1, -0.1];
        assert!((total_return(&r) - -0.01).abs() < 1e-12);
    }

    #[test]
    fn mean_and_std() {
        let r = vec![1.0, 2.0, 3.0];
        assert!((mean(&r) - 2.0).abs() < 1e-12);
        assert!((std_dev(&r) - 1.0).abs() < 1e-12);
    }

    #[test]
    fn percentile_extremes() {
        let s = vec![1.0, 2.0, 3.0, 4.0];
        assert_eq!(percentile(&s, 0.0), 1.0);
        assert_eq!(percentile(&s, 1.0), 4.0);
        assert_eq!(percentile(&s, 0.5), 2.5);
    }

    #[test]
    fn loss_probability_between_zero_and_one() {
        let r = vec![0.005, -0.003, 0.002, -0.001];
        let p = probability_of_loss(&r, 2, 100, 42);
        assert!((0.0..=1.0).contains(&p));
    }

    #[test]
    fn empty_input_safe() {
        assert_eq!(block_permute(&[], 2, 1), Vec::new());
        assert_eq!(mean(&[]), 0.0);
        assert_eq!(std_dev(&[]), 0.0);
    }
}
