"""Tests for the live trading loop (cryptobot.live.trader)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from cryptobot.core.events import KlineEvent
from cryptobot.live.trader import LiveTrader, LiveTraderConfig


def _kline(close: float, open_ms: int, *, closed: bool = True) -> KlineEvent:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    return KlineEvent(
        symbol="BTCUSDT",
        interval="1m",
        open_time=base + timedelta(milliseconds=open_ms),
        close_time=base + timedelta(milliseconds=open_ms + 60_000),
        open_price=Decimal(str(close)),
        high_price=Decimal(str(close * 1.01)),
        low_price=Decimal(str(close * 0.99)),
        close_price=Decimal(str(close)),
        volume=Decimal("10"),
        trades=5,
        is_closed=closed,
    )


def _trader(**overrides) -> LiveTrader:
    params = dict(
        strategy="dual_ma",
        strategy_params={"fast": 3, "slow": 5},
        symbol="BTCUSDT",
        timeframe="1m",
        warmup_bars=0,
        port=0,  # ephemeral: parallel tests / occupied 8080
    )
    params.update(overrides)
    return LiveTrader(LiveTraderConfig(**params))


@pytest.mark.asyncio
async def test_closed_klines_flow_to_venue_and_stats():
    trader = _trader()
    # push enough closed bars with alternating direction so dual_ma flips
    px = 100.0
    for i in range(40):
        px *= 1.02 if (i // 8) % 2 == 0 else 0.98
        await trader._on_kline(_kline(px, i * 60_000))

    assert trader.stats["bars_fed"] == 40
    assert trader.stats["orders_submitted"] >= 2
    assert trader.stats["fills"] == trader.stats["orders_submitted"]
    assert trader.stats["rejects"] == 0


@pytest.mark.asyncio
async def test_unclosed_and_foreign_events_are_ignored():
    trader = _trader()
    await trader._on_kline(_kline(100.0, 0, closed=False))
    assert trader.stats["bars_seen"] == 0

    foreign = _kline(100.0, 0)
    foreign.symbol = "ETHUSDT"
    await trader._on_kline(foreign)
    assert trader.stats["bars_seen"] == 0

    wrong_tf = _kline(100.0, 0)
    wrong_tf.interval = "5m"
    await trader._on_kline(wrong_tf)
    assert trader.stats["bars_seen"] == 0

    non_kline = object()
    await trader._on_kline(non_kline)


@pytest.mark.asyncio
async def test_duplicate_bar_timestamps_are_deduplicated():
    trader = _trader()
    for _ in range(3):
        await trader._on_kline(_kline(100.0, 0))
    assert trader.stats["bars_seen"] == 1
    assert trader.stats["bars_fed"] == 1


@pytest.mark.asyncio
async def test_rejections_are_counted():
    trader = _trader()
    # live-mode risk semantics: qty=1 BTC at ~$100 is $100 notional on $10k equity — fine.
    # Force a rejection by shrinking the venue's tradable price to zero via a bad bar.
    trader._engine.venue.prices.clear()
    for i in range(40):
        await trader._on_kline(_kline(100.0 + i, i * 60_000))
    assert trader.stats["orders_submitted"] >= 1
    assert (
        trader.stats["fills"] + trader.stats["rejects"]
        == trader.stats["orders_submitted"]
    )


@pytest.mark.asyncio
async def test_run_starts_ws_stops_cleanly(monkeypatch):
    """run() wires the kline callback through a stubbed WS client and exits on max_bars."""
    import cryptobot.live.trader as mod

    pushed: list = []

    class _StubWS:
        def __init__(self):
            self.subs = {}

        def subscribe(self, etype, cb):
            self.subs[str(etype)] = cb
            self.cb = cb

        async def start(self):
            pushed.append("start")
            # simulate two closed bars then let max_bars stop the loop
            for i in range(2):
                await self.cb(_kline(100.0 + i, i * 60_000))

        async def stop(self):
            pushed.append("stop")

    monkeypatch.setattr(mod, "_new_ws_client", lambda config=None: _StubWS())

    trader = _trader(max_bars=2)
    await asyncio.wait_for(trader.run(), timeout=10)

    assert pushed == ["start", "stop"]
    assert trader.stats["status"] == "stopped"
    assert trader.stats["bars_fed"] == 2
