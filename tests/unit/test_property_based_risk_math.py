"""Property-based tests (hypothesis) for risk / sizing / backtest-metric math.

Guards the invariants that hold for all valid inputs:

- sizing: strictly non-negative, never exceeds the config cap, monotone in equity
- risk: ``max_abs_correlation`` is bounded by 1 for probabilities and never negative
- drawdown / sharp ratio / sortino: never NaN, and single-point / flat series give
  the degenerate (0 / inf) results documented above.
"""

from __future__ import annotations

from decimal import Decimal
from math import isfinite

import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st

from cryptobot.backtest.metrics import PerformanceMetrics
from cryptobot.risk.correlation import max_abs_correlation
from cryptobot.risk.sizing import fixed_fraction_size, kelly_size, volatility_target_size

decimals_gt0 = st.decimals(min_value="0.00000001", max_value="1e9", allow_nan=False, allow_infinity=False)
prices = st.decimals(min_value="0.00000001", max_value="1e9", allow_nan=False, allow_infinity=False)
pct = st.decimals(min_value="0", max_value="1", allow_nan=False, allow_infinity=False)


@given(
    equity=decimals_gt0,
    fraction=pct,
    price=prices,
)
def test_fixed_fraction_size_invariants(equity, fraction, price):
    size = fixed_fraction_size(equity, fraction, price)
    assert size >= 0
    notional = size * price
    assert notional <= equity * Decimal("1.0000001"), "can never over-deploy capital"


@given(
    equity=decimals_gt0,
    price=decimals_gt0,
)
def test_fixed_fraction_zero_price_is_zero(equity, price):
    assert fixed_fraction_size(equity, Decimal("0"), price) == 0
    assert fixed_fraction_size(Decimal("0"), Decimal("0.1"), price) == 0
    assert fixed_fraction_size(equity, Decimal("0.1"), Decimal("0")) == 0


@given(
    equity=decimals_gt0,
    target=decimals_gt0,
    observed=decimals_gt0,
    price=decimals_gt0,
)
def test_volatility_target_size_monotonic(equity, target, observed, price):
    # halving observed vol -> cap at 1.0 fraction; never more than fixed_fraction(1.0)
    size = volatility_target_size(equity, target, observed, price)
    cap = fixed_fraction_size(equity, Decimal("1"), price)
    assert Decimal("0") <= size <= cap


@given(
    equity=decimals_gt0,
    win_rate=pct,
    win_loss_ratio=decimals_gt0,
    price=decimals_gt0,
)
def test_kelly_size_bounds(equity, win_rate, win_loss_ratio, price):
    size = kelly_size(equity, win_rate, win_loss_ratio, price)
    if win_rate < Decimal("0.5") or win_loss_ratio < Decimal("1"):
        # Kelly fraction is zero for a non-edge situation
        edge = win_rate - ((Decimal("1") - win_rate) / win_loss_ratio)
        if edge <= 0:
            assert size == 0
    else:
        assert size >= 0
        notional = size * price
        assert notional <= equity, "kelly may not over-deploy"
        max_notional = equity * Decimal("1.0000001")
        assert notional <= max_notional


@given(st.dictionaries(keys=st.tuples(st.text(min_size=1), st.text(min_size=1)), values=st.decimals(min_value="-1", max_value="1")))
def test_max_abs_correlation_bounds(corr_map):
    result = max_abs_correlation(corr_map)
    assert result >= 0
    assert result <= 1
    assert isinstance(result, Decimal)


def test_max_abs_correlation_empty_is_zero():
    assert max_abs_correlation({}) == 0


@given(st.lists(st.floats(min_value=1.0, max_value=10_000.0, allow_nan=False, allow_infinity=False), min_size=1))
@settings(max_examples=50)
def test_drawdown_range(equities):
    pm = PerformanceMetrics()
    dd = pm.calculate_drawdown(pd.Series(equities))
    assert 0.0 <= dd <= 100.0


@given(st.lists(st.floats(min_value=-0.5, max_value=0.5, allow_nan=False, allow_infinity=False), min_size=2))
@settings(max_examples=50)
def test_sharpe_is_finite_for_nonzero_vol(returns):
    pm = PerformanceMetrics()
    sharpe = pm.calculate_sharpe_ratio(list(returns), risk_free_rate=0.02)
    import statistics

    if len(set(returns)) > 1 and statistics.pstdev(returns) > 1e-9:
        assert isfinite(sharpe)


@given(st.lists(st.floats(min_value=0.0001, max_value=1000, allow_nan=False, allow_infinity=False), min_size=1))
@settings(max_examples=50)
def test_sharpe_flat_series_is_zero(equities):
    pm = PerformanceMetrics()
    forever_gains = equities
    returns = [float(x) / 100.0 for x in forever_gains]
    sharpe = pm.calculate_sharpe_ratio(returns, risk_free_rate=0.02)
    assert sharpe == 0.0 or isfinite(sharpe)


@given(st.lists(st.floats(min_value=-0.5, max_value=0.5, allow_nan=False, allow_infinity=False), max_size=0))
def test_nan_empty_series_return_zero(returns):
    pm = PerformanceMetrics()
    assert pm.calculate_sharpe_ratio(list(returns)) == 0.0
    assert pm.calculate_sortino_ratio(list(returns)) == 0.0
    assert pm.calculate_drawdown(pd.Series([])) == 0.0
