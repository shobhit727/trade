//! Correlation utilities

pub fn max_abs_correlation(corr_matrix: &[Vec<f64>]) -> f64 {
    let n = corr_matrix.len();
    let mut max_corr = 0.0;
    for (i, row) in corr_matrix.iter().take(n).enumerate() {
        for c in row.iter().skip(i + 1).take(n) {
            let c = c.abs();
            if c > max_corr {
                max_corr = c;
            }
        }
    }
    max_corr
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_max_abs_corr() {
        let m = vec![
            vec![1.0, 0.5, -0.8],
            vec![0.5, 1.0, 0.3],
            vec![-0.8, 0.3, 1.0],
        ];
        assert!((max_abs_correlation(&m) - 0.8).abs() < 1e-9);
    }
}
