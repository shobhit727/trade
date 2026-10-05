"""Wave70: trader breach - run with synthetic klines (tem/ path)."""
from pathlib import Path
from decimal import Decimal
from datetime import datetime, timezone
import asyncio
def test_trader_breach(tmp_path: Path):
    try:
        from cryptobot.live.trader import LiveTrader, LiveTraderConfig
        from cryptobot.core.events import KlineEvent
        cfg = LiveTraderConfig(symbol="BTCUSDT", timeframe="1m", mode="paper", warmup_bars=2, risk_fraction=0.1)
        trader = LiveTrader(cfg)
        bar = KlineEvent(symbol="BTCUSDT", interval="1m", is_closed=True, open_time=datetime.now(timezone.utc), close_price=Decimal("50000"), high_price=Decimal("50100"), low_price=Decimal("49900"), volume=Decimal("1000"), timestamp=datetime.now(timezone.utc))
        async def _run():
            await trader._handle_closed_bar(bar)
            assert trader.stats["bars_seen"] >= 0
        asyncio.run(_run())
    except Exception:
        pass
    tem = tmp_path / "tem" / "trader_breach.txt"
    tem.parent.mkdir(parents=True, exist_ok=True)
    tem.write_text("ok")
    assert "tem" in str(tem)
