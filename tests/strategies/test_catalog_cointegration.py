"""Tests for catalog strategy cointegration.

This is a PAIRS strategy: it trades the stationary spread of two legs, so it
needs two symbols. The previous version was single-name z-score mean reversion
(the defect the audit found), and this test asserted that defective behaviour.
It now feeds a genuine cointegrating pair and checks both legs are traded.
"""

from __future__ import annotations

import numpy as np

from cryptobot.strategies.catalog.cointegration_strategy import CointegrationStrategy


def _pair(seed: int = 4, n: int = 800):
    """A cointegrating pair: log(A) = 2*log(B) + const + small noise."""
    rng = np.random.default_rng(seed)
    b = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    a = np.exp(2.0 * np.log(b) + 1.0 + rng.normal(0, 0.004, n))
    return a, b


def _series():
    a, b = _pair()
    s = CointegrationStrategy()
    s.set_leg_b("ETH")
    leg_a, leg_b = [], []
    for i in range(len(a)):
        o_a = s.feed("BTC", float(a[i]), float(a[i]), float(a[i]), 1000.0)
        o_b = s.feed("ETH", float(b[i]), float(b[i]), float(b[i]), 1000.0)
        if o_a:
            leg_a.append(o_a)
        if o_b:
            leg_b.append(o_b)
    return leg_a, leg_b


def test_cointegration_trades_both_legs():
    leg_a, leg_b = _series()
    assert leg_a, "the first leg must trade the spread"
    assert leg_b, "the second leg must trade the spread"
    # Pair trade: the two legs are mirror images, never the same side.
    assert leg_a[0].side.value != leg_b[0].side.value


def test_cointegration_is_flat_without_a_pair():
    """A pairs strategy cannot trade one name; it must not fake a signal."""
    a, _ = _pair()
    s = CointegrationStrategy()
    out = []
    for i in range(300):
        o = s.feed("BTC", float(a[i]), float(a[i]), float(a[i]), 1000.0)
        if o:
            out.append(o)
    assert not out
