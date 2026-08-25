"""Kite venue tests — checksum math, payload shape, dry-run, rejection path.

All HTTP is mocked; nothing touches the network.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal

import pytest

from cryptobot.core.events import OrderEvent, OrderSide, OrderStatus, OrderType
from cryptobot.execution.venue.kite_venue import KiteSession, KiteVenue


def _order(side=OrderSide.BUY, otype=OrderType.MARKET, qty="10", price=None):
    return OrderEvent(symbol="RELIANCE", side=side, type=otype,
                      quantity=Decimal(qty), price=price)


def _session(tmp_path):
    return KiteSession(api_key="key123", api_secret="shhh",
                       session_file=tmp_path / "kite.json")


# ------------------------------------------------------------------ session

def test_login_url_contains_api_key(tmp_path):
    url = _session(tmp_path).login_url()
    assert "kite.zerodha.com/connect/login" in url and "key123" in url


def test_exchange_token_checksum_and_persistence(tmp_path, monkeypatch):
    captured = {}

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({
                "status": "success",
                "data": {"access_token": "tok456", "user_id": "AB1234"},
            }).encode()

    def fake_urlopen(req, timeout=20):
        captured["url"] = req.full_url
        captured["data"] = req.data.decode()
        return FakeResp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    s = _session(tmp_path)
    token = s.exchange_token("req789")

    assert token == "tok456"
    expected = hashlib.sha256(b"key123req789shhh").hexdigest()
    assert f"checksum={expected}" in captured["data"]
    assert s.session_file.exists()          # persisted for KiteVenue pickup
    assert s.access_token == "tok456"


# ------------------------------------------------------------------- venue

@pytest.mark.asyncio
async def test_dry_run_never_touches_network_and_fills(tmp_path):
    v = KiteVenue(_session(tmp_path), dry_run=True)
    v.prices["RELIANCE"] = Decimal("1300")
    o = await v.submit_order(_order())
    assert o.status == OrderStatus.FILLED
    assert o.payload.get("dry_run") is True
    assert o.avg_fill_price == Decimal("1300")


@pytest.mark.asyncio
async def test_live_place_sends_kite_payload(monkeypatch, tmp_path):
    v = KiteVenue(_session(tmp_path), dry_run=False, poll_seconds=0.01,
                  poll_timeout=1.0)
    calls = []

    def fake_request(path, params=None, method="GET"):
        calls.append((path, params, method))
        if path == "/orders/regular" and method == "POST":
            return {"order_id": "241501"}
        if path.startswith("/orders/regular/"):
            return [{"status": "COMPLETE", "filled_quantity": 10,
                     "average_price": 1301.5}]
        raise AssertionError(f"unexpected {path}")

    monkeypatch.setattr(v, "_request", fake_request)
    o = await v.submit_order(_order(qty="10"))

    assert o.status == OrderStatus.FILLED
    assert o.payload["kite_order_id"] == "241501"
    assert o.avg_fill_price == Decimal("1301.5")
    path, params, method = calls[0]
    assert path == "/orders/regular" and method == "POST"
    assert params["exchange"] == "NSE"
    assert params["transaction_type"] == "BUY"
    assert params["product"] == "CNC"
    assert params["quantity"] == "10"


@pytest.mark.asyncio
async def test_live_rejection_captured(monkeypatch, tmp_path):
    v = KiteVenue(_session(tmp_path), dry_run=False, poll_seconds=0.01,
                  poll_timeout=0.5)

    def fake_request(path, params=None, method="GET"):
        if method == "POST":
            return {"order_id": "1"}
        return [{"status": "REJECTED", "filled_quantity": 0,
                 "status_message": "INSUFFICIENT FUNDS"}]

    monkeypatch.setattr(v, "_request", fake_request)
    o = await v.submit_order(_order())
    assert o.status == OrderStatus.REJECTED
    assert "INSUFFICIENT" in (o.payload.get("error") or "")


@pytest.mark.asyncio
async def test_limit_price_rounded_to_paise(monkeypatch, tmp_path):
    v = KiteVenue(_session(tmp_path), dry_run=False, poll_seconds=0.01,
                  poll_timeout=0.5)
    seen = {}

    def fake_request(path, params=None, method="GET"):
        if method == "POST":
            seen.update(params or {})
            return {"order_id": "2"}
        return [{"status": "COMPLETE", "filled_quantity": 1,
                 "average_price": 100.05}]

    monkeypatch.setattr(v, "_request", fake_request)
    await v.submit_order(_order(otype=OrderType.LIMIT, price="100.053"))
    assert seen["price"] == "100.05"          # NSE tick grid


def test_missing_token_raises_clear_error(tmp_path):
    v = KiteVenue(_session(tmp_path), dry_run=False)
    with pytest.raises(RuntimeError, match="kite_login"):
        v._request("/profile")
