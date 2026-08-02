//! Cryptobot Statistical Validation
//! 
//! Statistical validation: PBO, Monte Carlo, deflated Sharpe, walk-forward analysis.
//! 
//! Provides rigorous statistical testing for strategy validation including
//! probabilistic backtest overfitting (PBO), Monte Carlo permutation testing,
//! deflated Sharpe ratio, and walk-forward analysis with embargo.

pub mod pbo;
pub mod monte_carlo;
pub mod deflated_sharpe;
pub mod walk_forward;
pub mod sensitivity;

#[cfg(test)]
mod tests {
    #[test]
    fn placeholder() {
        assert_eq!(2 + 2, 4);
    }
}