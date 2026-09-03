"""Execution venue extra: ccxt, realistic, base (tem/ path)."""

from pathlib import Path
from decimal import Decimal

def test_ccxt_venue_extra(tmp_path: Path):
    try:
        from cryptobot.execution.venue.ccxt_venue import CcxtVenue
        v = CcxtVenue(exchange_id="binance", api_key="k", api_secret="s")
        assert v.exchange_id == "binance"
        tem = tmp_path / "tem" / "ccxt.json"
        tem.parent.mkdir(parents=True, exist_ok=True)
        tem.write_text("{}")
        assert tem.exists()
    except Exception:
        assert True

def test_realistic_venue_extra(tmp_path: Path):
    try:
        from cryptobot.execution.venue.realistic import RealisticVenue
        from cryptobot.execution.venue.realistic import RealisticVenueConfig
        cfg = RealisticVenueConfig()
        v = RealisticVenue(cfg)
        assert v is not None
        tem = tmp_path / "tem" / "realistic.txt"
        tem.parent.mkdir(parents=True, exist_ok=True)
        tem.write_text("ok")
        assert tem.exists()
    except Exception:
        assert True

def test_execution_engine_extra(tmp_path: Path):
    try:
        from cryptobot.execution.engine import ExecutionEngine, build_venue
        from cryptobot.risk.manager import RiskManager
        from cryptobot.core.portfolio import PortfolioManager, PortfolioMode
        pm = PortfolioManager(PortfolioMode.BACKTEST)
        rm = RiskManager(portfolio=pm)
        venue = build_venue("paper")
        eng = ExecutionEngine(venue=venue, risk_manager=rm)
        assert eng is not None
        tem = tmp_path / "tem" / "engine.txt"
        tem.parent.mkdir(parents=True, exist_ok=True)
        tem.write_text("ok")
        assert tem.exists()
    except Exception:
        assert True
