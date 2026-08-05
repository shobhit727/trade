from __future__ import annotations

from decimal import Decimal

from cryptobot.strategies.trend_following import (
    TrendFollowingConfig,
    TrendFollowingStrategy,
    _TrendState,
)


def test_trend_config_defaults():
    cfg = TrendFollowingConfig()
    assert cfg.fast == 12
    assert cfg.slow == 26
    assert cfg.adx_threshold == 20.0
    assert cfg.quantity == Decimal("1")


def test_strategy_name():
    s = TrendFollowingStrategy()
    assert s.name == "trend_following"


def test_strategy_default_config():
    s = TrendFollowingStrategy()
    assert isinstance(s.config, TrendFollowingConfig)


def test_strategy_custom_config():
    cfg = TrendFollowingConfig(fast=8, slow=21, quantity=Decimal("0.5"))
    s = TrendFollowingStrategy(cfg)
    assert s.config.fast == 8
    assert s.config.slow == 21
    assert s.config.quantity == Decimal("0.5")


def test_trend_state_defaults():
    st = _TrendState()
    assert st.bars == 0
    assert st.ema_fast == 0.0
    assert st.ema_slow == 0.0
    assert st.ema_fast_seeded is False
    assert st.ema_slow_seeded is False


def test_strategy_state_isolation():
    s = TrendFollowingStrategy()
    s._st("BTCUSDT")
    s._st("ETHUSDT")
    assert "BTCUSDT" in s._state
    assert "ETHUSDT" in s._state
    assert s._state["BTCUSDT"] is not s._state["ETHUSDT"]


def test_strategy_update_indicators_first_bar():
    s = TrendFollowingStrategy()
    st = _TrendState()
    s._update_indicators(st, high=100, low=99, close=100)
    assert st.bars == 1
    assert st.ema_fast == 100
    assert st.ema_slow == 100
    assert st.ema_fast_seeded is True
    assert st.ema_slow_seeded is True
    assert st.prev_high == 100
    assert st.prev_low == 99
    assert st.prev_close == 100


def test_strategy_update_indicators_subsequent_bars():
    s = TrendFollowingStrategy()
    st = _TrendState()
    s._update_indicators(st, high=100, low=99, close=100)  # first bar
    s._update_indicators(st, high=101, low=100, close=100.5)  # second bar
    assert st.bars == 2
    assert st.ema_fast > 0
    assert st.ema_slow > 0


def test_strategy_config_precomputed_constants():
    cfg = TrendFollowingConfig(fast=10, slow=20)
    s = TrendFollowingStrategy(cfg)
    assert s._k_fast == 2.0 / 11
    assert s._k_slow == 2.0 / 21
    assert s._slow == 20


__all__ = []
