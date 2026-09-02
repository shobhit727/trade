from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    name: str = "cryptobot"
    env: str = "development"
    log_level: str = "INFO"
    timezone: str = "UTC"

    model_config = SettingsConfigDict(env_prefix="APP_", extra="ignore")


class ExchangeSettings(BaseSettings):
    enabled: bool = True
    testnet: bool = True
    api_key: str = ""
    api_secret: str = ""
    base_url: str = "https://testnet.binance.vision"
    ws_url: str = "wss://testnet.binance.vision"
    rate_limit: int = 1200
    symbols: list[str] = Field(default_factory=list)
    default_symbol: str = "BTCUSDT"
    timeframes: list[str] = Field(default_factory=list)
    max_positions: int = 5
    position_size_pct: float = 0.15

    model_config = SettingsConfigDict(env_prefix="BINANCE_", extra="ignore")


class MarketDataSettings(BaseSettings):
    buffer_size: int = 10000
    orderbook_depth: int = 20
    update_interval_ms: int = 100
    cache_ttl_seconds: int = 300
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_db: int = 0
    redis_max_connections: int = 50

    model_config = SettingsConfigDict(env_prefix="MARKET_DATA_", extra="ignore")


class RiskSettings(BaseSettings):
    max_total_exposure_pct: float = 0.80
    max_single_position_pct: float = 0.20
    max_daily_loss_pct: float = 0.05
    max_drawdown_pct: float = 0.15
    max_correlation: float = 0.7
    kill_switch_enabled: bool = True
    kill_switch_daily_loss_pct: float = 0.10
    position_sizing: str = "kelly_fraction"
    kelly_fraction: float = 0.25
    volatility_target: float = 0.15
    min_order_size_usd: float = 10
    max_order_size_usd: float = 10000
    max_leverage: float = 5.0
    max_open_positions: int = 10
    price_deviation_pct: float = 0.05
    max_orders_per_minute: int = 60
    require_stop_loss_above_usd: float = 1000.0
    drawdown_scale_start_pct: float = 0.05
    drawdown_scale_floor_pct: float = 0.25

    model_config = SettingsConfigDict(env_prefix="RISK_", extra="ignore")


class ExecutionSettings(BaseSettings):
    mode: str = "paper"
    order_type: str = "limit"
    limit_offset_bps: int = 5
    ioc_timeout_ms: int = 5000
    max_slippage_bps: int = 20
    retry_attempts: int = 3
    retry_delay_ms: int = 100
    smart_routing: bool = False

    model_config = SettingsConfigDict(env_prefix="EXECUTION_", extra="ignore")


class MLSettings(BaseSettings):
    enabled: bool = True
    inference_mode: str = "local"
    model_path: str = "/app/models"
    features: list[str] = Field(default_factory=list)
    min_samples_train: int = 10000
    feature_lookback: int = 500

    model_config = SettingsConfigDict(env_prefix="ML_", extra="ignore")


class XMRSettings(BaseSettings):
    enabled: bool = True
    daemon_host: str = "host.docker.internal"
    daemon_port: int = 18081
    daemon_ssl: bool = False
    daemon_username: str = ""
    daemon_password: str = ""
    wallet_host: str = "host.docker.internal"
    wallet_port: int = 18083
    wallet_ssl: bool = False
    wallet_username: str = ""
    wallet_password: str = ""
    funding_enabled: bool = True
    min_balance_xmr: float = 0.1
    target_balance_xmr: float = 1.0
    withdraw_threshold_xmr: float = 5.0
    withdraw_address: str = ""
    confirmations: int = 10
    subaddress_lookahead: int = 100

    model_config = SettingsConfigDict(env_prefix="XMR_", extra="ignore")


class MonitoringSettings(BaseSettings):
    prometheus_enabled: bool = True
    prometheus_port: int = 9090
    grafana_enabled: bool = True
    grafana_port: int = 3000
    telegram_enabled: bool = False
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    discord_webhook: str = ""
    email_enabled: bool = False
    email_smtp_host: str = ""
    email_smtp_port: int = 587
    email_username: str = ""
    email_password: str = ""
    email_from: str = ""
    email_to: list[str] = []
    whatsapp_enabled: bool = False
    whatsapp_token: str = ""
    whatsapp_phone_id: str = ""
    whatsapp_to: list[str] = []
    health_check_interval: int = 30
    data_stale_threshold_seconds: int = 60
    data_degraded_threshold_seconds: int = 10

    model_config = SettingsConfigDict(env_prefix="MONITORING_", extra="ignore")


class DatabaseSettings(BaseSettings):
    type: str = "timescaledb"
    host: str = "timescaledb"
    port: int = 5432
    name: str = "cryptobot"
    user: str = "cryptobot"
    password: str = ""
    pool_size: int = 10
    max_overflow: int = 20

    model_config = SettingsConfigDict(env_prefix="DB_", extra="ignore")


class BacktestSettings(BaseSettings):
    enabled: bool = True
    start_date: str = "2024-01-01"
    end_date: str = "2024-12-31"
    initial_capital: float = 10000
    commission_bps: int = 5
    slippage_bps: int = 3
    funding_rate_included: bool = True

    model_config = SettingsConfigDict(env_prefix="BACKTEST_", extra="ignore")


class ExternalServicesSettings(BaseSettings):
    kite_base_url: str = "https://api.kite.trade"
    kite_login_url: str = "https://kite.zerodha.com/connect/login"
    yahoo_finance_chart_url: str = "https://query1.finance.yahoo.com/v8/finance/chart/"
    binance_production_url: str = "https://api.binance.com"
    binance_futures_url: str = "https://fapi.binance.com"
    binance_spot_ws_url: str = "wss://stream.binance.com:9443/stream?streams="
    binance_futures_ws_url: str = "wss://fstream.binance.com/stream?streams="
    binance_data_ws_url: str = "wss://stream.binance.com:9443"
    telegram_api_url: str = "https://api.telegram.org"
    pagerduty_events_url: str = "https://events.pagerduty.com/v2/enqueue"
    whatsapp_api_url: str = "https://graph.facebook.com/v21.0"

    model_config = SettingsConfigDict(env_prefix="EXTERNAL_", extra="ignore")


class TimeoutSettings(BaseSettings):
    http_default_timeout: int = 20
    http_long_timeout: int = 30
    http_short_timeout: int = 10
    strategy_feed_timeout: float = 0.5
    stop_wait_timeout: int = 30
    smtp_timeout: int = 30

    model_config = SettingsConfigDict(env_prefix="TIMEOUT_", extra="ignore")


class ServerSettings(BaseSettings):
    host: str = "127.0.0.1"
    port: int = 8080
    nse_basket_port: int = 8084
    nse_powerhour_port: int = 8085

    model_config = SettingsConfigDict(env_prefix="SERVER_", extra="ignore")


class Settings(BaseSettings):
    app: AppSettings = Field(default_factory=AppSettings)
    exchange: ExchangeSettings = Field(default_factory=ExchangeSettings)
    market_data: MarketDataSettings = Field(default_factory=MarketDataSettings)
    risk: RiskSettings = Field(default_factory=RiskSettings)
    execution: ExecutionSettings = Field(default_factory=ExecutionSettings)
    ml: MLSettings = Field(default_factory=MLSettings)
    xmr: XMRSettings = Field(default_factory=XMRSettings)
    monitoring: MonitoringSettings = Field(default_factory=MonitoringSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    backtest: BacktestSettings = Field(default_factory=BacktestSettings)
    external_services: ExternalServicesSettings = Field(default_factory=ExternalServicesSettings)
    timeouts: TimeoutSettings = Field(default_factory=TimeoutSettings)
    server: ServerSettings = Field(default_factory=ServerSettings)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    @classmethod
    def from_yaml(cls, path: str | Path) -> "Settings":
        """Load settings from a YAML file, then let env vars override.

        Priority (12-factor): environment > yaml file. Without this, mounted
        configs/base.yaml silently defeated RISK_* / EXCHANGE_* env vars in
        containers even though the docs promise env-overridable settings.
        """
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        flat = _flatten_yaml(data)

        import os

        for name, field_info in cls.model_fields.items():
            sub = field_info.default_factory
            if not callable(sub) or not hasattr(sub, "model_fields"):
                continue
            prefix = (sub.model_config.get("env_prefix") or "").upper()
            if not prefix:
                continue
            section = flat.setdefault(name, {})
            for fname in sub.model_fields:
                ev = os.getenv(prefix + fname.upper())
                if ev is not None:
                    section[fname] = ev
        return cls(**flat)


def _flatten_yaml(data: dict[str, Any]) -> dict[str, Any]:
    binance = data.get("exchanges", {}).get("binance", {})
    market_data = data.get("market_data", {})
    redis_cfg = market_data.get("redis", {})
    monitoring = data.get("monitoring", {})
    prom_cfg = monitoring.get("prometheus", {})
    grafana_cfg = monitoring.get("grafana", {})
    alerts_cfg = monitoring.get("alerts", {})
    xmr = data.get("xmr", {})
    xmr_daemon = xmr.get("daemon", {})
    xmr_wallet = xmr.get("wallet_rpc", {})
    xmr_funding = xmr.get("funding", {})
    external_services = data.get("external_services", {})
    timeouts_cfg = data.get("timeouts", {})
    server_cfg = data.get("server", {})

    flattened: dict[str, Any] = {
        "app": data.get("app", {}),
        "exchange": {
            "enabled": binance.get("enabled", True),
            "testnet": binance.get("testnet", True),
            "api_key": binance.get("api_key", ""),
            "api_secret": binance.get("api_secret", ""),
            "base_url": binance.get("base_url", "https://testnet.binance.vision"),
            "ws_url": binance.get("ws_url", "wss://testnet.binance.vision"),
            "rate_limit": binance.get("rate_limit", 1200),
            "symbols": binance.get("symbols", []),
            "default_symbol": binance.get("default_symbol", "BTCUSDT"),
            "timeframes": binance.get("timeframes", []),
            "max_positions": binance.get("max_positions", 5),
            "position_size_pct": binance.get("position_size_pct", 0.15),
        },
        "market_data": {
            "buffer_size": market_data.get("buffer_size", 10000),
            "orderbook_depth": market_data.get("orderbook_depth", 20),
            "update_interval_ms": market_data.get("update_interval_ms", 100),
            "cache_ttl_seconds": market_data.get("cache_ttl_seconds", 300),
            "redis_host": redis_cfg.get("host", "redis"),
            "redis_port": redis_cfg.get("port", 6379),
            "redis_db": redis_cfg.get("db", 0),
            "redis_max_connections": redis_cfg.get("max_connections", 50),
        },
        "risk": data.get("risk", {}),
        "execution": data.get("execution", {}),
        "ml": data.get("ml", {}),
        "xmr": {
            "enabled": xmr.get("enabled", True),
            "daemon_host": xmr_daemon.get("host", "host.docker.internal"),
            "daemon_port": xmr_daemon.get("port", 18081),
            "daemon_ssl": xmr_daemon.get("ssl", False),
            "daemon_username": xmr_daemon.get("username", ""),
            "daemon_password": xmr_daemon.get("password", ""),
            "wallet_host": xmr_wallet.get("host", "host.docker.internal"),
            "wallet_port": xmr_wallet.get("port", 18083),
            "wallet_ssl": xmr_wallet.get("ssl", False),
            "wallet_username": xmr_wallet.get("username", ""),
            "wallet_password": xmr_wallet.get("password", ""),
            "funding_enabled": xmr_funding.get("enabled", True),
            "min_balance_xmr": xmr_funding.get("min_balance_xmr", 0.1),
            "target_balance_xmr": xmr_funding.get("target_balance_xmr", 1.0),
            "withdraw_threshold_xmr": xmr_funding.get("withdraw_threshold_xmr", 5.0),
            "withdraw_address": xmr_funding.get("withdraw_address", ""),
            "confirmations": xmr_funding.get("confirmations", 10),
            "subaddress_lookahead": xmr.get("subaddress_lookahead", 100),
        },
        "monitoring": {
            "prometheus_enabled": prom_cfg.get("enabled", True),
            "prometheus_port": prom_cfg.get("port", 9090),
            "grafana_enabled": grafana_cfg.get("enabled", True),
            "grafana_port": grafana_cfg.get("port", 3000),
            "telegram_enabled": alerts_cfg.get("telegram_enabled", False),
            "telegram_bot_token": alerts_cfg.get("telegram_bot_token", ""),
            "telegram_chat_id": alerts_cfg.get("telegram_chat_id", ""),
            "discord_webhook": alerts_cfg.get("discord_webhook", ""),
            "email_enabled": alerts_cfg.get("email_enabled", False),
            "whatsapp_enabled": alerts_cfg.get("whatsapp_enabled", False),
            "whatsapp_token": alerts_cfg.get("whatsapp_token", ""),
            "whatsapp_phone_id": alerts_cfg.get("whatsapp_phone_id", ""),
            "whatsapp_to": alerts_cfg.get("whatsapp_to", []),
            "health_check_interval": monitoring.get("health_check_interval", 30),
            "data_stale_threshold_seconds": monitoring.get("data_stale_threshold_seconds", 60),
            "data_degraded_threshold_seconds": monitoring.get("data_degraded_threshold_seconds", 10),
        },
        "database": data.get("database", {}),
        "backtest": data.get("backtest", {}),
        "external_services": {
            "kite_base_url": external_services.get("kite_base_url", "https://api.kite.trade"),
            "kite_login_url": external_services.get("kite_login_url", "https://kite.zerodha.com/connect/login"),
            "yahoo_finance_chart_url": external_services.get("yahoo_finance_chart_url", "https://query1.finance.yahoo.com/v8/finance/chart/"),
            "binance_production_url": external_services.get("binance_production_url", "https://api.binance.com"),
            "binance_futures_url": external_services.get("binance_futures_url", "https://fapi.binance.com"),
            "binance_spot_ws_url": external_services.get("binance_spot_ws_url", "wss://stream.binance.com:9443/stream?streams="),
            "binance_futures_ws_url": external_services.get("binance_futures_ws_url", "wss://fstream.binance.com/stream?streams="),
            "binance_data_ws_url": external_services.get("binance_data_ws_url", "wss://stream.binance.com:9443"),
            "telegram_api_url": external_services.get("telegram_api_url", "https://api.telegram.org"),
            "pagerduty_events_url": external_services.get("pagerduty_events_url", "https://events.pagerduty.com/v2/enqueue"),
            "whatsapp_api_url": external_services.get("whatsapp_api_url", "https://graph.facebook.com/v21.0"),
        },
        "timeouts": {
            "http_default_timeout": timeouts_cfg.get("http_default_timeout", 20),
            "http_long_timeout": timeouts_cfg.get("http_long_timeout", 30),
            "http_short_timeout": timeouts_cfg.get("http_short_timeout", 10),
            "strategy_feed_timeout": timeouts_cfg.get("strategy_feed_timeout", 0.5),
            "stop_wait_timeout": timeouts_cfg.get("stop_wait_timeout", 30),
            "smtp_timeout": timeouts_cfg.get("smtp_timeout", 30),
        },
        "server": {
            "host": server_cfg.get("host", "127.0.0.1"),
            "port": server_cfg.get("port", 8080),
            "nse_basket_port": server_cfg.get("nse_basket_port", 8084),
            "nse_powerhour_port": server_cfg.get("nse_powerhour_port", 8085),
        },
    }
    return flattened


@lru_cache
def get_settings() -> Settings:
    import os
    config_path_str = os.environ.get("CRYPTOBOT_CONFIG")
    if config_path_str:
        config_path = Path(config_path_str)
    else:
        config_path = Path(__file__).parent.parent.parent / "configs" / "base.yaml"
    if config_path.exists():
        return Settings.from_yaml(config_path)
    return Settings()


settings = get_settings()
