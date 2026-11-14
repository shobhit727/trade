from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    """Return the current timezone-aware UTC wall-clock time."""
    return datetime.now(UTC)


class ClockMode(StrEnum):
    REALTIME = "realtime"
    SIMULATED = "simulated"
    ACCELERATED = "accelerated"


@dataclass
class ClockConfig:
    mode: ClockMode = ClockMode.REALTIME
    start_time: datetime | None = None
    end_time: datetime | None = None
    speed_factor: float = 1.0
    tick_interval: float = 1.0
    timezone: str = "UTC"


class Clock:
    """Abstract base clock for time abstraction."""

    @property
    def mode(self) -> ClockMode:
        """Identify the time source implemented by this clock."""
        raise NotImplementedError

    def now(self) -> datetime:
        """Get current time."""
        raise NotImplementedError

    async def sleep(self, seconds: float):
        """Sleep for specified seconds."""
        raise NotImplementedError

    async def sleep_until(self, target: datetime):
        """Sleep until target time."""
        raise NotImplementedError


class RealtimeClock(Clock):
    """Real-time wall clock."""

    def __init__(self, timezone: str = "UTC"):
        """Create a wall-clock source; retain the requested timezone label."""
        self._timezone = timezone
        self._mode = ClockMode.REALTIME

    @property
    def mode(self) -> ClockMode:
        """Return the realtime clock mode."""
        return self._mode

    def now(self) -> datetime:
        """Return the current UTC wall-clock time."""
        return _utcnow()

    async def sleep(self, seconds: float):
        """Wait for the requested number of real seconds."""
        await asyncio.sleep(seconds)

    async def sleep_until(self, target: datetime):
        """Wait until the target time if it is later than the current time."""
        now = self.now()
        if target > now:
            await asyncio.sleep((target - now).total_seconds())


class SimulatedClock(Clock):
    """Simulated clock controlled by backtest engine."""

    def __init__(
        self,
        start_time: datetime,
        end_time: datetime | None = None,
        speed_factor: float = 1.0,
    ):
        """Initialize a controllable simulation clock and its waiting tasks."""
        self._current_time = start_time
        self._start_time = start_time
        self._end_time = end_time
        self._speed_factor = speed_factor
        self._mode = ClockMode.SIMULATED
        self._paused = False
        self._step_event = asyncio.Event()
        self._step_event.set()
        self._waiters: dict[datetime, list[asyncio.Future]] = {}
        self._lock = asyncio.Lock()

    @property
    def mode(self) -> ClockMode:
        """Return the simulated clock mode."""
        return self._mode

    @property
    def current_time(self) -> datetime:
        """Return the clock's current simulated timestamp."""
        return self._current_time

    @property
    def start_time(self) -> datetime:
        """Return the timestamp from which simulated elapsed time is measured."""
        return self._start_time

    @property
    def end_time(self) -> datetime | None:
        """Return the optional upper bound for simulated time."""
        return self._end_time

    @property
    def is_paused(self) -> bool:
        """Report whether calls that advance time are currently paused."""
        return self._paused

    def now(self) -> datetime:
        """Return the current simulated timestamp without advancing it."""
        return self._current_time

    def pause(self):
        """Pause time advancement."""
        self._paused = True
        self._step_event.clear()

    def resume(self):
        """Resume time advancement."""
        self._paused = False
        self._step_event.set()

    async def step(self, delta: timedelta) -> datetime:
        """Advance time by delta."""
        async with self._lock:
            if self._paused:
                await self._step_event.wait()

            new_time = self._current_time + delta

            if self._end_time and new_time >= self._end_time:
                new_time = self._end_time

            self._current_time = new_time
            await self._notify_waiters()

            return self._current_time

    async def step_to(self, target: datetime) -> datetime:
        """Advance time to target."""
        delta = target - self._current_time
        if delta.total_seconds() > 0:
            return await self.step(delta)
        return self._current_time

    async def _notify_waiters(self):
        """Notify all waiters whose target time has arrived."""
        ready = []
        for target, _futures in self._waiters.items():
            if target <= self._current_time:
                ready.append(target)

        for target in ready:
            futures_list = self._waiters.pop(target)
            for fut in futures_list:
                if not fut.done():
                    fut.set_result(self._current_time)

    async def sleep(self, seconds: float):
        """Virtual sleep."""
        target = self._current_time + timedelta(seconds=seconds)
        await self.sleep_until(target)

    async def sleep_until(self, target: datetime):
        """Virtual sleep until target time."""
        if target <= self._current_time:
            return

        fut = asyncio.get_running_loop().create_future()
        if target not in self._waiters:
            self._waiters[target] = []
        self._waiters[target].append(fut)

        try:
            await fut
        except asyncio.CancelledError:
            if target in self._waiters:
                self._waiters[target] = [f for f in self._waiters[target] if f != fut]
                if not self._waiters[target]:
                    del self._waiters[target]
            raise

    def reset(self, start_time: datetime | None = None):
        """Reset clock to start time."""
        self._current_time = start_time or self._start_time
        self._waiters.clear()
        self._step_event.set()
        self._paused = False

    def get_elapsed(self) -> timedelta:
        """Return simulated time elapsed since the configured start."""
        return self._current_time - self._start_time

    def get_remaining(self) -> timedelta | None:
        """Return time remaining to the configured end, or ``None`` without one."""
        if self._end_time:
            return self._end_time - self._current_time
        return None

    def is_finished(self) -> bool:
        """Report whether simulated time has reached its configured end."""
        if self._end_time:
            return self._current_time >= self._end_time
        return False


class AcceleratedClock(Clock):
    """Accelerated real-time clock."""

    def __init__(self, speed_factor: float = 10.0, timezone: str = "UTC"):
        """Start a clock whose simulated time advances faster than wall time."""
        self._speed_factor = max(0.001, speed_factor)
        self._timezone = timezone
        self._mode = ClockMode.ACCELERATED
        self._start_wall = time.monotonic()
        self._start_sim = _utcnow()

    @property
    def mode(self) -> ClockMode:
        """Return the accelerated clock mode."""
        return self._mode

    @property
    def speed_factor(self) -> float:
        """Return the multiplier applied to elapsed wall-clock time."""
        return self._speed_factor

    def now(self) -> datetime:
        """Map monotonic wall-time elapsed since creation onto simulated time."""
        wall_elapsed = time.monotonic() - self._start_wall
        sim_elapsed = wall_elapsed * self._speed_factor
        return self._start_sim + timedelta(seconds=sim_elapsed)

    async def sleep(self, seconds: float):
        """Wait the wall-time duration corresponding to simulated seconds."""
        real_seconds = seconds / self._speed_factor
        await asyncio.sleep(real_seconds)

    async def sleep_until(self, target: datetime):
        """Wait at the configured speed until the target simulated time."""
        now = self.now()
        if target > now:
            await self.sleep((target - now).total_seconds())


class ClockFactory:
    """Factory for creating clocks."""

    @staticmethod
    def create(config: ClockConfig) -> Clock:
        """Build the clock implementation selected by a complete clock config."""
        if config.mode == ClockMode.REALTIME:
            return RealtimeClock(timezone=config.timezone)
        elif config.mode == ClockMode.SIMULATED:
            start = config.start_time or _utcnow()
            return SimulatedClock(
                start_time=start,
                end_time=config.end_time,
                speed_factor=config.speed_factor,
            )
        elif config.mode == ClockMode.ACCELERATED:
            return AcceleratedClock(
                speed_factor=config.speed_factor,
                timezone=config.timezone,
            )
        else:
            raise ValueError(f"Unknown clock mode: {config.mode}")

    @staticmethod
    def create_for_backtest(
        start_time: datetime,
        end_time: datetime,
        speed_factor: float = 1.0,
    ) -> SimulatedClock:
        """Create a bounded simulated clock for deterministic backtest replay."""
        return SimulatedClock(
            start_time=start_time,
            end_time=end_time,
            speed_factor=speed_factor,
        )

    @staticmethod
    def create_for_paper(speed_factor: float = 1.0) -> Clock:
        """Use realtime for normal paper trading or accelerated time for replay."""
        if speed_factor == 1.0:
            return RealtimeClock()
        return AcceleratedClock(speed_factor=speed_factor)

    @staticmethod
    def create_for_live() -> RealtimeClock:
        """Create the wall-clock source used by live trading."""
        return RealtimeClock()


LiveClock = RealtimeClock
BacktestClock = SimulatedClock


@dataclass
class ClockContext:
    """Context manager for clock management."""
    clock: Clock
    _original_clock: Clock | None = None

    @classmethod
    async def back(cls, start_time: datetime, end_time: datetime) -> ClockContext:
        """Create backtest clock context."""
        from cryptobot.core.clock import SimulatedClock
        clock = SimulatedClock(
            start_time=start_time,
            end_time=end_time,
        )
        return cls(clock=clock)

    async def __aenter__(self) -> Clock:
        """Install this clock globally and return it for the context body."""
        from cryptobot.core.clock import get_clock, set_clock
        self._original_clock = get_clock()
        set_clock(self.clock)
        return self.clock

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Restore the prior global clock when leaving the context."""
        from cryptobot.core.clock import set_clock
        if self._original_clock:
            set_clock(self._original_clock)


# Global clock instance
_clock: Clock | None = None


def get_clock() -> Clock:
    """Get current global clock."""
    global _clock
    if _clock is None:
        _clock = RealtimeClock()
    return _clock


def set_clock(clock: Clock):
    """Set global clock."""
    global _clock
    _clock = clock


async def init_clock(config: ClockConfig) -> Clock:
    """Initialize clock from config."""
    global _clock
    _clock = ClockFactory.create(config)
    return _clock
