# CLI Reference

## Overview

The Cryptobot CLI provides commands for backtesting, market-making, ML inference, paper trading, live paper-funding monitoring, and system health checks.

## Installation

```bash
pip install -e .
# or
pip install cryptobot
```

## Commands

```bash
cryptobot --help
```

### Global Options

| Option | Description |
|--------|-------------|
| `--help` | Show help message |
| `--version` | Show version |
| `--config` | Path to config file (default: configs/base.yaml) |
| `--log-level` | Log level: DEBUG, INFO, WARNING, ERROR |

## Commands

### backtest

Run a backtest simulation.

```bash
cryptobot backtest [OPTIONS]
```

#### Options

| Option | Default | Description |
|--------|---------|-------------|
| `--strategy` | mean_reversion | Strategy: mean_reversion, trend_following, stat_arb |
| `--source` | synthetic | Data source: synthetic, csv, parquet, timescale |
| `--path` | - | Path to data file (csv/parquet) |
| `--bars` | 200 | Number of bars (synthetic; capped at 10,000,000) |
| `--seed` | 42 | RNG seed for synthetic data |
| `--vol` | 0.01 | Volatility for synthetic data |
| `--capital` | 10000 | Initial capital (Decimal) |
| `--start` | 2024-01-01T00:00:00 | Start datetime |
| `--end` | 2024-01-02T00:00:00 | End datetime |
| `--json` | false | Output result as JSON (logs go to stderr; stdout is pure JSON) |
| `--show-trades` | false | Include every closed trade in output (`trades[]` in JSON) |
| `--algorithms` | - | JSON file with a list of jobs to sweep in parallel |
| `--workers` | 0 | Worker processes for `--algorithms` (default: one per CPU core) |

#### Examples

```bash
# Basic backtest
cryptobot backtest --strategy trend_following --bars 500

# With CSV data
cryptobot backtest --strategy trend_following --source csv --path data/btc.csv

# JSON + every trade
cryptobot backtest --strategy trend_following --bars 5000 --json --show-trades

# Parallel sweep across CPU cores
cryptobot backtest --algorithms jobs.json --workers 8 --json

# Custom parameters
cryptobot backtest \
  --strategy trend_following \
  --bars 1000 \
  --capital 50000 \
  --seed 7 \
  --vol 0.02
```

### paper

Run paper trading (simulated live trading).

```bash
cryptobot paper [OPTIONS]
```

#### Options

| Option | Default | Description |
|--------|---------|-------------|
| `--host` | 0.0.0.0 | Host to bind |
| `--port` | 8080 | Port to bind |
| `--strategy` | trend_following | Strategy name |
| `--symbol` | BTCUSDT | Trading symbol |
| `--timeframe` | 1m | Timeframe |
| `--config` | configs/base.yaml | Config file |

#### Example

```bash
cryptobot paper --strategy trend_following --symbol ETHUSDT --timeframe 5m
```

### bot

Run live trading bot.

```bash
cryptobot bot [OPTIONS]
```

#### Options

| Option | Default | Description |
|--------|---------|-------------|
| `--host` | 0.0.0.0 | Host to bind |
| `--port` | 8080 | Port to bind |
| `--strategy` | trend_following | Strategy name |
| `--symbol` | BTCUSDT | Trading symbol |
| `--timeframe` | 1m | Timeframe |
| `--mode` | paper | paper, live, binance |

**⚠️ Warning**: Live mode uses real funds. Test thoroughly in paper mode first.

```bash
cryptobot bot --mode paper --strategy trend_following --symbol BTCUSDT
```

### serve

Run health/metrics server.

```bash
cryptobot serve [OPTIONS]
```

#### Options

| Option | Default | Description |
|--------|---------|-------------|
| `--host` | 0.0.0.0 | Host to bind |
| `--port` | 8080 | Port to bind |

```bash
cryptobot serve --port 8080
```

### mm

Run the market-making strategy against order book.

```bash
cryptobot mm [OPTIONS]
```

### ml

Train a direction classifier and emit predictions.

```bash
cryptobot ml [OPTIONS]
```

### validate

Validate backtest statistical significance.

```bash
cryptobot validate [OPTIONS]
```

### paper-funder

Live paper monitor for the funding-carry edge (public WS, no API keys).

```bash
cryptobot paper-funder [OPTIONS]
```

#### Options

| Option | Default | Description |
|--------|---------|-------------|
| `--symbols` | BTCUSDT ETHUSDT | Comma- or space-separated symbols |
| `--hours` | 24 | Hours to monitor (0 = run forever) |
| `--log` | paper_funding.csv | CSV log path |
| `--poll-fapi` | false | Use fapi REST polling for the perp leg (futures WS blocked on some networks) |
| `--poll-interval` | 5.0 | fapi polling seconds |
| `--json` | false | JSON output |

```bash
cryptobot paper-funder --symbols BTC,ETH --hours 6 --poll-fapi --json
```

## Strategy-Specific Options

### Trend Following

```bash
cryptobot backtest --strategy trend_following \
  --ema-fast 12 \
  --ema-slow 26 \
  --adx-threshold 25 \
  --atr-period 14 \
  --atr-mult 2.0
```

| Option | Default | Description |
|--------|---------|-------------|
| `--ema-fast` | 12 | Fast EMA period |
| `--ema-slow` | 26 | Slow EMA period |
| `--adx-threshold` | 25 | ADX trend threshold |
| `--atr-period` | 14 | ATR period |
| `--atr-mult` | 2.0 | ATR multiplier |
| `--risk-per-trade` | 0.02 | Risk per trade |

### Mean Reversion

```bash
cryptobot backtest --strategy mean_reversion \
  --bb-period 20 \
  --bb-std 2.0 \
  --rsi-period 14 \
  --rsi-overbought 70 \
  --rsi-oversold 30
```

### Market Making

```bash
cryptobot backtest --strategy market_making \
  --gamma 0.5 \
  --sigma 0.01 \
  --kappa 1.5 \
  --A 0.025 \
  --max-inventory 5
```

### Stat Arb

```bash
cryptobot backtest --strategy stat_arb \
  --lookback 60 \
  --z-entry 2.0 \
  --z-exit 0.4 \
  --z-stop 3.5
```

### Funding Arb

```bash
cryptobot backtest --strategy funding_arb \
  --min-funding-rate 0.0001 \
  --basis-entry-bps 5.0 \
  --basis-exit-bps 1.5
```

### ML Strategy

```bash
cryptobot backtest --strategy ml \
  --retrain-interval 100 \
  --min-train-samples 500
```

## Environment Variables

All CLI options can be set via environment variables:

```bash
export STRATEGY=trend_following
export BARS=500
export SYMBOL=BTCUSDT
export TIMEFRAME=1m
export INITIAL_CAPITAL=10000
export COMMISSION_BPS=5
export SLIPPAGE_BPS=3

cryptobot backtest
```

### Priority

1. CLI arguments (highest)
2. Environment variables
3. Config file (configs/base.yaml)
4. Defaults

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error |
| 2 | Invalid arguments |
| 3 | Config error |
| 4 | Connection error |
| 5 | Validation failed |

## Shell Completion

```bash
# Bash
eval "$(_CRYPTOBOT_COMPLETE=bash_source cryptobot)"

# Zsh
eval "$(_CRYPTOBOT_COMPLETE=zsh_source cryptobot)"

# Fish
eval (env _CRYPTOBOT_COMPLETE=fish_source cryptobot)
```

## Examples

### Run a complete workflow

```bash
# 1. Ingest data
cryptobot ingest --symbol BTCUSDT --timeframe 1h --days 90

# 2. Run backtest
cryptobot backtest --strategy trend_following --bars 1000 --validate

# 3. Run validation on results
cryptobot backtest --strategy trend_following --bars 1000 --validate --json

# 4. Paper trading
cryptobot paper --strategy trend_following --symbol BTCUSDT
```

### CI/CD Integration

```yaml
# .github/workflows/backtest.yml
- name: Run backtest
  run: |
    python -m cryptobot.cli.main backtest \
      --strategy trend_following \
      --bars 1000 \
      --validate \
      --json > backtest_result.json

- name: Check results
  run: |
    python -c "
import json
with open('backtest_result.json') as f:
    r = json.load(f)
    assert r['passed'], 'Validation failed'
    print(f'Sharpe: {r[\"sharpe\"]}')"
```