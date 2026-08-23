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
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import aiohttp

from cryptobot.backtest.runner import make_strategy
from cryptobot.core.allocator import CapitalAllocator, default_tiers
from cryptobot.core.breaker import BreakerConfig, CircuitBreaker
from cryptobot.core.bus import get_event_bus
from cryptobot.core.events import KlineEvent, OrderEvent, OrderSide, OrderStatus
from cryptobot.core.fund import FundConfig, GlobalFundLedger
from cryptobot.core.gate import GateConfig, PaperGateTracker
from cryptobot.core.portfolio import PortfolioManager, PortfolioMode
from cryptobot.core.profiles import get_profile
from cryptobot.core.tax import TaxEngine
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
    tax_state_path: str = "state/tax_engine.json"
    gate_state_path: str = "state/paper_gate.json"
    gate_enabled: bool = True
    risk_profile: str = "realistic"
    breaker_state_path: str = "state/breaker.json"
    protective_stop_pct: float = 10.0  # exchange-native stop this far below/above entry
    initial_equity: str = "10000"      # seeded when a fresh paper account starts at 0
    risk_fraction: float = 1.0         # equity fraction per entry (flip orders x2)


class LiveTrader:
    """Event-driven trading process: klines in, risk-checked orders out."""

    def __init__(self, config: LiveTraderConfig):
        self.config = config
        self.strategy = make_strategy(config.strategy, **config.strategy_params)
        logger.info("strategy %s effective config: %s",
                    config.strategy, self.strategy.config)

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
        self._trade_log: deque[dict] = deque(maxlen=100)
        self._price_history: deque[tuple[str, float]] = deque(maxlen=400)
        self._net_qty: dict[str, Decimal] = {}  # symbol -> net position (live book)
        self._fund = GlobalFundLedger(FundConfig(
            skim_fraction=Decimal(config.skim_fraction),
            state_path=config.fund_state_path,
        ))
        self._last_harvested_realized = Decimal("0")
        self._harvest_task: asyncio.Task | None = None
        self._gate = PaperGateTracker(GateConfig(state_path=config.gate_state_path)) \
            if config.gate_enabled else None
        self._profile = get_profile(config.risk_profile)
        self._breaker = CircuitBreaker(BreakerConfig(state_path=config.breaker_state_path))
        self._peak_equity = Decimal("0")
        self._allocator = CapitalAllocator(default_tiers())
        self._last_gate_day: date | None = None
        self._tax = TaxEngine()
        try:
            tax_file = Path(self.config.tax_state_path)
            if tax_file.exists():
                import json as _json
                self._tax.restore(_json.loads(tax_file.read_text(encoding="utf-8")))
        except Exception as exc:  # noqa: BLE001 - corrupt state must not kill startup
            logger.warning("tax state unreadable (%s); starting fresh", exc)
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
        snap["daily_pnl"] = str(state.daily_pnl)
        snap["peak_equity"] = str(state.peak_equity)
        snap["max_drawdown_pct"] = f"{float(state.max_drawdown) * 100:.1f}"
        curve = self._portfolio.get_equity_curve()
        snap["equity_curve"] = [
            {"ts": ts.isoformat(), "equity": str(v)} for ts, v in curve[-120:]
        ]
        snap["global_fund"] = self._fund.summary()
        snap["tax_summary"] = self._tax.summary()
        snap["recent_trades"] = list(self._trade_log)
        snap["price_history"] = [
            {"ts": ts, "close": c} for ts, c in self._price_history
        ]
        if self._gate is not None:
            snap["paper_gate"] = self._gate.summary()
        snap["risk_profile"] = self._profile.name
        try:
            _tier = self._allocator.tier_for(self._portfolio.get_state().total_equity)
            snap["allocator_tier"] = _tier.label if _tier else None
            config_strategy = getattr(self.config, "strategy", None)
            if _tier and config_strategy and config_strategy not in {s.name for s in _tier.strategies}:
                    snap["allocator_warning"] = (
                        f"strategy '{config_strategy}' is not active at this equity tier"
                    )
        except Exception:  # noqa: BLE001 - reporting only
            pass
        snap["breaker"] = self._breaker.summary()
        return snap

    def request_stop(self) -> None:
        self._stop.set()

    # -------------------------------------------------------------- lifecycle

    async def run(self) -> None:
        """Run until :meth:`request_stop` (or ``max_bars`` reached)."""
        ws = _new_ws_client(self.config)
        await self._portfolio.initialize()
        # A fresh paper account starts at equity 0, which would make the
        # paper gate's net-positive criterion unsatisfiable forever.
        if self.config.mode != "live" and self._portfolio.get_state().total_equity <= 0:
            seed = Decimal(self.config.initial_equity)
            await self._portfolio.update_equity(seed)
            # A stale persisted baseline (0) would book the whole seed as
            # "today's P&L"; reset so day one starts flat.
            self._portfolio.reset_daily_pnl()
            logger.info("seeded fresh paper portfolio with equity %s", seed)
        self._health.start()
        self._install_health_snapshot()

        try:
            self._harvest_task = asyncio.create_task(self._harvest_loop())
            if self.config.warmup_bars > 0:
                await self._warm_up()
                # Warmup fed history through the strategy and advanced its
                # internal position state without placing any orders. Reset
                # to flat so the first live signal is a plain entry, not a
                # 2x flip against a leg that does not exist.
                self._reset_strategy_state()
                logger.info("strategy state reset to flat after warmup")

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
                self._record_gate_day()
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
            ts_iso = datetime.fromtimestamp(
                int(row[0]) / 1000, tz=UTC).isoformat(timespec="seconds")
            self._price_history.append((ts_iso, close))
            self._feed_strategy(close=close, low=close, high=close, volume=float(row[5]))
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
        self._price_history.append(
            (bar.timestamp.isoformat(timespec="seconds") if getattr(bar, "timestamp", None)
             else datetime.now(UTC).isoformat(timespec="seconds"), close))

        if self._check_breaker():
            return  # breaker tripped: no new entries

        orders = self._feed_strategy(
            close=close, high=float(bar.high_price),
            low=float(bar.low_price), volume=float(bar.volume),
        )
        if orders is None:
            return

        for order in orders if isinstance(orders, list) else [orders]:
            if order is None:
                continue
            self._rescale_order(order, Decimal(str(close)))
            self._engine.venue.prices[bar.symbol] = Decimal(str(close))

            filled = await self._engine.submit_order(order)
            self.stats["orders_submitted"] += 1
            if filled.status == OrderStatus.FILLED and filled.filled_quantity > 0:
                self._record_tax_fill(filled)
                self._record_trade(filled)
                self._update_position_book(filled)
                self._place_protective_stop(filled, Decimal(str(close)))
            if filled.status in (OrderStatus.FILLED, OrderStatus.PARTIALLY_FILLED):
                self.stats["fills"] += 1
            elif filled.status == OrderStatus.REJECTED:
                self.stats["rejects"] += 1
                logger.warning("ORDER REJECTED %s %s qty=%s reason=%s",
                               order.side.value, order.symbol, order.quantity,
                               filled.payload.get("error"))
            self.stats["last_order_at"] = time.time()

    def _place_protective_stop(self, order, ref_price: Decimal) -> None:
        """Exchange-side stop so a dead host cannot leave naked positions."""
        pct = self.config.protective_stop_pct
        if pct <= 0 or order.reduce_only:
            return
        if order.side == OrderSide.BUY:
            stop = ref_price * (1 - Decimal(str(pct)) / 100)
            close_side = "sell"
        else:
            stop = ref_price * (1 + Decimal(str(pct)) / 100)
            close_side = "buy"
        qty = float(order.filled_quantity)

        async def _submit():
            try:
                await self._engine.venue.place_protective_stop(
                    order.symbol, close_side, qty, float(stop))
            except Exception as exc:  # noqa: BLE001 - venue may not support it
                logger.warning("protective stop skipped for %s: %s", order.symbol, exc)

        asyncio.get_event_loop().create_task(_submit())

    def _rescale_order(self, order, close: Decimal) -> None:
        """Equity-fractional sizing, mirroring BacktestEngine._run_orders.

        Catalog strategies emit unit quantity (1 BTC); without this the live
        path submitted ~$76k orders against a $10k account and risk rejected
        every single one.
        """
        venue_book = getattr(self._engine.venue, "_position_qty", {})
        current_qty = abs(venue_book.get(order.symbol, 0))
        order.payload["current_notional"] = float(current_qty * close)

        rf = self.config.risk_fraction
        if rf <= 0 or order.quantity <= 0:
            return
        equity = self._portfolio.get_state().total_equity
        if equity <= 0 or close <= 0:
            return
        if order.reduce_only:
            # Close the whole open leg regardless of nominal size.
            venue_qty = getattr(self._engine.venue, "_position_qty", {}).get(order.symbol)
            if venue_qty:
                order.quantity = abs(venue_qty)
            return
        mult = Decimal(2) if order.payload.get("flip") else Decimal(1)
        order.quantity = Decimal(str(round(rf * float(equity / close) * float(mult), 8)))

    def _update_position_book(self, order) -> None:
        """Keep StateManager's position book in sync with live fills.

        Nothing else wired this in the paper path, so risk checks that read
        positions (flip netting, exposure) saw an empty book.
        """
        from cryptobot.core.events import PositionSide
        from cryptobot.core.state import Position, StateManager

        signed = order.filled_quantity * (
            Decimal(1) if order.side == OrderSide.BUY else Decimal(-1))
        net = self._net_qty.get(order.symbol, Decimal("0")) + signed
        self._net_qty[order.symbol] = net
        sm = StateManager()
        if net == 0:
            pos = sm.get_positions()
            for existing in pos:
                if existing.symbol == order.symbol:
                    sm._positions.pop(order.symbol, None)
            return
        avg = order.avg_fill_price or order.price or Decimal("0")
        sm.save_position(Position(
            symbol=order.symbol,
            side=PositionSide.LONG if net > 0 else PositionSide.SHORT,
            quantity=abs(net),
            entry_price=avg,
            mark_price=avg,
            strategy=order.strategy or self.config.strategy,
        ))

    def _reset_strategy_state(self) -> None:
        if hasattr(self.strategy, "reset"):
            self.strategy.reset(self.config.symbol)

    def _record_trade(self, order) -> None:
        """Append every executed fill to the live trade tape (dashboard+log)."""
        qty = float(order.filled_quantity)
        price = float(order.avg_fill_price or order.price or 0)
        entry = {
            "ts": datetime.now(UTC).isoformat(timespec="seconds"),
            "symbol": order.symbol,
            "side": order.side.value if hasattr(order.side, "value") else str(order.side),
            "qty": qty,
            "price": price,
            "notional": round(qty * price, 2),
            "strategy": order.strategy or self.config.strategy,
        }
        self._trade_log.appendleft(entry)
        logger.info(
            "TRADE %s %s %s %s @ %s (notional %.2f)",
            entry["ts"], entry["side"], qty, entry["symbol"], price, entry["notional"],
        )

    def _record_gate_day(self) -> None:
        """Once per UTC day, feed equity/order stats to the paper-gate tracker."""
        if self._gate is None:
            return
        today = datetime.now(UTC).date()
        if today == self._last_gate_day:
            return
        self._last_gate_day = today
        try:
            state = self._portfolio.get_state()
            self._gate.record_day(
                state.total_equity,
                int(self.stats["orders_submitted"]),
                int(self.stats["rejects"]),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("gate snapshot failed: %s", exc)

    def _record_tax_fill(self, order) -> None:
        """Feed executed fills into the VDA tax ledger (FIFO, §115BBH)."""
        try:
            qty = order.filled_quantity
            price = order.avg_fill_price or order.price or Decimal("0")
            now = datetime.now(UTC)
            if order.side == OrderSide.BUY:
                self._tax.buy(order.symbol, qty, price, now)
            else:
                self._tax.sell(order.symbol, qty, price * qty, now)
            Path(self.config.tax_state_path).parent.mkdir(parents=True, exist_ok=True)
            Path(self.config.tax_state_path).write_text(
                json.dumps(self._tax.to_dict()), encoding="utf-8")
        except Exception as exc:  # noqa: BLE001 - tax bookkeeping must not kill trading
            logger.warning("tax fill recording failed: %s", exc)

    def _check_breaker(self) -> bool:
        """Update peak/drawdown; trip -> graceful profit-first close. True if tripped."""
        state = self._portfolio.get_state()
        equity = state.total_equity
        if equity > self._peak_equity:
            self._peak_equity = equity
        if not self._breaker.check(self._peak_equity, equity):
            return self._breaker.tripped

        dd = (equity - self._peak_equity) / self._peak_equity * 100
        self._breaker.trip(f"drawdown {dd:.1f}% from peak {self._peak_equity}",
                           now_iso=datetime.now(UTC).isoformat())
        self.stats["breaker"] = self._breaker.summary()
        if self._gate is not None:
            self._gate.breaker_trips += 1
            self._gate.save()
        if not self._fund.frozen:
            self._fund.freeze()
        asyncio.get_event_loop().create_task(self._graceful_close())
        return True

    async def _graceful_close(self) -> None:
        """Close open positions profit-first (agreed -25% protocol)."""
        from cryptobot.core.events import OrderSide, OrderType
        from cryptobot.core.state import StateManager

        try:
            positions = StateManager().get_positions()
        except Exception as exc:  # noqa: BLE001
            logger.warning("graceful close scan failed: %s", exc)
            return
        ordered = CircuitBreaker.close_order([
            {"symbol": pos.symbol, "side": str(pos.side),
             "quantity": pos.quantity, "unrealized_pnl": pos.unrealized_pnl}
            for pos in positions if pos.quantity > 0
        ])
        logger.error("graceful close: flattening %d positions profit-first", len(ordered))
        for pos in ordered:
            try:
                close_order = OrderEvent(
                    symbol=pos["symbol"],
                    side=OrderSide.SELL,
                    type=OrderType.MARKET,
                    quantity=Decimal(str(pos["quantity"])),
                    reduce_only=True,
                    strategy="breaker",
                )
                await self._engine.submit_order(close_order)
            except Exception as exc:  # noqa: BLE001
                logger.warning("close order failed for %s: %s", pos["symbol"], exc)

    def _feed_strategy(self, close: float, high: float, low: float, volume: float):
        if self._breaker.tripped:
            self.stats["bars_fed"] += 1  # keep counting bars; entries halted
            return
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
