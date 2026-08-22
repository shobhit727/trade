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

        // Downside deviation over ALL observations vs zero MAR (issue #40):
        // sqrt(mean(min(r, 0)^2)) — the previous losses-only std inflated Sortino ~2-4x.
        let downside_dev = (returns.iter().map(|r| r.min(0.0).powi(2)).sum::<f64>()
            / returns.len() as f64)
            .sqrt();

        let sharpe = if std_dev > 0.0 { mean / std_dev } else { 0.0 };
        let sortino = if downside_dev > 0.0 {
            mean / downside_dev
        } else {
            0.0
        };

        // Max drawdown on the cumulative-return curve, relative to the running peak
        // (issue #40): the old `peak.abs().max(1.0)` divisor understated drawdowns for
        // any decimal-scale series whose peak stayed below 1.0.
        let mut cumulative = 0.0;
        let mut peak = f64::NEG_INFINITY;
        let mut max_dd = 0.0;
        for r in returns {
            cumulative += r;
            if cumulative > peak {
                peak = cumulative;
            }
            if peak > 0.0 {
                let dd = (peak - cumulative) / peak;
                if dd > max_dd {
                    max_dd = dd;
                }
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

    #[test]
    fn test_sortino_uses_full_sample_downside_deviation() {
        // Reference: dd = sqrt(mean(min(r,0)^2)) over ALL returns.
        let returns = vec![0.01, -0.02, 0.03, -0.01];
        let m = PerformanceMetrics::calculate(&returns);
        let mean = returns.iter().sum::<f64>() / 4.0;
        let dd = (returns.iter().map(|r| r.min(0.0).powi(2)).sum::<f64>() / 4.0).sqrt();
        let expected = mean / dd * 252_f64.sqrt();
        assert!((m.sortino_ratio - expected).abs() < 1e-9);
        // The old losses-only formula reported ~7.9 for this series; the correct
        // value is ~3.55.
        assert!(m.sortino_ratio < 5.0, "sortino inflated: {}", m.sortino_ratio);
    }

    #[test]
    fn test_max_drawdown_decimal_scale() {
        // Cumulative curve 0.30 -> 0.15: drawdown from the running peak is
        // 0.15/0.30 = 0.5. The old max(peak,1.0) divisor reported 0.15 here.
        let returns = vec![0.3, -0.15];
        let m = PerformanceMetrics::calculate(&returns);
        assert!((m.max_drawdown - 0.5).abs() < 1e-9, "got {}", m.max_drawdown);
    }
}
