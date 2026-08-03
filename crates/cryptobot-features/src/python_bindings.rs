//! PyO3 bindings for cryptobot-features
//!
//! Exposes Rust feature computation to Python via PyO3.

use pyo3::prelude::*;

/// Python-accessible wrapper for log returns
#[pyfunction]
fn py_log_returns(prices: Vec<f64>, horizon: usize) -> PyResult<Vec<f64>> {
    Ok(crate::returns::log_returns(&prices, horizon))
}

/// Python-accessible wrapper for simple returns
#[pyfunction]
fn py_simple_returns(prices: Vec<f64>, horizon: usize) -> PyResult<Vec<f64>> {
    Ok(crate::returns::simple_returns(&prices, horizon))
}

/// Python-accessible wrapper for realized volatility
#[pyfunction]
fn py_realized_volatility(returns: Vec<f64>, window: usize) -> PyResult<Vec<f64>> {
    Ok(crate::volatility::realized_volatility(&returns, window))
}

/// Python-accessible wrapper for EWMA volatility
#[pyfunction]
fn py_ewma_volatility(returns: Vec<f64>, lambda: f64) -> PyResult<Vec<f64>> {
    Ok(crate::volatility::ewma_volatility(&returns, lambda))
}

/// Python-accessible wrapper for EMA
#[pyfunction]
fn py_ema(prices: Vec<f64>, period: usize) -> PyResult<Vec<f64>> {
    Ok(crate::trend::ema(&prices, period))
}

/// Python-accessible wrapper for MACD
#[pyfunction]
fn py_macd(
    prices: Vec<f64>,
    fast: usize,
    slow: usize,
    signal: usize,
) -> PyResult<(Vec<f64>, Vec<f64>, Vec<f64>)> {
    Ok(crate::trend::macd(&prices, fast, slow, signal))
}

/// Python-accessible wrapper for RSI
#[pyfunction]
fn py_rsi(prices: Vec<f64>, period: usize) -> PyResult<Vec<f64>> {
    Ok(crate::mean_reversion::rsi(&prices, period))
}

/// Python-accessible wrapper for Bollinger Bands
#[pyfunction]
fn py_bollinger_bands(
    prices: Vec<f64>,
    period: usize,
    std_mult: f64,
) -> PyResult<(Vec<f64>, Vec<f64>, Vec<f64>)> {
    Ok(crate::mean_reversion::bollinger_bands(
        &prices, period, std_mult,
    ))
}

/// Python module definition
#[pymodule]
fn cryptobot_features(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    m.add_function(wrap_pyfunction!(py_log_returns, m)?)?;
    m.add_function(wrap_pyfunction!(py_simple_returns, m)?)?;
    m.add_function(wrap_pyfunction!(py_realized_volatility, m)?)?;
    m.add_function(wrap_pyfunction!(py_ewma_volatility, m)?)?;
    m.add_function(wrap_pyfunction!(py_ema, m)?)?;
    m.add_function(wrap_pyfunction!(py_macd, m)?)?;
    m.add_function(wrap_pyfunction!(py_rsi, m)?)?;
    m.add_function(wrap_pyfunction!(py_bollinger_bands, m)?)?;
    Ok(())
}
