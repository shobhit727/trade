//! Cryptobot Feature Engineering
//!
//! High-performance feature computation for ML models.

pub mod returns;
pub mod volatility;
pub mod trend;
pub mod mean_reversion;

#[cfg(feature = "python")]
pub mod python_bindings;

#[cfg(test)]
mod tests {
    #[test]
    fn placeholder() {
        assert_eq!(2 + 2, 4);
    }
}