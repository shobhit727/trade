from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Any

logger = logging.getLogger(__name__)


HEALTH_PATH = "/health"
METRICS_PATH = "/metrics"
DASHBOARD_PATH = "/dashboard"


class _HealthSnapshot:
    def __init__(self):
        self.started_at = datetime.now(UTC)

    def snapshot(self) -> dict[str, Any]:
        uptime = (datetime.now(UTC) - self.started_at).total_seconds()
        return {
            "status": "ok",
            "service": "cryptobot",
            "uptime_seconds": round(uptime, 3),
            "now": datetime.now(UTC).isoformat(),
        }


class _Handler(BaseHTTPRequestHandler):
    server_version = "cryptobot/0.1"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        logger.debug("%s - %s", self.address_string(), format % args)

    def do_GET(self):  # noqa: N802
        if self.path == HEALTH_PATH:
            snap = self.server.health_snapshot.snapshot()  # type: ignore[attr-defined]
            body = json.dumps(snap).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == DASHBOARD_PATH:
            snap = self.server.health_snapshot.snapshot()  # type: ignore[attr-defined]
            body = render_dashboard_html(snap).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == METRICS_PATH:
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

    def __init__(self, host: str = "127.0.0.1", port: int = 8080):
        self.host = host
        self.port = port
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

    parts.append("</div>")
    parts.append(
        '<div class="foot">Read-only view · auto-refreshes every 30s · '
        'details at <a href="/health">/health</a></div>'
    )
    parts.append("</body></html>")
    return "".join(parts)


async def serve_health(host: str = "127.0.0.1", port: int = 8080) -> None:
    server = HealthServer(host=host, port=port)
    server.start()
    try:
        while True:
            await asyncio.sleep(1)
    finally:
        server.stop()


__all__ = ["HEALTH_PATH", "HealthServer", "METRICS_PATH", "serve_health"]
