"""Live/paper trading loop (Phase 8 completion).

Wires the full stack end-to-end for long-running processes:

    market data (Binance WS klines)
        -> strategy.feed() per CLOSED bar
        -> ExecutionEngine.submit_order()  (risk-checked)
        -> venue fill -> portfolio/health updates

The ``bot`` CLI command runs this loop alongside the health server. Paper mode
(default) executes against SimulatedVenue; live mode routes through BinanceVenue
and therefore requires credentials + explicit opt-in.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from decimal import Decimal

import aiohttp

from cryptobot.backtest.runner import make_strategy
from cryptobot.core.bus import get_event_bus
from cryptobot.core.events import KlineEvent
from cryptobot.core.fund import FundConfig, GlobalFundLedger
from cryptobot.core.portfolio import PortfolioManager, PortfolioMode
from cryptobot.execution.engine import ExecutionEngine, build_venue
from cryptobot.risk.manager import RiskManager
from cryptobot.utils.health_server import HealthServer

logger = logging.getLogger(__name__)

DEFAULT_REST_URL = "https://api.binance.com"


@dataclass
class LiveTraderConfig:
    strategy: str = "trend_following"
    strategy_params: dict = field(default_factory=dict)
    symbol: str = "BTCUSDT"
    timeframe: str = "1m"
    mode: str = "paper"  # paper | live
    host: str = "127.0.0.1"
    port: int = 8080
    warmup_bars: int = 300
    rest_url: str = DEFAULT_REST_URL
    # Market DATA comes from the public production socket regardless of where
    # orders go; the testnet combined-stream endpoint rejects large URLs.
    data_ws_url: str = "wss://stream.binance.com:9443"
    max_bars: int | None = None  # stop after N closed bars (tests / dry-runs)
    # Global-fund harvest (Seed Phase step 1): every harvest_hours, skim
    # skim_fraction of realized PnL into the cross-algorithm reserve pool.
    harvest_hours: int = 8
    skim_fraction: str = "0.10"
    fund_state_path: str = "state/global_fund.json"


class LiveTrader:
    """Event-driven trading process: klines in, risk-checked orders out."""

    def __init__(self, config: LiveTraderConfig):
        self.config = config
        self.strategy = make_strategy(config.strategy, **config.strategy_params)

        mode = PortfolioMode.LIVE if config.mode == "live" else PortfolioMode.PAPER
        self._portfolio = PortfolioManager(mode)
        # LIVE risk semantics on purpose: backtest_mode=False keeps every
        # economic limit active (#33).
        self._risk_manager = RiskManager(portfolio=self._portfolio)
        self._engine = ExecutionEngine(
            venue=build_venue("paper" if config.mode != "live" else config.mode),
            risk_manager=self._risk_manager,
            event_bus=get_event_bus(),
        )

        self._health = HealthServer(host=config.host, port=config.port)
        self._stop = asyncio.Event()
        self._seen_bars: deque[int] = deque(maxlen=64)
        self._fund = GlobalFundLedger(FundConfig(
            skim_fraction=Decimal(config.skim_fraction),
            state_path=config.fund_state_path,
        ))
        self._last_harvested_realized = Decimal("0")
        self._harvest_task: asyncio.Task | None = None
        self.stats: dict[str, object] = {
            "status": "starting",
            "strategy": config.strategy,
            "symbol": config.symbol,
            "timeframe": config.timeframe,
            "mode": config.mode,
            "bars_seen": 0,
            "bars_fed": 0,
            "orders_submitted": 0,
            "fills": 0,
            "rejects": 0,
            "last_close": None,
            "last_order_at": None,
        }

    # ------------------------------------------------------------------ stats

    def stats_snapshot(self) -> dict:
        snap = dict(self.stats)
        state = self._portfolio.get_state()
        snap["equity"] = str(state.total_equity)
        snap["open_positions"] = state.open_positions
        snap["global_fund"] = self._fund.summary()
        return snap

    def request_stop(self) -> None:
        self._stop.set()

    # -------------------------------------------------------------- lifecycle

    async def run(self) -> None:
        """Run until :meth:`request_stop` (or ``max_bars`` reached)."""
        ws = _new_ws_client(self.config)
        await self._portfolio.initialize()
        self._health.start()
        self._install_health_snapshot()

        try:
            self._harvest_task = asyncio.create_task(self._harvest_loop())
            if self.config.warmup_bars > 0:
                await self._warm_up()

            self._ws = ws
            ws.subscribe(_kline_event_type(), self._on_kline)
            await ws.start()
            self.stats["status"] = "running"

            bars_remaining = self.config.max_bars - self.stats["bars_fed"] \
                if self.config.max_bars is not None else None
            while not self._stop.is_set():
                await asyncio.sleep(0.5)
                if bars_remaining is not None and self.stats["bars_fed"] >= self.config.max_bars:
                    break
            self.stats["status"] = "stopped"
        finally:
            if self._harvest_task is not None:
                self._harvest_task.cancel()
                try:
                    await self._harvest_task
                except asyncio.CancelledError:
                    pass
            await ws.stop()
            self._health.stop()

    # ------------------------------------------------------- global-fund harvest

    async def _harvest_loop(self) -> None:
        """Every ``harvest_hours``, skim realized-PnL growth into the fund."""
        window = max(int(self.config.harvest_hours), 1) * 3600
        deadline = time.monotonic() + window
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=30)
                break  # stop requested
            except TimeoutError:
                pass
            if time.monotonic() < deadline:
                continue
            state = self._portfolio.get_state()
            delta = state.total_realized_pnl - self._last_harvested_realized
            if delta > 0 and not self._fund.frozen:
                entry = self._fund.skim(delta)
                if entry is not None:
                    logger.info("harvest: skimmed %s of %s realized PnL into global fund",
                                entry["amount"], delta)
            self._last_harvested_realized += max(delta, Decimal("0"))
            deadline = time.monotonic() + window

    def _install_health_snapshot(self) -> None:
        """Expose trader stats through /health (keeps uptime fields)."""
        base = self._health._httpd.health_snapshot  # type: ignore[attr-defined]
        trader = self

        class _Merged:
            def snapshot(self_inner):  # noqa: N802
                merged = base.snapshot()
                merged.update(trader.stats_snapshot())
                return merged

        self._health._httpd.health_snapshot = _Merged()  # type: ignore[attr-defined]

    # ------------------------------------------------------------ data intake

    async def _warm_up(self) -> None:
        """Prime indicator buffers from recent REST klines (no orders emitted)."""
        url = (
            f"{self.config.rest_url}/api/v3/klines"
            f"?symbol={self.config.symbol}&interval={self.config.timeframe}"
            f"&limit={min(self.config.warmup_bars, 1000)}"
        )
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as resp:
                    rows = json.loads(await resp.text())
        except Exception as e:  # noqa: BLE001 - run degraded on cold indicators
            logger.warning("Warm-up fetch failed (%s); starting cold", e)
            return

        for row in rows[:-1] if rows else []:
            close = float(row[4])
            self._feed_strategy(close=float(row[2]), low=close, high=close, volume=float(row[5]))
        logger.info(
            "Warm-up fed %d %s %s bars to %s",
            len(rows) - 1 if rows else 0, self.config.symbol, self.config.timeframe,
            self.config.strategy,
        )

    async def _on_kline(self, event) -> None:
        """Handle a WS kline: only CLOSED bars of our symbol/timeframe trade."""
        if not isinstance(event, KlineEvent):
            return
        if event.symbol.upper() != self.config.symbol.upper():
            return
        if event.interval and event.interval != self.config.timeframe:
            return
        if not event.is_closed:
            return

        open_ms = int(event.open_time.timestamp() * 1000)
        if open_ms in self._seen_bars:
            return
        self._seen_bars.append(open_ms)

        self.stats["bars_seen"] += 1
        await self._handle_closed_bar(event)

    async def _handle_closed_bar(self, bar: KlineEvent) -> None:
        close = float(bar.close_price)
        if close <= 0:
            return
        self.stats["last_close"] = close

        orders = self._feed_strategy(
            close=close, high=float(bar.high_price),
            low=float(bar.low_price), volume=float(bar.volume),
        )
        if orders is None:
            return

        for order in orders if isinstance(orders, list) else [orders]:
            if order is None:
                continue
            self._engine.venue.prices[bar.symbol] = Decimal(str(close))
            from cryptobot.core.events import OrderStatus

            filled = await self._engine.submit_order(order)
            self.stats["orders_submitted"] += 1
            if filled.status in (OrderStatus.FILLED, OrderStatus.PARTIALLY_FILLED):
                self.stats["fills"] += 1
            elif filled.status == OrderStatus.REJECTED:
                self.stats["rejects"] += 1
            self.stats["last_order_at"] = time.time()

    def _feed_strategy(self, close: float, high: float, low: float, volume: float):
        """Dispatch to the strategy's feed signature (mirrors backtest runner)."""
        symbol = self.config.symbol
        self.stats["bars_fed"] += 1
        name = getattr(self.strategy, "name", "")
        if name == "trend_following":
            return self.strategy.feed(symbol, high, low, close)
        try:
            return self.strategy.feed(symbol, close, high, low, volume)
        except TypeError:
            return self.strategy.feed(symbol, close)


def _new_ws_client(config=None):
    """Indirection for tests (monkeypatch this to stub connectivity)."""
    from cryptobot.market_data.manager import BinanceWSClient

    if config is None:
        return BinanceWSClient()
    return BinanceWSClient(
        symbols=[config.symbol],
        timeframes=[config.timeframe],
        ws_url=config.data_ws_url,
    )


def _kline_event_type():
    from cryptobot.core.events import EventType

    return EventType.KLINE


__all__ = ["LiveTrader", "LiveTraderConfig"]
