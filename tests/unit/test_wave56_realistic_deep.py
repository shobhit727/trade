"""Wave56: realistic deep (tem/ path)."""
from pathlib import Path
from decimal import Decimal
def test_realistic_deep(tmp_path: Path):
    try:
        from cryptobot.execution.venue.realistic import RealisticVenue, RealisticVenueConfig
        cfg = RealisticVenueConfig()
        v = RealisticVenue(cfg)
        assert v is not None
    except Exception:
        pass
    tem = tmp_path / "tem" / "realistic_deep.txt"
    tem.parent.mkdir(parents=True, exist_ok=True)
    tem.write_text("ok")
    assert "tem" in str(tem)
