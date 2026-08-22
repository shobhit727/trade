"""Frequency experiment: does a lower bar frequency rescue trend strategies?

Runs a curated strategy set over 1h / 4h / 1d real kline CSVs and reports net
return, trade count and max drawdown per (strategy x timeframe), plus buy&hold
benchmarks. Motivated by the 2026-08 sweep finding that 1h catalog strategies
carry ~zero gross edge while fee drag (~16bps round trip) sinks everything.

Usage:
    python3 tools/sweep_freq.py [--risk 0.05] [--workers 8]

Expects data/btcusdt_{1h,4h,1d}.csv next to the repo root.
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

STRATS: list[tuple[str, dict]] = [
    ("trend_following", {"fast": 12, "slow": 26}),
    ("trend_following", {"fast": 20, "slow": 50}),
    ("trend_following", {"fast": 50, "slow": 200}),
    ("ema_cross", {}),
    ("donchian", {}),
    ("roc", {}),
    ("macd", {}),
    ("keltner", {}),
    ("supertrend", {}),
    ("atr_trailing", {}),
    ("dual_ma", {}),
    ("zscore", {}),
]

DATASETS = {
    "1h": "data/btcusdt_1h.csv",
    "4h": "data/btcusdt_4h.csv",
    "1d": "data/btcusdt_1d.csv",
}

_CACHE: dict[str, list] = {}


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


def run_one(job):
    name, params, path, risk = job
    label = f"{name}{'/' + str(params['fast']) + '-' + str(params['slow']) if params else ''}"
    try:
        from cryptobot.backtest.runner import make_strategy, run_backtest

        if path not in _CACHE:
            _CACHE[path] = load_bars(path)
        strat = make_strategy(name, **params)
        res = asyncio.run(
            run_backtest(
                _CACHE[path],
                strategy=strat,
                initial_capital=Decimal("10000"),
                collect_trades=True,
                risk_fraction=risk,
                slippage_bps=3,
                commission_bps=5,
            )
        )
        peak, mdd = 0.0, 0.0
        for _, eq in res.equity_curve:
            v = float(eq)
            peak = max(peak, v)
            if peak > 0:
                mdd = max(mdd, (peak - v) / peak)
        return {
            "label": label,
            "ret": res.total_return,
            "trades": res.n_trades,
            "mdd": mdd,
        }
    except Exception as e:  # noqa: BLE001 - report per-strategy failures inline
        return {"label": label, "err": f"{type(e).__name__}: {e}"[:50]}


def bh_stats(path: str) -> tuple[float, float]:
    df = pd.read_csv(path)
    closes = df["close"].astype(float).values
    peak, mdd = closes[0], 0.0
    for c in closes[1:]:
        peak = max(peak, c)
        mdd = max(mdd, (peak - c) / peak)
    return closes[-1] / closes[0] - 1, mdd


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--risk", type=float, default=0.05, help="equity fraction per position")
    ap.add_argument("--workers", type=int, default=0, help="processes (default: all cores)")
    args = ap.parse_args()

    jobs = [(name, params, path, args.risk) for path in DATASETS.values() for name, params in STRATS]
    results: dict[str, list] = {tf: [] for tf in DATASETS}
    workers = args.workers or os.cpu_count() or 4
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for (_name, _params, path, _risk), r in zip(jobs, ex.map(run_one, jobs, chunksize=1), strict=True):
            tf = Path(path).stem.split("_")[-1]
            results[tf].append(r)

    print(f"risk_fraction={args.risk}  costs 5bps fee + 3bps slip per side  (BTCUSDT 2y)\n")
    hdr = f"{'strategy':<22}" + "".join(f"{tf + ' net':>10}{tf + ' trd':>7}{tf + ' MDD':>8}" for tf in DATASETS)
    print(hdr)
    print("-" * len(hdr))

    by_label: dict[str, dict] = {}
    for tf in DATASETS:
        for r in results[tf]:
            by_label.setdefault(r["label"], {})[tf] = r
    for label, row in sorted(by_label.items()):
        cells = ""
        for tf in DATASETS:
            r = row.get(tf)
            if r is None or "err" in r:
                cells += f"{'ERR':>10}{'':>7}{'':>8}"
            else:
                cells += f"{r['ret'] * 100:+9.1f}%{r['trades']:>7d}{r['mdd'] * 100:>7.1f}%"
        print(f"{label:<22}{cells}")
    print()
    for tf, path in DATASETS.items():
        ret, mdd = bh_stats(path)
        print(f"buy&hold {tf:>3}: {ret * 100:+.1f}%  MDD {mdd * 100:.1f}%")


if __name__ == "__main__":
    main()
