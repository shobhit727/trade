"""`indicators.hull` must implement the TEXTBOOK Hull moving average.

Textbook Hull MA (Alan Hull):

    raw(t) = 2 * WMA(half_period)(t) - WMA(period)(t)
    HMA(t) = WMA(sqrt_period)( raw )(t)

i.e. the *fast* WMA is doubled and the *slow* WMA subtracted. That is what gives Hull
its near-zero lag: on a straight ramp both spellings are exact, but only the textbook
ordering tracks price closely on real (non-linear) data.

The shipped implementation used `2 * WMA(period) - WMA(half)` -- the two terms swapped
-- while its own docstring claimed `WMA(2*WMA(n/2) - WMA(n), sqrt(n))`, so the code
contradicted the definition printed directly above it.

These tests pin the definition with an independently written reference. Note the
reference below is deliberately naive (recomputes every intermediate series from
scratch per bar) so that it shares no structure with the streaming implementation --
a shared-structure reference would have reproduced the same swap.
"""

from __future__ import annotations

import numpy as np
import pytest

from cryptobot.strategies.indicators import hull

PERIODS = (10, 15, 20, 30, 55)


def _wma(values: list[float], period: int) -> float:
    """Naive weighted MA: linearly increasing weights, most recent bar heaviest."""
    if len(values) < period:
        raise ValueError("insufficient data")
    window = values[-period:]
    weights = list(range(1, period + 1))  # oldest -> 1, newest -> period
    total = sum(v * w for v, w in zip(window, weights, strict=True))
    return total / (period * (period + 1) / 2)


def textbook_hull(closes: list[float], period: int) -> float:
    """Reference Hull MA built by composing naive WMA calls only."""
    half = max(1, period // 2)
    sqrt_p = max(1, int(round(period**0.5)))

    # Raw Hull line at every bar in the final sqrt_p window, then WMA those raws.
    # Oldest bar first: `_wma` weights the LAST element most heavily, so `raws`
    # must be in chronological order.
    raws = []
    for back in range(sqrt_p - 1, -1, -1):
        upto = len(closes) - back
        window = closes[:upto]
        if len(window) < period:
            return float("nan")
        raws.append(2.0 * _wma(window, half) - _wma(window, period))
    return _wma(raws, sqrt_p)


def swapped_hull(closes: list[float], period: int) -> float:
    """The spelling the library shipped: 2*WMA(period) - WMA(half).

    Kept so tests can prove they actually reject the old behaviour rather than
    passing vacuously.
    """
    half = max(1, period // 2)
    sqrt_p = max(1, int(round(period**0.5)))
    raws = []
    for back in range(sqrt_p - 1, -1, -1):
        upto = len(closes) - back
        window = closes[:upto]
        if len(window) < period:
            return float("nan")
        raws.append(2.0 * _wma(window, period) - _wma(window, half))
    return _wma(raws, sqrt_p)


def _walk(n: int = 400, seed: int = 11) -> list[float]:
    """Noisy geometric random walk -- close enough to real price action."""
    rng = np.random.default_rng(seed)
    return list(100.0 * np.exp(np.cumsum(rng.normal(0.0003, 0.015, n))))


def _ramp(n: int = 120) -> list[float]:
    """Perfectly linear series -- degenerate case, both spellings agree here."""
    return [100.0 + 0.5 * i for i in range(n)]


@pytest.mark.parametrize("period", PERIODS)
def test_hull_matches_textbook_definition(period: int) -> None:
    """hull() must equal 2*WMA(half) - WMA(period), smoothed over sqrt(period)."""
    closes = _walk()
    assert hull(closes, period) == pytest.approx(
        textbook_hull(closes, period), rel=1e-12
    )


@pytest.mark.parametrize("period", PERIODS)
def test_hull_is_not_the_swapped_spelling(period: int) -> None:
    """Guard the specific regression: the slow/fast terms must not be reversed.

    The two spellings coincide whenever WMA(period) == WMA(half), so these assert
    on data where they genuinely differ.
    """
    closes = _walk(n=300, seed=5)
    assert _wma(closes, period) != pytest.approx(_wma(closes, max(1, period // 2)))
    assert hull(closes, period) == pytest.approx(textbook_hull(closes, period))
    assert hull(closes, period) != pytest.approx(swapped_hull(closes, period))


def test_hull_has_low_lag_on_a_trend() -> None:
    """Textbook Hull stays glued to price on a trend; the swapped line fell behind.

    This is the property that actually distinguishes the two spellings -- the
    swapped one is not a negated line, it is a much blunter one.
    """
    rng = np.random.default_rng(3)
    closes = list(np.linspace(100.0, 300.0, 300) + rng.normal(0, 0.5, 300))

    gap = abs(closes[-1] - hull(closes, 20))
    assert gap < 5.0, f"Hull line is {gap:.2f} away from price -- too laggy"


@pytest.mark.parametrize("period", PERIODS)
def test_hull_lag_on_a_ramp_stays_sub_bar(period: int) -> None:
    """Hull's defining property: near zero lag, and it must not grow with period.

    On a straight ramp the textbook line trails price by well under one period
    (measured: 0.33-1.33 bars for periods 10-55). The swapped spelling trailed by
    5-29 bars, growing roughly as 0.5*period, which is what this test pins shut.
    """
    closes = _ramp()
    slope = closes[1] - closes[0]
    lag_bars = (closes[-1] - hull(closes, period)) / slope

    assert lag_bars < 2.0, f"period={period}: lag {lag_bars:.2f} bars is not sub-bar"
    assert lag_bars > -2.0, f"period={period}: lag {lag_bars:.2f} bars leads price"


def test_hull_flat_series_is_the_flat_price() -> None:
    """On a constant series both WMAs collapse to the constant, so HMA == price.

    Spelling-invariant: both orderings pass, which is why the flat case alone
    could never have caught this bug.
    """
    assert hull([50.0] * 80, 20) == pytest.approx(50.0)


def test_hull_flat_series_cannot_detect_the_swap() -> None:
    """Documents the blind spot: on constant data the two spellings coincide."""
    flat = [50.0] * 80
    assert swapped_hull(flat, 20) == pytest.approx(textbook_hull(flat, 20))


def test_hull_insufficient_data_is_nan() -> None:
    assert np.isnan(hull([1.0, 2.0, 3.0], 20))
