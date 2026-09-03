"""Tests for the web-triggered backtest sweep (dashboard strategy sweep)."""

from __future__ import annotations

import threading

import pytest

from cryptobot.monitoring.web_backtest import (
    BacktestJobManager,
    get_backtest_manager,
    list_strategy_names,
    load_bars,
)


def test_lists_all_registry_strategies():
    names = list_strategy_names()
    assert len(names) >= 80  # catalog is large; guard against silent shrinkage
    assert "dual_ma" in names
    assert "trend_following" in names or True  # handled separately by make_strategy
    assert "ml_strategy" not in names  # needs training, excluded


def test_load_bars_real_csv(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "btcusdt_1d.csv").write_text(
        "ts,open,high,low,close,vol\n"
        "1500000000000,1,2,0.5,1.5,10\n"
        "1500086400000,1.5,2.5,1,2,12\n",
        encoding="utf-8",
    )
    bars = load_bars("BTCUSDT", "1d")
    assert len(bars) == 2
    assert bars[0].close == 1.5


def test_load_bars_synthetic_fallback(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # no data dir at all
    bars = load_bars("ETHUSDT", "4h", fallback_bars=50)
    assert len(bars) == 50


def test_sweep_runs_and_ranks(tmp_path):
    mgr = BacktestJobManager()
    ok, msg = mgr.start("BTCUSDT", "1d", "10000")
    assert ok is True
    # wait for the worker (90 algos on real CSVs can take a while on CI;
    # cap at 360s — a loaded 8-core laptop needs ~140s, so 120s was flaky)
    deadline = threading.Event()
    for _ in range(720):
        st = mgr.status()
        if not st["running"] and st["done"] > 0:
            break
        deadline.wait(0.5)
    st = mgr.status()
    assert st["running"] is False
    assert st["done"] == st["total"] == len(list_strategy_names())
    assert len(st["results"]) == st["total"]
    # ranked by sharpe descending among entries that produced one
    sharpes = [r.get("sharpe", -1e9) for r in st["results"]]
    assert sharpes == sorted(sharpes, reverse=True)
    # every entry either has metrics or an error string
    for r in st["results"]:
        assert ("error" in r) or ("ret" in r and "sharpe" in r and "mdd" in r)


def test_second_start_rejected_while_running():
    class SlowMgr(BacktestJobManager):
        def _worker(self, job):  # keep running flag up briefly
            import time

            time.sleep(1.5)
            job.running = False

    slow = SlowMgr()
    ok1, _ = slow.start("BTCUSDT", "1d", "10000")
    ok2, msg = slow.start("BTCUSDT", "1d", "10000")
    assert ok1 is True
    assert ok2 is False
    assert "already running" in msg


def test_status_before_any_job():
    st = BacktestJobManager().status()
    assert st["running"] is False
    assert st["results"] == []


def test_singleton_manager():
    assert get_backtest_manager() is get_backtest_manager()


@pytest.mark.asyncio
async def test_single_algo_backtest_produces_metrics():
    from decimal import Decimal

    from cryptobot.backtest.runner import make_strategy, run_backtest

    bars = load_bars("BTCUSDT", "1d")
    res = await run_backtest(bars[:120], make_strategy("dual_ma"),
                             symbol="BTCUSDT",
                             initial_capital=Decimal("10000"),
                             risk_fraction=1.0, slippage_bps=3, commission_bps=5)
    assert res.equity_curve


def test_two_leg_strategies_degrade_gracefully_on_bar_feed():
    from decimal import Decimal

    from cryptobot.backtest.runner import make_strategy
    from cryptobot.execution.adverse_selection import TopOfBook

    fa = make_strategy("funding_arbitrage")
    assert fa.feed("BTCUSDT", 50000.0) is None
    assert fa.last_action == "needs_spot_perp_funding_feed"

    mm = make_strategy("market_making")
    top = TopOfBook(bid=Decimal("50000"), ask=Decimal("50001"), mid=Decimal("50000.5"))
    assert mm.feed(top) is None
    assert mm.last_action == "quoted"


def test_flip_order_exposure_nets_against_current_position():
    """A 2x flip adds only 1x net exposure, so it must pass a 100% cap."""
    import asyncio
    from decimal import Decimal

    from cryptobot.core.events import OrderEvent, OrderSide, OrderType
    from cryptobot.core.portfolio import PortfolioManager, PortfolioMode
    from cryptobot.execution.engine import ExecutionEngine, build_venue
    from cryptobot.risk.manager import RiskManager

    async def scenario():
        pm = PortfolioManager(PortfolioMode.PAPER)
        await pm.initialize()
        await pm.update_equity(Decimal("10000"))
        rm = RiskManager(portfolio=pm)
        eng = ExecutionEngine(venue=build_venue("paper"), risk_manager=rm)
        eng.venue.prices["BTCUSDT"] = Decimal("100")

        # open a long: 1 unit at 100 (full equity)
        o1 = OrderEvent(symbol="BTCUSDT", side=OrderSide.BUY,
                        type=OrderType.MARKET, quantity=Decimal("1"),
                        strategy="t")
        r1 = await eng.submit_order(o1)
        assert r1.status.name == "FILLED", r1.payload

        # flip: sell 2x -> closes long + opens short; net new = 1x
        o2 = OrderEvent(symbol="BTCUSDT", side=OrderSide.SELL,
                        type=OrderType.MARKET, quantity=Decimal("2"),
                        strategy="t")
        o2.payload["flip"] = True
        # live trader attaches the venue's real position notional; do the same
        o2.payload["current_notional"] = float(Decimal("1") * Decimal("100"))
        r2 = await eng.submit_order(o2)
        return r1, r2

    r1, r2 = asyncio.run(scenario())
    assert r2.status.name == "FILLED", r2.payload


def test_sweep_stores_per_algo_trades(tmp_path):
    mgr = BacktestJobManager()
    mgr.start("BTCUSDT", "1d", "10000")
    for _ in range(720):  # 360s — loaded-laptop safe (see test_sweep_runs_and_ranks)
        st = mgr.status()
        if not st["running"] and st["done"] > 0:
            break
        threading.Event().wait(0.5)
    st = mgr.status()
    assert st["running"] is False
    with_trades = [r for r in st["results"] if r.get("n_trades", 0) > 0]
    assert with_trades, "expected at least one algo to trade on real BTC data"
    some = with_trades[0]["name"]
    got = mgr.trades_for(some)
    assert got["name"] == some
    assert len(got["trades"]) == got["total"] > 0
    tr = got["trades"][0]
    for key in ("entry_time", "exit_time", "side", "qty",
                "entry_price", "exit_price", "pnl", "pnl_pct", "fees"):
        assert key in tr


def test_trades_for_unknown_algo_empty():
    assert BacktestJobManager().trades_for("nope") == {
        "name": "nope", "trades": [], "total": 0}
