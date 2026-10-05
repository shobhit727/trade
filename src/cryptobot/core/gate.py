"""60-day paper-gate tracker (Seed Phase step 5).

The gate stands between paper trading and real money:

- one equity snapshot per UTC day while the bot runs
- after ``min_days`` snapshots the criteria are evaluated:
    * net-positive over the window
    * annualized Sharpe of daily equity returns >= threshold
    * order reject rate <= tolerance ("fills match simulation")
    * zero circuit-breaker trips
- failure auto-extends the window by ``extension_days`` (max ``max_extensions``
  times); exhausting extensions fails the gate finally
- live mode is refused until status == PASSED

State persists as JSON so restarts never reset progress.
"""

from __future__ import annotations

import json
import logging
import os
import statistics
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class GateStatus:
    COLLECTING = "collecting"
    PASSED = "passed"
    EXTENDED = "extended"      # failed once/twice, window widened, still collecting
    FAILED_FINAL = "failed_final"


@dataclass
class GateConfig:
    state_path: str = "state/paper_gate.json"
    min_days: int = 60
    extension_days: int = 30
    max_extensions: int = 2
    sharpe_threshold: float = 1.0
    max_reject_rate: float = 0.05          # 5% of submitted orders rejected
    periods_per_year: int = 365            # crypto trades every day


@dataclass
class PaperGateTracker:
    config: GateConfig = field(default_factory=GateConfig)
    now_fn: Any = datetime.now

    def __post_init__(self) -> None:
        self.started_at: date | None = None
        self.window_days: int = self.config.min_days
        self.extensions_used: int = 0
        self.status: str = GateStatus.COLLECTING
        self.snapshots: list[dict[str, Any]] = []
        self.breaker_trips: int = 0
        try:
            self.load(self.config.state_path)
        except Exception:  # noqa: BLE001 - corrupt state must not kill startup
            logger.warning("gate state at %s unreadable; starting fresh",
                           self.config.state_path)

    # -------------------------------------------------------------- recording

    def record_day(self, equity: Decimal, orders_submitted: int,
                   rejects: int, breaker_trips: int | None = None) -> None:
        """Idempotent per UTC day: re-recording today overwrites today's row."""
        today = self.now_fn().date()
        if self.started_at is None:
            self.started_at = today
        if breaker_trips is not None:
            self.breaker_trips = breaker_trips
        row = {
            "date": today.isoformat(),
            "equity": str(equity),
            "orders_submitted": int(orders_submitted),
            "rejects": int(rejects),
        }
        for i, existing in enumerate(self.snapshots):
            if existing["date"] == row["date"]:
                self.snapshots[i] = row
                break
        else:
            self.snapshots.append(row)
        self.save()

    def days_elapsed(self) -> int:
        if self.started_at is None or not self.snapshots:
            return 0
        return len(self.snapshots)

    # ------------------------------------------------------------ evaluation

    def _daily_returns(self) -> list[float]:
        equities = [float(s["equity"]) for s in self.snapshots]
        return [
            equities[i] / equities[i - 1] - 1.0
            for i in range(1, len(equities))
            if equities[i - 1] > 0
        ]

    def evaluate(self) -> dict[str, Any]:
        """Evaluate criteria; advances the status machine when due."""
        days = self.days_elapsed()
        result: dict[str, Any] = {
            "status": self.status,
            "days_elapsed": days,
            "window_days": self.window_days,
            "extensions_used": self.extensions_used,
            "criteria": {},
        }
        if self.status in (GateStatus.PASSED, GateStatus.FAILED_FINAL):
            result["criteria"] = self._criteria_snapshot()
            return result
        if days < self.window_days or len(self.snapshots) < 3:
            result["criteria"] = self._criteria_snapshot()
            return result

        criteria = self._criteria_snapshot()
        result["criteria"] = criteria
        if all(criteria.values()):
            self.status = GateStatus.PASSED
        else:
            if self.extensions_used < self.config.max_extensions:
                self.extensions_used += 1
                self.window_days += self.config.extension_days
                self.status = GateStatus.EXTENDED
                logger.warning("paper gate failed; extended to %d days (use %d/%d)",
                               self.window_days, self.extensions_used,
                               self.config.max_extensions)
            else:
                self.status = GateStatus.FAILED_FINAL
                logger.error("paper gate FAILED permanently after %d days",
                             self.window_days)
        result["status"] = self.status
        result["window_days"] = self.window_days
        result["extensions_used"] = self.extensions_used
        self.save()
        return result

    def _criteria_snapshot(self) -> dict[str, bool]:
        snaps = self.snapshots
        if len(snaps) < 2:
            return {"net_positive": False, "sharpe_ok": False,
                    "reject_rate_ok": False, "no_breaker_trips": False}
        first = float(snaps[0]["equity"])
        last = float(snaps[-1]["equity"])
        net_positive = last > first > 0

        rets = self._daily_returns()
        if len(rets) >= 2 and statistics.pstdev(rets) > 0:
            sharpe = (statistics.fmean(rets) / statistics.pstdev(rets)) \
                * (self.config.periods_per_year ** 0.5)
        else:
            sharpe = 0.0

        submitted = sum(int(s["orders_submitted"]) for s in snaps)
        rejects = sum(int(s["rejects"]) for s in snaps)
        reject_rate = (rejects / submitted) if submitted else 0.0

        return {
            "net_positive": net_positive,
            "sharpe_ok": sharpe >= self.config.sharpe_threshold,
            "reject_rate_ok": reject_rate <= self.config.max_reject_rate,
            "no_breaker_trips": self.breaker_trips == 0,
        }

    def allows_live(self) -> tuple[bool, str]:
        if self.status == GateStatus.PASSED:
            return True, "gate passed"
        if self.status == GateStatus.FAILED_FINAL:
            return False, "gate failed permanently; strategy review required"
        days = self.days_elapsed()
        return False, f"gate still collecting ({days}/{self.window_days} days)"

    # ------------------------------------------------------------ persistence

    def save(self) -> None:
        path = Path(self.config.state_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "window_days": self.window_days,
            "extensions_used": self.extensions_used,
            "status": self.status,
            "breaker_trips": self.breaker_trips,
            "snapshots": self.snapshots,
        }
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        os.replace(tmp, path)

    def load(self, path: str | None = None) -> None:
        target = Path(path or self.config.state_path)
        if not target.exists():
            return
        data = json.loads(target.read_text(encoding="utf-8"))
        self.started_at = date.fromisoformat(data["started_at"]) if data.get("started_at") else None
        self.window_days = int(data.get("window_days", self.config.min_days))
        self.extensions_used = int(data.get("extensions_used", 0))
        self.status = data.get("status", GateStatus.COLLECTING)
        self.breaker_trips = int(data.get("breaker_trips", 0))
        self.snapshots = list(data.get("snapshots", []))

    def summary(self) -> dict[str, Any]:
        allowed, reason = self.allows_live()
        return {
            "status": self.status,
            "days_elapsed": self.days_elapsed(),
            "window_days": self.window_days,
            "extensions_used": self.extensions_used,
            "allows_live": allowed,
            "reason": reason,
        }


def timedelta_to_today(now_fn: Any = datetime.now) -> date:  # pragma: no cover
    return now_fn().date()


__all__ = ["GateConfig", "GateStatus", "PaperGateTracker"]
