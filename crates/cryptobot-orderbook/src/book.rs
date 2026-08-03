//! Order book data structures and operations

use std::collections::BTreeMap;

#[derive(Debug, Clone, Default)]
pub struct OrderBook {
    pub bids: BTreeMap<i64, f64>, // price -> size
    pub asks: BTreeMap<i64, f64>,
}

impl OrderBook {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn best_bid(&self) -> Option<(i64, f64)> {
        self.bids.iter().rev().next().map(|(p, s)| (*p, *s))
    }

    pub fn best_ask(&self) -> Option<(i64, f64)> {
        self.asks.iter().next().map(|(p, s)| (*p, *s))
    }

    pub fn mid_price(&self) -> Option<f64> {
        let bid = self.best_bid()?.0 as f64;
        let ask = self.best_ask()?.0 as f64;
        Some((bid + ask) / 2.0)
    }

    pub fn spread(&self) -> Option<f64> {
        let bid = self.best_bid()?.0 as f64;
        let ask = self.best_ask()?.0 as f64;
        Some(ask - bid)
    }

    pub fn update_bid(&mut self, price: i64, size: f64) {
        if size == 0.0 {
            self.bids.remove(&price);
        } else {
            self.bids.insert(price, size);
        }
    }

    pub fn update_ask(&mut self, price: i64, size: f64) {
        if size == 0.0 {
            self.asks.remove(&price);
        } else {
            self.asks.insert(price, size);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_orderbook() {
        let mut book = OrderBook::new();
        book.update_bid(50000, 1.0);
        book.update_ask(50100, 1.0);
        assert_eq!(book.best_bid(), Some((50000, 1.0)));
        assert_eq!(book.best_ask(), Some((50100, 1.0)));
        assert_eq!(book.mid_price(), Some(50050.0));
        assert_eq!(book.spread(), Some(100.0));
    }
}
