"""Tests for the read-only family dashboard endpoint."""

from cryptobot.utils.health_server import render_dashboard_html


def snap_fixture() -> dict:
    return {
        "status": "running",
        "strategy": "dual_ma",
        "symbol": "BTCUSDT",
        "timeframe": "1d",
        "mode": "paper",
        "equity": "10500.00",
        "orders_submitted": 8,
        "fills": 7,
        "rejects": 1,
        "risk_profile": "realistic",
        "global_fund": {"fund_balance": "35.20", "frozen": False},
        "paper_gate": {"status": "collecting", "days_elapsed": 12, "window_days": 60},
        "breaker": {"tripped": False, "reason": ""},
        "tax_summary": {"net_tax_payable": "150.50"},
    }


def test_dashboard_renders_key_rows():
    html = render_dashboard_html(snap_fixture())
    assert "Equity" in html and "10,500.00" in html
    assert "collecting" in html and "12 / 60" in html
    assert "pill ok" in html  # status pill armed/green
    assert "read-only" in html.lower()


def test_dashboard_tripped_breaker_is_bad():
    snap = snap_fixture()
    snap["breaker"] = {"tripped": True, "reason": "drawdown -26%"}
    html = render_dashboard_html(snap)
    assert ">TRIPPED</span>" in html and "drawdown -26%" in html
    assert "pill bad" in html


def test_dashboard_escapes_html():
    snap = snap_fixture()
    snap["strategy"] = "<script>x</script>"
    html = render_dashboard_html(snap)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
