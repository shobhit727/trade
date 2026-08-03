//! Fill Simulator - Realistic fill modeling

use rust_decimal::Decimal;

#[derive(Debug, Clone)]
pub struct Fill {
    pub timestamp: i64,
    pub symbol: String,
    pub side: String,
    pub quantity: Decimal,
    pub price: Decimal,
    pub commission: Decimal,
}

pub struct FillSimulator {
    pub commission_bps: f64,
    pub slippage_bps: f64,
}

impl FillSimulator {
    pub fn new(commission_bps: f64, slippage_bps: f64) -> Self {
        Self {
            commission_bps,
            slippage_bps,
        }
    }

    pub fn simulate_fill(&self, symbol: &str, side: &str, quantity: f64, mid_price: f64) -> Fill {
        let qty = Decimal::from_f64_retain(quantity).unwrap_or_default();
        let price = Decimal::from_f64_retain(mid_price).unwrap_or_default();
        let slippage = price * Decimal::from_f64_retain(self.slippage_bps / 10000.0).unwrap_or_default();
        let fill_price = if side == "BUY" { price + slippage } else { price - slippage };
        let commission = fill_price * qty
            * Decimal::from_f64_retain(self.commission_bps / 10000.0).unwrap_or_default();
        Fill {
            timestamp: chrono::Utc::now().timestamp_millis(),
            symbol: symbol.to_string(),
            side: side.to_string(),
            quantity: qty,
            price: fill_price,
            commission,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_fill_simulator() {
        let sim = FillSimulator::new(1.0, 5.0);
        let fill = sim.simulate_fill("BTCUSDT", "BUY", 0.001, 50000.0);
        assert!(fill.commission > Decimal::ZERO);
        assert!(fill.price > Decimal::from(50000));
    }
}