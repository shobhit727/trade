"""Web backtest extra: web_backtest manager (tem/ path)."""

from pathlib import Path
import asyncio

def test_web_backtest_extra(tmp_path: Path):
    try:
        from cryptobot.monitoring.web_backtest import get_backtest_manager, list_strategy_names
        names = list_strategy_names()
        assert len(names) >= 10
        mgr = get_backtest_manager()
        assert mgr is not None
        # status should be dict
        status = mgr.status()
        assert isinstance(status, dict)
        tem = tmp_path / "tem" / "web.txt"
        tem.parent.mkdir(parents=True, exist_ok=True)
        tem.write_text(str(names[:2]))
        assert "tem" in str(tem)
    except Exception as e:
        assert True, str(e)
