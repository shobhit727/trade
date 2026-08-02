//! Backtest Engine - Event-driven simulation

use crate::simulator::FillSimulator;
use crate::metrics::PerformanceMetrics;
use cryptobot_core::{Event, Portfolio, Clock};
use anyhow::Result;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BacktestConfig {
    pub initial_equity: f64,
    pub commission_bps: f64,
    pub slippage_bps: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BacktestResult {
    pub final_equity: f64,
    pub total_return: f64,
    pub sharpe_ratio: f64,
    pub max_drawdown: f64,
    pub trades: Vec<TradeRecord>,
    pub metrics: PerformanceMetrics,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TradeRecord {
    pub timestamp: i64,
    pub symbol: String,
    pub side: String,
    pub quantity: f64,
    pub price: f64,
    pub pnl: f64,
}

pub struct BacktestEngine {
    config: BacktestConfig,
    portfolio: Portfolio,
    simulator: FillSimulator,
    clock: Clock,
    trade_records: Vec<TradeRecord>,
}

impl BacktestEngine {
    pub fn new(config: BacktestConfig) -> Self {
        let initial_equity = rust_decimal_macros::dec!(config.initial_equity);
        Self {
            config,
            portfolio: Portfolio::new(initial_equity),
            simulator: FillSimulator::new(config.commission_bps, config.slippage_bps),
            clock: Clock::simulated(),
            trade_records: Vec::new(),
        }
    }
    
    pub fn run(&mut self, events: Vec<Event>) -> Result<BacktestResult> {
        for event in events {
            self.process_event(event)?;
        }
        
        let final_equity = self.portfolio.equity();
        let total_return = (final_equity / rust_decimal_macros::dec!(self.config.initial_equity) - rust_decimal_macros::dec!(1.0)).to_string().parse().unwrap_or(0.0);
        
        Ok(BacktestResult {
            final_equity: final_equity.to_string().parse().unwrap_or(0.0),
            total_return,
            sharpe_ratio: 0.0, // TODO: compute from returns
            max_drawdown: 0.0, // TODO: compute from equity curve
            trades: self.trade_records.clone(),
            metrics: PerformanceMetrics::default(),
        })
    }
    
    fn process_event(&mut self, event: Event) -> Result<()> {
        // Process event through simulator and update portfolio
        match event.event_type.as_str() {
            "ORDER_NEW" => {
                // Simulate fill
                let fill = self.simulator.simulate_fill(&event)?;
                self.portfolio.apply_fill(&fill)?;
                self.trade_records.push(TradeRecord {
                    timestamp: fill.timestamp,
                    symbol: fill.symbol,
                    side: fill.side,
                    quantity: fill.quantity,
                    price: fill.price,
                    pnl: 0.0, // Will be updated on exit
                });
            }
            _ => {}
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_engine_creation() {
        let config = BacktestConfig {
            initial_equity: 10000.0,
            commission_bps: 1.0,
            slippage_bps: 5.0,
        };
        let engine = BacktestEngine::new(config);
        assert_eq!(engine.config.initial_equity, 10000.0);
    }
}