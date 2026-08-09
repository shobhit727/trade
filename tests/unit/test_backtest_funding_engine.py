"""Engine-level funding accrual: open positions settle at each 8h boundary."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal

from cryptobot.backtest.funding import FixedFundingProvider
from cryptobot.backtest.runner import generate_synthetic_ohlcv, run_backtest
from cryptobot.core.events import OrderEvent, OrderSide, OrderType


class _HoldAll:
    """Opens 1 BTC on the first bar, never closes."""

    def __init__(self, side: str = "BUY"):
        self._opened = False
        self._side = side
        self.name = "hold_all"

    def feed(self, symbol, close):
        if not self._opened:
            self._opened = True
            return OrderEvent(
                symbol=symbol,
                side=OrderSide.BUY if self._side == "BUY" else OrderSide.SELL,
                type=OrderType.MARKET,
                quantity=Decimal("1"),
                price=Decimal("0"),
            )
        return None


def _equity(side: str, rate: Decimal | None) -> Decimal:
    bars = generate_synthetic_ohlcv(
        datetime(2024, 1, 1, tzinfo=UTC), n_bars=26, freq_minutes=60, seed=1
    )
    kwargs = {}
    if rate is not None:
        kwargs["funding"] = FixedFundingProvider(rate)
    result = asyncio.run(run_backtest(bars, strategy=_HoldAll(side), **kwargs))
    return result.final_equity


def test_long_pays_funding_at_settlement_blocks():
    # 26 1h bars from 00:00 UTC: settlements at 00:00, 08:00, 16:00 blocks.
    funded = _equity("BUY", Decimal("0.001"))
    plain = _equity("BUY", None)
    assert funded < plain  # long pays -> lower equity
    gap = plain - funded
    assert Decimal("0.05") < gap < Decimal("0.6"), gap


def test_short_receives_funding_at_settlement_blocks():
    funded = _equity("SELL", Decimal("0.001"))
    plain = _equity("SELL", None)
    assert funded > plain  # short receives -> higher equity
    gap = funded - plain
    assert Decimal("0.05") < gap < Decimal("0.6"), gap


def test_zero_rate_provider_is_noop():
    zero = _equity("BUY", Decimal("0"))
    plain = _equity("BUY", None)
    assert zero == plain
