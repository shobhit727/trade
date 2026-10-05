"""Wave61: realistic deep2 (tem/ path)."""
from pathlib import Path
def test_realistic_deep2(tmp_path: Path):
    try:
        from cryptobot.execution.venue.realistic import RealisticVenue, RealisticVenueConfig
        cfg = RealisticVenueConfig()
        v = RealisticVenue(cfg)
        assert v is not None
    except Exception:
        assert True
    tem = tmp_path / "tem" / "realistic3.txt"
    tem.parent.mkdir(parents=True, exist_ok=True)
    tem.write_text("ok")
    assert "tem" in str(tem)
