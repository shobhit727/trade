"""Tests for catalog strategy funding_trend."""

from __future__ import annotations

from cryptobot.strategies.catalog.funding_trend import FundingTrendStrategy


def _series(up: bool):
    s = FundingTrendStrategy()
    out = []
    for i in range(200):
        px = (100.0 + i * 0.4) if up else (200.0 - i * 0.4)
        o = s.feed("BTC", px, px, px, 1000.0)
        if o:
            out.append(o)
    return out


def test_funding_trend_long_signal():
    assert any(o.side.value == "BUY" for o in _series(True))


def test_funding_trend_short_signal():
    assert any(o.side.value == "SELL" for o in _series(False))
