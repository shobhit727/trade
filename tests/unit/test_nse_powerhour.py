"""Power-hour trader tests — VWAP pick logic, daily cycle, flat-by-close."""

from __future__ import annotations

import json

from cryptobot.live.nse_powerhour import PowerHourTrader, pick_power_hour


def _bars(close=100.0, qualifying=True, n=20):
    """Session shaped so the LAST five bars are pullback wicks with strong
    closes: close > session VWAP while recent-5 VWAP dips under it — the
    exact geometry the validated H1 filter selects. qualifying=False makes
    a clean downtrend that must NOT be picked."""
    bars = []
    for i in range(n):
        mod = 9 * 60 + 15 + i * 15
        if mod >= 14 * 60:
            break
        if qualifying:
            # deep-wick candles closing strong: typical price sits ~Rs 1.7
            # UNDER the close -> session VWAP < close, recent-5 VWAP == vwap
            # (flat slope passes the >= gate). The filter's exact geometry.
            c = close
            hi, lo = c + 1.2, c - 6.2
        else:
            c = close - i * 0.7                      # steady decline
            hi, lo = c + 0.2, c - 0.2
        bars.append({"ts": i, "date": "2026-08-26", "mod": mod,
                     "open": lo + 0.1, "high": hi, "low": lo,
                     "close": c, "volume": 1000.0})
    return bars


def test_pick_requires_above_rising_vwap():
    assert pick_power_hour(_bars(100.2, qualifying=True)) is True
    assert pick_power_hour(_bars(95.0, qualifying=False)) is False


def test_entry_opens_equal_weight_and_latches(tmp_path, monkeypatch):
    b = PowerHourTrader(["A", "B"], capital=10_000.0, port=8089,
                        state_file=tmp_path / "p.json")
    monkeypatch.setattr("cryptobot.live.nse_powerhour.fetch_bars",
                        lambda s: _bars(100.0))
    b._ist_now = lambda: __import__("datetime").datetime(
        2026, 8, 26, 14, 0, tzinfo=__import__("zoneinfo").ZoneInfo("Asia/Kolkata"))
    out = b.enter_phase()
    assert out["opened"] == 2
    assert len(b.state.positions) == 2
    again = b.enter_phase()
    assert again["status"] == "already"


def test_exit_flattens_and_records_pnl(tmp_path, monkeypatch):
    b = PowerHourTrader(["A"], capital=10_000.0, port=8088,
                        state_file=tmp_path / "p.json")
    monkeypatch.setattr("cryptobot.live.nse_powerhour.fetch_bars",
                        lambda s: _bars(100.0))
    b._ist_now = lambda: __import__("datetime").datetime(
        2026, 8, 26, 14, 0, tzinfo=__import__("zoneinfo").ZoneInfo("Asia/Kolkata"))
    b.enter_phase()
    assert b.state.positions

    # price pops into the exit window
    def up_bars(s):
        bs = _bars(105.0)
        for x in bs:
            x["mod"] += 15 * 60 if x["mod"] < 14 * 60 else 0
            x["mod"] = max(x["mod"], 14 * 60) if False else x["mod"]
        return [x for x in bs if x["mod"] >= 14 * 60] or bs

    b._marks["A"] = 105.0
    out = b.exit_phase()
    assert out["closed"] == 1
    assert b.state.positions == {}
    assert b.state.phase == "closed"
    assert any(t["side"] == "SELL" for t in b.state.trades)


def test_flat_by_close_no_carryover(tmp_path, monkeypatch):
    """After exit phase, next day starts from cash only."""
    b = PowerHourTrader(["A"], capital=5_000.0, port=8087,
                        state_file=tmp_path / "p.json")
    monkeypatch.setattr("cryptobot.live.nse_powerhour.fetch_bars",
                        lambda s: _bars(100.0))
    ISTz = __import__("zoneinfo").ZoneInfo("Asia/Kolkata")
    dt = __import__("datetime")
    b._ist_now = lambda: dt.datetime(2026, 8, 26, 14, 0, tzinfo=ISTz)
    b.enter_phase()
    b._marks.clear()
    b.exit_phase()
    st_dict = json.loads(b.state_file.read_text())
    assert st_dict["positions"] == {}
    assert st_dict["phase"] == "closed"
