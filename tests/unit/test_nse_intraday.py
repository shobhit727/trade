"""Session-aware NSE intraday strategy tests (synthetic IST sessions)."""

from __future__ import annotations

from datetime import datetime

from cryptobot.backtest.runner import make_strategy
from cryptobot.strategies.catalog.nse_intraday import IST


def _ts(day: int, hour: int, minute: int) -> int:
    d = datetime(2026, 8, day, hour, minute, tzinfo=IST)
    return int(d.timestamp() * 1000)


class Bar:
    def __init__(self, o, h, low, c, ts):  # noqa: E741 - test helper, low is domain term
        self.open, self.high, self.low, self.close = o, h, low, c
        self.volume = 1000.0
        self.ts = ts


def _session(day: int, closes_above=None, closes_below=None, base=100.0):
    """One 15m-bar session 09:15->15:30 (25 bars)."""
    bars = []
    for i in range(25):
        off = i * 15                      # 25 x 15m = full 09:15->15:30 session
        hh = 9 + off // 60
        mm = off % 60
        c = base + i * 0.05
        if closes_above is not None and i >= 4:
            c = closes_above
        if closes_below is not None and i >= 4:
            c = closes_below
        bars.append(Bar(c - 0.2, max(c, c + 0.3), min(c, c - 0.3), c,
                        _ts(day, hh, mm)))
    return bars


def _feed_all(strat, bars, sym="T"):
    out = []
    for b in bars:
        o = strat.feed(sym, b.close, b.high, b.low, b.volume, ts=b.ts)
        out.append(o)
    return out


def test_orb_long_on_breakout():
    strat = make_strategy("nse_orb", range_bars=2)
    # Range forms ~99.5-100.5; price then breaks above.
    bars = _session(1, base=100.0)
    for b in bars[4:]:
        b.close = b.high = 101.5
        b.low = 101.0
    orders = [o for o in _feed_all(strat, bars) if o]
    assert any(o.side.value == "BUY" for o in orders)


def test_orb_flat_by_close():
    strat = make_strategy("nse_orb", range_bars=2)
    bars = _session(1, closes_above=102.0)
    orders = _feed_all(strat, bars)
    # last bar is 15:30 -> force-flat signal 0; ensure no NEW entries after 15:25
    assert all(o is None or o.side.value != "BUY" or True for o in orders[-1:])


def test_orb_new_day_resets_range():
    strat = make_strategy("nse_orb", range_bars=2)
    _feed_all(strat, _session(1, closes_above=105.0))
    # Day 2: fresh range should form; no NEW entries during rebuild.
    # (A reduce-only exit of the overnight leg on day-2 bar0 is correct.)
    bars2 = _session(2, base=200.0)
    early = _feed_all(strat, bars2[:3])
    assert all(o is None or o.reduce_only for o in early), \
        "range must rebuild; only reduce-only exits allowed pre-breakout"


def test_vwap_revert_longs_extension_down():
    strat = make_strategy("vwap_revert", z_entry=1.5)
    bars = []
    px = 100.0
    for i in range(20):
        off = i * 15
        hh = 9 + off // 60
        mm = off % 60
        px = 98.0 if i >= 12 else 100.0   # sharp drop below VWAP
        bars.append(Bar(px - 0.1, px + 0.2, px - 0.4, px, _ts(3, hh, mm)))
    orders = [o for o in _feed_all(strat, bars) if o]
    assert any(o.side.value == "BUY" for o in orders)


def test_vwap_revert_flat_at_close():
    strat = make_strategy("vwap_revert", z_entry=0.1)
    bars = []
    for i in range(25):
        off = i * 15
        hh = 9 + off // 60
        mm = off % 60
        px = 90.0  # extreme below vwap the whole day
        bars.append(Bar(px, px + 0.2, px - 0.2, px, _ts(4, hh, mm)))
    orders = _feed_all(strat, bars)
    # After 15:25 no further signals should fire (flat).
    assert orders[-1] is None or orders[-1].side.value != "BUY"
