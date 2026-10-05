"""Tests for catalog strategy trend_volume."""

from __future__ import annotations

from cryptobot.strategies.catalog.trend_volume import TrendVolumeStrategy


def _flow(up: bool):
    s = TrendVolumeStrategy()
    out = []
    for i in range(200):
        px = (100.0 + i * 0.2) if up else (200.0 - i * 0.2)
        vol = 1000.0 + (300.0 if (i % 10 == 0) else 0)
        if up:
            o = s.feed("BTC", px + 1.0, px + 1.0, px, vol)
        else:
            o = s.feed("BTC", px - 1.0, px, px - 1.0, vol)
        if o:
            out.append(o)
    return out


def test_trend_volume_flow_long_signal():
    assert any(o.side.value == "BUY" for o in _flow(True))


def test_trend_volume_flow_short_signal():
    assert any(o.side.value == "SELL" for o in _flow(False))
