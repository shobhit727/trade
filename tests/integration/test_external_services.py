"""Integration tests for external services (TimescaleDB, Redis, Prometheus).

These tests exercise the real adapters against live services. They are
gated behind the ``integration`` marker so they are skipped by default
(``pytest -m "not integration"``) and are skipped even when run directly
if the target service is not reachable. CI runs them only on the `test`
Docker target where the compose stack is present.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

pytestmark = pytest.mark.integration

# ---------------------------------------------------------------------------
# Service-availability helpers
# ---------------------------------------------------------------------------


def _timescale_available() -> bool:
    import importlib.util

    if importlib.util.find_spec("asyncpg") is None:
        return False
    try:
        import socket

        sock = socket.create_connection(("timescaledb", 5432), timeout=1)
        sock.close()
        return True
    except Exception:
        return False


def _redis_available() -> bool:
    try:
        import redis

        client = redis.Redis(host="cryptobot-redis", port=6379, db=0, socket_connect_timeout=1)
        return client.ping()
    except Exception:
        return False


needs_timescale = pytest.mark.skipif(
    not _timescale_available(),
    reason="TimescaleDB not reachable at timescaledb:5432 (start compose stack)",
)
needs_redis = pytest.mark.skipif(
    not _redis_available(),
    reason="Redis not reachable at cryptobot-redis:6379 (start compose stack)",
)


# ---------------------------------------------------------------------------
# TimescaleDB
# ---------------------------------------------------------------------------


@needs_timescale
@pytest.mark.asyncio
async def test_timescale_write_read_klines_roundtrip():
    from cryptobot.data.storage import StorageConfig, TimescaleDBStorage

    cfg = StorageConfig()
    storage = TimescaleDBStorage(cfg)
    await storage.initialize()

    bars = [
        {
            "ts": datetime(2024, 1, 1, tzinfo=UTC),
            "open": 100.0,
            "high": 110.0,
            "low": 99.0,
            "close": 105.0,
            "volume": 1000.0,
            "symbol": "BTCUSDT",
            "timeframe": "1h",
        },
        {
            "ts": datetime(2024, 1, 1, 1, tzinfo=UTC),
            "open": 105.0,
            "high": 112.0,
            "low": 104.0,
            "close": 111.0,
            "volume": 900.0,
            "symbol": "BTCUSDT",
            "timeframe": "1h",
        },
    ]
    try:
        await storage.write_klines(bars)
        rows = await storage.read_klines(symbol="BTCUSDT", timeframe="1h")
        assert len(rows) == 2
        assert rows[0]["close"] == 105.0
    finally:
        await storage.close()


# ---------------------------------------------------------------------------
# Redis (in-memory market-data cache)
# ---------------------------------------------------------------------------


@needs_redis
@pytest.mark.asyncio
async def test_redis_market_data_cache_roundtrip():
    from cryptobot.market_data.manager import MarketDataCache

    cache = MarketDataCache(redis_host="localhost", redis_port=6379, db=0)
    await cache.start()
    try:
        key = "test:BTCUSDT:last"
        await cache.set(key, "100.5")
        value = await cache.get(key)
        assert value == "100.5"
    finally:
        await cache.stop()


@needs_redis
def test_redis_ping():
    import redis

    client = redis.Redis(host="localhost", port=6379, db=0, socket_connect_timeout=1)
    assert client.ping()


@needs_redis
def test_redis_state_manager_roundtrip():
    """StateManager with a Redis-backed bus transport would go here; for now
    verify key/value roundtrip on the shared cache namespace."""
    import redis

    client = redis.Redis(host="localhost", port=6379, db=0, socket_connect_timeout=1)
    client.set("cryptobot:test:k", "v1")
    assert client.get("cryptobot:test:k") == b"v1"
    client.delete("cryptobot:test:k")


# ---------------------------------------------------------------------------
# Prometheus metrics end-to-end
# ---------------------------------------------------------------------------


def test_prometheus_metrics_export_text():
    from prometheus_client import CollectorRegistry, Counter, generate_latest

    registry = CollectorRegistry()
    counter = Counter("cryptobot_orders_total", "count", registry=registry)
    counter.inc(3)
    out = generate_latest(registry).decode()
    assert "cryptobot_orders_total 3.0" in out


def test_monitoring_record_functions_persist():
    """record_order/record_pnl call real prometheus when available."""
    from cryptobot.monitoring import metrics

    assert metrics.PROMETHEUS_AVAILABLE is True
    # Exercise the record path — must not raise and must route through the
    # real prometheus_client objects (no-op stubs only when unavailable).
    metrics.record_order(
        strategy="trend", symbol="BTCUSDT", side="BUY",
        order_type="MARKET", status="FILLED", filled=True,
    )
    metrics.record_pnl(strategy="trend", daily=1.0, total=2.0, equity=10000.0, available=9000.0, margin=1000.0)


# ---------------------------------------------------------------------------
# State via file-backed SQLite (works without external services)
# ---------------------------------------------------------------------------


def test_sqlite_state_manager_roundtrip(tmp_path):
    """StateManager persists orders to the on-disk SQLite file and rows are
    queryable afterwards (real sqlite3, no monkeypatched fallback)."""
    import sqlite3

    if sqlite3 is None:  # pragma: no cover - graceful fallback path
        pytest.skip("sqlite3 unavailable in this interpreter")

    from cryptobot.core.events import OrderEvent, OrderSide, OrderStatus, OrderType
    from cryptobot.core.state import StateManager

    db_file = tmp_path / "cryptobot.db"
    mgr = StateManager()
    mgr._db_path = str(db_file)
    mgr._init_db()

    order = OrderEvent(
        order_id="o-int-1", symbol="BTCUSDT", side=OrderSide.BUY, type=OrderType.LIMIT,
        quantity=Decimal("1"), price=Decimal("100"), status=OrderStatus.NEW,
    )
    mgr.save_order(order)

    conn = sqlite3.connect(str(db_file))
    row = conn.execute("SELECT order_id, created_at, updated_at FROM orders WHERE order_id = ?", ("o-int-1",)).fetchone()
    conn.close()
    assert row is not None
    assert row[1] is not None and row[2] is not None, "order timestamps must be persisted"
