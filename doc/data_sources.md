# Data Sources

## Synthetic (Default)

Generates realistic OHLCV data: synthetic prices use a vectorized, mean-reverting (Ornstein-Uhlenbeck) random walk in log space, so long runs never overflow and keep trading; generation is deterministic per `seed`.

```bash
python -m cryptobot.cli.main backtest --strategy trend_following --bars 1000
```

**Characteristics**:
- Mean-reverting (Ornstein-Uhlenbeck) random walk in log space
- Realistic fat tails and volatility clustering
- Configurable drift, volatility, jump parameters
- Deterministic with seed for reproducibility

```python
from cryptobot.backtest.data import generate_synthetic_ohlcv

bars = generate_synthetic_ohlcv(
    start=datetime(2024, 1, 1),
    n_bars=1000,
    freq_minutes=1,
    seed=42,
)
```

## CSV

```bash
python -m cryptobot.cli.main backtest \
  --strategy trend_following \
  --source csv \
  --path ./data/btcusdt_1m.csv
```

### CSV Format

Required columns: `timestamp`, `open`, `high`, `low`, `close`, `volume`

```csv
timestamp,open,high,low,close,volume
2024-01-01T00:00:00,42000,42500,41500,42200,100.5
2024-01-01T00:01:00,42200,42300,42100,42250,98.3
```

### CSV Options

```bash
# With custom columns
python -m cryptobot.cli.main backtest \
  --source csv \
  --path ./data.csv \
  --timestamp-col timestamp \
  --open-col open \
  --high-col high \
  --low-col low \
  --close-col close \
  --volume-col volume
```

## Parquet

```bash
python -m cryptobot.cli.main backtest \
  --strategy trend_following \
  --source parquet \
  --path ./data/btcusdt.parquet
```

### Parquet Format

Supports partitioned and flat Parquet files. Must contain:
- `timestamp` (timestamp)
- `open`, `high`, `low`, `close` (numeric)
- `volume` (numeric)
- `symbol` (string, optional)
- `timeframe` (string, optional)

## TimescaleDB

```bash
python -m cryptobot.cli.main backtest \
  --strategy trend_following \
  --source timescale \
  --symbol BTCUSDT \
  --timeframe 1m \
  --start 2024-01-01 \
  --end 2024-02-01
```

### Configuration

```yaml
# configs/base.yaml
database:
  timescaledb_host: timescaledb
  timescaledb_port: 5432
  timescaledb_name: cryptobot
  timescaledb_user: cryptobot
  timescaledb_password: ${DB_PASSWORD}
  timescaledb_pool_size: 10
```

### Programmatic Access

```python
from cryptobot.backtest.data import load_bars

bars = await load_bars(
    source="timescale",
    symbol="BTCUSDT",
    timeframe="1h",
    start=datetime(2024, 1, 1),
    end=datetime(2024, 12, 31),
)
```

## Synthetic Data Generation

```python
from cryptobot.backtest.runner import generate_synthetic_ohlcv
from datetime import datetime

bars = generate_synthetic_ohlcv(
    start=datetime(2024, 1, 1),
    n_bars=2000,
    freq_minutes=1,
    seed=42,
    drift=0.0001,      # Daily drift
    volatility=0.02,   # Daily volatility
    jump_prob=0.001,   # Jump probability
    jump_size=0.03,    # Jump size (std)
)
```

## Custom Data Loading

### Custom OhlcvDataset

```python
from cryptobot.backtest.data import OhlcvDataset, OhlcvBar
from decimal import Decimal
from datetime import datetime

bars = [
    OhlcvBar(
        symbol="BTCUSDT",
        interval="1h",
        open_time=datetime(2024, 1, 1),
        close_time=datetime(2024, 1, 1, 1),
        open_price=Decimal("42000"),
        high_price=Decimal("42500"),
        low_price=Decimal("41500"),
        close_price=Decimal("42200"),
        volume=Decimal("100"),
        trades=1000,
        is_closed=True,
    )
]
dataset = OhlcvDataset(bars=bars, symbol="BTCUSDT", source="custom")
```

### Custom Data Loader

```python
from cryptobot.backtest.data import load_bars

# Custom source (implement in runner.py)
bars = await load_bars(
    source="custom",
    path="/path/to/data",
    symbol="BTCUSDT",
    timeframe="1h",
    start=datetime(2024, 1, 1),
    end=datetime(2024, 12, 31),
)
```

## OhlcvDataset API

```python
from cryptobot.backtest.data import OhlcvDataset

dataset = OhlcvDataset(bars=bars, symbol="BTCUSDT", source="csv")

# Filter by date range
filtered = dataset.filter_range(
    start=datetime(2024, 1, 1),
    end=datetime(2024, 12, 31),
)

# Iterate bars
for bar in dataset:
    print(bar.close_price)

# Length
len(dataset)

# Convert for runner
bars_list = dataset.to_runner_bars()
```

## Data Cleaning

```python
from cryptobot.data.cleaning import DataCleaner, validate_ohlcv

cleaner = DataCleaner()

# Clean klines
clean_df = cleaner.clean_klines(raw_df)

# Validate OHLCV
is_valid = validate_ohlcv(df)

# Clean tickers
clean_tickers = cleaner.clean_tickers(raw_tickers)

# Clean trades
clean_trades = cleaner.clean_trades(raw_trades)
```

### Validation Rules

- Timestamp monotonic increasing
- High >= max(open, close), Low <= min(open, close)
- Volume >= 0
- No missing required columns
- Detect and flag outliers (Z-score > 3)

## Data Storage

### TimescaleDB

```python
from cryptobot.data.storage import TimescaleDBStorage, StorageConfig

config = StorageConfig(
    timescaledb_host="localhost",
    timescaledb_port=5432,
    timescaledb_name="cryptobot",
    timescaledb_user="cryptobot",
    timescaledb_password="password",
)

storage = TimescaleDBStorage(config)
await storage.initialize()

# Write
await storage.write_klines(klines)
await storage.write_tickers(tickers)

# Read
df = await storage.read_klines("BTCUSDT", "1m", start, end)
```

### Parquet Storage

```python
from cryptobot.data.storage import ParquetStorage

storage = ParquetStorage(config)

await storage.write_klines(klines)
df = await storage.read_klines("BTCUSDT", "1m", start, end)
```

### Hybrid Storage

```python
from cryptobot.data.storage import HybridStorage

# Writes to both TimescaleDB and Parquet
storage = HybridStorage(config)
await storage.write_klines(klines)
df = await storage.read_klines("BTCUSDT", "1m", start, end)
```

## Custom Data Source

```python
from cryptobot.backtest.data import OhlcvDataset, OhlcvBar

# Create custom bars
bars = [
    OhlcvBar(
        symbol="BTCUSDT",
        interval="1h",
        open_time=datetime(2024, 1, 1),
        close_time=datetime(2024, 1, 1, 1),
        open_price=Decimal("42000"),
        high_price=Decimal("42500"),
        low_price=Decimal("41500"),
        close_price=Decimal("42200"),
        volume=Decimal("100"),
        trades=1000,
        is_closed=True,
    )
]

dataset = OhlcvDataset(bars=bars, symbol="BTCUSDT", source="custom")

# Use in backtest
from cryptobot.backtest.data import load_bars

ds = load_bars(source="synthetic", symbol="BTCUSDT", timeframe="1h", n_bars=500)
result = await run_backtest(ds.bars, strategy=strategy, symbol=ds.symbol)
```