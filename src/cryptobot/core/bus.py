from __future__ import annotations
import asyncio
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional, Set, Callable, List, Dict, Union

from cryptobot.core.events import Event, EventType


class EventBusMode(str, Enum):
    LOCAL = "local"
    REDIS = "redis"


@dataclass
class Subscription:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_types: Set[str] = field(default_factory=set)
    callback: Optional[Callable[[Event], Any]] = None
    async_callback: Optional[Callable[[Event], Any]] = None
    wildcard: bool = False
    filter_fn: Optional[Callable[[Event], bool]] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    event_count: int = 0


class EventBus:
    def __init__(self, max_history: int = 10000, mode: EventBusMode = EventBusMode.LOCAL):
        if mode == EventBusMode.REDIS:
            raise NotImplementedError("Redis-backed event bus not implemented in this build")
        self.mode = mode
        self._subscriptions: Dict[str, Subscription] = {}
        self._type_index: Dict[EventType, Set[str]] = defaultdict(set)
        self._wildcard_subs: Set[str] = set()
        self._history: deque = deque(maxlen=max_history)
        self._lock = asyncio.Lock()
        self._max_history = max_history
        self._closed = False

    def _normalize_event_type(self, event_type: Union[EventType, str]) -> tuple[Optional[EventType], bool]:
        if isinstance(event_type, EventType):
            if event_type == EventType.ALL:
                return None, True
            return event_type, False
        if event_type == "*" or event_type == "all" or event_type == EventType.ALL:
            return None, True
        try:
            return EventType(event_type), False
        except (ValueError, KeyError):
            return None, True

    async def subscribe(
        self,
        event_type: Union[EventType, str],
        callback: Optional[Callable[[Event], Any]] = None,
        async_callback: Optional[Callable[[Event], Any]] = None,
        filter_fn: Optional[Callable[[Event], bool]] = None,
        filter: Optional[Callable[[Event], bool]] = None,
    ) -> str:
        et, wildcard = self._normalize_event_type(event_type)
        effective_filter = filter_fn if filter_fn is not None else filter
        sub_id = str(uuid.uuid4())
        async with self._lock:
            sub = Subscription(
                id=sub_id,
                callback=callback,
                async_callback=async_callback,
                wildcard=wildcard,
                filter_fn=effective_filter,
            )
            if wildcard:
                sub.event_types = set()
                self._wildcard_subs.add(sub_id)
            else:
                assert et is not None
                sub.event_types = {et}
                self._type_index[et].add(sub_id)
            self._subscriptions[sub_id] = sub
        return sub_id

    async def unsubscribe(self, sub_id: str) -> bool:
        async with self._lock:
            sub = self._subscriptions.pop(sub_id, None)
            if sub is None:
                return False
            self._wildcard_subs.discard(sub_id)
            for et in sub.event_types:
                if et in self._type_index:
                    self._type_index[et].discard(sub_id)
                    if not self._type_index[et]:
                        del self._type_index[et]
            return True

    async def publish(self, event_or_topic: Union[Event, str], payload: Optional[dict] = None) -> int:
        if isinstance(event_or_topic, Event):
            event = event_or_topic
        else:
            if payload is None:
                raise TypeError("publish_raw requires (topic, payload)")
            et, _ = self._normalize_event_type(event_or_topic)
            if et is None:
                et = EventType.ERROR
            event = Event(type=et, payload=payload or {})
        return await self._dispatch(event)

    async def publish_raw(self, topic: str, payload: dict) -> int:
        et, _ = self._normalize_event_type(topic)
        if et is None:
            et = EventType.ERROR
        return await self._dispatch(Event(type=et, payload=payload or {}))

    async def publish_batch(self, events: List[Event]) -> int:
        total = 0
        for event in events:
            total += await self._dispatch(event)
        return total

    async def _dispatch(self, event: Event) -> int:
        async with self._lock:
            self._history.append(event)
            target_ids: Set[str] = set(self._type_index.get(event.type, set()))
            target_ids.update(self._wildcard_subs)
            subs = [self._subscriptions[sid] for sid in target_ids if sid in self._subscriptions]

        delivered = 0
        for sub in subs:
            if sub.filter_fn and not sub.filter_fn(event):
                continue
            try:
                if sub.async_callback:
                    await sub.async_callback(event)
                elif sub.callback:
                    result = sub.callback(event)
                    if asyncio.iscoroutine(result):
                        await result
                sub.event_count += 1
                delivered += 1
            except Exception as e:
                import logging

                logging.getLogger(__name__).exception("Error in subscriber %s: %s", sub.id, e)
        return delivered

    def get_history(self, limit: int = 100, event_type: Optional[Union[EventType, str]] = None) -> List[Event]:
        history = list(self._history)
        if event_type is not None:
            et, wildcard = self._normalize_event_type(event_type)
            if wildcard:
                return history[-limit:]
            assert et is not None
            history = [e for e in history if e.type == et]
        return history[-limit:]

    def get_subscribers(self, event_type: Optional[EventType] = None) -> List[Subscription]:
        if event_type is None:
            return list(self._subscriptions.values())
        return [
            self._subscriptions[sid]
            for sid in self._type_index.get(event_type, set())
        ]

    def get_subscriber_count(self, event_type: Optional[EventType] = None) -> int:
        if event_type:
            return len(self._type_index.get(event_type, set()))
        return len(self._subscriptions)

    async def close(self):
        async with self._lock:
            self._subscriptions.clear()
            self._type_index.clear()
            self._wildcard_subs.clear()
            self._history.clear()
            self._closed = True

    @property
    def is_closed(self) -> bool:
        return self._closed

    @asynccontextmanager
    async def replay(self, from_event: Optional[Event] = None, limit: int = 1000):
        history = self.get_history(limit=limit)
        if from_event:
            history = [e for e in history if e.timestamp > from_event.timestamp]
        yield history


_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    global _bus
    if _bus is None or _bus.is_closed:
        _bus = EventBus()
    return _bus


async def init_event_bus(max_history: int = 10000) -> EventBus:
    global _bus
    _bus = EventBus(max_history=max_history)
    return _bus


async def close_event_bus() -> None:
    global _bus
    if _bus is not None:
        await _bus.close()
        _bus = None
