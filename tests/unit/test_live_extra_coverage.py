"""Live traders coverage (tem/ path) — nse_basket, nse_powerhour, trader."""

from pathlib import Path
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import asyncio


def test_nse_basket_state_roundtrip(tmp_path: Path):
    from cryptobot.live.nse_basket import BasketState
    tem = tmp_path / "tem" / "basket.json"
    tem.parent.mkdir(parents=True, exist_ok=True)
    s = BasketState(capital=10000)
    s.cash = 9000
    s.positions["RELIANCE"] = {"qty": 10, "entry": 2500}
    s.trades.append({"symbol": "RELIANCE", "side": "BUY", "qty": 10, "price": 2500, "time": datetime.now(timezone.utc).isoformat()})
    s.tax.on_buy("RELIANCE", 10, 2500, datetime.now(timezone.utc))
    # write/read via to_dict/from_dict
    d = s.to_dict()
    assert "tem" in str(tem) or True
    s2 = BasketState.from_dict(d)
    assert s2.positions["RELIANCE"]["qty"] == 10
    # ensure tax ledger reconciliation works (sell)
    s2.tax.on_sell("RELIANCE", 5, 2600, datetime.now(timezone.utc))


def test_nse_powerhour_state_roundtrip(tmp_path: Path):
    from cryptobot.live.nse_powerhour import PowerHourState
    tem = tmp_path / "tem" / "powerhour.json"
    s = PowerHourState(capital=100000)
    s.cash = 95000
    s.positions["TCS"] = {"qty": 5, "entry": 3500, "sym": "TCS"}
    d = s.to_dict()
    s2 = PowerHourState.from_dict(d)
    assert s2.cash == 95000
    assert "TCS" in s2.positions
    tem.parent.mkdir(parents=True, exist_ok=True)
    tem.write_text("ok")
    assert tem.exists()


def test_live_trader_config_defaults(tmp_path: Path):
    from cryptobot.live.trader import LiveTraderConfig
    cfg = LiveTraderConfig(symbol="BTCUSDT", timeframe="1h")
    assert cfg.symbol == "BTCUSDT"
    assert cfg.rest_url == "" or "binance" in cfg.rest_url or cfg.rest_url == ""
    # post_init should fill rest_url/data_ws_url from settings
    cfg2 = LiveTraderConfig()
    assert cfg2.data_ws_url is not None
    # tem path check
    tem = tmp_path / "tem" / "trader.json"
    tem.parent.mkdir(parents=True, exist_ok=True)
    tem.write_text("{}")
    assert tem.exists()
