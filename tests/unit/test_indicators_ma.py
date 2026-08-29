"""Regression tests for DEMA/TEMA/HULL/KAMA indicators.

These guard against the catalog-inflation bug (#54) where dema/hull/kama/tema
strategies were plain EMA stubs. The indicators must be mathematically distinct
from EMA and return finite, well-defined values.
"""
import numpy as np
import pytest

from cryptobot.strategies.indicators import dema, tema, hull, kama, ema


def _trend(n=80, start=100.0, end=200.0):
    return list(np.linspace(start, end, n))


def test_indicators_distinct_from_ema_on_trend():
    closes = _trend()
    e = ema(closes, 20)
    d = dema(closes, 20)
    t = tema(closes, 20)
    h = hull(closes, 20)
    k = kama(closes, 20)
    # All finite and in a sane range.
    for v in (d, t, h, k):
        assert np.isfinite(v)
        assert abs(v) < 1e6
    # On an uptrend DEMA/TEMA reduce lag and sit above EMA; they are not equal to it.
    assert d != pytest.approx(e)
    assert t != pytest.approx(e)
    assert d > e
    assert t > d
    # HMA and KAMA are also distinct from EMA.
    assert h != pytest.approx(e)
    assert k != pytest.approx(e)


def test_flat_series_returns_last_close():
    flat = [50.0] * 60
    for fn in (dema, tema, hull, kama):
        assert fn(flat, 10) == pytest.approx(50.0)


def test_insufficient_data_returns_nan():
    short = [1.0, 2.0, 3.0]
    for fn in (dema, tema, hull, kama):
        assert fn(short, 10) != fn(short, 10)  # NaN != NaN


def test_hull_matches_reference_implementation():
    # Independent WMA-based HMA reference on a noisy-but-monotone series.
    closes = _trend(120)
    rng = np.random.default_rng(0)
    closes = [c + rng.normal(0, 0.5) for c in closes]

    def wma(vals, p):
        a = np.asarray(vals[-p:], dtype=float)
        w = np.arange(1, p + 1, dtype=float)
        return float(np.sum(a * w) / w.sum())

    period = 20
    half = period // 2
    sqrt_p = int(round(period ** 0.5))
    raw = [2 * wma(closes[: i + 1], period) - wma(closes[: i + 1], half) for i in range(len(closes) - sqrt_p, len(closes))]
    ref = wma(raw, sqrt_p)

    assert hull(closes, period) == pytest.approx(ref, rel=1e-9)


def test_kama_tracks_strong_trend():
    # On a strong, low-noise trend KAMA should sit close to the latest price.
    closes = _trend(120)
    k = kama(closes, 20)
    assert np.isfinite(k)
    assert abs(k - closes[-1]) < 5.0


def test_kama_default_period_requires_extra_bar():
    # kama needs period+1 points; exactly `period` points must be NaN.
    closes = _trend(20)  # 20 points, period default 20
    assert kama(closes) != kama(closes)  # NaN
    assert np.isfinite(kama(_trend(21)))
