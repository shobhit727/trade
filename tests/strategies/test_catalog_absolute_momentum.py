"""Tests for catalog strategy absolute_momentum."""

from __future__ import annotations

from cryptobot.strategies.catalog.absolute_momentum import AbsoluteMomentumStrategy


def _series(up: bool):
    s = AbsoluteMomentumStrategy()
    out = []
    for i in range(200):
        px = (100.0 + i * 0.4) if up else (200.0 - i * 0.4)
        o = s.feed("BTC", px, px, px, 1000.0)
        if o:
            out.append(o)
    return out


def test_absolute_momentum_long_signal():
    assert any(o.side.value == "BUY" for o in _series(True))


def test_absolute_momentum_short_signal():
    assert any(o.side.value == "SELL" for o in _series(False))


def test_absolute_momentum_neutral_zone_no_signal():
    # Flat prices => momentum ~0 => neutral zone must yield NO order (issue #47).
    # A -1 in the neutral zone would wrongly flip the book short on flat markets.
    s = AbsoluteMomentumStrategy()
    out = []
    for i in range(200):
        o = s.feed("BTC", 100.0, 100.0, 100.0, 1000.0)
        if o:
            out.append(o)
    assert out == []
