# Risk Management

## Overview

The risk management system provides pre-trade checks, position limits, kill switch, and portfolio-level controls.

## Risk Manager

```python
from cryptobot.risk.manager import RiskManager, RiskLimits

limits = RiskLimits(
    max_order_size_usd=10000,      # Max single order size
    min_order_size_usd=10,         # Min single order size
    max_position_usd=50000,        # Max position size per symbol
    max_total_exposure_pct=0.8,    # Max total portfolio exposure (80%)
    max_drawdown_pct=0.15,         # Max drawdown (15%)
    kill_switch_daily_loss_pct=0.05, # Daily loss limit (5%)
    max_leverage=3.0,              # Max leverage
    max_correlation=0.7,           # Max correlation between positions
)

risk_manager = RiskManager(limits=limits)
```

### Risk Check Result

```python
from cryptobot.risk.manager import RiskCheckResult

result = risk_manager.check_order(order, price=Decimal("50000"))

if result.passed:
    print("Order approved")
else:
    print(f"Rejected: {result.message}")
    print(f"Current: {result.current_value}, Limit: {result.limit_value}")
```

### RiskCheckResult

```python
@dataclass
class RiskCheckResult:
    passed: bool
    message: str = ""
    current_value: Decimal | None = None
    limit_value: Decimal | None = None

    def to_event(self, check_type: str, order: OrderEvent) -> RiskEvent:
        ...
```

### Risk Event

```python
from cryptobot.core.events import RiskEvent

event = RiskEvent(
    check_type="pre_trade",
    passed=False,
    message="Order above maximum size",
    current_value="55000",
    limit_value="50000",
    symbol="BTCUSDT",
    strategy="trend_following",
)
```

## Risk Checks

### 1. Kill Switch
```python
# Checked first - if active, all orders rejected
active, reason = kill_switch.evaluate(portfolio)
if active:
    return RiskCheckResult(False, reason)
```
- Triggers on daily loss limit exceeded
- Triggers on max drawdown exceeded
- Resets at UTC midnight

### 2. Order Size Limits
```python
notional = order.quantity * price
if notional < limits.min_order_size_usd:
    return RiskCheckResult(False, "Order below minimum size")
if notional > limits.max_order_size_usd:
    return RiskCheckResult(False, "Order above maximum size")
```

### 3. Position Limits
```python
# Max position per symbol
if position_value > limits.max_position_usd:
    return RiskCheckResult(False, "Position size exceeded")

# Max total exposure
total_exposure = used_margin + notional
if total_exposure / equity > limits.max_total_exposure_pct:
    return RiskCheckResult(False, "Total exposure limit exceeded")
```

### 4. Correlation Limits
```python
from cryptobot.risk.correlation import max_abs_correlation

max_corr = max_abs_correlation(positions)
if max_corr > limits.max_correlation:
    return RiskCheckResult(False, f"Correlation {max_corr} exceeds limit")
```

## Kill Switch

```python
from cryptobot.risk.kill_switch import KillSwitch

kill_switch = KillSwitch()

# Automatic evaluation
active, reason = kill_switch.evaluate(portfolio)

# Manual trigger
kill_switch.activate("Manual override")

# Reset
kill_switch.reset()
```

### Kill Switch Triggers

| Trigger | Condition | Action |
|---------|-----------|--------|
| Daily loss | `daily_pnl_pct <= -kill_switch_daily_loss_pct` | Reject all new orders |
| Max drawdown | `drawdown_pct >= max_drawdown_pct` | Reject all new orders |
| Manual | `kill_switch.activate("reason")` | Reject all new orders |

### Settings

```python
KillSwitchConfig:
    kill_switch_enabled: true
    kill_switch_daily_loss_pct: 0.05  # 5% daily loss
    max_drawdown_pct: 0.15            # 15% max drawdown
```

## Portfolio Manager

```python
from cryptobot.core.portfolio import PortfolioManager, PortfolioMode

pm = PortfolioManager(PortfolioMode.BACKTEST)
await pm.update_equity(Decimal("10000"))
```

### Portfolio State

```python
state = pm.get_state()

state.total_equity          # Total portfolio value
state.available_balance     # Available for new orders
state.used_margin           # Margin used by open positions
state.total_unrealized_pnl  # Unrealized P&L
state.total_realized_pnl    # Realized P&L
state.daily_pnl             # Daily P&L
state.peak_equity           # Peak equity (for drawdown)
state.max_drawdown          # Max drawdown from peak
state.open_positions        # Number of open positions
state.max_drawdown_pct      # Max drawdown percentage
state.daily_pnl_pct         # Daily P&L as % of equity
```

### Kill Switch Evaluation

```python
# Daily loss check
daily_loss_pct = portfolio.get_daily_pnl_pct()
if daily_loss_pct <= -settings.risk.kill_switch_daily_loss_pct:
    return True, f"Daily loss {daily_loss_pct:.2%} exceeds kill switch"

# Max drawdown check
drawdown_pct = portfolio.get_drawdown_pct()
if drawdown_pct >= settings.risk.max_drawdown_pct:
    return True, f"Max drawdown {drawdown_pct:.2%} exceeds limit"
```

## Position Sizing

```python
from cryptobot.risk.sizing import (
    fixed_fraction_size,
    kelly_size,
    volatility_target_size,
)
```

### Fixed Fraction
```python
size = fixed_fraction_size(
    equity=Decimal("10000"),
    risk_fraction=Decimal("0.02"),      # 2% risk per trade
    stop_loss_pct=Decimal("0.02"),      # 2% stop loss
)
# size = equity * risk_fraction / stop_loss_pct
# = 10000 * 0.02 / 0.02 = 10000
```

### Kelly Criterion
```python
size = kelly_size(
    win_rate=0.55,       # Historical win rate
    avg_win=Decimal("200"),
    avg_loss=Decimal("100"),
    max_fraction=0.25,   # Cap at 25% of equity
)
# Kelly = (p * avg_win - (1-p) * avg_loss) / avg_win
```

### Volatility Targeting
```python
size = volatility_target_size(
    equity=Decimal("10000"),
    target_vol=Decimal("0.15"),    # 15% annualized vol target
    asset_vol=Decimal("0.50"),     # Asset annualized vol
    max_position=Decimal("50000"),
)
# size = equity * target_vol / asset_vol
```

## Correlation Risk

```python
from cryptobot.risk.correlation import max_abs_correlation

# Correlation matrix of positions
corr_matrix = np.corrcoef(returns_matrix)

max_corr = max_abs_correlation(corr_matrix)

# Returns max absolute correlation between any two positions
# If > limit, reduce position sizes
```

## Risk Limits Configuration

```python
@dataclass
class RiskLimits:
    # Order size
    min_order_size_usd: Decimal = Decimal("10")
    max_order_size_usd: Decimal = Decimal("10000")
    
    # Position
    max_position_usd: Decimal = Decimal("50000")
    max_total_exposure_pct: Decimal = Decimal("0.80")
    
    # Drawdown
    max_drawdown_pct: Decimal = Decimal("0.15")
    kill_switch_daily_loss_pct: Decimal = Decimal("0.05")
    
    # Leverage
    max_leverage: Decimal = Decimal("3.0")
    
    # Correlation
    max_correlation: Decimal = Decimal("0.70")
    
    # Sizing
    max_position_pct: Decimal = Decimal("0.20")
    max_single_position_pct: Decimal = Decimal("0.10")
```

## Integration with Execution Engine

```python
from cryptobot.execution.engine import ExecutionEngine
from cryptobot.risk.manager import RiskManager

engine = ExecutionEngine(
    venue=venue,
    risk_manager=RiskManager(limits=limits),
)

# Order automatically checked before submission
filled = await engine.submit_order(order)
if filled.status == OrderStatus.REJECTED:
    print(f"Rejected: {filled.payload.get('error')}")
```

## Risk Events

```python
from cryptobot.core.events import RiskEvent

event = RiskEvent(
    check_type="pre_trade",
    passed=False,
    message="Order above maximum size",
    current_value="55000",
    limit_value="50000",
    symbol="BTCUSDT",
    strategy="trend_following",
)
```

## Monitoring Risk

```python
from cryptobot.monitoring.metrics import record_risk_check

# Record risk check
record_risk_check(
    check_type="pre_trade",
    passed=result.passed,
    check_name="position_size",
    symbol="BTCUSDT",
)

# Alert on rejection
if not result.passed:
    await alert_manager.fire(Alert(
        title="Order Rejected",
        message=f"Order rejected: {result.message}",
        severity=AlertSeverity.WARNING,
        category=AlertCategory.RISK,
    ))
```

## Configuration

### settings.yaml

```yaml
risk:
  max_order_size_usd: 10000
  min_order_size_usd: 10
  max_position_usd: 50000
  max_total_exposure_pct: 0.80
  max_drawdown_pct: 0.15
  kill_switch_daily_loss_pct: 0.05
  max_leverage: 3.0
  max_correlation: 0.70
  max_position_pct: 0.20
  max_single_position_pct: 0.10
  min_order_size_usd: 10
  kill_switch_enabled: true
  kill_switch_daily_loss_pct: 0.05
```

## Environment Variables

```bash
export RISK_MAX_POSITION_USD=50000
export RISK_MAX_DAILY_LOSS_PCT=0.05
export RISK_KILL_SWITCH_DAILY_LOSS_PCT=0.05
export RISK_MAX_CORRELATION=0.7
```