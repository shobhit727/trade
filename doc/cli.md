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
python -m cryptobot.cli.main --help     # or `cryptobot` if pip-installed
```

### Global Options

| Option | Description |
|--------|-------------|
| `--help` | Show help message |

> The CLI is argparse-based; there is no `--version`, `--config`, or `--log-level` global flag,
> and no shell completion (older versions of this page described click-style features that were
> never implemented). Logging follows `APP_LOG_LEVEL` from settings/env.

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
| `--timeframe` | 1h | Bar spacing for synthetic data (e.g. 1m, 5s, 100ms) |

> Note: `--strategy` accepts the three core strategies (`mean_reversion`, `trend_following`,
> `stat_arb`) — not yet the full 84-strategy catalog (registry names work programmatically via
> `make_strategy`).

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

Run paper trading dry-run (synthetic bars → market orders through SimulatedVenue).

```bash
cryptobot paper [OPTIONS]
```

#### Options

| Option | Default | Description |
|--------|---------|-------------|
| `--symbol` | BTCUSDT | Trading symbol |
| `--source` | synthetic | Data source |
| `--bars` | 200 | Number of synthetic bars |
| `--json` | false | JSON output |

#### Example

```bash
python -m cryptobot.cli.main paper --symbol ETHUSDT --bars 500
```

> `paper` is a synthetic dry-run that exits when the bars run out — it does not bind a port and
> has no `--host/--port/--strategy/--timeframe` options (older docs listed those; they never
> existed). The long-running process command is `bot`.

### bot

Run the live/paper trading loop: Binance WS klines -> strategy -> risk-checked
execution, alongside the health/metrics server.

```bash
cryptobot bot [OPTIONS]
```

#### Options

| Option | Default | Description |
|--------|---------|-------------|
| `--host` | 127.0.0.1 | Bind host |
| `--port` | 8080 | Bind port |
| `--strategy` | trend_following | Any registry/catalog strategy name |
| `--symbol` | BTCUSDT | Trading symbol |
| `--timeframe` | 1m | Kline interval |
| `--mode` | paper | paper (SimulatedVenue) or live (BinanceVenue; confirmation prompt) |
| `--warmup` | 300 | REST bars used to prime indicators before streaming |
| `--max-bars` | - | Stop after N closed bars (dry-run/testing) |

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

### carry

Two-leg funding-carry backtest (long spot / short perp) with real funding history.

```bash
cryptobot carry --spot data/spot.csv --perp data/perp.csv [OPTIONS]
```

#### Options

| Option | Default | Description |
|--------|---------|-------------|
| `--spot` | required | Spot CSV (Binance klines format) |
| `--perp` | required | Perp CSV (same format; time-aligned to spot) |
| `--funding` | - | Binance fundingRate CSV (`funding_time,funding_rate`); omit for fixed rate |
| `--fixed-rate` | 0.0001 | Fixed per-8h rate when no CSV |
| `--symbol` / `--perp-symbol` | BTCUSDT / BTCUSDTPERP | Leg symbols |
| `--entry` / `--exit` | 0.0003 / 0.00005 | Funding-rate entry/exit thresholds |
| `--qty` | USD 10k / price | Quantity per leg |
| `--capital` | 10000 | Starting capital |
| `--risk` | 0.0 | Equity fraction per pair (0 = fixed qty) |
| `--max-notional` | 0 (uncapped) | Cap pair notional in USD |
| `--commission-bps` | 5 | Per-leg commission |
| `--json` | false | JSON output |

```bash
python -m cryptobot.cli.main carry --spot spot.csv --perp perp.csv \
  --funding funding.csv --risk 0.02 --json
```

## Strategy-Specific Options

> ⚠️ The backtest CLI does **not** expose per-strategy flags (no `--ema-fast`, `--bb-period`,
> `--gamma`, `--lookback`, `--retrain-interval`, …). Strategy parameters come from dataclass
> defaults; to vary them use the parallel sweep with a params file:

```bash
cat > jobs.json <<'EOF'
[{"strategy": "trend_following", "params": {"fast": 8, "slow": 21}},
 {"strategy": "mean_reversion",  "params": {"rsi_period": 7}}]
EOF
python -m cryptobot.cli.main backtest --algorithms jobs.json --workers 4 --json
```

`make_strategy(name, **params)` (backtest/runner.py) is the programmatic equivalent.

## Environment Variables

The CLI does not read `STRATEGY`/`BARS`-style env vars (older docs claimed an env override layer
that was never implemented). Configuration comes from settings/env prefixes (`APP_`, `RISK_`,
`EXECUTION_`, `BINANCE_`, `MARKET_DATA_`, `MONITORING_`, `DB_`, `ML_`, `BACKTEST_`) via
`configs/base.yaml` + pydantic-settings.

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error (including `validate` reporting a failed significance check) |
| 2 | Invalid arguments / unknown command |

## Examples

### Run a backtest workflow

```bash
# 1. Backtest on synthetic data
python -m cryptobot.cli.main backtest --strategy trend_following --bars 1000

# 2. Validate statistical significance of a return series
python -m cryptobot.cli.main validate --bars 1000 --json

# 3. Two-leg carry backtest with real funding history
python -m cryptobot.cli.main carry --spot data/spot.csv --perp data/perp.csv \
  --funding data/funding.csv --json
```

### CI/CD Integration

```yaml
# .github/workflows/backtest.yml
- name: Run backtest
  run: |
    python -m cryptobot.cli.main backtest \
      --strategy trend_following \
      --bars 1000 \
      --json > backtest_result.json
```