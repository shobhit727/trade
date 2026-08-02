//! Reporting - HTML Tearsheet Generation

use crate::metrics::PerformanceMetrics;
use crate::validation::ValidationReport;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TearsheetData {
    pub strategy_name: String,
    pub backtest_result: BacktestSummary,
    pub metrics: PerformanceMetrics,
    pub validation: ValidationReport,
    pub equity_curve: Vec<f64>,
    pub drawdown_curve: Vec<f64>,
    pub monthly_returns: Vec<f64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BacktestSummary {
    pub start_date: String,
    pub end_date: String,
    pub initial_equity: f64,
    pub final_equity: f64,
    pub total_return: f64,
    pub annualized_return: f64,
    pub volatility: f64,
    pub total_trades: usize,
}

pub fn generate_html_tearsheet(data: &TearsheetData) -> String {
    format!(
        r#"<!DOCTYPE html>
<html>
<head>
    <title>{} - Tearsheet</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; }}
        .metric {{ display: inline-block; margin: 10px; padding: 15px; background: #f5f5f5; border-radius: 5px; }}
        .metric h3 {{ margin: 0; font-size: 14px; color: #666; }}
        .metric .value {{ font-size: 24px; font-weight: bold; color: #333; }}
        .section {{ margin: 30px 0; }}
    </style>
</head>
<body>
    <h1>{} - Strategy Tearsheet</h1>
    <div class="section">
        <h2>Performance Metrics</h2>
        <div class="metric"><h3>Sharpe Ratio</h3><div class="value">{:.2}</div></div>
        <div class="metric"><h3>Sortino Ratio</h3><div class="value">{:.2}</div></div>
        <div class="metric"><h3>Max Drawdown</h3><div class="value">{:.2}%</div></div>
        <div class="metric"><h3>Profit Factor</h3><div class="value">{:.2}</div></div>
        <div class="metric"><h3>Win Rate</h3><div class="value">{:.1}%</div></div>
        <div class="metric"><h3>Total Trades</h3><div class="value">{}</div></div>
    </div>
    <div class="section">
        <h2>Validation</h2>
        <div class="metric"><h3>Walk-Forward Passed</h3><div class="value">{}</div></div>
        <div class="metric"><h3>Monte Carlo p-value</h3><div class="value">{:.4}</div></div>
        <div class="metric"><h3>Deflated Sharpe</h3><div class="value">{:.2}</div></div>
    </div>
</body>
</html>"#,
        data.strategy_name,
        data.strategy_name,
        data.metrics.sharpe_ratio,
        data.metrics.sortino_ratio,
        data.metrics.max_drawdown * 100.0,
        data.metrics.profit_factor,
        data.metrics.win_rate * 100.0,
        data.metrics.total_trades,
        if data.validation.walk_forward.passed { "Yes" } else { "No" },
        data.validation.monte_carlo.p_value,
        data.validation.deflated_sharpe.deflated_sharpe
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_html_generation() {
        let data = TearsheetData {
            strategy_name: "Test".to_string(),
            backtest_result: BacktestSummary {
                start_date: "2024-01-01".to_string(),
                end_date: "2024-12-31".to_string(),
                initial_equity: 10000.0,
                final_equity: 12000.0,
                total_return: 0.2,
                annualized_return: 0.2,
                volatility: 0.15,
                total_trades: 100,
            },
            metrics: PerformanceMetrics::default(),
            validation: ValidationReport {
                walk_forward: crate::validation::WalkForwardResult { splits: 5, oos_returns: vec![], oos_mean: 0.0, oos_sharpe: 0.0, stability: 0.0, passed: false },
                monte_carlo: crate::validation::MonteCarloResult { permutations: 200, observed_sharpe: 0.0, p_value: 0.5, passed: false },
                deflated_sharpe: crate::validation::DeflatedSharpeResult { observed_sharpe: 0.0, expected_max_sharpe: 0.0, probabilistic_sharpe_ratio: 0.0, deflated_sharpe: 0.0, passed: false },
            },
            equity_curve: vec![],
            drawdown_curve: vec![],
            monthly_returns: vec![],
        };
        let html = generate_html_tearsheet(&data);
        assert!(html.contains("Tearsheet"));
    }
}