"""Regression tests for the six catalog "dead knob" defects.

Each test perturbs one config knob and asserts the emitted signal series
**changes**. Before the fix, every perturbation here produced byte-identical
output on real data — that is what made these knobs invisible to code review.

The fixtures use deterministic pseudo-random OHLCV (a fixed seed) rather than
live market data, so the tests are reproducible and offline.
"""

from __future__ import annotations

import math
from dataclasses import replace

import pytest

from cryptobot.strategies.catalog.regression_strategy import RegressionConfig, RegressionStrategy
from cryptobot.strategies.catalog.spot_futures_arbitrage import SpotFuturesConfig, SpotFuturesStrategy
from cryptobot.strategies.catalog.stablecoin_peg_strategy import (
    StablecoinPegConfig,
    StablecoinPegStrategy,
)
from cryptobot.strategies.catalog.supertrend_strategy import SupertrendConfig, SupertrendStrategy
from cryptobot.strategies.catalog.trend_mean_reversion import (
    TrendContinuationConfig,
    TrendContinuationStrategy,
)
from cryptobot.strategies.catalog.volume_weighted_momentum import VwMomentumConfig, VwMomentumStrategy

BARS = 900


def _ohlcv(n: int = BARS, seed: int = 7) -> tuple[list[float], list[float], list[float], list[float]]:
    """Deterministic random walk with a mild regime change part-way through.

    A trend + cyclical component is used so both up and down legs are exercised;
    the volume series is deliberately correlated with the size of the moves, so
    volume weighting has something to actually weight.
    """
    closes, highs, lows, volumes = [], [], [], []
    px = 100.0
    state = seed
    for i in range(n):
        state = (1103515245 * state + 12345) % (2**31)
        shock = (state / (2**31) - 0.5) * 4.0
        drift = 0.12 if i < n // 2 else -0.12
        cycle = 6.0 * math.sin(i / 9.0)
        px = max(1.0, px + drift + 0.6 * shock + 0.25 * math.cos(i / 5.0))
        hi = max(px, px + abs(shock) + 0.4)
        lo = min(px, px - abs(shock) - 0.4)
        closes.append(px)
        highs.append(hi)
        lows.append(lo)
        volumes.append(1_000.0 + 4_000.0 * abs(shock) + 500.0 * (1.0 if cycle > 0 else 0.0))
    return closes, highs, lows, volumes


OHLCV = _ohlcv()
CLOSES, HIGHS, LOWS, VOLUMES = OHLCV


def _signal_series(strategy_cls, cfg, ohlcv=OHLCV) -> list[int]:
    """Per-bar target position produced by `feed()` over the whole series."""
    s = strategy_cls(config=cfg)
    out: list[int] = []
    for c, h, lo, v in zip(*ohlcv, strict=False):
        s.feed("SYM", c, h, lo, v)
        out.append(s._pos.get("SYM", 0))
    return out


def _assert_knob_live(strategy_cls, cfg_cls, knob, values, ohlcv=OHLCV) -> None:
    """Perturbing `knob` must change the signal series for every other value."""
    base_cfg = cfg_cls()
    base = _signal_series(strategy_cls, base_cfg, ohlcv)
    assert any(v != 0 for v in base), "baseline never leaves flat - fixture is degenerate"
    default = getattr(base_cfg, knob)
    for value in values:
        if value == default:
            continue  # perturbing a knob to its own value is not a perturbation
        cfg = replace(base_cfg, **{knob: value})
        other = _signal_series(strategy_cls, cfg, ohlcv)
        diff = sum(1 for a, b in zip(base, other, strict=False) if a != b)
        assert diff > 0, f"{strategy_cls.__name__}.{knob}={value!r} produced an identical series (knob is dead)"


# --- 1. Supertrend: ATR was computed and discarded -------------------------


def test_supertrend_period_is_live():
    _assert_knob_live(SupertrendStrategy, SupertrendConfig, "period", [5, 14, 30, 60])


def test_supertrend_multiplier_is_live():
    _assert_knob_live(SupertrendStrategy, SupertrendConfig, "multiplier", [1.0, 2.0, 5.0, 8.0])


def test_supertrend_actually_uses_atr():
    """Flattening the high/low range must change the band, hence the signal.

    Proves the ATR feeds the bands rather than being computed and dropped.
    """
    base = _signal_series(SupertrendStrategy, SupertrendConfig())
    flat = (CLOSES, list(CLOSES), list(CLOSES), VOLUMES)
    other = _signal_series(SupertrendStrategy, SupertrendConfig(), flat)
    assert any(a != b for a, b in zip(base, other, strict=False))


def test_supertrend_multiplier_widens_the_band():
    """A wider band must survive strictly more price crossings (fewer flips)."""
    tight = _signal_series(SupertrendStrategy, SupertrendConfig(period=10, multiplier=1.0))
    wide = _signal_series(SupertrendStrategy, SupertrendConfig(period=10, multiplier=20.0))

    def flips(seq):
        return sum(1 for a, b in zip(seq, seq[1:], strict=False) if a != b)

    assert flips(wide) < flips(tight)


def test_supertrend_tracks_the_direction_of_a_clean_trend():
    """+1 on a rising ramp, -1 on a falling one."""
    up = [100.0 + i for i in range(200)]
    down = [300.0 - i for i in range(200)]

    def _last(bars):
        return _signal_series(
            SupertrendStrategy,
            SupertrendConfig(),
            (bars, list(bars), list(bars), [1000.0] * len(bars)),
        )[-1]

    assert _last(up) == 1
    assert _last(down) == -1


# --- 2. Volume weighted momentum: `vw > 0` was equivalent to `avg > 0` ------


def test_vw_momentum_volume_series_is_live():
    """Replacing the volume series with a constant must change the signal."""
    base = _signal_series(VwMomentumStrategy, VwMomentumConfig())
    const = (CLOSES, HIGHS, LOWS, [1.0] * len(CLOSES))
    other = _signal_series(VwMomentumStrategy, VwMomentumConfig(), const)
    assert any(a != b for a, b in zip(base, other, strict=False))


def test_vw_momentum_period_is_live():
    _assert_knob_live(VwMomentumStrategy, VwMomentumConfig, "period", [5, 10, 40, 60])


def test_vw_momentum_threshold_is_live():
    _assert_knob_live(VwMomentumStrategy, VwMomentumConfig, "threshold", [0.0, 0.02, 0.05])


def test_vw_momentum_differs_from_plain_roc():
    """The signal must not be the plain close-to-close ROC it replaced."""
    from cryptobot.strategies.catalog.volume_weighted_momentum import _vw_roc
    from cryptobot.strategies.indicators import roc

    vw = [_vw_roc(CLOSES[: i + 1], VOLUMES, 20) for i in range(100, len(CLOSES))]
    plain = [roc(CLOSES[: i + 1], 20) for i in range(100, len(CLOSES))]
    assert vw != plain
    assert all(not math.isnan(a) for a in vw)


# --- 3. Stablecoin peg: `entry` was hard-coded to 0.005 --------------------


def test_stablecoin_peg_entry_is_live():
    _assert_knob_live(StablecoinPegStrategy, StablecoinPegConfig, "entry", [0.001, 0.01, 0.03, 0.08])


def test_stablecoin_peg_entry_gates_the_signal():
    """A band wider than every observed deviation must produce a flat series."""
    closes, highs, lows, volumes = _ohlcv(n=400, seed=11)
    wide = _signal_series(
        StablecoinPegStrategy,
        StablecoinPegConfig(period=60, entry=10.0),
        (closes, highs, lows, volumes),
    )
    assert set(wide) == {0}


def test_stablecoin_peg_default_matches_previous_behaviour():
    """The corrected default keeps the original hard-coded 0.5% band."""
    assert StablecoinPegConfig().entry == 0.005


# --- 4. Spot-futures: zscore() ignored `period`, SMA was discarded ---------


def test_spot_futures_period_is_live():
    _assert_knob_live(SpotFuturesStrategy, SpotFuturesConfig, "period", [10, 20, 60, 120])


def test_spot_futures_zscore_window_follows_period():
    """The zscore must be computed over `period` bars, not the whole buffer."""
    from cryptobot.strategies.catalog.spot_futures_arbitrage import _zscore

    windowed = _zscore(CLOSES, 30)
    from cryptobot.strategies.indicators import zscore as buffer_zscore

    assert windowed != pytest.approx(buffer_zscore(CLOSES))
    manual_mean = sum(CLOSES[-30:]) / 30
    manual_sd = (sum((x - manual_mean) ** 2 for x in CLOSES[-30:]) / 30) ** 0.5
    assert windowed == pytest.approx((CLOSES[-1] - manual_mean) / manual_sd)


def test_spot_futures_entry_is_live():
    _assert_knob_live(SpotFuturesStrategy, SpotFuturesConfig, "entry", [0.5, 2.0, 3.0])


# --- 5. Regression: was `sma()` plus a level comparison --------------------


def test_regression_period_is_live():
    _assert_knob_live(RegressionStrategy, RegressionConfig, "period", [5, 10, 40, 80])


def test_regression_is_not_a_plain_sma_comparison():
    """The old rule was `close > sma(period)`; the new one must differ from it."""
    from cryptobot.strategies.indicators import sma

    new = _signal_series(RegressionStrategy, RegressionConfig(period=20))
    old = []
    for i in range(len(CLOSES)):
        m = sma(CLOSES[: i + 1], 20)
        old.append(0 if m != m else (1 if CLOSES[i] > m else -1))
    assert new != old


def test_regression_slope_gate_flips_the_old_buy_high_rule():
    """The fitted slope must veto positions the old `close > sma` rule opened.

    Case A: last close is *above* the fitted level but the fitted slope is
    negative. The old rule bought; the regression rule must stay flat.
    """
    period = 20

    def _last_signal(bars):
        closes = bars * 40
        ohlcv = (closes, list(closes), list(closes), [1000.0] * len(closes))
        return _signal_series(RegressionStrategy, RegressionConfig(period=period), ohlcv)[-1]

    # A: rising-then-falling window ending above its mean -> slope negative.
    bounce_up = [100.0 - 0.5 * i for i in range(period - 1)] + [100.0]
    assert bounce_up[-1] > sum(bounce_up) / period  # old rule would have said long
    assert _last_signal(bounce_up) == 0

    # B: falling-then-rising window ending below its mean -> slope positive.
    bounce_down = [100.0 + 0.5 * i for i in range(period - 1)] + [100.0]
    assert bounce_down[-1] < sum(bounce_down) / period  # old rule would have said short
    assert _last_signal(bounce_down) == 0

    # C: genuine uptrend ending above its mean -> both rules long.
    assert _last_signal([100.0 + 0.5 * i for i in range(period - 1)] + [115.0]) == 1


# --- 6. Trend continuation: `period` was dead, name lied --------------------


def test_trend_continuation_period_is_live():
    _assert_knob_live(
        TrendContinuationStrategy,
        TrendContinuationConfig,
        "period",
        [10, 20, 60, 120],
    )


def test_trend_continuation_zscore_window_follows_period():
    from cryptobot.strategies.catalog.trend_mean_reversion import _zscore

    assert _zscore(CLOSES, 20) != pytest.approx(_zscore(CLOSES, 100))


def test_trend_continuation_keeps_its_original_signal_direction():
    """Renamed, not re-specified: still buys strength (z>entry AND close>sma)."""
    s = TrendContinuationStrategy(config=TrendContinuationConfig(slow=40, period=20, entry=1.5))
    assert s.name == "trend_continuation"
    closes = [100.0 + 0.5 * i for i in range(120)]
    # a persistent uptrend: close above its mean by well over 1.5 sd and above sma(40)
    assert s.signal(closes, closes, closes, [1000.0] * len(closes)) == 1


def test_trend_continuation_backwards_compatible_aliases():
    from cryptobot.strategies.catalog.trend_mean_reversion import (
        TrendMrConfig,
        TrendMrStrategy,
    )

    assert TrendMrStrategy is TrendContinuationStrategy
    assert TrendMrConfig is TrendContinuationConfig


def test_trend_continuation_registry_has_both_keys():
    from cryptobot.strategies.catalog import _REGISTRY

    assert _REGISTRY["trend_continuation"] == _REGISTRY["trend_mean_reversion"]
    assert _REGISTRY["trend_continuation"][0] is TrendContinuationStrategy
