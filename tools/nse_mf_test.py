#!/usr/bin/env python3
"""Mid-frequency NSE test: session-aware algos across the 50 stocks.

Runs nse_orb + vwap_revert on every available 15m file at NSE intraday
costs, using the ts-aware backtest path. Writes a compact markdown table
to PROJECT_MEMORY/38_NSE_MidFreq_Results.md.
"""

from __future__ import annotations

import asyncio
import statistics as st
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd

from cryptobot.backtest.metrics import PerformanceMetrics
from cryptobot.backtest.runner import OhlcvBar, make_strategy, run_backtest

OUT_MD = Path("PROJECT_MEMORY/38_NSE_MidFreq_Results.md")
ALGOS = {"nse_orb": {}, "vwap_revert": {"z_entry": 2.0},
         "vwap_revert_z15": None}  # filled below
FEE_BPS, SLIP_BPS = 2, 1


def load(symbol: str) -> list[OhlcvBar]:
    df = pd.read_csv(f"data/nse/{symbol.lower()}_15m.csv")
    return [
        OhlcvBar(timestamp=datetime.fromtimestamp(int(r.ts) / 1000, tz=UTC),
                 open=float(r.open), high=float(r.high), low=float(r.low),
                 close=float(r.close), volume=float(r.vol))
        for r in df.itertuples(index=False)
    ]


def metrics(curve) -> tuple[float, float, float]:
    v = [float(x) for _t, x in curve]
    if len(v) < 2:
        return 0.0, 0.0, 0.0
    pm = PerformanceMetrics()
    pm.add_value(v[0])
    rets = [v[i] / v[i - 1] - 1.0 for i in range(1, len(v))]
    for r in rets:
        pm.add_value(v[0] * (1 + r))
    sharpe = float(pm.calculate_sharpe_ratio(rets))
    mdd = float(pm.calculate_drawdown(pd.Series(v))) / 100.0
    return v[-1] / v[0] - 1.0, sharpe, mdd


async def run_one(symbol: str, algo: str, params: dict) -> dict:
    bars = load(symbol)
    strat = make_strategy(algo, **params)
    res = await run_backtest(bars, strat, symbol=symbol,
                             initial_capital=Decimal("10000"),
                             risk_fraction=1.0,
                             slippage_bps=SLIP_BPS, commission_bps=FEE_BPS)
    ret, sharpe, mdd = metrics(res.equity_curve)
    return {"symbol": symbol, "algo": algo, "ret": ret, "sharpe": sharpe,
            "mdd": mdd, "trades": res.n_trades}


async def main() -> None:
    algos = [("nse_orb", {}), ("vwap_revert", {"z_entry": 2.0}),
             ("vwap_revert_z15", {"z_entry": 1.5})]
    symbols = sorted(p2.stem.split("_")[0] for p2 in Path("data/nse").glob("*_15m.csv"))
    results = []
    for sym in symbols:
        for algo, params in algos:
            try:
                r = await run_one(sym, algo if algo != "vwap_revert_z15" else "vwap_revert",
                                  params)
                r["algo"] = algo
                results.append(r)
            except Exception as exc:  # noqa: BLE001
                results.append({"symbol": sym, "algo": algo, "error": str(exc)[:80],
                                "ret": 0.0, "sharpe": 0.0})

    OUT_MD.write_text(
        "# NSE mid-frequency test — nse_orb & vwap_revert @15m\n\n"
        f"Generated {datetime.now(UTC).isoformat(timespec='seconds')} · "
        f"{len(symbols)} stocks · intraday costs {FEE_BPS}+{SLIP_BPS}bps/side\n\n"
        "| algo | wins | mean sharpe | median ret | total trades |\n|---|---|---|---|---|\n"
        + "".join(
            f"| {a} | {sum(1 for r in results if r['algo']==a and r.get('ret',0)>0)}"
            f"/{sum(1 for r in results if r['algo']==a)} "
            f"| {sum(r.get('sharpe',0) for r in results if r['algo']==a)/max(1,sum(1 for r in results if r['algo']==a)):.2f} "
            f"| {st.median([r['ret'] for r in results if r['algo']==a]):+.1%} "
            f"| {sum(r.get('trades',0) or 0 for r in results if r['algo']==a)} |\n"
            for a, _p in algos)
        + "\n## per-stock detail\n\n| symbol | algo | ret | sharpe | mdd | trades |\n|---|---|---|---|---|---|\n"
        + "".join(
            f"| {r['symbol']} | {r['algo']} | {r.get('ret',0):+.1%} | {r.get('sharpe',0):.2f} "
            f"| {r.get('mdd',0):.1%} | {r.get('trades',0)} |\n"
            for r in results if "error" not in r)
    )
    print(f"wrote {OUT_MD}")
    for r in results[:6]:
        print(r)


if __name__ == "__main__":
    asyncio.run(main())
