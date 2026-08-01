"""Regression test for B051.

`cryptobot.monitoring` and its submodules must import without optional
dependencies (prometheus_client, aiohttp). When those packages are
absent or broken, the package falls back to no-op stubs that keep the
call sites working.
"""

from __future__ import annotations

from typing import Any

import pytest


def _optional_usable(name: str) -> bool:
    """True iff `name` can be imported successfully right now.

    Catches the `_ssl` / `aiohttp` cases where `find_spec` returns True
    but `__import__` raises.
    """
    try:
        __import__(name)
        return True
    except Exception:
        return False


def _load(name: str) -> Any:
    return __import__(name, fromlist=["*"])


def test_package_facade_imports_without_prometheus():
    import cryptobot.monitoring

    assert len(cryptobot.monitoring.__all__) >= 100


def test_alerting_module_imports_without_aiohttp():
    a = _load("cryptobot.monitoring.alerting")

    assert hasattr(a, "AlertManager")
    assert hasattr(a, "TelegramChannel")
    assert hasattr(a, "DiscordChannel")
    assert hasattr(a, "PagerDutyChannel")
    assert hasattr(a, "EmailChannel")


def test_alerting_does_not_import_aiohttp_at_module_level():
    """`import aiohttp` must be deferred to the call site, not at import."""
    import ast
    import pathlib

    src = pathlib.Path("src/cryptobot/monitoring/alerting.py").read_text()
    tree = ast.parse(src)
    module_level = [n for n in tree.body if isinstance(n, ast.Import | ast.ImportFrom)]
    for node in module_level:
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        else:
            names = [node.module] if node.module else []
        for n in names:
            assert not (n == "aiohttp" or n.endswith(".aiohttp")), (
                f"aiohttp imported at module level in alerting.py: {n}"
            )


def test_monitoring_package_facade_resolves_health_dashboard_eagerly():
    """health and dashboard have no optional deps and import cleanly."""
    from cryptobot.monitoring import dashboard, health

    assert hasattr(health, "HealthMonitor")
    assert hasattr(dashboard, "create_pnl_dashboard")


def test_metrics_module_imports_when_prometheus_missing():
    m = _load("cryptobot.monitoring.metrics")

    if _optional_usable("prometheus_client"):
        pytest.skip("prometheus_client fully usable in this env; no-op not exercised")
    assert m.PROMETHEUS_AVAILABLE is False
    assert m.Counter is m._NoOpMetric  # type: ignore[attr-defined]
    assert m.Gauge is m._NoOpMetric  # type: ignore[attr-defined]
    assert m.Histogram is m._NoOpMetric  # type: ignore[attr-defined]
    assert m.Info is m._NoOpMetric  # type: ignore[attr-defined]
    assert m.generate_latest(m.registry) == b""
    assert m.get_metrics_text() == ""


def test_metric_noop_calls_dont_raise_when_prometheus_missing():
    if _optional_usable("prometheus_client"):
        pytest.skip("prometheus_client fully usable; no-op not exercised")
    m = _load("cryptobot.monitoring.metrics")

    m.orders_total.labels(
        strategy="s", symbol="BTCUSDT", side="BUY", type="MARKET", status="OK"
    ).inc()
    m.total_pnl.set(123.45)
    m.execution_latency.labels(
        venue="x", symbol="BTCUSDT", order_type="MARKET"
    ).observe(0.01)
    m.record_order(strategy="s", symbol="BTCUSDT", side="BUY", order_type="MARKET", status="OK")
    m.record_execution_latency(venue="x", symbol="BTCUSDT", order_type="MARKET", latency=0.01)
    m.record_pnl(strategy="s", daily=0.1, total=0.5, equity=1000, available=800, margin=200)
    m.record_backtest_run(strategy="s", status="ok", duration=1.0, trades=10, winning=6, losing=4)
    assert m.get_metrics_text() == ""


def test_noop_fallback_classes_work_standalone():
    """The fallback stub classes work even if prometheus_client can be imported.

    This test runs the no-op code path directly without depending on the
    environment. It exercises every method callers rely on.
    """
    import sys
    import textwrap

    src = textwrap.dedent(
        """
        import sys
        # Force Prometheus import to fail by injecting a broken stub
        class _Broken:
            def __getattr__(self, n):
                raise ImportError("prometheus_client unavailable")

        sys.modules['prometheus_client'] = _Broken()
        sys.modules['prometheus_client.exposition'] = _Broken()
        sys.modules['prometheus_client.metrics'] = _Broken()
        sys.modules['prometheus_client.registry'] = _Broken()

        import cryptobot.monitoring.metrics as m

        assert m.PROMETHEUS_AVAILABLE is False, "fallback did not engage"

        c = m.Counter('x', 'help')
        c.inc()
        c.labels(a='1', b='2').inc(3)
        c.labels(a='1').inc(amount=4)

        g = m.Gauge('g', 'help')
        g.set(1.5)
        g.dec()
        g.labels(k='v').inc(2)

        h = m.Histogram('h', 'help')
        h.observe(0.1)
        h.labels(k='v').observe(0.2)

        i = m.Info('i', 'help')
        i.info({'a': 'b'})

        out = m.generate_latest(m.registry)
        assert out == b''
        assert m.get_metrics_text() == ''

        m.record_order(strategy='s', symbol='BTCUSDT', side='BUY', order_type='MARKET', status='OK')
        m.record_execution_latency(venue='x', symbol='BTCUSDT', order_type='MARKET', latency=0.1)
        m.record_pnl(strategy='s', daily=0.1, total=0.5, equity=1000, available=800, margin=200)
        m.record_backtest_run(strategy='s', status='ok', duration=1.0, trades=10, winning=6, losing=4)

        from cryptobot.monitoring.alerting import TelegramChannel
        # Just construct — the HTTP call would need aiohttp, but construction is fine.
        ch = TelegramChannel(bot_token='t', chat_id='c')
        assert ch.chat_id == 'c'
        """
    )
    import os
    import subprocess

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    project_root = os.path.dirname(project_root)  # Go up from tests/unit to project root

    result = subprocess.run(
        [sys.executable, "-c", src],
        capture_output=True,
        text=True,
        cwd=project_root,
        env={"PYTHONPATH": "src", "PATH": "/usr/bin:/bin"},
    )
    assert result.returncode == 0, f"subprocess failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"



