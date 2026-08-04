from __future__ import annotations

import threading
import time
from collections import deque


class RateLimiter:
    """Sliding-window rate limiter for order submissions."""

    def __init__(self, max_events: int, window_seconds: float = 60.0):
        if max_events <= 0 or window_seconds <= 0:
            raise ValueError("max_events and window_seconds must be > 0")
        self._max_events = max_events
        self._window = window_seconds
        self._timestamps: deque[float] = deque()
        self._lock = threading.Lock()

    def try_acquire(self, now: float | None = None) -> bool:
        ts = time.time() if now is None else now
        with self._lock:
            self._evict(ts)
            if len(self._timestamps) >= self._max_events:
                return False
            self._timestamps.append(ts)
            return True

    def reset(self) -> None:
        with self._lock:
            self._timestamps.clear()

    def _evict(self, now: float) -> None:
        cutoff = now - self._window
        while self._timestamps and self._timestamps[0] < cutoff:
            self._timestamps.popleft()

    @property
    def current_count(self) -> int:
        with self._lock:
            self._evict(time.time())
            return len(self._timestamps)


__all__ = ["RateLimiter"]
