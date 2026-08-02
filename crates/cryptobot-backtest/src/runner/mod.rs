//! Runner - End-to-end backtest orchestration

use crate::engine::{BacktestEngine, BacktestConfig, BacktestResult};
use crate::simulator::FillSimulator;
use crate::metrics::PerformanceMetrics;
use crate::validation::run_validation;
use crate::reporting::{generate_html_tearsheet, TearsheetData, BacktestSummary};
use cryptobot_core::{Event, OhlcvBar, Portfolio, Clock};
use anyhow::Result;
use serde::{Deserialize, Serialize};
use std::fs;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RunnerConfig {
    pub backtest: BacktestConfig,
    pub validation_splits: usize,
    pub monte_carlo_permutations: usize,
    pub output_path: Option<String>,
}

pub struct BacktestRunner {
    config: RunnerConfig,
}

impl BacktestRunner {
    pub fn new(config: RunnerConfig) -> Self {
        Self { config }
    }
    
    pub fn run(&self, events: Vec<Event>) -> Result<BacktestResult> {
        let mut engine = BacktestEngine::new(self.config.backtest.clone());
        let result = engine.run(events)?;
        
        // Run validation if enabled
        if self.config.validation_splits > 0 {
            let returns = vec![result.total_return]; // Simplified
            let validation = run_validation(&returns, self.config.validation_splits, self.config.monte_carlo_permutations);
            
            // Generate tearsheet if output path provided
            if let Some(path) = &self.config.output_path {
                let tearsheet = TearsheetData {
                    strategy_name: "Backtest".to_string(),
                    backtest_result: BacktestSummary {
                        start_date: "2024-01-01".to_string(),
                        end_date: "2024-12-31".to_string(),
                        initial_equity: self.config.backtest.initial_equity,
                        final_equity: result.final_equity,
                        total_return: result.total_return,
                        annualized_return: result.total_return,
                        volatility: 0.0,
                        total_trades: result.trades.len(),
                    },
                    metrics: result.metrics.clone(),
                    validation,
                    equity_curve: vec![],
                    drawdown_curve: vec![],
                    monthly_returns: vec![],
                };
                let html = generate_html_tearsheet(&tearsheet);
                fs::write(path, html)?;
            }
        }
        
        Ok(result)
    }
    
    pub fn generate_synthetic_data(
        start: chrono::DateTime<chrono::Utc>,
        n_bars: usize,
        freq_minutes: i64,
        seed: u64,
    ) -> Vec<OhlcvBar> {
        use rand::SeedableRng;
        use rand::Rng;
        use rand::rngs::StdRng;
        
        let mut rng = StdRng::seed_from_u64(seed);
        let mut bars = Vec::with_capacity(n_bars);
        let mut price = 50000.0; // Starting BTC price
        let mut timestamp = start;
        
        for _ in 0..n_bars {
            let change = rng.gen_range(-0.002..0.002);
            price *= 1.0 + change;
            
            let open = price;
            let high = price * (1.0 + rng.gen_range(0.0..0.005));
            let low = price * (1.0 - rng.gen_range(0.0..0.005));
            let close = price * (1.0 + rng.gen_range(-0.001..0.001));
            let volume = rng.gen_range(100.0..10000.0);
            
            bars.push(OhlcvBar {
                timestamp,
                open: rust_decimal_macros::dec!(open),
                high: rust_decimal_macros::dec!(high),
                low: rust_decimal_macros::dec!(low),
                close: rust_decimal_macros::dec!(close),
                volume: rust_decimal_macros::dec!(volume),
            });
            
            timestamp = timestamp + chrono::Duration::minutes(freq_minutes);
        }
        
        bars
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_synthetic_data_generation() {
        let start = chrono::Utc::now();
        let bars = BacktestRunner::generate_synthetic_data(start, 100, 1, 42);
        assert_eq!(bars.len(), 100);
        assert!(bars[0].close > rust_decimal_macros::dec!(0));
    }
}