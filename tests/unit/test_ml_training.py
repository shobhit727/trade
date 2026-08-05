from __future__ import annotations

from cryptobot.ml.training import (
    FoldResult,
    PurgedKFold,
    SplitMethod,
    TrainingConfig,
    TrainingResult,
)


def test_split_method_enum():
    assert SplitMethod.PURGED_KFOLD.value == "purged_kfold"
    assert SplitMethod.WALK_FORWARD.value == "walk_forward"
    assert SplitMethod.BLOCK.value == "block"


def test_training_config_defaults():
    cfg = TrainingConfig()
    assert cfg.split_method == SplitMethod.PURGED_KFOLD
    assert cfg.n_splits == 5
    assert cfg.embargo_pct == 0.01
    assert cfg.min_train_size == 100
    assert cfg.test_size == 0.2
    assert cfg.random_state == 42
    assert cfg.use_optuna is False
    assert cfg.n_trials == 50
    assert cfg.models_to_train == ["direction", "volatility", "regime", "ensemble"]


def test_training_config_custom():
    cfg = TrainingConfig(
        split_method=SplitMethod.WALK_FORWARD,
        n_splits=3,
        embargo_pct=0.02,
        min_train_size=200,
    )
    assert cfg.split_method == SplitMethod.WALK_FORWARD
    assert cfg.n_splits == 3
    assert cfg.embargo_pct == 0.02
    assert cfg.min_train_size == 200


def test_fold_result_creation():
    fr = FoldResult(
        fold_idx=0,
        train_size=800,
        test_size=200,
        train_start=0,
        train_end=800,
        test_start=800,
        test_end=1000,
        metrics={"sharpe": 1.5},
        model_params={"C": 1.0},
    )
    assert fr.fold_idx == 0
    assert fr.train_size == 800
    assert fr.metrics["sharpe"] == 1.5


def test_training_result_creation():
    tr = TrainingResult(
        folds=[],
        best_params={"C": 1.0},
        best_score=1.5,
    )
    assert tr.best_score == 1.5
    assert tr.cv_scores == []


def test_purged_kfold_basic():
    pkf = PurgedKFold(n_splits=5, embargo_pct=0.01)
    n_samples = 1000
    splits = list(pkf.split(range(n_samples)))
    assert len(splits) == 5
    for train_idx, test_idx in splits:
        assert len(train_idx) > 0
        assert len(test_idx) > 0
        # Test that train indices don't overlap with test (due to purge)
        train_set = set(train_idx)
        test_set = set(test_idx)
        assert len(train_set & test_set) == 0
        # Test indices should be contiguous
        assert list(test_idx) == list(range(min(test_idx), max(test_idx) + 1))
        # Train can be on both sides of test (before and after), but no overlap
        assert len(set(train_idx) & set(test_idx)) == 0


def test_purged_kfold_embargo():
    pkf = PurgedKFold(n_splits=3, embargo_pct=0.02)
    n_samples = 1000
    splits = list(pkf.split(range(n_samples)))
    embargo = int(n_samples * 0.02)
    for train_idx, test_idx in splits:
        if len(train_idx) > 0 and len(test_idx) > 0:
            # The embargo creates a purge window around test
            # Train should not contain indices within embargo of test
            # Test indices are contiguous
            assert list(test_idx) == list(range(min(test_idx), max(test_idx) + 1))
            # There should be a gap of at least embargo between train and test
            if max(train_idx) < min(test_idx):
                gap = min(test_idx) - max(train_idx) - 1
                assert gap >= embargo - 1  # approximate


def test_purged_kfold_test_size_default():
    pkf = PurgedKFold(n_splits=4, embargo_pct=0.01)
    n_samples = 1000
    splits = list(pkf.split(range(n_samples)))
    test_size = n_samples // 4
    for train_idx, test_idx in splits:
        if len(test_idx) > 0:
            # Test size should be approximately test_size
            assert len(test_idx) <= test_size + 1


__all__ = []
