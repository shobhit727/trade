"""Wave54: nse_basket deep run_once (tem/ path)."""
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import patch

def test_nse_basket_deep(tmp_path: Path):
    from cryptobot.live.nse_basket import NseBasket
    tem = tmp_path / "tem" / "basket_deep.json"
    tem.parent.mkdir(parents=True, exist_ok=True)
    # mock fetch_bars to return synthetic
    def fake_bars(sym):
        base = datetime(2024,1,1, tzinfo=timezone.utc)
        return [{"ts": int((base.timestamp()+i*86400)*1000), "date": f"2024-01-{i+1:02d}", "open": 100, "high": 101, "low": 99, "close": 100+i*0.2, "volume": 1000} for i in range(40)]
    with patch("cryptobot.live.nse_basket.fetch_bars", side_effect=fake_bars):
        basket = NseBasket(symbols=["TEST"], capital=10000, state_file=tem)
        # ensure _closes populated
        basket._closes["TEST"] = [100+i*0.1 for i in range(40)]
        res = basket.run_once()
        assert isinstance(res, dict)
        snap = basket.snapshot()
        assert "equity" in snap
        assert "tem" in str(tem)
