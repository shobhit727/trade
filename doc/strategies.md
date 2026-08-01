# Strategies

## Supported Strategies

| Strategy | Class | Description |
|----------|-------|-------------|
| `trend_following` | `TrendFollowingStrategy` | EMA crossover with ADX filter and ATR trailing stop |
| `mean_reversion` | `MeanReversionStrategy` | Bollinger Bands + RSI mean reversion |
| `market_making` | `MarketMakingStrategy` | Avellaneda-Stoikov optimal market making |
| `stat_arb` | `StatArbStrategy` | Pairs trading with hedge ratio and z-score |
| `funding_arb` | `FundingArbStrategy` | Spot/perp basis + funding rate arbitrage |

## Strategy Configuration

### Trend Following
```python
from cryptobot.strategies.trend_following import TrendFollowingStrategy, TrendFollowingConfig

config = TrendFollowingConfig(
    ema_fast=12,           # Fast EMA period
    ema_slow=26,           # Slow EMA period
    adx_threshold=25,      # ADX trend strength threshold
    atr_period=14,         # ATR period for trailing stop
    atr_mult=2.0,          # ATR multiplier for trailing stop
    risk_per_trade=0.02,   # Risk per trade (fraction of equity)
)
strategy = TrendFollowingStrategy(config)
```

**Logic**: 
- Long when fast EMA > slow EMA AND ADX > threshold
- Short when fast EMA < slow EMA AND ADX > threshold
- Trailing stop at ATR × multiplier from entry

### Mean Reversion
```python
from cryptobot.strategies.mean_reversion import MeanReversionStrategy, MeanReversionConfig

config = MeanReversionConfig(
    bb_period=20,          # Bollinger Bands period
    bb_std=2.0,            # BB standard deviation multiplier
    rsi_period=14,         # RSI period
    rsi_overbought=70,     # RSI overbought threshold
    rsi_oversold=30,       # RSI oversold threshold
    risk_per_trade=0.02,
)
strategy = MeanReversionStrategy(config)
```

**Logic**:
- Long when price < lower BB AND RSI < oversold
- Short when price > upper BB AND RSI > overbought
- Exit at middle BB or RSI 50

### Market Making (Avellaneda-Stoikov)
```python
from cryptobot.strategies.market_making import MarketMakingStrategy, MarketMakingConfig

config = MarketMakingConfig(
    gamma=0.5,             # Risk aversion
    sigma=0.01,            # Volatility estimate
    kappa=1.5,             # Order book depth parameter
    A=0.025,               # Base spread factor
    max_inventory=Decimal("5"),
    quote_step_bps=1.0,    # Minimum quote step in bps
    min_quote_size=Decimal("0.001"),
    cancel_threshold_bps=5.0,
    risk_budget=0.02,
)
strategy = MarketMakingStrategy(config)
```

**Logic**: 
- Optimal spread = γσ²T + (2/γ)ln(1+γ/κ)
- Reservation price = mid - inventory × γσ²T
- Skew quotes based on inventory

### Statistical Arbitrage
```python
from cryptobot.strategies.stat_arb import StatArbStrategy, StatArbConfig

config = StatArbConfig(
    lookback=60,           # Rolling window for hedge ratio
    z_entry=2.0,           # Z-score entry threshold
    z_exit=0.4,            # Z-score exit threshold
    z_stop=3.5,            # Z-score stop loss
    quantity=Decimal("0.1"),
    fee_bps=5.0,
    min_correlation=0.3,
    half_life_bars=24,
)
strategy = StatArbStrategy(config)
```

**Logic**:
- Rolling OLS hedge ratio on lookback window
- Spread = price_a - hedge_ratio × price_b
- Z-score = (spread - mean) / std
- Enter at ±z_entry, exit at ±z_exit, stop at ±z_stop

### Funding Arbitrage
```python
from cryptobot.strategies.funding_arb import FundingArbStrategy, FundingArbConfig

config = FundingArbConfig(
    min_funding_rate=0.0001,
    max_funding_rate=0.005,
    basis_entry_bps=5.0,
    basis_exit_bps=1.5,
    hedge_leverage=Decimal("1"),
    quantity=Decimal("1"),
    fee_bps=5.0,
)
strategy = FundingArbStrategy(config)
```

**Logic**:
- Long spot + short perp when basis > entry AND funding > min
- Exit when basis < exit OR funding < min
- Hedge delta with perp position

## ML Strategy
```python
from cryptobot.strategies.ml_strategy import MLStrategy, MLStrategyConfig
from cryptobot.ml.models.direction import DirectionConfig

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