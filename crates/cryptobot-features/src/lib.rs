//! Cryptobot Feature Engineering
//! 
//! High-performance feature computation for ML models.
//! 
//! Provides 100+ features including returns, volatility, trend, mean reversion,
//! microstructure, volume, funding, regime, cross-asset, on-chain, and alternative data.

pub mod returns;
pub mod volatility;
pub mod trend;
pub mod mean_reversion;
pub mod microstructure;
pub mod volume;
pub mod funding;
pub mod regime;
pub mod cross_asset;
pub mod on_chain;
pub mod alternative;

#[cfg(test)]
mod tests {
    #[test]
    fn placeholder() {
        assert_eq!(2 + 2, 4);
    }
}