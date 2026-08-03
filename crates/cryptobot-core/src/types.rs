//! Core types: OHLCV bars, positions, events, etc.

use chrono::{DateTime, Utc};
use rust_decimal::Decimal;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct OhlcvBar {
    pub timestamp: DateTime<Utc>,
    pub open: Decimal,
    pub high: Decimal,
    pub low: Decimal,
    pub close: Decimal,
    pub volume: Decimal,
}

impl OhlcvBar {
    pub fn new(open: f64, high: f64, low: f64, close: f64, volume: f64) -> Self {
        Self {
            timestamp: Utc::now(),
            open: Decimal::from_f64_retain(open).unwrap_or_default(),
            high: Decimal::from_f64_retain(high).unwrap_or_default(),
            low: Decimal::from_f64_retain(low).unwrap_or_default(),
            close: Decimal::from_f64_retain(close).unwrap_or_default(),
            volume: Decimal::from_f64_retain(volume).unwrap_or_default(),
        }
    }

    pub fn with_timestamp(mut self, ts: DateTime<Utc>) -> Self {
        self.timestamp = ts;
        self
    }

    pub fn is_valid(&self) -> bool {
        self.high >= self.open
            && self.high >= self.close
            && self.high >= self.low
            && self.low <= self.open
            && self.low <= self.close
            && self.volume >= Decimal::ZERO
    }

    pub fn typical_price(&self) -> Decimal {
        (self.high + self.low + self.close) / Decimal::from(3)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_typical_price() {
        let bar = OhlcvBar::new(100.0, 110.0, 95.0, 105.0, 1000.0);
        let tp = bar.typical_price();
        assert_eq!(tp, Decimal::from(310) / Decimal::from(3));
    }
}
