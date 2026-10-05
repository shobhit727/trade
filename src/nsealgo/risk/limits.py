"""Hard risk limits and the kill switch.

`GOAL.md` §3.3 is binding: these numbers are **hard-coded** and cannot be raised by any
config flag, environment variable, or command-line argument. That is deliberate. The
single most dangerous property of a trading system is the ability to quietly widen its
own risk limits; this module makes that impossible by construction.

`RiskLimits` is a frozen dataclass with no "relax" setter. `verify_limits()` re-asserts
the values at import time so that a well-meaning edit cannot silently raise them.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from decimal import Decimal as D


class RiskLimitViolation(RuntimeError):
    """Raised when a limit is breached. The engine must not swallow this."""


class KillSwitchEngaged(RiskLimitViolation):
    """Raised when the kill switch is engaged and trading must stop."""


# --------------------------------------------------------------------------- #
# §3.3 — these values are the constitution. Do not parameterise them.
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class RiskLimits:
    """Capital-preservation limits. Frozen: no code path may widen them."""

    initial_capital: D = D("2100000")

    # --- drawdown
    max_drawdown_halt: D = D("0.15")      # -15% -> flatten and stop trading
    max_drawdown_absolute: D = D("0.25")   # -25% -> permanent capital-preservation mode
    per_trade_stop: D = D("0.08")          # -8% from entry, checked pre-order

    # --- intra-period loss
    max_daily_loss: D = D("0.02")          # -2.0% of equity -> intraday kill switch
    max_weekly_loss: D = D("0.04")         # -4.0% -> halt and review

    # --- concentration (§3.2)
    max_single_weight: D = D("0.12")       # 12%
    max_sector_weight: D = D("0.25")       # 25%
    min_position_weight: D = D("0.015")    # 1.5%
    max_positions: int = 30
    min_positions: int = 18
    min_cash_buffer: D = D("0.05")         # never deploy the last 5%

    def verify(self) -> None:
        """Re-assert the constitution. Called at import time."""
        expected = {
            "max_drawdown_halt": D("0.15"),
            "max_drawdown_absolute": D("0.25"),
            "per_trade_stop": D("0.08"),
            "max_daily_loss": D("0.02"),
            "max_weekly_loss": D("0.04"),
            "max_single_weight": D("0.12"),
            "max_sector_weight": D("0.25"),
            "min_position_weight": D("0.015"),
        }
        for name, want in expected.items():
            got = getattr(self, name)
            if got != want:
                raise RiskLimitViolation(
                    f"GOAL.md §3.3 violation: {name} is {got}, must be {want}. "
                    "Risk limits are hard-coded and must not be raised."
                )
        if self.min_positions > self.max_positions:
            raise RiskLimitViolation("min_positions exceeds max_positions")


LIMITS = RiskLimits()
LIMITS.verify()


# --------------------------------------------------------------------------- #
# Runtime risk state
# --------------------------------------------------------------------------- #


@dataclass
class RiskState:
    """Mutable *state* (not limits). Updated each cycle by the live engine."""

    equity_peak: D = D("0")
    equity: D = D("0")
    day_start_equity: D = D("0")
    week_start_equity: D = D("0")

    def drawdown(self) -> D:
        if self.equity_peak <= 0:
            return D("0")
        return (self.equity / self.equity_peak) - D("1")

    def day_pnl(self) -> D:
        if self.day_start_equity <= 0:
            return D("0")
        return (self.equity / self.day_start_equity) - D("1")

    def week_pnl(self) -> D:
        if self.week_start_equity <= 0:
            return D("0")
        return (self.equity / self.week_start_equity) - D("1")


class RiskManager:
    """Pre-trade and post-trade risk enforcement."""

    def __init__(self, limits: RiskLimits = LIMITS) -> None:
        self.limits = limits
        self.state = RiskState(
            equity_peak=limits.initial_capital,
            equity=limits.initial_capital,
            day_start_equity=limits.initial_capital,
            week_start_equity=limits.initial_capital,
        )
        self.kill_switch_reason: str | None = None
        #: Every breached limit this cycle, most severe first.
        self.breached_limits: list[str] = []

    # ------------------------------------------------------------------ #
    def update_equity(self, equity: D) -> None:
        """Recompute state and trip the kill switch if any limit is breached."""
        self.state.equity = equity
        if equity > self.state.equity_peak:
            self.state.equity_peak = equity
        self._check_switches()

    def start_day(self, equity: D) -> None:
        self.state.day_start_equity = equity

    def start_week(self, equity: D) -> None:
        self.state.week_start_equity = equity

    # ------------------------------------------------------------------ #
    def _check_switches(self) -> None:
        """Record every breached limit, reporting the most severe first.

        Ordering matters operationally: a −29% absolute drawdown that also happens to
        look like a big daily loss must be reported as the absolute drawdown, because
        that is the condition an operator must respond to.
        """
        lim = self.limits
        breaches: list[tuple[int, str]] = []

        dd = self.state.drawdown()
        if dd <= -lim.max_drawdown_absolute:
            breaches.append((0, f"ABSOLUTE DRAWDOWN {dd:.2%} breached the -"
                                f"{lim.max_drawdown_absolute:.0%} "
                                "capital-preservation limit"))
        elif dd <= -lim.max_drawdown_halt:
            breaches.append((3, f"DRAWDOWN {dd:.2%} breached the -"
                                f"{lim.max_drawdown_halt:.0%} halt limit"))

        day = self.state.day_pnl()
        if day <= -lim.max_daily_loss:
            breaches.append((1, f"DAILY LOSS {day:.2%} breached the -"
                                f"{lim.max_daily_loss:.0%} limit"))

        week = self.state.week_pnl()
        if week <= -lim.max_weekly_loss:
            breaches.append((2, f"WEEKLY LOSS {week:.2%} breached the -"
                                f"{lim.max_weekly_loss:.0%} limit"))

        if breaches:
            breaches.sort(key=lambda b: b[0])
            self.kill_switch_reason = breaches[0][1]
            self.breached_limits = [m for _, m in breaches]

    @property
    def is_halted(self) -> bool:
        return self.kill_switch_reason is not None

    def assert_tradable(self) -> None:
        """Call before any order. Raises if halted."""
        if self.is_halted:
            raise KillSwitchEngaged(self.kill_switch_reason or "kill switch engaged")

    def reset(self, equity: D) -> None:
        """Clear the kill switch. **Requires explicit human action in production.**"""
        self.kill_switch_reason = None
        self.breached_limits = []
        self.state = RiskState(equity, equity, equity, equity)

    # ------------------------------------------------------------------ #
    def check_order(
        self,
        symbol: str,
        weight: D,
        weights: dict[str, D],
        sectors: dict[str, str],
    ) -> None:
        """Validate a single intended weight against every concentration limit."""
        self.assert_tradable()
        lim = self.limits

        if weight > lim.max_single_weight:
            raise RiskLimitViolation(
                f"{symbol}: weight {weight:.2%} exceeds max single-name "
                f"{lim.max_single_weight:.0%}"
            )

        post = dict(weights)
        post[symbol] = weight
        n = sum(1 for w in post.values() if w > 0)
        if n > lim.max_positions:
            raise RiskLimitViolation(
                f"{n} positions exceeds max_positions {lim.max_positions}"
            )

        sec = sectors.get(symbol, "other")
        sec_total = sum(w for s, w in post.items() if sectors.get(s, "other") == sec)
        if sec_total > lim.max_sector_weight:
            raise RiskLimitViolation(
                f"sector '{sec}' would be {sec_total:.2%}, exceeds max_sector_weight "
                f"{lim.max_sector_weight:.0%}"
            )

        cash = D("1") - sum(post.values())
        if cash < lim.min_cash_buffer:
            raise RiskLimitViolation(
                f"cash buffer {cash:.2%} would fall below minimum "
                f"{lim.min_cash_buffer:.0%}"
            )

    # ------------------------------------------------------------------ #
    def check_stop(self, entry_price: D, current_price: D) -> None:
        """Per-trade stop. Raises if breached."""
        if entry_price <= 0:
            raise ValueError("entry_price must be positive")
        drop = (current_price / entry_price) - D("1")
        if drop <= -self.limits.per_trade_stop:
            raise RiskLimitViolation(
                f"per-trade stop hit: {drop:.2%} breaches -"
                f"{self.limits.per_trade_stop:.0%}"
            )


def limits_as_dict() -> dict[str, object]:
    """Serialisable view of the constitution, for health endpoints and audit logs."""
    return {f.name: getattr(LIMITS, f.name) for f in fields(RiskLimits)}
