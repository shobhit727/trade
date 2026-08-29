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

    // Convention: zero average loss in the window -> RSI is exactly 100.
    if avg_loss > 0.0 {
        let rs = avg_gain / avg_loss;
        rsi.push(100.0 - 100.0 / (1.0 + rs));
    } else {
        rsi.push(100.0);
    }

    for i in period..gains.len() {
        avg_gain = (avg_gain * (period - 1) as f64 + gains[i]) / period as f64;
        avg_loss = (avg_loss * (period - 1) as f64 + losses[i]) / period as f64;
        if avg_loss > 0.0 {
            let rs = avg_gain / avg_loss;
            rsi.push(100.0 - 100.0 / (1.0 + rs));
        } else {
            rsi.push(100.0);
        }
    }

    rsi
}

pub fn bollinger_bands(
    prices: &[f64],
    period: usize,
    std_mult: f64,
) -> (Vec<f64>, Vec<f64>, Vec<f64>) {
    // Guard against `windows(0)` panic (issue #53): empty inputs return empty bands.
    if prices.is_empty() || period == 0 || period > prices.len() {
        return (Vec::new(), Vec::new(), Vec::new());
    }
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

    #[test]
    fn rsi_zero_loss_is_exactly_100() {
        // Monotonic uptrend -> zero average loss -> RSI must be exactly 100.0,
        // not the 99.01 the old `100 - 100/(1+rs)` formula produced (issue #53).
        let prices = vec![1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0];
        let rsi = rsi(&prices, 2);
        assert!(!rsi.is_empty());
        assert!(rsi.iter().all(|&v| (v - 100.0).abs() < 1e-12), "rsi = {:?}", rsi);
    }

    #[test]
    fn bollinger_period_zero_is_empty() {
        // `windows(0)` panicked before the guard (issue #53).
        let (mid, up, low) = bollinger_bands(&[1.0, 2.0, 3.0], 0, 2.0);
        assert!(mid.is_empty() && up.is_empty() && low.is_empty());
    }
}
