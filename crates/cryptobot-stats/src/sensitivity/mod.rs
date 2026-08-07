//! Parameter sensitivity analysis for strategy configs.

/// Result of perturbing one parameter around a base value.
#[derive(Debug, Clone, PartialEq)]
pub struct SensitivityPoint {
    pub param: String,
    pub base_value: f64,
    pub metric: f64,
    /// Change in metric per unit change in parameter (numerical derivative).
    pub derivative: f64,
}

/// Mean sensitivity across a parameter grid: how much the metric moves.
pub fn parameter_sensitivity(
    param: &str,
    base_value: f64,
    perturbations: &[f64],
    metric: &dyn Fn(f64) -> f64,
) -> SensitivityPoint {
    let base_metric = metric(base_value);
    let mut max_delta = 0.0_f64;
    for &p in perturbations {
        let delta = (metric(p) - base_metric).abs();
        if delta > max_delta {
            max_delta = delta;
        }
    }
    // Central-difference derivative at base.
    let h = 1e-6 * base_value.abs().max(1.0);
    let derivative = (metric(base_value + h) - metric(base_value - h)) / (2.0 * h);
    SensitivityPoint {
        param: param.to_string(),
        base_value,
        metric: base_metric,
        derivative,
    }
}

/// Grid-search sensitivity: evaluates the metric at every point in `grid`
/// and reports which parameter variation caused the largest metric swing.
pub fn grid_sensitivity(_param: &str, grid: &[f64], metric: &dyn Fn(f64) -> f64) -> (f64, f64) {
    // (max_metric, min_metric)
    if grid.is_empty() {
        return (0.0, 0.0);
    }
    let vals: Vec<f64> = grid.iter().map(|&g| metric(g)).collect();
    let max = vals.iter().cloned().fold(f64::NEG_INFINITY, f64::max);
    let min = vals.iter().cloned().fold(f64::INFINITY, f64::min);
    (max, min)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sensitivity_derivative_of_square() {
        // f(x) = x^2, derivative at 3 is 6.
        let sp = parameter_sensitivity("x", 3.0, &[2.9, 3.1], &|x| x * x);
        assert_eq!(sp.param, "x");
        assert!((sp.metric - 9.0).abs() < 1e-6);
        assert!((sp.derivative - 6.0).abs() < 1e-3);
    }

    #[test]
    fn grid_sensitivity_range() {
        let (max, min) = grid_sensitivity("x", &[-2.0, -1.0, 0.0, 1.0, 2.0], &|x| x * x);
        assert_eq!(max, 4.0);
        assert_eq!(min, 0.0);
    }

    #[test]
    fn empty_grid() {
        let (max, min) = grid_sensitivity("x", &[], &|x| x);
        assert_eq!((max, min), (0.0, 0.0));
    }

    #[test]
    fn flat_function_zero_sensitivity() {
        let sp = parameter_sensitivity("x", 1.0, &[0.5, 1.5], &|_| 42.0);
        assert!((sp.metric - 42.0).abs() < 1e-9);
        assert!((sp.derivative).abs() < 1e-6);
    }
}
