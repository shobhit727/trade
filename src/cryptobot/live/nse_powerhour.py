"""NSE power-hour trader — H1 from PROJECT_MEMORY/43, as a live process.

Two-phase daily cycle (paper):
  14:00 IST  ENTRY  — long every stock whose close > session VWAP and VWAP
                      still rising (5-bar slope). Equal-weight slices.
  15:16 IST  EXIT   — flatten everything at the final 15:15 bar. Flat by
                      close, no overnight risk, MIS costs 2+1bps/side.

State persisted to state-nse/powerhour.json. /health + /dashboard on its
own port, control-room compatible. Breaker: -25% from peak equity.
"""

from __future__ import annotations

import argparse
import json
import logging
import threading
import time
import urllib.request
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from zoneinfo import ZoneInfo

from cryptobot.core.tax_equity import TaxLedger

logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")
STATE_DIR = Path("state-nse")

from cryptobot.config import get_settings

def _get_yahoo_chart_url() -> str:
    return get_settings().external_services.yahoo_finance_chart_url

def _get_http_default_timeout() -> int:
    return get_settings().timeouts.http_default_timeout

def _get_nse_powerhour_port() -> int:
    return get_settings().server.nse_powerhour_port

FEE_BPS, SLIP_BPS = Decimal("2"), Decimal("1")


def _svg_chart(values: list[float], w: int = 260, h: int = 64) -> str:
    if len(values) < 2:
        return "<span style=color:#8b98a9>collecting…</span>"
    lo, hi = min(values), max(values)
    rng = (hi - lo) or 1
    pts = [(i / (len(values) - 1)) * w for i in range(len(values))]
    ys = [h - ((v - lo) / rng) * (h - 6) - 3 for v in values]
    poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(pts, ys, strict=False))
    up = values[-1] >= values[0]
    color = "#22c55e" if up else "#ef4444"
    gid = f"g{abs(hash(tuple(values[:9]))) % 99999}"
    return (f'<svg width="{w}" height="{h}"><defs><linearGradient id="{gid}" '
            f'x1=0 y1=0 x2=0 y2=1><stop offset=0 stop-color="{color}" '
            f'stop-opacity=.25/><stop offset=1 stop-color="{color}" '
            f'stop-opacity=0/></linearGradient></defs>'
            f'<polygon points="0,{h} {poly} {w},{h}" fill="url(#{gid})"/>'
            f'<polyline points="{poly}" fill=none stroke="{color}" '
            f'stroke-width=1.8/></svg>')


def fetch_bars(symbol: str) -> list[dict]:
    url = f"{_get_yahoo_chart_url()}{symbol}.NS?interval=15m&range=10d"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=_get_http_default_timeout()) as r:
        payload = json.load(r)
    res = payload["chart"]["result"][0]
    ts = res.get("timestamp") or []
    q = res["indicators"]["quote"][0]
    bars = []
    for i, tt in enumerate(ts):
        c = q["close"][i]
        if c is None:
            continue
        dt = datetime.fromtimestamp(tt, tz=UTC).astimezone(IST)
        # keep only TODAY'S bars for session math; older bars warm nothing here
        bars.append({"ts": int(tt * 1000), "date": dt.date().isoformat(),
                     "mod": dt.hour * 60 + dt.minute,
                     "open": float(q["open"][i] or c),
                     "high": float(q["high"][i] or c),
                     "low": float(q["low"][i] or c), "close": float(c),
                     "volume": float(q["volume"][i] or 0)})
    return bars


def pick_power_hour(bars_today: list[dict]) -> bool:
    """close > session VWAP and VWAP not falling (5-bar slope >= 0)."""
    pre = [b for b in bars_today if b["mod"] < 14 * 60]
    if len(pre) < 8:
        return False
    tp = [(b["high"] + b["low"] + b["close"]) / 3 for b in pre]
    vols = [b["volume"] for b in pre]
    total_v = sum(vols)
    if total_v <= 0:
        return False
    vwap = sum(t * v for t, v in zip(tp, vols, strict=False)) / total_v
    tail_n = min(5, len(pre))
    tail_v = sum(vols[-tail_n:])
    vwap_recent = (sum(t * v for t, v in zip(tp[-tail_n:], vols[-tail_n:],
                                             strict=False)) / tail_v
                   if tail_v > 0 else vwap)
    return bool(pre[-1]["close"] > vwap and vwap >= vwap_recent)


class PowerHourState:
    def __init__(self, capital: float):
        self.capital = capital
        self.cash = capital
        self.peak_equity = capital
        self.breaker_tripped = False
        self.breaker_reason: str | None = None
        self.day: str | None = None          # date of current/last cycle
        self.phase: str = "idle"             # idle|entered|closed
        self.positions: dict[str, dict] = {}
        self.trades: list[dict] = []
        self.equity_curve: list[dict] = []
        self.tax = TaxLedger()

    def equity(self, marks: dict[str, float] | None = None) -> float:
        marks = marks or {}
        eq = self.cash
        for sym, p in self.positions.items():
            px = marks.get(sym, p["entry"])
            eq += p["qty"] * px
        return eq

    def to_dict(self) -> dict:
        return {"capital": self.capital, "cash": self.cash,
                "peak_equity": self.peak_equity,
                "breaker_tripped": self.breaker_tripped,
                "breaker_reason": self.breaker_reason, "day": self.day,
                "phase": self.phase, "positions": self.positions,
                "trades": self.trades[-400:], "equity_curve": self.equity_curve[-200:]}

    @classmethod
    def from_dict(cls, d: dict) -> PowerHourState:
        s = cls(d["capital"])
        s.cash = d.get("cash", d["capital"])
        s.peak_equity = d.get("peak_equity", d["capital"])
        s.breaker_tripped = d.get("breaker_tripped", False)
        s.breaker_reason = d.get("breaker_reason")
        s.day = d.get("day")
        s.phase = d.get("phase", "idle")
        s.positions = d.get("positions", {})
        s.trades = d.get("trades", [])
        s.equity_curve = d.get("equity_curve", [])
        return s


class PowerHourTrader:
    def __init__(self, symbols: list[str], capital: float = 100_000.0,
                 port: int | None = None, state_file: Path | None = None):
        self.symbols = symbols
        self.port = port if port is not None else _get_nse_powerhour_port()
        self.state_file = state_file or (STATE_DIR / "powerhour.json")
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state = (PowerHourState.from_dict(json.loads(self.state_file.read_text()))
                      if self.state_file.exists() else PowerHourState(capital))
        self.stats = {"entries": 0, "exits": 0}
        self._closes: dict[str, list[float]] = {}
        self._marks: dict[str, float] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------ helpers

    def _ist_now(self) -> datetime:
        return datetime.now(IST)

    def _fee(self, notional: float) -> float:
        return notional * float(FEE_BPS + SLIP_BPS) / 10_000

    def _equity(self) -> float:
        eq = self.state.cash
        for p in self.state.positions.values():
            mark = self._marks.get(p["sym"], p["entry"])
            eq += p["qty"] * (mark - p["entry"]) if False else p["qty"] * mark
        return eq

    # ------------------------------------------------------------- phases

    def enter_phase(self) -> dict:
        """14:00 IST — open longs on qualifying stocks."""
        st, today = self.state, self._ist_now().date().isoformat()
        if st.day == today and st.phase in ("entered", "closed"):
            return {"status": "already", "day": today}
        marks: dict[str, float] = {}
        stale = 0
        picks: list[tuple[str, float]] = []
        for sym in self.symbols:
            try:
                bars = fetch_bars(sym)
            except Exception:  # noqa: BLE001
                stale += 1
                continue
            todays = [b for b in bars if b["date"] == today]
            if not todays:
                stale += 1
                continue
            self._closes[sym] = [b["close"] for b in todays]
            px = todays[-1]["close"]
            marks[sym] = px
            if pick_power_hour(todays):
                picks.append((sym, px))
        if stale == len(self.symbols):
            logger.info("market closed/holiday — no entry today")
            return {"status": "holiday"}
        with self._lock:
            if st.breaker_tripped:
                return {"status": "breaker"}
            slice_size = st.cash / max(1, len(picks))
            opened = 0
            for sym, px in picks:
                qty = int(slice_size // px)
                if qty < 1:
                    continue
                fee = self._fee(qty * px)
                st.cash -= qty * px + fee
                st.tax.on_buy(sym, float(qty), px, self._ist_now())
                st.positions[sym] = {"qty": qty, "entry": px, "sym": sym}
                st.trades.append({"time": self._ist_now().isoformat(timespec="seconds"),
                                  "symbol": sym, "side": "BUY", "qty": qty,
                                  "price": round(px, 2)})
                opened += 1
            st.day, st.phase = today, "entered" if opened else "closed"
            self.stats["entries"] += opened
            self.state_file.write_text(json.dumps(st.to_dict(), indent=1))
            logger.info("entry phase: %d picks, %d opened", len(picks), opened)
            return {"status": "ok", "picks": len(picks), "opened": opened}

    def exit_phase(self) -> dict:
        """15:16 IST — flatten everything at the final 15m bar."""
        st = self.state
        today = self._ist_now().date().isoformat()
        if st.phase != "entered":
            return {"status": "nothing-open"}
        closed, pnl_day = 0, 0.0
        with self._lock:
            for sym, p in list(st.positions.items()):
                try:
                    bars = fetch_bars(sym)
                except Exception:  # noqa: BLE001
                    continue
                todays = [b for b in bars if b["date"] == today]
                if not todays:
                    continue
                px = todays[-1]["close"]
                qty, entry = p["qty"], p["entry"]
                gross = qty * px
                fee = self._fee(gross)
                st.cash += gross - fee
                pnl_day += qty * (px - entry) - fee
                st.tax.on_sell(sym, float(qty), px, self._ist_now())
                st.trades.append({"time": self._ist_now().isoformat(timespec="seconds"),
                                  "symbol": sym, "side": "SELL", "qty": qty,
                                  "price": round(px, 2)})
                del st.positions[sym]
                closed += 1
            self.stats["exits"] += closed
            marks = {s: self._marks.get(s, p["entry"])
                     for s, p in st.positions.items()}
            eq = st.equity() if not st.positions else None
            eq_final = eq if eq is not None else (
                st.cash + sum(p["qty"] * self._marks.get(s, p["entry"])
                              for s, p in st.positions.items()))
            st.equity_curve.append({"date": today, "equity": round(eq_final, 2)})
            if not st.breaker_tripped:
                st.peak_equity = max(st.peak_equity, eq_final)
                if st.peak_equity > 0 and eq_final <= st.peak_equity * 0.75:
                    st.breaker_tripped = True
                    st.breaker_reason = (f"equity {eq_final:,.0f} <= 75% of "
                                         f"peak {st.peak_equity:,.0f}")
            st.phase = "closed" if not st.positions else st.phase
            self.state_file.write_text(json.dumps(st.to_dict(), indent=1))
        logger.info("exit phase: %d closed, day pnl %.2f", closed, pnl_day)
        return {"status": "ok", "closed": closed, "pnl": round(pnl_day, 2)}

    def snapshot(self) -> dict:
        with self._lock:
            eq = self.state.cash + sum(
                p["qty"] * (self._marks.get(s, p["entry"]) - 0)
                for s, p in self.state.positions.items())
            pos_view = {s: {"qty": p["qty"], "entry": round(p["entry"], 2)}
                        for s, p in self.state.positions.items()}
            gate_day = len(self.state.equity_curve)
            return {
                "status": "running", "service": "nse-powerhour",
                "symbol": f"NSE×{len(self.symbols)}",
                "strategy": "power_hour(VWAP)", "timeframe": "15m",
                "mode": "paper",
                "equity": f"{eq:.2f}", "daily_pnl": f"{eq - self.state.capital:.2f}",
                "peak_equity": f"{self.state.peak_equity:.2f}",
                "bars_fed": 0, "orders_submitted": self.stats["entries"],
                "fills": self.stats["entries"] + self.stats["exits"],
                "rejects": 0, "open_positions": len(self.state.positions),
                "positions": pos_view,
                "positions_detail": pos_view,
                "recent_trades": self.state.trades[-12:],
                "trades_total": len(self.state.trades),
                "tax_summary": self.state.tax.summary(),
                "equity_curve": self.state.equity_curve[-120:],
                "paper_gate": {"days_elapsed": gate_day, "required_days": 30,
                               "breaker_tripped": self.state.breaker_tripped,
                               "breaker_reason": self.state.breaker_reason},
                "last_run": self.state.day,
            }

    def reset_breaker(self) -> None:
        with self._lock:
            self.state.breaker_tripped = False
            self.state.breaker_reason = None
            self.state.peak_equity = max(self.state.equity(), self.state.cash)
            self.state_file.write_text(json.dumps(self.state.to_dict(), indent=1))

    # ------------------------------------------------------------ serving

    def _dashboard_html(self) -> str:
        s = self.snapshot()
        eq = float(s["equity"])
        pnl = eq - self.state.capital
        cls = "pos" if pnl >= 0 else "neg"
        spark = _svg_chart([c["equity"] for c in s.get("equity_curve", [])])
        rows = "".join(
            f"<tr><td>{t['time'][11:16]}</td><td>{t['symbol']}</td>"
            f"<td>{t['side']}</td><td>{t['qty']} @ ₹{t['price']:,.2f}</td></tr>"
            for t in reversed(s.get("recent_trades", [])[-12:])
        ) or "<tr><td colspan=4 class=muted>no trades yet</td></tr>"
        pos_rows = "".join(
            f"<tr><td>{k}</td><td>{v['qty']}</td><td>₹{v['entry']:,.2f}</td></tr>"
            for k, v in s.get("positions_detail", {}).items()
        ) or "<tr><td colspan=3 class=muted>flat</td></tr>"
        gate = s["paper_gate"]
        pct = min(100, gate["days_elapsed"] / max(1, gate["required_days"]) * 100)
        return f"""<!doctype html><html><head><meta charset=utf-8>
<title>NSE Power Hour — Live</title><meta http-equiv=refresh content="15">
<style>
body{{background:#0a0e14;color:#e6edf3;font:14px/1.5 system-ui,sans-serif;
padding:28px;max-width:1080px;margin-inline:auto}}
h1{{font-size:17px;display:flex;gap:10px;align-items:center}}
.dot{{width:8px;height:8px;border-radius:50%;background:#22c55e;
box-shadow:0 0 8px #22c55e;animation:p 2s infinite}}
@keyframes p{{50%{{opacity:.4}}}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:18px}}
.card{{background:#11161f;border:1px solid #1f2733;border-radius:12px;padding:18px}}
.hero{{grid-column:1/-1;display:flex;gap:24px;align-items:center;flex-wrap:wrap}}
.eq{{font-size:36px;font-weight:700;font-variant-numeric:tabular-nums}}
.pos{{color:#22c55e}} .neg{{color:#ef4444}} .muted{{color:#8b98a9}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
td,th{{padding:6px;border-bottom:1px solid #1f2733;text-align:left}}
th{{font-size:10px;text-transform:uppercase;color:#8b98a9;letter-spacing:1px}}
.bar{{height:6px;background:#161d29;border-radius:6px;overflow:hidden;margin-top:8px}}
.fill{{height:100%;background:linear-gradient(90deg,#4a9eff,#7c5cff)}}
</style></head><body>
<h1><span class=dot></span>NSE Power Hour <span class=muted>14:00→15:15 · flat by close · paper</span></h1>
<div class=grid>
<div class="card hero"><div><div class=muted>EQUITY</div>
<div class="eq num">₹{eq:,.0f}</div><div class="chg {cls} num">({pnl:+,.0f})</div></div>
<div style=flex:1>{spark}</div></div>
<div class=card><h3>Paper gate · day {gate["days_elapsed"]} of {gate["required_days"]}</h3>
<div class=bar><div class=fill style="width:{pct}%"></div></div></div>
<div class=card><h3>Open positions ({s["open_positions"]})</h3><table>{pos_rows}</table></div>
<div class=card><h3>Recent trades</h3><table>{rows}</table></div>
</div><p class=muted style=margin-top:16px>JSON /health · refresh 15s</p></body></html>"""

    def serve_forever(self) -> None:
        trader = self
        bind_host = "0.0.0.0"  # Always bind to all interfaces for container compatibility

        class H(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                if self.path.startswith("/health"):
                    body = json.dumps(trader.snapshot()).encode()
                    ctype = "application/json"
                elif self.path.startswith("/dashboard") or self.path == "/":
                    body = trader._dashboard_html().encode()
                    ctype = "text/html; charset=utf-8"
                else:
                    self.send_response(404)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        ThreadingHTTPServer((bind_host, self.port), H).serve_forever()

    # --------------------------------------------------------- scheduling

    def _next_at(self, hour: int, minute: int) -> tuple[datetime, float]:
        now = self._ist_now()
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if now >= target or now.weekday() >= 5:
            target += timedelta(days=1)
            while target.weekday() >= 5:
                target += timedelta(days=1)
        return target, (target - now).total_seconds()

    def loop(self) -> None:
        while True:
            _, wait_enter = self._next_at(14, 0)
            _, wait_exit = self._next_at(15, 16)
            if wait_enter < wait_exit:
                time.sleep(max(1.0, wait_enter))
                try:
                    self.enter_phase()
                except Exception as exc:  # noqa: BLE001
                    logger.error("enter failed: %s", exc)
            else:
                time.sleep(max(1.0, min(wait_exit, 3600)))
                if self.state.phase == "entered":
                    try:
                        self.exit_phase()
                    except Exception as exc:  # noqa: BLE001
                        logger.error("exit failed: %s", exc)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols-file", default="tmp/nifty50.csv")
    ap.add_argument("--capital", type=float, default=100_000.0)
    ap.add_argument("--port", type=int, default=None, help=f"Port to bind (default: {_get_nse_powerhour_port()})")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO)
    import csv
    with open(args.symbols_file, newline="", encoding="utf-8") as f:
        symbols = [r["Symbol"].strip().upper() for r in csv.DictReader(f)]

    trader = PowerHourTrader(symbols, capital=args.capital, port=args.port)
    threading.Thread(target=trader.serve_forever, daemon=True).start()
    logger.info("power-hour up on :%d — %d symbols, Rs %.0f",
                args.port or _get_nse_powerhour_port(), len(symbols), args.capital)
    trader.loop()


if __name__ == "__main__":
    main()
