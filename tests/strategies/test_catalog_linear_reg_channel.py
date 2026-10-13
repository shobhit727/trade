"""Tests for catalog strategy linear_reg_channel.

NOTE ON THE FIXTURE
-------------------
This originally fed a *perfectly linear* ramp (`100 + 0.4*i`) and asserted a BUY.
That fixture encoded the bug this strategy used to have.

A perfectly linear window has a residual standard deviation of exactly zero, so the
close sits precisely on the fitted line and never breaks the channel band. The old
implementation was `sma() + a level comparison` with no regression and no band at all,
so it fired on the trend and this assertion passed. The corrected implementation trades
the residual z-score against `multiplier * sigma`, and on a noiseless ramp there is no
residual to trade -- correctly producing no signal.

Any *correct* channel rule, including the textbook close/large-close/least-squares
regression channel, would fail this fixture. The fixture now injects deterministic noise
so the channel actually has width, which is the condition the strategy is defined for.
"""

from __future__ import annotations

import random

from cryptobot.strategies.catalog.linear_regression_channel import LinearRegChannelStrategy


def _series(up: bool, seed: int = 1):
    """Feed a drifting price with deterministic residual noise.

    The noise is what gives the regression fit a non-zero residual sigma; without it a
    channel strategy has no band to trade against.
    """
    rng = random.Random(seed)
    s = LinearRegChannelStrategy()
    out = []
    for i in range(200):
        drift = 100.0 + i * 0.4 if up else 200.0 - i * 0.4
        px = drift + rng.uniform(-4.0, 4.0)
        o = s.feed("BTC", px, px, px, 1000.0)
        if o:
            out.append(o)
    return out


def test_linear_reg_channel_long_signal():
    assert any(o.side.value == "BUY" for o in _series(True))


def test_linear_reg_channel_short_signal():
    assert any(o.side.value == "SELL" for o in _series(False))


def test_channel_is_deterministic():
    """Same input must give the same orders -- backtests depend on this."""
    assert [o.side.value for o in _series(True, seed=7)] == [
        o.side.value for o in _series(True, seed=7)
    ]


def test_noiseless_series_trades_nothing():
    """A noiseless ramp has zero residual sigma, so there is no channel to break.

    This is the property the original fixture got wrong: it expected a BUY here.
    """
    s = LinearRegChannelStrategy()
    orders = [s.feed("BTC", 100.0 + i * 0.4, 100.0 + i * 0.4, 100.0 + i * 0.4, 1000.0)
              for i in range(200)]
    assert not [o for o in orders if o]
