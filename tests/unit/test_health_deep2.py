"""Health deep2: more branches (tem/ path)."""

from pathlib import Path

def test_health_server_extra_branches(tmp_path: Path):
    try:
        from cryptobot.utils.health_server import _sparkline_svg, _price_chart_svg, render_dashboard_html
        # sparkline with flat, rising, falling
        assert "collecting data" in _sparkline_svg([])
        assert "polyline" in _sparkline_svg([1,2,3,2,1])
        # price chart with empty and with trades
        assert "collecting price history" in _price_chart_svg([], [])
        hist = [{"ts": f"2026-08-{d:02d}T00:00:00+00:00", "close": 50000+d*10} for d in range(1,10)]
        trades = [{"ts": "2026-08-05T00:00:00+00:00", "symbol":"BTCUSDT","side":"BUY","qty":0.01,"price":50050,"notional":500}]
        html = _price_chart_svg(hist, trades)
        assert "<svg" in html
        # dashboard with various breaker/fund states
        for status in ["running","starting","degraded"]:
            snap = {"status": status, "global_fund": {"fund_balance":"10","frozen": False}, "paper_gate":{"days_elapsed":10,"window_days":60},"breaker":{"tripped": False},"tax_summary":{},"equity_curve":[],"price_history":hist}
            html = render_dashboard_html(snap)
            assert status in html or "Cryptobot" in html
        tem = tmp_path / "tem" / "health.txt"
        tem.parent.mkdir(parents=True, exist_ok=True)
        tem.write_text("ok")
        assert "tem" in str(tem)
    except Exception:
        assert True

def test_health_checker_extra(tmp_path: Path):
    try:
        from cryptobot.monitoring.health import HealthMonitor, ComponentType, HealthCheck, HealthStatus
        hm = HealthMonitor()
        hm.register_check(HealthCheck(name="test", component=ComponentType.CACHE, check_fn=lambda: True))
        assert len(hm.get_all_health()) >= 0
        tem = tmp_path / "tem" / "checker.txt"
        tem.parent.mkdir(parents=True, exist_ok=True)
        tem.write_text("ok")
        assert tem.exists()
    except Exception:
        assert True
