//! Kill switch: halt trading on drawdown / daily-loss breaches.

/// Reason a kill switch tripped.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum KillReason {
    None,
    MaxDrawdown,
    MaxDailyLoss,
    Manual,
}

/// Kill-switch state machine. Latches: once tripped it stays tripped until reset.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct KillSwitch {
    pub active: bool,
    pub reason: KillReason,
    pub max_drawdown_pct: f64,
    pub max_daily_loss_pct: f64,
    pub peak_equity: f64,
    pub day_start_equity: f64,
}

impl Default for KillSwitch {
    fn default() -> Self {
        KillSwitch {
            active: false,
            reason: KillReason::None,
            max_drawdown_pct: 0.20,
            max_daily_loss_pct: 0.05,
            peak_equity: f64::NAN,
            day_start_equity: f64::NAN,
        }
    }
}

impl KillSwitch {
    /// Update with the latest equity and (optionally) a fresh day-start equity.
    /// Returns the kill-switch state after the update.
    pub fn update(&mut self, equity: f64, day_start_equity: Option<f64>) -> (bool, KillReason) {
        if self.active {
            return (true, self.reason);
        }
        if !equity.is_finite() || equity <= 0.0 {
            return (self.active, self.reason);
        }
        if self.peak_equity.is_nan() || equity > self.peak_equity {
            self.peak_equity = equity;
        }
        if let Some(d) = day_start_equity {
            if d > 0.0 {
                self.day_start_equity = d;
            }
        }
        if self.peak_equity > 0.0 {
            let dd = (self.peak_equity - equity) / self.peak_equity;
            if dd >= self.max_drawdown_pct {
                self.active = true;
                self.reason = KillReason::MaxDrawdown;
                return (true, self.reason);
            }
        }
        if self.day_start_equity > 0.0 {
            let day_loss = (self.day_start_equity - equity) / self.day_start_equity;
            if day_loss >= self.max_daily_loss_pct {
                self.active = true;
                self.reason = KillReason::MaxDailyLoss;
                return (true, self.reason);
            }
        }
        (false, KillReason::None)
    }

    pub fn trip_manual(&mut self) {
        self.active = true;
        self.reason = KillReason::Manual;
    }

    pub fn reset(&mut self) {
        self.active = false;
        self.reason = KillReason::None;
        self.peak_equity = f64::NAN;
        self.day_start_equity = f64::NAN;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn new_switch_inactive() {
        let ks = KillSwitch::default();
        assert!(!ks.active);
        assert_eq!(ks.reason, KillReason::None);
    }

    #[test]
    fn trips_on_drawdown() {
        let mut ks = KillSwitch {
            peak_equity: 1000.0,
            ..KillSwitch::default()
        };
        let (active, reason) = ks.update(700.0, Some(1000.0));
        assert!(active);
        assert_eq!(reason, KillReason::MaxDrawdown);
    }

    #[test]
    fn latches_once_tripped() {
        let mut ks = KillSwitch {
            peak_equity: 1000.0,
            ..KillSwitch::default()
        };
        ks.update(700.0, Some(1000.0));
        let (active, reason) = ks.update(2000.0, Some(2000.0));
        assert!(active);
        assert_eq!(reason, KillReason::MaxDrawdown); // still reports original reason
    }

    #[test]
    fn trips_on_daily_loss() {
        let mut ks = KillSwitch {
            peak_equity: 1000.0,
            ..KillSwitch::default()
        };
        let (active, reason) = ks.update(970.0, Some(1000.0));
        // 3% daily loss < 5% threshold -> not tripped.
        assert!(!active);
        assert_eq!(reason, KillReason::None);
        let (active, reason) = ks.update(940.0, Some(1000.0));
        assert!(active);
        assert_eq!(reason, KillReason::MaxDailyLoss);
    }

    #[test]
    fn manual_trip_and_reset() {
        let mut ks = KillSwitch::default();
        ks.trip_manual();
        assert!(ks.active);
        assert_eq!(ks.reason, KillReason::Manual);
        ks.reset();
        assert!(!ks.active);
    }
}
