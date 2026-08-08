"""Tests for catalog strategy anchored_vwap."""

from __future__ import annotations

import math

from cryptobot.strategies.catalog.anchored_vwap import AnchoredVwapStrategy


def _series(up: bool):
    s = AnchoredVwapStrategy()
    out = []
    for i in range(300):
        px = 100.0 + 8.0 * math.sin(i / 6.0) + (0.05 * i if up else -0.05 * i)
        o = s.feed("BTC", px, px * 1.002, px * 0.998, 1000.0)
        if o:
            out.append(o)
    return out


def test_anchored_vwap_long_signal():
    assert any(o.side.value == "BUY" for o in _series(True))


def test_anchored_vwap_short_signal():
    assert any(o.side.value == "SELL" for o in _series(False))
