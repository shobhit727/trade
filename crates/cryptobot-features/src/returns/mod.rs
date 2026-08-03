//! Returns features

pub fn log_returns(prices: &[f64], horizon: usize) -> Vec<f64> {
    if prices.len() <= horizon {
        return vec![];
    }
    prices
        .windows(horizon + 1)
        .map(|w| (w[horizon] / w[0]).ln())
        .collect()
}

pub fn simple_returns(prices: &[f64], horizon: usize) -> Vec<f64> {
    if prices.len() <= horizon {
        return vec![];
    }
    prices
        .windows(horizon + 1)
        .map(|w| w[horizon] / w[0] - 1.0)
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_log_returns() {
        let prices = vec![100.0, 101.0, 102.0, 103.0];
        let returns = log_returns(&prices, 1);
        assert_eq!(returns.len(), 3);
    }
}
