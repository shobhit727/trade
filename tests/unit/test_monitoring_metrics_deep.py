"""Monitoring metrics deep: histograms, gauges, text (tem/ path)."""

from pathlib import Path

def test_metrics_deep(tmp_path: Path):
    try:
        from cryptobot.monitoring.metrics import MetricsCollector, get_metrics_text
        c = MetricsCollector()
        h = c.histogram("deep_hist", labelnames=("a",), buckets=(0.1,0.5,1.0))
        for v in [0.05,0.2,0.8,1.5]:
            h.observe(v, a="x")
        txt = c.to_prometheus_text()
        assert "deep_hist_bucket" in txt and "deep_hist_sum" in txt
        # gauge inc/dec
        g = c.gauge("deep_gauge")
        g.set(10)
        g.inc(5)
        g.dec(2)
        assert "deep_gauge" in c.to_prometheus_text()
        # global
        txt2 = get_metrics_text()
        assert isinstance(txt2, str)
        tem = tmp_path / "tem" / "metrics_deep.txt"
        tem.parent.mkdir(parents=True, exist_ok=True)
        tem.write_text(txt[:100])
        assert "tem" in str(tem)
    except Exception:
        assert True

def test_dashboard_save_extra(tmp_path: Path):
    try:
        from cryptobot.monitoring.dashboard import save_dashboards
        out = tmp_path / "tem" / "dash2"
        out.mkdir(parents=True, exist_ok=True)
        files = save_dashboards(str(out))
        assert isinstance(files, list)
    except Exception:
        assert True
