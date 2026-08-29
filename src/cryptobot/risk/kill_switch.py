from __future__ import annotations

from dataclasses import dataclass

from cryptobot.config import settings
from cryptobot.core.portfolio import PortfolioManager


@dataclass
class KillSwitch:
    active: bool = False
    reason: str = ""

    def evaluate(self, portfolio: PortfolioManager) -> tuple[bool, str]:
        if not settings.risk.kill_switch_enabled:
            self.active = False
            self.reason = ""
            return False, ""
        # Latch: once tripped, stay tripped until an explicit reset() so a
        # transient recovery in portfolio metrics cannot silently re-arm trading.
        if self.active:
            return True, self.reason
        active, reason = portfolio.check_kill_switch()
        if active:
            self.active = True
            self.reason = reason
        return active, reason

    def reset(self) -> None:
        self.active = False
        self.reason = ""


__all__ = ["KillSwitch"]
