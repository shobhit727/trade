from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Any

from cryptobot.monitoring.web_backtest import get_backtest_manager

from cryptobot.config import get_settings

def _get_server_host() -> str:
    return get_settings().server.host

def _get_server_port() -> int:
    return get_settings().server.port

logger = logging.getLogger(__name__)


HEALTH_PATH = "/health"
METRICS_PATH = "/metrics"
DASHBOARD_PATH = "/dashboard"


class _HealthSnapshot:
    def __init__(self):
        self.started_at = datetime.now(UTC)

    def snapshot(self) -> dict[str, Any]:
        uptime = (datetime.now(UTC) - self.started_at).total_seconds()
        base: dict[str, Any] = {
            "status": "ok",
            "service": "cryptobot",
            "uptime_seconds": round(uptime, 3),
            "now": datetime.now(UTC).isoformat(),
        }
        try:
            from cryptobot.monitoring.health import get_health_monitor

            monitor = get_health_monitor()
            component_health = monitor.get_all_health()
            if component_health:
                base["status"] = monitor.get_overall_status().value
                base["components"] = {
                    comp.value: {
                        "status": ch.status.value,
                        "checks": [
                            {
                                "name": c.check_name,
                                "status": c.status.value,
                                "message": c.message,
                                "details": c.details,
                            }
                            for c in ch.checks
                        ],
                    }
                    for comp, ch in component_health.items()
                }
        except Exception:  # pragma: no cover - health monitor is best-effort
            logger.debug("health snapshot: monitor unavailable", exc_info=True)
        return base


class _Handler(BaseHTTPRequestHandler):
    server_version = "cryptobot/0.1"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        logger.debug("%s - %s", self.address_string(), format % args)

    def do_POST(self):  # noqa: N802
        from urllib.parse import parse_qs, urlparse

        parsed = urlparse(self.path)
        if parsed.path != "/api/backtest/start":
            self.send_response(404)
            self.end_headers()
            return
        qs = parse_qs(parsed.query)
        symbol = (qs.get("symbol") or ["BTCUSDT"])[0]
        timeframe = (qs.get("timeframe") or ["1d"])[0]
        capital = (qs.get("capital") or ["10000"])[0]
        ok, msg = get_backtest_manager().start(symbol, timeframe, capital)
        body = ('{"ok": ' + ("true" if ok else "false") + ', "msg": "' + msg.replace('"', "'") + '"}').encode()
        self.send_response(200 if ok else 409)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        from urllib.parse import urlparse

        path = urlparse(self.path).path  # strip query so ?name=... still routes
        if path == HEALTH_PATH:
            snap = self.server.health_snapshot.snapshot()  # type: ignore[attr-defined]
            body = json.dumps(snap).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/api/backtest/trades":
            from urllib.parse import parse_qs, urlparse

            qs = parse_qs(urlparse(self.path).query)
            name = (qs.get("name") or [""])[0]
            snap = get_backtest_manager().trades_for(name)
            body = json.dumps(snap).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/api/backtest/status":
            snap = get_backtest_manager().status()
            body = json.dumps(snap).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path == DASHBOARD_PATH:
            snap = self.server.health_snapshot.snapshot()  # type: ignore[attr-defined]
            body = render_dashboard_html(snap).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path == METRICS_PATH:
            try:
                from cryptobot.monitoring.metrics import get_metrics_text
                body = get_metrics_text().encode()
            except Exception as exc:
                logger.warning("metrics scrape failed: %s", exc)
                body = b""
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        body = b'{"error":"not found"}'
        self.send_response(404)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class HealthServer:
    """Tiny stdlib HTTP server exposing ``/health`` and ``/metrics``."""

    def __init__(self, host: str | None = None, port: int | None = None):
        self.host = host if host is not None else _get_server_host()
        self.port = port if port is not None else _get_server_port()
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: Thread | None = None

    def start(self) -> None:
        if self._httpd is not None:
            return
        snap = _HealthSnapshot()
        try:
            httpd = ThreadingHTTPServer((self.host, self.port), _Handler)
        except OSError as exc:
            if exc.errno == 98:  # EADDRINUSE
                raise RuntimeError(
                    f"health server cannot bind {self.host}:{self.port} - port already in use. "
                    f"Start the bot with a free port, e.g. --port 8081"
                ) from exc
            raise
        httpd.health_snapshot = snap  # type: ignore[attr-defined]
        self._httpd = httpd
        self._thread = Thread(target=httpd.serve_forever, name="cryptobot-health", daemon=True)
        self._thread.start()
        logger.info("health server listening on http://%s:%d%s", self.host, self.port, HEALTH_PATH)

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
        self._thread = None


def _sparkline_svg(points: list[float], width: int = 560, height: int = 90) -> str:
    """Inline SVG polyline for the equity curve; handles flat/empty data."""
    if len(points) < 2:
        return '<div class="spark-empty">collecting data…</div>'
    vmin, vmax = min(points), max(points)
    span = (vmax - vmin) or 1.0
    step = width / (len(points) - 1)
    coords = [
        (i * step, height - 8 - ((v - vmin) / span) * (height - 16))
        for i, v in enumerate(points)
    ]
    poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
    color = "#3fb950" if points[-1] >= points[0] else "#f85149"
    return (
        f'<svg viewBox="0 0 {width} {height}" preserveAspectRatio="none" '
        f'class="spark"><polyline fill="none" stroke="{color}" stroke-width="2" '
        f'points="{poly}"/></svg>'
    )


def _price_chart_svg(price_history: list[dict], trades: list[dict],
                     width: int = 960, height: int = 260) -> str:
    """Price line + BUY/SELL markers. Times are ISO strings."""
    if len(price_history) < 2:
        return '<div class="spark-empty">collecting price history…</div>'

    def tsv(ts: str) -> float:
        try:
            from datetime import datetime as _dt
            return _dt.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
        except Exception:  # noqa: BLE001
            return 0.0

    pts = [(tsv(p["ts"]), float(p["close"])) for p in price_history]
    t0, t1 = pts[0][0], pts[-1][0]
    span_t = (t1 - t0) or 1.0
    prices = [v for _x, v in pts] + [float(tr.get("price") or 0) for tr in trades]
    vmin, vmax = min(prices), max(prices)
    span_p = (vmax - vmin) or 1.0

    def X(ts: float) -> float:
        return (ts - t0) / span_t * (width - 10) + 5

    def Y(v: float) -> float:
        return height - 14 - ((v - vmin) / span_p) * (height - 24)

    poly = " ".join(f"{X(x):.1f},{Y(v):.1f}" for x, v in pts)
    last_x, last_y = X(pts[-1][0]), Y(pts[-1][1])

    markers = []
    for tr in trades:
        ts = tsv(tr.get("ts", ""))
        if ts < t0:
            continue
        px = min(X(ts), width - 5)
        py = Y(min(max(float(tr.get("price") or vmin), vmin), vmax))
        buy = str(tr.get("side", "")).upper() == "BUY"
        color = "#3fb950" if buy else "#f85149"
        shape = (f'<path d="M {px:.1f} {py - 6:.1f} l 5 8 l -10 0 z"'
                 if buy else
                 f'<path d="M {px:.1f} {py + 6:.1f} l 5 -8 l -10 0 z"')
        markers.append(f'<{shape[1:]} fill="{color}" stroke="#0d1117" stroke-width="0.5"><title>'
                       f'{esc_static(tr.get("side"))} {tr.get("qty")} @ {tr.get("price")}</title></path>')

    first_d = price_history[0]["ts"][:10]
    last_d = price_history[-1]["ts"][:10]
    return (
        f'<svg viewBox="0 0 {width} {height}" class="spark" preserveAspectRatio="none">'
        f'<polyline fill="none" stroke="#58a6ff" stroke-width="1.6" points="{poly}"/>'
        f'<circle cx="{last_x:.1f}" cy="{last_y:.1f}" r="3" fill="#58a6ff"/>'
        + "".join(markers) +
        f'<text x="6" y="{height - 3}" fill="#8b949e" font-size="10">{first_d}</text>'
        f'<text x="{width - 6}" y="{height - 3}" fill="#8b949e" font-size="10" '
        f'text-anchor="end">{last_d}</text>'
        f'<text x="{last_x - 6:.1f}" y="{max(last_y - 8, 10):.1f}" fill="#58a6ff" '
        f'font-size="11" text-anchor="end">{pts[-1][1]:,.2f}</text>'
        "</svg>"
    )


def esc_static(value) -> str:
    import html as _h

    return _h.escape(str(value))


def render_dashboard_html(snap: dict) -> str:
    """Read-only family dashboard: cards, sparkline, gate progress."""
    import html as _html

    def esc(value):
        return _html.escape(str(value))

    def money(value):
        try:
            return f"{float(value):,.2f}"
        except (TypeError, ValueError):
            return esc(value)

    fund = snap.get("global_fund") or {}
    gate = snap.get("paper_gate") or {}
    breaker = snap.get("breaker") or {}
    tax = snap.get("tax_summary") or {}
    curve = [float(p["equity"]) for p in snap.get("equity_curve", []) if p.get("equity")]

    status = snap.get("status", "-")
    tripped = bool(breaker.get("tripped"))
    frozen = bool(fund.get("frozen"))
    daily_pnl = float(snap.get("daily_pnl") or 0)
    pnl_cls = "pos" if daily_pnl > 0 else ("neg" if daily_pnl < 0 else "")

    days = int(gate.get("days_elapsed", 0))
    window = int(gate.get("window_days", 60)) or 60
    pct = min(100, int(days * 100 / window))

    status_cls = "ok" if status == "running" else "warn"
    breaker_html = (
        '<span class="pill bad">TRIPPED</span>'
        f'<div class="sub">{esc(breaker.get("reason", ""))}</div>'
        if tripped
        else '<span class="pill ok">armed</span>'
             f'<div class="sub">trips at {esc(breaker.get("max_drawdown", "-25%"))} from peak</div>'
    )

    warning = ""
    if snap.get("allocator_warning"):
        warning = f'<div class="banner warn">⚠ {esc(snap["allocator_warning"])}</div>'

    rows = "".join(
        f"<tr><td>{esc(k)}</td><td class='num'>{esc(v)}</td></tr>"
        for k, v in [
            ("Total proceeds", money(tax.get("total_proceeds"))),
            ("Taxable income", money(tax.get("taxable_income"))),
            ("Est. tax (30%+cess)", money(tax.get("estimated_tax"))),
            ("TDS credits", money(tax.get("tds_credits"))),
            ("Net payable", money(tax.get("net_tax_payable"))),
        ]
    )

    head = (
        '<!doctype html><html><head><meta charset="utf-8">'
        '<meta http-equiv="refresh" content="30">'
        "<title>cryptobot - live status</title>"
        "<style>"
        ":root{--bg:#0d1117;--card:#161b22;--line:#21262d;--fg:#e6edf3;"
        "--dim:#8b949e;--green:#3fb950;--red:#f85149;--amber:#d29922;--blue:#58a6ff}"
        "*{box-sizing:border-box}"
        "body{margin:0;padding:24px;background:var(--bg);color:var(--fg);"
        'font:14px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif}'
        "h1{font-size:18px;margin:0 0 4px;display:inline-block;margin-right:12px}"
        ".head{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:20px}"
        ".pill{padding:2px 10px;border-radius:999px;font-size:12px;font-weight:600}"
        ".pill.ok{background:#12351c;color:var(--green);border:1px solid #1f4d2a}"
        ".pill.bad{background:#3d1418;color:var(--red);border:1px solid #67272c}"
        ".pill.warn{background:#332a10;color:var(--amber);border:1px solid #57491b}"
        ".muted{color:var(--dim);font-size:12px}"
        ".grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px}"
        ".card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px}"
        ".card h2{font-size:11px;text-transform:uppercase;letter-spacing:.08em;"
        "color:var(--dim);margin:0 0 8px}"
        ".big{font-size:26px;font-weight:700;font-variant-numeric:tabular-nums}"
        ".big.pos{color:var(--green)}.big.neg{color:var(--red)}"
        ".kv{display:flex;justify-content:space-between;gap:8px;padding:3px 0;font-size:13px}"
        ".kv b{font-weight:600;font-variant-numeric:tabular-nums}"
        ".kv span{color:var(--dim)}"
        "table{width:100%;border-collapse:collapse;font-size:13px}"
        "td{padding:4px 0;border-top:1px solid var(--line)}"
        "td:first-child{color:var(--dim)}"
        "td.num{text-align:right;font-variant-numeric:tabular-nums}"
        ".bar{height:8px;background:#21262d;border-radius:99px;overflow:hidden;margin:8px 0 6px}"
        ".bar i{display:block;height:100%;background:var(--blue)}"
        ".spark{width:100%;height:90px;display:block}"
        '.spark-empty{color:var(--dim);font-size:12px;padding:36px 0;text-align:center}'
        ".banner{grid-column:1/-1;background:#332a10;border:1px solid #57491b;"
        "color:var(--amber);border-radius:10px;padding:10px 14px;font-size:13px}"
        ".foot{margin-top:18px;color:var(--dim);font-size:12px}"
        "a{color:var(--blue)}"
        "button{background:var(--blue);color:#0d1117;border:0;border-radius:6px;"
        "padding:6px 14px;font-weight:600;cursor:pointer}"
        "input,select{background:#0d1117;color:var(--fg);border:1px solid var(--line);"
        "border-radius:6px;padding:4px 8px}"
        "th{text-align:left;color:var(--dim);font-size:11px;text-transform:uppercase;"
        "letter-spacing:.06em;padding:6px 8px;border-bottom:1px solid var(--line)}"
        "#sw-table td{padding:5px 8px}"
        ".pos{color:var(--green)}.neg{color:var(--red)}"
        "</style></head><body>"
    )

    parts = [
        head,
        '<div class="head"><h1>Cryptobot</h1>',
        f'<span class="pill {status_cls}">{esc(status)}</span>',
        '<span class="muted">'
        f"{esc(snap.get('strategy'))} · {esc(snap.get('symbol'))} · "
        f"{esc(snap.get('timeframe'))} · {esc(snap.get('mode'))} mode · "
        f"profile {esc(snap.get('risk_profile'))}</span></div>",
    ]
    if warning:
        parts.append(warning)
    parts.append('<div class="grid">')

    # Equity card
    parts.append(
        '<div class="card"><h2>Equity</h2>'
        f'<div class="big">{money(snap.get("equity"))}</div>'
        f'<div class="kv"><span>today&#39;s P&amp;L</span><b class="{pnl_cls}">{money(daily_pnl)}</b></div>'
        f'<div class="kv"><span>peak equity</span><b>{money(snap.get("peak_equity"))}</b></div>'
        '<div class="kv"><span>max drawdown</span>'
        f"<b>{esc(snap.get('max_drawdown_pct', '0.0'))}%</b></div></div>"
    )
    # Price & trades chart card
    parts.append(
        '<div class="card" style="grid-column:1/-1"><h2>'
        + esc(snap.get("symbol", "")) + ' price &amp; trades</h2>'
        + _price_chart_svg(snap.get("price_history", []),
                           snap.get("recent_trades", []))
        + '<div class="muted" style="margin-top:6px">'
          '&#9650; BUY / &#9660; SELL markers on close prices · updates every 30s</div></div>'
    )

    # Curve card
    parts.append(
        '<div class="card"><h2>Equity curve</h2>'
        + _sparkline_svg(curve)
        + f'<div class="muted" style="margin-top:6px">last {len(curve)} snapshots</div></div>'
    )
    # Trading card
    parts.append(
        '<div class="card"><h2>Trading</h2>'
        f'<div class="kv"><span>bars seen / fed</span><b>{snap.get("bars_seen", 0)} / {snap.get("bars_fed", 0)}</b></div>'
        f'<div class="kv"><span>orders submitted</span><b>{snap.get("orders_submitted", 0)}</b></div>'
        f'<div class="kv"><span>fills</span><b>{snap.get("fills", 0)}</b></div>'
        f'<div class="kv"><span>rejects</span><b>{snap.get("rejects", 0)}</b></div>'
        f'<div class="kv"><span>open positions</span><b>{snap.get("open_positions", 0)}</b></div>'
        f'<div class="kv"><span>last close</span><b>{money(snap.get("last_close") or 0)}</b></div></div>'
    )
    # Gate card
    parts.append(
        '<div class="card"><h2>Paper gate &rarr; live</h2>'
        f'<div class="kv"><span>status</span><b>{esc(gate.get("status", "-"))}</b></div>'
        f'<div class="bar"><i style="width:{pct}%"></i></div>'
        f'<div class="kv"><span>days</span><b>{days} / {window}</b></div>'
        f'<div class="kv"><span>extensions used</span><b>{gate.get("extensions_used", 0)} / 2</b></div>'
        '<div class="kv"><span>live unlocked</span><b>'
        + ("yes" if gate.get("allows_live") else "not yet")
        + "</b></div></div>"
    )
    # Fund card
    frozen_pill = (
        '<span class="pill bad">FROZEN</span>'
        if frozen
        else '<span class="pill ok">active</span>'
    )
    parts.append(
        '<div class="card"><h2>Global fund</h2>'
        f'<div class="big">{money(fund.get("fund_balance"))}</div>{frozen_pill}'
        '<div class="kv" style="margin-top:8px"><span>ledger entries</span>'
        f"<b>{fund.get('n_entries', 0)}</b></div></div>"
    )
    # Breaker card
    parts.append(f'<div class="card"><h2>Circuit breaker</h2>{breaker_html}</div>')
    # Tax card
    parts.append(
        '<div class="card"><h2>India VDA tax estimate</h2>' + f"<table>{rows}</table></div>"
    )

    # --- live trade tape ---
    parts.append(
        '<div class="card" style="grid-column:1/-1">'
        '<h2>Live trades</h2>'
        '<div style="max-height:260px;overflow:auto">'
        '<table id="tt-table"><thead><tr>'
        "<th>time (UTC)</th><th>side</th><th>qty</th><th>symbol</th>"
        "<th>price</th><th>notional</th><th>strategy</th>"
        "</tr></thead><tbody>"
        '<tr><td colspan="7" class="muted">no trades yet this session</td></tr>'
        "</tbody></table></div></div>"
    )

    # --- strategy sweep card ---
    sweep = """
    <div class="card" style="grid-column:1/-1">
      <h2>Strategy sweep &mdash; backtest every algorithm</h2>
      <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:10px">
        <label>symbol <input id="sw-sym" value="{{SYM}}" size="9"></label>
        <label>timeframe
          <select id="sw-tf">
            <option>1d</option><option>4h</option><option>1h</option>
          </select>
        </label>
        <label>capital <input id="sw-cap" value="10000" size="7"></label>
        <button id="sw-run" onclick="sweepStart()">Run all {{N}} algorithms</button>
        <span id="sw-progress" class="muted"></span>
      </div>
      <div style="max-height:340px;overflow:auto">
        <table id="sw-table"><thead><tr>
          <th>#</th><th>algorithm</th><th>return</th><th>sharpe</th>
          <th>max DD</th><th>trades</th><th>note</th>
        </tr></thead><tbody></tbody></table>
      </div>
      <div id="sw-trades" style="display:none;margin-top:10px">
        <h3 style="margin:4px 0;font-size:13px;color:var(--blue)">
          Trade detail: <span id="sw-tname"></span>
          <button style="float:right" onclick="document.getElementById('sw-trades').style.display='none'">close</button>
        </h3>
        <div style="max-height:260px;overflow:auto">
          <table id="swt-table"><thead><tr>
            <th>entry (UTC)</th><th>exit (UTC)</th><th>side</th><th>qty</th>
            <th>entry px</th><th>exit px</th><th>P&L</th><th>P&L %</th><th>fees</th>
          </tr></thead><tbody></tbody></table>
        </div>
      </div>
    </div>
    <script>
    function fmt(x, pct) {
      if (x === null || x === undefined) return "";
      return pct ? (100 * x).toFixed(1) + "%" : x.toFixed(2);
    }
    async function sweepStart() {
      const sym = document.getElementById("sw-sym").value;
      const tf = document.getElementById("sw-tf").value;
      const cap = document.getElementById("sw-cap").value;
      const btn = document.getElementById("sw-run");
      btn.disabled = true;
      await fetch(`/api/backtest/start?symbol=${sym}&timeframe=${tf}&capital=${cap}`,
                  {method: "POST"});
      poll();
    }
    let polling = null;
    function poll() {
      if (polling) return;
      polling = setInterval(async () => {
        const r = await fetch("/api/backtest/status");
        const s = await r.json();
        document.getElementById("sw-progress").textContent =
          s.running ? `${s.done}/${s.total} (${
            s.elapsed_s ? s.elapsed_s.toFixed(0) : 0}s)` : "";
        if (!s.running && s.done > 0) {
          clearInterval(polling); polling = null;
          document.getElementById("sw-run").disabled = false;
        }
        if (!s.results || !s.results.length) return;
        const tb = document.querySelector("#sw-table tbody");
        tb.innerHTML = s.results.map((row, i) => `
          <tr>
            <td>${i + 1}</td>
            <td><a href="#" onclick="showTrades('${row.name}');return false"
                   style="color:var(--blue)">${row.name}</a></td>
            <td class="${row.ret >= 0 ? "pos" : "neg"}">${fmt(row.ret, true)}</td>
            <td>${fmt(row.sharpe)}</td>
            <td>${fmt(row.mdd, true)}</td>
            <td>${row.n_trades ?? ""}</td>
            <td class="muted">${row.error || ""}</td>
          </tr>`).join("");
      }, 2000);
    }
    poll();

    async function refreshTrades() {
      try {
        const r = await fetch("/health");
        const s = await r.json();
        const trades = s.recent_trades || [];
        const tb = document.querySelector("#tt-table tbody");
        if (!trades.length) return;
        tb.innerHTML = trades.map(t => `
          <tr>
            <td>${t.ts}</td>
            <td class="${t.side === "BUY" ? "pos" : "neg"}">${t.side}</td>
            <td>${t.qty}</td>
            <td>${t.symbol}</td>
            <td>${Number(t.price).toLocaleString()}</td>
            <td>${Number(t.notional).toLocaleString()}</td>
            <td class="muted">${t.strategy}</td>
          </tr>`).join("");
      } catch (e) { /* health endpoint hiccup; retry next tick */ }
    }
    refreshTrades();
    setInterval(refreshTrades, 5000);

    async function showTrades(name) {
      const r = await fetch(`/api/backtest/trades?name=${encodeURIComponent(name)}`);
      const d = await r.json();
      document.getElementById("sw-tname").textContent =
        `${name} (${d.trades.length} trades)`;
      const tb = document.querySelector("#swt-table tbody");
      tb.innerHTML = d.trades.map(tr => `
        <tr>
          <td>${(tr.entry_time || "").slice(0, 16).replace("T", " ")}</td>
          <td>${(tr.exit_time || "").slice(0, 16).replace("T", " ")}</td>
          <td class="${tr.side === "long" ? "pos" : "neg"}">${tr.side}</td>
          <td>${tr.qty}</td>
          <td>${Number(tr.entry_price).toLocaleString()}</td>
          <td>${Number(tr.exit_price).toLocaleString()}</td>
          <td class="${tr.pnl >= 0 ? "pos" : "neg"}">${Number(tr.pnl).toFixed(2)}</td>
          <td>${Number(tr.pnl_pct).toFixed(2)}%</td>
          <td class="muted">${Number(tr.fees).toFixed(2)}</td>
        </tr>`).join("") ||
        '<tr><td colspan="9" class="muted">no closed trades</td></tr>';
      document.getElementById("sw-trades").style.display = "block";
    }
    </script>
    """
    sweep = (sweep
             .replace("{SYM}", esc(snap.get("symbol") or "BTCUSDT"))
             .replace("{N}", str(len(__import__("cryptobot.monitoring.web_backtest",
                                                fromlist=["list_strategy_names"])
                                    .list_strategy_names()))))
    parts.append(sweep)
    parts.append("</div>")
    parts.append(
        '<div class="foot">Read-only view · auto-refreshes every 30s · '
        'details at <a href="/health">/health</a></div>'
    )
    parts.append("</body></html>")
    return "".join(parts)


async def serve_health(host: str | None = None, port: int | None = None) -> None:
    server = HealthServer(host=host, port=port)
    server.start()
    try:
        while True:
            await asyncio.sleep(1)
    finally:
        server.stop()


__all__ = ["HEALTH_PATH", "HealthServer", "METRICS_PATH", "serve_health"]
