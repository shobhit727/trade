//! Cryptobot Python Bindings (PyO3)
//!
//! Top-level Python module that exposes Rust crates as submodules:
//! - cryptobot_rs.features: feature engineering (returns, volatility, RSI, MACD, etc.)
//! - cryptobot_rs.risk: risk math (Kelly, position sizing, correlation)
//! - cryptobot_rs.orderbook: order book operations, VPIN
//! - cryptobot_rs.backtest: performance metrics, fill simulator
//!
//! Build with: maturin develop --release

use pyo3::prelude::*;

mod backtest;
/// Re-export submodule bindings
mod features;
mod orderbook;
mod risk;

#[pymodule]
fn cryptobot_rs(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    m.add("__all__", vec!["features", "risk", "orderbook", "backtest"])?;

    let features = PyModule::new(m.py(), "features")?;
    features::cryptobot_features(&features)?;
    m.add_submodule(&features)?;

    let risk = PyModule::new(m.py(), "risk")?;
    risk::cryptobot_risk(&risk)?;
    m.add_submodule(&risk)?;

    let orderbook = PyModule::new(m.py(), "orderbook")?;
    orderbook::cryptobot_orderbook(&orderbook)?;
    m.add_submodule(&orderbook)?;

    let backtest = PyModule::new(m.py(), "backtest")?;
    backtest::cryptobot_backtest(&backtest)?;
    m.add_submodule(&backtest)?;
    Ok(())
}
