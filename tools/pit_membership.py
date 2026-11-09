#!/usr/bin/env python3
"""Loader stub for POINT-IN-TIME NIFTY-50 membership.

Why this exists
---------------
Every backtest in this repo runs on `data/nse/*_1d.csv`, which contains exactly
50 symbols: today's NIFTY-50, backfilled to 2008. Names that were removed from
the index, or delisted outright, are simply absent. Measured on 2008-2026 this
flatters an equal-weight construction by **+8.94 pp/yr of CAGR**
(see `reports/DATA_GAP_ASSESSMENT.md`).

This module loads membership as a *function of date* instead of a fixed list.

STATUS: STUB. Wired up and self-checking, but NOT yet imported by
`src/nsealgo/`. It is deliberately outside `src/` so it cannot silently change a
stored backtest result — merging it into the engine is a separate, gated step.

Data
----
`data/nse_membership/nifty50_monthly_membership.csv` (long format:
date, symbol, source). Built by `tools/build_pit_membership.py`.

Known gaps — read before trusting:
  * reconstructed months 2008-01 .. 2025-08 are only VERIFIED against
    independent ground truth from 2017-10 onward (6/7 archive.org snapshots
    matched exactly; one had a single-symbol one-month timing offset).
  * 2025-09 .. 2026-07 has NO recorded membership and is served by forward-fill
    from 2025-08. Treat that window as INFERRED, not known.
  * a handful of month-ends are absent from the source, including several
    rebalance months; forward-fill silently spans them.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import pandas as pd

DEFAULT_PATH = os.environ.get(
    "NSE_MEMBERSHIP", "data/nse_membership/nifty50_monthly_membership.csv"
)

#: membership rows in this window come from a single unverified reconstruction
#: and are forward-filled. Downstream reports must disclose it.
INFERRED_START = pd.Timestamp("2025-09-01")
INFERRED_END = pd.Timestamp("2026-08-01")

#: known-unobtainable names. These are the collapsed/delisted securities whose
#: absence biases the point-in-time universe *optimistically*. See the report.
UNOBTAINABLE = frozenset({"SATYAMCOMP", "VSNL", "MCDOWELLN", "STER"})


def _norm(symbol: str) -> str:
    return str(symbol).strip().upper().replace("-", "").replace("&", "").replace(" ", "")


@dataclass(frozen=True)
class Membership:
    """Point-in-time NIFTY-50 membership, queryable by date."""

    table: pd.DataFrame  # index = month-end Timestamp, columns = symbol (bool)

    @property
    def symbols(self) -> list[str]:
        return sorted(self.table.columns)

    @property
    def start(self) -> pd.Timestamp:
        return self.table.index.min()

    @property
    def end(self) -> pd.Timestamp:
        return self.table.index.max()

    def members(self, when: pd.Timestamp | str) -> list[str]:
        """Constituents in force at `when` (forward-filled from the last prior month-end)."""
        t = pd.Timestamp(when)
        if t < self.start or t > self.end:
            raise ValueError(
                f"{t.date()} is outside membership coverage "
                f"[{self.start.date()}, {self.end.date()}]"
            )
        prior = self.table.index[self.table.index <= t]
        if len(prior) == 0:
            raise ValueError(f"no membership on or before {t.date()}")
        row = self.table.loc[prior[-1]]
        return sorted(row.index[row.fillna(False).to_numpy(dtype=bool)])

    def is_member(self, symbol: str, when: pd.Timestamp | str) -> bool:
        return _norm(symbol) in self.members(when)

    def is_inferred_window(self, when: pd.Timestamp | str) -> bool:
        return INFERRED_START <= pd.Timestamp(when) <= INFERRED_END

    def rebalance_dates(self) -> list[pd.Timestamp]:
        """Month-ends where membership actually changed.

        NSE rebalances semi-annually, so this should be roughly 2 per year over
        the covered window — anything near one-per-month means the comparison is
        broken, not that the index churns.
        """
        changes = [d for i, d in enumerate(self.table.index) if i and
                   not bool((self.table.iloc[i] == self.table.iloc[i - 1]).all())]
        return changes

    def summary(self) -> dict[str, object]:
        return {
            "months": len(self.table),
            "symbols_ever": len(self.symbols),
            "coverage": f"{self.start.date()} .. {self.end.date()}",
            "changes": len(self.rebalance_dates()),
            "unobtainable": sorted(UNOBTAINABLE),
            "inferred_window": f"{INFERRED_START.date()} .. {INFERRED_END.date()}",
        }


def load_membership(path: str | None = None) -> Membership:
    """Read the long table into a dense month-end x symbol boolean matrix.

    The source is POSITIVE-ONLY: a symbol is listed if and only if it was a
    member that month. So two very different absences have to be told apart:

      * symbol absent from a month that HAS records -> genuinely not a member
      * month entirely absent from the source        -> inherit the prior month

    Collapsing both into a forward-fill (or a fillna-before-ffill) silently
    inflates the index, so the two cases are handled separately below.
    """
    path = path or DEFAULT_PATH
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"{path} not found — build it with `python tools/build_pit_membership.py`"
        )
    long = pd.read_csv(path)
    long["date"] = pd.to_datetime(long["date"])
    long["symbol"] = long["symbol"].map(_norm)

    months = pd.date_range(long.date.min(), long.date.max(), freq="ME")
    symbols = sorted(long.symbol.unique())
    table = pd.DataFrame(False, index=months, columns=symbols, dtype=bool)

    by_date = {d: set(g.symbol) for d, g in long.groupby("date")}

    carried = 0
    previous: set[str] = set()
    for d in months:
        if d in by_date:
            previous = by_date[d]
        else:
            carried += 1          # month missing from source -> inherit
        if previous:
            table.loc[d, sorted(previous)] = True

    table.index.name = "date"
    return Membership(table=table)


if __name__ == "__main__":  # quick manual check
    import json

    mem = load_membership()
    print(json.dumps(mem.summary(), indent=2))
    for d in ("2009-06-30", "2016-06-30", "2020-06-30", "2026-06-30"):
        d = pd.Timestamp(d)
        print(f"\n{d.date()}  n={len(mem.members(d))}  inferred={mem.is_inferred_window(d)}")
        print("  " + ", ".join(mem.members(d)[:12]) + ", ...")
