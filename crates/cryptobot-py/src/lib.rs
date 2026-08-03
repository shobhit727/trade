//! Cryptobot Python Bindings (PyO3)
//!
//! Top-level Python module that exposes Rust crates as submodules:
//! - cryptobot_py.features: feature engineering (returns, volatility, RSI, MACD, etc.)
//! - cryptobot_py.risk: risk math (Kelly, position sizing, correlation)
//! - cryptobot_py.orderbook: order book operations, VPIN
//! - cryptobot_py.backtest: performance metrics, fill simulator
//!
//! Build with: maturin develop --release

use pyo3::prelude::*;

/// Re-export submodule bindings
mod features;
mod risk;
mod orderbook;
mod backtest;

#[pymodule]
fn cryptobot_py(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    m.add("__all__", vec!["features", "risk", "orderbook", "backtest"])?;
    Ok(())
}