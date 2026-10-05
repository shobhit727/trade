"""Tests for catalog strategy ma_cross."""

from __future__ import annotations

from cryptobot.strategies.catalog.ma_cross import MaCrossStrategy


def _series(up: bool):
    s = MaCrossStrategy()
    out = []
    for i in range(200):
        px = (100.0 + i * 0.4) if up else (200.0 - i * 0.4)
        o = s.feed("BTC", px, px, px, 1000.0)
        if o:
            out.append(o)
    return out


def test_ma_cross_long_signal():
    assert any(o.side.value == "BUY" for o in _series(True))


def test_ma_cross_short_signal():
    assert any(o.side.value == "SELL" for o in _series(False))
