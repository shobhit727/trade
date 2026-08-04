//! Cryptobot core: shared types, events, math, time primitives.

pub mod math;
pub mod time;
pub mod types;

pub use math::*;
pub use time::*;
pub use types::*;

pub fn placeholder() -> &'static str {
    "cryptobot-core"
}

#[cfg(test)]
mod tests {
    use super::*;
    use rust_decimal::Decimal;

    #[test]
    fn placeholder_returns_name() {
        assert_eq!(placeholder(), "cryptobot-core");
    }

    #[test]
    fn test_ohlcv_bar_creation() {
        let bar = OhlcvBar::new(50000.0, 50100.0, 49900.0, 50050.0, 1000.0);
        assert_eq!(bar.open, Decimal::from(50000));
        assert!(bar.is_valid());
    }

    #[test]
    fn test_ohlcv_bar_validation() {
        let invalid = OhlcvBar::new(100.0, 50.0, 90.0, 95.0, 100.0);
        assert!(!invalid.is_valid()); // high < open
    }
}
