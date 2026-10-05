"""Equity circuit breaker (Seed Phase step 6).

Agreed rule: a drawdown of 25% from peak equity trips the breaker —

1. trading halts (no new entries),
2. open positions close *gracefully*: profitable positions first, capturing
   open profit while restoring liquidity,
3. the global fund freezes and the paper gate records a breaker trip,
4. restarting requires an explicit manual reset (CLI).

State persists so a restart cannot silently un-trip it.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class BreakerConfig:
    state_path: str = "state/breaker.json"
    max_drawdown: Decimal = Decimal("-0.25")  # fraction of peak equity


@dataclass
class CircuitBreaker:
    config: BreakerConfig = field(default_factory=BreakerConfig)

    def __post_init__(self) -> None:
        self.tripped: bool = False
        self.reason: str = ""
        self.tripped_at: str = ""
        try:
            self.load(self.config.state_path)
        except Exception:  # noqa: BLE001
            logger.warning("breaker state at %s unreadable; starting fresh",
                           self.config.state_path)

    # ------------------------------------------------------------------ check

    def check(self, peak_equity: Decimal, current_equity: Decimal) -> bool:
        """True if this drawdown should trip the breaker."""
        if self.tripped or peak_equity <= 0:
            return False
        drawdown = (current_equity - peak_equity) / peak_equity
        return drawdown <= self.config.max_drawdown

    def trip(self, reason: str, now_iso: str = "") -> None:
        if self.tripped:
            return
        self.tripped = True
        self.reason = reason
        self.tripped_at = now_iso
        logger.error("CIRCUIT BREAKER TRIPPED: %s", reason)
        self.save()

    def reset(self) -> None:
        """Manual-reset action (CLI only by convention)."""
        logger.warning("circuit breaker manually reset")
        self.tripped = False
        self.reason = ""
        self.tripped_at = ""
        self.save()

    # --------------------------------------------------------- close ordering

    @staticmethod
    def close_order(positions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Profit-first liquidation order: biggest unrealized profit first.

        Positions are dicts with at least ``unrealized_pnl`` (Decimal/str).
        Losing positions go last, most-negative last of all.
        """
        def pnl_key(pos: dict[str, Any]) -> Decimal:
            try:
                return Decimal(str(pos.get("unrealized_pnl", "0")))
            except Exception:  # noqa: BLE001
                return Decimal("0")

        return sorted(positions, key=pnl_key, reverse=True)

    # ------------------------------------------------------------ persistence

    def save(self) -> None:
        path = Path(self.config.state_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "tripped": self.tripped,
            "reason": self.reason,
            "tripped_at": self.tripped_at,
        }
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        os.replace(tmp, path)

    def load(self, path: str | None = None) -> None:
        target = Path(path or self.config.state_path)
        if not target.exists():
            return
        data = json.loads(target.read_text(encoding="utf-8"))
        self.tripped = bool(data.get("tripped", False))
        self.reason = data.get("reason", "")
        self.tripped_at = data.get("tripped_at", "")

    def summary(self) -> dict[str, Any]:
        return {
            "tripped": self.tripped,
            "reason": self.reason,
            "max_drawdown": str(self.config.max_drawdown),
        }


__all__ = ["BreakerConfig", "CircuitBreaker"]
