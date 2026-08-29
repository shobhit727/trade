from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from cryptobot.core.events import OrderEvent


class AdverseAction(Enum):
    NONE = "none"
    CANCEL = "cancel"
    REPLACE = "replace"


logger = logging.getLogger(__name__)


@dataclass
class AdverseSelectionConfig:
    mid_move_bps: float = 5.0
    spread_widening_bps: float = 3.0
    book_imbalance_threshold: float = 0.65
    cancel_replace_extra_bps: float = 1.0
    toxicity_lookback: int = 30
    toxicity_threshold: float = 0.7


@dataclass
class QueuePosition:
    order_id: str
    symbol: str
    side: str
    price: Decimal
    quantity: Decimal
    placed_at_ms: float
    mid_at_place: Decimal
    spread_at_place: Decimal
    book_imbalance_at_place: float = 0.0

    def time_in_queue_ms(self, now_ms: float) -> float:
        return max(0.0, now_ms - self.placed_at_ms)

    def mid_distance_bps(self, mid_now: Decimal) -> float:
        if self.mid_at_place <= 0:
            return 0.0
        return float(abs(mid_now - self.mid_at_place) / self.mid_at_place) * 10_000.0


@dataclass
class TopOfBook:
    bid: Decimal
    ask: Decimal
    mid: Decimal
    spread_bps: float = 0.0
    imbalance: float = 0.0

    @classmethod
    def from_levels(cls, bids: list[Decimal], asks: list[Decimal], top_levels: int = 5) -> TopOfBook:
        if not bids or not asks:
            return cls(bid=Decimal("0"), ask=Decimal("0"), mid=Decimal("0"))
        bid = bids[0]
        ask = asks[0]
        mid = (bid + ask) / Decimal("2")
        spread_bps = float((ask - bid) / mid) * 10_000.0 if mid > 0 else 0.0
        bv = sum(bids[:top_levels])
        av = sum(asks[:top_levels])
        total = bv + av
        imbalance = float((bv - av) / total) if total > 0 else 0.0
        return cls(bid=bid, ask=ask, mid=mid, spread_bps=spread_bps, imbalance=imbalance)


class AdverseSelectionGuard:
    """Cancels / moves orders when the book shows toxic flow.

    Designed to be plugged into ``ExecutionEngine`` via ``execution_engine.adverse_guard = self``
    or directly call ``step(queue, snapshot)`` from a market-making strategy.
    """

    def __init__(self, config: AdverseSelectionConfig | None = None):
        self.config = config or AdverseSelectionConfig()
        self._positions: dict[str, QueuePosition] = {}
        self._toxicity_history: deque[float] = deque(maxlen=self.config.toxicity_lookback)
        self._last_toxicity = 0.0
        self._last_actions: list[str] = []

    def note_top(self, snapshot: TopOfBook) -> None:
        self._toxicity_history.append(abs(snapshot.imbalance))
        if self._toxicity_history:
            self._last_toxicity = sum(self._toxicity_history) / len(self._toxicity_history)

    def register(self, order: OrderEvent, top: TopOfBook) -> QueuePosition:
        now_ms = time.time() * 1000.0
        pos = QueuePosition(
            order_id=order.order_id or "",
            symbol=order.symbol,
            side=order.side.value,
            price=order.price or top.mid,
            quantity=order.quantity,
            placed_at_ms=now_ms,
            mid_at_place=top.mid,
            spread_at_place=Decimal(str(top.spread_bps)),
            book_imbalance_at_place=top.imbalance,
        )
        self._positions[order.order_id or ""] = pos
        return pos

    def step(self, order_id: str, top: TopOfBook) -> AdverseAction:
        pos = self._positions.get(order_id)
        if pos is None:
            return AdverseAction.NONE
        move_bps = pos.mid_distance_bps(top.mid)
        cfg = self.config
        toxic = self._last_toxicity
        action = AdverseAction.NONE

        spread_widened = (
            top.spread_bps - float(pos.spread_at_place)
            > cfg.spread_widening_bps
        )
        if move_bps >= cfg.mid_move_bps or spread_widened:
            action = AdverseAction.CANCEL
        elif (
            cfg.toxicity_threshold > 0
            and toxic >= cfg.toxicity_threshold
            and abs(top.imbalance - pos.book_imbalance_at_place)
            >= (1 - cfg.book_imbalance_threshold)
        ):
            action = AdverseAction.CANCEL

        if action is AdverseAction.CANCEL:
            self._last_actions.append("cancel")
        return action

    def decide_replace(
        self,
        pos: QueuePosition,
        top: TopOfBook,
        side: str,
    ) -> Decimal | None:
        if pos.quantity <= 0 or pos.mid_at_place <= 0:
            return None
        if pos.side == side:
            return pos.mid_at_place
        return None

    def forget(self, order_id: str) -> None:
        self._positions.pop(order_id, None)

    @property
    def last_toxicity(self) -> float:
        return self._last_toxicity

    @property
    def tracked(self) -> list[str]:
        return list(self._positions.keys())


def _install_guard_hook(engine, guard: AdverseSelectionGuard) -> None:
    """Wrap ``engine.submit_order`` so every filled order is registered with the
    adverse-selection guard at the most recent book top (``engine._last_top``).

    Idempotent: safe to call more than once. Raises ``TypeError`` if the engine
    lacks a ``cancel_order`` coroutine (the guard needs it to cancel toxic flow).
    """
    if not hasattr(engine, "cancel_order"):
        raise TypeError("expected object with cancel_order coroutine")

    engine.adverse_guard = guard  # type: ignore[attr-defined]
    original_submit = engine.submit_order
    if getattr(original_submit, "_adverse_wrapped", False):
        return

    async def wrapped(order: OrderEvent, *args, **kwargs) -> OrderEvent:
        filled = await original_submit(order, *args, **kwargs)
        top = getattr(engine, "_last_top", None)
        if top is not None:
            guard.register(order, top)
        return filled

    wrapped._adverse_wrapped = True  # type: ignore[attr-defined]
    engine.submit_order = wrapped  # type: ignore[assignment]


async def attach_to_engine(engine, guard: AdverseSelectionGuard) -> None:
    """Optional helper: register the adverse-selection guard on the engine's
    submit path. Every order submitted after this is auto-registered with the
    guard at the last known book top (``engine._last_top``), which the strategy
    sets via ``on_top``. Act on ``AdverseAction.CANCEL`` (from ``guard.step``)
    by calling ``engine.cancel_order(order_id)``.
    """
    _install_guard_hook(engine, guard)
    logger.debug("AdverseSelectionGuard attached to engine")


__all__ = [
    "AdverseAction",
    "AdverseSelectionConfig",
    "AdverseSelectionGuard",
    "QueuePosition",
    "TopOfBook",
    "attach_to_engine",
    "_install_guard_hook",
]
