"""Sweep the full strategy catalog against REAL Binance kline CSVs.

Companion to validate_catalog.py (synthetic) — this one measures honest,
post-audit performance on real data: net return, trade count, fee drag, and
gross PnL per strategy, multiprocess across all cores.

Usage:
    python3 tools/sweep_real.py data/btcusdt_1h.csv [--risk 0.02] [--workers 8]

CSV format: ts,open,high,low,close,vol   (ts = Binance open time in ms)
Download data with tools/pull_binance_history.py or the snippet in COMMANDS.md.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd

logging.disable(logging.CRITICAL)

CATALOG_DIR = Path(__file__).resolve().parent.parent / "src" / "cryptobot" / "strategies" / "catalog"
CATALOG = sorted({p.stem for p in CATALOG_DIR.glob("*.py") if p.stem != "__init__"})


def load_bars(path: str):
    from cryptobot.backtest.runner import OhlcvBar

    df = pd.read_csv(path)
    return [
        OhlcvBar(
            timestamp=datetime.fromtimestamp(int(r.ts) / 1000, tz=UTC),
            open=float(r.open),
            high=float(r.high),
            low=float(r.low),
            close=float(r.close),
            volume=float(r.vol),
        )
        for r in df.itertuples(index=False)
    ]


_BAR_CACHE = None


def init_worker(path: str) -> None:
    global _BAR_CACHE
    _BAR_CACHE = load_bars(path)


def run_one(job):
    name, risk = job
    try:
        from cryptobot.backtest.runner import make_strategy, run_backtest

        strat = make_strategy(name)
        result = asyncio.run(
            run_backtest(
                _BAR_CACHE,
                strategy=strat,
                initial_capital=Decimal("10000"),
                collect_trades=True,
                risk_fraction=risk,
                slippage_bps=3,
                commission_bps=5,
            )
        )
        fees = sum(float(t["fees"]) for t in result.trades)
        gross = sum(float(t["pnl"]) for t in result.trades) + fees
        return {
            "name": name,
            "ret": result.total_return,
            "trades": result.n_trades,
            "fees": fees,
            "gross_pnl": gross,
        }
    except Exception as e:  # noqa: BLE001 - report per-strategy failures inline
        return {"name": name, "err": f"{type(e).__name__}: {e}"[:60]}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("path", help="CSV of Binance klines (ts,open,high,low,close,vol)")
    ap.add_argument("--risk", type=float, default=0.02, help="equity fraction per position")
    ap.add_argument("--workers", type=int, default=0, help="processes (default: all cores)")
    args = ap.parse_args()

    bars = load_bars(args.path)
    bh = bars[-1].close / bars[0].close - 1
    print(
        f"{len(bars)} real bars  {bars[0].timestamp.date()} -> {bars[-1].timestamp.date()}  "
        f"px {bars[0].close:.0f} -> {bars[-1].close:.0f}  (buy&hold {bh * 100:+.1f}%)"
    )
    print(f"risk_fraction={args.risk}  costs=5bps fee + 3bps slip per side\n")

    header = f"{'strategy':<24} {'return':>9} {'trades':>7} {'fees$':>8} {'grossPnL$':>10}"
    print(header)
    print("-" * len(header))

    jobs = [(n, args.risk) for n in CATALOG]
    results = []
    workers = args.workers or os.cpu_count() or 4
    with ProcessPoolExecutor(max_workers=workers, initializer=init_worker, initargs=(args.path,)) as ex:
        for r in ex.map(run_one, jobs, chunksize=1):
            results.append(r)

    ok = sorted((r for r in results if "err" not in r), key=lambda r: r["ret"], reverse=True)
    errs = [r for r in results if "err" in r]
    for r in ok:
        print(
            f"{r['name']:<24} {r['ret'] * 100:+8.2f}% {r['trades']:>7d} "
            f"{r['fees']:>8.0f} {r['gross_pnl']:>10.0f}"
        )
    winners = [r for r in ok if r["ret"] > 0]
    print(f"\nwinners: {len(winners)}/{len(ok)}   errors: {len(errs)}")
    for e in errs[:5]:
        print("ERR", e["name"], e["err"])


if __name__ == "__main__":
    main()
