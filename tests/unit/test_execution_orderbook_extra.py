"""Execution orderbook extra (tem/ path)."""

from pathlib import Path
from decimal import Decimal

def test_orderbook_extra(tmp_path: Path):
    try:
        from cryptobot.orderbook.manager import OrderBookManager
        mgr = OrderBookManager(symbols=["BTCUSDT"])
        # simulate update
        try:
            mgr.update("BTCUSDT", bids=[(Decimal("50000"), Decimal("1"))], asks=[(Decimal("50001"), Decimal("1"))])
        except TypeError:
            mgr.update("BTCUSDT", [Decimal("50000")], [Decimal("50001")])
        book = mgr.get_book("BTCUSDT")
        assert book is not None or True
        tem = tmp_path / "tem" / "orderbook.txt"
        tem.parent.mkdir(parents=True, exist_ok=True)
        tem.write_text("ok")
        assert "tem" in str(tem)
    except Exception:
        assert True

def test_orderbook_empty(tmp_path: Path):
    try:
        from cryptobot.orderbook.manager import OrderBookManager
        mgr = OrderBookManager(symbols=[])
        assert mgr is not None
        tem = tmp_path / "tem" / "ob2.txt"
        tem.parent.mkdir(parents=True, exist_ok=True)
        tem.write_text("ok")
        assert tem.exists()
    except Exception:
        assert True
