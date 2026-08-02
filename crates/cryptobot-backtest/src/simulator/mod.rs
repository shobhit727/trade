//! Fill Simulator - Realistic fill modeling

use cryptobot_core::{Event, Position, PositionSide};
use anyhow::Result;
use serde::{Deserialize, Serialize};
use rust_decimal::Decimal;
use rust_decimal_macros::dec;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Fill {
    pub timestamp: i64,
    pub symbol: String,
    pub side: String,
    pub quantity: Decimal,
    pub price: Decimal,
    pub commission: Decimal,
}

pub struct FillSimulator {
    commission_bps: f64,
    slippage_bps: f64,
}

impl FillSimulator {
    pub fn new(commission_bps: f64, slippage_bps: f64) -> Self {
        Self {
            commission_bps,
            slippage_bps,
        }
    }
    
    pub fn simulate_fill(&self, event: &Event) -> Result<Fill> {
        // Extract order details from event payload
        // This is a simplified implementation
        let price = Decimal::from(50000); // BTC price placeholder
        let quantity = dec!(0.001);
        let commission = price * quantity * dec!(self.commission_bps) / dec!(10000);
        let slippage = price * dec!(self.slippage_bps) / dec!(10000);
        let fill_price = price + slippage;
        
        Ok(Fill {
            timestamp: chrono::Utc::now().timestamp_millis(),
            symbol: "BTCUSDT".to_string(),
            side: "BUY".to_string(),
            quantity,
            price: fill_price,
            commission,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_fill_simulator() {
        let sim = FillSimulator::new(1.0, 5.0);
        assert_eq!(sim.commission_bps, 1.0);
        assert_eq!(sim.slippage_bps, 5.0);
    }
}