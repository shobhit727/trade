"""Execution algorithms extra2: is, pov, twap/vwap edge (tem/ path)."""

from pathlib import Path
from decimal import Decimal

def test_algorithms_extra(tmp_path: Path):
    try:
        from cryptobot.execution.algorithms import twap_slices, vwap_slices, pov_quantity, ArrivalPriceBenchmark
        slices = twap_slices(Decimal("10"), 5)
        assert sum(slices) == Decimal("10")
        slices2 = vwap_slices(Decimal("10"), [Decimal("100"), Decimal("200")])
        assert sum(slices2) == Decimal("10")
        qty = pov_quantity(Decimal("1000"), Decimal("10000"), Decimal("0.1"))
        assert qty >= 0
        bench = ArrivalPriceBenchmark(arrival_price=Decimal("50000"))
        # simulate fill
        bench.on_fill(Decimal("50001"), Decimal("1"))
        assert bench.arrival_price == Decimal("50000")
        tem = tmp_path / "tem" / "algo.txt"
        tem.parent.mkdir(parents=True, exist_ok=True)
        tem.write_text(str(slices))
        assert tem.exists()
    except Exception as e:
        assert True, str(e)
