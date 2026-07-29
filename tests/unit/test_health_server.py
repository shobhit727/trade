from __future__ import annotations

import asyncio
import json
import urllib.request

import pytest

from cryptobot.utils.health_server import (
    HEALTH_PATH,
    METRICS_PATH,
    HealthServer,
    serve_health,
)


def _start_server() -> HealthServer:
    server = HealthServer(host="127.0.0.1", port=0)
    server.start()
    return server


@pytest.mark.asyncio
async def test_serve_health_returns_static_snapshot():
    server = HealthServer(host="127.0.0.1", port=0)
    server.start()
    port = server._httpd.server_address[1]  # type: ignore[attr-defined]
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{HEALTH_PATH}", timeout=2) as r:
            assert r.status == 200
            body = json.loads(r.read())
        assert body["status"] == "ok"
        assert body["service"] == "cryptobot"
        assert "uptime_seconds" in body
    finally:
        server.stop()


@pytest.mark.asyncio
async def test_metrics_endpoint_emits_text():
    server = _start_server()
    port = server._httpd.server_address[1]  # type: ignore[attr-defined]
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{METRICS_PATH}", timeout=2) as r:
            assert r.status == 200
            assert "text/plain" in r.headers.get("Content-Type", "")
    finally:
        server.stop()


@pytest.mark.asyncio
async def test_unknown_path_returns_404():
    server = _start_server()
    port = server._httpd.server_address[1]  # type: ignore[attr-defined]
    try:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/nope", timeout=2)
            assert False, "expected HTTPError for unknown path"
        except urllib.error.HTTPError as e:
            assert e.code == 404
    finally:
        server.stop()


@pytest.mark.asyncio
async def test_serve_health_helper_starts_server():
    task = asyncio.create_task(serve_health(host="127.0.0.1", port=0))
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
