"""Funding-arbitrage backtest runner.

Simulates a delta-neutral carry trade over real funding timestamps:
  - short perpetual leg + long spot leg, 1:1 notional
  - collects or pays the *recorded* 8h funding rate while the position is open
  - charges maker/taker fees on each leg per the configured commission fields

Dedicated runner: the generic BacktestEngine cannot model a two-leg perp+spot
position with real data-driven funding payments.
"""

from __future__ import annotations

import bisect
import json
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from cryptobot.strategies.funding_arb import FundingArbStrategy


@dataclass
class FundingSimResult:
    """Result of a funding-arb backtest window."""

    start: datetime | None = None
    end: datetime | None = None
    total_return_bps: float = 0.0
    carry_bps: float = 0.0
    basis_bps: float = 0.0
    fees_bps: float = 0.0
    n_roundtrips: int = 0
    intervals_held: int = 0
    frac_time_in_market: float = 0.0
    equity_curve: list[tuple[datetime, Decimal]] = field(default_factory=list)
    years: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "start": self.start.isoformat() if self.start else None,
            "end": self.end.isoformat() if self.end else None,
            "total_return_bps": round(self.total_return_bps, 2),
            "total_return_pct": round(self.total_return_bps / 100.0, 2),
            "annualized_pct": round(self.total_return_bps / 100.0 / max(self.years, 1e-9), 2),
            "carry_bps": round(self.carry_bps, 2),
            "basis_bps": round(self.basis_bps, 2),
            "fees_bps": round(self.fees_bps, 2),
            "n_roundtrips": self.n_roundtrips,
            "intervals_held": self.intervals_held,
            "frac_time_in_market": round(self.frac_time_in_market, 4),
            "years": round(self.years, 2),
        }


def _price_at(sorted_ts: list[datetime], sorted_close: list[float], ts: datetime) -> float | None:
    idx = bisect.bisect_right(sorted_ts, ts) - 1
    if idx < 0:
        return None
    return sorted_close[idx]


def run_funding_backtest(
    funding_ts: list[datetime],
    funding_rates: list[float],
    spot_ts: list[datetime],
    spot_close: list[float],
    perp_ts: list[datetime],
    perp_close: list[float],
    strategy: FundingArbStrategy | None = None,
    spot_maker_bps: float = 7.5,
    spot_taker_bps: float = 7.5,
    perp_maker_bps: float = 1.8,
    perp_taker_bps: float = 4.5,
    initial_capital: Decimal = Decimal("10000"),
) -> FundingSimResult:
    """Run the funding-arb strategy over the merged funding/price timeline.

    Decision points are the 8h funding timestamps (the strategy evaluates
    basis + funding there and opens/closes). While a position is open, the
    recorded funding rate of each interval is credited (short perp when
    rate > 0) or debited (rate < 0) on the notional.

    Fees: 4 fills per round trip (open/close each leg); each leg is charged
    at its maker rate if the strategy enters at the passive side is unknown,
    so we model spot as taker and perp as maker by default (conservative,
    spot limit fills are unreliable for immediacy).
    """
    n = len(funding_ts)
    if n == 0:
        raise ValueError("no funding events")

    cfg = strategy.config if strategy else None
    min_funding = float(cfg.min_funding_rate) if cfg else 0.0001
    max_funding = float(cfg.max_funding_rate) if cfg else 0.005
    basis_entry = float(cfg.basis_entry_bps) if cfg else 5.0
    basis_exit = float(cfg.basis_exit_bps) if cfg else 1.5

    # sort spot/perp by ts once
    order_s = sorted(zip(spot_ts, spot_close, strict=False))
    s_ts = [t for t, _ in order_s]
    s_cl = [c for _, c in order_s]
    order_p = sorted(zip(perp_ts, perp_close, strict=False))
    p_ts = [t for t, _ in order_p]
    p_cl = [c for _, c in order_p]

    res = FundingSimResult(start=funding_ts[0], end=funding_ts[-1])
    res.years = (funding_ts[-1] - funding_ts[0]).total_seconds() / 31557600.0

    carry = 0.0
    basis_gain = 0.0
    fees = 0.0
    n_rips = 0
    held = 0
    in_pos = False
    entry_basis = 0.0
    curve: list[tuple[datetime, Decimal]] = []

    for ts, rate in zip(funding_ts, funding_rates, strict=True):
        spot_p = _price_at(s_ts, s_cl, ts)
        perp_p = _price_at(p_ts, p_cl, ts)
        if spot_p is None or perp_p is None or spot_p <= 0:
            continue
        basis = (perp_p / spot_p - 1.0) * 10000.0

        if in_pos:
            held += 1
            carry += rate * 10000.0
            if basis <= basis_exit:
                basis_gain += entry_basis - basis
                fees += 2 * (spot_taker_bps + perp_maker_bps)
                n_rips += 1
                in_pos = False
        else:
            if min_funding <= rate <= max_funding and basis >= basis_entry:
                in_pos = True
                entry_basis = basis
                fees += 2 * (spot_taker_bps + perp_maker_bps)
        curve.append((ts, Decimal(str(round(carry + basis_gain - fees, 4)))))

    res.carry_bps = carry
    res.basis_bps = basis_gain
    res.fees_bps = fees
    res.n_roundtrips = n_rips
    res.intervals_held = held
    res.total_return_bps = carry + basis_gain - fees
    res.frac_time_in_market = held / max(n, 1)
    res.equity_curve = curve
    return res


def _load_csv_ts_closes(path: Path):
    import csv

    ts: list[datetime] = []
    closes: list[float] = []
    with path.open() as f:
        for row in csv.DictReader(f):
            ts.append(datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00")))
            closes.append(float(row["close"]))
    return ts, closes


def run_funding_backtest_from_files(
    sym: str,
    funding_file: str | Path,
    spot_file: str | Path,
    perp_file: str | Path,
    strategy: FundingArbStrategy | None = None,
    spot_maker_bps: float = 7.5,
    spot_taker_bps: float = 7.5,
    perp_maker_bps: float = 1.8,
    perp_taker_bps: float = 4.5,
    initial_capital: Decimal = Decimal("10000"),
) -> FundingSimResult:
    """Run a funding-arb backtest from the researcher's cache files.

    Funding file: JSON array of {"fundingTime", "fundingRate"}.
    Spot/perp files: JSON arrays of Binance klines [open_ms, open, high, low, close, vol, ...].
    """
    funding = json.loads(Path(funding_file).read_text())
    f_ts = [datetime.fromtimestamp(int(e["fundingTime"]) / 1000.0) for e in funding]
    f_rates = [float(e["fundingRate"]) for e in funding]
    spot_ts, spot_cl = _klines_to_series(Path(spot_file))
    perp_ts, perp_cl = _klines_to_series(Path(perp_file))
    return run_funding_backtest(
        f_ts, f_rates, spot_ts, spot_cl, perp_ts, perp_cl,
        strategy=strategy, spot_maker_bps=spot_maker_bps, spot_taker_bps=spot_taker_bps,
        perp_maker_bps=perp_maker_bps, perp_taker_bps=perp_taker_bps,
        initial_capital=initial_capital,
    )


def _klines_to_series(path: Path) -> tuple[list[datetime], list[float]]:
    klines = json.loads(path.read_text())
    ts = [datetime.fromtimestamp(int(k[0]) / 1000.0) for k in klines]
    closes = [float(k[4]) for k in klines]
    return ts, closes


__all__ = [
    "FundingSimResult",
    "run_funding_backtest",
    "run_funding_backtest_from_files",
]
