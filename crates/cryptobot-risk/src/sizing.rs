//! Sizing algorithms: Kelly, fixed-fraction, volatility-target

/// Kelly fraction: f* = (p * b - q) / b
/// where p = win probability, q = 1-p, b = win/loss ratio
pub fn kelly_fraction(win_prob: f64, win_loss_ratio: f64) -> f64 {
    let q = 1.0 - win_prob;
    (win_prob * win_loss_ratio - q) / win_loss_ratio
}

/// Kelly fraction from win rate and avg win/loss
pub fn kelly_from_stats(win_rate: f64, avg_win: f64, avg_loss: f64) -> f64 {
    if avg_loss == 0.0 {
        return 0.0;
    }
    let win_loss_ratio = avg_win / avg_loss.abs();
    kelly_fraction(win_rate, win_loss_ratio)
}

/// Fixed fractional position size
pub fn fixed_fraction(equity: f64, fraction: f64) -> f64 {
    equity * fraction
}

/// Volatility-targeted position size
/// size = (target_vol / realized_vol) * equity
pub fn vol_target(equity: f64, target_vol: f64, realized_vol: f64) -> f64 {
    if realized_vol == 0.0 {
        return 0.0;
    }
    (target_vol / realized_vol) * equity
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_kelly() {
        let f = kelly_fraction(0.6, 2.0);
        assert!((f - 0.4).abs() < 1e-9);
    }

    #[test]
    fn test_fixed_fraction() {
        assert_eq!(fixed_fraction(10000.0, 0.02), 200.0);
    }

    #[test]
    fn test_vol_target() {
        assert_eq!(vol_target(10000.0, 0.10, 0.20), 5000.0);
    }
}
