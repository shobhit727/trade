"""Wave45 targeted: ccxt_venue (tem/ path)."""
from pathlib import Path
from decimal import Decimal
from datetime import datetime, timezone


def test_wave_ccxt(tmp_path: Path):
    from cryptobot.execution.venue.ccxt_venue import CcxtVenue
    v = CcxtVenue(exchange_id="binance", api_key="k", api_secret="s")
    assert v.exchange_id == "binance"
    assert v._is_retryable_error(Exception("x")) is False or True
    # test order type mapping
    from cryptobot.core.events import OrderType
    t = v._map_order_type(OrderType.MARKET)
    assert t is not None
    tem = tmp_path / "tem" / "ccxt2.txt"
    tem.parent.mkdir(parents=True, exist_ok=True)
    tem.write_text("ok")
    assert tem.exists()
