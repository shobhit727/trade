# Cryptobot Backtesting Guide

## Overview

The Cryptobot backtesting engine provides a comprehensive event-driven backtesting framework for testing trading strategies against historical or synthetic market data.

## Quick Start

### CLI Usage

```bash
# Run a basic backtest with synthetic data
python -m cryptobot.cli.main backtest \
  --strategy trend_following \
  --bars 500 \
  --symbol BTCUSDT \
  --timeframe 1m

# Run with CSV data
python -m cryptobot.cli.main backtest \
  --strategy mean_reversion \
  --bars 1000 \
  --source csv \
  --path ./data/btcusdt_1m.csv \
  --symbol BTCUSDT \
  --timeframe 1m
```

### Programmatic Usage

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

## CLI Reference

### Required Arguments

| Option | Description |
|--------|-------------|
| `--strategy` | Strategy name (required) |

### Optional Arguments

| Option | Default | Description |
|--------|---------|-------------|
| `--bars` | 200 | Number of synthetic bars to generate |
| `--source` | synthetic | Data source: `synthetic`, `csv`, `parquet`, `timescale` |
| `--path` | - | Path to data file (required for csv/parquet) |
| `--symbol` | BTCUSDT | Trading symbol |
| `--timeframe` | 1m | Timeframe (1m, 5m, 15m, 1h, 4h, 1d) |
| `--initial-capital` | 10000 | Initial capital |
| `--commission-bps` | 5 | Commission in basis points |
| `--slippage-bps` | 3 | Slippage in basis points |
| `--json` | false | Output results as JSON |
| `--start` | - | Start date (YYYY-MM-DD) for timescale |
| `--end` | - | End date (YYYY-MM-DD) for timescale |
| `--validate` | false | Run walk-forward validation |

## Supported Strategies

| Strategy | Module | Key Parameters |
|----------|--------|----------------|
| `trend_following` | `TrendFollowingStrategy` | ema_fast, ema_slow, adx_threshold, atr_period, atr_mult, risk_per_trade |
| `mean_reversion` | `MeanReversionStrategy` | bb_period, bb_std, rsi_period, rsi_overbought, rsi_oversold |
| `market_making` | `MarketMakingStrategy` | gamma, sigma, kappa, A, max_inventory, quote_step_bps, min_quote_size |
| `stat_arb` | `StatArbStrategy` | lookback, z_entry, z_exit, z_stop, hedge_ratio, min_correlation |
| `funding_arb` | `FundingArbStrategy` | min_funding_rate, basis_entry_bps, basis_exit_bps, hedge_leverage |

### Strategy Configuration Details

#### Trend Following
```python
TrendFollowingConfig(
    ema_fast=12,           # Fast EMA period
    ema_slow=26,           # Slow EMA period
    adx_threshold=25,      # ADX trend strength threshold
    atr_period=14,         # ATR period for trailing stop
    atr_mult=2.0,          # ATR multiplier for trailing stop
    risk_per_trade=0.02,   # Risk per trade (fraction of equity)
)
```

#### Mean Reversion
```python
MeanReversionConfig(
    bb_period=20,          # Bollinger Bands period
    bb_std=2.0,            # BB standard deviation multiplier
    rsi_period=14,         # RSI period
    rsi_overbought=70,     # RSI overbought threshold
    rsi_oversold=30,       # RSI oversold threshold
    risk_per_trade=0.02,
)
```

#### Market Making (Avellaneda-Stoikov)
```python
MarketMakingConfig(
    gamma=0.5,             # Risk aversion
    sigma=0.01,            # Volatility estimate
    kappa=1.5,             # Order book depth parameter
    A=0.025,               # Base spread factor
    max_inventory=Decimal("5"),   # Max inventory
    quote_step_bps=1.0,    # Minimum quote step in bps
    min_quote_size=Decimal("0.001"),
    cancel_threshold_bps=5.0,
    risk_budget=0.02,
)
```

#### Statistical Arbitrage
```python
StatArbConfig(
    lookback=60,           # Rolling window for hedge ratio
    z_entry=2.0,           # Z-score entry threshold
    z_exit=0.4,            # Z-score exit threshold
    z_stop=3.5,            # Z-score stop loss
    quantity=Decimal("0.1"),
    fee_bps=5.0,
    min_correlation=0.3,
    half_life_bars=24,
)
```

#### Funding Arbitrage
```python
FundingArbConfig(
    min_funding_rate=0.0001,    # Min funding rate for entry
    max_funding_rate=0.005,     # Max funding rate cap
    basis_entry_bps=5.0,        # Basis entry threshold (bps)
    basis_exit_bps=1.5,         # Basis exit threshold (bps)
    hedge_leverage=Decimal("1"),
    quantity=Decimal("1"),
    fee_bps=5.0,
)
```

## Data Sources

### Synthetic (Default)
Generates realistic OHLCV data using geometric Brownian motion with volatility clustering.

```bash
python -m cryptobot.cli.main backtest --strategy trend_following --bars 1000
```

### CSV
```bash
python -m cryptobot.cli.main backtest \
  --strategy trend_following \
  --source csv \
  --path ./data/btcusdt_1m.csv
```

CSV format must have columns: `timestamp`, `open`, `high`, `low`, `close`, `volume`

### Parquet
```bash
python -m cryptobot.cli.main backtest \
  --strategy trend_following \
  --source parquet \
  --path ./data/btcusdt.parquet
```

### TimescaleDB
```bash
python -m cryptobot.cli.main backtest \
  --strategy trend_following \
  --source timescale \
  --symbol BTCUSDT \
  --timeframe 1m \
  --start 2024-01-01 \
  --end 2024-02-01
```

## Docker

```bash
# Run tests
docker compose --profile test run --rm cryptobot-test

# Run backtest
docker compose --profile backtest run --rm cryptobot-backtest \
  python -m cryptobot.cli.main backtest --strategy trend_following --bars 500
```

## Backtest Results

The backtest returns a `BacktestResult` object with:

| Field | Description |
|-------|-------------|
| `total_return` | Total return percentage |
| `Sharpe_ratio` | Sharpe ratio (annualized) |
| `Sortino_ratio` | Sortino ratio |
| `max_drawdown` | Maximum drawdown percentage |
| `win_rate` | Win rate percentage |
| `profit_factor` | Gross profit / gross loss |
| `total_trades` | Number of trades |
| `winning_trades` | Number of winning trades |
| `losing_trades` | Number of losing trades |
| `avg_win` | Average winning trade |
| `avg_loss` | Average losing trade |
| `equity_curve` | List of (timestamp, equity) tuples |
| `trades` | List of TradeRecord objects |

## Advanced Configuration

### Custom Strategy Config

```python
from cryptobot.strategies.trend_following import TrendFollowingConfig

config = TrendFollowingConfig(
    ema_fast=10,
    ema_slow=30,
    adx_threshold=20,
    atr_period=14,
    atr_mult=2.0,
    risk_per_trade=0.02,
)
strategy = TrendFollowingStrategy(config)
```

### Custom Backtest Parameters

```python
result = await run_backtest(
    strategy=strategy,
    symbol="ETHUSDT",
    timeframe="5m",
    bars=2000,
    initial_capital=50000,
    commission_bps=3,
    slippage_bps=2,
    funding_included=True,
)
```

## Output Formats

### Text (Default)
```
Results: final_equity=12345.67 total_return=23.46% max_dd=5.23% sharpe=1.87 trades=42
```

### JSON
```bash
python -m cryptobot.cli.main backtest \
  --strategy trend_following \
  --json
```

Output:
```json
{
  "start_time": "2024-01-01T00:00:00",
  "end_time": "2024-01-31T23:59:59",
  "initial_capital": "10000.0",
  "final_equity": "12345.67",
  "total_return": "23.46",
  "max_drawdown": "5.23",
  "sharpe": "1.87",
  "sortino": "2.15",
  "win_rate": "58.33",
  "profit_factor": "2.34",
  "total_trades": 42,
  "winning_trades": 25,
  "losing_trades": 17,
  "avg_win": "125.50",
  "avg_loss": "-89.25",
  "equity_curve": [[...], [...]]
}
```

## Validation Framework

### Walk-Forward Analysis
```python
from cryptobot.backtest.validation import run_validation, walk_forward_returns

# Run validation on returns series
report = run_validation(
    returns=returns_series,
    n_splits=5,
    n_permutations=1000,
)
print(f"Walk-forward passed: {report['walk_forward']['passed']}")
print(f"Monte Carlo passed: {report['monte_carlo']['passed']}")
print(f"Deflated Sharpe passed: {report['deflated_sharpe']['passed']}")
```

### Monte Carlo Permutation Testing
```python
from cryptobot.backtest.validation import monte_carlo_significance

result = monte_carlo_significance(
    returns=returns,
    n_permutations=1000,
)
print(f"P-value: {result['p_value']}")
print(f"Observed Sharpe: {result['observed_sharpe']}")
```

### Deflated Sharpe Ratio
```python
from cryptobot.backtest.validation import deflated_sharpe

result = deflated_sharpe(
    returns=returns,
    n_trials=1,
    benchmark_sharpe=0.0,
)
print(f"Probabilistic Sharpe Ratio: {result['probabilistic_sharpe_ratio']}")
```

## Risk Management in Backtesting

The backtest engine includes built-in risk management:

- **Kill Switch**: Daily loss limit and max drawdown limits
- **Position Limits**: Max position size, max total exposure
- **Kill Switch**: Daily loss limit triggers full position liquidation
- **Position Sizing**: Fixed fraction, volatility targeting, Kelly criterion

```python
from cryptobot.risk.manager import RiskManager, RiskLimits
from cryptobot.risk.kill_switch import KillSwitch

limits = RiskLimits(
    max_order_size_usd=10000,
    min_order_size_usd=10,
    max_position_usd=50000,
    max_total_exposure_pct=0.8,
    max_drawdown_pct=0.15,
    kill_switch_daily_loss_pct=0.05,
)
```

## Execution Engine

The backtest engine uses a simulated venue with configurable slippage and commission:

```python
venue = SimulatedVenue(
    prices={"BTCUSDT": Decimal("50000")},
    slippage_bps=Decimal("2"),    # 2 bps slippage
    commission_bps=Decimal("5"),  # 5 bps commission
)
```

### Smart Order Router
```python
from cryptobot.execution.router import SmartOrderRouter, RouterConfig

router = SmartOrderRouter(
    venues=[venue1, venue2],
    config=RouterConfig(
        max_slippage_bps=Decimal("20"),
        max_latency_ms=250.0,
    ),
    ranker=latency_aware_ranker,
)
```

## Monitoring & Observability

### Metrics Collection
```python
from cryptobot.monitoring.metrics import (
    record_order, record_fill, record_pnl,
    record_execution_latency, record_venue_quote_latency,
)

record_order(strategy="trend", symbol="BTCUSDT", side="BUY", type="MARKET")
record_fill(symbol="BTCUSDT", side="BUY", quantity=1, price=50000, fees=5)
```

### Health Checks
```python
from cryptobot.monitoring.health import HealthMonitor, HealthCheck, ComponentType

monitor = HealthMonitor(check_interval=30.0)
monitor.register_check(HealthCheck(
    name="exchange_ping",
    component=ComponentType.EXCHANGE,
    check_fn=lambda: exchange.get_server_time(),
    interval_seconds=30.0,
))
```

## ML Strategy Usage

```python
from cryptobot.strategies.ml_strategy import MLStrategy, MLStrategyConfig

config = MLStrategyConfig(
    direction_config=DirectionConfig(threshold=0.55, horizon=5),
    retrain_interval=100,
    min_train_samples=500,
)
strategy = MLStrategy(config)

# Train on historical data
strategy.fit(historical_features, historical_labels)

# Run backtest
result = await run_backtest(strategy=strategy, ...)
```

## Custom Data Sources

### Custom Data Loader
```python
from cryptobot.backtest.data import load_bars

# Load from custom source
bars = await load_bars(
    source="custom",
    path="/path/to/data",
    symbol="BTCUSDT",
    timeframe="1h",
    start=datetime(2024, 1, 1),
    end=datetime(2024, 12, 31),
)
```

### Custom OhlcvDataset
```python
from cryptobot.backtest.data import OhlcvDataset, OhlcvBar

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

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "No valid price" | Check data source has valid price columns |
| "Kill switch triggered" | Reduce position size or increase limits |
| "No fills" | Check slippage/commission settings, ensure venue is connected |
| "Validation failed" | Increase bars or check strategy logic |
| "Order rejected" | Check risk limits (min/max size, exposure) |
| "Module not found" | Run `pip install -e .` from project root |

## Performance Tips

1. **Use sufficient bars**: Minimum 200 bars for meaningful statistics
2. **Test multiple timeframes**: Strategy behavior varies by timeframe
3. **Include costs**: Always set realistic commission and slippage
4. **Walk-forward validation**: Use `run_validation()` for robust testing
5. **Monte Carlo testing**: Use permutation tests to verify significance
6. **Profile memory**: Large bar counts may need generator-based streaming

## Files Reference

- `src/cryptobot/backtest/engine.py` - Core backtest engine
- `src/cryptobot/backtest/runner.py` - High-level runner API
- `src/cryptobot/backtest/data.py` - Data loading utilities
- `src/cryptobot/backtest/validation.py` - Statistical validation
- `src/cryptobot/backtest/reporting.py` - HTML/JSON reporting
- `src/cryptobot/backtest/simulator.py` - Fill simulation
- `src/cryptobot/cli/main.py` - CLI entry point
- `src/cryptobot/strategies/*.py` - Strategy implementations
- `src/cryptobot/ml/models/*.py` - ML models
- `src/cryptobot/execution/*.py` - Execution engine
- `src/cryptobot/risk/*.py` - Risk management
- `src/cryptobot/monitoring/*.py` - Monitoring/alerting

## FAQ

**Q: How do I run a backtest on multiple symbols?**
A: Run separate backtests per symbol, or implement a multi-symbol strategy that subscribes to multiple symbols.

**Q: How do I use real historical data?**
A: Use `--source csv` with a CSV file, `--source parquet`, or `--source timescale` with TimescaleDB.

**Q: How do I add a custom strategy?**
A: Subclass `BaseStrategy`, implement `on_event()` and `generate_signals()`, register in `strategies/registry.py`.

**Q: How do I run optimization?**
A: Use Optuna or grid search over strategy config parameters, running multiple backtests.

**Q: Why are my results different from live trading?**
A: Backtest uses simplified fill model (no partial fills, no latency, no adverse selection). Use `adverse_selection` module for more realistic fills.

**Q: How to run multi-strategy backtest?**
A: Create multiple strategies, each with their own `PortfolioManager` allocation, or use the `ExecutionEngine` with multiple strategies.

**Q: What is the minimum data required?**
A: At least 200 bars for statistical significance. 500+ recommended for walk-forward validation.

## Common Pitfalls

1. **Look-ahead bias**: Ensure features only use past data (use `walk_forward_score`)
2. **Overfitting**: Validate on out-of-sample data with walk-forward
3. **Ignoring costs**: Always include realistic commission + slippage
4. **Survivorship bias**: Test on delisted symbols if possible
5. **Data snooping**: Don't tune parameters on full dataset
5. **Overfitting to synthetic data**: Validate on real historical data

## Migration Guide

### From v0.1 to v0.2
- `BacktestEngine.run()` now requires `await engine.initialize()` first
- `OrderEvent` requires `strategy` field
- `RiskManager.check_order()` now requires `price` parameter

### Breaking Changes
- `SimulatedVenue` now requires explicit `slippage_bps` and `commission_bps`
- `SmartOrderRouter` requires explicit `RouterConfig`
- `HealthMonitor.is_healthy()` added (was missing)
- `ComponentType.RISK` and `ComponentType.STRATEGY` added as aliases

## Support

- GitHub Issues: https://github.com/shobhit727/trade/issues
- Documentation: See `docs/` folder
- Architecture: See `PROJECT_MEMORY/` for design decisions