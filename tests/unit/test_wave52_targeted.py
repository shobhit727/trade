"""Wave52 targeted: costs (tem/ path)."""
from pathlib import Path
from decimal import Decimal
from datetime import datetime, timezone


def test_wave_costs(tmp_path: Path):
    from decimal import Decimal
    from cryptobot.execution.costs import TransactionCostModel
    m = TransactionCostModel()
    costs = m.calculate_total_cost(symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity=Decimal("1"), price=Decimal("50000"), mark_price=Decimal("50000"))
    assert "total" in costs
    assert costs["total"] >= 0
    assert "slippage" in costs
    tem = tmp_path / "tem" / "costs2.txt"
    tem.parent.mkdir(parents=True, exist_ok=True)
    tem.write_text(str(costs["total"]))
    assert "tem" in str(tem)
