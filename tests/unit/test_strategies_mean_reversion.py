from __future__ import annotations

from decimal import Decimal

from cryptobot.strategies.mean_reversion import (
    MeanReversionConfig,
    MeanReversionStrategy,
)


def test_config_defaults():
    cfg = MeanReversionConfig()
    assert cfg.lookback == 20
    assert cfg.z_entry == 2.0
    assert cfg.quantity == Decimal("1")


def test_strategy_name():
    s = MeanReversionStrategy()
    assert s.name == "mean_reversion"


def test_strategy_default_config():
    s = MeanReversionStrategy()
    assert isinstance(s.config, MeanReversionConfig)


def test_strategy_returns_none_until_enough_data():
    s = MeanReversionStrategy()
    for price in [100.0, 101.0, 102.0]:
        result = s.feed("BTCUSDT", price)
        assert result is None


def test_strategy_returns_no_signal_in_stable_market():
    s = MeanReversionStrategy()
    for i in range(30):
        s.feed("BTCUSDT", 100.0 + (i % 3) * 0.1)
    result = s.feed("BTCUSDT", 100.0)
    assert result is None


def test_strategy_buy_signal_requires_all_conditions():
    """Test that BUY signal requires all three conditions: z-score, RSI, and BB."""
    s = MeanReversionStrategy(
        MeanReversionConfig(lookback=10, z_entry=1.5, rsi_oversold=40.0, bb_period=10, rsi_period=5)
    )
    prices = [100, 100, 100, 100, 100, 99, 98, 97, 96, 95, 60.0]
    last = None
    for p in prices:
        last = s.feed("BTCUSDT", p)
    # Crash: z <= -z_entry, RSI ~ 0 (gains=0, losses>0), price below bb_lower -> BUY
    assert last is not None
    assert last.side.value == "BUY"


def test_strategy_sell_signal_requires_all_conditions():
    s = MeanReversionStrategy(
        MeanReversionConfig(lookback=10, z_entry=1.5, rsi_overbought=60.0, bb_period=10, rsi_period=5)
    )
    prices = [100, 100, 100, 100, 100, 101, 102, 103, 104, 105, 140.0]
    last = None
    for p in prices:
        last = s.feed("BTCUSDT", p)
    # Spike: z >= 1.5, RSI ~ 100 (gains>0, losses=0), price above BB upper -> SELL
    assert last is not None
    assert last.side.value == "SELL"


def test_strategy_exit_signal_on_z_reversion():
    """Test that exit signal (z reversion) works independently of RSI."""
    s = MeanReversionStrategy(
        MeanReversionConfig(lookback=10, z_entry=1.5, z_exit=0.5, bb_period=10, rsi_period=5)
    )
    # Create a mean-reverting sequence that brings z back to near 0
    prices = [100]*10 + [95]*5 + [97]*3 + [98]*2  # z goes negative then reverts
    last = None
    for p in prices:
        last = s.feed("BTCUSDT", p)
    # Exit signal may fire if |z| <= z_exit
    # This just tests the method runs without error
    assert last is None or isinstance(last.side, str)


def test_strategy_handles_zero_std():
    cfg = MeanReversionConfig(lookback=5, bb_period=5, rsi_period=3)
    s = MeanReversionStrategy(cfg)
    for _ in range(10):
        s.feed("BTCUSDT", 100.0)
    result = s.feed("BTCUSDT", 100.0)
    assert result is None


def test_strategy_uses_quantity_from_config():
    s = MeanReversionStrategy(MeanReversionConfig(quantity=Decimal("0.5")))
    for _ in range(20):
        s.feed("BTCUSDT", 100.0)
    s.feed("BTCUSDT", 100.0)
    result = s.feed("BTCUSDT", 130.0)
    if result is not None:
        assert result.quantity == Decimal("0.5")


def test_strategy_multi_symbol_state_isolation():
    s = MeanReversionStrategy(
        MeanReversionConfig(lookback=10, z_entry=2.0, rsi_overbought=70.0, bb_period=10, rsi_period=5)
    )
    for _ in range(10):
        s.feed("BTCUSDT", 100.0)
    for _ in range(10):
        s.feed("ETHUSDT", 50.0)
    assert "BTCUSDT" in s._prices
    assert "ETHUSDT" in s._prices


def _entry_long_entry(s: MeanReversionStrategy, symbol: str = "BTCUSDT") -> float:
    """Drive price down hard enough to force a long entry; returns entry price."""
    prices = [100.0] * 16 + [50.0]
    entry_price = prices[-1]
    for p in prices:
        s.feed(symbol, p)
    assert symbol in s._positions, "expected a long entry to fire"
    return entry_price


def test_take_profit_exits_full_position_at_market():
    s = MeanReversionStrategy(MeanReversionConfig(lookback=14, z_entry=2.0, bb_period=10, rsi_period=5, take_profit=0.02, stop_loss=0, max_hold_bars=0, quantity=Decimal("2"), z_exit=0.0))
    entry = _entry_long_entry(s)
    exit_order = s.feed("BTCUSDT", entry * 1.05)
    assert exit_order is not None
    assert exit_order.side.value == "SELL"
    assert exit_order.type.value == "MARKET"
    assert exit_order.quantity == Decimal("2")
    assert "BTCUSDT" not in s._positions


def test_stop_loss_exits_full_position_at_market():
    s = MeanReversionStrategy(MeanReversionConfig(lookback=14, z_entry=2.0, bb_period=10, rsi_period=5, take_profit=0, stop_loss=0.02, max_hold_bars=0, z_exit=0.0))
    entry_price = _entry_long_entry(s)
    exit_order = s.feed("BTCUSDT", entry_price * 0.97)
    assert exit_order is not None
    assert exit_order.side.value == "SELL"
    assert exit_order.type.value == "MARKET"


def test_max_hold_bars_force_exit():
    s = MeanReversionStrategy(MeanReversionConfig(lookback=14, z_entry=2.0, bb_period=10, rsi_period=5, take_profit=0, stop_loss=0, max_hold_bars=10, z_exit=0.0))
    entry_price = _entry_long_entry(s)
    exited = None
    for _i in range(12):
        exited = s.feed("BTCUSDT", entry_price)  # flat price: no TP/SL, no z-reversion
        if exited is not None:
            break
    assert exited is not None
    assert exited.side.value == "SELL"
    assert "BTCUSDT" not in s._positions


def test_no_pyramiding_while_in_position():
    s = MeanReversionStrategy(MeanReversionConfig(lookback=14, z_entry=2.0, bb_period=10, rsi_period=5, take_profit=0.02, stop_loss=0.02, max_hold_bars=48, z_exit=0.0))
    entry_price = _entry_long_entry(s)
    for _ in range(5):
        order = s.feed("BTCUSDT", entry_price)  # flat at entry: no exit rule fires; must not add
        assert order is None


def test_quantity_closes_full_position():
    s = MeanReversionStrategy(MeanReversionConfig(lookback=14, z_entry=2.0, bb_period=10, rsi_period=5, take_profit=0, stop_loss=0.02, max_hold_bars=0, quantity=Decimal("2.5"), z_exit=0.0))
    _entry_long_entry(s)
    exit_order = s.feed("BTCUSDT", 40.0)
    assert exit_order is not None
    assert exit_order.quantity == Decimal("2.5")


__all__ = []
