//! VPIN (Volume-synchronized Probability of Informed Trading)
//!
//! Measures order flow toxicity by bucketing trades by volume.

pub fn vpin(buckets: &[f64]) -> f64 {
    if buckets.len() < 2 {
        return 0.0;
    }
    let mut sum_diff = 0.0;
    let mut sum_vol = 0.0;
    for w in buckets.windows(2) {
        sum_diff += (w[0] - w[1]).abs();
        sum_vol += w[0] + w[1];
    }
    if sum_vol == 0.0 {
        0.0
    } else {
        sum_diff / sum_vol
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_vpin() {
        let buckets = vec![100.0, 110.0, 90.0, 105.0];
        let v = vpin(&buckets);
        assert!(v > 0.0 && v < 1.0);
    }
}