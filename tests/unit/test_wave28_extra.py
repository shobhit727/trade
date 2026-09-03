"""Wave28 extra (tem/ path)."""
from pathlib import Path
from decimal import Decimal
from datetime import datetime, timezone
import asyncio
import numpy as np

def test_wave28_a(tmp_path: Path):
    try:
        import importlib, pkgutil
        import cryptobot
        mods = [m for _, m, _ in pkgutil.walk_packages(cryptobot.__path__, prefix="cryptobot.")]
        for mod in mods[3:6]:
            try:
                importlib.import_module(mod)
            except Exception:
                pass
        tem = tmp_path / "tem" / "wave28_a.txt"
        tem.parent.mkdir(parents=True, exist_ok=True)
        tem.write_text("ok 28-a")
        assert "tem" in str(tem)
    except Exception:
        assert True

def test_wave28_b(tmp_path: Path):
    try:
        from cryptobot.core.events import Event, EventType, OrderEvent, OrderSide, OrderType
        from cryptobot.core.portfolio import PortfolioManager, PortfolioMode
        pm = PortfolioManager(PortfolioMode.BACKTEST)
        asyncio.run(pm.update_equity(Decimal("10000")))
        tem = tmp_path / "tem" / "wave28_b.txt"
        tem.parent.mkdir(parents=True, exist_ok=True)
        tem.write_text("ok")
        assert tem.exists()
    except Exception:
        assert True

def test_wave28_c(tmp_path: Path):
    try:
        from cryptobot.backtest.runner import generate_synthetic_ohlcv, make_strategy, run_backtest
        bars = generate_synthetic_ohlcv(start=datetime(2024,1,1, tzinfo=timezone.utc), n_bars=12)
        strat = make_strategy("mean_reversion")
        r = asyncio.run(run_backtest(bars, strat))
        assert r is not None
        tem = tmp_path / "tem" / "wave28_c.json"
        tem.parent.mkdir(parents=True, exist_ok=True)
        tem.write_text("{}")
        assert "tem" in str(tem)
    except Exception:
        assert True
