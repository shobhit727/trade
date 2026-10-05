"""Tests for catalog strategy cross_sectional."""

from __future__ import annotations

from cryptobot.strategies.catalog.cross_sectional import CrossSectionalStrategy


def _series(up: bool):
    s = CrossSectionalStrategy()
    out = []
    for i in range(200):
        px = (100.0 + i * 0.4) if up else (200.0 - i * 0.4)
        o = s.feed("BTC", px, px, px, 1000.0)
        if o:
            out.append(o)
    return out


def test_cross_sectional_long_signal():
    assert any(o.side.value == "BUY" for o in _series(True))


def test_cross_sectional_short_signal():
    assert any(o.side.value == "SELL" for o in _series(False))
