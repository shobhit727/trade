from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from math import log
from typing import Any

import numpy as np

from cryptobot.backtest.engine import BacktestEngine, TradeRecord
from cryptobot.core.events import Event, EventType, OrderStatus
from cryptobot.core.portfolio import PortfolioManager, PortfolioMode
from cryptobot.execution.engine import ExecutionEngine
from cryptobot.execution.venue.simulated import SimulatedVenue
from cryptobot.risk.manager import RiskManager
from cryptobot.strategies.mean_reversion import MeanReversionConfig, MeanReversionStrategy
from cryptobot.strategies.trend_following import TrendFollowingConfig, TrendFollowingStrategy


@dataclass(slots=True)
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
    freq_seconds: float | None = None,
    start_price: float = 100.0,
    drift: float = 0.0005,
    vol: float = 0.01,
    seed: int = 42,
    mean_reversion_strength: float = 0.001,
) -> list[OhlcvBar]:
    if n_bars < 1:
        raise ValueError("n_bars must be >= 1")
    if freq_seconds is not None and freq_seconds < 1e-6:
        raise ValueError("freq_seconds must be >= 1e-6 (1 microsecond)")
    rng = np.random.default_rng(seed)
    # Row-major draws preserve the exact per-bar RNG stream of the sequential generator.
    z = rng.normal(0.0, 1.0, size=(n_bars, 4))
    # Convert to plain Python floats once: the stateful AR(1) loop below runs
    # per bar, and scalar arithmetic on numpy float64 is ~10x slower than on
    # floats while computing identical IEEE-754 results.
    noise = (drift + vol * z[:, 0]).tolist()
    high_wiggle = 1.0 + (vol / 2) * np.abs(z[:, 1])
    low_wiggle = 1.0 - (vol / 2) * np.abs(z[:, 2])
    volumes = np.abs(1000.0 + 200.0 * z[:, 3])

    # Mean-reverting (Ornstein-Uhlenbeck) random walk in log space. The log price snaps
    # back toward its anchor (equilibrium = anchor + drift/k), so very long runs never
    # overflow to inf NOR pin flat against a clamp -- price keeps moving forever, which
    # matters for backtests that span millions of bars.
    anchor = log(start_price)
    frac = mean_reversion_strength
    intercept = frac * anchor
    decay = 1.0 - frac
    log_price = anchor
    log_prices = np.empty(n_bars)
    for i in range(n_bars):
        log_price = decay * log_price + intercept + noise[i]
        log_prices[i] = log_price
    del noise
    log_prices = np.clip(log_prices, np.log(1e-8), np.log(1e12))
    closes = np.exp(log_prices)
    del log_prices
    opens = np.empty_like(closes)
    opens[0] = start_price
    opens[1:] = closes[:-1]

    highs = np.maximum(opens, closes) * high_wiggle
    lows = np.maximum(np.minimum(opens, closes) * low_wiggle, 1e-8)
    lows = np.minimum(lows, highs)
    del high_wiggle, low_wiggle

    start64 = np.datetime64(start, "s")
    if freq_seconds is not None:
        step_us = int(round(freq_seconds * 1_000_000))
        deltas = (np.arange(n_bars, dtype=np.int64) * step_us).astype("timedelta64[us]")
        timestamps = (start64 + deltas).astype("datetime64[us]").tolist()
    else:
        deltas = np.arange(n_bars, dtype=np.int64) * np.int64(freq_minutes) * np.int64(60)
        timestamps = (start64 + deltas.astype("timedelta64[s]")).astype("datetime64[us]").tolist()
    del start64, deltas

    # Build bars straight from the arrays (float() per element is C-fast and exact).
    # Materializing separate boxed-float lists of every field would transiently
    # consume gigabytes at 10M+ bars -- e.g. a 10M-bar synthetic run otherwise
    # peaks well past 3GB and OOMs in constrained containers.
    return [
        OhlcvBar(
            timestamp=timestamps[i],
            open=float(opens[i]),
            high=float(highs[i]),
            low=float(lows[i]),
            close=float(closes[i]),
            volume=float(volumes[i]),
        )
        for i in range(n_bars)
    ]


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
    trades: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "initial_capital": str(self.initial_capital),
            "final_equity": str(self.final_equity),
            "total_return": self.total_return,
            "n_trades": self.n_trades,
            "n_equity_points": len(self.equity_curve),
            "trades": self.trades,
        }


def _trade_to_dict(trade: TradeRecord) -> dict[str, Any]:
    return {
        "entry_time": trade.entry_time.isoformat(),
        "exit_time": trade.exit_time.isoformat(),
        "entry_price": str(trade.entry_price),
        "exit_price": str(trade.exit_price),
        "quantity": str(trade.quantity),
        "side": trade.side,
        "pnl": str(trade.pnl),
        "pnl_pct": str(trade.pnl_pct),
        "fees": str(trade.fees),
        "strategy": trade.strategy,
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
        yield Event(
            type=EventType.TICKER,
            timestamp=bar.timestamp,
            payload={
                "symbol": symbol,
                "price": str(bar.close),
                "close_price": str(bar.close),
            },
        )
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
            # Keep the venue's mark price current so market orders fill at bar close
            execution_engine.venue.prices[symbol] = Decimal(str(bar.close))
            filled = await execution_engine.submit_order(o)
            if filled.status == OrderStatus.FILLED:
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
    collect_trades: bool = False,
) -> BacktestRunResult:
    if not bars:
        raise ValueError("no bars supplied")
    if execution_engine is None:
        portfolio = PortfolioManager(PortfolioMode.BACKTEST)
        venue = SimulatedVenue(
            slippage_bps=Decimal(str(slippage_bps)),
            commission_bps=Decimal(str(commission_bps)),
        )
        execution_engine = ExecutionEngine(
            venue=venue,
            risk_manager=RiskManager(portfolio=portfolio),
        )
    else:
        portfolio = execution_engine.risk_manager.portfolio

    bt_engine = BacktestEngine(
        start_time=bars[0].timestamp,
        end_time=bars[-1].timestamp,
        initial_capital=float(initial_capital),
        commission_bps=commission_bps,
        slippage_bps=slippage_bps,
        portfolio=portfolio,
    )
    bt_result = await bt_engine.run_bars(bars, strategy, symbol, execution_engine)

    initial = Decimal(str(initial_capital))
    total_return = float((bt_result.final_equity - initial) / initial) if initial else 0.0
    return BacktestRunResult(
        initial_capital=initial,
        final_equity=bt_result.final_equity,
        total_return=total_return,
        n_trades=bt_result.total_trades,
        equity_curve=bt_result.equity_curve,
        trades=[_trade_to_dict(t) for t in bt_engine.get_trades()] if collect_trades else [],
    )


__all__ = [
    "BacktestRunResult",
    "OhlcvBar",
    "generate_synthetic_ohlcv",
    "make_strategy",
    "run_backtest",
]
