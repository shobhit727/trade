"""Long-only multi-asset portfolio simulation using delayed open execution.

This engine is for historical research and paper simulation. It does not connect to a
broker or venue. It uses the market-scoped cash ledger and rejects cross-market fills.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Mapping

import numpy as np
import pandas as pd

from .domain import MARKET_SPECS, Market
from .market import Fill, MarketLedger, Side


D = Decimal


@dataclass(frozen=True, slots=True)
class PortfolioConfig:
    """Declared execution and portfolio assumptions for one market."""

    market: Market
    fee_bps: Decimal
    slippage_bps: Decimal = D("5")
    impact_coefficient_bps: Decimal = D("10")
    max_participation: Decimal = D("0.05")
    max_gross_exposure: Decimal = D("1.0")
    assumed_timezone: str = "UTC"
    cost_model_id: str = "research-cost-v1"

    def __post_init__(self) -> None:
        # Enforce long-only exposure and bounded participation for the cash simulator.
        if self.fee_bps < 0 or self.slippage_bps < 0 or self.impact_coefficient_bps < 0:
            raise ValueError("cost assumptions cannot be negative")
        if self.fee_bps + self.slippage_bps + self.impact_coefficient_bps >= D("10000"):
            raise ValueError("maximum fee, slippage and impact assumptions must stay below 10000 bps")
        if not D("0") < self.max_participation <= D("1"):
            raise ValueError("max_participation must be in (0, 1]")
        if not D("0") < self.max_gross_exposure <= D("1"):
            raise ValueError("cash simulator exposure must be in (0, 1]")
        if not self.assumed_timezone.strip() or not self.cost_model_id.strip():
            raise ValueError("timezone and cost_model_id are required")


@dataclass(frozen=True, slots=True)
class SimulatedFill:
    """Execution record including reference price, realised price and cost breakdown."""

    fill: Fill
    reference_price: Decimal
    participation: Decimal
    slippage_bps: Decimal
    impact_bps: Decimal

    def to_dict(self) -> dict[str, str]:
        # Serialize all financial quantities as decimal strings.
        return {
            "fill_id": self.fill.fill_id,
            "market": self.fill.market.value,
            "instrument": self.fill.instrument,
            "side": self.fill.side.value,
            "quantity": str(self.fill.quantity),
            "reference_price": str(self.reference_price),
            "price_inr": str(self.fill.price_inr),
            "fee_inr": str(self.fill.fee_inr),
            "participation": str(self.participation),
            "slippage_bps": str(self.slippage_bps),
            "impact_bps": str(self.impact_bps),
            "timestamp": self.fill.timestamp.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class PortfolioResult:
    """Market-scoped equity curve, simulated fills and summary metadata."""

    market: Market
    initial_capital_inr: Decimal
    equity_curve: pd.Series
    cash_curve: pd.Series
    fills: tuple[SimulatedFill, ...]
    turnover: Decimal
    fees_paid_inr: Decimal
    final_positions: Mapping[str, Decimal]
    cost_model_id: str

    @property
    def total_return(self) -> Decimal:
        # Calculate simple return without combining other market environments.
        return self.equity_curve.iloc[-1] / self.initial_capital_inr - D("1")

    def to_dict(self) -> dict[str, object]:
        # Results expose this market only; no cross-market aggregator is provided.
        return {
            "market": self.market.value,
            "initial_capital_inr": str(self.initial_capital_inr),
            "final_equity_inr": str(self.equity_curve.iloc[-1]),
            "total_return": str(self.total_return),
            "cash_inr": str(self.cash_curve.iloc[-1]),
            "fills": len(self.fills),
            "turnover": str(self.turnover),
            "fees_paid_inr": str(self.fees_paid_inr),
            "final_positions": {key: str(value) for key, value in self.final_positions.items()},
            "cost_model_id": self.cost_model_id,
        }


class PortfolioSimulator:
    """Simulate close-derived target weights executed at the next period's open."""

    REQUIRED_COLUMNS = frozenset({"open", "close", "volume"})

    def __init__(self, config: PortfolioConfig) -> None:
        # Bind the simulator to one market and its isolated seed allocation.
        self.config = config
        self.initial_capital = MARKET_SPECS[config.market].initial_simulated_capital
        self.ledger = MarketLedger(config.market, self.initial_capital)

    def _normalise_index(self, index: pd.Index) -> pd.DatetimeIndex:
        # Convert timestamps into one explicit timezone without guessing from values.
        parsed = pd.DatetimeIndex(pd.to_datetime(index, errors="raise"))
        if parsed.tz is None:
            parsed = parsed.tz_localize(self.config.assumed_timezone, ambiguous="raise", nonexistent="raise")
        return parsed

    def _validate_data(self, bars: Mapping[str, pd.DataFrame], targets: pd.DataFrame) -> tuple[list[str], pd.DatetimeIndex]:
        # Ensure each asset has a clean price/volume panel on the exact target calendar.
        if not bars or targets.empty:
            raise ValueError("bars and target weights must be non-empty")
        symbols = sorted(bars)
        first_index = self._normalise_index(bars[symbols[0]].index)
        if len(first_index) < 2 or not first_index.is_monotonic_increasing or first_index.has_duplicates:
            raise ValueError("bar timestamps must be unique, increasing and contain at least two rows")
        for symbol in symbols:
            frame = bars[symbol]
            if not self.REQUIRED_COLUMNS.issubset(frame.columns):
                raise ValueError(f"{symbol}: requires open, close and volume columns")
            index = self._normalise_index(frame.index)
            if not index.equals(first_index):
                raise ValueError(f"{symbol}: bars must align to the common calendar")
            values = frame[["open", "close", "volume"]].to_numpy(dtype=np.float64)
            if not np.isfinite(values).all() or (values[:, :2] <= 0).any() or (values[:, 2] < 0).any():
                raise ValueError(f"{symbol}: prices must be positive and volume non-negative")
        target_index = self._normalise_index(targets.index)
        if not target_index.equals(first_index):
            raise ValueError("target weights must align exactly with the bar calendar")
        if set(targets.columns) != set(symbols):
            raise ValueError("target columns must exactly match the supplied asset universe")
        weight_values = targets[symbols].to_numpy(dtype=np.float64)
        if not np.isfinite(weight_values).all() or (weight_values < 0).any():
            raise ValueError("target weights must be finite and long-only")
        gross = weight_values.sum(axis=1)
        if (gross > float(self.config.max_gross_exposure) + 1e-9).any():
            raise ValueError("target gross exposure exceeds the configured cash-account limit")
        return symbols, first_index

    def run(self, bars: Mapping[str, pd.DataFrame], targets: pd.DataFrame) -> PortfolioResult:
        """Run the portfolio with decisions at close t and fills at open t+1.

        Targets are fractional portfolio weights based only on information available at
        the target row's close. Row t is executed at row t+1 open. The final close has no
        following execution bar and therefore cannot create a fill.
        """
        # Validate the full input panel before creating any simulated transactions.
        symbols, index = self._validate_data(bars, targets)
        ordered_targets = targets[symbols]
        initial_snapshot = self.ledger.snapshot({})
        equity_values = [initial_snapshot.equity_inr]
        cash_values = [initial_snapshot.cash_inr]
        equity_dates = [index[0]]
        fills: list[SimulatedFill] = []
        turnover = D("0")
        participation_cap = self.config.max_participation

        for row in range(1, len(index)):
            # Target quantities use equity and marks known at the prior close.
            prior_marks = {
                symbol: D(str(bars[symbol]["close"].iloc[row - 1]))
                for symbol in symbols
            }
            prior_snapshot = self.ledger.snapshot(prior_marks)
            decision_weights = ordered_targets.iloc[row - 1]
            desired_quantities = {
                symbol: D(str(float(decision_weights[symbol]) * float(prior_snapshot.equity_inr)
                               / float(prior_marks[symbol])))
                for symbol in symbols
            }
            orders: list[tuple[str, Side, Decimal, Decimal, Decimal]] = []

            # Compute orders against the next open; sell orders are processed first.
            for symbol in symbols:
                current_quantity = self.ledger.positions.get(symbol)
                current_quantity = current_quantity.quantity if current_quantity else D("0")
                difference = desired_quantities[symbol] - current_quantity
                if difference == 0:
                    continue
                side = Side.BUY if difference > 0 else Side.SELL
                requested = abs(difference)
                reference = D(str(bars[symbol]["open"].iloc[row]))
                available = D(str(bars[symbol]["volume"].iloc[row]))
                max_quantity = available * participation_cap
                executable = min(requested, max_quantity)
                if executable <= 0:
                    continue
                participation = executable / available if available > 0 else D("0")
                impact = self.config.impact_coefficient_bps * D(str(float(participation) ** 0.5))
                adverse = self.config.slippage_bps + impact
                direction = D("1") if side is Side.BUY else D("-1")
                price = reference * (D("1") + direction * adverse / D("10000"))
                orders.append((symbol, side, executable, reference, price))

            # Unwind existing risk first to make proceeds available for new long positions.
            orders.sort(key=lambda item: (0 if item[1] is Side.SELL else 1, item[0]))
            for symbol, side, quantity, reference, price in orders:
                notional = quantity * price
                fee = notional * self.config.fee_bps / D("10000")
                if side is Side.BUY:
                    # Cap the buy size by available cash including the fee reserve.
                    affordable = self.ledger.cash_inr / (price * (D("1") + self.config.fee_bps / D("10000")))
                    quantity = min(quantity, affordable)
                    if quantity <= 0:
                        continue
                    notional = quantity * price
                    fee = notional * self.config.fee_bps / D("10000")
                timestamp = index[row].to_pydatetime()
                fill = Fill(
                    fill_id=f"{self.config.market.value}-{timestamp.isoformat()}-{symbol}-{side.value}",
                    market=self.config.market,
                    instrument=symbol,
                    side=side,
                    quantity=quantity,
                    price_inr=price,
                    fee_inr=fee,
                    timestamp=timestamp,
                    cost_model_id=self.config.cost_model_id,
                    fx_provenance="input bars are required to be INR-denominated",
                )
                self.ledger.apply_fill(fill)
                participation = quantity / D(str(bars[symbol]["volume"].iloc[row]))
                impact = self.config.impact_coefficient_bps * D(str(float(participation) ** 0.5))
                fills.append(SimulatedFill(fill, reference, participation,
                                           self.config.slippage_bps, impact))
                turnover += notional / self.initial_capital

            # Mark all open positions at this bar's close without forward filling.
            close_marks = {
                symbol: D(str(bars[symbol]["close"].iloc[row]))
                for symbol in symbols
                if symbol in self.ledger.positions
                and self.ledger.positions[symbol].quantity > 0
            }
            snapshot = self.ledger.snapshot(close_marks)
            equity_values.append(snapshot.equity_inr)
            cash_values.append(snapshot.cash_inr)
            equity_dates.append(index[row])

        equity = pd.Series(equity_values, index=pd.DatetimeIndex(equity_dates), name="equity")
        cash = pd.Series(cash_values, index=pd.DatetimeIndex(equity_dates), name="cash")
        final_positions = {
            symbol: position.quantity
            for symbol, position in self.ledger.positions.items()
            if position.quantity > 0
        }
        return PortfolioResult(
            market=self.config.market,
            initial_capital_inr=self.initial_capital,
            equity_curve=equity,
            cash_curve=cash,
            fills=tuple(fills),
            turnover=turnover,
            fees_paid_inr=self.ledger.fees_paid_inr,
            final_positions=final_positions,
            cost_model_id=self.config.cost_model_id,
        )
