
import numpy as np
import pytest

from cryptobot.backtest.reporting import (
    compute_drawdown_series,
    equity_curve_from_trades,
    generate_report,
    render_trade_distribution,
    sharpe_ratio,
)
from cryptobot.backtest.validation import (
    deflated_sharpe,
    monte_carlo_significance,
    run_validation,
    walk_forward_returns,
)
from cryptobot.execution.venue.simulated import SimulatedVenue


def _returns(seed: int = 0, n: int = 200) -> list[float]:
    rng = np.random.default_rng(seed)
    return rng.normal(loc=0.0015, scale=0.01, size=n).tolist()


def test_walk_forward_returns_produces_split_results():
    out = walk_forward_returns(_returns(seed=7, n=300), n_splits=5)
    assert out["splits"] >= 2
    assert "oos_mean" in out
    assert "stability" in out


def test_monte_carlo_significance_returns_p_value_in_unit_interval():
    out = monte_carlo_significance(_returns(seed=11, n=200), n_permutations=200)
    assert 0.0 <= out["p_value"] <= 1.0
    assert "observed_sharpe" in out


def test_run_validation_keys_present():
    out = run_validation(_returns(seed=13, n=150), n_splits=4, n_permutations=200)
    assert set(out.keys()) == {"walk_forward", "monte_carlo", "deflated_sharpe", "passed"}
    assert "psr" not in out["deflated_sharpe"]
    assert "probabilistic_sharpe_ratio" in out["deflated_sharpe"]


def test_deflated_sharpe_shape():
    out = deflated_sharpe(_returns(seed=17, n=300), n_trials=4)
    assert out["deflated_sharpe"] == pytest.approx(out["observed_sharpe"] - out["expected_max_sharpe"], abs=1e-9)


def test_simulated_venue_charges_fees_and_slippage():
    from decimal import Decimal

    from cryptobot.core.events import OrderEvent, OrderSide, OrderType

    venue = SimulatedVenue(
        prices={"BTCUSDT": Decimal("100")},
        slippage_bps=Decimal("5"),
        commission_bps=Decimal("5"),
    )
    order = OrderEvent(
        order_id="o1",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        type=OrderType.MARKET,
        quantity=Decimal("1"),
    )
    import asyncio

    filled = asyncio.run(venue.submit_order(order))
    assert filled.filled_quantity == Decimal("1")
    assert filled.avg_fill_price > Decimal("100")
    assert filled.commission > Decimal("0")
    assert abs(filled.avg_fill_price - Decimal("100.0005")) <= Decimal("0.001")


def test_reporting_drawdown_and_sharpe():
    eq = [100.0, 110.0, 105.0, 102.0, 108.0]
    dd = compute_drawdown_series(eq)
    assert len(dd) == len(eq)
    assert dd[1] == 0.0
    assert min(dd) < 0
    rets = [0.01, -0.005, -0.003, 0.006]
    sr = sharpe_ratio(rets)
    assert sr > 0


def test_reporting_generate_report_renders_html():
    from datetime import datetime, timedelta

    t0 = datetime(2024, 1, 1)
    trades = [
        {"timestamp": (t0 + timedelta(days=i)).isoformat(), "symbol": "BTCUSDT", "side": "BUY", "quantity": 1, "pnl": 5 + i}
        for i in range(5)
    ]
    equity = [(t0 + timedelta(days=i), 100 + i * 3) for i in range(6)]
    html = generate_report(
        "Test",
        t0,
        t0 + timedelta(days=5),
        100.0,
        115.0,
        equity,
        trades,
        metrics_extra={"sharpe": 1.2},
    )
    assert "<!DOCTYPE html>" in html
    assert "Test" in html
    assert "Sharpe" in html
    assert "BTCUSDT" in html
    assert "PNL histogram" in html


def test_reporting_trade_distribution_buckets():
    from datetime import datetime

    t0 = datetime(2024, 1, 1)
    trades = [{"pnl": v} for v in (3, 12, -7, 25, -1)]
    out = render_trade_distribution(trades)
    assert "PNL histogram" in out
    assert "0..10" in out


def test_equity_curve_from_trades_handles_empty():
    out = equity_curve_from_trades(100.0, [])
    assert len(out) == 1
    assert out[0][1] == 100.0


def test_equity_curve_from_trades_accumulates_pnl():
    from datetime import datetime, timedelta

    t0 = datetime(2024, 1, 1)
    out = equity_curve_from_trades(1000.0, [(t0, 50.0), (t0 + timedelta(days=1), -20.0), (t0 + timedelta(days=2), 30.0)])
    assert len(out) == 3
    assert out[-1][1] == pytest.approx(1060.0)
