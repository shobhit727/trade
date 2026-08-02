//! Cryptobot Backtest Engine
//! 
//! Event-driven backtester, fill simulator, and performance metrics.
//! 
//! This crate provides the Rust-native implementation of the backtesting engine
//! for high-performance historical simulation.

pub mod engine;
pub mod simulator;
pub mod metrics;
pub mod validation;
pub mod reporting;
pub mod runner;

#[cfg(test)]
mod tests {
    #[test]
    fn placeholder() {
        assert_eq!(2 + 2, 4);
    }
}