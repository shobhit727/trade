"""
Utility decorators for resilience, timeouts, and circuit breaking.
"""

import asyncio
import inspect
import logging
import random
from collections.abc import Callable
from functools import wraps
from typing import Any

logger = logging.getLogger(__name__)


def retry(
    max_attempts: int = 3,
    backoff_factor: float = 0.5,
    exceptions: tuple = (Exception,),
    jitter: bool = True,
):
    """
    A decorator that retries a function call on failure.

    Args:
        max_attempts: Maximum number of attempts
        backoff_factor: Base multiplier for exponential backoff
        exceptions: Tuple of exceptions to catch and retry
        jitter: Add random jitter to prevent thundering herd
    """

    def decorator(func: Callable[..., Any]):
        """Wrap a sync or async callable with the configured retry policy."""
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            """Retry the coroutine with exponential backoff, then re-raise its final error."""
            last_exception = None
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt == max_attempts - 1:
                        logger.error(
                            f"Function '{func.__name__}' failed after {max_attempts} attempts. Final error: {e}"
                        )
                        raise

                    sleep_time = backoff_factor * (2**attempt)
                    if jitter:
                        sleep_time += random.uniform(-0.1, 0.1)
                    sleep_time = max(0.0, sleep_time)
                    logger.warning(
                        f"Attempt {attempt + 1} failed with {type(e).__name__}: {e}. Retrying in {sleep_time:.2f}s."
                    )
                    await asyncio.sleep(sleep_time)
            raise last_exception

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            """Retry the synchronous call with exponential backoff, then re-raise its error."""
            last_exception = None
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt == max_attempts - 1:
                        logger.error(
                            f"Function '{func.__name__}' failed after {max_attempts} attempts. Final error: {e}"
                        )
                        raise

                    sleep_time = backoff_factor * (2**attempt)
                    if jitter:
                        sleep_time += random.uniform(-0.1, 0.1)
                    sleep_time = max(0.0, sleep_time)
                    logger.warning(
                        f"Attempt {attempt + 1} failed with {type(e).__name__}: {e}. Retrying in {sleep_time:.2f}s."
                    )
                    import time
                    time.sleep(sleep_time)
            raise last_exception

        if inspect.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def timeout_decorator(timeout: float):
    """
    A decorator to enforce a maximum execution time on an async function.

    Args:
        timeout: Maximum execution time in seconds
    """

    def decorator(func: Callable[..., Any]):
        """Wrap an async callable with the requested execution timeout."""
        @wraps(func)
        async def wrapper(*args, **kwargs):
            """Run the coroutine until completion or raise a normalized timeout error."""
            try:
                return await asyncio.wait_for(func(*args, **kwargs), timeout=timeout)
            except TimeoutError as err:
                logger.error(f"Function '{func.__name__}' timed out after {timeout} seconds.")
                raise TimeoutError(f"Operation exceeded time limit of {timeout}s") from err

        return wrapper

    return decorator


class CircuitBreaker:
    """
    Circuit breaker state machine for external service calls.

    States: CLOSED (normal) -> OPEN (failing) -> HALF_OPEN (testing recovery)
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        success_threshold: int = 2,
        reset_timeout: float = 60.0,
        exceptions: tuple = (Exception,),
    ):
        """Configure failure thresholds, recovery timeout, and counted exception types."""
        self.failure_threshold = failure_threshold
        self.success_threshold = success_threshold
        self.reset_timeout = reset_timeout
        self.exceptions = exceptions

        self._state = "CLOSED"
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: float | None = None
        self._lock = asyncio.Lock()

    @property
    def state(self) -> str:
        """Return the current CLOSED, OPEN, or HALF_OPEN state."""
        return self._state

    async def call(self, func: Callable[..., Any], *args, **kwargs) -> Any:
        """Invoke a callable unless open, updating breaker state around its result."""
        async with self._lock:
            if self._state == "OPEN":
                if self._last_failure_time and (
                    asyncio.get_running_loop().time() - self._last_failure_time >= self.reset_timeout
                ):
                    self._state = "HALF_OPEN"
                    self._success_count = 0
                    logger.info("Circuit breaker entering HALF_OPEN state")
                else:
                    raise CircuitBreakerOpenError(f"Circuit breaker OPEN for {func.__name__}")

        try:
            if inspect.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)

            async with self._lock:
                self._on_success()
            return result

        except self.exceptions:
            async with self._lock:
                self._on_failure()
            raise

    def _on_success(self):
        """Advance half-open recovery or clear failures after a closed-state success."""
        if self._state == "HALF_OPEN":
            self._success_count += 1
            if self._success_count >= self.success_threshold:
                self._state = "CLOSED"
                self._failure_count = 0
                logger.info("Circuit breaker CLOSED")
        elif self._state == "CLOSED":
            self._failure_count = 0

    def _on_failure(self):
        """Record a failure and open the circuit at the configured threshold."""
        self._failure_count += 1
        self._last_failure_time = asyncio.get_running_loop().time()

        if self._state == "HALF_OPEN":
            self._state = "OPEN"
            logger.warning("Circuit breaker OPEN after HALF_OPEN failure")
        elif self._state == "CLOSED" and self._failure_count >= self.failure_threshold:
            self._state = "OPEN"
            logger.warning(f"Circuit breaker OPEN after {self._failure_count} failures")

    def reset(self):
        """Manually reset the circuit breaker."""
        self._state = "CLOSED"
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = None


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open."""
    pass


def circuit_breaker(
    failure_threshold: int = 5,
    success_threshold: int = 2,
    reset_timeout: float = 60.0,
    exceptions: tuple = (Exception,),
):
    """
    Decorator to add circuit breaker protection to a function.

    Args:
        failure_threshold: Failures before opening circuit
        success_threshold: Successes in HALF_OPEN before closing
        reset_timeout: Seconds before trying HALF_OPEN
        exceptions: Exceptions that count as failures
    """
    breaker = CircuitBreaker(
        failure_threshold=failure_threshold,
        success_threshold=success_threshold,
        reset_timeout=reset_timeout,
        exceptions=exceptions,
    )

    def decorator(func: Callable[..., Any]):
        """Wrap a function so calls pass through the configured circuit breaker."""
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            """Route an async call through the shared breaker instance."""
            return await breaker.call(func, *args, **kwargs)

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            """Run a sync call through the breaker only when no event loop is active."""
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop is not None:
                raise RuntimeError(
                    f"circuit_breaker({func.__name__}) called from a running event loop; "
                    "use the async form, or call from a thread without a running loop."
                )
            return asyncio.run(breaker.call(func, *args, **kwargs))

        if inspect.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator
