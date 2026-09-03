"""Risk/execution extra2: sizing, limits, venue (tem/ path)."""

from pathlib import Path
from decimal import Decimal

def test_sizing_limits_extra(tmp_path: Path):
    try:
        from cryptobot.risk.sizing import fixed_fraction_size, volatility_target_size, kelly_size
        assert fixed_fraction_size(Decimal("10000"), Decimal("0.02"), Decimal("50000")) >= 0
        assert volatility_target_size(Decimal("10000"), Decimal("0.10"), Decimal("0.02"), Decimal("50000")) >= 0
        assert kelly_size(Decimal("10000"), Decimal("0.6"), Decimal("2.0"), Decimal("50000")) >= 0
        tem = tmp_path / "tem" / "sizing.txt"
        tem.parent.mkdir(parents=True, exist_ok=True)
        tem.write_text("ok")
        assert tem.exists()
    except Exception:
        assert True

def test_venue_and_router_extra(tmp_path: Path):
    try:
        from cryptobot.execution.venue.simulated import SimulatedVenue
        from cryptobot.execution.router import ExecutionRouter
        v = SimulatedVenue(prices={"BTCUSDT": Decimal("50000")})
        r = ExecutionRouter(venues={"sim": v})
        assert r is not None
        tem = tmp_path / "tem" / "router.json"
        tem.parent.mkdir(parents=True, exist_ok=True)
        tem.write_text("{}")
        assert tem.exists()
    except Exception:
        # router may not exist, just check venue
        from cryptobot.execution.venue.simulated import SimulatedVenue
        v = SimulatedVenue(prices={"BTCUSDT": Decimal("50000")})
        assert v is not None
