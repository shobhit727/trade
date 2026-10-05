"""Tests for catalog strategy nr4."""

from __future__ import annotations

from cryptobot.strategies.catalog.nr4 import Nr4Strategy


def _series(up: bool):
    s = Nr4Strategy()
    out = []
    for i in range(200):
        px = (100.0 + i * 0.4) if up else (200.0 - i * 0.4)
        o = s.feed("BTC", px, px, px, 1000.0)
        if o:
            out.append(o)
    return out


def test_nr4_long_signal():
    assert any(o.side.value == "BUY" for o in _series(True))


def test_nr4_short_signal():
    assert any(o.side.value == "SELL" for o in _series(False))
