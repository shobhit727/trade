"""Tests for catalog strategy open_range."""

from __future__ import annotations

from cryptobot.strategies.catalog.open_range import OpenRangeStrategy


def _series(up: bool):
    s = OpenRangeStrategy()
    out = []
    for i in range(200):
        px = (100.0 + i * 0.4) if up else (200.0 - i * 0.4)
        o = s.feed("BTC", px, px, px, 1000.0)
        if o:
            out.append(o)
    return out


def test_open_range_long_signal():
    assert any(o.side.value == "BUY" for o in _series(True))


def test_open_range_short_signal():
    assert any(o.side.value == "SELL" for o in _series(False))
