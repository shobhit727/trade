"""Tests for the monthly PDF report (Seed Phase reporting)."""

from decimal import Decimal

import pytest

fpdf = pytest.importorskip("fpdf")

from cryptobot.monitoring.monthly_report import build_monthly_report  # noqa: E402


def stats_fixture() -> dict:
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
    }


def equity_fixture(n=30):
    from datetime import date, timedelta

    start = date(2026, 7, 1)
    return [
        {"date": (start + timedelta(days=i)).isoformat(),
         "equity": str(Decimal("10000") + Decimal(i * 17))}
        for i in range(n)
    ]


def test_pdf_renders_and_is_pdf(tmp_path):
    out = tmp_path / "reports" / "july.pdf"
    written = build_monthly_report(
        out, "July 2026", stats_fixture(), equity_fixture(),
        {"total_proceeds": "550.00", "taxable_income": "50.00",
         "estimated_tax": "15.60", "tds_credits": "5.50", "net_tax_payable": "10.10"},
    )
    assert written == out and out.exists()
    head = out.read_bytes()[:5]
    assert head == b"%PDF-"
    assert out.stat().st_size > 1000


def test_pdf_without_equity_history_still_renders(tmp_path):
    out = tmp_path / "empty.pdf"
    build_monthly_report(out, "August 2026", stats_fixture(), [], {})
    assert out.exists()


def test_pdf_tripped_breaker_shown(tmp_path):
    stats = stats_fixture()
    stats["breaker"] = {"tripped": True, "reason": "drawdown -26.1%"}
    out = tmp_path / "trip.pdf"
    build_monthly_report(out, "August 2026", stats, equity_fixture(5), {})
    assert out.exists()
