"""Global fund ledger — the cross-algorithm profit reserve (Seed Phase step 1).

Every harvest window (default 8h) a fraction of *realized* profit is skimmed
into a shared pool. Algorithms may draw from the pool only to keep valid open
signals alive, subject to guardrails agreed in PROJECT_MEMORY/28:

- draws are blocked while the kill-switch freeze is active
- per-algorithm daily draw cap (fraction of the *current* balance)
- every mutation is persisted atomically so restarts never lose state

All money math is :class:`~decimal.Decimal` — floats are forbidden.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_QUANT = Decimal("0.00000001")


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class FundConfig:
    """Tunables for the global fund (all fractions are Decimals in [0, 1])."""

    skim_fraction: Decimal = Decimal("0.10")
    max_draw_fraction_per_day: Decimal = Decimal("0.30")
    state_path: str = "state/global_fund.json"


@dataclass
class GlobalFundLedger:
    """Virtual sub-ledger separating trading equity from the reserve pool."""

    config: FundConfig = field(default_factory=FundConfig)
    now_fn: Callable[[], datetime] = _utcnow

    def __post_init__(self) -> None:
        self._balance = Decimal("0")
        self.frozen = False
        self.history: list[dict[str, Any]] = []
        # Best-effort restore; a missing/corrupt file starts fresh.
        try:
            self.load(self.config.state_path)
        except Exception:  # noqa: BLE001 - corrupt state must not kill startup
            logger.warning("global-fund state at %s unreadable; starting fresh",
                           self.config.state_path)

    # ------------------------------------------------------------- properties

    @property
    def fund_balance(self) -> Decimal:
        return self._balance

    # ---------------------------------------------------------------- actions

    def skim(self, realized_pnl: Decimal) -> dict[str, Any] | None:
        """Move ``skim_fraction`` of positive realized PnL into the pool."""
        realized_pnl = Decimal(realized_pnl)
        if self.frozen or realized_pnl <= 0:
            return None
        amount = (realized_pnl * self.config.skim_fraction).quantize(_QUANT)
        self._balance += amount
        entry = self._record("skim", amount=amount, realized_pnl=realized_pnl)
        return entry

    def draw(self, algo_id: str, amount: Decimal, reason: str) -> bool:
        """Withdraw from the pool for a valid need; guarded, all-or-nothing."""
        amount = Decimal(amount)
        if self.frozen or not reason.strip() or amount <= 0:
            return False
        cap = self._balance * self.config.max_draw_fraction_per_day
        if self._daily_drawn(algo_id) + amount > cap:
            logger.info("fund draw rejected for %s: cap %.8f exceeded", algo_id, cap)
            return False
        self._balance -= amount
        self._record("draw", amount=amount, algo_id=algo_id, reason=reason)
        return True

    def deposit(self, algo_id: str, amount: Decimal) -> None:
        """Return borrowed funds to the pool."""
        self._balance += Decimal(amount).quantize(_QUANT)
        self._record("deposit", amount=Decimal(amount), algo_id=algo_id)

    def freeze(self) -> None:
        """Kill-switch hook: block all draws (and skims) until manual reset."""
        self.frozen = True
        self._record("freeze")

    def unfreeze(self) -> None:
        """Manual-reset action: re-enable pool operations."""
        self.frozen = False
        self._record("unfreeze")

    # --------------------------------------------------------------- internals

    def _daily_drawn(self, algo_id: str) -> Decimal:
        today = self.now_fn().date()
        return sum(
            (Decimal(e["amount"]) for e in self.history
             if e["type"] == "draw" and e.get("algo_id") == algo_id
             and datetime.fromisoformat(e["ts"]).date() == today),
            start=Decimal("0"),
        )

    def _record(self, type_: str, **fields: Any) -> dict[str, Any]:
        entry: dict[str, Any] = {"ts": self.now_fn().isoformat(), "type": type_, **fields}
        for key in ("amount", "realized_pnl"):
            if key in entry:
                entry[key] = str(entry[key])
        self.history.append(entry)
        self.save()
        return entry

    # ------------------------------------------------------------ persistence

    def save(self) -> None:
        path = Path(self.config.state_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "balance": str(self._balance),
            "frozen": self.frozen,
            "history": self.history,
        }
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        os.replace(tmp, path)

    def load(self, path: str | None = None) -> None:
        target = Path(path or self.config.state_path)
        if not target.exists():
            return
        data = json.loads(target.read_text(encoding="utf-8"))
        self._balance = Decimal(data["balance"])
        self.frozen = bool(data["frozen"])
        self.history = list(data["history"])

    def summary(self) -> dict[str, Any]:
        return {
            "fund_balance": str(self._balance),
            "frozen": self.frozen,
            "n_entries": len(self.history),
        }


__all__ = ["FundConfig", "GlobalFundLedger"]
