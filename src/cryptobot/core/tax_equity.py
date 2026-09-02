"""India equity capital-gains engine (post-July-2024 rules).

FIFO lot matching over the basket's trade ledger:
  - STCG: holding period <= 365 days -> 20% tax
  - LTCG: holding period  > 365 days -> 12.5% tax, first Rs 1,25,000 of
    LTCG per financial year exempt
  - STT is already embedded in costs; gains are taxed as above.

The basket is long-only delivery, so every SELL closes lots FIFO.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

STCG_RATE = 0.20
LTCG_RATE = 0.125
LTCG_EXEMPT = 125_000.0


@dataclass
class Lot:
    qty: float
    price: float
    date: datetime


@dataclass
class GainRecord:
    symbol: str
    qty: float
    buy_date: datetime
    sell_date: datetime
    proceeds: float
    cost: float
    gain: float
    kind: str            # "STCG" | "LTCG"
    holding_days: int

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol, "qty": self.qty,
            "buy_date": self.buy_date.date().isoformat(),
            "sell_date": self.sell_date.date().isoformat(),
            "proceeds": round(self.proceeds, 2), "cost": round(self.cost, 2),
            "gain": round(self.gain, 2), "kind": self.kind,
            "holding_days": self.holding_days,
        }


@dataclass
class TaxLedger:
    lots: dict[str, list[Lot]] = field(default_factory=dict)
    records: list[GainRecord] = field(default_factory=list)

    # ------------------------------------------------------------- intake

    def on_buy(self, symbol: str, qty: float, price: float,
               when: datetime) -> None:
        self.lots.setdefault(symbol, []).append(Lot(qty, price, when))

    def on_sell(self, symbol: str, qty: float, price: float,
                when: datetime) -> list[GainRecord]:
        """Close lots FIFO; returns the gain records created."""
        pool = self.lots.get(symbol, [])
        remaining = qty
        out: list[GainRecord] = []
        while remaining > 1e-9 and pool:
            lot = pool[0]
            take = min(lot.qty, remaining)
            holding_days = (when.date() - lot.date.date()).days
            kind = "LTCG" if holding_days > 365 else "STCG"
            out.append(GainRecord(
                symbol=symbol, qty=take,
                buy_date=lot.date, sell_date=when,
                proceeds=take * price, cost=take * lot.price,
                gain=take * (price - lot.price), kind=kind,
                holding_days=holding_days))
            lot.qty -= take
            remaining -= take
            if lot.qty <= 1e-9:
                pool.pop(0)
        if remaining > 1e-9:
            # Try to auto-recover by creating a lot from position if available
            # This handles cases where state was restored without tax lots
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(
                "tax ledger missing lots for %s (remaining=%s); "
                "this may indicate state file corruption or version mismatch",
                symbol, remaining
            )
            raise ValueError(
                f"sell {remaining} {symbol} without open lots — ledger corrupt")
        self.records.extend(out)
        return out

    # ------------------------------------------------------------ summary

    def summary(self, fy_end: date | None = None) -> dict:
        """Aggregate taxes. fy_end: last day of the financial year being
        filed (e.g. 2027-03-31 for FY26); None = all records."""
        recs = self.records
        if fy_end is not None:
            fy_start = date(fy_end.year - 1 if fy_end.month <= 3 else fy_end.year,
                            4, 1)
            recs = [r for r in self.records
                    if fy_start <= r.sell_date.date() <= fy_end]
        stcg = sum(r.gain for r in recs if r.kind == "STCG")
        ltcg_gross = sum(r.gain for r in recs if r.kind == "LTCG")
        ltcg_taxable = max(0.0, ltcg_gross - LTCG_EXEMPT)
        return {
            "trades": len(recs),
            "stcg_gain": round(stcg, 2),
            "stcg_tax": round(max(0.0, stcg) * STCG_RATE, 2),
            "ltcg_gain": round(ltcg_gross, 2),
            "ltcg_exempt_used": round(min(ltcg_gross, LTCG_EXEMPT), 2),
            "ltcg_taxable": round(ltcg_taxable, 2),
            "ltcg_tax": round(ltcg_taxable * LTCG_RATE, 2),
            "total_tax": round(max(0.0, stcg) * STCG_RATE
                               + ltcg_taxable * LTCG_RATE, 2),
        }

    def to_dicts(self) -> list[dict]:
        return [r.to_dict() for r in self.records]
