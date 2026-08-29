//! Volatility features

pub fn realized_volatility(returns: &[f64], window: usize) -> Vec<f64> {
    if returns.len() < window {
        return vec![];
    }
    returns
        .windows(window)
        .map(|w| {
            let mean = w.iter().sum::<f64>() / w.len() as f64;
            let variance = w.iter().map(|r| (r - mean).powi(2)).sum::<f64>() / w.len() as f64;
            variance.sqrt()
        })
        .collect()
}

pub fn ewma_volatility(returns: &[f64], lambda: f64) -> Vec<f64> {
    // Reject invalid decay factors (issue #53): λ outside [0, 1] makes the recursion
    // negative -> sqrt(NaN) poisons the whole stream.
    if returns.is_empty() || !(0.0..=1.0).contains(&lambda) {
        return vec![];
    }
    let mut vol = Vec::with_capacity(returns.len());
    let mut var = returns[0].powi(2);
    vol.push(var.sqrt());

    for r in &returns[1..] {
        var = lambda * var + (1.0 - lambda) * r.powi(2);
        vol.push(var.sqrt());
    }
    vol
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_realized_vol() {
        let returns = vec![0.01, -0.005, 0.02, -0.01, 0.015, 0.005];
        let vol = realized_volatility(&returns, 3);
        assert_eq!(vol.len(), 4);
    }

    #[test]
    fn ewma_rejects_invalid_lambda() {
        // λ outside [0, 1] makes the recursion negative -> sqrt(NaN) poisons the
        // stream (issue #53). Guard returns an empty series instead.
        let returns = vec![0.01, -0.005, 0.02, -0.01];
        assert!(ewma_volatility(&returns, 1.5).is_empty());
        assert!(ewma_volatility(&returns, -0.1).is_empty());
        assert!(ewma_volatility(&[], 0.94).is_empty());
    }
}
