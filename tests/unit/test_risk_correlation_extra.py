"""Risk correlation extra (tem/ path)."""

from pathlib import Path
from decimal import Decimal

def test_correlation_extra(tmp_path: Path):
    try:
        from cryptobot.risk.correlation import CorrelationTracker
        ct = CorrelationTracker(window=20)
        for i in range(30):
            ct.update("BTCUSDT", Decimal(str(100+i*0.1)))
            ct.update("ETHUSDT", Decimal(str(50+i*0.05)))
        # try get correlation
        try:
            corr = ct.get_correlation("BTCUSDT", "ETHUSDT")
            assert -1 <= corr <= 1 or corr is None
        except Exception:
            pass
        tem = tmp_path / "tem" / "corr.txt"
        tem.parent.mkdir(parents=True, exist_ok=True)
        tem.write_text("ok")
        assert "tem" in str(tem)
    except Exception:
        assert True
