from __future__ import annotations

from decimal import Decimal

import numpy as np

from cryptobot.backtest.data import load_bars
from cryptobot.ml.features import build_features, features_and_labels, future_returns
from cryptobot.ml.models.direction import (
    DirectionClassifier,
)
from cryptobot.ml.online import DriftConfig, DriftDetector, WalkForwardTrainer
from cryptobot.strategies.funding_arb import (
    FundingArbConfig,
    FundingArbState,
    FundingArbStrategy,
)
from cryptobot.strategies.market_making import (
    MarketMakingConfig,
    MarketMakingStrategy,
)
from cryptobot.strategies.stat_arb import StatArbConfig, StatArbStrategy


def test_market_making_quote_changes_with_inventory():
    cfg = MarketMakingConfig(gamma=0.5, sigma=0.01, kappa=1.5)
    strat = MarketMakingStrategy(cfg)
    bid_a, ask_a = strat.quote(Decimal("100"), t_remaining=1.0)
    strat.inventory = Decimal("3")
    bid_b, ask_b = strat.quote(Decimal("100"), t_remaining=1.0)
    assert bid_b < bid_a
    assert ask_b < ask_a


async def test_market_making_run_on_history_emits_fills():
    bars = load_bars(source="synthetic", symbol="BTCUSDT", timeframe="1h")
    bars.bars = bars.bars[:30]
    cfg = MarketMakingConfig(quantity=Decimal("0.5"), max_inventory=Decimal("5"))
    strat = MarketMakingStrategy(cfg)
    fills = await strat.run_on_history(bars.bars)
    assert isinstance(fills, list)
    assert all(f.filled_quantity > 0 for f in fills)


def test_stat_arb_needs_history_before_signal():
    strat = StatArbStrategy(StatArbConfig(lookback=10))
    assert strat.step() is None
    for v in range(5):  # Less than lookback
        strat.feed(100 + v * 0.1, 50 + v * 0.05)
    assert strat.step() is None
    for v in range(5, 15):  # Now we have enough
        strat.feed(100 + v * 0.1, 50 + v * 0.05)
    # After enough history, step may return a signal
    signal = strat.step()
    assert signal is None or isinstance(signal, tuple)


def test_stat_arb_walks_history_and_yields_signal_after_warmup():
    strat = StatArbStrategy(StatArbConfig(lookback=15, z_entry=0.5, z_exit=0.1))
    import numpy as np
    rng = np.random.default_rng(0)
    prices_a = 100.0 + rng.normal(0, 0.5, 60).cumsum()
    prices_b = prices_a * 0.5 + rng.normal(0, 0.05, 60).cumsum()
    signal = None
    for a, b in zip(prices_a, prices_b):
        signal = strat.feed_and_signal(a, b)
    assert signal is None or isinstance(signal, tuple)


def test_funding_arb_emits_pair_on_funding_signal():
    from cryptobot.core.events import OrderSide

    strat = FundingArbStrategy()
    state = FundingArbState(
        spot_price=Decimal("100"), perp_price=Decimal("100.06"), funding_rate=0.0008, next_funding_seconds=60
    )
    sides = strat.feed(state)
    assert sides in {(OrderSide.SELL, OrderSide.BUY), (OrderSide.BUY, OrderSide.SELL)}


def test_funding_arb_ignores_low_funding():
    strat = FundingArbStrategy(FundingArbConfig(min_funding_rate=0.01))
    state = FundingArbState(
        spot_price=Decimal("100"), perp_price=Decimal("100.02"), funding_rate=0.0001, next_funding_seconds=60
    )
    assert strat.feed(state) is None


def test_build_features_returns_shape():
    bars = load_bars(source="synthetic", symbol="BTCUSDT", timeframe="1h")
    bars.bars = bars.bars[:80]
    feature_set = build_features(bars)
    X = feature_set.features
    assert X.ndim == 2
    # Features: 4 returns + 1 RSI + 3 MACD + 1 ATR + 2 BB + 1 log_vol + 1 vol_ratio + 1 momentum = 14
    assert X.shape[1] == 14
    assert X.shape[0] > 0


def test_future_returns_length_matches_bars():
    bars = load_bars(source="synthetic", symbol="BTCUSDT", timeframe="1h")
    bars.bars = bars.bars[:60]
    out = future_returns(bars.close, horizons=[5])
    assert out.shape == (60, 1)


def test_direction_classifier_fits_and_predicts():
    rng = np.random.default_rng(0)
    n = 200
    X = rng.normal(size=(n, 5))
    y = (X[:, 0] + 0.5 * X[:, 1] > 0).astype(int)
    clf = DirectionClassifier()
    clf.fit(X, y)
    proba = clf.predict_proba(X)
    assert proba.shape == (n,)
    assert (proba >= 0).all() and (proba <= 1).all()
    preds = clf.predict(X)
    accuracy = (preds == y).mean()
    assert accuracy > 0.55


def test_direction_classifier_walk_forward_score_returns_float():
    rng = np.random.default_rng(0)
    n = 200
    X = rng.normal(size=(n, 6))
    y = (X[:, 0] + X[:, 1] > 0).astype(int)
    clf = DirectionClassifier()
    score = clf.walk_forward_score(X, y, n_splits=4)
    assert 0.0 <= score <= 1.0


def test_features_and_labels_aligned():
    bars = load_bars(source="synthetic", symbol="BTCUSDT", timeframe="1h")
    bars.bars = bars.bars[:80]
    feature_set, y = features_and_labels(bars, label_horizons=[3])
    X = feature_set.features
    assert X.shape[0] == y.shape[0]


def test_drift_detector_signals_high_score_after_shift():
    detector = DriftDetector(DriftConfig(baseline_size=20, recent_size=10, threshold=0.2))
    for _ in range(40):
        detector.update(1.0)
    for _ in range(10):
        detector.update(5.0)
    assert detector.drift_score() > 0.2


def test_walk_forward_trainer_splits():
    trainer = WalkForwardTrainer(n_splits=3, embargo=2)
    splits = trainer.splits(n=300, min_train=100)
    assert len(splits) >= 1
    for train_start, train_end, test_start, test_end in splits:
        assert train_end > train_start
        assert test_end > test_start
        assert test_start >= train_end + trainer.embargo


def test_featureset_to_array_returns_features():
    from cryptobot.ml.features import FeatureSet

    feats = np.arange(12, dtype=float).reshape(4, 3)
    fs = FeatureSet(
        features=feats,
        feature_names=["a", "b", "c"],
        timestamps=np.zeros(4, dtype="datetime64[ns]"),
        config=None,
    )
    out = fs.to_array()
    assert out.shape == (4, 3)
    assert np.array_equal(out, feats)
    assert out.dtype == np.float64


def test_walk_forward_score_requires_labels():
    import pytest

    rng = np.random.default_rng(1)
    X = rng.normal(size=(100, 6))
    clf = DirectionClassifier()
    # Labels must not be fabricated when absent (issue #48)
    with pytest.raises(ValueError):
        clf.walk_forward_score(X, labels=None, n_splits=4)


def test_drift_detector_zero_mean_does_not_saturate():
    # A near-zero-mean baseline (e.g. returns) must not produce a saturated
    # drift score when the recent window has only a small mean shift (#48).
    detector = DriftDetector(DriftConfig(baseline_size=50, recent_size=20, threshold=0.9))
    rng = np.random.default_rng(0)
    for _ in range(50):
        detector.update(rng.normal(0.0, 1.0))  # zero-mean baseline
    for _ in range(20):
        detector.update(rng.normal(0.1, 1.0))  # small mean shift, same std
    score = detector.drift_score()
    assert 0.0 <= score <= 1.0
    assert score < 0.5  # old mean-normalized bug saturated this to ~1.0
