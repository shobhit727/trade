//! Portfolio optimization: hierarchical risk parity and risk-based weights.

/// Invert a positive-definite-ish covariance matrix via Gaussian elimination (2x2+).
/// Returns None if singular. Tiny implementation; real prod uses LAPACK via ndarray.
fn invert_2d(mat: &[Vec<f64>]) -> Option<Vec<Vec<f64>>> {
    let n = mat.len();
    if n == 0 || mat.iter().any(|r| r.len() != n) {
        return None;
    }
    // Gauss-Jordan
    let mut a = mat.to_vec();
    let mut inv: Vec<Vec<f64>> = (0..n)
        .map(|i| (0..n).map(|j| if i == j { 1.0 } else { 0.0 }).collect())
        .collect();
    for col in 0..n {
        let mut pivot = col;
        for row in col + 1..n {
            if a[row][col].abs() > a[pivot][col].abs() {
                pivot = row;
            }
        }
        if a[pivot][col].abs() < 1e-12 {
            return None; // singular
        }
        a.swap(col, pivot);
        inv.swap(col, pivot);
        let d = a[col][col];
        for j in 0..n {
            a[col][j] /= d;
            inv[col][j] /= d;
        }
        for row in 0..n {
            if row != col {
                let factor = a[row][col];
                if factor != 0.0 {
                    for j in 0..n {
                        a[row][j] -= factor * a[col][j];
                        inv[row][j] -= factor * inv[col][j];
                    }
                }
            }
        }
    }
    Some(inv)
}

/// Mean-variance (Markowitz) weights given expected returns and covariance.
/// Returns None if covariance is singular. No short-sale constraint.
pub fn mean_variance_weights(mean_returns: &[f64], cov: &[Vec<f64>]) -> Option<Vec<f64>> {
    let inv = invert_2d(cov)?;
    let n = mean_returns.len();
    let mut num = vec![0.0_f64; n];
    for i in 0..n {
        num[i] = inv[i].iter().zip(mean_returns).map(|(a, b)| a * b).sum();
    }
    let denom: f64 = num.iter().sum();
    if denom.abs() < 1e-12 {
        return None;
    }
    Some(num.iter().map(|w| w / denom).collect())
}

/// Inverse-volatility weights: proportional to 1/std per asset, normalized to 1.
pub fn inverse_vol_weights(cov: &[Vec<f64>]) -> Vec<f64> {
    let n = cov.len();
    let mut w = Vec::with_capacity(n);
    let mut total = 0.0_f64;
    for (i, row) in cov.iter().enumerate().take(n) {
        let var = row.get(i).copied().unwrap_or(0.0);
        let inv = if var > 0.0 { 1.0 / var.sqrt() } else { 0.0 };
        total += inv;
        w.push(inv);
    }
    if total <= 0.0 {
        return vec![1.0 / n as f64; n];
    }
    w.iter().map(|x| x / total).collect()
}

/// Equal-risk-contribution weights via iterative solver (a.k.a. risk parity).
pub fn risk_parity_weights(cov: &[Vec<f64>], iters: usize) -> Vec<f64> {
    let n = cov.len();
    if n == 0 {
        return Vec::new();
    }
    let mut w = vec![1.0 / n as f64; n];
    for _ in 0..iters {
        let vol: Vec<f64> = (0..n)
            .map(|i| {
                let var = cov[i].iter().zip(&w).map(|(c, ww)| c * ww).sum::<f64>();
                (w[i] * var).max(1e-12)
            })
            .collect();
        let total: f64 = vol.iter().sum();
        if total <= 0.0 {
            break;
        }
        for i in 0..n {
            w[i] = (vol[i] / total) * (w[i] / (w[i] * cov[i][i]).max(1e-12));
        }
        let s: f64 = w.iter().sum();
        if s > 0.0 {
            for value in w.iter_mut() {
                *value /= s;
            }
        }
    }
    w
}

#[cfg(test)]
mod tests {
    use super::*;

    fn diag_cov(vars: &[f64]) -> Vec<Vec<f64>> {
        let n = vars.len();
        (0..n)
            .map(|i| (0..n).map(|j| if i == j { vars[i] } else { 0.0 }).collect())
            .collect()
    }

    #[test]
    fn inverse_vol_weights_normalize() {
        let cov = diag_cov(&[4.0, 9.0]);
        let w = inverse_vol_weights(&cov);
        assert!((w.iter().sum::<f64>() - 1.0).abs() < 1e-12);
        assert!(w[0] > w[1]); // lower vol -> more weight
    }

    #[test]
    fn mean_variance_weights_positive() {
        let cov = diag_cov(&[4.0, 9.0]);
        let w = mean_variance_weights(&[0.1, 0.05], &cov).unwrap();
        assert!((w.iter().sum::<f64>() - 1.0).abs() < 1e-12);
        assert!(w[0] > w[1]);
    }

    #[test]
    fn mean_variance_singular_returns_none() {
        let cov = vec![vec![1.0, 1.0], vec![1.0, 1.0]];
        assert!(mean_variance_weights(&[0.1, 0.1], &cov).is_none());
    }

    #[test]
    fn risk_parity_equal_variance() {
        let cov = diag_cov(&[1.0, 1.0]);
        let w = risk_parity_weights(&cov, 100);
        assert!((w[0] - 0.5).abs() < 1e-6);
        assert!((w[1] - 0.5).abs() < 1e-6);
    }
}
