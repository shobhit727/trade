//! Cryptobot core: shared types, events, math, time primitives.
//!
//! This crate is a scaffolding placeholder. The Python orchestration layer
//! does not currently depend on it via PyO3. Surface will be added as the
//! Rust performance layer (backtest, features, risk, stats, orderbook, py)
//! comes online — see `plan.md` §5b and `PROJECT_MEMORY/26_Audit_2026-07-31_v2.md`.

pub fn placeholder() -> &'static str {
    "cryptobot-core"
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn placeholder_returns_name() {
        assert_eq!(placeholder(), "cryptobot-core");
    }
}
