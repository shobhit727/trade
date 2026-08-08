"""Tests for catalog strategy bb_squeeze2."""

from __future__ import annotations

from cryptobot.strategies.catalog.bb_squeeze2 import BbSqueeze2Strategy


def _series(up: bool):
    s = BbSqueeze2Strategy()
    out = []
    for i in range(200):
        px = (100.0 + i * 0.4) if up else (200.0 - i * 0.4)
        o = s.feed("BTC", px, px, px, 1000.0)
        if o:
            out.append(o)
    return out


def test_bb_squeeze2_long_signal():
    assert any(o.side.value == "BUY" for o in _series(True))


def test_bb_squeeze2_short_signal():
    assert any(o.side.value == "SELL" for o in _series(False))
