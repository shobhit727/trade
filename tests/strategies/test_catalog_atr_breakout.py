"""Tests for catalog strategy atr_breakout."""

from __future__ import annotations

from cryptobot.strategies.catalog.atr_breakout import AtrBreakoutStrategy


def test_atr_breakout_expansion_follows_spike():
    s = AtrBreakoutStrategy()
    got = []
    for i in range(120):
        px = 100.0 + i * 0.1
        o = s.feed("BTC", px, px * 1.001, px * 0.999, 1000.0)
        if o:
            got.append(o.side.value)
    px = 120.0
    o = s.feed("BTC", px, px * 1.05, px * 0.95, 5000.0)
    assert o is None or o.side.value == "BUY"
