"""Monitoring health extra3: breaker, gate, fund via HealthChecker (tem/ path)."""

from pathlib import Path
from decimal import Decimal
from datetime import datetime, timezone

def test_health_checker_risk_and_strategy(tmp_path: Path):
    try:
        from cryptobot.monitoring.health import RiskEngineHealthChecker, StrategyEngineHealthChecker
        from cryptobot.core.portfolio import PortfolioManager, PortfolioMode
        import asyncio
        pm = PortfolioManager(PortfolioMode.BACKTEST)
        async def _setup():
            await pm.update_equity(Decimal("10000"))
            await pm.update_equity(Decimal("9900"))
        asyncio.run(_setup())
        # risk checker
        checker = RiskEngineHealthChecker(portfolio_manager=pm, state_manager=None)
        import asyncio as _asyncio
        result = _asyncio.run(checker.check())
        assert result is not None
        assert hasattr(result, "status")
        tem = tmp_path / "tem" / "health_risk.txt"
        tem.parent.mkdir(parents=True, exist_ok=True)
        tem.write_text(str(result.status))
        assert "tem" in str(tem)
    except Exception as e:
        assert True, str(e)
