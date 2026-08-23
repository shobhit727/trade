"""Multi-algorithm trader: N strategies, one symbol, one process.

Each algorithm trades its own equity slice (weight * total) with its own
position state — economics match running N separate bots, but they share one
websocket, one risk manager, one gate/tax/fund/breaker stack and one tape.

Weights are normalized to 1.0. Per-algo fills are tagged with the algo name so
the tape, tax ledger and sweep-style attribution stay per-algorithm.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from decimal import Decimal

from cryptobot.backtest.runner import make_strategy
from cryptobot.live.trader import LiveTrader, LiveTraderConfig

logger = logging.getLogger(__name__)


@dataclass
class AlgoSlot:
    """One algorithm's slice of the portfolio."""

    name: str
    params: dict = field(default_factory=dict)
    weight: float = 0.0            # normalized at construction
    strategy: object = None        # strategy instance
    net_qty: Decimal = Decimal("0")


@dataclass
class MultiAlgoConfig(LiveTraderConfig):
    algos: list[dict] = field(default_factory=list)   # [{"name","params","weight"}]

    def normalized(self) -> list[AlgoSlot]:
        raw = [a for a in self.algos if a.get("weight", 0) > 0]
        total = sum(a.get("weight", 0) for a in raw) or 1.0
        return [
            AlgoSlot(name=a["name"], params=dict(a.get("params") or {}),
                     weight=a["weight"] / total)
            for a in raw
        ]


class MultiAlgoTrader(LiveTrader):
    """Runs every configured algorithm against the same symbol/feed."""

    def __init__(self, config: MultiAlgoConfig):
        super().__init__(config)
        self.config: MultiAlgoConfig = config
        self.slots: list[AlgoSlot] = config.normalized()
        if not self.slots:
            raise ValueError("MultiAlgoTrader requires at least one algo with weight > 0")
        for slot in self.slots:
            slot.strategy = make_strategy(slot.name, **slot.params)
        # single-strategy plumbing unused
        self.strategy = self.slots[0].strategy
        logger.info("multi-algo: %s",
                    ", ".join(f"{s.name}({s.weight:.0%})" for s in self.slots))

    # ------------------------------------------------------------------ feed

    def _feed_strategy(self, close: float, high: float = None,
                       low: float = None, volume: float = None, **_kw):
        if self._breaker.tripped:
            self.stats["bars_fed"] += 1
            return None
        orders = []
        for slot in self.slots:
            o = slot.strategy.feed(self.config.symbol, close, high, low, volume)
            if o is None:
                continue
            o.strategy = slot.name          # attribute fills to this algo
            orders.append(o)
        self.stats["bars_fed"] += 1
        return orders or None

    def _rescale_order(self, order, close: Decimal) -> None:
        """Per-algo equity slice sizing with per-algo position state."""
        slot = next((s for s in self.slots if s.name == order.strategy),
                    self.slots[0])
        venue_book = getattr(self._engine.venue, "_position_qty", {})
        current_notional = float(abs(slot.net_qty) * close)
        order.payload["current_notional"] = current_notional

        rf = self.config.risk_fraction * slot.weight
        if order.reduce_only:
            order.quantity = abs(slot.net_qty)
            if order.quantity == 0:
                # nothing open for this algo: treat as no-op via tiny qty that
                # risk will reject on min size rather than corrupting state
                order.quantity = Decimal("0")
            return
        mult = Decimal(2) if order.payload.get("flip") else Decimal(1)
        equity = float(self._portfolio.get_state().total_equity)
        order.quantity = Decimal(str(round(rf * equity / float(close) * float(mult), 8)))

    def _update_position_book(self, order) -> None:
        """Shared-symbol book for risk plus per-algo net tracking."""
        from cryptobot.core.events import OrderSide

        signed = order.filled_quantity * (
            Decimal(1) if order.side == OrderSide.BUY else Decimal(-1))
        slot = next((s for s in self.slots if s.name == order.strategy), None)
        if slot is not None:
            slot.net_qty += signed
        super()._update_position_book(order)

    # warmup reset applies to every algo
    def _reset_strategy_state(self) -> None:
        for slot in self.slots:
            if hasattr(slot.strategy, "reset"):
                slot.strategy.reset(self.config.symbol)

    def stats_snapshot(self) -> dict:
        snap = super().stats_snapshot()
        snap["algos"] = [
            {"name": s.name, "weight": round(s.weight, 4),
             "net_qty": str(s.net_qty)}
            for s in self.slots
        ]
        return snap


def load_multi_config(base: LiveTraderConfig, path: str | None,
                      env_json: str | None) -> MultiAlgoConfig:
    """Build a MultiAlgoConfig from a JSON file or BOT_ALGOS env JSON."""
    src = path or env_json
    if not src:
        raise ValueError("no algo list given (--algos-json or BOT_ALGOS)")
    raw = Path(src).read_text(encoding="utf-8") if Path(src).exists() else src
    algos = json.loads(raw)
    cfg = MultiAlgoConfig(**{k: v for k, v in vars(base).items()
                             if k in MultiAlgoConfig.__dataclass_fields__})
    cfg.algos = algos
    return cfg


__all__ = ["AlgoSlot", "MultiAlgoConfig", "MultiAlgoTrader", "load_multi_config"]
