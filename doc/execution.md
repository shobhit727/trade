# Execution Engine

## Overview

The execution engine handles order routing, risk management, and venue connectivity.

## Core Components

### ExecutionEngine

```python
from cryptobot.execution.engine import ExecutionEngine, build_venue
from cryptobot.execution.venue.simulated import SimulatedVenue
from cryptobot.risk.manager import RiskManager

engine = ExecutionEngine(
    venue=SimulatedVenue(prices={"BTCUSDT": Decimal("50000")}),
    risk_manager=RiskManager(),
)
```

### Submit Order

```python
from cryptobot.core.events import OrderEvent, OrderType, OrderSide
from decimal import Decimal

order = OrderEvent(
    symbol="BTCUSDT",
    type=OrderType.MARKET,
    side=OrderSide.BUY,
    quantity=Decimal("1"),
    strategy="trend_following",
)

filled = await engine.submit_order(order)

if filled.status == OrderStatus.FILLED:
    print(f"Filled: {filled.filled_quantity} @ {filled.avg_fill_price}")
else:
    print(f"Rejected: {filled.payload.get('error')}")
```

### Cancel Order

```python
cancelled = await engine.cancel_order(order_id)
```

### Execution Flow

```
submit_order()
  → risk_manager.check_order()
  → If rejected: ORDER_REJECTED event
  → If router: router.route() → smart routing
  → Else: venue.submit_order()
  → If filled: ORDER_FILLED event
  → If rejected: ORDER_REJECTED event
```

## Venues

### SimulatedVenue

```python
from cryptobot.execution.venue.simulated import SimulatedVenue

venue = SimulatedVenue(
    prices={"BTCUSDT": Decimal("50000")},
    slippage_bps=Decimal("2"),     # 2 bps slippage
    commission_bps=Decimal("5"),   # 5 bps commission
    funding_rate=Decimal("0.0001"),
)

# Submit order
filled = await venue.submit_order(order)

# Get price
price = await venue.get_price("BTCUSDT")

# Cancel
await venue.cancel_order(order_id)
```

### SimulatedVenue Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `prices` | {} | Initial symbol prices |
| `slippage_bps` | 2 | Slippage in basis points |
| `commission_bps` | 5 | Commission in basis points |
| `funding_rate` | 0.0001 | Funding rate |

### Order Fill Logic

```python
# MARKET BUY
fill_price = mark * (1 + slippage_bps / 10000)

# MARKET SELL  
fill_price = mark * (1 - slippage_bps / 10000)

# Commission
commission = quantity * fill_price * commission_bps / 10000
```

### RealisticVenue

```python
from cryptobot.execution.venue.realistic import RealisticVenue

venue = RealisticVenue(
    prices={"BTCUSDT": Decimal("50000")},
    bid_quantity=Decimal("1.5"),
    ask_quantity=Decimal("1.5"),
    bid_queue=[QueuePosition(id="q1", size=Decimal("1"))],
    ask_queue=[QueuePosition(id="q2", size=Decimal("1"))],
)

# Limit fills execute at limit price (not mark); partial fills at qty × fill_ratio;
# fees charged on filled qty; adverse-selection guard wired via attach_to_engine.
```

### Transaction Cost Model

```python
from cryptobot.execution.costs import CostModel

costs = CostModel(
    spread_bps=Decimal("1"),
    taker_fee_bps=Decimal("2"),
    maker_fee_bps=Decimal("1"),
    slippage_bps=Decimal("1"),
    funding_bps=Decimal("0.5"),
    rebate_bps=Decimal("0"),
)
round_trip = costs.round_trip_bps(side=OrderSide.BUY)  # spread + fees + slippage
```

### BinanceVenue (Live/Testnet)

```python
from cryptobot.execution.venue.binance import BinanceVenue

venue = BinanceVenue(
    api_key="your_key",
    api_secret="your_secret",
    market_type="future",      # "spot" or "future"
    sandbox=True,              # Testnet
    rate_limit_ms=200,
    max_retries=3,
)

# Requires ccxt.async_support
# pip install ccxt
```

### Venue Interface

```python
from cryptobot.execution.venue.base import Venue

class Venue(ABC):
    @abstractmethod
    async def submit_order(self, order: OrderEvent) -> OrderEvent:
        ...
    
    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        ...
    
    @abstractmethod
    async def get_price(self, symbol: str) -> Decimal:
        ...
    
    @property
    @abstractmethod
    def name(self) -> str:
        ...
```

## Smart Order Router

```python
from cryptobot.execution.router import SmartOrderRouter, RouterConfig
from cryptobot.execution.venue.base import Venue

router = SmartOrderRouter(
    venues=[venue1, venue2, venue3],
    config=RouterConfig(
        max_slippage_bps=Decimal("20"),
        max_latency_ms=250.0,
        quote_timeout_s=1.0,
        max_child_venues=3,
    ),
    ranker=latency_aware_ranker,
    fee_overrides={"binance": Decimal("2")},
)
```

### Routing Flow

```
route(order)
  → quote_all(symbol)
  → pick(symbol, scores)  → best venue
  → submit_order(child)
  → if failed: fallback to next best
  → return RoutedOrder
```

### Router Config

```python
RouterConfig(
    max_slippage_bps=Decimal("20"),   # Max slippage tolerance
    max_latency_ms=250.0,             # Max venue latency
    quote_timeout_s=1.0,              # Quote timeout
    max_child_venues=3,               # Max venues for split
)
```

### Rankers

```python
from cryptobot.execution.router import (
    best_price_ranker,
    latency_aware_ranker,
    best_effort_ranker,
)

# Best price (lowest ask for buy, highest bid for sell)
best_price_ranker(symbol, scores)

# Latency-aware (speed + price)
latency_aware_ranker(symbol, scores)

# Best effort (price only)
best_effort_ranker(symbol, scores)
```

### Split and Route

```python
from cryptobot.execution.router import SmartOrderRouter, RouterConfig
from decimal import Decimal

router = SmartOrderRouter(venues=[v1, v2, v3])
routed = await router.split_and_route(
    parent=OrderEvent(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        quantity=Decimal("10"),
        type=OrderType.MARKET,
    ),
    ratio=[Decimal("1"), Decimal("1"), Decimal("1")],  # Equal split
)
```

### RoutedOrder

```python
@dataclass
class RoutedOrder:
    parent: OrderEvent
    children: list[OrderEvent] = field(default_factory=list)
    fills: list[OrderEvent] = field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        if not self.fills:
            return False
        total_child_qty = sum((c.quantity for c in self.children), Decimal("0"))
        total_filled_qty = sum((f.filled_quantity for f in self.fills), Decimal("0"))
        return total_child_qty >= self.parent.quantity and total_filled_qty >= self.parent.quantity
```

## Execution Algorithms

```python
from cryptobot.execution.algorithms import (
    TWAPAlgorithm,
    VWAPAlgorithm,
    POVAlgorithm,
    ImplementationShortfallAlgorithm,
    IcebergAlgorithm,
)
```

### TWAP (Time-Weighted Average Price)

```python
from cryptobot.execution.algorithms import TWAPAlgorithm, TWAPConfig

algo = TWAPAlgorithm(TWAPConfig(
    duration_minutes=60,
    num_slices=12,           # 12 slices over 60 min = 5 min each
    randomization_pct=0.2,   # ±20% randomization
))

# Usage
slices = algo.generate_slices(total_qty=Decimal("10"), start_time=now)
for slice in slices:
    await venue.submit_order(OrderEvent(..., quantity=slice.qty))
```

### VWAP (Volume-Weighted Average Price)

```python
from cryptobot.execution.algorithms import VWAPAlgorithm

algo = VWAPAlgorithm(VWAPConfig(
    volume_profile=[Decimal("10"), Decimal("20"), Decimal("30"), Decimal("40")],
    num_slices=4,
))
```

### POV (Percentage of Volume)

```python
from cryptobot.execution.algorithms import POVAlgorithm

algo = POVAlgorithm(POVConfig(
    participation_rate=Decimal("0.1"),  # 10% of volume
    max_participation=Decimal("0.2"),
    min_order_size=Decimal("0.01"),
))
```

### Implementation Shortfall (Perée-Clark)

```python
from cryptobot.execution.algorithms import ImplementationShortfallAlgorithm

algo = ImplementationShortfallAlgorithm(ISConfig(
    risk_aversion=Decimal("1.0"),
    volatility=Decimal("0.02"),
    urgency=Decimal("0.5"),
))
```

### Iceberg

```python
from cryptobot.execution.algorithms import IcebergAlgorithm, IcebergConfig

algo = IcebergAlgorithm(IcebergConfig(
    display_quantity=Decimal("1"),    # Visible qty
    randomization=Decimal("0.2"),     # ±20% randomization
))
```

### Liquidity Seek

```python
from cryptobot.execution.algorithms import liquidity_seek_slices

slices = liquidity_seek_slices(
    total_qty=Decimal("10"),
    levels=[
        (Decimal("100"), Decimal("5")),
        (Decimal("101"), Decimal("3")),
        (Decimal("102"), Decimal("2")),
    ],
    min_slice=Decimal("0.1"),
)
```

### Arrival Price Benchmark

```python
from cryptobot.execution.algorithms import arrival_price_benchmark

benchmark = arrival_price_benchmark(
    arrival_price=Decimal("100"),
    executed_price=Decimal("100.05"),
    fee_bps=Decimal("5"),
)
```

### Slicer Factory

```python
from cryptobot.execution.algorithms import slicer_for

slicer = slicer_for("twap")
slices = await slicer.generate_slices(total_qty=Decimal("10"), ...)
```

## Adverse Selection Guard

```python
from cryptobot.execution.adverse_selection import (
    AdverseSelectionGuard,
    TopOfBook,
)

guard = AdverseSelectionGuard(
    mid_move_threshold_bps=10,
    spread_widen_threshold_bps=5,
    toxicity_threshold=0.7,
)

# Register order
guard.register(order, TopOfBook(bid=100, ask=101, mid=100.5))

# Check before fill
should_cancel = guard.step(top_of_book)
if should_cancel:
    await engine.cancel_order(order.order_id)
```

### Adverse Selection Logic

| Trigger | Condition | Action |
|---------|-----------|--------|
| Mid move | `|mid - last_mid| > threshold` | Cancel order |
| Spread widen | `spread > last_spread * (1 + threshold)` | Cancel order |
| Toxicity spike | `toxicity > threshold` | Cancel order |

## Custom Venue

```python
from cryptobot.execution.venue.base import Venue
from cryptobot.core.events import OrderEvent, OrderStatus

class CustomVenue(Venue):
    def __init__(self, api_client):
        self.client = api_client
        self.name = "custom"
    
    async def submit_order(self, order: OrderEvent) -> OrderEvent:
        # Your exchange API call
        response = await self.client.place_order(...)
        
        order.status = OrderStatus.FILLED
        order.filled_quantity = order.quantity
        order.avg_fill_price = Decimal(str(response["price"]))
        order.commission = Decimal(str(response["fee"]))
        order.__post_init__()
        return order
    
    async def cancel_order(self, order_id: str) -> bool:
        return await self.client.cancel_order(order_id)
    
    async def get_price(self, symbol: str) -> Decimal:
        ticker = await self.client.get_ticker(symbol)
        return Decimal(str(ticker["last"]))

    @property
    def name(self) -> str:
        return "custom_venue"
```

## Configuration

### Execution Settings

```yaml
# configs/base.yaml
execution:
  mode: paper              # paper, backtest, binance, testnet
  venue: simulated         # simulated, binance
  max_slippage_bps: 20
  max_latency_ms: 250
  quote_timeout_s: 1.0
  max_retries: 3
  rate_limit_ms: 200
```

### Environment Variables

```bash
export EXECUTION_MODE=paper
export EXECUTION_VENUE=simulated
export BINANCE_API_KEY=your_key
export BINANCE_API_SECRET=your_secret
export EXECUTION_MAX_SLIPPAGE_BPS=20
export EXECUTION_MAX_LATENCY_MS=250
```

## Monitoring Execution

```python
from cryptobot.monitoring.metrics import (
    record_routing_decision,
    record_execution_latency,
    record_fill,
)

# Record routing decision
record_routing_decision(
    venue="binance",
    symbol="BTCUSDT",
    action="selected",
)

# Record execution latency
record_execution_latency(
    venue="binance",
    symbol="BTCUSDT",
    order_type="MARKET",
    latency=0.045,
)

# Record fill
record_fill(
    symbol="BTCUSDT",
    side="BUY",
    quantity=Decimal("1"),
    price=Decimal("50000"),
    commission=Decimal("2.50"),
)
```

## Error Handling

```python
try:
    filled = await engine.submit_order(order)
except Exception as exc:
    logger.error(f"Execution failed: {exc}")
    # Handle error
    return OrderEvent(status=OrderStatus.REJECTED, ...)
```

### Common Errors

| Error | Cause | Resolution |
|-------|-------|------------|
| `REJECTED: Order below minimum size` | Notional < min_order_size | Increase quantity |
| `REJECTED: Order above maximum size` | Notional > max_order_size | Reduce quantity |
| `REJECTED: Max drawdown exceeded` | Portfolio drawdown > limit | Reduce positions |
| `REJECTED: ccxt not installed` | Live Binance needs ccxt | `pip install ccxt` |
| `Venue connection failed` | Network/API issue | Check connectivity, retry |

## Testing

```python
from cryptobot.execution.venue.simulated import SimulatedVenue

# Unit test
venue = SimulatedVenue(prices={"BTCUSDT": Decimal("50000")}, slippage_bps=0)
filled = await venue.submit_order(order)
assert filled.status == OrderStatus.FILLED
assert filled.avg_fill_price == Decimal("50000")
```

## Files

- `src/cryptobot/execution/engine.py` - ExecutionEngine
- `src/cryptobot/execution/router.py` - SmartOrderRouter
- `src/cryptobot/execution/venue/base.py` - Venue ABC
- `src/cryptobot/execution/venue/simulated.py` - SimulatedVenue
- `src/cryptobot/execution/venue/realistic.py` - RealisticVenue (seeded book, partial fills, adverse selection)
- `src/cryptobot/execution/venue/binance.py` - BinanceVenue
- `src/cryptobot/execution/costs.py` - Transaction cost model (spread/fees/slippage/funding/rebates)
- `src/cryptobot/execution/algorithms.py` - Execution algorithms
- `src/cryptobot/execution/adverse_selection.py` - AdverseSelectionGuard