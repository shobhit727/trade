"""Unit tests for the 60-day paper gate (Seed Phase step 5)."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from cryptobot.core.gate import GateConfig, GateStatus, PaperGateTracker


class FakeClock:
    def __init__(self):
        self._now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self._now

    def advance_days(self, n=1):
        self._now += timedelta(days=n)


def make_tracker(tmp_path, **cfg_overrides) -> tuple[PaperGateTracker, FakeClock]:
    clock = FakeClock()
    cfg = GateConfig(state_path=str(tmp_path / "gate.json"),
                     min_days=6, extension_days=3, max_extensions=2,
                     **cfg_overrides)
    return PaperGateTracker(cfg, now_fn=clock), clock


def feed(tracker, clock, equities, submitted=100, rejects=0):
    for eq in equities:
        tracker.record_day(Decimal(str(eq)), submitted, rejects)
        clock.advance_days()


def test_collecting_before_window(tmp_path):
    tr, clock = make_tracker(tmp_path)
    feed(tr, clock, [100, 101, 102])
    res = tr.evaluate()
    assert res["status"] == GateStatus.COLLECTING
    assert res["days_elapsed"] == 3
    assert tr.allows_live() == (False, "gate still collecting (3/6 days)")


def test_pass_happy_path(tmp_path):
    tr, clock = make_tracker(tmp_path)
    # steady growth: net positive, positive sharpe, no rejects, no trips
    feed(tr, clock, [100, 101, 102, 103, 104, 105])
    res = tr.evaluate()
    assert res["status"] == GateStatus.PASSED
    assert all(res["criteria"].values())
    assert tr.allows_live()[0] is True


def test_fail_then_extend_then_pass(tmp_path):
    tr, clock = make_tracker(tmp_path)
    feed(tr, clock, [100, 99, 98, 97, 96, 95])   # window 1: negative
    res = tr.evaluate()
    assert res["status"] == GateStatus.EXTENDED
    assert res["window_days"] == 9               # 6 + 3
    assert res["extensions_used"] == 1
    # keep feeding winning days until the widened window fills
    feed(tr, clock, [96, 97, 98])                # days 7-9 recover above start? still < 100
    res = tr.evaluate()
    assert res["status"] == GateStatus.EXTENDED  # still net-negative -> second extension
    assert res["window_days"] == 12
    feed(tr, clock, [99, 101, 102])              # days 10-12: crosses start
    res = tr.evaluate()
    assert res["status"] == GateStatus.PASSED


def test_fail_permanently_after_max_extensions(tmp_path):
    tr, clock = make_tracker(tmp_path)
    feed(tr, clock, [100, 90, 90, 90, 90, 90])
    assert tr.evaluate()["status"] == GateStatus.EXTENDED
    feed(tr, clock, [90, 90, 90])
    assert tr.evaluate()["status"] == GateStatus.EXTENDED
    feed(tr, clock, [90, 90, 90])
    res = tr.evaluate()
    assert res["status"] == GateStatus.FAILED_FINAL
    ok, reason = tr.allows_live()
    assert ok is False and "review" in reason


def test_reject_rate_criterion(tmp_path):
    tr, clock = make_tracker(tmp_path, max_reject_rate=0.05)
    feed(tr, clock, [100, 101, 102, 103, 104, 105], submitted=100, rejects=10)
    res = tr.evaluate()
    assert res["criteria"]["reject_rate_ok"] is False
    assert res["status"] != GateStatus.PASSED


def test_breaker_trip_blocks_gate(tmp_path):
    tr, _ = make_tracker(tmp_path)
    tr.record_day(Decimal("100"), 10, 0)
    tr.record_day(Decimal("101"), 10, 0, breaker_trips=1)
    crit = tr._criteria_snapshot()
    assert crit["no_breaker_trips"] is False


def test_same_day_rerecord_overwrites(tmp_path):
    tr, _ = make_tracker(tmp_path)
    tr.record_day(Decimal("100"), 5, 0)
    tr.record_day(Decimal("110"), 8, 1)          # same fake day
    assert len(tr.snapshots) == 1
    assert tr.snapshots[0]["equity"] == "110"
    assert tr.snapshots[0]["rejects"] == 1


def test_sharpe_zero_when_flat(tmp_path):
    tr, clock = make_tracker(tmp_path, sharpe_threshold=1.0)
    feed(tr, clock, [100, 100, 100, 100, 100, 100])
    res = tr.evaluate()
    assert res["criteria"]["sharpe_ok"] is False  # zero variance -> sharpe 0
    assert res["criteria"]["net_positive"] is False


def test_persistence_roundtrip(tmp_path):
    path = tmp_path / "gate.json"
    clock = FakeClock()
    tr = PaperGateTracker(GateConfig(state_path=str(path), min_days=6,
                                     extension_days=3, max_extensions=2),
                          now_fn=clock)
    feed(tr, clock, [100, 101, 102])

    restored = PaperGateTracker(GateConfig(state_path=str(path), min_days=6,
                                           extension_days=3, max_extensions=2),
                                now_fn=clock)
    assert restored.days_elapsed() == 3
    assert restored.snapshots == tr.snapshots
    assert restored.status == GateStatus.COLLECTING


def test_missing_state_starts_fresh(tmp_path):
    tr = PaperGateTracker(GateConfig(state_path=str(tmp_path / "none.json")))
    assert tr.days_elapsed() == 0
    assert tr.started_at is None
