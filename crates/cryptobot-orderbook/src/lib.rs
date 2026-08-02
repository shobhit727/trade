//! Cryptobot Order Book Operations
//! 
//! Order book operations, VPIN, microstructure analysis.
//! 
//! Provides high-performance order book data structures and microstructure metrics
//! including VPIN (Volume-synchronized Probability of Informed Trading),
//! Kyle's lambda, order flow toxicity, queue position, and hidden order detection.

pub mod book;
pub mod vpin;
pub mod microstructure;
pub mod queue_position;
pub mod hidden_orders;
pub mod liquidity;

#[cfg(test)]
mod tests {
    #[test]
    fn placeholder() {
        assert_eq!(2 + 2, 4);
    }
}