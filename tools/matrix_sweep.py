"""HFT matrix sweep: every algorithm x every timeframe x BTC/ETH.

89 algos x 6 timeframes (1m 5m 15m 1h 4h 1d) x 2 symbols = 1068 backtests,
parallel across cores. Results ranked per (symbol, timeframe) by Sharpe and
written to PROJECT_MEMORY/30_HFT_Matrix_Sweep.md + a raw JSON.

Fees: base taker 5bps + 3bps slippage per side. HFT truth serum.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd

logging.disable(logging.CRITICAL)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cryptobot.backtest.metrics import PerformanceMetrics  # noqa: E402
from cryptobot.backtest.runner import OhlcvBar, make_strategy, run_backtest  # noqa: E402
from cryptobot.strategies.registry import _STRATEGY_REGISTRY_MAP  # noqa: E402

SYMBOLS = ["BTCUSDT", "ETHUSDT"]
TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d"]
OUT_JSON = Path("PROJECT_MEMORY/30_hft_matrix_raw.json")
OUT_MD = Path("PROJECT_MEMORY/30_HFT_Matrix_Sweep.md")

_FILES: dict[str, list] = {}


def load_bars(symbol: str, tf: str) -> list:
    key = f"{symbol}_{tf}"
    if key not in _FILES:
        df = pd.read_csv(f"data/{key.lower()}.csv")
        _FILES[key] = [
            OhlcvBar(timestamp=datetime.fromtimestamp(int(r.ts) / 1000, tz=UTC),
                     open=float(r.open), high=float(r.high), low=float(r.low),
                     close=float(r.close), volume=float(r.vol))
            for r in df.itertuples(index=False)
        ]
    return _FILES[key]


def run_one(job):
    symbol, tf, name = job
    try:
        bars = load_bars(symbol, tf)
        strat = make_strategy(name)
        res = asyncio.run(run_backtest(
            bars, strat, symbol=symbol, initial_capital=Decimal("10000"),
            risk_fraction=1.0, slippage_bps=3, commission_bps=5,
            collect_trades=True))
        curve = [float(v) for _t, v in res.equity_curve]
        if len(curve) < 2:
            return {**job, "ret": 0.0, "sharpe": 0.0, "mdd": 0.0,
                    "trades": 0, "error": None}
        pm = PerformanceMetrics()
        pm.add_value(curve[0])
        for v in curve[1:]:
            pm.add_value(v)
        rets = [curve[i] / curve[i - 1] - 1.0 for i in range(1, len(curve))]
        return {
            **job,
            "ret": curve[-1] / curve[0] - 1.0,
            "sharpe": float(pm.calculate_sharpe_ratio(rets)),
            "mdd": float(pm.calculate_drawdown(pd.Series(curve))) / 100.0,
            "trades": len(res.trades),
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001
        return {**job, "ret": None, "sharpe": None, "mdd": None,
                "trades": None, "error": str(exc)[:100]}


def main():
    names = sorted(n for n in _STRATEGY_REGISTRY_MAP if n != "ml_strategy")
    jobs = [(s, tf, n) for s in SYMBOLS for tf in TIMEFRAMES for n in names]
    print(f"{len(jobs)} backtests on {os.cpu_count()} cores...", flush=True)

    from tqdm import tqdm

    results = []
    with ProcessPoolExecutor(max_workers=min(8, os.cpu_count() or 4)) as ex:
        for r in tqdm(ex.map(run_one, jobs, chunksize=4),
                      total=len(jobs), unit="bt", ncols=80,
                      desc="matrix sweep"):
            results.append(r)

    OUT_JSON.write_text(json.dumps(results, indent=1))

    lines = ["# HFT matrix sweep — 89 algos x 6 timeframes x BTC/ETH",
             "",
             f"Generated {datetime.now(UTC).isoformat(timespec='seconds')} · "
             "base costs 5bps fee + 3bps slip per side · $10k · per-bar MTM",
             ""]
    for sym in SYMBOLS:
        for tf in TIMEFRAMES:
            rows = [r for r in results
                    if r["symbol"] == sym and r["tf"] == tf and not r["error"]]
            rows.sort(key=lambda r: r["sharpe"], reverse=True)
            prof = [r for r in rows if r["ret"] > 0]
            lines.append(f"## {sym} {tf} — profitable {len(prof)}/{len(rows)}")
            lines.append("")
            lines.append("| algo | ret | sharpe | mdd | trades |")
            lines.append("|---|---|---|---|---|")
            for r in rows[:10]:
                lines.append(
                    f"| {r['name']} | {r['ret']:.1%} | {r['sharpe']:.2f} "
                    f"| {r['mdd']:.1%} | {r['trades']} |")
            lines.append("")
    errs = [r for r in results if r["error"]]
    if errs:
        lines.append("## Errors")
        lines.append("")
        seen = set()
        for r in errs:
            key = (r["name"], r["error"][:40])
            if key in seen:
                continue
            seen.add(key)
            lines.append(f"- {r['name']} ({r['tf']}): {r['error']}")
        lines.append("")
    OUT_MD.write_text("\n".join(lines))
    print(f"wrote {OUT_MD} and {OUT_JSON}", flush=True)


if __name__ == "__main__":
    main()
