//! Performance Metrics - Sharpe, Sortino, Drawdown, Profit Factor

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct PerformanceMetrics {
    pub sharpe_ratio: f64,
    pub sortino_ratio: f64,
    pub max_drawdown: f64,
    pub profit_factor: f64,
    pub win_rate: f64,
    pub total_trades: usize,
    pub winning_trades: usize,
    pub losing_trades: usize,
    pub avg_win: f64,
    pub avg_loss: f64,
}

impl PerformanceMetrics {
    pub fn calculate(returns: &[f64]) -> Self {
        if returns.is_empty() {
            return Self::default();
        }

        let mean = returns.iter().sum::<f64>() / returns.len() as f64;
        let variance =
            returns.iter().map(|r| (r - mean).powi(2)).sum::<f64>() / returns.len() as f64;
        let std_dev = variance.sqrt();

        let downside_returns: Vec<f64> = returns.iter().filter(|&&r| r < 0.0).cloned().collect();
        let downside_std = if downside_returns.is_empty() {
            1.0
        } else {
            let downside_mean =
                downside_returns.iter().sum::<f64>() / downside_returns.len() as f64;
            let downside_var = downside_returns
                .iter()
                .map(|r| (r - downside_mean).powi(2))
                .sum::<f64>()
                / downside_returns.len() as f64;
            downside_var.sqrt()
        };

        let sharpe = if std_dev > 0.0 { mean / std_dev } else { 0.0 };
        let sortino = if downside_std > 0.0 {
            mean / downside_std
        } else {
            0.0
        };

        // Max drawdown
        let mut peak = 0.0;
        let mut max_dd = 0.0;
        let mut cumulative = 0.0;
        for r in returns {
            cumulative += r;
            if cumulative > peak {
                peak = cumulative;
            }
            let dd = (peak - cumulative).abs() / peak.abs().max(1.0);
            if dd > max_dd {
                max_dd = dd;
            }
        }

        let wins: Vec<f64> = returns.iter().filter(|&&r| r > 0.0).cloned().collect();
        let losses: Vec<f64> = returns.iter().filter(|&&r| r < 0.0).cloned().collect();

        let profit_factor = if !losses.is_empty() {
            wins.iter().sum::<f64>() / losses.iter().sum::<f64>().abs()
        } else {
            f64::INFINITY
        };

        Self {
            sharpe_ratio: sharpe * 252_f64.sqrt(),
            sortino_ratio: sortino * 252_f64.sqrt(),
            max_drawdown: max_dd,
            profit_factor,
            win_rate: wins.len() as f64 / returns.len() as f64,
            total_trades: returns.len(),
            winning_trades: wins.len(),
            losing_trades: losses.len(),
            avg_win: if !wins.is_empty() {
                wins.iter().sum::<f64>() / wins.len() as f64
            } else {
                0.0
            },
            avg_loss: if !losses.is_empty() {
                losses.iter().sum::<f64>() / losses.len() as f64
            } else {
                0.0
            },
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_metrics() {
        let returns = vec![0.01, -0.005, 0.02, -0.01, 0.015];
        let m = PerformanceMetrics::calculate(&returns);
        assert_eq!(m.total_trades, 5);
        assert!(m.sharpe_ratio >= 0.0);
    }
}
