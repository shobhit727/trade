from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal


@dataclass
class StrategyRiskState:
    """Per-strategy risk snapshot."""

    strategy: str
    peak_equity: Decimal = Decimal("0")
    daily_pnl: Decimal = Decimal("0")
    daily_pnl_start: Decimal = Decimal("0")
    max_drawdown: Decimal = Decimal("0")
    total_pnl: Decimal = Decimal("0")
    last_reset_day: int = 0


class StrategyRiskTracker:
    """Aggregates per-strategy risk metrics from order/position events."""

    def __init__(self):
        self._states: dict[str, StrategyRiskState] = defaultdict(
            lambda: StrategyRiskState(strategy="")
        )

    def record_pnl(self, strategy: str, pnl: Decimal, day_key: int) -> None:
        st = self._states[strategy]
        st.strategy = strategy
        st.total_pnl += pnl
        st.daily_pnl += pnl
        st.last_reset_day = day_key
        equity = st.peak_equity + pnl
        if equity > st.peak_equity:
            st.peak_equity = equity
            st.max_drawdown = Decimal("0")
        elif st.peak_equity > 0:
            dd = (st.peak_equity - equity) / st.peak_equity
            if dd > st.max_drawdown:
                st.max_drawdown = dd

    def reset_daily(self, strategy: str, equity: Decimal, day_key: int) -> None:
        st = self._states[strategy]
        st.strategy = strategy
        st.daily_pnl = Decimal("0")
        st.daily_pnl_start = equity
        st.last_reset_day = day_key

    def get(self, strategy: str) -> StrategyRiskState:
        if strategy not in self._states:
            self._states[strategy] = StrategyRiskState(strategy=strategy)
        return self._states[strategy]

    def all(self) -> dict[str, StrategyRiskState]:
        return dict(self._states)


__all__ = ["StrategyRiskState", "StrategyRiskTracker"]
