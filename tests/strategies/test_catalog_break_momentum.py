"""Tests for catalog strategy break_momentum."""

from __future__ import annotations

from cryptobot.strategies.catalog.break_momentum import BreakMomentumStrategy


def _series(up: bool):
    s = BreakMomentumStrategy()
    out = []
    for i in range(200):
        px = (100.0 + i * 0.4) if up else (200.0 - i * 0.4)
        o = s.feed("BTC", px, px, px, 1000.0)
        if o:
            out.append(o)
    return out


def test_break_momentum_long_signal():
    assert any(o.side.value == "BUY" for o in _series(True))


def test_break_momentum_short_signal():
    assert any(o.side.value == "SELL" for o in _series(False))
