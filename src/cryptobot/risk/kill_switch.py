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
        self.active, self.reason = portfolio.check_kill_switch()
        return self.active, self.reason

    def reset(self) -> None:
        self.active = False
        self.reason = ""


__all__ = ["KillSwitch"]
