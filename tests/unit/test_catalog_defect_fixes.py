"""Defect tests for the catalog strategies fixed after the 27-agent audit.

Each test pins a specific defect that was verified mechanically on NSE data,
so a regression reintroduces the old behaviour rather than just changing a
number.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from cryptobot.strategies.catalog.adx_trend import (
    AdxTrendConfig,
    AdxTrendStrategy,
    wilder_adx,
    wilder_di,
)
from cryptobot.strategies.catalog.atr_trailing_stop import (
    AtrTrailingConfig,
    AtrTrailingStrategy,
)
from cryptobot.strategies.catalog.cointegration_strategy import (
    CointegrationConfig,
    CointegrationStrategy,
    _hedge_ratio,
    cointegration_zscore,
)
from cryptobot.strategies.catalog.correlation_gate import (
    CorrGateConfig,
    CorrGateStrategy,
    _pearson,
)
from cryptobot.strategies.catalog.donchian_channel import DonchianConfig, DonchianStrategy
from cryptobot.strategies.catalog.flag_pattern import FlagConfig, FlagStrategy
from cryptobot.strategies.catalog.gap_strategy import GapConfig, GapStrategy
from cryptobot.strategies.catalog.gaussian_strategy import (
    GaussianConfig,
    GaussianStrategy,
)


def _walk(seed: int, n: int, vol: float = 0.014, width: float = 0.020) -> tuple[np.ndarray, ...]:
    """Deterministic OHLC random walk calibrated to NSE daily bars.

    Real NSE 1d: ~1.4% daily return vol, ~3.2% mean (high-low)/close. Narrow
    synthetic bars would make range-based statistics look far too trigger-happy.
    """
    rng = np.random.default_rng(seed)
    closes = 100 * np.exp(np.cumsum(rng.normal(0, vol, n)))
    highs = closes * (1 + np.abs(rng.normal(0, width, n)))
    lows = closes * (1 - np.abs(rng.normal(0, width, n)))
    return closes, highs, lows


def _run(strategy, closes, highs, lows):
    """Feed bars one at a time; return the signal series after warmup."""
    out = []
    c: list[float] = []
    h: list[float] = []
    low: list[float] = []
    v: list[float] = []
    for i in range(len(closes)):
        c.append(float(closes[i]))
        h.append(float(highs[i]))
        low.append(float(lows[i]))
        v.append(1.0)
        strategy.feed("X", closes[i], highs[i], lows[i], 1.0)
        if len(c) >= strategy.warmup(c):
            out.append(strategy.signal(c, h, low, v))
    return out


# --------------------------------------------------------------------------- #
# 1. adx_trend -- previously `return 1 if closes[-1] > closes[-2] else -1`
# --------------------------------------------------------------------------- #


def test_adx_matches_hand_computed_wilder_values():
    """Wilder's algorithm on a hand-worked 7-bar series (period=3).

    TR        = [_, 1.5, 1.5, 1.5, 2.0, 2.0, 1.0]
    +DM       = [_, 1.0, 1.0, 0.0, 1.0, 1.0, 0.0]
    -DM       = [_, 0.0, 0.0, 0.5, 0.0, 0.0, 0.0]
    RMA(TR)   = [1.5, 3.0, 4.0, 3.666667]
    +DI       = [44.444444, 48.148148, 49.074074, 35.690228]
    -DI       = [11.111111,  3.703704,  1.851852,  1.346793]
    DX        = [60.0, 85.714286, 92.727273, 92.727273]
    ADX       = mean(DX[:3]) = 79.480519, then Wilder-smoothed -> 83.896104
    """
    highs = [10.0, 11.0, 12.0, 12.0, 13.0, 14.0, 14.0]
    lows = [9.0, 10.0, 11.0, 10.5, 11.0, 12.0, 13.0]
    closes = [9.5, 10.5, 11.5, 11.0, 12.5, 13.5, 13.8]

    plus_di, minus_di = wilder_di(highs, lows, closes, 3)
    assert plus_di == pytest.approx(35.690228, abs=1e-5)
    assert minus_di == pytest.approx(1.346793, abs=1e-5)
    assert wilder_adx(highs, lows, closes, 3) == pytest.approx(83.896104, abs=1e-5)


def test_adx_is_nan_before_enough_bars():
    """ADX needs 2*period bars; it must not fabricate a value from less."""
    highs = [10.0 + i for i in range(10)]
    lows = [9.0 + i for i in range(10)]
    closes = [9.5 + i for i in range(10)]
    assert wilder_adx(highs, lows, closes, 14) != wilder_adx(highs, lows, closes, 14)  # NaN


def test_adx_responds_to_period():
    """config.period was provably dead: period=14 and period=200 gave identical
    signals. Period must now drive the smoothing windows."""
    closes, highs, lows = _walk(21, 600)
    sigs = {}
    adxs = {}
    for period in (5, 14, 40):
        strat = AdxTrendStrategy(AdxTrendConfig(period=period))
        sigs[period] = _run(strat, closes, highs, lows)
        c, h, low = [], [], []
        for i in range(len(closes)):
            c.append(float(closes[i]))
            h.append(float(highs[i]))
            low.append(float(lows[i]))
        adxs[period] = wilder_adx(h, low, c, period)

    assert len(set(sigs[5])) > 1 and len(set(sigs[14])) > 1
    assert sigs[5] != sigs[14], "period=5 and period=14 must not produce identical signals"
    assert adxs[5] != adxs[14] != adxs[40]


def test_adx_signal_is_not_bar_direction():
    """The old return was `sign(close[t]-close[t-1])` on 370/370 bars."""
    closes, highs, lows = _walk(21, 600)
    strat = AdxTrendStrategy(AdxTrendConfig(period=14, threshold=25.0))
    sigs = _run(strat, closes, highs, lows)

    bar = []
    c = []
    for x in closes:
        c.append(float(x))
        if len(c) >= strat.warmup(c):
            bar.append(1 if c[-1] > c[-2] else -1)
    agree = sum(1 for a, b in zip(sigs, bar) if a == b)
    assert agree < len(sigs) * 0.9, "signal must not be the bar's sign"


def test_adx_trend_follows_dominant_directional_index():
    """A clean uptrend has +DI > -DI and ADX > threshold -> long."""
    strat = AdxTrendStrategy(AdxTrendConfig(period=5, threshold=20.0))
    n = 60
    closes = np.array([100.0 + i for i in range(n)])
    highs = closes + 0.4
    lows = closes - 0.4
    sigs = _run(strat, closes, highs, lows)
    assert sigs and sigs[-1] == 1
    plus_di, minus_di = wilder_di(list(highs), list(lows), list(closes), 5)
    assert plus_di > minus_di


# --------------------------------------------------------------------------- #
# 2. donchian -- channel included today's bar, so a breakout could never fire
# --------------------------------------------------------------------------- #


def test_donchian_channel_excludes_current_bar():
    """max(highs[-p:]) includes today, so `close >= hh` only held when the close
    sat exactly on the day's high (0.25% fire rate, 0.00% on one window)."""
    strat = DonchianStrategy(DonchianConfig(period=5))
    # 5 prior bars at 10, then a bar whose high == close: not a breakout.
    closes = [10.0] * 5 + [10.0]
    highs = [10.0] * 5 + [10.0]
    lows = [10.0] * 6
    assert strat.signal(closes, highs, lows, [1.0] * 6) == 0

    # A close strictly above the prior highs IS a breakout.
    assert strat.signal([10.0] * 5 + [10.5], [10.0] * 5 + [10.5], [10.0] * 6, [1.0] * 6) == 1
    assert strat.signal([10.0] * 5 + [9.5], [10.0] * 5 + [9.5], [10.0] * 5 + [9.5], [1.0] * 6) == -1


def test_donchian_fires_at_a_sensible_rate():
    """Must be a few percent, not 0.25%."""
    closes, highs, lows = _walk(7, 2000)
    strat = DonchianStrategy(DonchianConfig(period=20))
    sigs = _run(strat, closes, highs, lows)
    rate = sum(1 for s in sigs if s != 0) / len(sigs)
    assert 0.01 < rate < 0.35, f"fire rate {rate:.4%} is not a usable breakout rate"


# --------------------------------------------------------------------------- #
# 3. correlation_gate -- contained no correlation statistic at all
# --------------------------------------------------------------------------- #


def test_corr_gate_computes_real_correlation():
    """The statistic must equal a hand-computed Pearson correlation.

    Built from varying returns (a pure geometric ramp has zero-variance returns,
    so its correlation is undefined).
    """
    rng = np.random.default_rng(31)
    benchmark = list(100 * np.exp(np.cumsum(rng.normal(0, 0.01, 120))))
    noise = rng.normal(0, 0.002, 120)
    symbol = list(benchmark * np.exp(noise))
    strat = CorrGateStrategy(CorrGateConfig(period=20, min_correlation=0.3))
    strat.set_benchmark(benchmark)
    corr = strat.rolling_correlation(symbol)

    own = [symbol[i] / symbol[i - 1] - 1.0 for i in range(1, len(symbol))][-20:]
    market = [benchmark[i] / benchmark[i - 1] - 1.0 for i in range(1, len(benchmark))][-20:]
    assert corr == pytest.approx(_pearson(own, market))
    assert corr > 0.9


def test_corr_gate_pearson_matches_hand_computation():
    xs = [1.0, 2.0, 3.0, 4.0, 5.0]
    ys = [2.0, 4.0, 5.0, 4.0, 5.0]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = math.sqrt(sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys))
    assert _pearson(xs, ys) == pytest.approx(num / den)


def test_corr_gate_blocks_uncorrelated_and_trades_correlated():
    """The gate must actually gate: identical trend legs, different outcomes."""
    rng = np.random.default_rng(9)
    benchmark = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, 1500)))
    beta_half = benchmark**0.5 * np.exp(np.cumsum(rng.normal(0, 0.008, 1500)))
    noise = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, 1500)))

    def fire(series, min_corr):
        strat = CorrGateStrategy(CorrGateConfig(period=20, min_correlation=min_corr))
        strat.set_benchmark(benchmark)
        return _run(strat, series, series * 1.001, series * 0.999)

    open_gate = fire(beta_half, 0.0)
    gated = fire(beta_half, 0.9)
    uncorrelated = fire(noise, 0.9)

    assert sum(1 for s in open_gate if s != 0) > sum(1 for s in gated if s != 0)
    # A 0.9 threshold is unreachable for these series, so the gate is shut.
    assert all(s == 0 for s in gated), "min_correlation=0.9 must block a beta<1 name"
    assert all(s == 0 for s in uncorrelated), "an uncorrelated name must never pass the gate"


def test_corr_gate_threshold_is_live():
    """Tightening min_correlation must monotonically reduce the trade count."""
    rng = np.random.default_rng(9)
    benchmark = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, 1500)))
    beta_half = benchmark**0.5 * np.exp(np.cumsum(rng.normal(0, 0.008, 1500)))

    counts = []
    for mc in (0.0, 0.3, 0.6):
        strat = CorrGateStrategy(CorrGateConfig(period=20, min_correlation=mc))
        strat.set_benchmark(benchmark)
        sigs = _run(strat, beta_half, beta_half * 1.001, beta_half * 0.999)
        counts.append(sum(1 for s in sigs if s != 0))
    assert counts[0] > counts[1] >= counts[2]


# --------------------------------------------------------------------------- #
# 4. flag_pattern -- config.period was dead; geometry was hard-coded to 3 bars
# --------------------------------------------------------------------------- #


def test_flag_responds_to_period():
    closes, highs, lows = _walk(3, 4000)
    sigs = {
        p: _run(FlagStrategy(FlagConfig(period=p)), closes, highs, lows)
        for p in (3, 5, 10, 20)
    }
    assert sigs[3] != sigs[10], "period must change the pattern geometry"
    rates = [sum(1 for s in sigs[p] if s != 0) / len(sigs[p]) for p in (3, 5, 10, 20)]
    assert rates[0] > rates[-1], "a longer period must produce fewer, wider flags"


def test_flag_needs_pole_consolidation_and_breakout():
    """A bare 3-bar chain is no longer enough: no pole, no signal."""
    strat = FlagStrategy(FlagConfig(period=5))
    n = 2 * 5 + 1
    rising = [100.0 + i for i in range(n)]  # pole and flag both rising, no tight flag
    highs = [x + 0.1 for x in rising]
    lows = [x - 0.1 for x in rising]
    assert strat.signal(rising, highs, lows, [1.0] * n) == 0


def test_flag_signals_a_real_breakout():
    strat = FlagStrategy(FlagConfig(period=3))
    pole = [100.0 + i for i in range(3)]  # up-pole
    flag = [102.5, 102.7, 102.6]  # tight consolidation
    closes = pole + flag + [103.5]
    highs = [x + 0.05 for x in closes]
    lows = [x - 0.05 for x in closes]
    assert strat.signal(closes, highs, lows, [1.0] * len(closes)) == 1


# --------------------------------------------------------------------------- #
# 5. gaussian -- zscore() consumed the whole 300-bar deque; period was decorative
# --------------------------------------------------------------------------- #


def test_gaussian_uses_only_the_last_period_bars():
    """The old z-score spanned the entire buffer, so it was a fixed 300-bar
    statistic no matter what `period` said."""
    strat = GaussianStrategy(GaussianConfig(period=5))
    closes = [100.0 + i for i in range(20)] + [200.0]
    window = closes[-5:]
    mean = sum(window) / 5
    sd = (sum((c - mean) ** 2 for c in window) / 5) ** 0.5
    expected = (closes[-1] - mean) / sd
    assert strat.signal(closes, [0.0] * len(closes), [0.0] * len(closes), [0.0] * len(closes)) == (
        -1 if expected >= 0.8 else (1 if expected <= -0.8 else 0)
    )

    # A long flat history must not change a short-window signal.
    padded = [500.0] * 300 + closes
    assert (
        strat.signal(padded, [0.0] * len(padded), [0.0] * len(padded), [0.0] * len(padded))
        == strat.signal(
            closes, [0.0] * len(closes), [0.0] * len(closes), [0.0] * len(closes)
        )
    )


def test_gaussian_responds_to_period():
    closes, highs, lows = _walk(11, 4000)
    sigs = {
        p: _run(GaussianStrategy(GaussianConfig(period=p)), closes, highs, lows)
        for p in (10, 30, 120)
    }
    assert sigs[10] != sigs[30]
    rates = [sum(1 for s in sigs[p] if s != 0) / len(sigs[p]) for p in (10, 30, 120)]
    assert all(0.0 < r < 1.0 for r in rates)


# --------------------------------------------------------------------------- #
# 6. cointegration -- was single-name z-score on a trending price
# --------------------------------------------------------------------------- #


def test_hedge_ratio_recovers_known_beta():
    """For log(A) = beta*log(B) + c, OLS must recover beta."""
    b = [100.0 * (1.01**i) for i in range(200)]
    for beta in (0.5, 1.0, 2.0):
        a = [math.exp(beta * math.log(x) + 1.0) for x in b]
        assert _hedge_ratio([math.log(x) for x in a], [math.log(x) for x in b]) == pytest.approx(
            beta, abs=1e-6
        )


def test_cointegration_spread_is_stationary_for_a_cointegrating_pair():
    """The spread of a cointegrating pair must be tighter than that of two
    independent walks -- that is the whole point of trading the spread."""
    rng = np.random.default_rng(4)
    b = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, 800)))
    a = np.exp(2.0 * np.log(b) + 1.0 + rng.normal(0, 0.004, 800))
    b2 = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, 800)))
    a2 = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, 800)))

    def spread_vol(x, y):
        beta = _hedge_ratio([math.log(v) for v in x], [math.log(v) for v in y])
        spread = [math.log(p) - beta * math.log(q) for p, q in zip(x, y)]
        return float(np.std(np.diff(spread)))

    assert spread_vol(list(a), list(b)) < 0.8 * spread_vol(list(a2), list(b2))


def test_cointegration_trades_the_pair_and_is_flat_single_name():
    rng = np.random.default_rng(4)
    b = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, 800)))
    a = np.exp(2.0 * np.log(b) + 1.0 + rng.normal(0, 0.004, 800))

    strat = CointegrationStrategy(CointegrationConfig(period=30, entry=1.0))
    strat.set_leg_b("B")
    orders_a, orders_b = [], []
    for i in range(len(a)):
        oa = strat.feed("A", float(a[i]), float(a[i]), float(a[i]), 1.0)
        ob = strat.feed("B", float(b[i]), float(b[i]), float(b[i]), 1.0)
        if oa is not None:
            orders_a.append(oa.side.value)
        if ob is not None:
            orders_b.append(ob.side.value)
    assert orders_a and orders_b, "a real pair must produce trades on both legs"
    # The two legs must be mirror images: long the cheap leg, short the rich one.
    assert orders_a[0] != orders_b[0]

    # Single name -> correctly flat; it must not fall back to a single-name proxy.
    single = CointegrationStrategy(CointegrationConfig(period=30, entry=1.0))
    c: list[float] = []
    fired = False
    for i in range(300):
        single.feed("A", float(a[i]), 0.0, 0.0, 1.0)
        c.append(float(a[i]))
        if len(c) >= single.warmup(c):
            if single.signal(c, [0.0] * len(c), [0.0] * len(c), [0.0] * len(c)) != 0:
                fired = True
    assert not fired, "with no second leg the pairs strategy must stay flat"


def test_cointegration_zscore_uses_the_windowed_spread():
    a = [100.0 * (1.01**i) for i in range(60)]
    b = [100.0 * (1.01**i) for i in range(60)]
    z = cointegration_zscore(a, b, 30)
    assert z == z  # not NaN
    assert abs(z) < 1e-6, "a perfectly cointegrating pair has a zero spread"


# --------------------------------------------------------------------------- #
# 7. gap -- computed a close-to-close return, and threshold=0.0 was a no-op
# --------------------------------------------------------------------------- #


def test_gap_uses_open_not_close_to_close():
    """The old line 30 was `(closes[-1]-closes[-2])/closes[-2]`.
    A bar that gaps up at the open but closes flat must read as a gap."""
    strat = GapStrategy(GapConfig(period=1, threshold=0.0))
    closes = [100.0, 100.0]  # no close-to-close move at all
    highs = [100.0, 103.0]
    lows = [100.0, 101.0]  # whole bar traded above the prior close -> gapped up
    assert strat.gap(closes, lows, highs) > 0.0
    assert strat.signal(closes, highs, lows, [1.0] * 2) == 1

    # Exact open path: open/prev_close - 1.
    strat2 = GapStrategy(GapConfig(period=1, threshold=0.0))
    strat2.feed("X", 100.0, 100.0, 100.0, 1.0, open=100.0)
    strat2.feed("X", 100.0, 103.0, 101.0, 1.0, open=105.0)
    assert strat2.gap([100.0, 100.0], [100.0, 101.0], [100.0, 103.0]) == pytest.approx(0.05)


def test_gap_threshold_default_is_not_degenerate():
    """threshold=0.0 fired on 49% of bars. The default must be a real gap."""
    assert GapConfig().threshold > 0.0
    closes, highs, lows = _walk(13, 3000)
    strat = GapStrategy(GapConfig(period=1))
    sigs = _run(strat, closes, highs, lows)
    rate = sum(1 for s in sigs if s != 0) / len(sigs)
    assert rate < 0.30, f"default threshold still fires on {rate:.2%} of bars"
    assert rate > 0.0


# --------------------------------------------------------------------------- #
# 8. atr_trailing_stop -- contained no trailing stop at all
# --------------------------------------------------------------------------- #


def test_atr_trailing_keeps_a_peak_and_a_stop():
    """There was no peak, no trail and no stop: just an SMA +/- k*ATR band."""
    strat = AtrTrailingStrategy(AtrTrailingConfig(period=5, multiplier=2.0))
    bars = [(10.0, 10.2, 9.8)] * 5 + [(11.0, 11.2, 10.8)] + [(10.9, 11.0, 10.8)] * 3
    for close, high, low in bars:
        strat.feed("X", close, high, low, 1.0)
    state = strat._trail["X"]
    assert state[0] == 1, "a close above the prior high must open a long"
    # The peak is the extreme reached since entry -- the entry bar's high.
    assert state[1] == pytest.approx(11.2)

    # The stop ratchets: peak (held) minus multiplier*ATR rises as ATR decays.
    from cryptobot.strategies.indicators import atr as _atr

    highs, lows, closes = [], [], []
    atrs = []
    for close, high, low in bars:
        highs.append(high)
        lows.append(low)
        closes.append(close)
        atrs.append(_atr(highs, lows, closes, 5))
    assert atrs[-3] > atrs[-1], "ATR must be decaying across the flag"
    stops = [11.2 - 2.0 * a for a in atrs[-3:]]
    assert stops[0] < stops[-1], "a falling ATR must ratchet the stop up"


def test_atr_trailing_exits_when_price_breaks_the_stop():
    """Enter long on a breakout, then drop through the trail -> flat."""
    strat = AtrTrailingStrategy(AtrTrailingConfig(period=5, multiplier=2.0))
    bars = [(10.0, 10.2, 9.8)] * 5 + [(11.0, 11.2, 10.8)] + [(10.9, 11.0, 10.8)] * 3
    for close, high, low in bars:
        strat.feed("X", close, high, low, 1.0)
    assert strat._trail["X"][0] == 1

    # A drop that stays inside the prior-low channel breaks the trail, not the
    # channel -- so the exit is the stop, not a flip.
    order = strat.feed("X", 9.9, 9.95, 9.85, 1.0)
    assert order is not None and order.side.value == "SELL"
    assert order.reduce_only is True, "exiting a trailing stop must be reduce-only"
    assert strat._trail["X"][0] == 0, "state must reset on exit"


def test_atr_trailing_multiplier_is_live():
    closes, highs, lows = _walk(17, 800)
    wide = _run(
        AtrTrailingStrategy(AtrTrailingConfig(period=14, multiplier=2.0)),
        closes,
        highs,
        lows,
    )
    tight = _run(
        AtrTrailingStrategy(AtrTrailingConfig(period=14, multiplier=0.5)),
        closes,
        highs,
        lows,
    )
    assert wide != tight, "multiplier must control how tight the trail is"
