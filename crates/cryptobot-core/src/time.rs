//! Time primitives: clock, intervals, scheduling

use chrono::{DateTime, Duration, Utc};

pub fn now() -> DateTime<Utc> {
    Utc::now()
}

pub fn timestamp_millis() -> i64 {
    Utc::now().timestamp_millis()
}

pub fn parse_iso(s: &str) -> Result<DateTime<Utc>, chrono::ParseError> {
    DateTime::parse_from_rfc3339(s).map(|dt| dt.with_timezone(&Utc))
}

pub fn add_minutes(ts: DateTime<Utc>, minutes: i64) -> DateTime<Utc> {
    ts + Duration::minutes(minutes)
}

pub fn add_hours(ts: DateTime<Utc>, hours: i64) -> DateTime<Utc> {
    ts + Duration::hours(hours)
}

pub fn diff_seconds(a: DateTime<Utc>, b: DateTime<Utc>) -> i64 {
    (a - b).num_seconds()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_add_minutes() {
        let t = Utc::now();
        let t2 = add_minutes(t, 60);
        assert_eq!((t2 - t).num_minutes(), 60);
    }

    #[test]
    fn test_diff() {
        let t = Utc::now();
        let t2 = add_hours(t, 1);
        assert_eq!(diff_seconds(t2, t), 3600);
    }
}
