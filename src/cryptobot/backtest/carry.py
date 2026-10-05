"""Two-leg funding-carry backtest driver (long spot, short perp).

Runs a FundingArb-style strategy inside the real backtest machinery:
orders flow through ExecutionEngine/RiskManager, positions are tracked
in the engine's per-symbol book, and funding settles at real 8h
boundaries via the engine's FundingProvider.

Legs: the strategy returns ``(perp_side, spot_side)``; entry is SELL
perp / BUY spot, exit is BUY perp / SELL spot. Both legs are emitted at
the same bar timestamp; spot and perp klines must be time-aligned.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal

from cryptobot.backtest.engine import BacktestEngine
from cryptobot.backtest.funding import (
    CsvFundingProvider,
    FixedFundingProvider,
    FundingProvider,
)
from cryptobot.backtest.runner import OhlcvBar
from cryptobot.core.events import (
    Event,
    EventType,
    OrderEvent,
    OrderSide,
    OrderStatus,
    OrderType,
)
from cryptobot.core.portfolio import PortfolioManager, PortfolioMode
from cryptobot.execution.engine import ExecutionEngine
from cryptobot.execution.venue.simulated import SimulatedVenue
from cryptobot.risk.manager import RiskManager

logger = logging.getLogger(__name__)


def make_funding_provider(csv_path: str | None = None, fixed_rate: str | None = None) -> FundingProvider:
    """Build a provider from a Binance funding CSV or a constant rate."""
    if csv_path:
        return CsvFundingProvider(csv_path)
    return FixedFundingProvider(Decimal(fixed_rate) if fixed_rate else Decimal("0.0001"))


def align_spot_to_perp(spot_bars: list[OhlcvBar], perp_bars: list[OhlcvBar]) -> list[OhlcvBar]:
    """Resample spot (1h) bars to each perp (8h) bar's close instant.

    Perp 8h bar opening at U closes at price-at-U+8h. The contemporaneous
    1h spot close is the bar opening at U+7h (it closes at U+8h). A spot bar
    at H therefore pairs with the perp bar at H-7h. This avoids the
    7-14h-stale spot pricing bug that otherwise mints fake carry PnL.
    """
    perp_by_open = {p.timestamp: p for p in perp_bars}
    out: list[OhlcvBar] = []
    for sb in spot_bars:
        pb = perp_by_open.get(sb.timestamp - timedelta(hours=7))
        if pb is None:
            continue
        out.append(
            OhlcvBar(
                timestamp=pb.timestamp,
                open=float(sb.close),
                high=float(sb.close),
                low=float(sb.close),
                close=float(sb.close),
                volume=0.0,
            )
        )
    return out


async def run_carry(
    spot_bars,
    perp_bars,
    strategy,
    funding: FundingProvider,
    symbol: str = "BTCUSDT",
    perp_symbol: str = "BTCUSDTPERP",
    initial_capital: float = 10_000,
    slippage_bps: int = 2,
    commission_bps: int = 5,
) -> BacktestEngine:
    """Two-leg funding carry: returns the engine (trades/equity inspectable)."""
    if len(spot_bars) != len(perp_bars):
        raise ValueError("spot_bars and perp_bars must be time-aligned")
    start = spot_bars[0].timestamp
    end = spot_bars[-1].timestamp

    portfolio = PortfolioManager(PortfolioMode.BACKTEST)
    venue = SimulatedVenue(
        slippage_bps=Decimal(str(slippage_bps)),
        commission_bps=Decimal(str(commission_bps)),
    )
    ee = ExecutionEngine(
        venue=venue,
        risk_manager=RiskManager(portfolio=portfolio, backtest_mode=True),
    )
    bt = BacktestEngine(
        start_time=start,
        end_time=end,
        initial_capital=float(initial_capital),
        commission_bps=commission_bps,
        slippage_bps=slippage_bps,
        portfolio=portfolio,
        funding=funding,
        funding_symbols={perp_symbol},
    )
    await bt.initialize()

    for i, sb in enumerate(spot_bars):
        pb = perp_bars[i]
        await bt._maybe_settle_funding(sb.timestamp)
        s, p = Decimal(str(sb.close)), Decimal(str(pb.close))
        ee.venue.prices[symbol] = s
        ee.venue.prices[perp_symbol] = p
        rate = funding.rate(perp_symbol, sb.timestamp)
        signal = strategy.feed(sb.timestamp, s, p, rate)
        if signal is None:
            continue
        perp_side, spot_side = signal
        legs = ((perp_side, perp_symbol, p), (spot_side, symbol, s))
        # Size the pair at entry from current equity (risk scaling); the exit
        # reuses the entry size so both legs always match. Entry = SELL perp.
        if strategy.config.risk_fraction > 0 and perp_side == OrderSide.SELL:
            equity = bt._portfolio.get_state().total_equity
            strategy.qty = strategy.size_position(s, equity)
        for side, sym, px in legs:
            fill = await ee.submit_order(
                OrderEvent(
                    symbol=sym,
                    side=side,
                    type=OrderType.MARKET,
                    quantity=strategy.qty,
                    price=px,
                )
            )
            if fill.status != OrderStatus.FILLED:
                logger.debug("carry leg %s %s not filled: %s", sym, side, fill.status)
                continue
            await bt._process_event(
                Event(
                    type=EventType.ORDER_FILLED,
                    timestamp=sb.timestamp,
                    payload={
                        "symbol": fill.symbol,
                        "filled_quantity": str(fill.filled_quantity),
                        "avg_fill_price": str(fill.avg_fill_price or px),
                        "side": fill.side.value,
                        "strategy": "funding_carry",
                        "unrealized_pnl": "0",
                        "fees": str(fill.commission),
                    },
                )
            )
    return bt


__all__ = ["make_funding_provider", "run_carry"]
