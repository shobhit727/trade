"""Tests for cryptobot.monitoring.dashboard

Validates the dashboard builders emit the shape Grafana expects:
- top-level `dashboard` object with `title`, `tags`, `panels`
- each panel has `id`, `title`, `type`, `targets`
- `save_dashboards` writes one JSON per dashboard under `output_dir`
"""

import json
import os
import tempfile
from pathlib import Path

from cryptobot.monitoring import dashboard as dash_mod


def _panel(db: dict):
    assert "dashboard" in db
    panels = db["dashboard"]["panels"]
    assert isinstance(panels, list) and len(panels) >= 1
    return panels


def test_pnl_dashboard_shape():
    db = dash_mod.create_pnl_dashboard()
    panels = _panel(db)
    for p in panels:
        assert "id" in p and "title" in p and "type" in p
        assert "targets" in p


def test_risk_dashboard_shape():
    db = dash_mod.create_risk_dashboard()
    panels = _panel(db)
    assert any("risk" in t.get("expr", "").lower() for p in panels for t in p["targets"])


def test_system_dashboard_shape():
    db = dash_mod.create_system_dashboard()
    panels = _panel(db)
    assert any("system" in t.get("expr", "").lower() for p in panels for t in p["targets"])


def test_strategy_dashboard_shape():
    db = dash_mod.create_strategy_dashboard()
    panels = _panel(db)
    assert any("strategy" in t.get("expr", "").lower() for p in panels for t in p["targets"])


def test_ml_dashboard_shape():
    db = dash_mod.create_ml_dashboard()
    panels = _panel(db)
    assert any("ml" in t.get("expr", "").lower() for p in panels for t in p["targets"])


def test_execution_dashboard_shape():
    db = dash_mod.create_execution_dashboard()
    panels = _panel(db)
    assert any("execution" in t.get("expr", "").lower() for p in panels for t in p["targets"])


def test_all_dashboards_returns_six():
    dashboards = dash_mod.create_all_dashboards()
    assert len(dashboards) == 6


def test_save_dashboards_writes_one_file_per_dashboard(tmp_path: Path):
    out = tmp_path / "dashboards"
    dash_mod.save_dashboards(str(out))
    files = list(out.iterdir())
    assert len(files) == 6


def test_save_dashboards_filename_slug_no_spaces(tmp_path: Path):
    out = tmp_path / "dashboards"
    out.mkdir(parents=True, exist_ok=True)
    dash_mod.save_dashboards(str(out))
    for f in out.iterdir():
        assert " " not in f.name
        assert "-" in f.name