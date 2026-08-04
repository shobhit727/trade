from __future__ import annotations

import asyncio
import os
from concurrent.futures import ProcessPoolExecutor
from decimal import Decimal
from typing import Any

from cryptobot.backtest.data import load_bars
from cryptobot.backtest.runner import make_strategy, run_backtest

JOB_DEFAULTS: dict[str, Any] = {
    "source": "synthetic",
    "symbol": "BTCUSDT",
    "timeframe": "1h",
    "bars": 200,
    "capital": 10000,
    "seed": 42,
}


def _run_one(job: dict[str, Any]) -> dict[str, Any]:
    """Run a single backtest job in a worker process (must be top-level for pickling)."""
    job = {**JOB_DEFAULTS, **job}
    ds = load_bars(
        source=job["source"],
        path=job.get("path"),
        symbol=job["symbol"],
        timeframe=job["timeframe"],
        n_bars=job.get("bars"),
    )
    if job["source"] == "synthetic":
        ds.bars = ds.bars[: job["bars"]]
    strategy = make_strategy(job["strategy"], **job.get("params", {}))
    result = asyncio.run(
        run_backtest(
            ds.bars,
            strategy=strategy,
            symbol=ds.symbol,
            initial_capital=Decimal(str(job["capital"])),
        )
    )
    return {
        "index": job.get("index"),
        "strategy": job["strategy"],
        "params": job.get("params", {}),
        "bars": len(ds.bars),
        "initial_capital": str(result.initial_capital),
        "final_equity": str(result.final_equity),
        "total_return": result.total_return,
        "n_trades": result.n_trades,
    }


def run_parallel(jobs: list[dict[str, Any]], workers: int | None = None) -> list[dict[str, Any]]:
    """Run backtest jobs across a process pool.

    Each job is a dict: {"strategy": str, "params": {...}, optional overrides}.
    Results are returned in input order. Forks per worker, so each worker
    generates its own copy of the bar data (N workers x bars held in memory).
    """
    if not jobs:
        return []
    n_workers = workers or max(1, min(os.cpu_count() or 1, len(jobs)))
    indexed = [{**job, "index": i} for i, job in enumerate(jobs)]
    with ProcessPoolExecutor(max_workers=n_workers) as pool:
        results = list(pool.map(_run_one, indexed))
    return sorted(results, key=lambda r: r["index"])
