//! Cryptobot Risk Management
//!
//! Risk math: Kelly criterion, CVaR, HRP portfolio optimization, correlation analysis.

pub mod sizing;
pub mod correlation;

#[cfg(feature = "python")]
pub mod python_bindings;

#[cfg(test)]
mod tests {
    #[test]
    fn placeholder() {
        assert_eq!(2 + 2, 4);
    }
}