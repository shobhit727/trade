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
from datetime import time as dt_time
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from zoneinfo import ZoneInfo

from cryptobot.config import get_settings
from cryptobot.core.tax_equity import TaxLedger

logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")

def _get_yahoo_chart_url() -> str:
    return get_settings().external_services.yahoo_finance_chart_url

def _get_http_default_timeout() -> int:
    return get_settings().timeouts.http_default_timeout

def _get_nse_basket_port() -> int:
    return get_settings().server.nse_basket_port

DELIVERY_FEE_BPS = Decimal("11")
SLIP_BPS = Decimal("1")
STATE_DIR = Path("state-nse")


def fetch_bars(symbol: str) -> list[dict]:
    """Yahoo chart JSON -> [{ts,date,open,high,low,close,volume}] ascending."""
    url = f"{_get_yahoo_chart_url()}{symbol}.NS?interval=1d&range=180d"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=_get_http_default_timeout()) as r:
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


def _svg_chart(values: list[float], w: int = 260, h: int = 64) -> str:
    """Minimal inline SVG area chart."""
    if len(values) < 2:
        return "<span class=muted>collecting…</span>"
    lo, hi = min(values), max(values)
    rng = (hi - lo) or 1
    pts = [(i / (len(values) - 1)) * w for i in range(len(values))]
    ys = [h - ((v - lo) / rng) * (h - 6) - 3 for v in values]
    poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(pts, ys, strict=False))
    up = values[-1] >= values[0]
    color = "#22c55e" if up else "#ef4444"
    gid = f"g{abs(hash(tuple(values[:9]))) % 99999}"
    return (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
            f'<defs><linearGradient id="{gid}" x1=0 y1=0 x2=0 y2=1>'
            f'<stop offset=0 stop-color="{color}" stop-opacity=.25/>'
            f'<stop offset=1 stop-color="{color}" stop-opacity=0/></linearGradient></defs>'
            f'<polygon points="0,{h} {poly} {w},{h}" fill="url(#{gid})"/>'
            f'<polyline points="{poly}" fill=none stroke="{color}" stroke-width=1.8 '
            f'stroke-linejoin=round/></svg>')


class BasketState:
    def __init__(self, capital: float):
        self.capital = capital
        self.cash = capital
        self.peak_equity: float = capital
        self.breaker_tripped: bool = False
        self.breaker_reason: str | None = None
        self.positions: dict[str, dict] = {}   # sym -> {qty, entry}
        self.trades: list[dict] = []
        self.equity_curve: list[dict] = []
        self.skipped: dict[str, str] = {}      # sym -> reason (affordability)
        self.last_run: str | None = None
        self.tax = TaxLedger()

    def equity(self, marks: dict[str, float]) -> float:
        eq = self.cash
        for sym, p in self.positions.items():
            px = marks.get(sym, p["entry"])
            eq += p["qty"] * px
        return eq

    def to_dict(self) -> dict:
        return {"capital": self.capital, "cash": self.cash,
                "peak_equity": self.peak_equity,
                "breaker_tripped": self.breaker_tripped,
                "breaker_reason": self.breaker_reason,
                "positions": self.positions, "trades": self.trades[-200:],
                "equity_curve": self.equity_curve[-400:],
                "skipped": self.skipped, "last_run": self.last_run,
                "tax_lots": {s: [{"qty": lot.qty, "price": lot.price,
                                  "date": lot.date.isoformat()}
                                 for lot in lots]
                             for s, lots in self.tax.lots.items()},
                "tax_records": self.tax.to_dicts()}

    @classmethod
    def from_dict(cls, d: dict) -> BasketState:
        s = cls(d["capital"])
        s.cash = d["cash"]
        s.peak_equity = d.get("peak_equity", d["capital"])
        s.breaker_tripped = d.get("breaker_tripped", False)
        s.breaker_reason = d.get("breaker_reason")
        s.positions = d.get("positions", {})
        s.trades = d.get("trades", [])
        s.equity_curve = d.get("equity_curve", [])
        s.skipped = d.get("skipped", {})
        s.last_run = d.get("last_run")
        # Restore tax lots from saved state
        for sym, lots in d.get("tax_lots", {}).items():
            for lot in lots:
                s.tax.on_buy(sym, lot["qty"], lot["price"],
                             datetime.fromisoformat(lot["date"]))
        # Reconcile: if positions exist but tax lots are missing, rebuild from trades
        for sym, pos in s.positions.items():
            if sym not in s.tax.lots or not s.tax.lots[sym]:
                # Find first BUY trade for this symbol to get entry date/price
                entry_trade = next(
                    (t for t in s.trades if t["symbol"] == sym and t["side"] == "BUY"),
                    None
                )
                if entry_trade:
                    entry_date = datetime.fromisoformat(entry_trade["time"])
                    s.tax.on_buy(sym, pos["qty"], pos["entry"], entry_date)
                else:
                    # Fallback: use position entry price and current time
                    s.tax.on_buy(sym, pos["qty"], pos["entry"], datetime.now(IST))
        return s


class NseBasket:
    def __init__(self, symbols: list[str], capital: float = 10_000.0,
                 fast: int = 5, slow: int = 12, port: int | None = None,
                 state_file: Path | None = None,
                 kite_session=None, dry_run: bool = True):
        self.kite_session = kite_session
        self.dry_run = dry_run
        self.symbols = symbols
        self.fast, self.slow = fast, slow
        self.port = port if port is not None else _get_nse_basket_port()
        self.state_file = state_file or (STATE_DIR / "basket.json")
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state = (BasketState.from_dict(json.loads(self.state_file.read_text()))
                      if self.state_file.exists() else BasketState(capital))
        self.stats = {"runs": 0, "orders": 0, "fills": 0, "skipped_unaffordable": 0}
        self._closes: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------ trading

    def _ist_today(self) -> str:
        return self._ist_now().date().isoformat()

    def _ist_now(self) -> datetime:
        return datetime.now(IST)

    def run_once(self) -> dict:
        """One daily rebalance across every symbol."""
        marks: dict[str, float] = {}
        wanted: dict[str, int] = {}
        today = None
        stale: set[str] = set()
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
            # NSE holiday / session not closed yet: newest bar is stale.
            if last["date"] != self._ist_today():
                stale.add(sym)
            sig = trend_signal(closes, self.fast, self.slow)
            wanted[sym] = sig

        # If EVERY symbol is stale, the market did not trade today (holiday)
        # — do nothing rather than re-trade yesterday's signals.
        if len(stale) == len(self.symbols):
            logger.info("market closed today (%s) — rebalance skipped", today)
            return {"date": today, "equity": self.state.equity(marks),
                    "positions": len(self.state.positions), "skipped_holiday": True}

        with self._lock:
            st = self.state
            # Breaker runs EVERY cycle — even on restarts mid-day.
            eq_now = st.equity(marks)
            if not st.breaker_tripped:
                st.peak_equity = max(st.peak_equity, eq_now)
                if st.peak_equity > 0 and eq_now <= st.peak_equity * 0.75:
                    st.breaker_tripped = True
                    st.breaker_reason = (f"equity {eq_now:,.0f} <= 75% of peak "
                                         f"{st.peak_equity:,.0f} on {today}")
                    logger.error("BREAKER TRIPPED: %s — flattening all positions",
                                 st.breaker_reason)
                    for sym in list(st.positions.keys()):
                        self._close(sym, marks.get(sym))
            # Trade at most ONCE per calendar day, never while the market is
            # open: restarts (--run-now) must warm up, not churn the book.
            already_traded = bool(st.last_run and st.last_run[:10] == today)
            market_open = self._ist_now().time() < dt_time(15, 30)
            if already_traded or market_open or st.breaker_tripped:
                why = ("breaker tripped" if st.breaker_tripped else
                       "already traded today" if already_traded else "market open")
                logger.info("trade gate: %s — marks refreshed, no orders", why)
                return {"date": today, "equity": st.equity(marks),
                        "positions": len(st.positions), "no_trade_reason": why}
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
            if st.breaker_tripped:
                wanted = {}   # breaker open: no further entries
            st.last_run = self._ist_now().isoformat(timespec="seconds")
            self.stats["runs"] += 1
            self.state_file.write_text(json.dumps(st.to_dict(), indent=1))
            result = {"date": today, "equity": eq, "positions": len(st.positions)}
        # notify OUTSIDE the lock: snapshot() takes it too (non-reentrant)
        try:
            self._notify(result)
        except Exception as exc:  # noqa: BLE001
            logger.warning("notify failed: %s", exc)
        return result

    def _notify(self, result: dict) -> None:
        """Evening P&L ping via WhatsApp/email when env-configured."""
        s = self.snapshot()
        pnl = float(s["equity"]) - self.state.capital
        lines = [f"NSE basket {result.get('date','')}",
                 f"Equity Rs {float(s['equity']):,.0f} ({pnl:+,.0f})",
                 f"Positions {s['open_positions']} | gate day {s['paper_gate']['days_elapsed']}/60"]
        if self.state.breaker_tripped:
            lines.append(f"BREAKER TRIPPED: {self.state.breaker_reason}")
        text = "\n".join(lines)
        from cryptobot.monitoring.whatsapp import WhatsAppConfig, send_whatsapp
        cfg = WhatsAppConfig.from_env()
        if cfg.configured():
            import asyncio
            asyncio.run(send_whatsapp(text, cfg))
        from cryptobot.monitoring.email_digest import EmailConfig, send_digest
        if EmailConfig.from_env().configured():
            send_digest({"equity": s["equity"],
                         "daily_pnl": f"{pnl:+,.2f}",
                         "open_positions": s["open_positions"],
                         "recent_trades": s.get("recent_trades", [])},
                        subject_prefix="[nse-basket]")

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
        st.tax.on_buy(sym, float(qty), px, datetime.now(IST))
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
        st.tax.on_sell(sym, float(pos["qty"]), px,
                       datetime.now(IST))
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
            pos_view = {}
            for s, p in self.state.positions.items():
                mark = self._closes.get(s, [p["entry"]])[-1] if self._closes.get(s) else p["entry"]
                qty = p["qty"]
                pos_view[s] = {"qty": qty, "entry": round(p["entry"], 2),
                               "mark": round(mark, 2),
                               "pnl": round(qty * (mark - p["entry"]), 2)}
            return {
                "status": "running",
                "service": "nse-basket",
                "equity_curve": self.state.equity_curve[-120:],
                "symbol": f"NSE×{len(self.symbols)}",
                "strategy": "trend_following(5,12)",
                "timeframe": "1d",
                "mode": "paper",
                "equity": f"{eq:.2f}",
                "daily_pnl": f"{eq - self.state.capital:.2f}",
                "bars_fed": sum(len(v) for v in self._closes.values()),
                "orders_submitted": self.stats["orders"],
                "fills": self.stats["fills"],
                "rejects": self.stats["skipped_unaffordable"],
                "open_positions": len(self.state.positions),
                "positions_detail": pos_view,
                "positions": {s: f"{p['qty']}@{p['entry']}" for s, p in self.state.positions.items()},
                "trades_total": len(self.state.trades),
                "tax_summary": self.state.tax.summary(),
                "recent_trades": self.state.trades[-60:],
                "paper_gate": {"days_elapsed": gate_day or 0,
                               "required_days": 60,
                               "breaker_tripped": self.state.breaker_tripped,
                               "breaker_reason": self.state.breaker_reason},
                "peak_equity": f"{self.state.peak_equity:.2f}",
                "last_run": self.state.last_run,
                "skipped": dict(list(self.state.skipped.items())[:8]),
            }

    def _dashboard_html(self) -> str:
        s = self.snapshot()
        eq = float(s["equity"])
        pnl = eq - self.state.capital
        pnl_pct = pnl / self.state.capital * 100
        cls = "pos" if pnl >= 0 else "neg"
        curve = s.get("equity_curve", [])
        spark = _svg_chart([c["equity"] for c in curve])
        day = s["paper_gate"]["days_elapsed"]
        gate_pct = min(100, day / 60 * 100)
        pos_rows = "".join(
            f"<tr><td class=sym>{sym}</td><td class=num>{p['qty']}</td>"
            f"<td class=num>₹{p['entry']:,.2f}</td><td class=num>₹{p['mark']:,.2f}</td>"
            f"<td class=num class={'pos' if p['pnl']>=0 else 'neg'}>₹{p['pnl']:+,.2f}</td></tr>"
            for sym, p in sorted(s.get("positions_detail", {}).items())
        ) or '<tr><td colspan=5 class=muted>flat — waiting for signals</td></tr>'
        trade_rows = "".join(
            f"<tr><td class=muted>{t['time'][5:16].replace('T',' ')}</td>"
            f"<td class=sym>{t['symbol']}</td>"
            f"<td><span class='pill {"buy" if t["side"]=="BUY" else "sell"}'>{t['side']}</span></td>"
            f"<td class=num>{t['qty']}</td><td class=num>₹{t['price']:,.2f}</td></tr>"
            for t in reversed(s.get("recent_trades", []))
        ) or '<tr><td colspan=5 class=muted>no trades yet</td></tr>'
        skip_rows = "".join(
            f"<tr><td class=sym>{k}</td><td class=muted>{v}</td></tr>"
            for k, v in list(s.get("skipped", {}).items())[:10])
        return f"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>NSE Basket — Live</title><meta http-equiv=refresh content="15">
<style>
:root{{--bg:#0a0e14;--s1:#11161f;--s2:#161d29;--bd:#1f2733;--tx:#e6edf3;
--mut:#8b98a9;--ac:#4a9eff;--pos:#22c55e;--neg:#ef4444}}
*{{box-sizing:border-box;margin:0}}
body{{background:var(--bg);color:var(--tx);font:14px/1.5 system-ui,-apple-system,sans-serif;padding:28px;max-width:1080px;margin-inline:auto}}
.num{{font-variant-numeric:tabular-nums}}
header{{display:flex;justify-content:space-between;align-items:center;margin-bottom:22px}}
h1{{font-size:17px;font-weight:600;letter-spacing:.2px;display:flex;gap:10px;align-items:center}}
.dot{{width:8px;height:8px;border-radius:50%;background:var(--pos);box-shadow:0 0 8px var(--pos);animation:pulse 2s infinite}}
@keyframes pulse{{50%{{opacity:.4}}}}
.muted{{color:var(--mut)}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}
.card{{background:var(--s1);border:1px solid var(--bd);border-radius:12px;padding:18px}}
.card h3{{font-size:11px;text-transform:uppercase;letter-spacing:1.2px;color:var(--mut);margin-bottom:12px}}
.hero{{grid-column:1/-1;display:flex;gap:24px;align-items:center;flex-wrap:wrap}}
.eq{{font-size:38px;font-weight:700;font-variant-numeric:tabular-nums;letter-spacing:-1px}}
.chg{{font-size:16px;font-weight:600}}
.pos{{color:var(--pos)}} .neg{{color:var(--neg)}}
.spark{{flex:1;min-width:220px}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
td,th{{padding:7px 6px;border-bottom:1px solid var(--bd);text-align:left}}
th{{font-size:10px;text-transform:uppercase;letter-spacing:1px;color:var(--mut);font-weight:500}}
tr:last-child td{{border-bottom:none}}
tbody tr:hover{{background:var(--s2)}}
.sym{{font-weight:600;letter-spacing:.3px}}
.pill{{font-size:10px;font-weight:700;padding:2px 8px;border-radius:20px;letter-spacing:.5px}}
.pill.buy{{background:rgba(34,197,94,.12);color:var(--pos)}}
.pill.sell{{background:rgba(239,68,68,.12);color:var(--neg)}}
.gate{{grid-column:1/-1}}
.bar{{height:6px;background:var(--s2);border-radius:6px;overflow:hidden;margin-top:8px}}
.fill{{height:100%;background:linear-gradient(90deg,var(--ac),#7c5cff);border-radius:6px}}
footer{{margin-top:20px;font-size:12px;color:var(--mut)}}
a{{color:var(--ac)}}
@media(max-width:720px){{.grid{{grid-template-columns:1fr}}}}
</style></head><body>
<header><h1><span class=dot></span>NSE Nifty50 Basket</h1>
<span class="muted num">{s.get("last_run","—")} IST</span></header>
<div class=grid>
<div class="card hero">
 <div><div class=muted style=font-size:11px;letter-spacing:1px>EQUITY</div>
   <div class="eq num">₹{eq:,.0f}</div>
   <div class="chg {cls} num">{pnl:+,.0f} ({pnl_pct:+.2f}%)</div></div>
 <div class=spark>{spark}</div>
</div>
<div class="card gate">
 <h3>Paper gate · day {day} of 60</h3>
 <div class=bar><div class=fill style="width:{gate_pct}%"></div></div>
 <p class="muted" style="margin-top:8px;font-size:12px">pass = net positive · Sharpe ≥ 1 · zero breaker trips</p>
</div>
<div class=card><h3>Holdings · {s["open_positions"]}</h3>
<table><thead><tr><th>Symbol</th><th style=text-align:right>Qty</th><th style=text-align:right>Entry</th><th style=text-align:right>Mark</th><th style=text-align:right>P&L</th></tr></thead>
<tbody>{pos_rows}</tbody></table></div>
<div class=card><h3>Trades · {s["trades_total"]} total</h3>
<table><thead><tr><th>Time</th><th>Symbol</th><th>Side</th><th style=text-align:right>Qty</th><th style=text-align:right>Price</th></tr></thead>
<tbody>{trade_rows}</tbody></table></div>
{"" if not skip_rows else f'<div class="card" style="grid-column:1/-1"><h3>Skipped — unaffordable at current slice</h3><table><tbody>{skip_rows}</tbody></table></div>'}
</div>
<footer>JSON <a href=/health>/health</a> · refresh 15s · capital ₹{self.state.capital:,.0f} · delivery costs 11+1 bps/side</footer>
</body></html>"""

    def reset_breaker(self) -> None:
        """Manual reset after a breaker trip (owner decision, never auto)."""
        with self._lock:
            self.state.breaker_tripped = False
            self.state.breaker_reason = None
            # re-anchor peak at current equity so the next trip needs a fresh -25%
            marks = {s: v[-1] for s, v in self._closes.items()}
            self.state.peak_equity = self.state.equity(marks)
            self.state_file.write_text(json.dumps(self.state.to_dict(), indent=1))
        logger.warning("breaker manually reset; peak re-anchored")

    def serve_forever(self) -> None:
        basket = self
        bind_host = "0.0.0.0"  # Always bind to all interfaces for container compatibility

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

        ThreadingHTTPServer((bind_host, self.port), H).serve_forever()

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
    ap.add_argument("--port", type=int, default=None, help=f"Port to bind (default: {_get_nse_basket_port()})")
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
    logger.info("nse-basket up on :%d — %d symbols, ₹%.0f", args.port or _get_nse_basket_port(),
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
