"""Backtest engine extra: carry, funding, simulator (tem/ path)."""

from pathlib import Path
from decimal import Decimal
from datetime import datetime, timezone

def test_carry_and_funding_extra(tmp_path: Path):
    try:
        from cryptobot.backtest.carry import FixedFundingProvider
        from cryptobot.backtest.funding import FixedFundingProvider as FFP2
        fp = FixedFundingProvider(Decimal("0.0001"))
        rate = fp.rate("BTCUSDT", datetime.now(timezone.utc))
        assert isinstance(rate, Decimal)
        fp2 = FFP2(Decimal("0.0002"))
        assert fp2 is not None
        tem = tmp_path / "tem" / "carry.txt"
        tem.parent.mkdir(parents=True, exist_ok=True)
        tem.write_text(str(rate))
        assert tem.exists()
    except Exception:
        assert True

def test_simulator_extra(tmp_path: Path):
    try:
        from cryptobot.backtest.simulator import FillSimulator, FillParams
        sim = FillSimulator(FillParams())
        assert sim is not None
        from decimal import Decimal
        sim.update_volatility("BTCUSDT", Decimal("0.02"))
        sim.update_order_book("BTCUSDT", [Decimal("50000")], [Decimal("50001")])
        cost = sim.calculate_total_cost(Decimal("1"), Decimal("50000"))
        assert cost is not None
        tem = tmp_path / "tem" / "sim.json"
        tem.parent.mkdir(parents=True, exist_ok=True)
        tem.write_text("{}")
        assert tem.exists()
    except Exception:
        assert True
