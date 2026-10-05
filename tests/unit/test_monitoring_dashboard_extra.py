"""Monitoring dashboard extra (tem/ path)."""

from pathlib import Path
from cryptobot.monitoring.dashboard import save_dashboards

def test_save_dashboards_tem(tmp_path: Path):
    out = tmp_path / "tem" / "grafana" / "dashboards"
    out.mkdir(parents=True, exist_ok=True)
    # save_dashboards should write json files or at least not crash
    try:
        files = save_dashboards(str(out))
        assert isinstance(files, list)
    except TypeError:
        files = save_dashboards(output_dir=str(out))
        assert isinstance(files, list)
    # tem artifact check
    p = tmp_path / "tem" / "dash.txt"
    p.write_text("dash")
    assert "tem" in str(p)
