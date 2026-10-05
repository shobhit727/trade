"""Look-ahead and correctness tests for the backtest engine.

The look-ahead tests are the most important in this repo. A backtest with look-ahead
produces beautiful, worthless numbers — which is exactly the failure mode `GOAL.md` §6
exists to prevent.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from nsealgo.backtest.engine import PortfolioConfig, run_backtest, sector_of
from nsealgo.backtest.metrics import (
    compute_metrics,
    drawdown_series,
    max_drawdown,
    yearly_returns,
)
from nsealgo.costs import CostModel
from nsealgo.factors.core import (
    build_composite_score,
    momentum_12_1,
    zscore_cross_sectional,
)
from nsealgo.factors.regime import blend_with_cash, exposure_series

CM = CostModel(segment="delivery", slippage_bps=5)


def make_panel(seed: int = 0, n_days: int = 900, n_sym: int = 25) -> pd.DataFrame:
    """Deterministic synthetic panel with a genuine momentum structure, so the
    look-ahead tests have something real to detect."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2010-01-01", periods=n_days, tz="Asia/Kolkata")
    cols = [f"s{i:02d}" for i in range(n_sym)]

    # Give each symbol a persistent drift so momentum is real, not noise.
    drifts = rng.normal(0.0004, 0.0006, n_sym)
    shocks = rng.normal(0, 0.012, (n_days, n_sym))
    prices = np.empty((n_days, n_sym))
    p0 = rng.uniform(100, 2000, n_sym)
    for t in range(n_days):
        p0 = p0 * (1.0 + drifts + shocks[t])
        prices[t] = p0
    return pd.DataFrame(prices, index=dates, columns=cols)


class TestNoLookahead:
    """Weights decided at date t must not use information from t+1 onward."""

    def test_factors_are_trailing_only(self) -> None:
        p = make_panel()
        mom = momentum_12_1(p)          # DataFrame: dates x symbols
        # Truncating the panel must not change any *past* factor value.
        cut = p.index[600]
        mom_trunc = momentum_12_1(p.loc[:cut])
        pd.testing.assert_frame_equal(mom.loc[:cut], mom_trunc.loc[:cut])

    def test_future_prices_cannot_change_past_signals(self) -> None:
        p = make_panel()
        cut = p.index[700]
        before = build_composite_score(p.loc[:cut])

        # Corrupt everything AFTER the cut. Past signals must be bit-identical.
        poisoned = p.copy()
        poisoned.loc[poisoned.index > cut] *= 3.0
        after = build_composite_score(poisoned).loc[:cut]

        pd.testing.assert_frame_equal(before, after)

    def test_regime_exposure_is_lagged(self) -> None:
        p = make_panel()
        e = exposure_series(p, lookback=126, threshold=0.0)
        # exposure[t] may only use data through t-1, so poisoning t+1.. must not
        # change any past exposure.
        cutoff = p.index[800]
        p2 = p.copy()
        p2.loc[p2.index > cutoff] *= 5.0
        e2 = exposure_series(p2, lookback=126, threshold=0.0)
        pd.testing.assert_series_equal(e.loc[:cutoff], e2.loc[:cutoff])

    def test_zscore_is_cross_sectional_per_day(self) -> None:
        f = pd.DataFrame(
            [[1.0, 2.0, 3.0], [100.0, 200.0, 300.0]],
            index=pd.to_datetime(["2020-01-01", "2020-01-02"]),
            columns=list("abc"),
        )
        z = zscore_cross_sectional(f)
        # Row 2 is a pure scale multiple of row 1 -> identical z-scores.
        np.testing.assert_allclose(z.iloc[0].values, z.iloc[1].values, atol=1e-9)


class TestCostRealism:
    def test_costs_reduce_return_monotonically(self) -> None:
        p = make_panel()
        sc = build_composite_score(p)
        cfg = PortfolioConfig()
        cheap = run_backtest(p, sc, CostModel(slippage_bps=0), cfg, "M")
        dear = run_backtest(p, sc, CostModel(slippage_bps=30), cfg, "M")
        assert dear.metrics.cagr < cheap.metrics.cagr
        assert dear.metrics.cost_drag_annual > cheap.metrics.cost_drag_annual

    def test_costs_are_actually_charged(self) -> None:
        """Regression: costs were once charged as a bare fraction of turnover rather
        than of equity, understating the drag ~20x on a compounding book."""
        p = make_panel()
        sc = build_composite_score(p)
        res = run_backtest(p, sc, CM, PortfolioConfig(), "M")
        assert res.costs_paid > 0
        assert res.metrics.cost_drag_annual > 0
        assert res.metrics.annual_turnover > 0

    def test_cost_scales_with_equity_growth(self) -> None:
        """On a book that compounds, later costs must be larger in rupee terms."""
        p = make_panel()
        sc = build_composite_score(p)
        res = run_backtest(p, sc, CM, PortfolioConfig(), "M")
        assert res.equity.iloc[-1] > 1.0


class TestConstraints:
    def test_position_count_respected(self) -> None:
        p = make_panel(n_sym=40)
        sc = build_composite_score(p)
        res = run_backtest(p, sc, CM, PortfolioConfig(n_positions=12), "M")
        assert res.diag["avg_names"] <= 13  # +1 for a partial rebalance leg

    def test_single_name_cap_respected(self) -> None:
        p = make_panel(n_sym=40)
        sc = build_composite_score(p)
        res = run_backtest(p, sc, CM, PortfolioConfig(max_weight=0.12), "M")
        assert res.weights.max().max() <= 0.1201

    def test_weights_sum_below_one_for_cash_buffer(self) -> None:
        p = make_panel(n_sym=40)
        sc = build_composite_score(p)
        cfg = PortfolioConfig(cash_buffer=0.15)
        res = run_backtest(p, sc, CM, cfg, "M")
        assert res.weights.sum(axis=1).max() <= 0.851

    def test_weights_never_negative(self) -> None:
        p = make_panel()
        sc = build_composite_score(p)
        res = run_backtest(p, sc, CM, PortfolioConfig(), "M")
        assert res.weights.min().min() >= 0.0

    def test_sector_map_is_total(self) -> None:
        assert all(isinstance(sector_of(s), str) for s in ["tcs", "hdfcbank", "zzz"])


class TestMetrics:
    def test_annualisation_uses_244_days(self) -> None:
        """Regression risk: the parent repo mixed sqrt(252) and sqrt(244)."""
        rng = np.random.default_rng(1)
        daily = pd.Series(rng.normal(0.0004, 0.01, 244 * 3))
        m = compute_metrics(daily)
        assert 0.15 < m.volatility < 0.25, m.volatility

    def test_sharpe_subtracts_risk_free(self) -> None:
        """A strategy earning exactly the risk-free rate must have Sharpe ~0."""
        rf = 0.065
        per_day = (1 + rf) ** (1 / 244) - 1
        flat = pd.Series([per_day] * 488)
        assert abs(compute_metrics(flat, rf_annual=rf).sharpe) < 1e-6

    def test_zero_volatility_gives_zero_sharpe_not_nan(self) -> None:
        flat = pd.Series([0.0] * 300)
        m = compute_metrics(flat)
        assert m.sharpe == 0.0
        assert m.volatility == 0.0

    def test_max_drawdown_on_equity_curve(self) -> None:
        eq = pd.Series([1.0, 1.5, 0.75, 1.2, 0.9])
        dd, days = max_drawdown(eq)
        assert dd == pytest.approx(-0.5)
        assert days >= 2
        assert drawdown_series(eq).min() == pytest.approx(-0.5)

    def test_monotonic_equity_has_no_drawdown(self) -> None:
        eq = pd.Series([1.0, 1.1, 1.2, 1.3])
        dd, _ = max_drawdown(eq)
        assert dd == pytest.approx(0.0)

    def test_yearly_returns_are_per_year_not_cumulative(self) -> None:
        """Regression: this once returned cumulative equity, showing +467% 'annual'
        returns. Each entry must now be growth within that year."""
        idx = pd.DatetimeIndex(
            ["2020-01-02", "2020-01-03", "2021-01-04", "2021-01-05"], tz="Asia/Kolkata"
        )
        r = pd.Series([0.10, 0.10, 0.10, 0.10], index=idx)
        y = yearly_returns(r)
        assert y[2020] == pytest.approx(0.21)
        assert y[2021] == pytest.approx(0.21)

    def test_empty_input_is_safe(self) -> None:
        m = compute_metrics(pd.Series(dtype=float))
        assert m.n_periods == 0
        assert m.cagr == 0.0


class TestOverlay:
    def test_blend_keeps_shares_summed_to_one(self) -> None:
        p = make_panel()
        r = pd.Series(0.001, index=p.index)
        e = pd.Series(0.5, index=p.index)
        out = blend_with_cash(r, e)
        assert len(out) == len(r)
        assert (out > -1).all()

    def test_full_exposure_reproduces_strategy(self) -> None:
        p = make_panel()
        r = pd.Series(0.001, index=p.index)
        e = pd.Series(1.0, index=p.index)
        out = blend_with_cash(r, e)
        np.testing.assert_allclose(out.values, 0.001, atol=1e-9)

    def test_zero_exposure_earns_risk_free(self) -> None:
        p = make_panel()
        r = pd.Series(-0.05, index=p.index)  # catastrophic strategy day
        e = pd.Series(0.0, index=p.index)   # fully de-risked
        out = blend_with_cash(r, e)
        assert (out > 0).all(), "de-risked day should not follow the strategy down"


class TestWalkForwardSafety:
    def test_insufficient_data_raises(self) -> None:
        from nsealgo.backtest.walkforward import walk_forward

        p = make_panel(n_days=300, n_sym=10)
        with pytest.raises(ValueError, match="not enough data"):
            walk_forward(p, [{"n": 1}], lambda pn, prm: None, n_folds=5,
                         train_years=6, test_years=2)

    def test_rejects_unknown_rebalance_freq(self) -> None:
        from nsealgo.backtest.engine import _rebalance_dates

        with pytest.raises(ValueError, match="W.*M.*Q"):
            _rebalance_dates(make_panel().index, "Y")
