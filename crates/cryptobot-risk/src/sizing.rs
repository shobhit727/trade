//! Sizing algorithms: Kelly, fixed-fraction, volatility-target

/// Kelly fraction: f* = (p * b - q) / b
/// where p = win probability, q = 1-p, b = win/loss ratio
///
/// Returns 0.0 for degenerate inputs (issue #41): non-finite or zero/negative
/// win-loss ratio, or win_prob outside [0, 1] — the raw formula produced ±inf/NaN.
pub fn kelly_fraction(win_prob: f64, win_loss_ratio: f64) -> f64 {
    if !win_loss_ratio.is_finite() || win_loss_ratio <= 0.0 {
        return 0.0;
    }
    if !win_prob.is_finite() || !(0.0..=1.0).contains(&win_prob) {
        return 0.0;
    }
    let q = 1.0 - win_prob;
    ((win_prob * win_loss_ratio - q) / win_loss_ratio).max(0.0)
}

/// Kelly fraction from win rate and avg win/loss
pub fn kelly_from_stats(win_rate: f64, avg_win: f64, avg_loss: f64) -> f64 {
    if avg_loss == 0.0 || !avg_win.is_finite() {
        return 0.0;
    }
    let win_loss_ratio = avg_win / avg_loss.abs();
    if win_loss_ratio <= 0.0 {
        return 0.0;
    }
    kelly_fraction(win_rate, win_loss_ratio)
}

/// Fixed fractional position size
pub fn fixed_fraction(equity: f64, fraction: f64) -> f64 {
    equity * fraction
}

/// Volatility-targeted position size
/// size = (target_vol / realized_vol) * equity
///
/// Guards against degenerate realized vol (issue #41): NaN/negative vol returns 0,
/// and absurd vol ratios are clamped to [`MAX_VOL_TARGET_LEVERAGE`] instead of
/// producing unbounded (1e12x-equity) notional.
pub const MAX_VOL_TARGET_LEVERAGE: f64 = 10.0;

pub fn vol_target(equity: f64, target_vol: f64, realized_vol: f64) -> f64 {
    if !realized_vol.is_finite() || realized_vol <= 0.0 {
        return 0.0;
    }
    if !target_vol.is_finite() || target_vol < 0.0 {
        return 0.0;
    }
    let size = (target_vol / realized_vol) * equity;
    let cap = MAX_VOL_TARGET_LEVERAGE * equity;
    if size > cap {
        cap
    } else {
        size
    }
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

    #[test]
    fn test_kelly_degenerate_inputs() {
        assert_eq!(kelly_fraction(0.5, 0.0), 0.0); // was -inf
        assert_eq!(kelly_fraction(0.5, f64::NAN), 0.0); // was NaN
        assert_eq!(kelly_fraction(-0.2, 1.0), 0.0); // invalid prob
        assert_eq!(kelly_from_stats(0.6, 0.0, 1.0), 0.0); // zero avg_win ratio
    }

    #[test]
    fn test_vol_target_degenerate_vol() {
        assert_eq!(vol_target(10_000.0, 0.10, 0.0), 0.0);
        assert_eq!(vol_target(10_000.0, 0.10, f64::NAN), 0.0); // was NaN
        assert_eq!(vol_target(10_000.0, 0.10, -0.2), 0.0); // was negative size
                                                           // Absurd ratio clamped to MAX_VOL_TARGET_LEVERAGE (was ~1e12 notional).
        assert_eq!(vol_target(10_000.0, 0.10, 1e-9), 100_000.0);
    }
}
