"""NSE basket trader tests — signal math, sizing, accounting, affordability."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from cryptobot.live.nse_basket import BasketState, NseBasket, trend_signal


def test_trend_signal_long_only():
    up = [100 * (1.01 ** i) for i in range(30)]
    down = [100 * (0.99 ** i) for i in range(30)]
    assert trend_signal(up, 5, 12) == 1
    assert trend_signal(down, 5, 12) == 0      # long-only: no short signal
    assert trend_signal([1.0] * 5, 5, 12) == 0  # insufficient history


def _basket(capital=10_000.0, tmp=None):
    b = NseBasket(["X"], capital=capital, port=8098,
                  state_file=(tmp or Path("tmp")) / "b.json")
    return b


def test_buy_and_close_accounting(tmp_path):
    b = _basket(10_000.0, tmp_path)
    b._buy("X", 10, 500.0)                     # 5000 notional + fees
    assert "X" in b.state.positions
    assert b.state.cash < Decimal("5000")
    eq_open = b.state.equity({"X": 500.0})
    assert eq_open == pytest.approx(10_000 - 2 * (5000 * 12 / 10_000), rel=0.01)
    b._close("X", 520.0)
    assert not b.state.positions
    # sold higher than bought: net of round-trip fees we must be up
    assert b.state.cash > 10_000


def test_unaffordable_slice_skipped(tmp_path):
    """₹200 slice can't buy a ₹1300 share — must skip, not go negative."""
    b = _basket(10_000.0, tmp_path)
    st = b.state
    st.cash = 200.0
    b._buy("EXPENSIVE", 1, 1300.0)
    assert "EXPENSIVE" not in st.positions
    assert st.cash == pytest.approx(200.0)


def test_state_roundtrip(tmp_path):
    b = _basket(10_000.0, tmp_path)
    b._buy("X", 5, 100.0)
    d = b.state.to_dict()
    s2 = BasketState.from_dict(d)
    assert s2.positions["X"]["qty"] == 5
    assert s2.cash == b.state.cash


def test_run_once_flattens_on_exit_signal(tmp_path, monkeypatch):
    from cryptobot.live import nse_basket as nb

    def fake_bars(sym):
        base = [100 * (1.01 ** i) for i in range(40)]     # uptrend -> long
        if sym == "DOWNSTOCK":
            base = [100 * (0.99 ** i) for i in range(40)]  # downtrend -> flat
        return [{"ts": i, "date": f"2026-08-{i%28+1:02d}", "open": c,
                 "high": c, "low": c, "close": c, "volume": 1e5}
                for i, c in enumerate(base)]

    monkeypatch.setattr(nb, "fetch_bars", fake_bars)
    b = NseBasket(["UPSTOCK", "DOWNSTOCK"], capital=10_000.0, port=8097,
                  state_file=tmp_path / "b.json")
    b._ist_today = lambda: "2026-08-12"
    b._ist_now = lambda: __import__("datetime").datetime(2026, 8, 12, 15, 36, tzinfo=__import__("zoneinfo").ZoneInfo("Asia/Kolkata"))   # match fake bar dates
    out = b.run_once()
    assert out["positions"] >= 1
    assert "UPSTOCK" in b.state.positions
    assert "DOWNSTOCK" not in b.state.positions


def test_breaker_trips_at_25pct_drawdown_and_flattens(tmp_path, monkeypatch):
    from cryptobot.live import nse_basket as nb

    prices = {"value": 100.0}

    def fake_bars(sym):
        # uptrend into the current price so EMA(5)>EMA(12) -> long signal
        base = prices["value"]
        hist = [base * (0.99 ** (40 - i)) for i in range(40)]
        return [{"ts": i, "date": f"2026-08-{i%28+1:02d}", "open": c,
                 "high": c, "low": c, "close": c, "volume": 1e6}
                for i, c in enumerate(hist)]

    monkeypatch.setattr(nb, "fetch_bars", fake_bars)
    b = nb.NseBasket(["UPSTOCK"], capital=10_000.0, port=8095,
                     state_file=tmp_path / "b.json")
    b._ist_today = lambda: "2026-08-12"
    b._ist_now = lambda: __import__("datetime").datetime(2026, 8, 12, 15, 36, tzinfo=__import__("zoneinfo").ZoneInfo("Asia/Kolkata"))            # match fake bar dates
    b.run_once()                                   # opens full-notional long
    assert b.state.positions and not b.state.breaker_tripped

    prices["value"] = 70.0                         # -30% crash
    b.run_once()
    assert b.state.breaker_tripped is True
    assert b.state.positions == {}                 # flattened
    assert "75% of peak" in (b.state.breaker_reason or "")


def test_breaker_blocks_reentry_until_reset(tmp_path, monkeypatch):
    from cryptobot.live import nse_basket as nb

    seq = {"i": 0}
    def fake_bars(sym):
        seq["i"] += 1
        c = 100.0 if seq["i"] <= 20 else 60.0      # long entry, then crash
        return [{"ts": i, "date": f"2026-08-{i%28+1:02d}", "open": c,
                 "high": c, "low": c, "close": c, "volume": 1e6}
                for i, c in enumerate([c] * 40)]

    monkeypatch.setattr(nb, "fetch_bars", fake_bars)
    b = nb.NseBasket(["S"], capital=10_000.0, port=8094,
                     state_file=tmp_path / "b.json")
    b._ist_today = lambda: "2026-08-12"
    b._ist_now = lambda: __import__("datetime").datetime(2026, 8, 12, 15, 36, tzinfo=__import__("zoneinfo").ZoneInfo("Asia/Kolkata"))
    b.run_once()
    # force trip
    b.state.peak_equity = max(b.state.peak_equity, 10_000)
    b.state.cash = 7_000                            # simulate -30%
    b.run_once()
    assert b.state.breaker_tripped
    n_pos_after_trip = len(b.state.positions)

    b.run_once()                                    # next day: must stay flat
    assert n_pos_after_trip == 0 and len(b.state.positions) == 0

    b.reset_breaker()
    assert b.state.breaker_tripped is False


def test_holiday_skips_rebalance(tmp_path, monkeypatch):
    """When no bar is dated today (NSE closed), do nothing."""
    from cryptobot.live import nse_basket as nb

    def fake_bars(sym):
        return [{"ts": i, "date": f"2026-08-{i+1:02d}", "open": 100,
                 "high": 100, "low": 100, "close": 100 * (1.01 ** i),
                 "volume": 1e6} for i in range(40)]

    monkeypatch.setattr(nb, "fetch_bars", fake_bars)
    b = nb.NseBasket(["UPSTOCK"], capital=10_000.0, port=8093,
                     state_file=tmp_path / "b.json")
    b._ist_today = lambda: "2026-09-15"            # not in the data
    out = b.run_once()
    assert out.get("skipped_holiday") is True
    assert b.state.positions == {}


def test_restart_mid_market_does_not_retrade(tmp_path, monkeypatch):
    """--run-now during market hours must warm up, never place orders."""
    from cryptobot.live import nse_basket as nb

    def fake_bars(sym):
        base = [100 * (1.01 ** i) for i in range(40)]
        return [{"ts": i, "date": f"2026-08-{i%28+1:02d}", "open": c,
                 "high": c, "low": c, "close": c, "volume": 1e6}
                for i, c in enumerate(base)]

    monkeypatch.setattr(nb, "fetch_bars", fake_bars)
    b = nb.NseBasket(["UPSTOCK"], capital=10_000.0, port=8092,
                     state_file=tmp_path / "b.json")
    b._ist_today = lambda: "2026-08-12"
    b._ist_now = lambda: __import__("datetime").datetime(
        2026, 8, 12, 11, 1, tzinfo=__import__("zoneinfo").ZoneInfo("Asia/Kolkata"))
    out = b.run_once()                       # 11:01 — market open
    assert out.get("no_trade_reason") == "market open"
    assert b.state.positions == {}
    b._ist_now = lambda: __import__("datetime").datetime(
        2026, 8, 12, 15, 36, tzinfo=__import__("zoneinfo").ZoneInfo("Asia/Kolkata"))
    out2 = b.run_once()                      # after close — trades
    assert out2["positions"] == 1
    out3 = b.run_once()                      # same day again — latched
    assert out3.get("no_trade_reason") == "already traded today"
    assert len(b.state.trades) == 1
