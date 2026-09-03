"""Wave64: basket deep3 - more branches (tem/ path)."""
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import patch

def test_basket_deep3(tmp_path: Path):
    from cryptobot.live.nse_basket import NseBasket, BasketState
    tem = tmp_path / "tem" / "basket4.json"
    tem.parent.mkdir(parents=True, exist_ok=True)
    basket = NseBasket(symbols=["A"], capital=10000, state_file=tem)
    # test _ist_today, _ist_now
    assert basket._ist_today() is not None
    assert basket._ist_now() is not None
    # test seconds_until_next_close
    secs = basket.seconds_until_next_close()
    assert secs > 0
    # test dashboard html
    html = basket._dashboard_html()
    assert "NSE" in html or "Equity" in html
    # test snapshot with empty closes
    snap = basket.snapshot()
    assert "equity" in snap
    assert "tem" in str(tem)
