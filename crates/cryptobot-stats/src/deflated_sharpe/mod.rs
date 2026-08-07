//! Deflated Sharpe Ratio (Bailey & López de Prado)

/// Expected maximum of `n_trials` iid standard normals via deterministic MC.
fn expected_max_sharpe(n_trials: usize) -> f64 {
    if n_trials <= 1 {
        return 0.0;
    }
    let sims = 50_000usize;
    let mut rng = 0x9E3779B97F4A7C15u64;
    let mut acc = 0.0_f64;
    for _ in 0..sims {
        let mut best = f64::NEG_INFINITY;
        for _ in 0..n_trials {
            best = best.max(sample_normal(&mut rng));
        }
        acc += best;
    }
    acc / sims as f64
}

fn sample_normal(rng: &mut u64) -> f64 {
    // Box-Muller on deterministic xorshift stream.
    let u1 = next_unit(rng).max(1e-12);
    let u2 = next_unit(rng).max(1e-12);
    (-2.0 * u1.ln()).sqrt() * (std::f64::consts::TAU * u2).cos()
}

fn next_unit(rng: &mut u64) -> f64 {
    let mut x = *rng;
    x ^= x >> 12;
    x ^= x << 25;
    x ^= x >> 27;
    *rng = x;
    (x >> 11) as f64 / (1u64 << 53) as f64
}

/// Deflated Sharpe Ratio.
///
/// `sharpe`: observed Sharpe. `trials`: number of strategies tried.
/// `n_obs`: number of observations (e.g. return periods). `skew`, `kurtosis`: return moments.
pub fn deflated_sharpe(sharpe: f64, trials: usize, n_obs: usize, skew: f64, kurtosis: f64) -> f64 {
    if n_obs == 0 || trials == 0 || sharpe.is_nan() {
        return 0.0;
    }
    // Standard error of Sharpe (Lo, 2002) extended for skew/kurtosis.
    let se = (1.0 - skew * sharpe + (kurtosis - 1.0) * sharpe.powi(2) / 4.0) / (n_obs as f64 - 1.0);
    if se <= 0.0 {
        return f64::INFINITY;
    }
    let emc = expected_max_sharpe(trials);
    (sharpe - emc) / se.sqrt()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn zero_trials_returns_zero() {
        assert_eq!(deflated_sharpe(1.0, 0, 100, 0.0, 3.0), 0.0);
    }

    #[test]
    fn zero_observations_returns_zero() {
        assert_eq!(deflated_sharpe(1.0, 10, 0, 0.0, 3.0), 0.0);
    }

    #[test]
    fn high_sharpe_defeats_trials() {
        let ds = deflated_sharpe(3.0, 10, 1000, 0.0, 3.0);
        assert!(ds > 0.0);
    }

    #[test]
    fn more_trials_deflates_more() {
        let few = deflated_sharpe(1.5, 10, 500, 0.0, 3.0);
        let many = deflated_sharpe(1.5, 5000, 500, 0.0, 3.0);
        assert!(many < few);
    }

    #[test]
    fn expected_max_sharpe_grows() {
        assert!(expected_max_sharpe(100) > expected_max_sharpe(10));
    }
}
