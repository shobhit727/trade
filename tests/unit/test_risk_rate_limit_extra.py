"""Risk rate_limit extra (tem/ path)."""

from pathlib import Path
import time
from cryptobot.risk.rate_limit import RateLimiter

def test_rate_limit_extra(tmp_path: Path):
    rl = RateLimiter(max_events=2, window_seconds=0.1)
    assert rl.try_acquire() is True
    assert rl.try_acquire() is True
    assert rl.try_acquire() is False
    assert rl.current_count == 2
    time.sleep(0.15)
    assert rl.try_acquire() is True
    rl.reset()
    assert rl.current_count == 0
    # invalid args
    try:
        RateLimiter(max_events=0, window_seconds=60)
        assert False
    except ValueError:
        assert True
    tem = tmp_path / "tem" / "rate.txt"
    tem.parent.mkdir(parents=True, exist_ok=True)
    tem.write_text("ok")
    assert "tem" in str(tem)
