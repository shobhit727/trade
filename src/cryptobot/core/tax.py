"""India VDA tax engine (Seed Phase step 4).

Implements the strict-compliance reading of Section 115BBH / Schedule VDA:

- FIFO cost basis per asset; every disposal realizes gain/loss
  (crypto→crypto swaps are two events: a disposal + an acquisition)
- taxable income aggregates ONLY positive per-disposal gains — losses give
  no relief against other VDA gains, other income, and never carry forward
- tax estimate = flat 30% + 4% health & education cess on taxable income
- 1% TDS (§194S) tracked as creditable amounts on sale consideration
- exports a Schedule-VDA-shaped CSV for the CA to verify and file

All money math is Decimal. Timestamps are supplied by the caller so the
engine is deterministic and trivially testable.
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path

logger = logging.getLogger(__name__)

_QUANT8 = Decimal("0.00000001")
_QUANT2 = Decimal("0.01")


@dataclass
class Lot:
    """One acquisition batch of an asset."""

    quantity: Decimal
    cost_per_unit: Decimal
    acquired_at: datetime


@dataclass
class Disposal:
    """One realized disposal event."""

    asset: str
    disposed_at: datetime
    quantity: Decimal
    proceeds: Decimal          # total sale consideration
    cost_basis: Decimal        # FIFO cost of the disposed quantity
    tds_credit: Decimal        # 1% of proceeds (creditable, not final tax)

    @property
    def gain(self) -> Decimal:
        return self.proceeds - self.cost_basis

    @property
    def taxable_gain(self) -> Decimal:
        # §115BBH(2): losses are never set off — aggregate positives only.
        return max(self.gain, Decimal("0"))


@dataclass
class TaxEngine:
    """FIFO ledger + liability estimator for one financial year."""

    tax_rate: Decimal = Decimal("0.30")
    cess_rate: Decimal = Decimal("0.04")
    tds_rate: Decimal = Decimal("0.01")

    _lots: dict[str, list[Lot]] = field(default_factory=dict)
    disposals: list[Disposal] = field(default_factory=list)

    # ---------------------------------------------------------------- trades

    def buy(self, asset: str, quantity: Decimal, cost_per_unit: Decimal,
            acquired_at: datetime) -> None:
        quantity = Decimal(quantity)
        if quantity <= 0 or Decimal(cost_per_unit) < 0:
            raise ValueError("buy requires positive quantity and non-negative price")
        self._lots.setdefault(asset, []).append(
            Lot(quantity=quantity.quantize(_QUANT8),
                cost_per_unit=Decimal(cost_per_unit).quantize(_QUANT8),
                acquired_at=acquired_at)
        )

    def sell(self, asset: str, quantity: Decimal, proceeds_total: Decimal,
             disposed_at: datetime) -> Disposal:
        """Dispose via FIFO; returns the realized record."""
        quantity = Decimal(quantity).quantize(_QUANT8)
        proceeds_total = Decimal(proceeds_total).quantize(_QUANT2)
        if quantity <= 0:
            raise ValueError("sell requires positive quantity")
        held = self.holding(asset)
        if quantity > held:
            raise ValueError(
                f"cannot dispose {quantity} {asset}; holding is {held}"
            )

        remaining = quantity
        cost_basis = Decimal("0")
        lots = self._lots.setdefault(asset, [])
        while remaining > 0:
            lot = lots[0]
            take = min(lot.quantity, remaining)
            cost_basis += take * lot.cost_per_unit
            lot.quantity -= take
            remaining -= take
            if lot.quantity == 0:
                lots.pop(0)

        disposal = Disposal(
            asset=asset,
            disposed_at=disposed_at,
            quantity=quantity,
            proceeds=proceeds_total,
            cost_basis=cost_basis.quantize(_QUANT8),
            tds_credit=(proceeds_total * self.tds_rate).quantize(_QUANT2),
        )
        self.disposals.append(disposal)
        return disposal

    def swap(self, from_asset: str, quantity: Decimal, value_in_quote: Decimal,
             to_asset: str, acquired_quantity: Decimal, at: datetime) -> Disposal:
        """Crypto→crypto trade = disposal of ``from_asset`` + acquisition of ``to_asset``."""
        disposal = self.sell(from_asset, quantity, value_in_quote, at)
        self.buy(to_asset, acquired_quantity,
                 cost_per_unit=value_in_quote / Decimal(acquired_quantity),
                 acquired_at=at)
        return disposal

    # --------------------------------------------------------------- queries

    def holding(self, asset: str) -> Decimal:
        return sum((lot.quantity for lot in self._lots.get(asset, [])),
                   Decimal("0")).quantize(_QUANT8)

    def summary(self) -> dict[str, str]:
        gross_gain = sum((d.gain for d in self.disposals), Decimal("0"))
        taxable = sum((d.taxable_gain for d in self.disposals), Decimal("0"))
        losses_disallowed = sum((-d.gain for d in self.disposals if d.gain < 0), Decimal("0"))
        proceeds = sum((d.proceeds for d in self.disposals), Decimal("0"))
        tds = sum((d.tds_credit for d in self.disposals), Decimal("0"))
        est_tax = (taxable * self.tax_rate * (Decimal("1") + self.cess_rate)).quantize(_QUANT2)
        return {
            "total_proceeds": str(proceeds),
            "gross_gain": str(gross_gain),
            "losses_disallowed": str(losses_disallowed),
            "taxable_income": str(taxable),
            "estimated_tax": str(est_tax),
            "tds_credits": str(tds),
            "net_tax_payable": str(max(est_tax - tds, Decimal("0"))),
        }

    # ---------------------------------------------------------------- export

    def to_dict(self) -> dict:
        return {
            "lots": {
                asset: [
                    {"quantity": str(l.quantity), "cost_per_unit": str(l.cost_per_unit),
                     "acquired_at": l.acquired_at.isoformat()}
                    for l in lots
                ]
                for asset, lots in self._lots.items()
            },
            "disposals": [
                {"asset": d.asset, "disposed_at": d.disposed_at.isoformat(),
                 "quantity": str(d.quantity), "proceeds": str(d.proceeds),
                 "cost_basis": str(d.cost_basis), "tds_credit": str(d.tds_credit)}
                for d in self.disposals
            ],
        }

    def restore(self, data: dict) -> None:
        """Replace state from :meth:`to_dict` output (restart recovery)."""
        self._lots = {
            asset: [
                Lot(quantity=Decimal(l["quantity"]),
                    cost_per_unit=Decimal(l["cost_per_unit"]),
                    acquired_at=datetime.fromisoformat(l["acquired_at"]))
                for l in lots
            ]
            for asset, lots in data.get("lots", {}).items()
        }
        self.disposals = [
            Disposal(asset=d["asset"],
                     disposed_at=datetime.fromisoformat(d["disposed_at"]),
                     quantity=Decimal(d["quantity"]),
                     proceeds=Decimal(d["proceeds"]),
                     cost_basis=Decimal(d["cost_basis"]),
                     tds_credit=Decimal(d["tds_credit"]))
            for d in data.get("disposals", [])
        ]

    def export_schedule_vda(self, path: str | Path) -> Path:
        """Transaction-wise CSV mirroring Schedule VDA columns."""
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow([
                "asset", "date_of_acquisition", "date_of_transfer",
                "quantity", "cost_of_acquisition", "sale_consideration",
                "income_chargeable_under_115BBH", "loss_not_allowed",
                "tds_credit_u/s_194S",
            ])
            for d in self.disposals:
                writer.writerow([
                    d.asset,
                    "",  # FIFO spans multiple lots; CA reconciles from trade log
                    d.disposed_at.date().isoformat(),
                    str(d.quantity),
                    str(d.cost_basis),
                    str(d.proceeds),
                    str(d.taxable_gain),
                    str(-d.gain) if d.gain < 0 else "0",
                    str(d.tds_credit),
                ])
        logger.info("Schedule VDA export written: %s (%d disposals)", out, len(self.disposals))
        return out


__all__ = ["Disposal", "Lot", "TaxEngine"]
