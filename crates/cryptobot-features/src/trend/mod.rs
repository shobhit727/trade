//! Trend features

pub fn ema(prices: &[f64], period: usize) -> Vec<f64> {
    if prices.is_empty() || period == 0 {
        return vec![];
    }
    let alpha = 2.0 / (period + 1) as f64;
    let mut ema = Vec::with_capacity(prices.len());
    ema.push(prices[0]);
    
    for p in &prices[1..] {
        ema.push(alpha * p + (1.0 - alpha) * ema.last().unwrap());
    }
    ema
}

pub fn macd(prices: &[f64], fast: usize, slow: usize, signal: usize) -> (Vec<f64>, Vec<f64>, Vec<f64>) {
    let ema_fast = ema(prices, fast);
    let ema_slow = ema(prices, slow);
    
    let macd_line: Vec<f64> = ema_fast.iter().zip(ema_slow.iter()).map(|(f, s)| f - s).collect();
    let signal_line = ema(&macd_line, signal);
    let histogram: Vec<f64> = macd_line.iter().zip(signal_line.iter()).map(|(m, s)| m - s).collect();
    
    (macd_line, signal_line, histogram)
}

#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_ema() {
        let prices = vec![100.0, 101.0, 102.0, 103.0, 104.0];
        let ema = ema(&prices, 3);
        assert_eq!(ema.len(), 5);
    }
}