//! Cryptobot Python Bindings (PyO3)
//! 
//! PyO3 bindings for the Rust performance layer.
//! 
//! Exposes Rust crates to Python via maturin:
//! - cryptobot_core: shared types, events, math, time
//! - cryptobot_backtest: engine, simulator, metrics
//! - cryptobot_features: feature computation (100+ features)
//! - cryptobot_risk: Kelly, CVaR, HRP, correlation
//! - cryptobot_stats: PBO, Monte Carlo, deflated Sharpe
//! - cryptobot_orderbook: book ops, VPIN, microstructure

use pyo3::prelude::*;

#[pymodule]
fn cryptobot_py(m: &Bound<'_, PyModule>) -> PyResult<()> {
    // Core types and utilities
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    
    // Re-export core types
    m.add_class::<cryptobot_core::Event>()?;
    m.add_class::<cryptobot_core::Clock>()?;
    m.add_class::<cryptobot_core::Portfolio>()?;
    
    Ok(())
}

/// Python-accessible wrapper for core Event
#[pyclass]
#[derive(Clone, Debug)]
struct PyEvent {
    inner: cryptobot_core::Event,
}

#[pymethods]
impl PyEvent {
    #[new]
    fn new(event_type: String, payload: String) -> Self {
        Self {
            inner: cryptobot_core::Event::new(event_type, payload),
        }
    }
    
    #[getter]
    fn event_type(&self) -> String {
        self.inner.event_type.clone()
    }
    
    #[getter]
    fn payload(&self) -> String {
        self.inner.payload.clone()
    }
}

/// Python-accessible wrapper for core Clock
#[pyclass]
#[derive(Clone, Debug)]
struct PyClock {
    inner: cryptobot_core::Clock,
}

#[pymethods]
impl PyClock {
    #[new]
    fn new(mode: String) -> Self {
        Self {
            inner: cryptobot_core::Clock::new(mode),
        }
    }
    
    fn now(&self) -> String {
        self.inner.now().to_string()
    }
}

/// Python-accessible wrapper for Portfolio
#[pyclass]
#[derive(Clone, Debug)]
struct PyPortfolio {
    inner: cryptobot_core::Portfolio,
}

#[pymethods]
impl PyPortfolio {
    #[new]
    fn new(initial_equity: f64) -> Self {
        Self {
            inner: cryptobot_core::Portfolio::new(rust_decimal_macros::dec!(initial_equity)),
        }
    }
    
    fn equity(&self) -> f64 {
        self.inner.equity().to_string().parse().unwrap_or(0.0)
    }
    
    fn update_equity(&mut self, new_equity: f64) {
        self.inner.update_equity(rust_decimal_macros::dec!(new_equity));
    }
}

#[cfg(test)]
mod tests {
    #[test]
    fn placeholder() {
        assert_eq!(2 + 2, 4);
    }
}