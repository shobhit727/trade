"""
Data module for Cryptobot - Ingestion, storage, and cleaning.
"""

from cryptobot.data.cleaning import (
    DataCleaner,
    DataQualityIssue,
    QualityReport,
    clean_klines,
    clean_tickers,
    clean_trades,
    detect_outliers_zscore,
    fill_missing_bars,
    validate_ohlcv,
)
from cryptobot.data.ingestion import (
    OHLCV,
    BinanceDataIngestion,
    DataIngestion,
    DataIngestionManager,
    DataSourceConfig,
    Tick,
    TradeData,
    get_ingestion_manager,
)
from cryptobot.data.storage import (
    HybridStorage,
    ParquetDataFrameStorage,
    ParquetStorage,
    StorageBackend,
    StorageConfig,
    TimescaleDBStorage,
    TimescaleStorage,
    get_storage,
    init_storage,
    shutdown_storage,
)

__all__ = [
    "DataSourceConfig",
    "DataIngestion",
    "BinanceDataIngestion",
    "DataIngestionManager",
    "get_ingestion_manager",
    "OHLCV",
    "Tick",
    "TradeData",
    "StorageConfig",
    "StorageBackend",
    "TimescaleDBStorage",
    "TimescaleStorage",
    "ParquetStorage",
    "ParquetDataFrameStorage",
    "HybridStorage",
    "get_storage",
    "init_storage",
    "shutdown_storage",
    "DataQualityIssue",
    "QualityReport",
    "DataCleaner",
    "clean_klines",
    "clean_tickers",
    "clean_trades",
    "validate_ohlcv",
    "detect_outliers_zscore",
    "fill_missing_bars",
]
