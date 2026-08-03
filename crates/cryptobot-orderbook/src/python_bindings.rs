//! PyO3 bindings for cryptobot-orderbook

use pyo3::prelude::*;

/// Python wrapper for OrderBook
#[pyclass]
struct PyOrderBook {
    inner: crate::book::OrderBook,
}

#[pymethods]
impl PyOrderBook {
    #[new]
    fn new() -> Self {
        Self {
            inner: crate::book::OrderBook::new(),
        }
    }

    fn update_bid(&mut self, price: i64, size: f64) {
        self.inner.update_bid(price, size);
    }

    fn update_ask(&mut self, price: i64, size: f64) {
        self.inner.update_ask(price, size);
    }

    #[getter]
    fn best_bid(&self) -> Option<(i64, f64)> {
        self.inner.best_bid()
    }

    #[getter]
    fn best_ask(&self) -> Option<(i64, f64)> {
        self.inner.best_ask()
    }

    #[getter]
    fn mid_price(&self) -> Option<f64> {
        self.inner.mid_price()
    }

    #[getter]
    fn spread(&self) -> Option<f64> {
        self.inner.spread()
    }
}

/// VPIN from volume buckets
#[pyfunction]
fn py_vpin(buckets: Vec<f64>) -> PyResult<f64> {
    Ok(crate::vpin::vpin(&buckets))
}

#[pymodule]
fn cryptobot_orderbook(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    m.add_class::<PyOrderBook>()?;
    m.add_function(wrap_pyfunction!(py_vpin, m)?)?;
    Ok(())
}
