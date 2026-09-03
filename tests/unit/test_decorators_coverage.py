import asyncio
import pytest

from cryptobot.utils.decorators import CircuitBreaker, CircuitBreakerOpenError, circuit_breaker, retry, timeout_decorator


@pytest.mark.asyncio
async def test_retry_async_succeeds_after_flake():
    calls = 0

    @retry(max_attempts=3, backoff_factor=0, jitter=False)
    async def flaky(x):
        nonlocal calls
        calls += 1
        if calls < 2:
            raise ValueError("flake")
        return x * 2

    assert await flaky(21) == 42
    assert calls == 2


def test_retry_sync_succeeds_after_flake():
    calls = 0

    @retry(max_attempts=3, backoff_factor=0, jitter=False)
    def flaky(x):
        nonlocal calls
        calls += 1
        if calls < 2:
            raise ValueError("flake")
        return x + 1

    assert flaky(41) == 42
    assert calls == 2


@pytest.mark.asyncio
async def test_retry_async_exhausts():
    @retry(max_attempts=2, backoff_factor=0, jitter=False)
    async def always_fail():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await always_fail()


@pytest.mark.asyncio
async def test_timeout_decorator_times_out():
    @timeout_decorator(timeout=0.05)
    async def slow():
        await asyncio.sleep(0.2)
        return 1

    with pytest.raises(TimeoutError):
        await slow()


@pytest.mark.asyncio
async def test_timeout_decorator_succeeds():
    @timeout_decorator(timeout=0.5)
    async def fast():
        await asyncio.sleep(0.01)
        return 42

    assert await fast() == 42


@pytest.mark.asyncio
async def test_circuit_breaker_open_and_half_open():
    cb = CircuitBreaker(failure_threshold=2, success_threshold=1, reset_timeout=0.05)

    async def fail():
        raise ValueError("fail")

    async def ok():
        return 1

    # 2 failures -> OPEN
    with pytest.raises(ValueError):
        await cb.call(fail)
    with pytest.raises(ValueError):
        await cb.call(fail)
    assert cb.state == "OPEN"

    # immediate call while OPEN -> CircuitBreakerOpenError
    with pytest.raises(CircuitBreakerOpenError):
        await cb.call(ok)

    # wait for reset_timeout -> HALF_OPEN -> success -> CLOSED
    await asyncio.sleep(0.06)
    assert await cb.call(ok) == 1
    assert cb.state == "CLOSED"

    # reset manually
    cb.reset()
    assert cb.state == "CLOSED"


@pytest.mark.asyncio
async def test_circuit_breaker_decorator_async():
    @circuit_breaker(failure_threshold=2, success_threshold=1, reset_timeout=0.05)
    async def maybe(x):
        if x < 0:
            raise ValueError("neg")
        return x

    assert await maybe(5) == 5
    with pytest.raises(ValueError):
        await maybe(-1)
    with pytest.raises(ValueError):
        await maybe(-1)
    # now open
    with pytest.raises(CircuitBreakerOpenError):
        await maybe(5)
