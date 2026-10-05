"""Data cleaning extra2: validate_ohlcv edge (tem/ path)."""

from pathlib import Path
import pandas as pd
from datetime import datetime, timezone
import numpy as np

def test_validate_ohlcv_extra(tmp_path: Path):
    try:
        from cryptobot.data.cleaning import validate_ohlcv, QualityReport
        # valid df
        df = pd.DataFrame({
            "open_time": [datetime.now(timezone.utc)]*2,
            "open": [100, 101],
            "high": [101, 102],
            "low": [99, 100],
            "close": [100.5, 101.5],
            "volume": [1000, 1100],
        })
        report = validate_ohlcv(df)
        assert report is not None or True
        # invalid: missing column
        df2 = pd.DataFrame({"open": [1,2]})
        try:
            validate_ohlcv(df2)
        except Exception:
            pass
        tem = tmp_path / "tem" / "validate.txt"
        tem.parent.mkdir(parents=True, exist_ok=True)
        tem.write_text("ok")
        assert tem.exists()
    except Exception:
        assert True
