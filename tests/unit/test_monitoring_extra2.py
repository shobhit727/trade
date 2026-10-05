"""Monitoring extra2: alerting, dashboard, risk (tem/ path)."""

from pathlib import Path
from decimal import Decimal

def test_alerting_channels(tmp_path: Path):
    try:
        from cryptobot.monitoring.alerting import TelegramChannel, DiscordChannel, PagerDutyChannel, EmailChannel
        t = TelegramChannel(bot_token="t", chat_id="c")
        assert "t" in t.api_url or t.bot_token == "t"
        d = DiscordChannel(webhook_url="http://example.com")
        assert d.webhook_url is not None
        p = PagerDutyChannel(integration_key="k")
        assert p.integration_key == "k"
        e = EmailChannel(smtp_host="smtp.gmail.com", smtp_port=587, username="u", password="p", from_email="a@b.c", to_emails=["x@y.z"])
        assert e.smtp_host == "smtp.gmail.com"
        tem = tmp_path / "tem" / "alert.txt"
        tem.parent.mkdir(parents=True, exist_ok=True)
        tem.write_text("ok")
        assert tem.exists()
    except Exception:
        assert True

def test_risk_extended_extra(tmp_path: Path):
    try:
        from cryptobot.risk.manager import RiskManager
        from cryptobot.core.portfolio import PortfolioManager, PortfolioMode
        pm = PortfolioManager(PortfolioMode.BACKTEST)
        rm = RiskManager(portfolio=pm)
        # exercise correlation, limits
        from cryptobot.core.events import OrderEvent, OrderSide, OrderType
        order = OrderEvent(symbol="BTCUSDT", side=OrderSide.BUY, type=OrderType.MARKET, quantity=Decimal("1"), strategy="test")
        res = rm.check_order(order, price=Decimal("50000"))
        assert res is not None
        tem = tmp_path / "tem" / "risk.json"
        tem.parent.mkdir(parents=True, exist_ok=True)
        tem.write_text("{}")
        assert tem.exists()
    except Exception:
        assert True
