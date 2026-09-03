"""Monitoring metrics extra3: _Counter, _Gauge, _Histogram (tem/ path)."""

from pathlib import Path

def test_metrics_extra3(tmp_path: Path):
    from cryptobot.monitoring.metrics import MetricsCollector
    c = MetricsCollector()
    # counter with labels
    ctr = c.counter("extra_counter", labelnames=("symbol","side"))
    ctr.inc(2, symbol="BTCUSDT", side="BUY")
    ctr.inc(3, symbol="BTCUSDT", side="SELL")
    # gauge dec
    g = c.gauge("extra_gauge")
    g.set(5)
    g.inc(2)
    g.dec(1)
    assert abs(g._values[()] - 6) < 1e-9
    # histogram with custom buckets
    h = c.histogram("extra_hist2", buckets=(0.1, 0.5, 1.0))
    h.observe(0.05)
    h.observe(0.6)
    h.observe(2.0)
    txt = c.to_prometheus_text()
    assert "extra_counter" in txt
    assert "extra_hist2_bucket" in txt
    tem = tmp_path / "tem" / "metrics3.txt"
    tem.parent.mkdir(parents=True, exist_ok=True)
    tem.write_text(txt[:200])
    assert "tem" in str(tem)
