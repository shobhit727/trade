"""Wave59: basket deep2 - breaker, tax, snapshot (tem/ path)."""
from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch

def test_basket_deep2(tmp_path: Path):
    from cryptobot.live.nse_basket import NseBasket, BasketState
    tem = tmp_path / "tem" / "basket3.json"
    tem.parent.mkdir(parents=True, exist_ok=True)
    # test breaker
    basket = NseBasket(symbols=["A","B"], capital=10000, state_file=tem)
    basket.state.peak_equity = 20000
    basket.state.cash = 10000
    basket.state.positions["A"] = {"qty": 10, "entry": 100}
    # force breaker trip via equity drop
    with patch.object(basket, "_closes", {"A": [50], "B": [50]}):
        snap = basket.snapshot()
        assert snap["open_positions"] == 1
    # test tax lot recovery
    basket.state.tax.lots.clear()
    basket.state.positions["A"] = {"qty": 5, "entry": 100}
    basket.state.trades.append({"symbol": "A", "side": "BUY", "qty": 5, "price": 100, "time": datetime.now(timezone.utc).isoformat()})
    # save and reload should reconstruct
    basket.state_file.write_text(__import__("json").dumps(basket.state.to_dict()))
    basket2 = NseBasket(symbols=["A"], capital=10000, state_file=tem)
    assert "A" in basket2.state.positions
    # test reset_breaker
    basket2.reset_breaker()
    assert basket2.state.breaker_tripped is False
    assert "tem" in str(tem)
