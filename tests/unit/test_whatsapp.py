"""Tests for the WhatsApp Cloud API sender (Seed Phase reporting)."""

import pytest

from cryptobot.monitoring.whatsapp import (
    WhatsAppConfig,
    format_daily_summary,
    send_whatsapp,
)


def stats_fixture() -> dict:
    return {
        "mode": "paper",
        "equity": "10500.00",
        "orders_submitted": 8,
        "fills": 7,
        "rejects": 1,
        "global_fund": {"fund_balance": "35.20", "frozen": False},
        "paper_gate": {"status": "collecting", "days_elapsed": 12, "window_days": 60},
        "breaker": {"tripped": False, "reason": ""},
    }


def test_format_daily_summary_lines():
    text = format_daily_summary(stats_fixture())
    assert "equity 10500.00" in text
    assert "Orders 8 | fills 7 | rejects 1" in text
    assert "Fund 35.20" in text
    assert "Gate: collecting 12/60d" in text
    assert "ALERT" not in text


def test_format_flags_tripped_breaker():
    stats = stats_fixture()
    stats["breaker"] = {"tripped": True, "reason": "drawdown -26%"}
    assert "ALERT: breaker tripped - drawdown -26%" in format_daily_summary(stats)


def test_unconfigured_skips():
    assert WhatsAppConfig().configured() is False


class _Resp:
    def __init__(self, status: int):
        self.status = status

    async def text(self):
        return "{}" if self.status == 200 else "err"

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeSession:
    """Stands in for aiohttp.ClientSession; records posts."""

    status_code = 200
    posts: list[tuple] = []

    @classmethod
    def reset(cls, status_code=200):
        cls.status_code = status_code
        cls.posts = []

    def post(self, url, json=None, headers=None, timeout=None):
        type(self).posts.append((url, json, headers))
        return _Resp(type(self).status_code)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


@pytest.fixture
def fake_http(monkeypatch):
    import aiohttp

    _FakeSession.reset()
    monkeypatch.setattr(aiohttp, "ClientSession", _FakeSession)
    return _FakeSession


@pytest.mark.asyncio
async def test_send_posts_to_graph_api(fake_http):
    cfg = WhatsAppConfig(token="tok", phone_id="PID", to=["919999999999"])
    ok = await send_whatsapp("hello", cfg)
    assert ok is True
    url, payload, headers = fake_http.posts[0]
    assert "PID/messages" in url
    assert payload["to"] == "919999999999"
    assert payload["text"]["body"] == "hello"
    assert headers["Authorization"] == "Bearer tok"


@pytest.mark.asyncio
async def test_send_failure_returns_false(fake_http):
    fake_http.reset(status_code=500)
    cfg = WhatsAppConfig(token="tok", phone_id="PID", to=["x"])
    assert await send_whatsapp("hello", cfg) is False


@pytest.mark.asyncio
async def test_send_all_recipients(monkeypatch):
    import aiohttp

    _FakeSession.reset()
    monkeypatch.setattr(aiohttp, "ClientSession", _FakeSession)
    cfg = WhatsAppConfig(token="t", phone_id="P", to=["a", "b"])
    ok = await send_whatsapp("hi family", cfg)
    assert ok is True
    assert len(_FakeSession.posts) == 2
