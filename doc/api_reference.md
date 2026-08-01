# API Reference

## Core Modules

### cryptobot.backtest

#### `run_backtest`

```python
async def run_backtest(
    strategy: BaseStrategy,
    symbol: str = "BTCUSDT",
    timeframe: str = "1m",
    bars: int = 200,
    initial_capital: float = 10000.0,
    commission_bps: int = 5,
    slippage_bps: int = 3,
    funding_included: bool = True,
    data_source: str = "synthetic",
    data_path: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> BacktestResult
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `strategy` | `BaseStrategy` | required | Strategy instance |
| `symbol` | `str` | "BTCUSDT" | Trading symbol |
| `timeframe` | `str` | "1m" | Timeframe |
| `bars` | `int` | 200 | Number of bars |
| `initial_capital` | `float` | 10000.0 | Starting capital |
| `commission_bps` | `int` | 5 | Commission (bps) |
| `slippage_bps` | `int` | 3 | Slippage (bps) |
| `funding_included` | `bool` | True | Include funding |
| `data_source` | `str` | "synthetic" | Data source |
| `data_path` | `str \| None` | None | Data file path |
| `start` | `datetime \| None` | None | Start date |
| `end` | `datetime \| None` | None | End date |

**Returns:** `BacktestResult`

#### `BacktestResult`

```python
@dataclass
class BacktestResult:
    start_time: datetime
    end_time: datetime
    initial_capital: Decimal
    final_equity: Decimal
    total_return: Decimal
    max_drawdown: Decimal
    Sharpe_ratio: Decimal
    Sortino_ratio: Decimal
    win_rate: Decimal
    profit_factor: Decimal
    total_trades: int
    winning_trades: int
    losing_trades: int
    avg_win: Decimal
    avg_loss: Decimal
    equity_curve: list[tuple[datetime, Decimal]]
    trades: list[TradeRecord]
```

#### `run_validation`

```python
def run_validation(
    returns: Sequence[float],
    n_splits: int = 5,
    n_permutations: int = 1000,
    n_trials: int = 1,
) -> dict[str, Any]
```

### `cryptobot.backtest.engine`

#### `BacktestEngine`

```python
class BacktestEngine:
    def __init__(
        self,
        start_time: datetime,
        end_time: datetime,
        initial_capital: float,
        commission_bps: int = 5,
        slippage_bps: int = 3,
        funding_included: bool = True,
    )

    async def initialize(self) -> None
    async def run(self, data_stream: AsyncIterator[Event]) -> BacktestResult
    def get_trades(self) -> list[TradeRecord]
    def get_positions(self) -> dict[str, Position]
```

#### `BacktestResult` (same as above)

#### `TradeRecord`

```python
@dataclass
class TradeRecord:
    symbol: str
    entry_time: datetime
    exit_time: datetime
    entry_price: Decimal
    exit_price: Decimal
    quantity: Decimal
    side: str
    pnl: Decimal
    pnl_pct: Decimal
    fees: Decimal
    strategy: str
```

#### `generate_synthetic_ohlcv`

```python
def generate_synthetic_ohlcv(
    start: datetime,
    n_bars: int,
    freq_minutes: int,
    seed: int = 42,
    drift: float = 0.0001,
    volatility: float = 0.02,
    jump_prob: float = 0.001,
    jump_size: float = 0.03,
) -> list[OhlcvBar]
```

### `cryptobot.backtest.data`

#### `load_bars`

```python
async def load_bars(
    source: str,
    path: str | Path | None = None,
    symbol: str = "BTCUSDT",
    start: datetime | None = None,
    end: datetime | None = None,
    timeframe: str = "15m",
) -> OhlcvDataset
```

#### `OhlcvDataset`

```python
@dataclass
class OhlcvDataset:
    bars: list[OhlcvBar] = field(default_factory=list)
    symbol: str = "BTCUSDT"
    source: str = "memory"

    def __len__(self) -> int
    def __iter__(self):
    def filter_range(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> OhlcvDataset
    def to_runner_bars(self) -> list[OhlcvBar]
```

#### `OhlcvBar`

```python
@dataclass
class OhlcvBar:
    symbol: str
    interval: str
    open_time: datetime
    close_time: datetime
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal
    volume: Decimal
    trades: int
    is_closed: bool = True
```

### `cryptobot.backtest.validation`

#### `walk_forward_returns`

```python
def walk_forward_returns(
    returns: Sequence[float],
    n_splits: int = 5,
    embargo: float = 0.01,
) -> dict[str, Any]
```

#### `monte_carlo_significance`

```python
def monte_carlo_significance(
    returns: Sequence[float],
    n_permutations: int = 1000,
) -> dict[str, Any]
```

#### `deflated_sharpe`

```python
def deflated_sharpe(
    returns: Sequence[float],
    n_trials: int = 1,
    benchmark_sharpe: float = 0.0,
) -> dict[str, Any]
```

#### `run_validation`

```python
def run_validation(
    returns: Sequence[float],
    n_splits: int = 5,
    n_permutations: int = 1000,
    n_trials: int = 1,
) -> dict[str, Any]
```

### `cryptobot.backtest.reporting`

#### `generate_report`

```python
def generate_report(
    result: BacktestResult,
    strategy_name: str = "",
    output_format: str = "html",
) -> str
```

## Core Modules

### `cryptobot.core.events`

#### `Event`

```python
@dataclass
class Event:
    id: str = field(default_factory=lambda: str(uuid4()))
    type: EventType
    timestamp: datetime = field(default_factory=datetime.utcnow)
    source: str = ""
    correlation_id: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
```

#### `EventType`

```python
class EventType(StrEnum):
    KLINE = "kline"
    TICKER = "ticker"
    TRADE = "trade"
    ORDER_BOOK = "orderbook"
    FUNDING_RATE = "funding_rate"
    MARK_PRICE = "mark_price"
    ORDER_NEW = "order_new"
    ORDER_FILLED = "order_filled"
    ORDER_CANCELED = "order_canceled"
    ORDER_REJECTED = "order_rejected"
    POSITION_UPDATE = "position_update"
    PNL_UPDATE = "pnl_update"
    HEARTBEAT = "heartbeat"
    SYSTEM = "system"
    RISK = "risk"
    ML = "ml"
```

#### `OrderEvent`

```python
@dataclass
class OrderEvent(Event):
    order_id: str = ""
    client_order_id: str = ""
    symbol: str = ""
    side: OrderSide = OrderSide.BUY
    type: OrderType = OrderType.MARKET
    quantity: Decimal = Decimal("0")
    price: Decimal | None = None
    stop_price: Decimal | None = None
    status: OrderStatus = OrderStatus.NEW
    filled_quantity: Decimal = Decimal("0")
    avg_fill_price: Decimal | None = None
    commission: Decimal = Decimal("0")
    commission_asset: str = ""
    time_in_force: TimeInForce = TimeInForce.GTC
    reduce_only: bool = False
    position_side: PositionSide = PositionSide.BOTH
    strategy: str = ""
```

#### Enums

```python
class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"

class OrderType(StrEnum):
    MARKET = "market"
    LIMIT = "limit"
    STOP_LOSS = "stop_market"
    STOP_LOSS_LIMIT = "stop"
    TAKE_PROFIT = "take_profit_market"
    TAKE_PROFIT_LIMIT = "take_profit"
    LIMIT_MAKER = "limit_maker"

class OrderStatus(StrEnum):
    NEW = "new"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"
    EXPIRED = "expired"

class TimeInForce(StrEnum):
    GTC = "GTC"
    IOC = "IOC"
    FOK = "FOK"
    GTX = "GTX"
```

### `cryptobot.core.bus`

#### `EventBus`

```python
class EventBus:
    def subscribe(self, event_type: EventType, handler: Callable) -> str
    def unsubscribe(self, subscription_id: str) -> bool
    async def publish(self, event: Event) -> None
    async def publish_batch(self, events: list[Event]) -> None
    def get_history(self, event_type: EventType | None = None, limit: int = 100) -> list[Event]
    async def replay(self, event_type: EventType, handler: Callable, limit: int = 1000) -> None
    def close(self) -> None
```

### `cryptobot.core.clock`

#### `Clock`

```python
class Clock(ABC):
    @property
    def mode(self) -> ClockMode: ...
    def now(self) -> datetime: ...
    async def sleep(self, seconds: float): ...
    async def sleep_until(self, target: datetime): ...
```

#### `ClockMode`

```python
class ClockMode(StrEnum):
    REALTIME = "realtime"
    SIMULATED = "simulated"
    ACCELERATED = "accelerated"
```

#### `RealtimeClock`

```python
class RealtimeClock(Clock):
    def __init__(self, timezone: str = "UTC")
    @property
    def mode(self) -> ClockMode: ...
    def now(self) -> datetime: ...
    async def sleep(self, seconds: float): ...
    async def sleep_until(self, target: datetime): ...
```

#### `SimulatedClock`

```python
class SimulatedClock(Clock):
    def __init__(
        self,
        start_time: datetime,
        end_time: datetime | None = None,
        speed_factor: float = 1.0,
    )
    @property
    def mode(self) -> ClockMode: ...
    def now(self) -> datetime: ...
    async def step(self, delta: timedelta) -> datetime
    async def step_to(self, target: datetime) -> datetime
    async def sleep(self, seconds: float): ...
    async def sleep_until(self, target: datetime): ...
    def pause(self): ...
    def resume(self): ...
    def reset(self, start_time: datetime | None = None): ...
    def is_finished(self) -> bool: ...
```

#### `AcceleratedClock`

```python
class AcceleratedClock(Clock):
    def __init__(self, speed_factor: float = 10.0, timezone: str = "UTC")
    @property
    def mode(self) -> ClockMode: ...
    def now(self) -> datetime: ...
    async def sleep(self, seconds: float): ...
    async def sleep_until(self, target: datetime): ...
```

#### `ClockFactory`

```python
class ClockFactory:
    @staticmethod
    def create(config: ClockConfig) -> Clock: ...
    @staticmethod
    def create_for_backtest(
        start_time: datetime,
        end_time: datetime,
        speed_factor: float = 1.0,
    ) -> SimulatedClock: ...
    @staticmethod
    def create_for_paper(speed_factor: float = 1.0) -> Clock: ...
    @staticmethod
    def create_for_live() -> RealtimeClock: ...
```

### `cryptobot.core.portfolio`

#### `PortfolioManager`

```python
class PortfolioManager:
    def __init__(self, mode: PortfolioMode = PortfolioMode.PAPER)
    async def initialize(self): ...
    async def update_equity(self, equity: Decimal): ...
    def get_state(self) -> PortfolioState: ...
    def register_strategy(
        self,
        strategy: str,
        target_weight: Decimal,
        max_weight: Decimal | None = None,
        risk_budget: Decimal | None = None,
    ): ...
    def check_risk_limits(self, order: OrderEvent, price: Decimal) -> RiskCheckResult: ...
```

#### `PortfolioState`

```python
@dataclass
class PortfolioState:
    total_equity: Decimal = Decimal("0")
    available_balance: Decimal = Decimal("0")
    used_margin: Decimal = Decimal("0")
    total_unrealized_pnl: Decimal = Decimal("0")
    total_realized_pnl: Decimal = Decimal("0")
    daily_pnl: Decimal = Decimal("0")
    peak_equity: Decimal = Decimal("0")
    max_drawdown: Decimal = Decimal("0")
    open_positions: int = 0
    open_orders: int = 0
    strategies_active: int = 0
    total_return: Decimal = Decimal("0")
    annualized_return: Decimal = Decimal("0")
    volatility: Decimal = Decimal("0")
    Sharpe_ratio: Decimal = Decimal("0")
    Sortino_ratio: Decimal = Decimal("0")
    max_drawdown_pct: Decimal = Decimal("0")
    win_rate: Decimal = Decimal("0")
    profit_factor: Decimal = Decimal("0")
```

#### `PortfolioMode`

```python
class PortfolioMode(StrEnum):
    BACKTEST = "backtest"
    PAPER = "paper"
    LIVE = "live"
```

### `cryptobot.core.state`

#### `StateManager`

```python
class StateManager:
    async def initialize(self): ...
    async def close(self): ...
    async def save_order(self, order: OrderEvent): ...
    async def save_position(self, position: Position): ...
    async def update_account_equity(self, equity: Decimal): ...
    def get_account(self) -> AccountState: ...
    def get_positions(self) -> list[Position]: ...
    def get_open_orders(self) -> list[OrderEvent]: ...
    async def update_account_state(self, state: AccountState): ...
    def reset_daily_pnl(self): ...
```

## Execution Modules

### `cryptobot.execution.engine`

#### `ExecutionEngine`

```python
class ExecutionEngine:
    def __init__(
        self,
        venue: Venue = field(default_factory=build_venue),
        risk_manager: RiskManager = field(default_factory=get_risk_manager),
        event_bus: EventBus = field(default_factory=get_event_bus),
        router: SmartOrderRouter | None = None,
    )

    async def submit_order(self, order: OrderEvent) -> OrderEvent
    async def cancel_order(self, order_id: str) -> bool
```

#### `build_venue`

```python
def build_venue(mode: str | None = None) -> Venue:
    """mode: paper, backtest, testnet, live, binance"""
```

### `cryptobot.execution.router`

#### `SmartOrderRouter`

```python
class SmartOrderRouter:
    def __init__(
        self,
        venues: Sequence[Venue],
        config: RouterConfig | None = None,
        ranker: Ranker = best_price_ranker,
        fee_overrides: dict[str, Decimal] | None = None,
    )

    async def route(self, order: OrderEvent) -> RoutedOrder
    async def split_and_route(
        self,
        parent: OrderEvent,
        ratio: Sequence[Decimal],
    ) -> RoutedOrder
    async def quote_all(self, symbol: str) -> list[VenueScore]
```

#### `RouterConfig`

```python
@dataclass
class RouterConfig:
    max_slippage_bps: Decimal = Decimal("20")
    max_latency_ms: float = 250.0
    quote_timeout_s: float = 1.0
    max_child_venues: int = 3
```

### `cryptobot.execution.venue.simulated`

#### `SimulatedVenue`

```python
class SimulatedVenue(Venue):
    def __init__(
        self,
        prices: dict[str, Decimal] | None = None,
        slippage_bps: Decimal = Decimal("2"),
        commission_bps: Decimal = Decimal("5"),
        funding_rate: Decimal = Decimal("0.0001"),
    )

    async def submit_order(self, order: OrderEvent) -> OrderEvent
    async def cancel_order(self, order_id: str) -> bool
    async def get_price(self, symbol: str) -> Decimal
```

### `cryptobot.execution.router`

#### `VenueScore`

```python
@dataclass
class VenueScore:
    name: str
    venue: Venue
    price: Decimal
    latency_ms: float = 0.0
    fee_bps: Decimal = Decimal("0")
    liquidity_score: float = 1.0
    error: str | None = None
    round_trip_ms: float = 0.0

    @property
    def score(self) -> float: ...
```

#### Rankers

```python
def best_price_ranker(symbol: str, scores: Sequence[VenueScore]) -> int
def latency_aware_ranker(symbol: str, scores: Sequence[VenueScore]) -> int
def best_effort_ranker(symbol: str, scores: Sequence[VenueScore]) -> int
```

## Risk Management

### `cryptobot.risk.manager`

#### `RiskManager`

```python
class RiskManager:
    def __init__(
        self,
        portfolio: PortfolioManager = field(default_factory=get_portfolio_manager),
        limits: RiskLimits = field(default_factory=RiskLimits),
        kill_switch: KillSwitch = field(default_factory=KillSwitch),
    )

    def check_order(self, order: OrderEvent, price: Decimal | None = None) -> RiskCheckResult
```

#### `RiskCheckResult`

```python
@dataclass
class RiskCheckResult:
    passed: bool
    message: str = ""
    current_value: Decimal | None = None
    limit_value: Decimal | None = None

    def to_event(self, check_type: str, order: OrderEvent) -> RiskEvent: ...
```

#### `RiskLimits`

```python
@dataclass
class RiskLimits:
    min_order_size_usd: Decimal = Decimal("10")
    max_order_size_usd: Decimal = Decimal("10000")
    max_position_usd: Decimal = Decimal("50000")
    max_total_exposure_pct: Decimal = Decimal("0.80")
    max_drawdown_pct: Decimal = Decimal("0.15")
    kill_switch_daily_loss_pct: Decimal = Decimal("0.05")
    max_leverage: Decimal = Decimal("3.0")
    max_correlation: Decimal = Decimal("0.70")
```

### `cryptobot.risk.kill_switch`

```python
class KillSwitch:
    def evaluate(self, portfolio: PortfolioManager) -> tuple[bool, str]: ...
    def reset(self) -> None: ...
```

### `cryptobot.risk.correlation`

```python
def max_abs_correlation(correlation_matrix: np.ndarray) -> float:
    """Returns maximum absolute correlation between any two positions."""
```

## ML Models

### `cryptobot.ml.models.direction`

#### `DirectionClassifier`

```python
class DirectionClassifier:
    def __init__(self, config: DirectionConfig | None = None)
    def fit(self, features: np.ndarray, labels: np.ndarray) -> DirectionClassifier
    def predict_proba(self, features: np.ndarray) -> np.ndarray
    def predict(self, features: np.ndarray) -> np.ndarray
    def walk_forward_score(
        self,
        features: np.ndarray,
        labels: np.ndarray | None = None,
        n_splits: int = 4,
    ) -> float
    def summary(self) -> dict[str, Any]
```

#### `DirectionConfig`

```python
@dataclass
class DirectionConfig:
    threshold: float = 0.55
    horizon: int = 5
    max_features: int = 8
```

### `cryptobot.ml.models.volatility`

#### `VolatilityModel`

```python
class VolatilityModel:
    def __init__(self, config: VolatilityConfig | None = None)
    def fit(self, returns: np.ndarray) -> VolatilityModel
    def forecast(self, horizon: int | None = None) -> float
    def forecast_series(self, returns: np.ndarray, horizon: int | None = None) -> np.ndarray
    def summary(self) -> dict[str, Any]
```

#### `VolatilityConfig`

```python
@dataclass
class VolatilityConfig:
    horizon: int = 5
    window: int = 20
    method: str = "ewma"  # ewma, garch, realized
    lambda_: float = 0.94
```

### `cryptobot.ml.models.regime`

#### `RegimeDetector`

```python
class RegimeDetector:
    def __init__(self, config: RegimeConfig | None = None)
    def fit(self, features: np.ndarray) -> RegimeDetector
    def predict(self, features: np.ndarray) -> np.ndarray
    def predict_proba(self, features: np.ndarray) -> np.ndarray
    def current_regime(self, features: np.ndarray) -> int
    def regime_summary(self) -> dict[int, dict[str, Any]]
    def summary(self) -> dict[str, Any]
```

#### `RegimeConfig`

```python
@dataclass
class RegimeConfig:
    n_regimes: int = 3
    window: int = 50
    method: str = "hmm"  # hmm, kmeans, threshold
    min_duration: int = 5
```

### `cryptobot.ml.models.ensemble`

#### `EnsembleModel`

```python
class EnsembleModel:
    def __init__(self, config: EnsembleConfig | None = None)
    def fit(self, features: np.ndarray, labels: np.ndarray) -> EnsembleModel
    def predict_proba(self, features: np.ndarray) -> np.ndarray
    def predict(self, features: np.ndarray) -> np.ndarray
    def predict_with_confidence(self, features: np.ndarray) -> tuple[np.ndarray, np.ndarray]
    def predict_volatility(self, returns: np.ndarray, horizon: int = 5) -> float
    def current_regime(self, features: np.ndarray) -> int
    def summary(self) -> dict[str, Any]
```

#### `EnsembleConfig`

```python
@dataclass
class EnsembleConfig:
    models: list[str] | None = None  # "direction", "volatility", "regime"
    weights: list[float] | None = None
    direction_config: DirectionConfig | None = None
    volatility_config: VolatilityConfig | None = None
    regime_config: RegimeConfig | None = None
    meta_learner: str = "weighted_vote"  # weighted_vote, logistic_regression
```

#### `create_ensemble`

```python
def create_ensemble(
    direction_weight: float = 0.5,
    volatility_weight: float = 0.2,
    regime_weight: float = 0.3,
) -> EnsembleModel
```