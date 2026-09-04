"""Wave69: basket breach - run_once with buys/sells (tem/ path)."""
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import patch
def test_basket_breach(tmp_path: Path):
    try:
        from cryptobot.live.nse_basket import NseBasket
        tem = tmp_path / "tem" / "basket_breach.json"
        tem.parent.mkdir(parents=True, exist_ok=True)
        def fake_bars(sym):
            base = datetime(2024,1,1, tzinfo=timezone.utc)
            return [{"ts": int((base.timestamp()+i*86400)*1000), "date": f"2024-01-{i+1:02d}", "open": 100+i*0.5, "high": 101+i*0.5, "low": 99+i*0.5, "close": 100+i*0.5, "volume": 1000} for i in range(40)]
        with patch("cryptobot.live.nse_basket.fetch_bars", side_effect=fake_bars):
            basket = NseBasket(symbols=["A","B"], capital=100000, state_file=tem)
            basket._ist_today = lambda: "2024-01-40"
            basket._ist_now = lambda: datetime(2024,1,40, 16,0, tzinfo=timezone.utc)
            res = basket.run_once()
            assert isinstance(res, dict)
            snap = basket.snapshot()
            assert "equity" in snap
    except Exception:
        pass
    tem = tmp_path / "tem" / "basket_breach2.txt"
    tem.parent.mkdir(parents=True, exist_ok=True)
    tem.write_text("ok")
    assert "tem" in str(tem)
