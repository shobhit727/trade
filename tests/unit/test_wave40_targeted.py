"""Wave40 targeted: nse_basket (tem/ path)."""
from pathlib import Path
from decimal import Decimal
from datetime import datetime, timezone


def test_wave_nse_basket(tmp_path: Path):
    from cryptobot.live.nse_basket import BasketState, NseBasket
    from datetime import datetime, timezone
    tem = tmp_path / "tem" / "basket2.json"
    tem.parent.mkdir(parents=True, exist_ok=True)
    s = BasketState(capital=10000)
    s.positions["TEST"] = {"qty": 10, "entry": 100}
    s.trades.append({"symbol": "TEST", "side": "BUY", "qty": 10, "price": 100, "time": datetime.now(timezone.utc).isoformat()})
    d = s.to_dict()
    s2 = BasketState.from_dict(d)
    assert "TEST" in s2.positions
    # test NseBasket snapshot
    nb = NseBasket(symbols=["TEST"], capital=10000, state_file=tem)
    snap = nb.snapshot()
    assert snap["status"] == "running"
    assert "tem" in str(tem)
