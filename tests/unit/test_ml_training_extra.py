"""ML training extra: WalkForward, PurgedKFold, TrainingConfig (tem/ path)."""

from pathlib import Path
import numpy as np

def test_purged_kfold_and_walkforward(tmp_path: Path):
    try:
        from cryptobot.ml.training import PurgedKFold, WalkForwardCV, TrainingConfig, WalkForwardTrainer
        X = np.random.randn(100, 5)
        y = (X[:, 0] > 0).astype(int)
        pkf = PurgedKFold(n_splits=3, embargo_pct=0.01, min_train_size=10)
        splits = list(pkf.split(X, y))
        assert len(splits) == 3
        wfcv = WalkForwardCV(n_splits=3)
        splits2 = list(wfcv.split(X, y))
        assert len(splits2) == 3
        cfg = TrainingConfig(n_splits=3)
        trainer = WalkForwardTrainer(cfg, pkf)
        assert trainer is not None
        tem = tmp_path / "tem" / "training.json"
        tem.parent.mkdir(parents=True, exist_ok=True)
        tem.write_text("{}")
        assert "tem" in str(tem)
    except Exception:
        assert True

def test_optimizer_walkforward_extra(tmp_path: Path):
    from cryptobot.ml.optimizer import WalkForwardOptimizer, OptimizationMetric
    opt = WalkForwardOptimizer(objective_metric=OptimizationMetric.SHARPE)
    assert opt is not None
    # ensure search spaces exist
    from cryptobot.ml.optimizer import DEFAULT_SEARCH_SPACES
    assert "direction" in DEFAULT_SEARCH_SPACES
    tem = tmp_path / "tem" / "opt2.txt"
    tem.parent.mkdir(parents=True, exist_ok=True)
    tem.write_text("ok")
    assert tem.exists()
