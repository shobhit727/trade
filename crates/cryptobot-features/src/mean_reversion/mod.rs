//! Mean Reversion features

pub fn rsi(prices: &[f64], period: usize) -> Vec<f64> {
    if prices.len() < period + 1 {
        return vec![];
    }

    let mut gains = Vec::new();
    let mut losses = Vec::new();

    for i in 1..prices.len() {
        let diff = prices[i] - prices[i - 1];
        if diff > 0.0 {
            gains.push(diff);
            losses.push(0.0);
        } else {
            gains.push(0.0);
            losses.push(-diff);
        }
    }

    let mut rsi = Vec::new();
    let mut avg_gain = gains[..period].iter().sum::<f64>() / period as f64;
    let mut avg_loss = losses[..period].iter().sum::<f64>() / period as f64;

    let rs = if avg_loss > 0.0 {
        avg_gain / avg_loss
    } else {
        100.0
    };
    rsi.push(100.0 - 100.0 / (1.0 + rs));

    for i in period..gains.len() {
        avg_gain = (avg_gain * (period - 1) as f64 + gains[i]) / period as f64;
        avg_loss = (avg_loss * (period - 1) as f64 + losses[i]) / period as f64;
        let rs = if avg_loss > 0.0 {
            avg_gain / avg_loss
        } else {
            100.0
        };
        rsi.push(100.0 - 100.0 / (1.0 + rs));
    }

    rsi
}

pub fn bollinger_bands(
    prices: &[f64],
    period: usize,
    std_mult: f64,
) -> (Vec<f64>, Vec<f64>, Vec<f64>) {
    let mut middle = Vec::new();
    let mut upper = Vec::new();
    let mut lower = Vec::new();

    for window in prices.windows(period) {
        let mean = window.iter().sum::<f64>() / period as f64;
        let variance = window.iter().map(|p| (p - mean).powi(2)).sum::<f64>() / period as f64;
        let std = variance.sqrt();

        middle.push(mean);
        upper.push(mean + std_mult * std);
        lower.push(mean - std_mult * std);
    }

    (middle, upper, lower)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_rsi() {
        let prices = vec![
            100.0, 101.0, 100.5, 102.0, 101.5, 103.0, 102.5, 104.0, 103.5, 105.0,
        ];
        let rsi = rsi(&prices, 5);
        assert!(!rsi.is_empty());
        assert!(rsi.iter().all(|&v| (0.0..=100.0).contains(&v)));
    }
}
