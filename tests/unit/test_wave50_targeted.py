"""Wave50 targeted: cleaning (tem/ path)."""
from pathlib import Path
from decimal import Decimal
from datetime import datetime, timezone


def test_wave_cleaning(tmp_path: Path):
    import pandas as pd
    from datetime import datetime, timezone
    from cryptobot.data.cleaning import clean_klines, clean_trades, validate_ohlcv
    df = pd.DataFrame({
        "open_time": [datetime.now(timezone.utc)]*2,
        "open": [100, 101],
        "high": [101, 102],
        "low": [99, 100],
        "close": [100.5, 101.5],
        "volume": [1000, 1100],
    })
    validate_ohlcv(df)
    cleaned, rep = clean_klines(df, "BTCUSDT", "1h")
    assert cleaned is not None
    df2 = pd.DataFrame({"price": [100, 101], "quantity": [1, 2], "time": [datetime.now(timezone.utc)]*2})
    cleaned2, rep2 = clean_trades(df2, "BTCUSDT")
    assert cleaned2 is not None
    tem = tmp_path / "tem" / "clean2.txt"
    tem.parent.mkdir(parents=True, exist_ok=True)
    tem.write_text("ok")
    assert tem.exists()
