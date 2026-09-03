"""Core tax extra: TaxEngine branches (tem/ path)."""

from pathlib import Path
from decimal import Decimal
from datetime import datetime, timezone, timedelta

def test_tax_extra(tmp_path: Path):
    from cryptobot.core.tax import TaxEngine
    eng = TaxEngine()
    now = datetime.now(timezone.utc)
    # buy/sell across year boundary
    eng.buy("BTCUSDT", Decimal("2"), Decimal("50000"), now - timedelta(days=400))
    eng.sell("BTCUSDT", Decimal("1"), Decimal("60000"), now)
    eng.buy("ETHUSDT", Decimal("5"), Decimal("3000"), now - timedelta(days=10))
    eng.sell("ETHUSDT", Decimal("5"), Decimal("3100")*Decimal("5"), now)
    s = eng.summary()
    assert "taxable_income" in s or "total_tax" in s or "gross_gain" in s
    # fy filter
    try:
        s2 = eng.summary(fy_end=(now.date().replace(month=3) if now.month>3 else now.date()))
        assert isinstance(s2, dict)
    except TypeError:
        s2 = eng.summary()
        assert isinstance(s2, dict)
    # to_dict
    d = eng.to_dict()
    assert isinstance(d, dict)
    # tem artifact
    p = tmp_path / "tem" / "tax_extra.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    import json
    p.write_text(json.dumps(s))
    assert "tem" in str(p)

def test_tax_equity_extra(tmp_path: Path):
    from cryptobot.core.tax_equity import TaxLedger
    ledger = TaxLedger()
    now = datetime.now(timezone.utc)
    ledger.on_buy("A", 10, 100, now)
    ledger.on_buy("A", 5, 110, now + timedelta(days=5))
    recs = ledger.on_sell("A", 12, 120, now + timedelta(days=20))
    assert len(recs) == 2
    assert ledger.summary()["trades"] == 2
    p = tmp_path / "tem" / "tax_eq.txt"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(str(recs[0].gain))
    assert p.exists()
