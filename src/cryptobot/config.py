from functools import lru_cache
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
import yaml
from pathlib import Path


class AppSettings(BaseSettings):
    name: str = "cryptobot"
    env: str = "development"
    log_level: str = "INFO"
    timezone: str = "UTC"

    model_config = SettingsConfigDict(env_prefix="APP_")


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

    model_config = SettingsConfigDict(env_prefix="BINANCE_")


class MarketDataSettings(BaseSettings):
    buffer_size: int = 10000
    orderbook_depth: int = 20
    update_interval_ms: int = 100
    cache_ttl_seconds: int = 300
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_db: int = 0
    redis_max_connections: int = 50

    model_config = SettingsConfigDict(env_prefix="MARKET_DATA_")


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

    model_config = SettingsConfigDict(env_prefix="RISK_")


class ExecutionSettings(BaseSettings):
    mode: str = "paper"
    order_type: str = "limit"
    limit_offset_bps: int = 5
    ioc_timeout_ms: int = 5000
    max_slippage_bps: int = 20
    retry_attempts: int = 3
    retry_delay_ms: int = 100
    smart_routing: bool = False

    model_config = SettingsConfigDict(env_prefix="EXECUTION_")


class MLSettings(BaseSettings):
    enabled: bool = True
    inference_mode: str = "local"
    model_path: str = "/app/models"
    features: list[str] = Field(default_factory=list)
    min_samples_train: int = 10000
    feature_lookback: int = 500

    model_config = SettingsConfigDict(env_prefix="ML_")


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

    model_config = SettingsConfigDict(env_prefix="XMR_")


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
    health_check_interval: int = 30

    model_config = SettingsConfigDict(env_prefix="MONITORING_")


class DatabaseSettings(BaseSettings):
    type: str = "timescaledb"
    host: str = "timescaledb"
    port: int = 5432
    name: str = "cryptobot"
    user: str = "cryptobot"
    password: str = ""
    pool_size: int = 10
    max_overflow: int = 20

    model_config = SettingsConfigDict(env_prefix="DB_")


class BacktestSettings(BaseSettings):
    enabled: bool = True
    start_date: str = "2024-01-01"
    end_date: str = "2024-12-31"
    initial_capital: float = 10000
    commission_bps: int = 5
    slippage_bps: int = 3
    funding_rate_included: bool = True

    model_config = SettingsConfigDict(env_prefix="BACKTEST_")


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

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    @classmethod
    def from_yaml(cls, path: str | Path) -> "Settings":
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls(**data)


@lru_cache
def get_settings() -> Settings:
    config_path = Path(__file__).parent.parent.parent / "configs" / "base.yaml"
    if config_path.exists():
        return Settings.from_yaml(config_path)
    return Settings()


settings = get_settings()