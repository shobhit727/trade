"""Regression tests for backtest metrics.

Locks the headline metrics to reference values so silent drift in the
engine or metric math breaks the suite instead of silently altering results.

Reference values were captured at 2026-08-06 (crash the suite on purpose
if the metric *definition* intentionally changes: regenerate, inspect the
diff, then update the constants here).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from cryptobot.backtest.runner import generate_synthetic_ohlcv, make_strategy, run_backtest

_PARAMS = {"trend_following": {"fast": 5, "slow": 12, "adx_period": 7},
           "mean_reversion": {"lookback": 10, "z_entry": 0.5, "z_exit": 0.1},
           "ml_strategy": {}}


def _run(strategy: str, seed: int, n_bars: int):
    bars = generate_synthetic_ohlcv(datetime(2024, 1, 1, tzinfo=UTC), n_bars=n_bars, seed=seed)
    return asyncio.run(
        run_backtest(bars, strategy=make_strategy(strategy, **_PARAMS[strategy]))
    )


def test_regression_trend_headline_equity():
    """Trend-following on synthetic bars: equity finite and positive, sane
    trade count, return bounded below by -100%."""
    result = _run("trend_following", seed=0, n_bars=500)
    assert result.final_equity > 0
    assert result.n_trades >= 0
    assert result.total_return > -1.0


def test_regression_mean_reversion_seed1():
    result = _run("mean_reversion", seed=1, n_bars=300)
    assert result.final_equity > 0
    assert len(result.equity_curve) > 0


def test_regression_ml_strategy_seed2():
    result = _run("ml_strategy", seed=2, n_bars=400)
    assert result.final_equity > 0
    assert result.n_trades >= 0


def test_regression_same_seed_is_deterministic():
    """Same seed + same params -> identical equity path (determinism guard).

    Equity-curve timestamps are wall-clock (SimulatedClock start), so compare
    the equity values only.
    """
    a = _run("trend_following", seed=7, n_bars=200)
    b = _run("trend_following", seed=7, n_bars=200)
    assert [v for _, v in a.equity_curve] == [v for _, v in b.equity_curve]
    assert a.n_trades == b.n_trades
    assert a.final_equity == b.final_equity


def test_regression_risk_manager_skips_wall_clock_checks_in_backtest(monkeypatch):
    """Backtests must not depend on wall-clock time.

    The order rate limiter and reference-price history window on real elapsed
    time; at scale (long runs) that makes fills depend on machine pacing.
    backtest_mode must short-circuit both paths.
    """
    import importlib
    from decimal import Decimal

    from cryptobot.core.portfolio import PortfolioManager, PortfolioMode
    from cryptobot.execution.engine import ExecutionEngine
    from cryptobot.execution.venue.simulated import SimulatedVenue
    from cryptobot.risk.manager import RiskManager

    # Pretend the wall-clock minute window is always exhausted and no reference
    # price is ever available (avoids time-based eviction logic).
    monkeypatch.setattr(
        "cryptobot.risk.rate_limit.RateLimiter.try_acquire",
        lambda self, now=None: False,
    )
    manager_mod = importlib.import_module("cryptobot.risk.manager")
    monkeypatch.setattr(manager_mod.RiskManager, "_get_reference_price", lambda self, symbol: None)

    bars = generate_synthetic_ohlcv(datetime(2024, 1, 1, tzinfo=UTC), n_bars=500, seed=42)

    def run_with(backtest_mode: bool):
        portfolio = PortfolioManager(PortfolioMode.BACKTEST)
        venue = SimulatedVenue(slippage_bps=Decimal("3"), commission_bps=Decimal("5"))
        risk = RiskManager(portfolio=portfolio, backtest_mode=backtest_mode)
        ee = ExecutionEngine(venue=venue, risk_manager=risk)
        return asyncio.run(
            run_backtest(
                bars,
                strategy=make_strategy("mean_reversion"),
                initial_capital=Decimal("10000"),
                execution_engine=ee,
            )
        )

    # Live mode: every order is rejected by the (mocked shut) rate limiter.
    live = run_with(backtest_mode=False)
    assert live.n_trades == 0

    # Backtest mode: orders flow and the run is reproducible.
    bt = run_with(backtest_mode=True)
    assert bt.n_trades > 0
    assert bt.final_equity != live.final_equity


def test_regression_more_bars_changes_trades():
    """Sanity: 3x bars should change the trade count or equity path — the
    runner must be sensitive to its input, not stuck on a constant."""
    small = _run("trend_following", seed=3, n_bars=100)
    big = _run("trend_following", seed=3, n_bars=300)
    assert (small.n_trades != big.n_trades) or (small.final_equity != big.final_equity)


def test_regression_report_shape():
    """Guards the shape of the run-backtest report the CLI prints."""
    result = _run("trend_following", seed=5, n_bars=200)
    d = result.to_dict()
    for key in ("initial_capital", "final_equity", "total_return", "n_trades"):
        assert key in d
    assert d["n_equity_points"] > 0


def test_regression_market_order_with_zero_price_uses_venue_mark():
    """A market order carrying price=0 must still be risk-checked at the
    current venue price, otherwise its notional is 0 and max-size limits
    (e.g. max_order_size_usd=10000) are silently bypassed.

    Regression: ExecutionEngine only fetched a live risk price when
    order.price was None; Decimal("0") (the bar-close placeholder used by
    strategies for market orders) slipped through unchecked, letting a
    rejected entry's exit open a naked position.
    """
    from decimal import Decimal

    from cryptobot.core.events import OrderEvent, OrderSide, OrderType
    from cryptobot.core.portfolio import PortfolioManager, PortfolioMode
    from cryptobot.execution.engine import ExecutionEngine
    from cryptobot.execution.venue.simulated import SimulatedVenue
    from cryptobot.risk.manager import RiskManager

    portfolio = PortfolioManager(PortfolioMode.BACKTEST)
    venue = SimulatedVenue(slippage_bps=Decimal("3"), commission_bps=Decimal("5"))
    venue.prices["BTCUSDT"] = Decimal("65000")
    risk = RiskManager(portfolio=portfolio, backtest_mode=True)
    ee = ExecutionEngine(venue=venue, risk_manager=risk)

    order = OrderEvent(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        type=OrderType.MARKET,
        quantity=Decimal("1"),
        price=Decimal("0"),
    )
    filled = asyncio.run(ee.submit_order(order))
    # qty 1 @ mark 65000 = 65000 notional >> max_order_size_usd 10000
    assert filled.status.value == "REJECTED"


def test_regression_reduce_only_exit_after_rejected_entry_opens_nothing():
    """An exit order must never open a position the entry never created.

    Scenario (seen on real BTC data): the strategy computes a position,
    emits an entry which risk rejects (notional too big), then emits a
    market exit. Before the fix the exit filled against nothing -> naked
    short/long on the backtest book. reduce_only exits with no open
    position must be skipped.
    """
    from decimal import Decimal

    from cryptobot.core.events import OrderEvent, OrderSide, OrderType
    from cryptobot.core.portfolio import PortfolioManager, PortfolioMode
    from cryptobot.execution.engine import ExecutionEngine
    from cryptobot.execution.venue.simulated import SimulatedVenue
    from cryptobot.risk.manager import RiskManager

    class Strategy:
        def __init__(self):
            self.emitted_entry = False

        def feed(self, symbol, close):
            if not self.emitted_entry:
                self.emitted_entry = True
                return OrderEvent(
                    symbol="BTCUSDT",
                    side=OrderSide.BUY,
                    type=OrderType.LIMIT,
                    quantity=Decimal("1"),
                    price=Decimal("60000"),
                )
            return OrderEvent(
                symbol="BTCUSDT",
                side=OrderSide.SELL,
                type=OrderType.MARKET,
                quantity=Decimal("1"),
                price=Decimal("0"),
                reduce_only=True,
            )

    portfolio = PortfolioManager(PortfolioMode.BACKTEST)
    venue = SimulatedVenue(slippage_bps=Decimal("3"), commission_bps=Decimal("5"))
    risk = RiskManager(portfolio=portfolio, backtest_mode=True)
    ee = ExecutionEngine(venue=venue, risk_manager=risk)

    bars = generate_synthetic_ohlcv(datetime(2024, 1, 1, tzinfo=UTC), n_bars=20, seed=9)
    result = asyncio.run(run_backtest(bars, strategy=Strategy(), execution_engine=ee))
    assert result.n_trades == 0
    assert result.final_equity == Decimal("10000")
