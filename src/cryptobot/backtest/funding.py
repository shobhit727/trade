"""Funding rate plumbing for backtests.

Real perpetual funding settles every 8h (00/08/16 UTC). A provider returns
the settled rate for ``(symbol, timestamp)``; the CSV provider replays
Binance funding history so carry is priced honestly, with zero lookahead
(the rate at or before a bar's timestamp is used).
"""

from __future__ import annotations

import bisect
import csv
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from decimal import Decimal

# Funding settles at the top of every 8h block (UTC).
SETTLEMENT_HOURS = (0, 8, 16)
_MS = 1000


class FundingProvider(ABC):
    @abstractmethod
    def rate(self, symbol: str, timestamp: datetime) -> Decimal:
        """Settled funding rate for ``symbol`` at ``timestamp`` (no lookahead)."""

    @staticmethod
    def is_settlement(timestamp: datetime) -> bool:
        return timestamp.astimezone(UTC).hour in SETTLEMENT_HOURS


class FixedFundingProvider(FundingProvider):
    """Constant rate for every interval — the pre-plumbing default."""

    def __init__(self, rate: Decimal = Decimal("0.0001")):
        self._rate = rate

    def rate(self, symbol: str, timestamp: datetime) -> Decimal:
        return self._rate


class CsvFundingProvider(FundingProvider):
    """Replay Binance fundingRate-history CSV (funding_time, funding_rate).

    ``funding_time`` is in milliseconds; the lookup is the last row at or
    before ``timestamp``, so events never see future rates.
    """

    def __init__(self, path: str):
        times: list[int] = []
        rates: list[Decimal] = []
        with open(path, newline="") as f:
            for row in csv.DictReader(f):
                if "funding_time" not in row or "funding_rate" not in row:
                    continue
                times.append(int(row["funding_time"]))
                rates.append(Decimal(row["funding_rate"]))
        self._times = times
        self._rates = rates

    def rate(self, symbol: str, timestamp: datetime) -> Decimal:
        if not self._times:
            return Decimal("0")
        t_ms = int(timestamp.timestamp() * _MS)
        i = bisect.bisect_right(self._times, t_ms) - 1
        return self._rates[i] if i >= 0 else Decimal("0")


def funding_cashflow(
    side: str,
    quantity: Decimal,
    mark_price: Decimal,
    rate: Decimal,
) -> Decimal:
    """Net cash to ``cash`` for one position at one settlement.

    Longs pay when rate > 0 (cash decreases), shorts receive (cash
    increases); symmetric for negative rates.
    """
    if quantity <= 0 or rate == 0 or mark_price <= 0:
        return Decimal("0")
    notional = quantity * mark_price
    return -notional * rate if side == "LONG" else notional * rate
