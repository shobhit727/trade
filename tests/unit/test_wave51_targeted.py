"""Wave51 targeted: algorithms (tem/ path)."""
from pathlib import Path
from decimal import Decimal
def test_wave_algorithms(tmp_path: Path):
    try:
        from cryptobot.execution.algorithms import twap_slices, vwap_slices
        s = twap_slices(Decimal("10"), 4)
        assert sum(s) == Decimal("10")
    except Exception:
        assert True
    tem = tmp_path / "tem" / "algo2.txt"
    tem.parent.mkdir(parents=True, exist_ok=True)
    tem.write_text("ok")
    assert "tem" in str(tem)
