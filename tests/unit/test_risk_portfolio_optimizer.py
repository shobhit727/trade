"""Tests for risk/portfolio_optimizer.py + RiskManager risk-metric wiring."""

from __future__ import annotations

from decimal import Decimal

import numpy as np
import pytest

from cryptobot.core.portfolio import PortfolioManager, PortfolioMode
from cryptobot.risk.manager import RiskManager
from cryptobot.risk.portfolio_optimizer import hrp_weights, mean_cvar_weights


def _two_asset_returns() -> np.ndarray:
    rng = np.random.default_rng(42)
    a = rng.normal(0.0005, 0.02, 500)
    b = a + rng.normal(0.0, 0.001, 500)
    return np.column_stack([a, b])


# --- HRP -----------------------------------------------------------------


def test_hrp_weights_sum_to_one():
    r = _two_asset_returns()
    res = hrp_weights(r, ["A", "B"])
    assert res.method == "hrp"
    assert set(res.weights) == {"A", "B"}
    assert sum(res.weights.values()) == pytest.approx(1.0, abs=1e-9)
    assert all(w > 0 for w in res.weights.values())


def test_hrp_single_asset():
    res = hrp_weights(np.column_stack([np.linspace(0, 1, 10)]), ["A"])
    assert res.weights == {"A": pytest.approx(1.0)}


def test_hrp_correlated_pair_gets_balanced():
    # Two near-identical assets -> HRP splits weight roughly evenly.
    r = np.column_stack([np.linspace(0, 1, 200), np.linspace(0.001, 1.001, 200)])
    res = hrp_weights(r, ["A", "B"])
    assert abs(res.weights["A"] - res.weights["B"]) < 0.05


def test_hrp_rejects_bad_shape():
    r = np.column_stack([np.linspace(0, 1, 10), np.linspace(1, 2, 10)])
    with pytest.raises(ValueError):
        hrp_weights(r, ["A"])


def test_hrp_rejects_single_observation():
    r = np.array([[0.01, 0.02]])
    with pytest.raises(ValueError):
        hrp_weights(r, ["A", "B"])


# --- Mean-CVaR ------------------------------------------------------------


def test_mean_cvar_weights_sum_to_one():
    r = _two_asset_returns()
    res = mean_cvar_weights(r, ["A", "B"])
    assert res.method == "mean_cvar"
    assert sum(res.weights.values()) == pytest.approx(1.0, abs=1e-9)


def test_mean_cvar_penalizes_tail_risk():
    # Asset B has rare severe crashes -> B gets less weight than A.
    rng = np.random.default_rng(7)
    a = rng.normal(0.0, 0.01, 1000)
    b = rng.normal(0.0, 0.01, 1000)
    b[::25] -= 0.5  # periodic crash
    res = mean_cvar_weights(np.column_stack([a, b]), ["A", "B"])
    assert res.weights["B"] < res.weights["A"]


def test_mean_cvar_alpha_bounds():
    r = _two_asset_returns()
    with pytest.raises(ValueError):
        mean_cvar_weights(r, ["A", "B"], alpha=0.0)
    with pytest.raises(ValueError):
        mean_cvar_weights(r, ["A", "B"], alpha=1.0)


# --- RiskManager metric wiring ---------------------------------------------


def test_risk_manager_reports_metrics(pytestconfig):
    import asyncio

    pm = PortfolioManager(PortfolioMode.BACKTEST)
    asyncio.run(pm.update_equity(Decimal("10000")))
    rm = RiskManager(portfolio=pm)
    # Should not raise when emitting Prometheus gauges.
    rm.report_risk_metrics()


def test_risk_manager_report_skips_zero_equity():
    import asyncio

    pm = PortfolioManager(PortfolioMode.BACKTEST)
    asyncio.run(pm.update_equity(Decimal("0")))
    rm = RiskManager(portfolio=pm)
    rm.report_risk_metrics()  # no-op, must not raise
