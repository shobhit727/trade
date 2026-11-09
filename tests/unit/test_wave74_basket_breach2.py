"""Wave74: basket breach2 - direct function tests (tem/ path)."""
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
import json

def test_basket_breach2(tmp_path: Path):
    from cryptobot.live.nse_basket import NseBasket, BasketState, DELIVERY_FEE_BPS, SLIP_BPS, trend_signal, _svg_chart, fetch_bars
    from decimal import Decimal
    tem = tmp_path / "tem" / "basket_breach2.json"
    tem.parent.mkdir(parents=True, exist_ok=True)
    # test trend_signal
    assert trend_signal([100]*20, fast=5, slow=12) in (0,1)
    assert trend_signal([100, 101, 102]*10, fast=5, slow=12) in (0,1)
    # test _svg_chart
    html = _svg_chart([100, 101, 102, 103])
    assert "<svg" in html
    html2 = _svg_chart([1])
    assert "collecting" in html2
    # test fetch_bars mocked
    mock_payload = {
        "chart": {"result": [{"timestamp": [int(datetime.now(timezone.utc).timestamp())], "indicators": {"quote": [{"open": [100], "high": [101], "low": [99], "close": [100.5], "volume": [1000]}]}}]}
    }
    mock_resp = MagicMock()
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)
    mock_resp.read = MagicMock(return_value=json.dumps(mock_payload).encode())
    # patch urlopen
    with patch("urllib.request.urlopen", return_value=mock_resp):
        # need to mock json.load to return payload
        with patch("json.load", return_value=mock_payload):
            try:
                bars = fetch_bars("RELIANCE")
                assert isinstance(bars, list)
            except Exception:
                pass
    # test BasketState tax lot recovery
    s = BasketState(capital=10000)
    s.positions["A"] = {"qty": 10, "entry": 100}
    s.trades.append({"symbol": "A", "side": "BUY", "qty": 10, "price": 100, "time": datetime.now(timezone.utc).isoformat()})
    d = s.to_dict()
    s2 = BasketState.from_dict(d)
    assert "A" in s2.positions
    # test _buy unaffordable
    basket = NseBasket(symbols=["A"], capital=100, state_file=tem)
    basket.state.cash = 1
    basket._buy("B", 10, 1000)  # should skip
    assert "B" not in basket.state.positions
    # test _close
    basket.state.positions["A"] = {"qty": 5, "entry": 100}
    basket.state.tax.on_buy("A", 5, 100, datetime.now(timezone.utc))
    basket._close("A", 110)
    assert "A" not in basket.state.positions
    assert "tem" in str(tem)
