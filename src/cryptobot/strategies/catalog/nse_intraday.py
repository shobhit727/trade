"""NSE session-aware intraday strategies (mid-frequency research).

Both trade INTRADAY-ONLY: flat by the 15:25 IST close, so no overnight
gap risk and no delivery STT — pure intraday cost economics.

- NseOrbStrategy: opening-range breakout. Range = first `range_bars` bars
  of the session (default first 30 min on 15m bars). Long on close above
  range high, short on close below range low (intraday short), exit at
  session end or opposite break.
- VwapRevertStrategy: fade extensions from session VWAP beyond `z` stddevs
  of the day's typical prices; exit on reversion to VWAP or session end.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from cryptobot.strategies.signal_base import SignalStrategy

IST = timezone(timedelta(hours=5, minutes=30))
SESSION_START = (9, 15)
SESSION_END = (15, 30)
FLAT_AT = (15, 25)  # force-flat 5 min before close


def _ist_minute_of_day(ts_ms: int | None) -> int | None:
    if ts_ms is None:
        return None
    dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).astimezone(IST)
    return dt.hour * 60 + dt.minute



@dataclass
class NseOrbConfig:
    range_bars: int = 2          # 2 x 15m = first 30 minutes
    quantity: Decimal = Decimal("1")


class NseOrbStrategy(SignalStrategy):
    """Opening-range breakout, intraday-only, flat into the close."""

    name = "nse_orb"

    def __init__(self, config: NseOrbConfig | None = None):
        super().__init__(config or NseOrbConfig())
        self._session: dict[str, dict] = {}

    def warmup(self, closes) -> int:
        return self.config.range_bars + 1

    def _session_state(self, symbol: str, ts_ms: int | None) -> dict:
        st = self._session.get(symbol)
        mod = _ist_minute_of_day(ts_ms)
        new_day = st is None or (mod is not None and mod < st.get("mod", 10**9))
        if st is None or new_day:
            st = {"mod": mod, "hi": None, "lo": None, "bars": 0}
            self._session[symbol] = st
        else:
            st["mod"] = mod  # advance the clock within the session
        return st

    def signal(self, closes, highs, lows, volumes):
        symbol = getattr(self, "_cur_symbol", "S")
        ts_ms = self._last_ts(symbol)
        st = self._session_state(symbol, ts_ms)
        mod = st["mod"]
        if mod is None:
            return 0

        # Force flat near the close.
        if mod >= FLAT_AT[0] * 60 + FLAT_AT[1]:
            return 0
        # Outside session: no opinion.
        if mod < SESSION_START[0] * 60 + SESSION_START[1]:
            return 0

        c, h, l = closes[-1], highs[-1], lows[-1]
        # Build the opening range.
        if st["bars"] < self.config.range_bars:
            st["hi"] = h if st["hi"] is None else max(st["hi"], h)
            st["lo"] = l if st["lo"] is None else min(st["lo"], l)
            st["bars"] += 1
            return 0

        if st["hi"] is None:
            return 0
        if c > st["hi"]:
            return 1
        if c < st["lo"]:
            return -1
        return 0

    def feed(self, symbol: str, *a, **kw):
        self._cur_symbol = symbol
        return super().feed(symbol, *a, **kw)


@dataclass
class VwapRevertConfig:
    z_entry: float = 2.0
    quantity: Decimal = Decimal("1")


class VwapRevertStrategy(SignalStrategy):
    """Fade >z-stddev extensions from session VWAP; flat into the close."""

    name = "vwap_revert"

    def __init__(self, config: VwapRevertConfig | None = None):
        super().__init__(config or VwapRevertConfig())
        self._day: dict[str, dict] = {}

    def warmup(self, closes) -> int:
        return 3

    def signal(self, closes, highs, lows, volumes):
        symbol = getattr(self, "_cur_symbol", "S")
        ts_ms = self._last_ts(symbol)
        mod = _ist_minute_of_day(ts_ms)
        if mod is None:
            return 0
        if mod >= FLAT_AT[0] * 60 + FLAT_AT[1]:
            return 0

        d = self._day.get(symbol)
        if d is None or mod < d.get("mod", 10**9):
            d = {"mod": mod, "pv": 0.0, "v": 0.0, "tps": []}
            self._day[symbol] = d
        else:
            d["mod"] = mod

        tp = (highs[-1] + lows[-1] + closes[-1]) / 3.0
        d["pv"] += tp * volumes[-1]
        d["v"] += volumes[-1]
        d["tps"].append(tp)

        if d["v"] <= 0 or len(d["tps"]) < 5:
            return 0
        vwap = d["pv"] / d["v"]
        mean = sum(d["tps"]) / len(d["tps"])
        var = sum((x - mean) ** 2 for x in d["tps"]) / len(d["tps"])
        sd = var ** 0.5
        if sd <= 0:
            return 0
        z = (closes[-1] - vwap) / sd
        if z <= -self.config.z_entry:
            return 1     # below fair value -> long reversion
        if z >= self.config.z_entry:
            return -1    # above fair value -> intraday short
        return 0

    def feed(self, symbol: str, *a, **kw):
        self._cur_symbol = symbol
        return super().feed(symbol, *a, **kw)
