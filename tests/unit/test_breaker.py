"""Unit tests for the equity circuit breaker (Seed Phase step 6)."""

from decimal import Decimal

from cryptobot.core.breaker import BreakerConfig, CircuitBreaker


def test_trips_at_threshold():
    br = CircuitBreaker(BreakerConfig(state_path="/tmp/opencode/b1.json"))
    assert br.check(Decimal("10000"), Decimal("7499")) is True   # -25.01%
    assert br.check(Decimal("10000"), Decimal("7500")) is True   # exactly -25%
    assert br.check(Decimal("10000"), Decimal("7501")) is False  # -24.99%


def test_trip_sets_state_and_persists(tmp_path):
    path = tmp_path / "breaker.json"
    br = CircuitBreaker(BreakerConfig(state_path=str(path)))
    br.trip("drawdown -27% from peak", now_iso="2026-08-22T00:00:00+00:00")
    assert br.tripped is True

    restored = CircuitBreaker(BreakerConfig(state_path=str(path)))
    assert restored.tripped is True
    assert restored.reason == "drawdown -27% from peak"


def test_reset_clears_and_persists(tmp_path):
    path = tmp_path / "breaker.json"
    br = CircuitBreaker(BreakerConfig(state_path=str(path)))
    br.trip("x")
    br.reset()
    assert br.tripped is False
    restored = CircuitBreaker(BreakerConfig(state_path=str(path)))
    assert restored.tripped is False


def test_double_trip_is_noop(tmp_path):
    br = CircuitBreaker(BreakerConfig(state_path=str(tmp_path / "b.json")))
    br.trip("first")
    br.trip("second")  # ignored
    assert br.reason == "first"


def test_check_ignores_when_already_tripped(tmp_path):
    br = CircuitBreaker(BreakerConfig(state_path=str(tmp_path / "b.json")))
    br.trip("x")
    assert br.check(Decimal("100"), Decimal("10")) is False


def test_check_zero_peak_safe():
    br = CircuitBreaker(BreakerConfig(state_path="/tmp/opencode/b2.json"))
    assert br.check(Decimal("0"), Decimal("50")) is False


def test_close_order_profit_first():
    positions = [
        {"symbol": "A", "unrealized_pnl": "-50"},
        {"symbol": "B", "unrealized_pnl": "120"},
        {"symbol": "C", "unrealized_pnl": "30"},
        {"symbol": "D", "unrealized_pnl": "-200"},
    ]
    ordered = CircuitBreaker.close_order(positions)
    assert [p["symbol"] for p in ordered] == ["B", "C", "A", "D"]


def test_close_order_handles_bad_pnl():
    positions = [{"symbol": "A", "unrealized_pnl": "junk"},
                 {"symbol": "B", "unrealized_pnl": "5"}]
    ordered = CircuitBreaker.close_order(positions)
    assert [p["symbol"] for p in ordered] == ["B", "A"]
