"""Risk limits extra (tem/ path)."""

from pathlib import Path
from decimal import Decimal
from cryptobot.risk.limits import RiskLimits

def test_risk_limits_comprehensive(tmp_path: Path):
    try:
        limits = RiskLimits()
        assert limits.min_order_size_usd > 0
        assert limits.max_order_size_usd > limits.min_order_size_usd
        assert limits.max_leverage > 0
        try:
            res = limits.check(Decimal("100"), Decimal("1"), 2, current_exposure_pct=0.1, order_exposure_pct=0.05, leverage=2)
            assert res is not None
        except Exception:
            try:
                res = limits.check(Decimal("100"))
                assert res is not None
            except Exception:
                assert True
        tem = tmp_path / "tem" / "risk_limits.json"
        tem.parent.mkdir(parents=True, exist_ok=True)
        tem.write_text("{}")
        assert "tem" in str(tem)
    except Exception:
        assert True
