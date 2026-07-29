from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List, Any
import asyncio
import logging
from datetime import datetime
from decimal import Decimal
from cryptobot.core.events import Event, OrderEvent, OrderSide, OrderType, PositionSide
from cryptobot.utils.decorators import timeout_decorator


logger = logging.getLogger(__name__)

class BaseStrategy(ABC):
    """
    Abstract Base Class defining the contract for all quantitative trading strategies.
    All custom strategies MUST inherit from this class to ensure compatibility with
    the EventBus and BacktestEngine.
    """
    def __init__(self, strategy_name: str, config: Dict[str, Any]):
        self.strategy_name = strategy_name
        self._config = config
        # Store internal state (e.g., indicator buffers, historical data slice)
        self.internal_state: Dict[str, Any] = {}

    @abstractmethod
    async def initialize(self, initial_data: Any):
        """
        Called once at the start of a backtest run or live session startup.
        Must populate internal state (e.g., calculating initial indicators).
        """
        pass

    @abstractmethod
    async def on_market_data(self, event: "Event") -> List["OrderEvent"]:
        """
        The primary entry point for market data updates.
        Processes the raw market tick and determines if any trading action is required.

        Args:
            event: The incoming MARKET_DATA event.
        Returns: A list of proposed OrderEvents to be passed back to the engine.
        """
        pass

    async def on_order_update(self, event: "Event") -> List["OrderEvent"]:
        """
        Callback called when an order is filled, cancelled, or rejected.
        This method allows strategies to react dynamically to execution confirmations.
        Returns: A list of *new* proposed actions (e.g., adjusting stop losses).
        """
        return [] # Default implementation returns no action

    def get_name(self) -> str:
        """Returns the unique, displayable name of the strategy."""
        return self.strategy_name

# --- Strategy Registry Singleton ---

class StrategyRegistry:
    """
    Manages all available and loaded strategies, facilitating discovery by the backtester.
    Implements a factory pattern to create instances with correct configurations.
    """
    _instance = None
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(StrategyRegistry, cls).__new__(cls)
            cls._instance.strategies: Dict[str, BaseStrategy] = {}
            logger.debug("StrategyRegistry initialized.")
        return cls._instance

    def register(self, strategy_class: type[BaseStrategy], config: Dict[str, Any]):
        """Registers a new strategy instance."""
        if not issubclass(strategy_class, BaseStrategy):
             raise TypeError("Provided class must inherit from BaseStrategy.")

        instance = strategy_class(strategy_name=config.get('name', strategy_class.__name__), config=config)
        self.strategies[instance.get_name()] = instance

    def get_all_active_strategies(self) -> List[BaseStrategy]:
        """Returns a list of all strategies currently loaded and ready to run."""
        return list(self.strategies.values())


# --- Example Implementation: Mean Reversion (A simple placeholder strategy) ---

class MeanReversionStrategyPlaceholder(BaseStrategy):
    def __init__(self, strategy_name: str, config: Dict[str, Any]):
        super().__init__(strategy_name, config)

    @timeout_decorator(timeout=0.5) # Use timeout decorator for safety
    async def initialize(self, initial_data: Any):
        # In reality, this would load historical data slices into internal buffers.
        logger.info("[%s] Initializing with %s data points.", self.get_name(), len(initial_data) if initial_data is not None else 0)
        self.internal_state['z_score'] = [] # Placeholder for indicator history

    async def on_market_data(self, event: Event) -> List[OrderEvent]:
        """Simple logic: if price deviates more than 2 STD from mean, attempt a reversal trade."""
        price = event.payload.get("price")
        if price is None: return []

        # Placeholder Logic (needs full Indicator Calculation):
        is_overbought = float(price) > self._config.get("high_trigger", 1.2) * 65000 # Example trigger
        is_oversold = float(price) < self._config.get("low_trigger", 0.8) * 65000

        if is_overbought:
            logger.info("[MR] Overbought detected (%.2f). SIGNAL: SHORT.", float(price))
            return [OrderEvent(type=OrderType.MARKET, symbol=event.payload["symbol"], quantity=Decimal("1"), side=OrderSide.SELL, position_side=PositionSide.SHORT)]
        elif is_oversold:
            logger.info("[MR] Oversold detected (%.2f). SIGNAL: LONG.", float(price))
            return [OrderEvent(type=OrderType.MARKET, symbol=event.payload["symbol"], quantity=Decimal("1"), side=OrderSide.BUY, position_side=PositionSide.LONG)]

        return [] # No action taken


# --- Global Registry Singleton Instance ---
registry = StrategyRegistry()
