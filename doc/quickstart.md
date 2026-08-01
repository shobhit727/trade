# Cryptobot Backtesting - Quick Start

## CLI Usage

```bash
# Basic backtest with synthetic data
python -m cryptobot.cli.main backtest \
  --strategy trend_following \
  --bars 500 \
  --symbol BTCUSDT \
  --timeframe 1m

# With CSV data
python -m cryptobot.cli.main backtest \
  --strategy mean_reversion \
  --bars 1000 \
  --source csv \
  --path ./data/btcusdt_1m.csv \
  --symbol BTCUSDT \
  --timeframe 1m
```

### CLI Options

| Option | Default | Description |
|--------|---------|-------------|
| `--strategy` | required | Strategy name |
| `--bars` | 200 | Number of synthetic bars |
| `--source` | synthetic | Data source: synthetic, csv, parquet, timescale |
| `--path` | - | Path to data file (csv/parquet) |
| `--symbol` | BTCUSDT | Trading symbol |
| `--timeframe` | 1m | Timeframe (1m, 5m, 15m, 1h, 4h, 1d) |
| `--initial-capital` | 10000 | Initial capital |
| `--commission-bps` | 5 | Commission in basis points |
| `--slippage-bps` | 3 | Slippage in basis points |
| `--json` | false | Output as JSON |

## Programmatic Usage

```python
import asyncio
from cryptobot.backtest.runner import run_backtest
from cryptobot.strategies.trend_following import TrendFollowingStrategy, TrendFollowingConfig

async def run():
    config = TrendFollowingConfig(ema_fast=12, ema_slow=26, adx_threshold=25)
    strategy = TrendFollowingStrategy(config)
    
    result = await run_backtest(
        strategy=strategy,
        symbol="BTCUSDT",
        timeframe="1m",
        bars=500,
        initial_capital=10000,
        commission_bps=5,
        slippage_bps=3,
    )
    
    print(f"Return: {result.total_return}%")
    print(f"Sharpe: {result.Sharpe_ratio}")
    print(f"Max DD: {result.max_drawdown}%")
    print(f"Trades: {result.total_trades}")

asyncio.run(run())
```