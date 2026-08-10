"""Real-data funding-carry backtest runner.

Pulls spot (1h) + perp (8h) + funding-history CSVs and drives
``backtest.carry.run_carry`` with the CSV funding provider (no lookahead).

Usage:
    python tools/run_carry_real.py [--json]

Data files by default:
    spot    : /tmp/opencode/spot_BTCUSDT_1h.csv
    perp    : /tmp/opencode/perp_BTCUSDT_8h.csv
    funding : /tmp/opencode/funding_BTCUSDT.csv
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import logging
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from cryptobot.backtest.carry import align_spot_to_perp, run_carry
from cryptobot.backtest.funding import CsvFundingProvider
from cryptobot.backtest.runner import OhlcvBar
from cryptobot.strategies.funding_arb import FundingArbConfig, FundingArbStrategy

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("run_carry_real")

DEFAULTS = {
    "spot": "/tmp/opencode/spot_BTCUSDT_1h.csv",
    "perp": "/tmp/opencode/perp_BTCUSDT_8h.csv",
    "funding": "/tmp/opencode/funding_BTCUSDT.csv",
}


def load_ohlcv(path: str) -> list[OhlcvBar]:
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    bars: list[OhlcvBar] = []
    for row in rows:
        ts_row = row.get("timestamp") or row.get("open_time")
        if not ts_row:
            continue
        try:
            ts_ms = int(ts_row)
            ts = datetime.fromtimestamp(ts_ms / 1000, tz=UTC)
        except ValueError:
            ts = datetime.fromisoformat(ts_row.replace("Z", "+00:00"))
        try:
            bars.append(
                OhlcvBar(
                    timestamp=ts,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row.get("volume") or 0),
                )
            )
        except (KeyError, ValueError) as exc:
            logger.debug("skipping bad row %s: %s", ts_row, exc)
    bars.sort(key=lambda b: b.timestamp)
    return bars


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--spot", default=DEFAULTS["spot"])
    ap.add_argument("--perp", default=DEFAULTS["perp"])
    ap.add_argument("--funding", default=DEFAULTS["funding"])
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--perp-symbol", default="BTCUSDT_PERP")
    ap.add_argument("--capital", type=float, default=10_000)
    ap.add_argument("--entry", type=float, default=0.0001, help="Enter carry when 8h funding rate >= this")
    ap.add_argument(
        "--risk",
        type=float,
        default=0.0,
        help="Equity fraction per pair at entry (0 = fixed qty from --capital)",
    )
    ap.add_argument("--max-notional", type=Decimal, default=Decimal("0"), help="Cap pair notional in USD")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    for p in (args.spot, args.perp, args.funding):
        if not Path(p).exists():
            logger.error("missing data file: %s", p)
            return 2

    spot = load_ohlcv(args.spot)
    perp = load_ohlcv(args.perp)
    logger.info(
        "spot %d bars, perp %d bars, window %s..%s",
        len(spot),
        len(perp),
        perp[0].timestamp.isoformat(),
        perp[-1].timestamp.isoformat(),
    )

    aligned = align_spot_to_perp(spot, perp)
    logger.info("aligned spot->perp: %d bars", len(aligned))
    if not aligned:
        logger.error("no spot bars within perp window")
        return 2
    aligned_ts = {b.timestamp for b in aligned}
    spot = aligned
    perp = [b for b in perp if b.timestamp in aligned_ts]
    logger.info(
        "filtered perp to aligned timestamps: %d bars (drop %d unpaired)",
        len(perp), 0,
    )

    funding = CsvFundingProvider(args.funding)
    qty = (Decimal(str(args.capital)) / Decimal(str(aligned[0].close))).quantize(Decimal("0.000001"))
    strategy = FundingArbStrategy(
        FundingArbConfig(
            symbol=args.symbol,
            perp_symbol=args.perp_symbol,
            min_funding_rate=args.entry,
            max_funding_rate=0.0,
            quantity=qty,
            risk_fraction=Decimal(str(args.risk)),
            max_notional=args.max_notional,
        )
    )
    sizing = "equity-scaled" if args.risk > 0 else "fixed"
    logger.info("sizing: %s (risk=%.4f, max_notional=%s)", sizing, args.risk, args.max_notional)
    bt = asyncio.run(
        run_carry(
            aligned,
            perp,
            strategy,
            funding,
            symbol=args.symbol,
            perp_symbol=args.perp_symbol,
            initial_capital=args.capital,
        )
    )
    state = bt._portfolio.get_state()
    trades = bt.get_trades()
    pnl = state.total_equity - Decimal(str(args.capital))
    per_year: dict[str, float] = {}
    for t in trades:
        per_year[str(t.exit_time.year)] = per_year.get(str(t.exit_time.year), 0.0) + (
            float(t.pnl) if t.pnl else 0.0
        )
    result = {
        "symbol": args.symbol,
        "perp_symbol": args.perp_symbol,
        "window": (perp[0].timestamp.isoformat(), perp[-1].timestamp.isoformat()),
        "bars": len(perp),
        "entry_threshold": args.entry,
        "sizing": sizing,
        "capital": str(args.capital),
        "final_equity": str(state.total_equity),
        "pnl": str(pnl),
        "pnl_pct": float(pnl / Decimal(str(args.capital)) * 100),
        "trades": len(trades),
        "pnl_by_year": per_year,
        "note": "equity-scaled legs at entry" if args.risk > 0 else "fixed qty per leg (not risk-scaled)",
    }
    if args.json:
        json.dump(result, sys.stdout, default=str, indent=2)
    else:
        for k, v in result.items():
            print(f"{k}: {v}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
