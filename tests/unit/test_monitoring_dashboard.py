from __future__ import annotations

import json

from cryptobot.monitoring.dashboard import (
    create_all_dashboards,
    create_execution_dashboard,
    create_ml_dashboard,
    create_pnl_dashboard,
    create_risk_dashboard,
    create_strategy_dashboard,
    create_system_dashboard,
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


def test_risk_dashboard_exposure_ratio_uses_unlabeled_equity():
    """Issue #50: exposure % must divide by the unlabeled total_equity gauge."""

    def _collect_exprs(panels):
        exprs = []
        for p in panels:
            for t in p.get("targets", []):
                exprs.append(t.get("expr", ""))
            exprs.extend(_collect_exprs(p.get("panels", [])))
        return exprs

    dash = create_risk_dashboard()
    exprs = _collect_exprs(dash["dashboard"]["panels"])
    assert any(
        "cryptobot_position_size_usd / on() group_left() cryptobot_total_equity_usd * 100" in e
        for e in exprs
    )
