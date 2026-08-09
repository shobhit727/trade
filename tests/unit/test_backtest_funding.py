"""Funding-rate plumbing: provider semantics + 8h settlement accrual."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from cryptobot.backtest.funding import (
    CsvFundingProvider,
    FixedFundingProvider,
    funding_cashflow,
)


def test_funding_cashflow_long_pays_short_receives():
    qty = Decimal("2")
    mark = Decimal("100")
    rate = Decimal("0.001")
    assert funding_cashflow("LONG", qty, mark, rate) == Decimal("-0.2")
    assert funding_cashflow("SHORT", qty, mark, rate) == Decimal("0.2")
    assert funding_cashflow("LONG", qty, mark, -rate) == Decimal("0.2")
    assert funding_cashflow("LONG", Decimal("0"), mark, rate) == Decimal("0")
    assert funding_cashflow("LONG", qty, Decimal("0"), rate) == Decimal("0")
    assert funding_cashflow("LONG", qty, mark, Decimal("0")) == Decimal("0")


def test_fixed_funding_provider_constant(tmp_path):
    p = FixedFundingProvider(Decimal("0.0001"))
    ts = datetime(2024, 1, 1, 8, 0, tzinfo=UTC)
    assert p.rate("BTCUSDT", ts) == Decimal("0.0001")
    assert FixedFundingProvider.is_settlement(ts)
    assert not FixedFundingProvider.is_settlement(datetime(2024, 1, 1, 9, 0, tzinfo=UTC))


def test_csv_funding_provider_no_lookahead(tmp_path):
    csv_path = tmp_path / "funding.csv"
    csv_path.write_text(
        "funding_time,funding_rate\n"
        "1704067200000,0.00010000\n"  # 2024-01-01 00:00 UTC
        "1704096000000,0.00020000\n"  # 2024-01-01 08:00 UTC
    )
    p = CsvFundingProvider(str(csv_path))
    before = datetime(2023, 12, 31, 23, 0, tzinfo=UTC)
    at_first = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
    mid = datetime(2024, 1, 1, 4, 0, tzinfo=UTC)
    at_second = datetime(2024, 1, 1, 8, 0, tzinfo=UTC)
    assert p.rate("BTCUSDT", before) == Decimal("0")
    assert p.rate("BTCUSDT", at_first) == Decimal("0.0001")
    assert p.rate("BTCUSDT", mid) == Decimal("0.0001")
    assert p.rate("BTCUSDT", at_second) == Decimal("0.0002")


def test_csv_funding_provider_empty_file(tmp_path):
    csv_path = tmp_path / "empty.csv"
    csv_path.write_text("funding_time,funding_rate\n")
    p = CsvFundingProvider(str(csv_path))
    assert p.rate("BTCUSDT", datetime(2024, 1, 1, tzinfo=UTC)) == Decimal("0")
