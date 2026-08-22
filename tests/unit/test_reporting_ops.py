"""Tests for the audit log and email digest (Seed Phase reporting/ops)."""

from decimal import Decimal

from cryptobot.monitoring.email_digest import EmailConfig, format_digest, send_digest
from cryptobot.utils.audit import ActionAudit

# ------------------------------------------------------------------- audit


def test_audit_log_append_and_tail(tmp_path):
    audit = ActionAudit(state_path=str(tmp_path / "audit.jsonl"))
    audit.log("owner", "breaker-reset", {"reason": "reviewed drawdown"})
    audit.log("owner", "config-change", {"key": "risk_profile", "value": "aggressive"})
    entries = audit.tail(10)
    assert len(entries) == 2
    assert entries[0]["action"] == "breaker-reset"
    assert entries[1]["details"]["value"] == "aggressive"
    assert all("ts" in e and e["actor"] == "owner" for e in entries)


def test_audit_tail_empty_when_missing(tmp_path):
    assert ActionAudit(state_path=str(tmp_path / "none.jsonl")).tail() == []


def test_audit_log_is_jsonl_parseable(tmp_path):
    import json

    path = tmp_path / "audit.jsonl"
    audit = ActionAudit(state_path=str(path))
    for i in range(5):
        audit.log("system", f"event-{i}")
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert [json.loads(line)["action"] for line in lines] == [f"event-{i}" for i in range(5)]


# ------------------------------------------------------------- email digest


def stats_fixture() -> dict:
    return {
        "status": "running",
        "strategy": "dual_ma",
        "symbol": "BTCUSDT",
        "timeframe": "1d",
        "mode": "paper",
        "equity": "10500.00",
        "bars_fed": 120,
        "bars_seen": 125,
        "orders_submitted": 8,
        "fills": 7,
        "rejects": 1,
        "global_fund": {"fund_balance": "35.20", "frozen": False},
        "paper_gate": {"status": "collecting", "days_elapsed": 12, "window_days": 60},
        "breaker": {"tripped": False, "reason": ""},
        "tax_summary": {"estimated_tax": "156.00", "net_tax_payable": "150.50"},
    }


def test_format_digest_contains_key_lines():
    body = format_digest(stats_fixture())
    assert "Equity      : 10500.00" in body
    assert "Global fund : 35.20 (frozen=False)" in body
    assert "Paper gate  : collecting (12/60 days)" in body
    assert "Breaker     : ok" in body
    assert "Tax est." in body


def test_format_digest_tripped_breaker():
    stats = stats_fixture()
    stats["breaker"] = {"tripped": True, "reason": "drawdown -26%"}
    assert "TRIPPED - drawdown -26%" in format_digest(stats)


def test_send_skips_when_unconfigured(monkeypatch):
    monkeypatch.delenv("EMAIL_SMTP_USER", raising=False)
    monkeypatch.delenv("EMAIL_SMTP_PASS", raising=False)
    monkeypatch.delenv("EMAIL_TO", raising=False)
    assert send_digest(stats_fixture()) is False


def test_send_success_path(monkeypatch):
    cfg = EmailConfig(user="me@gmail.com", password="app-pass",
                      to=["family@gmail.com"])
    sent = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            sent["host"], sent["port"] = host, port

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def login(self, user, password):
            sent["user"] = user

        def send_message(self, msg):
            sent["msg"] = msg

    monkeypatch.setattr("cryptobot.monitoring.email_digest.smtplib.SMTP_SSL", FakeSMTP)
    ok = send_digest(stats_fixture(), cfg)
    assert ok is True
    assert sent["user"] == "me@gmail.com"
    assert sent["msg"]["To"] == "family@gmail.com"
    assert "10500.00" in sent["msg"].get_content()


def test_send_failure_returns_false(monkeypatch):
    cfg = EmailConfig(user="u", password="p", to=["x@y.z"])

    def boom(*a, **kw):
        raise OSError("network down")

    monkeypatch.setattr("cryptobot.monitoring.email_digest.smtplib.SMTP_SSL", boom)
    assert send_digest(stats_fixture(), cfg) is False


def test_decimal_equity_renders():
    stats = stats_fixture()
    stats["equity"] = str(Decimal("9999.99"))
    assert "9999.99" in format_digest(stats)
