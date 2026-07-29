"""
Data module for Cryptobot - Ingestion, storage, and cleaning.
"""

from cryptobot.data.ingestion import (
    DataSourceConfig,
    DataIngestion,
    BinanceDataIngestion,
    DataIngestionManager,
    get_ingestion_manager,
    OHLCV,
    Tick,
    TradeData,
)

from cryptobot.data.storage import (
    StorageConfig,
    StorageBackend,
    TimescaleDBStorage,
    TimescaleStorage,
    ParquetStorage,
    ParquetDataFrameStorage,
    HybridStorage,
    get_storage,
    init_storage,
    shutdown_storage,
)

from cryptobot.data.cleaning import (
    DataQualityIssue,
    QualityReport,
    DataCleaner,
    clean_klines,
    clean_tickers,
    clean_trades,
    validate_ohlcv,
    detect_outliers_zscore,
    fill_missing_bars,
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
