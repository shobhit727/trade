"""Wave74: basket deep3 - more branches (tem/ path)."""
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import patch
from decimal import Decimal

def test_basket_deep3(tmp_path: Path):
    from cryptobot.live.nse_basket import NseBasket, BasketState
    tem = tmp_path / "tem" / "basket3.json"
    tem.parent.mkdir(parents=True, exist_ok=True)
    basket = NseBasket(symbols=["A"], capital=10000, state_file=tem)
    # test seconds_until_next_close
    secs = basket.seconds_until_next_close()
    assert secs > 0
    # test snapshot with positions and closes
    basket._closes["A"] = [100, 101, 102]
    basket.state.positions["A"] = {"qty": 10, "entry": 100}
    # add tax lot for A
    basket.state.tax.on_buy("A", 10, 100, datetime.now(timezone.utc))
    snap = basket.snapshot()
    assert snap["open_positions"] == 1
    assert "equity_curve" in snap
    # test _buy with affordable and unaffordable
    basket.state.cash = 10000
    basket._buy("B", 10, 100)
    assert "B" in basket.state.positions
    basket.state.cash = 1
    basket._buy("C", 10, 1000)  # should skip unaffordable
    assert "C" not in basket.state.positions
    # test _close
    basket._close("A", 110)
    assert "A" not in basket.state.positions
    # test breaker
    basket.state.peak_equity = 20000
    basket.state.cash = 10000
    basket.state.positions["D"] = {"qty": 10, "entry": 100}
    basket.state.tax.on_buy("D", 10, 100, datetime.now(timezone.utc))
    with patch("cryptobot.live.nse_basket.fetch_bars", side_effect=lambda sym: [{"ts": int(datetime(2024,1,1, tzinfo=timezone.utc).timestamp()*1000)+i*86400000, "date": f"2024-01-{i+1:02d}", "open": 100, "high": 101, "low": 99, "close": 50, "volume": 1000} for i in range(40)]):
        basket.state.peak_equity = 20000
        basket.state.cash = 5000
        res = basket.run_once()
        assert isinstance(res, dict)
    assert "tem" in str(tem)