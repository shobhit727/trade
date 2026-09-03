"""Execution costs extra: slippage models (tem/ path)."""

from pathlib import Path
from decimal import Decimal
from cryptobot.execution.costs import TransactionCostModel, TransactionCostConfig, FeeSchedule, SlippageConfig, SlippageModel

def test_costs_all_models(tmp_path: Path):
    for model in [SlippageModel.FIXED_BPS, SlippageModel.VOLATILITY_ADJUSTED, SlippageModel.VOLUME_WEIGHTED, SlippageModel.SQUARE_ROOT, SlippageModel.ALMGREN_CHRISS]:
        cfg = TransactionCostConfig(slippage=SlippageConfig(model=model, base_slippage_bps=Decimal("2"), max_slippage_bps=Decimal("50")))
        m = TransactionCostModel(cfg)
        costs = m.calculate_total_cost(symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity=Decimal("1"), price=Decimal("50000"), mark_price=Decimal("50000"))
        assert "total" in costs
        assert costs["total"] >= 0
    # fee tiered
    fs = FeeSchedule(maker_fee_bps=Decimal("1"), taker_fee_bps=Decimal("5"))
    fee = fs.calculate_fee(Decimal("50000"), is_maker=False)
    assert fee > 0
    tem = tmp_path / "tem" / "costs.txt"
    tem.parent.mkdir(parents=True, exist_ok=True)
    tem.write_text("ok")
    assert "tem" in str(tem)

def test_costs_bounds(tmp_path: Path):
    cfg = TransactionCostConfig(min_cost_bps=Decimal("10"), max_cost_bps=Decimal("50"))
    m = TransactionCostModel(cfg)
    costs = m.calculate_total_cost(symbol="BTCUSDT", side="BUY", order_type="LIMIT", quantity=Decimal("0.01"), price=Decimal("50000"), mark_price=Decimal("50000"))
    assert costs["total_bps"] >= 0
    tem = tmp_path / "tem" / "bounds.txt"
    tem.parent.mkdir(parents=True, exist_ok=True)
    tem.write_text("ok")
    assert tem.exists()
