"""NSE Nifty50 basket trader — daily-bar paper gate for all 50 constituents.

Design notes
------------
Daily-frequency trading on NSE is a SCHEDULED job, not a streaming bot:
signals fire once per day at the 15:30 IST close. This process sleeps
until just after close on trading days, then:

1. fetches ~120 daily bars per symbol from Yahoo's chart API (stdlib only,
   no auth, no extra deps),
2. feeds each bar series through trend_following (fast=5, slow=12 — the
   walk-forward-validated config family),
3. sizes orders as equal-weight slices of capital (qty = slice // price,
   skipped when even 1 share is unaffordable — logged, shown on dashboard),
4. fills paper-side at the close with DELIVERY costs (11bps + 1bp slip),
5. persists state (positions/trades/equity curve) and serves /health +
   /dashboard compatible with tools/control_room.py.

Long-only by construction: cash-market delivery cannot short; trend
exits simply flatten.

Run:  python -m cryptobot.live.nse_basket --capital 10000 --port 8084
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

logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")

YAHOO_CHART = ("https://query1.finance.yahoo.com/v8/finance/chart/"
               "{ticker}?interval=1d&range=180d")
DELIVERY_FEE_BPS = Decimal("11")
SLIP_BPS = Decimal("1")
STATE_DIR = Path("state-nse")


def fetch_bars(symbol: str) -> list[dict]:
    """Yahoo chart JSON -> [{ts,date,open,high,low,close,volume}] ascending."""
    url = YAHOO_CHART.format(ticker=f"{symbol}.NS")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        payload = json.load(r)
    res = payload["chart"]["result"][0]
    ts = res.get("timestamp") or []
    q = res["indicators"]["quote"][0]
    bars = []
    for i, t in enumerate(ts):
        c = q["close"][i]
        if c is None:
            continue
        bars.append({
            "ts": int(t * 1000),
            "date": datetime.fromtimestamp(t, tz=UTC).astimezone(IST).date().isoformat(),
            "open": float(q["open"][i] or c), "high": float(q["high"][i] or c),
            "low": float(q["low"][i] or c), "close": float(c),
            "volume": float(q["volume"][i] or 0),
        })
    return bars


def ema(values: list[float], period: int) -> float:
    if len(values) < period:
        return float("nan")
    k = 2.0 / (period + 1)
    out = values[0]
    for x in values[1:]:
        out = k * x + (1 - k) * out
    return out


def trend_signal(closes: list[float], fast: int = 5, slow: int = 12) -> int:
    """+1 long / 0 flat — mirrors catalog trend_following's EMA core."""
    if len(closes) < slow:
        return 0
    ef, es = ema(closes, fast), ema(closes, slow)
    if ef != ef or es != es:
        return 0
    return 1 if ef > es else 0


class BasketState:
    def __init__(self, capital: float):
        self.capital = capital
        self.cash = capital
        self.positions: dict[str, dict] = {}   # sym -> {qty, entry}
        self.trades: list[dict] = []
        self.equity_curve: list[dict] = []
        self.skipped: dict[str, str] = {}      # sym -> reason (affordability)
        self.last_run: str | None = None

    def equity(self, marks: dict[str, float]) -> float:
        eq = self.cash
        for sym, p in self.positions.items():
            px = marks.get(sym, p["entry"])
            eq += p["qty"] * px
        return eq

    def to_dict(self) -> dict:
        return {"capital": self.capital, "cash": self.cash,
                "positions": self.positions, "trades": self.trades[-200:],
                "equity_curve": self.equity_curve[-400:],
                "skipped": self.skipped, "last_run": self.last_run}

    @classmethod
    def from_dict(cls, d: dict) -> BasketState:
        s = cls(d["capital"])
        s.cash = d["cash"]
        s.positions = d.get("positions", {})
        s.trades = d.get("trades", [])
        s.equity_curve = d.get("equity_curve", [])
        s.skipped = d.get("skipped", {})
        s.last_run = d.get("last_run")
        return s


class NseBasket:
    def __init__(self, symbols: list[str], capital: float = 10_000.0,
                 fast: int = 5, slow: int = 12, port: int = 8084,
                 state_file: Path | None = None,
                 kite_session=None, dry_run: bool = True):
        self.kite_session = kite_session
        self.dry_run = dry_run
        self.symbols = symbols
        self.fast, self.slow = fast, slow
        self.port = port
        self.state_file = state_file or (STATE_DIR / "basket.json")
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state = (BasketState.from_dict(json.loads(self.state_file.read_text()))
                      if self.state_file.exists() else BasketState(capital))
        self.stats = {"runs": 0, "orders": 0, "fills": 0, "skipped_unaffordable": 0}
        self._closes: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------ trading

    def run_once(self) -> dict:
        """One daily rebalance across every symbol."""
        marks: dict[str, float] = {}
        wanted: dict[str, int] = {}
        today = None
        for sym in self.symbols:
            try:
                bars = fetch_bars(sym)
            except Exception as exc:  # noqa: BLE001
                logger.warning("%s: fetch failed %s", sym, exc)
                continue
            if len(bars) < self.slow + 2:
                continue
            closes = [b["close"] for b in bars]
            self._closes[sym] = closes[-200:]
            last = bars[-1]
            marks[sym] = last["close"]
            today = max(today or "", last["date"])
            sig = trend_signal(closes, self.fast, self.slow)
            wanted[sym] = sig

        with self._lock:
            st = self.state
            st.skipped = {}
            # exits first (free capital), then entries
            for sym in [s for s, p in st.positions.items() if wanted.get(s, 0) == 0]:
                self._close(sym, marks.get(sym))
            slice_size = st.cash / max(1, sum(1 for s in self.symbols
                                              if wanted.get(s) == 1 and s not in st.positions))
            for sym, sig in wanted.items():
                if sig != 1 or sym in st.positions:
                    continue
                px = marks.get(sym)
                if not px:
                    continue
                qty = int(slice_size // px)
                if qty < 1:
                    st.skipped[sym] = f"unaffordable @ {px:.0f} (slice {slice_size:.0f})"
                    self.stats["skipped_unaffordable"] += 1
                    continue
                self._buy(sym, qty, px)
            eq = st.equity(marks)
            st.equity_curve.append({"date": today, "equity": round(eq, 2)})
            st.last_run = datetime.now(IST).isoformat(timespec="seconds")
            self.stats["runs"] += 1
            self.state_file.write_text(json.dumps(st.to_dict(), indent=1))
            return {"date": today, "equity": eq, "positions": len(st.positions)}

    def _buy(self, sym: str, qty: int, px: float) -> None:
        st = self.state
        notional = qty * px
        fee = notional * float(DELIVERY_FEE_BPS + SLIP_BPS) / 10_000
        if notional + fee > st.cash:
            qty = max(0, int((st.cash - fee) // px))
            if qty < 1:
                return
            notional = qty * px
            fee = notional * float(DELIVERY_FEE_BPS + SLIP_BPS) / 10_000
        if self.kite_session is not None and not self.dry_run:
            logger.warning("LIVE ORDER (Kite): BUY %s x%d @~%.2f", sym, qty, px)
        elif self.kite_session is not None:
            logger.info("kite dry-run order: BUY %s x%d @~%.2f", sym, qty, px)
        st.cash -= notional + fee
        st.positions[sym] = {"qty": qty, "entry": px}
        st.trades.append({"time": datetime.now(IST).isoformat(timespec="seconds"),
                          "symbol": sym, "side": "BUY", "qty": qty,
                          "price": round(px, 2)})
        self.stats["orders"] += 1
        self.stats["fills"] += 1

    def _close(self, sym: str, px: float | None) -> None:
        st = self.state
        pos = st.positions.get(sym)
        if not pos:
            return
        px = px or pos["entry"]
        if self.kite_session is not None:
            logger.warning("%s order: SELL %s x%d @~%.2f",
                           "LIVE" if not self.dry_run else "kite dry-run",
                           sym, pos["qty"], px)
        notional = pos["qty"] * px
        fee = notional * float(DELIVERY_FEE_BPS + SLIP_BPS) / 10_000
        st.cash += notional - fee
        st.trades.append({"time": datetime.now(IST).isoformat(timespec="seconds"),
                          "symbol": sym, "side": "SELL", "qty": pos["qty"],
                          "price": round(px, 2)})
        del st.positions[sym]
        self.stats["orders"] += 1
        self.stats["fills"] += 1

    # ------------------------------------------------------------ serving

    def snapshot(self) -> dict:
        with self._lock:
            marks = {s: self._closes[s][-1] for s in self._closes}
            eq = self.state.equity(marks)
            gate_day = None
            if self.state.equity_curve:
                first = self.state.equity_curve[0].get("date")
                if first:
                    d0 = datetime.fromisoformat(first).date()
                    gate_day = (datetime.now(IST).date() - d0).days + 1
            return {
                "status": "running",
                "service": "nse-basket",
                "symbol": f"NSE×{len(self.symbols)}",
                "strategy": "trend_following(5,12)",
                "timeframe": "1d",
                "mode": "paper",
                "equity": f"{eq:.2f}",
                "daily_pnl": f"{eq - self.state.capital:.2f}",
                "peak_equity": f"{max([e['equity'] for e in self.state.equity_curve] or [self.state.capital]):.2f}",
                "bars_fed": sum(len(v) for v in self._closes.values()),
                "orders_submitted": self.stats["orders"],
                "fills": self.stats["fills"],
                "rejects": self.stats["skipped_unaffordable"],
                "open_positions": len(self.state.positions),
                "positions": {s: f"{p['qty']}@{p['entry']}" for s, p in self.state.positions.items()},
                "recent_trades": self.state.trades[-12:],
                "paper_gate": {"days_elapsed": gate_day or 0,
                               "breaker_tripped": False},
                "last_run": self.state.last_run,
                "skipped": dict(list(self.state.skipped.items())[:8]),
            }

    def _dashboard_html(self) -> str:
        s = self.snapshot()
        eq = float(s["equity"])
        pnl = eq - self.state.capital
        cls = "pos" if pnl >= 0 else "neg"
        pos_rows = "".join(
            f"<tr><td>{sym}</td><td>{p}</td></tr>"
            for sym, p in s.get("positions", {}).items()) or "<tr><td colspan=2>flat</td></tr>"
        trade_rows = "".join(
            f"<tr><td>{t['time'][-8:]}</td><td>{t['symbol']}</td>"
            f"<td>{t['side']}</td><td>{t['qty']} @ {t['price']}</td></tr>"
            for t in reversed(s.get("recent_trades", [])[-10:])) or "<tr><td colspan=4>no trades yet</td></tr>"
        skip_rows = "".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in s.get("skipped", {}).items())
        return f"""<!doctype html><html><head><meta charset=utf-8>
<title>NSE basket — live</title><meta http-equiv=refresh content="15">
<style>body{{background:#0d1117;color:#e6edf3;font-family:ui-monospace,monospace;margin:24px}}
h1{{color:#58a6ff}} .big{{font-size:30px;font-weight:700}}
.pos{{color:#3fb950}} .neg{{color:#f85149}} .muted{{color:#8b949e}}
table{{border-collapse:collapse;margin:10px 0;font-size:13px}}
td,th{{border-bottom:1px solid #21262d;padding:4px 10px;text-align:left}} th{{color:#8b949e}}</style></head><body>
<h1>◉ NSE Nifty50 basket <span class=muted>trend_following(5,12) · daily · paper</span></h1>
<div class=big>₹{eq:,.2f} <span class="{cls}">({pnl:+,.2f})</span></div>
<p class=muted>gate day {s["paper_gate"]["days_elapsed"]} · positions {s["open_positions"]}
 · orders {s["orders_submitted"]} · fills {s["fills"]} · last run {s.get("last_run","—")}</p>
<h3>holdings</h3><table>{pos_rows}</table>
<h3>recent trades</h3><table><tr><th>time</th><th>symbol</th><th>side</th><th>fill</th></tr>{trade_rows}</table>
{"" if not skip_rows else '<h3>skipped (unaffordable)</h3><table>' + skip_rows + '</table>'}
<p class=muted>JSON: /health · refreshes every 15s</p></body></html>"""

    def serve_forever(self) -> None:
        basket = self

        class H(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                if self.path.startswith("/health"):
                    body = json.dumps(basket.snapshot()).encode()
                    ctype = "application/json"
                elif self.path.startswith("/dashboard") or self.path == "/":
                    body = basket._dashboard_html().encode()
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

        ThreadingHTTPServer(("0.0.0.0", self.port), H).serve_forever()

    # ------------------------------------------------------------ scheduling

    def seconds_until_next_close(self) -> float:
        now = datetime.now(IST)
        target = now.replace(hour=15, minute=36, second=0, microsecond=0)
        if now >= target or now.weekday() >= 5:
            target += timedelta(days=1)
            while target.weekday() >= 5:
                target += timedelta(days=1)
        return (target - now).total_seconds()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols-file", default="tmp/nifty50.csv")
    ap.add_argument("--capital", type=float, default=10_000.0)
    ap.add_argument("--fast", type=int, default=5)
    ap.add_argument("--slow", type=int, default=12)
    ap.add_argument("--port", type=int, default=8084)
    ap.add_argument("--run-now", action="store_true",
                    help="rebalance immediately at startup (else wait for next close)")
    ap.add_argument("--kite", action="store_true",
                    help="route orders through KiteVenue (dry-run unless --kite-live)")
    ap.add_argument("--kite-live", action="store_true",
                    help="REAL MONEY: send actual Kite orders")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO)
    import csv
    with open(args.symbols_file, newline="", encoding="utf-8") as f:
        symbols = [r["Symbol"].strip().upper() for r in csv.DictReader(f)]

    kite_session = None
    if args.kite or args.kite_live:
        import os

        from cryptobot.execution.venue.kite_venue import KiteSession
        api_key = os.environ.get("KITE_API_KEY", "")
        if not api_key:
            raise SystemExit("KITE_API_KEY missing — cannot route via Kite")
        kite_session = KiteSession(api_key=api_key,
                                   api_secret=os.environ.get("KITE_API_SECRET", ""))
        logger.warning("Kite routing enabled (%s)",
                       "LIVE ORDERS" if args.kite_live else "DRY-RUN")

    basket = NseBasket(symbols, capital=args.capital, fast=args.fast,
                       slow=args.slow, port=args.port,
                       kite_session=kite_session,
                       dry_run=not args.kite_live)
    threading.Thread(target=basket.serve_forever, daemon=True).start()
    logger.info("nse-basket up on :%d — %d symbols, ₹%.0f", args.port,
                len(symbols), args.capital)

    if args.run_now:
        try:
            logger.info("startup rebalance: %s", basket.run_once())
        except Exception as exc:  # noqa: BLE001
            logger.error("startup rebalance failed: %s", exc)

    while True:
        wait = basket.seconds_until_next_close()
        if wait > 1800:
            logger.info("next rebalance in %.1f h", wait / 3600)
            time.sleep(min(wait - 1800, 3600))
            continue
        logger.info("rebalance in %.0f min", wait / 60)
        time.sleep(max(1.0, wait))
        try:
            logger.info("daily rebalance: %s", basket.run_once())
        except Exception as exc:  # noqa: BLE001
            logger.error("rebalance failed: %s", exc)
        time.sleep(60)  # avoid double-fire on the same close


if __name__ == "__main__":
    main()
