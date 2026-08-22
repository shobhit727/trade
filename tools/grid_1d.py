"""Parameter-robustness grid for daily EMA-cross / dual-MA trend candidates.

If edge only exists at one magic parameter pair it's curve-fit; we want a
plateau where most of the neighborhood is positive on BOTH BTC and ETH.
Includes a punitive-cost pass (commission 17bps vs base 5bps) to check the
edge survives realistic taker fees.

Usage:
    python3 tools/grid_1d.py [--workers 8]

Expects data/btcusdt_1d.csv and data/ethusdt_1d.csv (see COMMANDS.md).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime
from decimal import Decimal

import pandas as pd

logging.disable(logging.CRITICAL)

GRID = [
    ("ema_cross", {"fast": f, "slow": s})
    for f in (5, 10, 15, 20)
    for s in (30, 50, 100, 150)
    if f < s
] + [
    ("dual_ma", {"fast": f, "slow": s})
    for f in (10, 20, 30)
    for s in (50, 75, 100)
]

ASSETS = {"BTC": "data/btcusdt_1d.csv", "ETH": "data/ethusdt_1d.csv"}
FEE_PASSES = {"base (5bps)": 5, "punitive (17bps)": 17}

_FILES: dict[str, list] = {}


def load(path: str):
    from cryptobot.backtest.runner import OhlcvBar

    if path not in _FILES:
        df = pd.read_csv(path)
        _FILES[path] = [
            OhlcvBar(timestamp=datetime.fromtimestamp(int(r.ts) / 1000, tz=UTC),
                     open=float(r.open), high=float(r.high), low=float(r.low),
                     close=float(r.close), volume=float(r.vol))
            for r in df.itertuples(index=False)
        ]
    return _FILES[path]


def run_one(job):
    name, params, path, fee_bps = job
    try:
        from cryptobot.backtest.runner import make_strategy, run_backtest

        strat = make_strategy(name, **params)
        res = asyncio.run(run_backtest(load(path), strategy=strat,
                                       initial_capital=Decimal("10000"),
                                       collect_trades=False, risk_fraction=1.0,
                                       slippage_bps=3, commission_bps=fee_bps))
        return {"name": name, "fast": params["fast"], "slow": params["slow"],
                "asset": "BTC" if "btc" in path else "ETH",
                "fee": fee_bps, "ret": res.total_return}
    except Exception as e:  # noqa: BLE001 - report inline
        return {"name": name, "fast": params.get("fast", -1), "slow": params.get("slow", -1),
                "asset": "?", "fee": fee_bps, "ret": None, "err": str(e)[:40]}


def report(results, fee_label: str) -> None:
    print(f"\n=== commission {fee_label} + 3bps slippage per side ===")
    print(f"{'strategy':<10}{'fast':>5}{'slow':>6} | {'BTC':>9} {'ETH':>9}  both+")
    print("-" * 52)
    by_key: dict[tuple, dict] = {}
    for r in results:
        by_key.setdefault((r["name"], r["fast"], r["slow"]), {})[r["asset"]] = r["ret"]
    both_pos = total = 0
    for (name, f, s), d in sorted(by_key.items()):
        b, e = d.get("BTC"), d.get("ETH")
        mark = ""
        if b is not None and e is not None and b > 0 and e > 0:
            mark = " *"
            both_pos += 1
        total += 1
        fb = f"{b * 100:+8.1f}%" if b is not None else "     ERR"
        fe = f"{e * 100:+8.1f}%" if e is not None else "     ERR"
        print(f"{name:<10}{f:>5}{s:>6} | {fb} {fe}{mark}")
    print(f"positive on BOTH assets: {both_pos}/{total}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workers", type=int, default=0, help="processes (default: all cores)")
    args = ap.parse_args()

    jobs = [(name, params, path, fee)
            for fee in FEE_PASSES.values()
            for path in ASSETS.values()
            for name, params in GRID]

    with ProcessPoolExecutor(max_workers=args.workers or os.cpu_count() or 4) as ex:
        out = list(ex.map(run_one, jobs, chunksize=1))

    for fee_label, fee in FEE_PASSES.items():
        report([r for r in out if r["fee"] == fee], fee_label)


if __name__ == "__main__":
    main()
