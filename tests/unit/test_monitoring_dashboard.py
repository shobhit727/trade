from __future__ import annotations

import json

from cryptobot.monitoring.dashboard import (
    create_pnl_dashboard,
    create_risk_dashboard,
    create_system_dashboard,
    create_strategy_dashboard,
    create_ml_dashboard,
    create_execution_dashboard,
    create_all_dashboards,
    save_dashboards,
)


def test_dashboard_serializes_to_json():
    """Dashboard builders must produce JSON-serializable structures (B035)."""
    for builder in (
        create_pnl_dashboard,
        create_risk_dashboard,
        create_system_dashboard,
        create_strategy_dashboard,
        create_ml_dashboard,
        create_execution_dashboard,
    ):
        out = builder()
        encoded = json.dumps(out)
        decoded = json.loads(encoded)
        assert decoded["dashboard"]["title"].startswith("Cryptobot")


def test_create_all_dashboards_returns_six():
    all_dashboards = create_all_dashboards()
    assert len(all_dashboards) == 6


def test_save_dashboards(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    written = save_dashboards(output_dir=str(tmp_path / "dashboards"))
    assert len(written) == 6
    for path_str in written:
        from pathlib import Path
        path = Path(path_str)
        assert path.exists()
        json.loads(path.read_text())
