"""Live paper-trading harness for the funding-carry edge.

Subscribes to public Binance streams (no API keys required):
  - spot ``<sym>@bookTicker``  -> best bid/ask of the spot leg
  - futures ``<sym>@markPrice@1m`` -> perp mark price + live funding rate

Feeds the ``FundingArbStrategy`` with the merged state and logs every signal
(entry/exit) plus a daily PnL estimate to a local CSV so the regime-dependent
funding-carry edge can be observed live without risking capital.

Run from the CLI:
    python -m cryptobot.cli.main paper-funder --hours 24

The stream URLs default to Binance public endpoints; override with
``--spot-ws`` / ``--futures-ws`` for testing against a replay server.
"""

from __future__ import annotations

import asyncio
import csv
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from cryptobot.strategies.funding_arb import (
    FundingArbConfig,
    FundingArbState,
    FundingArbStrategy,
)

logger = logging.getLogger(__name__)

SPOT_WS = "wss://stream.binance.com:9443/stream?streams="
FUTURES_WS = "wss://fstream.binance.com/stream?streams="


@dataclass
class PaperState:
    """Running paper position + realized estimate for one symbol."""

    symbol: str
    in_position: bool = False
    entry_basis_bps: float = 0.0
    entry_ts: datetime | None = None
    carry_bps: float = 0.0
    n_trips: int = 0
    last_action: str = "startup"
    last_ts: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_row(self) -> dict:
        return {
            "ts": self.last_ts.isoformat(),
            "symbol": self.symbol,
            "in_position": self.in_position,
            "entry_basis_bps": round(self.entry_basis_bps, 2),
            "carry_bps": round(self.carry_bps, 2),
            "n_trips": self.n_trips,
            "last_action": self.last_action,
        }


class FundingPaperHarness:
    """Merges spot + perp WS updates and drives the funding strategy.

    ``process_spot`` / ``process_perp`` accept parsed JSON messages so the
    harness is fully unit-testable without a live connection.
    """

    def __init__(
        self,
        symbols: list[str] = ("BTCUSDT", "ETHUSDT"),
        strategy: FundingArbStrategy | None = None,
        log_path: str | Path = "paper_funding.csv",
    ):
        self.symbols = list(symbols)
        self.strategy = strategy or FundingArbStrategy(FundingArbConfig())
        self.log_path = Path(log_path)
        self.states: dict[str, PaperState] = {s: PaperState(symbol=s) for s in self.symbols}
        self._spot_price: dict[str, Decimal] = {}
        self._perp_price: dict[str, Decimal] = {}
        self._funding_rate: dict[str, float] = {}
        self._logger = logger.getChild("paper")
        self._signal_count = 0

    # -- message ingestion -------------------------------------------------

    def process_spot_message(self, sym: str, msg: dict) -> None:
        """Parse a spot ``bookTicker`` message and re-evaluate the symbol."""
        bid = msg.get("b") or msg.get("bid")
        ask = msg.get("a") or msg.get("ask")
        if bid is None or ask is None:
            return
        try:
            mid = (Decimal(str(bid)) + Decimal(str(ask))) / Decimal("2")
        except (ValueError, ArithmeticError):
            return
        if mid <= 0:
            return
        self._spot_price[sym] = mid
        self._evaluate(sym)

    def process_perp_message(self, sym: str, msg: dict) -> None:
        """Parse a futures ``markPriceUpdate`` message."""
        mark = msg.get("p") or msg.get("markPrice")
        rate = msg.get("r") or msg.get("fundingRate")
        if mark is None:
            return
        try:
            self._perp_price[sym] = Decimal(str(mark))
            if rate is not None:
                self._funding_rate[sym] = float(rate)
        except (ValueError, ArithmeticError):
            return
        self._evaluate(sym)

    def process_json_message(self, msg: dict) -> None:
        """Dispatch a raw stream JSON payload (from the combined stream)."""
        stream = msg.get("stream", "")
        data = msg.get("data", msg)
        for sym in self.symbols:
            if stream.endswith(f"{sym.lower()}@bookTicker"):
                self.process_spot_message(sym, data)
            elif stream.endswith(f"{sym.lower()}@markPrice@1m"):
                self.process_perp_message(sym, data)

    # -- evaluation ----------------------------------------------------------

    def _evaluate(self, sym: str) -> None:
        spot = self._spot_price.get(sym)
        perp = self._perp_price.get(sym)
        rate = self._funding_rate.get(sym)
        if spot is None or perp is None or rate is None or spot <= 0:
            return
        state = FundingArbState(
            spot_price=spot,
            perp_price=perp,
            funding_rate=rate,
            next_funding_seconds=0.0,
        )
        action = self.strategy.feed(state)
        self._apply_signal(sym, action, state)

    def _apply_signal(self, sym: str, action, state: FundingArbState) -> None:
        st = self.states[sym]
        now = datetime.now(UTC)
        basis = float((state.perp_price - state.spot_price) / state.spot_price) * 10_000.0
        cfg = self.strategy.config
        action_name = "none"
        # The strategy re-emits enter/exit tuples whenever the threshold holds,
        # so gate on position state to avoid spurious duplicate signals.
        if action is not None and not st.in_position and basis >= cfg.basis_entry_bps:
            action_name = "enter"
        elif action is not None and st.in_position and basis <= cfg.basis_exit_bps:
            action_name = "exit"
        if action_name == "enter":
            st.in_position = True
            st.entry_basis_bps = basis
            st.entry_ts = now
            st.last_action = f"enter_basis_{basis:.1f}"
            self._signal_count += 1
            self._logger.info(
                "SIGNAL %s enter basis=%.2fbps funding=%.4f%%",
                sym, basis, state.funding_rate * 100,
            )
            self._append_log_row(sym, st, basis, state.funding_rate, "ENTER")
        elif action_name == "exit":
            st.in_position = False
            st.n_trips += 1
            st.last_action = f"exit_basis_{basis:.1f}"
            self._signal_count += 1
            self._logger.info(
                "SIGNAL %s exit basis=%.2fbps funding=%.4f%% entry_basis=%.2f",
                sym, basis, state.funding_rate * 100, st.entry_basis_bps,
            )
            self._append_log_row(sym, st, basis, state.funding_rate, "EXIT")
        elif st.in_position:
            # accumulate carry while in position (8h cadence assumed)
            st.carry_bps += state.funding_rate * 10_000.0
            st.last_action = "in_position_carry"
        else:
            st.last_action = "no_signal"

        st.last_ts = now

    def _append_log_row(self, sym: str, st: PaperState, basis: float, rate: float, kind: str) -> None:
        new_file = not self.log_path.exists()
        with self.log_path.open("a", newline="") as f:
            writer = csv.writer(f)
            if new_file:
                writer.writerow(["ts", "symbol", "kind", "basis_bps", "funding_pct", "carry_bps", "n_trips"])
            writer.writerow([
                datetime.now(UTC).isoformat(), sym, kind,
                round(basis, 2), round(rate * 100, 4), round(st.carry_bps, 2), st.n_trips,
            ])

    # -- live loop -------------------------------------------------------------

    async def run(
        self,
        hours: float = 24,
        spot_ws: str | None = None,
        futures_ws: str | None = None,
        poll_fapi: bool = False,
        poll_interval_s: float = 5.0,
        rest_base: str = "https://fapi.binance.com",
    ) -> None:
        """Run the monitor for ``hours`` (0 = forever).

        Uses two live legs by default (spot + futures WebSocket). Some networks
        block the futures WS endpoint; pass ``poll_fapi=True`` to fetch perp
        mark/funding via the public REST ``premiumIndex`` endpoint instead.
        """
        import aiohttp

        spot_ws = spot_ws or SPOT_WS + "/".join(f"{s.lower()}@bookTicker" for s in self.symbols)
        futures_ws = futures_ws or FUTURES_WS + "/".join(f"{s.lower()}@markPrice@1m" for s in self.symbols)
        deadline = None if hours <= 0 else time.monotonic() + hours * 3600

        async with aiohttp.ClientSession() as session:
            tasks = [asyncio.create_task(self._consume(session, spot_ws, "spot"))]
            if poll_fapi:
                tasks.append(asyncio.create_task(self._poll_fapi(session, poll_interval_s, rest_base)))
            else:
                tasks.append(asyncio.create_task(self._consume(session, futures_ws, "futures")))
            try:
                while deadline is None or time.monotonic() < deadline:
                    await asyncio.sleep(1)
            finally:
                for t in tasks:
                    t.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)

    async def _poll_fapi(self, session, interval_s: float, base: str) -> None:
        """Poll public REST ``premiumIndex`` for perp mark + funding rate."""
        for sym in self.symbols:
            url = f"{base}/fapi/v1/premiumIndex?symbol={sym}"
            while True:
                try:
                    async with session.get(url, timeout=10) as resp:
                        if resp.status != 200:
                            raise RuntimeError(f"HTTP {resp.status}")
                        data = await resp.json()
                    mark = data.get("markPrice")
                    rate = data.get("lastFundingRate")
                    if mark is not None:
                        self._perp_price[sym] = Decimal(str(mark))
                        if rate is not None:
                            self._funding_rate[sym] = float(rate)
                        self._evaluate(sym)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # noqa: BLE001 - keep polling
                    self._logger.warning("fapi poll %s error: %s", sym, exc)
                await asyncio.sleep(interval_s)

    async def _consume(self, session, url: str, kind: str) -> None:

        backoff = 1.0
        while True:
            try:
                async with session.ws_connect(url, heartbeat=20) as ws:
                    backoff = 1.0
                    self._logger.info("connected %s stream: %s", kind, url)
                    async for wrapped in ws:
                        try:
                            msg = json.loads(wrapped.data)
                        except (TypeError, ValueError):
                            continue
                        self.process_json_message(msg)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - reconnect on any failure
                self._logger.warning("%s stream error: %s; reconnecting in %.0fs", kind, exc, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)


__all__ = ["FundingPaperHarness", "PaperState"]
