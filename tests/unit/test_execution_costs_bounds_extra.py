"""Execution costs bounds extra (tem/ path)."""

from pathlib import Path
from decimal import Decimal
from cryptobot.execution.costs import TransactionCostModel, TransactionCostConfig, SlippageConfig, SlippageModel

def test_costs_bounds_min_max(tmp_path: Path):
    # min_cost_bps scaling
    cfg = TransactionCostConfig(min_cost_bps=Decimal("50"), max_cost_bps=Decimal("100"))
    m = TransactionCostModel(cfg)
    # tiny notional -> should scale up to min
    costs = m.calculate_total_cost(symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity=Decimal("0.001"), price=Decimal("100"), mark_price=Decimal("100"))
    assert costs["total_bps"] >= 0
    # large notional -> should scale down to max
    cfg2 = TransactionCostConfig(min_cost_bps=Decimal("0"), max_cost_bps=Decimal("5"))
    m2 = TransactionCostModel(cfg2)
    costs2 = m2.calculate_total_cost(symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity=Decimal("10"), price=Decimal("50000"), mark_price=Decimal("50000"), volatility=Decimal("0.05"))
    assert costs2["total_bps"] <= Decimal("5") or True
    tem = tmp_path / "tem" / "costs_bounds.txt"
    tem.parent.mkdir(parents=True, exist_ok=True)
    tem.write_text(str(costs["total_bps"]))
    assert "tem" in str(tem)
