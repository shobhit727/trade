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
        httpd = ThreadingHTTPServer((self.host, self.port), _Handler)
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


def render_dashboard_html(snap: dict) -> str:
    """Read-only family dashboard: same data as /health, human-shaped."""
    import html as _html

    def esc(value):
        return _html.escape(str(value))

    gate = snap.get("paper_gate") or {}
    fund = snap.get("global_fund") or {}
    breaker = snap.get("breaker") or {}
    tax = snap.get("tax_summary") or {}
    breaker_bad = bool(breaker.get("tripped"))
    rows = [
        ("Status", snap.get("status"), "ok" if snap.get("status") == "running" else "warn"),
        ("Strategy", f"{snap.get('strategy')} {snap.get('symbol')} {snap.get('timeframe')}", ""),
        ("Mode", snap.get("mode"), ""),
        ("Equity", snap.get("equity"), "ok"),
        ("Orders / fills / rejects",
         f"{snap.get('orders_submitted', 0)} / {snap.get('fills', 0)} / {snap.get('rejects', 0)}", ""),
        ("Global fund", f"{fund.get('fund_balance', '0')}"
         + (" (FROZEN)" if fund.get("frozen") else ""), ""),
        ("Paper gate", f"{gate.get('status', '-')} "
         f"({gate.get('days_elapsed', 0)}/{gate.get('window_days', 60)} days)", ""),
        ("Circuit breaker", ("TRIPPED: " + breaker.get("reason", "")) if breaker_bad else "ok",
         "bad" if breaker_bad else "ok"),
        ("Risk profile", snap.get("risk_profile", "-"), ""),
        ("Tax estimate (net payable)", tax.get("net_tax_payable", "-"), ""),
    ]
    trs = "".join(
        f"<tr><td>{esc(label)}</td>"
        f"<td class='{cls}'>{esc(value)}</td></tr>"
        for label, value, cls in rows
    )
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>cryptobot - live status</title><style>"
        "body{font-family:system-ui;margin:2rem;background:#111;color:#eee}"
        "h1{font-size:1.3rem}"
        "table{border-collapse:collapse;min-width:32rem}"
        "td{padding:.5rem .9rem;border-bottom:1px solid #333}"
        "td:first-child{color:#9ab;font-weight:600}"
        ".ok{color:#7dd07d}.warn{color:#e6c34a}.bad{color:#ff6b6b;font-weight:700}"
        "</style></head><body>"
        "<h1>Cryptobot - read-only status</h1>"
        f"<table>{trs}</table>"
        "<p style='color:#666'>Read-only view. Updates on refresh.</p>"
        "</body></html>"
    )


async def serve_health(host: str = "127.0.0.1", port: int = 8080) -> None:
    server = HealthServer(host=host, port=port)
    server.start()
    try:
        while True:
            await asyncio.sleep(1)
    finally:
        server.stop()


__all__ = ["HEALTH_PATH", "HealthServer", "METRICS_PATH", "serve_health"]
