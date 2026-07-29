from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Awaitable, Callable, Dict, List, Optional, Sequence

from cryptobot.core.events import OrderEvent, OrderSide
from cryptobot.execution.venue.base import Venue


Ranker = Callable[[str, Sequence["VenueScore"]], int]


@dataclass
class VenueScore:
    name: str
    venue: Venue
    price: Decimal
    latency_ms: float = 0.0
    fee_bps: Decimal = Decimal("0")
    liquidity_score: float = 1.0
    error: Optional[str] = None
    round_trip_ms: float = 0.0

    @property
    def score(self) -> float:
        if self.error:
            return float("-inf")
        latency_penalty = self.round_trip_ms
        fee_penalty = float(self.fee_bps)
        return float(self.price) - latency_penalty - fee_penalty


@dataclass
class RouterConfig:
    max_slippage_bps: Decimal = Decimal("20")
    max_latency_ms: float = 250.0
    quote_timeout_s: float = 1.0
    max_child_venues: int = 3


@dataclass
class RoutedOrder:
    parent: OrderEvent
    children: List[OrderEvent] = field(default_factory=list)
    fills: List[OrderEvent] = field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        return bool(self.fills) and sum((c.quantity for c in self.children), Decimal("0")) <= Decimal("0") or sum(
            (f.filled_quantity for f in self.fills), Decimal("0")
        ) >= self.parent.quantity


def best_price_ranker(symbol: str, scores: Sequence[VenueScore]) -> int:
    valid = [(i, s) for i, s in enumerate(scores) if s.error is None and s.price > 0]
    if not valid:
        return -1
    return min(valid, key=lambda kv: (float(kv[1].price), kv[1].latency_ms))[0]


def latency_aware_ranker(symbol: str, scores: Sequence[VenueScore]) -> int:
    valid = [(i, s) for i, s in enumerate(scores) if s.error is None and s.price > 0]
    if not valid:
        return -1
    return min(valid, key=lambda kv: (kv[1].score, kv[1].latency_ms))[0]


def best_effort_ranker(symbol: str, scores: Sequence[VenueScore]) -> int:
    return latency_aware_ranker(symbol, scores)


class SmartOrderRouter:
    """Pick the best venue for an order based on live quotes and route fills there."""

    def __init__(
        self,
        venues: Sequence[Venue],
        config: Optional[RouterConfig] = None,
        ranker: Ranker = best_price_ranker,
        fee_overrides: Optional[Dict[str, Decimal]] = None,
    ):
        if not venues:
            raise ValueError("SmartOrderRouter requires at least one venue")
        self.venues: List[Venue] = list(venues)
        self.config = config or RouterConfig()
        self.ranker = ranker
        self.fee_overrides = dict(fee_overrides or {})
        for i, v in enumerate(self.venues):
            if not getattr(v, "name", None):
                v.name = f"venue_{i}"  # type: ignore[attr-defined]

    async def _quote(self, venue: Venue, symbol: str) -> VenueScore:
        name: str = getattr(venue, "name", "venue")  # type: ignore[attr-defined]
        fee = self.fee_overrides.get(name, Decimal("0"))
        start = time.perf_counter()
        try:
            price = await asyncio.wait_for(venue.get_price(symbol), timeout=self.config.quote_timeout_s)
            latency_ms = (time.perf_counter() - start) * 1000.0
            if price <= 0:
                return VenueScore(name=name, venue=venue, price=Decimal("0"), latency_ms=latency_ms, fee_bps=fee, error="no quote")
            return VenueScore(
                name=name,
                venue=venue,
                price=Decimal(str(price)),
                latency_ms=latency_ms,
                fee_bps=fee,
            )
        except Exception as exc:
            latency_ms = (time.perf_counter() - start) * 1000.0
            return VenueScore(name=name, venue=venue, price=Decimal("0"), latency_ms=latency_ms, fee_bps=fee, error=str(exc))

    async def quote_all(self, symbol: str) -> List[VenueScore]:
        scores = await asyncio.gather(*(self._quote(v, symbol) for v in self.venues))
        return list(scores)

    def pick(self, scores: Sequence[VenueScore]) -> Optional[VenueScore]:
        idx = self.ranker(symbol="", scores=scores)
        return scores[idx] if idx >= 0 else None

    async def route(self, order: OrderEvent) -> RoutedOrder:
        routed = RoutedOrder(parent=order)
        scores = await self.quote_all(order.symbol)
        chosen = self.pick(scores)
        if chosen is None:
            return routed
        child = OrderEvent(
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            price=order.price,
            type=order.type,
            strategy=order.strategy,
            client_order_id=order.client_order_id,
        )
        routed.children.append(child)
        try:
            filled = await asyncio.wait_for(
                chosen.venue.submit_order(child),
                timeout=self.config.quote_timeout_s * 4,
            )
            routed.fills.append(filled)
        except Exception:
            for fallback_score in scores:
                if fallback_score is chosen or fallback_score.error:
                    continue
                if fallback_score.venue is chosen.venue:
                    continue
                fallback_child = OrderEvent(
                    symbol=order.symbol,
                    side=order.side,
                    quantity=order.quantity,
                    price=order.price,
                    type=order.type,
                    strategy=order.strategy,
                    client_order_id=order.client_order_id,
                )
                routed.children.append(fallback_child)
                try:
                    filled = await fallback_score.venue.submit_order(fallback_child)
                    routed.fills.append(filled)
                    break
                except Exception:
                    continue
        return routed

    async def split_and_route(
        self,
        parent: OrderEvent,
        ratio: Sequence[Decimal],
    ) -> RoutedOrder:
        if not ratio:
            return await self.route(parent)
        if len(ratio) > len(self.venues):
            raise ValueError("ratio longer than number of venues")
        if sum(ratio, Decimal("0")) <= 0:
            raise ValueError("ratio must sum to a positive quantity")
        scores = await self.quote_all(parent.symbol)
        ordered = sorted(
            ((i, s) for i, s in enumerate(scores) if s.error is None and s.price > 0),
            key=lambda kv: kv[1].score if kv[1].error is None else float("inf"),
        )
        if not ordered:
            return RoutedOrder(parent=parent)
        total = sum(ratio)
        routed = RoutedOrder(parent=parent)
        for n, (idx, score) in enumerate(ordered[: len(ratio)]):
            qty = (parent.quantity * ratio[n] / total).quantize(Decimal("0.0001"))
            if qty <= 0:
                continue
            child = OrderEvent(
                symbol=parent.symbol,
                side=parent.side,
                quantity=qty,
                price=parent.price,
                type=parent.type,
                strategy=parent.strategy,
                client_order_id=f"{parent.client_order_id or 'split'}-{n}",
            )
            routed.children.append(child)
            try:
                filled = await score.venue.submit_order(child)
                routed.fills.append(filled)
            except Exception:
                continue
        return routed


__all__ = [
    "RouterConfig",
    "RoutedOrder",
    "SmartOrderRouter",
    "VenueScore",
    "best_effort_ranker",
    "best_price_ranker",
    "latency_aware_ranker",
]
