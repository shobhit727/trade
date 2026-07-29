from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Any, Callable, Dict, Optional


logger = logging.getLogger(__name__)


HEALTH_PATH = "/health"
METRICS_PATH = "/metrics"


class _HealthSnapshot:
    def __init__(self):
        self.started_at = datetime.now(timezone.utc)

    def snapshot(self) -> Dict[str, Any]:
        uptime = (datetime.now(timezone.utc) - self.started_at).total_seconds()
        return {
            "status": "ok",
            "service": "cryptobot",
            "uptime_seconds": round(uptime, 3),
            "now": datetime.now(timezone.utc).isoformat(),
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
        self._httpd: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[Thread] = None

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


async def serve_health(host: str = "127.0.0.1", port: int = 8080) -> None:
    server = HealthServer(host=host, port=port)
    server.start()
    try:
        while True:
            await asyncio.sleep(1)
    finally:
        server.stop()


__all__ = ["HEALTH_PATH", "HealthServer", "METRICS_PATH", "serve_health"]
