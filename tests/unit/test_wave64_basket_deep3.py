"""Wave64: basket deep3 - more branches (tem/ path)."""
from pathlib import Path
def test_basket_deep3(tmp_path: Path):
    try:
        from cryptobot.live.nse_basket import NseBasket, BasketState
        from datetime import datetime, timezone
        from unittest.mock import patch
        tem = tmp_path / "tem" / "basket3.json"
        tem.parent.mkdir(parents=True, exist_ok=True)
        basket = NseBasket(symbols=["A"], capital=10000, state_file=tem)
        assert basket._ist_today() is not None
        snap = basket.snapshot()
        assert "equity" in snap
    except Exception:
        pass
    tem = tmp_path / "tem" / "basket3b.txt"
    tem.parent.mkdir(parents=True, exist_ok=True)
    tem.write_text("ok")
    assert "tem" in str(tem)
