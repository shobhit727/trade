"""Unit tests for the global-fund ledger (Seed Phase step 1)."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from cryptobot.core.fund import FundConfig, GlobalFundLedger


def make_ledger(tmp_path, **overrides) -> GlobalFundLedger:
    cfg = FundConfig(state_path=str(tmp_path / "fund.json"), **overrides)
    return GlobalFundLedger(cfg)


class FakeClock:
    """Injectable clock so daily-cap rollover is testable."""

    def __init__(self):
        self._now = datetime(2026, 8, 22, 12, 0, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self._now

    def advance(self, **kwargs) -> None:
        self._now += timedelta(**kwargs)


def test_skim_only_positive_pnl(tmp_path):
    led = make_ledger(tmp_path)
    assert led.skim(Decimal("-50")) is None
    assert led.skim(Decimal("0")) is None
    assert led.fund_balance == Decimal("0")
    assert led.history == []


def test_skim_math(tmp_path):
    led = make_ledger(tmp_path)
    entry = led.skim(Decimal("100"))
    assert entry is not None
    assert Decimal(entry["amount"]) == Decimal("10.00000000")
    assert led.fund_balance == Decimal("10")


def test_draw_happy_path(tmp_path):
    led = make_ledger(tmp_path)
    led.skim(Decimal("100"))  # fund = 10
    assert led.draw("algo-1", Decimal("3"), "margin top-up") is True  # == 30% cap
    assert led.fund_balance == Decimal("7")


def test_draw_rejections(tmp_path):
    led = make_ledger(tmp_path)
    led.skim(Decimal("100"))
    # empty reason
    assert led.draw("a", Decimal("1"), "   ") is False
    # non-positive amount
    assert led.draw("a", Decimal("0"), "why") is False
    assert led.draw("a", Decimal("-1"), "why") is False
    # frozen blocks draws
    led.freeze()
    assert led.draw("a", Decimal("1"), "why") is False
    # freeze also blocks skims
    assert led.skim(Decimal("100")) is None
    # nothing mutated by the rejected calls
    assert led.fund_balance == Decimal("10")
    led.unfreeze()
    assert led.draw("a", Decimal("1"), "why") is True
    assert led.fund_balance == Decimal("9")


def test_per_algo_daily_cap_independent(tmp_path):
    clock = FakeClock()
    cfg = FundConfig(state_path=str(tmp_path / "f.json"))
    led = GlobalFundLedger(cfg, now_fn=clock)
    led.skim(Decimal("1000"))  # fund = 100
    # algo A can draw up to 30% of current balance
    assert led.draw("A", Decimal("29"), "ok") is True  # fund -> 71
    # exceeding A's remaining cap rejects and leaves state unchanged
    before = (led.fund_balance, len(led.history))
    assert led.draw("A", Decimal("2"), "over cap") is False
    assert (led.fund_balance, len(led.history)) == before
    # algo B has its own independent cap: 30% of the *current* balance (71 -> 21.3)
    assert led.draw("B", Decimal("22"), "over B cap") is False
    assert led.draw("B", Decimal("21"), "ok too") is True


def test_cap_resets_next_utc_day(tmp_path):
    clock = FakeClock()
    cfg = FundConfig(state_path=str(tmp_path / "f.json"))
    led = GlobalFundLedger(cfg, now_fn=clock)
    led.skim(Decimal("1000"))  # fund = 100
    assert led.draw("A", Decimal("30"), "day one") is True  # fund -> 70
    assert led.draw("A", Decimal("1"), "still day one") is False
    clock.advance(hours=25)  # new UTC day: cap resets to 30% of 70 = 21
    assert led.draw("A", Decimal("21"), "day two") is True
    assert led.draw("A", Decimal("1"), "day two over cap") is False


def test_deposit_returns_funds(tmp_path):
    led = make_ledger(tmp_path)
    led.skim(Decimal("100"))  # fund = 10
    led.draw("A", Decimal("3"), "borrow")  # within 30% cap
    led.deposit("A", Decimal("3"))
    assert led.fund_balance == Decimal("10")


def test_persistence_roundtrip(tmp_path):
    path = str(tmp_path / "fund.json")
    led = GlobalFundLedger(FundConfig(state_path=path))
    led.skim(Decimal("200"))
    led.draw("X", Decimal("3"), "need")
    led.freeze()

    restored = GlobalFundLedger(FundConfig(state_path=path))
    assert restored.fund_balance == led.fund_balance
    assert restored.frozen is True
    assert restored.history == led.history


def test_missing_state_file_starts_fresh(tmp_path):
    led = GlobalFundLedger(FundConfig(state_path=str(tmp_path / "nope.json")))
    assert led.fund_balance == Decimal("0")
    assert led.frozen is False


def test_summary_shape(tmp_path):
    led = make_ledger(tmp_path)
    led.skim(Decimal("10"))
    s = led.summary()
    assert s["fund_balance"] == "1.00000000"
    assert s["frozen"] is False
    assert s["n_entries"] == 1


def test_corrupt_state_starts_fresh(tmp_path):
    bad = tmp_path / "fund.json"
    bad.write_text("{not json", encoding="utf-8")
    led = GlobalFundLedger(FundConfig(state_path=str(bad)))
    assert led.fund_balance == Decimal("0")
