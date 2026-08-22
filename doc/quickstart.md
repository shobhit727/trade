# Cryptobot Backtesting - Quick Start

## CLI Usage

```bash
# Basic backtest with synthetic data
python -m cryptobot.cli.main backtest \
  --strategy trend_following \
  --bars 500 \
  --timeframe 1h

# With CSV data
python -m cryptobot.cli.main backtest \
  --strategy mean_reversion \
  --bars 1000 \
  --source csv \
  --path ./data/btcusdt_1m.csv
```

### CLI Options

| Option | Default | Description |
|--------|---------|-------------|
| `--strategy` | mean_reversion | One of: mean_reversion, trend_following, stat_arb |
| `--bars` | 200 | Number of synthetic bars (capped at 10M) |
| `--source` | synthetic | Data source: synthetic, csv, parquet, timescale |
| `--path` | - | Path to data file (csv/parquet) |
| `--timeframe` | 1h | Synthetic bar spacing (e.g. 1m, 5s) |
| `--capital` | 10000 | Initial capital |
| `--seed` / `--vol` | 42 / 0.01 | Synthetic generator knobs |
| `--json` | false | Output as JSON (logs to stderr) |
| `--show-trades` | false | Include per-trade list |
| `--algorithms` / `--workers` | - | Parallel sweep of strategy/param jobs |

> Note: the backtest CLI has no `--symbol`, `--initial-capital`, `--commission-bps`, or
> `--slippage-bps` flags (older docs listed them). Symbol is fixed to BTCUSDT; capital is
> `--capital`; commission/slippage are set programmatically via `run_backtest(...)` kwargs.

## Programmatic Usage

```python
import asyncio
from cryptobot.backtest.data import load_bars
from cryptobot.backtest.runner import run_backtest
from cryptobot.strategies.trend_following import TrendFollowingStrategy, TrendFollowingConfig

async def run():
    config = TrendFollowingConfig(ema_fast=12, ema_slow=26, adx_threshold=25)
    strategy = TrendFollowingStrategy(config)
    
    ds = load_bars(source="synthetic", symbol="BTCUSDT", timeframe="1h", n_bars=500)
    result = await run_backtest(
        ds.bars,
        strategy=strategy,
        symbol=ds.symbol,
        initial_capital=10000,
    )
    
    print(f"Return: {result.total_return * 100:.2f}%")
    print(f"Final equity: {result.final_equity}")
    print(f"Trades: {result.n_trades}")

asyncio.run(run())
```