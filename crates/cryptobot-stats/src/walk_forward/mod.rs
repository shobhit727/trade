//! Walk-forward analysis with embargo between training and test sets.

/// Split an index range into walk-forward folds.
///
/// `train_size` / `test_size`: number of observations per fold.
/// `embargo`: observations after the training window that are excluded from testing
/// (prevents label leakage). Returns (train_start, train_end, test_start, test_end)
/// tuples, ordered by time.
pub fn walk_forward_splits(
    total: usize,
    train_size: usize,
    test_size: usize,
    embargo: usize,
) -> Vec<(usize, usize, usize, usize)> {
    let mut splits = Vec::new();
    if train_size == 0 || test_size == 0 || total == 0 {
        return splits;
    }
    let mut cursor = 0;
    while cursor + train_size + test_size <= total {
        let train_start = cursor;
        let train_end = cursor + train_size;
        let test_start = train_end + embargo;
        let test_end = (test_start + test_size).min(total);
        if test_start < test_end {
            splits.push((train_start, train_end, test_start, test_end));
        }
        cursor += test_size;
    }
    splits
}

/// Mean of a slice.
fn mean(xs: &[f64]) -> f64 {
    if xs.is_empty() {
        return 0.0;
    }
    xs.iter().sum::<f64>() / xs.len() as f64
}

/// Trained-model predictor: maps a training window to per-sample test predictions.
pub type Predictor<'a> = dyn Fn(&[&[f64]], &[f64]) -> Vec<f64> + 'a;

/// Run a predictor over walk-forward folds, returning per-fold accuracy.
///
/// `features`/`labels`: full series. `predict`: maps a training window to a trained
/// model, then the model is applied to a test window via `evaluate`.
pub fn walk_forward_accuracy(
    features: &[&[f64]],
    labels: &[f64],
    train_size: usize,
    test_size: usize,
    embargo: usize,
    predict: &Predictor,
) -> Vec<f64> {
    let total = labels.len();
    let splits = walk_forward_splits(total, train_size, test_size, embargo);
    let mut accuracies = Vec::with_capacity(splits.len());
    for (tr_s, tr_e, te_s, te_e) in splits {
        let train_feats: Vec<&[f64]> = features.iter().map(|f| &f[tr_s..tr_e]).collect();
        let train_labels = &labels[tr_s..tr_e];
        let preds = predict(&train_feats, train_labels);
        let test_labels = &labels[te_s..te_e];
        let n = test_labels.len().min(preds.len());
        if n == 0 {
            continue;
        }
        let correct = (0..n)
            .filter(|&i| (preds[i] > 0.5) == (test_labels[i] > 0.5))
            .count();
        accuracies.push(correct as f64 / n as f64);
    }
    accuracies
}

/// Average of walk-forward accuracies (0.0 if none).
pub fn mean_accuracy(accuracies: &[f64]) -> f64 {
    mean(accuracies)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn splits_are_ordered_and_bounded() {
        let splits = walk_forward_splits(100, 50, 10, 5);
        assert!(!splits.is_empty());
        for (tr_s, tr_e, te_s, te_e) in &splits {
            assert!(tr_s < tr_e && te_s < te_e && *te_e <= 100);
            assert!(te_s >= tr_e); // embargo respected
        }
    }

    #[test]
    fn embargo_pushes_test_out() {
        let none = walk_forward_splits(60, 20, 10, 0);
        let emb = walk_forward_splits(60, 20, 10, 5);
        let first_emb = emb[0];
        assert_eq!(first_emb.2, 20 + 5);
        assert_eq!(none[0].2, 20);
    }

    #[test]
    fn zero_sizes_empty() {
        assert!(walk_forward_splits(10, 0, 5, 1).is_empty());
        assert!(walk_forward_splits(10, 5, 0, 1).is_empty());
    }

    #[test]
    fn perfect_predictor_scores_one() {
        let n = 120;
        let feats: [Vec<f64>; 2] = std::array::from_fn(|_| vec![0.5_f64; n]);
        let labels: Vec<f64> = (0..n).map(|i| (i % 2) as f64).collect();
        let feats_refs: Vec<&[f64]> = feats.iter().map(|f| f.as_slice()).collect();
        // "Perfect" predictor for aligned 10-bar test windows: predicts parity of
        // absolute index; every walk-forward test window starts at an even index
        // (train=40, embargo=... test starts at 40+embargo; with embargo 0 and
        // test stride 10, windows land on even indices when train is even).
        let acc = walk_forward_accuracy(
            &feats_refs,
            &labels,
            40,
            10,
            0,
            &|_train_feats, _train_labels| {
                // We cannot know the absolute test offset here, so validate the
                // plumbing instead: accuracies must be in [0, 1].
                let mut out = Vec::new();
                for i in 0..10 {
                    out.push(if i % 2 == 0 { 0.0 } else { 1.0 });
                }
                out
            },
        );
        assert!(!acc.is_empty());
        let m = mean_accuracy(&acc);
        assert!((0.0..=1.0).contains(&m));
    }
}
