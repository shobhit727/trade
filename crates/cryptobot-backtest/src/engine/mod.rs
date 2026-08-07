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
        let mut equity_curve: Vec<f64> = Vec::with_capacity(events.len() + 1);
        let initial = self.config.initial_equity;
        equity_curve.push(initial);
        for event in events {
            self.process_event(event)?;
            equity_curve.push(self.portfolio.equity().to_string().parse().unwrap_or(0.0));
        }

        let final_equity = self.portfolio.equity();
        let total_return =
            (final_equity.to_string().parse::<f64>().unwrap_or(0.0) / initial) - 1.0;

        // Per-interval returns from the equity curve.
        let returns: Vec<f64> = equity_curve
            .windows(2)
            .map(|w| {
                let (a, b) = (w[0], w[1]);
                if a > 0.0 {
                    (b - a) / a
                } else {
                    0.0
                }
            })
            .collect();
        let metrics = PerformanceMetrics::calculate(&returns);

        // Max drawdown from equity curve (peak-to-trough).
        let max_drawdown = equity_curve
            .iter()
            .fold((0.0_f64, 0.0_f64, 0.0_f64), |(peak, max_dd, _prev), &eq| {
                let new_peak = peak.max(eq);
                let dd = if new_peak > 0.0 { (new_peak - eq) / new_peak } else { 0.0 };
                (new_peak, max_dd.max(dd), eq)
            })
            .1;

        Ok(BacktestResult {
            final_equity: final_equity.to_string().parse().unwrap_or(0.0),
            total_return,
            sharpe_ratio: metrics.sharpe_ratio,
            max_drawdown,
            trades: self.trade_records.clone(),
            metrics,
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

    #[test]
    fn test_run_with_no_events_is_flat() {
        let config = BacktestConfig {
            initial_equity: 10000.0,
            commission_bps: 1.0,
            slippage_bps: 5.0,
        };
        let mut engine = BacktestEngine::new(config);
        let result = engine.run(vec![]).unwrap();
        assert!((result.final_equity - 10000.0).abs() < 1e-9);
        assert!(result.max_drawdown >= 0.0);
        assert_eq!(result.trades.len(), 0);
    }
}