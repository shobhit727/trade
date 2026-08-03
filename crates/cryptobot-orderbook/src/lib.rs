//! Cryptobot Order Book Operations
//!
//! Order book operations, VPIN, microstructure analysis.

pub mod book;
pub mod vpin;

#[cfg(feature = "python")]
pub mod python_bindings;

#[cfg(test)]
mod tests {
    #[test]
    fn placeholder() {
        assert_eq!(2 + 2, 4);
    }
}