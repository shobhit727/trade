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
    out = b.run_once()
    assert out["positions"] >= 1
    assert "UPSTOCK" in b.state.positions
    assert "DOWNSTOCK" not in b.state.positions
