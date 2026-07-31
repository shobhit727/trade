from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

import numpy as np

from cryptobot.backtest.engine import BacktestEngine
from cryptobot.core.events import Event, EventType
from cryptobot.execution.engine import ExecutionEngine
from cryptobot.execution.venue.simulated import SimulatedVenue
from cryptobot.strategies.mean_reversion import MeanReversionConfig, MeanReversionStrategy
from cryptobot.strategies.trend_following import TrendFollowingConfig, TrendFollowingStrategy


@dataclass
class OhlcvBar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "open_time": self.timestamp.isoformat(),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
        }


def generate_synthetic_ohlcv(
    start: datetime,
    n_bars: int = 200,
    freq_minutes: int = 15,
    start_price: float = 100.0,
    drift: float = 0.0005,
    vol: float = 0.01,
    seed: int = 42,
) -> list[OhlcvBar]:
    rng = np.random.default_rng(seed)
    bars: list[OhlcvBar] = []
    price = start_price
    for i in range(n_bars):
        ts = start + timedelta(minutes=i * freq_minutes)
        ret = rng.normal(loc=drift, scale=vol)
        new_close = max(price * (1.0 + ret), 1e-8)
        high = max(price, new_close) * (1.0 + abs(rng.normal(0.0, vol / 2)))
        low = min(price, new_close) * (1.0 - abs(rng.normal(0.0, vol / 2)))
        low = max(low, 1e-8)
        bars.append(
            OhlcvBar(
                timestamp=ts,
                open=price,
                high=high,
                low=low,
                close=new_close,
                volume=float(abs(rng.normal(1000, 200))),
            )
        )
        price = new_close
    return bars


def make_strategy(name: str, **kwargs):
    if name == "mean_reversion":
        cfg = MeanReversionConfig(**kwargs) if kwargs else MeanReversionConfig()
        return MeanReversionStrategy(cfg)
    if name == "trend_following":
        cfg = TrendFollowingConfig(**kwargs) if kwargs else TrendFollowingConfig()
        return TrendFollowingStrategy(cfg)
    raise ValueError(f"Unknown strategy: {name}")


@dataclass
class BacktestRunResult:
    initial_capital: Decimal
    final_equity: Decimal
    total_return: float
    n_trades: int
    equity_curve: list[tuple[datetime, Decimal]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "initial_capital": str(self.initial_capital),
            "final_equity": str(self.final_equity),
            "total_return": self.total_return,
            "n_trades": self.n_trades,
            "n_equity_points": len(self.equity_curve),
        }


async def _stream_filled_events(
    bars: Sequence[OhlcvBar],
    strategy,
    symbol: str,
    execution_engine: ExecutionEngine,
) -> AsyncIterator[Event]:
    """Generator that yields ORDER_FILLED events whenever the strategy reacts.

    For each bar:
      1. Feed price (and high/low) to the strategy.
      2. For every order returned, await ExecutionEngine.submit_order; that
         path publishes ORDER_FILLED through the engine's bus.
      3. Yield each filled order as an Event back to BacktestEngine.
    """
    for bar in bars:
        order = None
        if hasattr(strategy, "feed") and hasattr(strategy, "name"):
            if strategy.name == "trend_following":
                order = strategy.feed(symbol, bar.high, bar.low, bar.close)
            else:
                order = strategy.feed(symbol, bar.close)
        if order is None:
            continue
        if not isinstance(order, list):
            order = [order]
        for o in order:
            if o is None:
                continue
            filled = await execution_engine.submit_order(o)
            if filled.status.value in ("filled", "rejected", "canceled"):
                yield Event(
                    type=EventType.ORDER_FILLED,
                    timestamp=bar.timestamp,
                    payload={
                        "symbol": filled.symbol,
                        "filled_quantity": str(filled.filled_quantity),
                        "avg_fill_price": str(filled.avg_fill_price or Decimal("0")),
                        "side": filled.side.value,
                        "strategy": filled.strategy or strategy.name,
                        "unrealized_pnl": "0",
                        "fees": str(filled.commission),
                    },
                )


async def run_backtest(
    bars: Sequence[OhlcvBar],
    strategy,
    symbol: str = "BTCUSDT",
    initial_capital: Decimal = Decimal("10000"),
    slippage_bps: int = 3,
    commission_bps: int = 5,
    execution_engine: ExecutionEngine | None = None,
) -> BacktestRunResult:
    if not bars:
        raise ValueError("no bars supplied")
    if execution_engine is None:
        venue = SimulatedVenue(
            slippage_bps=Decimal(str(slippage_bps)),
            commission_bps=Decimal(str(commission_bps)),
        )
        execution_engine = ExecutionEngine(venue=venue)

    stream = _stream_filled_events(bars, strategy, symbol, execution_engine)

    bt_engine = BacktestEngine(
        start_time=bars[0].timestamp,
        end_time=bars[-1].timestamp,
        initial_capital=float(initial_capital),
        commission_bps=commission_bps,
        slippage_bps=slippage_bps,
    )
    bt_result = await bt_engine.run(stream)

    initial = Decimal(str(initial_capital))
    total_return = float((bt_result.final_equity - initial) / initial) if initial else 0.0
    return BacktestRunResult(
        initial_capital=initial,
        final_equity=bt_result.final_equity,
        total_return=total_return,
        n_trades=bt_result.total_trades,
        equity_curve=bt_result.equity_curve,
    )


__all__ = [
    "BacktestRunResult",
    "OhlcvBar",
    "generate_synthetic_ohlcv",
    "make_strategy",
    "run_backtest",
]
