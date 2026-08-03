//! PyO3 bindings for cryptobot-risk

use pyo3::prelude::*;

/// Kelly fraction from win rate and win/loss ratio
#[pyfunction]
fn py_kelly_fraction(win_prob: f64, win_loss_ratio: f64) -> PyResult<f64> {
    Ok(crate::sizing::kelly_fraction(win_prob, win_loss_ratio))
}

/// Kelly fraction from win rate and avg win/loss
#[pyfunction]
fn py_kelly_from_stats(win_rate: f64, avg_win: f64, avg_loss: f64) -> PyResult<f64> {
    Ok(crate::sizing::kelly_from_stats(win_rate, avg_win, avg_loss))
}

/// Fixed fractional position size
#[pyfunction]
fn py_fixed_fraction(equity: f64, fraction: f64) -> PyResult<f64> {
    Ok(crate::sizing::fixed_fraction(equity, fraction))
}

/// Volatility-targeted position size
#[pyfunction]
fn py_vol_target(equity: f64, target_vol: f64, realized_vol: f64) -> PyResult<f64> {
    Ok(crate::sizing::vol_target(equity, target_vol, realized_vol))
}

/// Max absolute correlation in matrix
#[pyfunction]
fn py_max_abs_correlation(corr_matrix: Vec<Vec<f64>>) -> PyResult<f64> {
    Ok(crate::correlation::max_abs_correlation(&corr_matrix))
}

#[pymodule]
fn cryptobot_risk(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    m.add_function(wrap_pyfunction!(py_kelly_fraction, m)?)?;
    m.add_function(wrap_pyfunction!(py_kelly_from_stats, m)?)?;
    m.add_function(wrap_pyfunction!(py_fixed_fraction, m)?)?;
    m.add_function(wrap_pyfunction!(py_vol_target, m)?)?;
    m.add_function(wrap_pyfunction!(py_max_abs_correlation, m)?)?;
    Ok(())
}
