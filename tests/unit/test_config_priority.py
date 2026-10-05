"""Env vars must override YAML config values (12-factor contract)."""


from cryptobot.config import Settings


def test_env_overrides_yaml_risk_limits(tmp_path, monkeypatch):
    yml = tmp_path / "base.yaml"
    yml.write_text(
        "risk:\n"
        "  max_single_position_pct: 0.20\n"
        "  max_total_exposure_pct: 0.80\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("RISK_MAX_SINGLE_POSITION_PCT", "1.0")
    monkeypatch.setenv("RISK_MAX_TOTAL_EXPOSURE_PCT", "1.0")
    s = Settings.from_yaml(yml)
    assert float(s.risk.max_single_position_pct) == 1.0
    assert float(s.risk.max_total_exposure_pct) == 1.0


def test_yaml_value_used_when_no_env(tmp_path, monkeypatch):
    yml = tmp_path / "base.yaml"
    yml.write_text("risk:\n  max_single_position_pct: 0.33\n", encoding="utf-8")
    monkeypatch.delenv("RISK_MAX_SINGLE_POSITION_PCT", raising=False)
    s = Settings.from_yaml(yml)
    assert float(s.risk.max_single_position_pct) == 0.33
