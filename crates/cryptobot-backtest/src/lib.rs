//! Cryptobot Backtest Engine
//!
//! Event-driven backtester, fill simulator, and performance metrics.

pub mod metrics;
pub mod simulator;

#[cfg(feature = "python")]
pub mod python_bindings;

#[cfg(test)]
mod tests {
    #[test]
    fn placeholder() {
        assert_eq!(2 + 2, 4);
    }
}