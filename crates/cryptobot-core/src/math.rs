//! Math utilities: statistics, numerical helpers

pub fn mean(values: &[f64]) -> f64 {
    if values.is_empty() {
        return 0.0;
    }
    values.iter().sum::<f64>() / values.len() as f64
}

pub fn variance(values: &[f64]) -> f64 {
    if values.is_empty() {
        return 0.0;
    }
    let m = mean(values);
    values.iter().map(|v| (v - m).powi(2)).sum::<f64>() / values.len() as f64
}

pub fn std_dev(values: &[f64]) -> f64 {
    variance(values).sqrt()
}

pub fn correlation(x: &[f64], y: &[f64]) -> f64 {
    let n = x.len().min(y.len());
    if n < 2 {
        return 0.0;
    }
    let mx = mean(&x[..n]);
    let my = mean(&y[..n]);
    let mut num = 0.0;
    let mut den_x = 0.0;
    let mut den_y = 0.0;
    for i in 0..n {
        let dx = x[i] - mx;
        let dy = y[i] - my;
        num += dx * dy;
        den_x += dx * dx;
        den_y += dy * dy;
    }
    let denom = (den_x * den_y).sqrt();
    if denom == 0.0 {
        0.0
    } else {
        num / denom
    }
}

pub fn rolling_mean(values: &[f64], window: usize) -> Vec<f64> {
    if window == 0 || values.is_empty() {
        return vec![];
    }
    values
        .windows(window)
        .map(|w| mean(w))
        .collect()
}

pub fn rolling_std(values: &[f64], window: usize) -> Vec<f64> {
    if window == 0 || values.is_empty() {
        return vec![];
    }
    values.windows(window).map(|w| std_dev(w)).collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_mean() {
        assert_eq!(mean(&[1.0, 2.0, 3.0, 4.0, 5.0]), 3.0);
    }

    #[test]
    fn test_correlation() {
        let x = vec![1.0, 2.0, 3.0, 4.0];
        let y = vec![2.0, 4.0, 6.0, 8.0];
        assert!((correlation(&x, &y) - 1.0).abs() < 1e-9);
    }

    #[test]
    fn test_rolling() {
        let v = vec![1.0, 2.0, 3.0, 4.0, 5.0];
        assert_eq!(rolling_mean(&v, 3), vec![2.0, 3.0, 4.0]);
    }
}