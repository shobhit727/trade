//! PyO3 bindings for cryptobot-backtest

use pyo3::prelude::*;

/// Python wrapper for PerformanceMetrics
#[pyclass]
#[derive(Clone, Debug)]
struct PyPerformanceMetrics {
    inner: crate::metrics::PerformanceMetrics,
}

#[pymethods]
impl PyPerformanceMetrics {
    #[new]
    fn new(returns: Vec<f64>) -> Self {
        Self {
            inner: crate::metrics::PerformanceMetrics::calculate(&returns),
        }
    }

    #[getter]
    fn sharpe_ratio(&self) -> f64 {
        self.inner.sharpe_ratio
    }

    #[getter]
    fn sortino_ratio(&self) -> f64 {
        self.inner.sortino_ratio
    }

    #[getter]
    fn max_drawdown(&self) -> f64 {
        self.inner.max_drawdown
    }

    #[getter]
    fn profit_factor(&self) -> f64 {
        self.inner.profit_factor
    }

    #[getter]
    fn win_rate(&self) -> f64 {
        self.inner.win_rate
    }

    #[getter]
    fn total_trades(&self) -> usize {
        self.inner.total_trades
    }
}

/// Calculate metrics from returns
#[pyfunction]
fn py_calculate_metrics(returns: Vec<f64>) -> PyResult<PyPerformanceMetrics> {
    Ok(PyPerformanceMetrics {
        inner: crate::metrics::PerformanceMetrics::calculate(&returns),
    })
}

/// Create fill simulator and simulate a fill
#[pyfunction]
fn py_simulate_fill(
    commission_bps: f64,
    slippage_bps: f64,
    symbol: String,
    side: String,
    quantity: f64,
    mid_price: f64,
) -> PyResult<(f64, f64, f64)> {
    let sim = crate::simulator::FillSimulator::new(commission_bps, slippage_bps);
    let fill = sim.simulate_fill(&symbol, &side, quantity, mid_price);
    let price: f64 = fill.price.to_string().parse().unwrap_or(0.0);
    let qty: f64 = fill.quantity.to_string().parse().unwrap_or(0.0);
    let comm: f64 = fill.commission.to_string().parse().unwrap_or(0.0);
    Ok((price, qty, comm))
}

#[pymodule]
fn cryptobot_backtest(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    m.add_class::<PyPerformanceMetrics>()?;
    m.add_function(wrap_pyfunction!(py_calculate_metrics, m)?)?;
    m.add_function(wrap_pyfunction!(py_simulate_fill, m)?)?;
    Ok(())
}
