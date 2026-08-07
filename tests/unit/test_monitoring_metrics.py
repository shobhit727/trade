"""Tests for cryptobot.monitoring.metrics."""

from __future__ import annotations

import time

import pytest

import cryptobot.monitoring.metrics as m

pytestmark = [
    pytest.mark.usefixtures("metrics_registry"),
]


def _text() -> str:
    return m.get_metrics_text()


# --- record_* functions -----------------------------------------------------


def test_init_system_info():
    m.init_system_info("1.2.3", "deadbeef", "2026-01-01")
    text = _text()
    assert 'cryptobot_system_info_info{build_date="2026-01-01",' in text
    assert 'git_commit="deadbeef"' in text
    assert 'version="1.2.3"' in text


def test_record_order_filled():
    m.record_order(
        strategy="trend", symbol="BTCUSDT", side="BUY",
        order_type="MARKET", status="FILLED", filled=True,
    )
    text = _text()
    assert 'cryptobot_orders_total{side="BUY",status="FILLED",strategy="trend",symbol="BTCUSDT",type="MARKET"} 1.0' in text
    assert 'cryptobot_orders_filled_total{side="BUY",strategy="trend",symbol="BTCUSDT"} 1.0' in text


def test_record_order_rejected():
    m.record_order(
        "trend", "BTCUSDT", "BUY", "LIMIT", "REJECTED", rejected_reason="insufficient_balance"
    )
    text = _text()
    assert 'cryptobot_orders_rejected_total{reason="insufficient_balance",strategy="trend",symbol="BTCUSDT"} 1.0' in text


def test_record_order_not_filled_no_filled_metric():
    m.record_order("trend", "BTCUSDT", "BUY", "LIMIT", "NEW")
    text = _text()
    # The HELP/TYPE annotation always appears; the sample line must not.
    assert 'cryptobot_orders_filled_total{side="BUY",strategy="trend",symbol="BTCUSDT"} ' not in text


def test_record_position_update_open():
    m.record_position_update("mm", "ETHUSDT", "LONG", 5000.0, unrealized_pnl=10.0)
    text = _text()
    assert 'cryptobot_positions_open{side="LONG",strategy="mm",symbol="ETHUSDT"} 1.0' in text
    assert 'cryptobot_position_size_usd{side="LONG",strategy="mm",symbol="ETHUSDT"} 5000.0' in text
    assert 'cryptobot_position_pnl_unrealized_usd{strategy="mm",symbol="ETHUSDT"} 10.0' in text


def test_record_position_update_realized_pnl_accumulates():
    m.record_position_update("mm", "ETHUSDT", "LONG", 0.0, realized_pnl=50.0)
    m.record_position_update("mm", "ETHUSDT", "LONG", 0.0, realized_pnl=25.0)
    text = _text()
    assert 'cryptobot_position_pnl_realized_usd{strategy="mm",symbol="ETHUSDT"} 75.0' in text


def test_record_position_close_zeroes_open_flag():
    m.record_position_update("mm", "ETHUSDT", "SHORT", 0.0)
    text = _text()
    assert 'cryptobot_positions_open{side="SHORT",strategy="mm",symbol="ETHUSDT"} 0.0' in text
    assert 'cryptobot_position_size_usd{side="SHORT",strategy="mm",symbol="ETHUSDT"} 0.0' in text


def test_record_pnl():
    m.record_pnl("trend", daily=100.0, total=1000.0, equity=10000.0, available=8000.0, margin=2000.0)
    text = _text()
    assert 'cryptobot_daily_pnl_usd{strategy="trend"} 100.0' in text
    assert 'cryptobot_total_pnl_usd{strategy="trend"} 1000.0' in text
    assert "cryptobot_total_equity_usd 10000.0" in text
    assert "cryptobot_available_balance_usd 8000.0" in text
    assert "cryptobot_used_margin_usd 2000.0" in text


def test_record_performance():
    m.record_performance("trend", sharpe=1.5, sortino=2.0, max_dd=-0.1, win_rate_val=0.6, profit_f=1.4)
    text = _text()
    assert 'cryptobot_sharpe_ratio{period="all",strategy="trend"} 1.5' in text
    assert 'cryptobot_sortino_ratio{period="all",strategy="trend"} 2.0' in text
    assert 'cryptobot_max_drawdown_pct{strategy="trend"} -0.1' in text
    assert 'cryptobot_win_rate_pct{strategy="trend"} 0.6' in text
    assert 'cryptobot_profit_factor{strategy="trend"} 1.4' in text


def test_record_risk_kill_switch_on():
    m.record_risk(0.5, 0.01, 0.2, True, concentration_pct=0.3)
    text = _text()
    assert 'cryptobot_risk_exposure_pct{strategy="portfolio"} 0.5' in text
    assert 'cryptobot_risk_daily_loss_pct{strategy="portfolio"} 0.01' in text
    assert "cryptobot_risk_drawdown_pct 0.2" in text
    assert "cryptobot_risk_kill_switch_active 1.0" in text
    assert 'cryptobot_position_concentration_pct{strategy="portfolio"} 0.3' in text


def test_record_risk_kill_switch_off():
    m.record_risk(0.0, 0.0, 0.0, False)
    assert "cryptobot_risk_kill_switch_active 0.0" in _text()


def test_record_market_data_latency():
    m.record_market_data_latency("binance", "BTCUSDT", "bookTicker", 0.015)
    text = _text()
    assert 'cryptobot_market_data_latency_seconds_count{source="binance",symbol="BTCUSDT",type="bookTicker"} 1.0' in text
    assert 'cryptobot_market_data_latency_seconds_sum{source="binance",symbol="BTCUSDT",type="bookTicker"} 0.015' in text
    assert 'cryptobot_market_data_messages_total{source="binance",symbol="BTCUSDT",type="bookTicker"} 1.0' in text


def test_record_execution_latency():
    m.record_execution_latency("binance", "BTCUSDT", "MARKET", 0.042)
    text = _text()
    assert 'cryptobot_execution_latency_seconds_count{order_type="MARKET",symbol="BTCUSDT",venue="binance"} 1.0' in text
    assert 'cryptobot_execution_latency_seconds_sum{order_type="MARKET",symbol="BTCUSDT",venue="binance"} 0.042' in text


def test_record_execution_slippage():
    m.record_execution_slippage("binance", "BTCUSDT", "BUY", 1.2)
    text = _text()
    assert 'cryptobot_execution_slippage_bps_count{side="BUY",symbol="BTCUSDT",venue="binance"} 1.0' in text
    assert 'cryptobot_execution_slippage_bps_sum{side="BUY",symbol="BTCUSDT",venue="binance"} 1.2' in text


def test_record_venue_quote_latency():
    m.record_venue_quote_latency("binance", "BTCUSDT", 0.03)
    text = _text()
    assert 'order_type="quote"' in text
    assert 'cryptobot_execution_latency_seconds_sum{order_type="quote",symbol="BTCUSDT",venue="binance"} 0.03' in text


def test_record_routing_decision_selected():
    m.record_routing_decision("binance", "BTCUSDT", "selected")
    text = _text()
    assert 'cryptobot_execution_retry_total{reason="selected",symbol="BTCUSDT",venue="binance"} 1.0' in text
    assert 'cryptobot_execution_fill_rate_pct{symbol="BTCUSDT",venue="binance"} 1.0' in text


def test_record_routing_decision_failed():
    m.record_routing_decision("binance", "BTCUSDT", "failed")
    text = _text()
    assert 'cryptobot_execution_retry_total{reason="failed",symbol="BTCUSDT",venue="binance"} 1.0' in text
    assert 'cryptobot_execution_fill_rate_pct{symbol="BTCUSDT",venue="binance"} 0.0' in text


def test_record_strategy_signal():
    m.record_strategy_signal("trend", "long", "BTCUSDT")
    assert 'cryptobot_strategy_signals_total{signal_type="long",strategy="trend",symbol="BTCUSDT"} 1.0' in _text()


def test_record_ml_inference():
    m.record_ml_inference("regime", "classifier", 0.002, 0.8)
    text = _text()
    assert 'cryptobot_ml_inference_latency_seconds_count{model="regime",type="classifier"} 1.0' in text
    assert 'cryptobot_ml_prediction_count{model="regime",type="classifier"} 1.0' in text


def test_record_error():
    m.record_error("execution", "timeout")
    assert 'cryptobot_errors_total{component="execution",error_type="timeout"} 1.0' in _text()


def test_record_warning():
    m.record_warning("data", "stale")
    assert 'cryptobot_warnings_total{component="data",warning_type="stale"} 1.0' in _text()


def test_record_connection_status_true():
    m.record_connection_status("binance", "wss://broker", True)
    assert 'cryptobot_connection_status{component="binance",endpoint="wss://broker"} 1.0' in _text()


def test_record_connection_status_false():
    m.record_connection_status("binance", "wss://broker", False)
    assert 'cryptobot_connection_status{component="binance",endpoint="wss://broker"} 0.0' in _text()


def test_record_backtest_run():
    m.record_backtest_run("trend", "ok", duration=3.5, trades=100, winning=60, losing=40)
    text = _text()
    assert 'cryptobot_backtest_runs_total{status="ok",strategy="trend"} 1.0' in text
    assert 'cryptobot_backtest_duration_seconds_count{strategy="trend"} 1.0' in text
    assert 'cryptobot_backtest_duration_seconds_sum{strategy="trend"} 3.5' in text
    assert 'cryptobot_backtest_trades_total{result="win",strategy="trend"} 60.0' in text
    assert 'cryptobot_backtest_trades_total{result="loss",strategy="trend"} 40.0' in text


def test_get_metrics_bytes_and_text():
    raw = m.get_metrics()
    assert isinstance(raw, bytes)
    assert isinstance(m.get_metrics_text(), str)


# --- MetricsContext / timed -------------------------------------------------


def test_metrics_context_times_histogram():
    with m.timed(m.execution_latency, venue="binance", symbol="BTCUSDT", order_type="MARKET"):
        time.sleep(0.01)
    text = _text()
    assert 'cryptobot_execution_latency_seconds_count{order_type="MARKET",symbol="BTCUSDT",venue="binance"} 1.0' in text


def test_metrics_context_records_observation():
    with m.timed(m.execution_latency, venue="binance", symbol="BTCUSDT", order_type="MARKET"):
        pass
    assert 'cryptobot_execution_latency_seconds_count{order_type="MARKET",symbol="BTCUSDT",venue="binance"} 1.0' in _text()


# --- MetricsCollector ---------------------------------------------------------


def test_metrics_collector_counter():
    c = m.MetricsCollector()
    counter = c.counter("requests_total", "Requests", ("method",))
    counter.inc(method="GET")
    counter.inc(2, method="POST")
    out = c.to_prometheus_text()
    assert 'requests_total{method="GET"} 1.0' in out
    assert 'requests_total{method="POST"} 2.0' in out


def test_metrics_collector_gauge():
    c = m.MetricsCollector()
    g = c.gauge("temp", "Temperature", ("sensor",))
    g.set(21.5, sensor="a")
    g.inc(sensor="a")
    g.dec(0.5, sensor="a")
    out = c.to_prometheus_text()
    assert 'temp{sensor="a"} 22.0' in out


def test_metrics_collector_histogram():
    c = m.MetricsCollector()
    h = c.histogram("lat", "Latency", (), buckets=(0.1, 0.5, 1.0))
    h.observe(0.05)
    h.observe(0.3)
    h.observe(2.0)
    out = c.to_prometheus_text()
    assert 'lat_bucket{le="0.1"} 1' in out
    assert 'lat_bucket{le="0.5"} 2' in out
    assert 'lat_bucket{le="1.0"} 2' in out
    assert 'lat_bucket{le="+Inf"} 3' in out
    assert "lat_count 3" in out
    assert "lat_sum 2.35" in out


def test_metrics_collector_histogram_no_labels():
    c = m.MetricsCollector()
    h = c.histogram("plain", "Plain latency")
    h.observe(0.2)
    out = c.to_prometheus_text()
    assert 'plain_bucket{le="0.25"} 1' in out
    assert "plain_count 1" in out


def test_metrics_collector_reuses_metric_objects():
    c = m.MetricsCollector()
    assert c.counter("x") is c.counter("x")
    assert c.gauge("y") is c.gauge("y")
    assert c.histogram("z") is c.histogram("z")


def test_metrics_collector_reset():
    c = m.MetricsCollector()
    c.counter("x").inc()
    assert "x " in c.to_prometheus_text()
    c.reset()
    assert c.to_prometheus_text() == "\n"


def test_metrics_collector_format_labels_no_labels():
    c = m.MetricsCollector()
    assert c._format_labels((), ()) == ""


def test_get_metrics_collector_singleton(monkeypatch):
    monkeypatch.setattr(m, "_collector", None)
    first = m.get_metrics_collector()
    second = m.get_metrics_collector()
    assert first is second
