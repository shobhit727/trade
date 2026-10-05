from cryptobot.utils.health_server import _price_chart_svg, _sparkline_svg, render_dashboard_html


def test_sparkline_empty_and_flat():
    assert "collecting data" in _sparkline_svg([])
    assert "collecting data" in _sparkline_svg([1.0])
    html = _sparkline_svg([1, 2, 3])
    assert "<svg" in html and "polyline" in html
    html_down = _sparkline_svg([3, 2, 1])
    assert 'stroke="#f85149"' in html_down  # red for down
    assert 'stroke="#3fb950"' in _sparkline_svg([1, 2, 3])  # green for up


def test_price_chart_empty_and_markers():
    assert "collecting price history" in _price_chart_svg([], [])
    hist = [{"ts": f"2026-08-{d:02d}T00:00:00+00:00", "close": 50000 + d * 100} for d in range(1, 20)]
    trades = [
        {"ts": "2026-08-10T00:00:00+00:00", "symbol": "BTCUSDT", "side": "BUY", "qty": 0.01, "price": 50900},
        {"ts": "2026-08-12T00:00:00+00:00", "symbol": "BTCUSDT", "side": "SELL", "qty": 0.01, "price": 51200},
    ]
    html = _price_chart_svg(hist, trades)
    assert "<svg" in html and "<path" in html
    assert "50900" in html or "51200" in html or "BUY" in html


def test_dashboard_variants():
    base = {
        "status": "running",
        "strategy": "dual_ma",
        "symbol": "BTCUSDT",
        "timeframe": "1d",
        "mode": "paper",
        "equity": "10500.00",
        "daily_pnl": "-123.45",
        "peak_equity": "11000.00",
        "max_drawdown_pct": "5.1",
        "risk_profile": "realistic",
        "global_fund": {"fund_balance": "35.20", "frozen": True, "n_entries": 3},
        "paper_gate": {"status": "collecting", "days_elapsed": 55, "window_days": 60, "extensions_used": 1, "allows_live": False},
        "breaker": {"tripped": True, "reason": "drawdown -26%", "max_drawdown": "-25%"},
        "tax_summary": {"total_proceeds": "1000", "taxable_income": "200", "estimated_tax": "60", "tds_credits": "10", "net_tax_payable": "50"},
        "equity_curve": [{"equity": 10000}, {"equity": 10500}],
        "price_history": [{"ts": f"2026-08-{d:02d}T00:00:00+00:00", "close": 50000 + d * 10} for d in range(1, 10)],
        "recent_trades": [{"ts": "2026-08-10T00:00:00+00:00", "symbol": "BTCUSDT", "side": "BUY", "qty": 0.01, "price": 50000, "notional": 500, "strategy": "dual_ma"}],
        "bars_seen": 10,
        "bars_fed": 9,
        "orders_submitted": 5,
        "fills": 4,
        "rejects": 1,
        "open_positions": 1,
        "last_close": 50500,
        "allocator_warning": "test warning <b>",
    }
    html = render_dashboard_html(base)
    assert "TRIPPED" in html
    assert "drawdown -26%" in html
    assert "FROZEN" in html
    assert "&lt;b&gt;" in html  # escaped
    assert "55 / 60" in html
    assert "Live trades" in html
    assert "Strategy sweep" in html
    # negative pnl -> neg class
    assert 'class="big neg"' in html or 'neg' in html


def test_dashboard_empty_curve_and_zero_pnl():
    snap = {
        "status": "starting",
        "global_fund": {},
        "paper_gate": {},
        "breaker": {},
        "tax_summary": {},
        "equity_curve": [],
    }
    html = render_dashboard_html(snap)
    assert "collecting data" in html
    assert "starting" in html
