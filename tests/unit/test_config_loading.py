from __future__ import annotations

from pathlib import Path

import yaml

from cryptobot.config import Settings, _flatten_yaml


def _write_yaml(tmp_path: Path, body: dict) -> Path:
    p = tmp_path / "cfg.yaml"
    p.write_text(yaml.safe_dump(body))
    return p


def test_flatten_yaml_picks_up_exchange_settings(tmp_path: Path):
    body = {
        "exchanges": {
            "binance": {
                "testnet": False,
                "symbols": ["BTCUSDT", "ETHUSDT"],
                "api_key": "x",
                "ws_url": "wss://example",
            }
        },
        "risk": {"max_total_exposure_pct": 0.42},
    }
    flat = _flatten_yaml(body)
    assert flat["exchange"]["symbols"] == ["BTCUSDT", "ETHUSDT"]
    assert flat["exchange"]["testnet"] is False
    assert flat["exchange"]["api_key"] == "x"
    assert flat["exchange"]["ws_url"] == "wss://example"
    assert flat["risk"]["max_total_exposure_pct"] == 0.42


def test_flatten_yaml_handles_missing_sections(tmp_path: Path):
    flat = _flatten_yaml({})
    assert flat["exchange"]["symbols"] == []
    assert flat["monitoring"]["prometheus_port"] == 9090
    assert flat["xmr"]["min_balance_xmr"] == 0.1
    assert flat["app"] == {}


def test_settings_from_yaml_real_config_file():
    root = Path(__file__).resolve().parents[2]
    yaml_path = root / "configs" / "base.yaml"
    if not yaml_path.exists():
        return
    s = Settings.from_yaml(yaml_path)
    assert s.exchange.symbols == [
        "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT",
        "XRPUSDT", "ADAUSDT", "DOGEUSDT", "AVAXUSDT",
    ]
    assert s.exchange.default_symbol == "BTCUSDT"
    assert s.market_data.redis_host == "redis"
    assert s.market_data.redis_port == 6379
    assert s.monitoring.prometheus_port == 9090
    assert s.monitoring.grafana_port == 3000
    assert s.xmr.daemon_port == 18081
    assert s.xmr.wallet_port == 18083
    assert s.backtest.commission_bps == 5
    assert s.risk.max_daily_loss_pct == 0.05
