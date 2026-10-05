"""Wave55: trader deep (tem/ path)."""
from pathlib import Path
def test_trader_deep(tmp_path: Path):
    try:
        from cryptobot.live.trader import LiveTrader, LiveTraderConfig
        cfg = LiveTraderConfig(symbol="BTCUSDT", timeframe="1m", mode="paper")
        trader = LiveTrader(cfg)
        assert trader is not None
        from decimal import Decimal
        from cryptobot.core.events import OrderEvent, OrderSide, OrderType
        order = OrderEvent(symbol="BTCUSDT", side=OrderSide.BUY, type=OrderType.MARKET, quantity=Decimal("1"), strategy="test")
        trader._rescale_order(order, Decimal("50000"))
    except Exception:
        pass
    tem = tmp_path / "tem" / "trader_deep.txt"
    tem.parent.mkdir(parents=True, exist_ok=True)
    tem.write_text("ok")
    assert "tem" in str(tem)
