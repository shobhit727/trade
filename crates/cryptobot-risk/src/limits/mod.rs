//! Risk limits and exposure bounds.

/// Bounds for a single trading limit.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct RiskLimits {
    pub max_exposure_pct: f64,
    pub max_single_position_pct: f64,
    pub max_drawdown_pct: f64,
    pub max_leverage: f64,
}

impl Default for RiskLimits {
    fn default() -> Self {
        RiskLimits {
            max_exposure_pct: 0.8,
            max_single_position_pct: 0.25,
            max_drawdown_pct: 0.20,
            max_leverage: 3.0,
        }
    }
}

/// Result of evaluating a prospective order against limits.
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum LimitCheck {
    Pass,
    Fail {
        reason: &'static str,
        limit: f64,
        actual: f64,
    },
}

/// Evaluate a single order: notional as fraction of equity, existing exposure.
/// `increase_exposure`: net exposure added by this order (0..=1 fraction of equity).
pub fn check_order(
    limits: &RiskLimits,
    current_exposure_pct: f64,
    order_exposure_pct: f64,
    leverage: f64,
) -> LimitCheck {
    // NaN fails closed (issue #41): `NaN > x` is always false, so a poisoned
    // upstream computation used to sail through every gate.
    if !current_exposure_pct.is_finite()
        || !order_exposure_pct.is_finite()
        || !leverage.is_finite()
    {
        return LimitCheck::Fail {
            reason: "non-finite input",
            limit: 0.0,
            actual: 0.0,
        };
    }
    let total = current_exposure_pct + order_exposure_pct;
    if order_exposure_pct > limits.max_single_position_pct {
        return LimitCheck::Fail {
            reason: "single-position limit",
            limit: limits.max_single_position_pct,
            actual: order_exposure_pct,
        };
    }
    if total > limits.max_exposure_pct {
        return LimitCheck::Fail {
            reason: "total-exposure limit",
            limit: limits.max_exposure_pct,
            actual: total,
        };
    }
    if leverage > limits.max_leverage {
        return LimitCheck::Fail {
            reason: "leverage limit",
            limit: limits.max_leverage,
            actual: leverage,
        };
    }
    LimitCheck::Pass
}

/// Scale position size down as drawdown grows (risk-on/risk-off ramp).
/// Returns a multiplier in [floor, 1.0]. No scaling while dd <= start.
pub fn drawdown_scale(drawdown_pct: f64, start_pct: f64, floor_pct: f64) -> f64 {
    if drawdown_pct <= start_pct || start_pct >= 1.0 {
        return 1.0;
    }
    let progress = ((drawdown_pct - start_pct) / (1.0 - start_pct)).clamp(0.0, 1.0);
    (1.0 - (1.0 - floor_pct) * progress).max(floor_pct)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn default_limits_sane() {
        let l = RiskLimits::default();
        assert!(l.max_exposure_pct > 0.0 && l.max_exposure_pct <= 1.0);
        assert!(l.max_leverage >= 1.0);
    }

    #[test]
    fn order_within_limits_passes() {
        let l = RiskLimits::default();
        assert_eq!(check_order(&l, 0.1, 0.2, 2.0), LimitCheck::Pass);
    }

    #[test]
    fn exposure_breach_fails() {
        let l = RiskLimits::default();
        match check_order(&l, 0.9, 0.2, 1.0) {
            LimitCheck::Fail { reason, .. } => assert!(reason.contains("exposure")),
            _ => panic!("expected failure"),
        }
    }

    #[test]
    fn leverage_breach_fails() {
        let l = RiskLimits::default();
        assert!(matches!(
            check_order(&l, 0.1, 0.1, 5.0),
            LimitCheck::Fail { .. }
        ));
    }

    #[test]
    fn drawdown_scale_ramp() {
        assert_eq!(drawdown_scale(0.05, 0.10, 0.2), 1.0);
        let mid = drawdown_scale(0.55, 0.10, 0.2);
        assert!(mid < 1.0 && mid > 0.2);
        assert_eq!(drawdown_scale(1.0, 0.10, 0.2), 0.2);
    }
}
