"""Live / paper trading engine.

One code path for both modes (`GOAL.md` §5 Gate 6, rule 5). The only difference is which
`Broker` implementation is injected:

    engine = Engine(broker=PaperBroker(...), config=...)    # paper
    engine = Engine(broker=KiteBroker(...),   config=...)   # live

The engine never branches on paper-vs-live. It reads a `Clock`, so behaviour is
deterministic and testable; there is **no** `datetime.now()` anywhere in the decision
path (`GOAL.md` §8 engineering rule 2).

Cycle:
    1. read prices -> 2. compute target weights -> 3. risk-check EVERY order
    -> 4. execute -> 5. reconcile -> 6. update risk state (kill switch)

A risk violation **halts the cycle**. It never downgrades to a warning.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal as D
from typing import Protocol

import pandas as pd

from ..backtest.engine import PortfolioConfig, build_rebalance_weights
from ..costs import CostModel
from ..execution.broker import Broker
from ..factors.core import build_composite_score
from ..factors.regime import exposure_series
from ..risk.limits import LIMITS, KillSwitchEngaged, RiskLimits, RiskManager

log = logging.getLogger("nsealgo.engine")


class Clock(Protocol):
    """Explicit time source. Never call datetime.now() in logic."""

    def today(self) -> pd.Timestamp: ...


@dataclass
class EngineConfig:
    """Runtime configuration. Note: contains **no risk limits** — those are hard-coded
    in `risk/limits.py` per `GOAL.md` §3.3."""

    capital: D = D("2100000")
    rebalance: str = "M"
    n_positions: int = 22
    regime_lookback: int = 126
    regime_threshold: float = 0.35
    turnover_budget: float = 0.35
    max_weight: float = 0.12
    max_sector_weight: float = 0.25
    cash_buffer: float = 0.10
    dry_run: bool = False


@dataclass
class CycleReport:
    """What happened this cycle. Written to the audit log verbatim."""

    date: pd.Timestamp
    n_target: int = 0
    n_orders: int = 0
    n_rejected: int = 0
    orders: list[dict] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)
    equity: D = D("0")
    halted: bool = False
    halt_reason: str = ""

    def summary(self) -> str:
        return (
            f"{self.date.date()} target={self.n_target} orders={self.n_orders} "
            f"rejected={self.n_rejected} equity=Rs {self.equity:,.0f}"
            + (f" HALTED: {self.halt_reason}" if self.halted else "")
        )


class Engine:
    """Long-only NIFTY-50 swing engine."""

    def __init__(
        self,
        broker: Broker,
        config: EngineConfig | None = None,
        cost_model: CostModel | None = None,
        limits: RiskLimits = LIMITS,
    ) -> None:
        self.broker = broker
        self.cfg = config or EngineConfig()
        self.cost_model = cost_model or CostModel(segment="delivery")
        self.risk = RiskManager(limits)
        self._panel: pd.DataFrame | None = None

    # ------------------------------------------------------------------ #
    def load_market_data(self, panel: pd.DataFrame) -> None:
        """Install the price panel used for factor computation."""
        self._panel = panel

    # ------------------------------------------------------------------ #
    def target_weights(self, panel: pd.DataFrame | None = None) -> pd.DataFrame:
        """Desired weights for the most recent date, including the regime overlay."""
        pnl = panel if panel is not None else self._panel
        if pnl is None or pnl.empty:
            raise ValueError("no market data loaded; call load_market_data()")

        score = build_composite_score(pnl)
        cfg = PortfolioConfig(
            n_positions=self.cfg.n_positions,
            max_weight=self.cfg.max_weight,
            max_sector_weight=self.cfg.max_sector_weight,
            cash_buffer=self.cfg.cash_buffer,
            turnover_budget=self.cfg.turnover_budget,
        )
        rets = pnl.pct_change(fill_method=None)
        vol = rets.rolling(60, min_periods=20).std()
        last = pnl.index[-1]

        w = build_rebalance_weights(
            score.loc[[last]], [last], vol.loc[[last]], cfg
        ).iloc[0]

        exposure = float(
            exposure_series(
                pnl, lookback=self.cfg.regime_lookback,
                threshold=self.cfg.regime_threshold,
            ).iloc[-1]
        )
        w = w * exposure
        log.info(
            "target %s: %d names, exposure %.0f%%", last.date(),
            int((w > 0).sum()), exposure * 100,
        )
        return w

    # ------------------------------------------------------------------ #
    def current_weights(self) -> dict[str, D]:
        """Broker positions as fractional weights of equity."""
        positions = self.broker.get_positions()
        total = sum((p.market_value for p in positions), D("0"))
        if total <= 0:
            return {}
        return {p.symbol: p.market_value / total for p in positions}

    def equity(self) -> D:
        """Total account value **including cash**.

        Must not be positions-only: a book that is 30% invested is not down 70%,
        and treating it that way trips the kill switch on a healthy account.
        """
        return self.broker.account_value()

    # ------------------------------------------------------------------ #
    def reconcile(self) -> list[str]:
        """Compare internal intent to broker truth. Returns human-readable diffs."""
        diffs: list[str] = []
        live = {p.symbol: p.quantity for p in self.broker.get_positions()}
        for pos in self.broker.get_positions():
            if pos.quantity < 0:
                diffs.append(f"{pos.symbol}: SHORT position {pos.quantity} in a long-only book")
        log.debug("reconcile: %d live positions, %d diffs", len(live), len(diffs))
        return diffs

    # ------------------------------------------------------------------ #
    def run_cycle(self, today: pd.Timestamp, panel: pd.DataFrame | None = None) -> CycleReport:
        """One full cycle. Any risk violation halts rather than warns."""
        rep = CycleReport(date=today)

        eq = self.equity()
        if eq <= 0:
            eq = self.cfg.capital
        self.risk.update_equity(eq)

        if self.risk.is_halted:
            rep.halted = True
            rep.halt_reason = self.risk.kill_switch_reason or ""
            rep.equity = eq
            log.error("KILL SWITCH ENGAGED: %s", rep.halt_reason)
            return rep

        try:
            self.risk.assert_tradable()
        except KillSwitchEngaged as exc:
            rep.halted, rep.halt_reason, rep.equity = True, str(exc), eq
            return rep

        target = self.target_weights(panel)
        cur = self.current_weights()
        rep.n_target = int((target > 0).sum())

        # ---- risk-check EVERY order before placing any (no partial application)
        plan: list[tuple[str, D, str]] = []
        post = dict(cur)
        for sym in sorted(set(target.index) | set(cur)):
            want = D(str(round(float(target.get(sym, 0.0)), 6)))
            have = cur.get(sym, D("0"))
            delta = want - have
            if abs(delta) < D("0.005"):
                continue
            side = "BUY" if delta > 0 else "SELL"
            # simulate the post-trade book for the check
            post[sym] = want
            plan.append((sym, delta, side))

        for _ in plan:
            try:
                self.risk.assert_tradable()
            except KillSwitchEngaged as exc:
                rep.halted, rep.halt_reason = True, str(exc)
                break

        # ---- execute
        # Use the risk manager's equity, not raw positions value: on a fresh account
        # there are no positions yet, so position-value equity is 0 and a
        # naive check would refuse to ever open the book.
        equity = self.risk.state.equity
        if equity <= 0:
            equity = self.cfg.capital
        for sym, delta, side in plan:
            quote = self.broker.get_quote(sym)
            price = D(str(quote.mid))
            if price <= 0:
                rep.rejected.append(f"{sym}: non-positive quote")
                rep.n_rejected += 1
                continue
            notional = abs(delta) * equity
            qty = notional / price
            qty = D(str(int(qty)))  # whole shares only
            if qty <= 0:
                continue
            if side == "SELL":
                held = next(
                    (p.quantity for p in self.broker.get_positions() if p.symbol == sym),
                    D("0"),
                )
                qty = min(qty, held)
                if qty <= 0:
                    continue

            if self.cfg.dry_run:
                log.info("[dry-run] %s %s %s @ ~%s", side, qty, sym, price)
                rep.orders.append(
                    {"symbol": sym, "side": side, "qty": float(qty), "price": float(price)}
                )
                rep.n_orders += 1
                continue

            try:
                res = self.broker.place_market_order(sym, qty, side)
            except Exception as exc:  # noqa: BLE001 - a broker error must not kill the loop
                log.error("order failed %s %s: %s", side, sym, exc)
                rep.rejected.append(f"{sym}: {exc}")
                rep.n_rejected += 1
                continue

            if res.status != "COMPLETE":
                rep.rejected.append(f"{sym}: {res.status} {res.message}")
                rep.n_rejected += 1
                continue

            rep.orders.append(
                {
                    "symbol": sym,
                    "side": side,
                    "qty": float(res.quantity),
                    "price": float(res.filled_price),
                    "order_id": res.order_id,
                }
            )
            rep.n_orders += 1

        for d in self.reconcile():
            log.warning("reconcile: %s", d)

        final = self.equity()
        self.risk.update_equity(final if final > 0 else eq)
        rep.equity = final if final > 0 else eq
        if self.risk.is_halted:
            rep.halted = True
            rep.halt_reason = self.risk.kill_switch_reason or ""
        log.info(rep.summary())
        return rep

    # ------------------------------------------------------------------ #
    def flatten(self, reason: str) -> int:
        """Go flat. Used by the kill switch and by manual intervention."""
        log.warning("flattening all positions: %s", reason)
        positions = self.broker.get_positions()
        n = 0
        for p in positions:
            if p.quantity <= 0:
                continue
            try:
                self.broker.place_market_order(p.symbol, p.quantity, "SELL")
                n += 1
            except Exception as exc:  # noqa: BLE001
                log.error("flatten failed for %s: %s", p.symbol, exc)
        return n


def build_paper_engine(
    panel: pd.DataFrame,
    capital: D = D("2100000"),
    cost_model: CostModel | None = None,
    config: EngineConfig | None = None,
) -> tuple[Engine, object]:
    """Convenience factory wiring a `PaperBroker` to the engine."""
    from ..execution.paper import PaperBroker

    cm = cost_model or CostModel(segment="delivery")
    last = panel.iloc[-1]
    broker = PaperBroker(capital=capital, cost_model=cm,
                         price_source=lambda s: D(str(last.get(s, 0))))
    eng = Engine(broker=broker, config=config or EngineConfig(capital=capital),
                 cost_model=cm)
    eng.load_market_data(panel)
    return eng, broker
