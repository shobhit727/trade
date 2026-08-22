"""Walk-forward parameter tuning for the daily dual-MA trend family.

Uses the fixed optimize_strategy (train-scored selection, honest OOS tail):
  - tune fast/slow on the leading ~65% of daily bars per symbol
  - report the winner's Sharpe/return on the untouched final ~35%
  - then run winners full-period and combine BTC+ETH 50/50 (daily rebalance)

Usage: python3 tools/tune_1d.py
Expects data/btcusdt_1d.csv and data/ethusdt_1d.csv.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from decimal import Decimal

import pandas as pd

from cryptobot.backtest.metrics import PerformanceMetrics
from cryptobot.backtest.optimize import ParamSpec, optimize_strategy
from cryptobot.backtest.runner import OhlcvBar, make_strategy, run_backtest

logging.disable(logging.CRITICAL)

ASSETS = {"BTC": "data/btcusdt_1d.csv", "ETH": "data/ethusdt_1d.csv"}
PARAMS = [
    ParamSpec("fast", 0, 0, "categorical", choices=[5, 10, 15, 20, 25]),
    ParamSpec("slow", 0, 0, "categorical", choices=[30, 50, 80, 120, 200]),
]


def load(path: str) -> list[OhlcvBar]:
    df = pd.read_csv(path)
    return [
        OhlcvBar(timestamp=datetime.fromtimestamp(int(r.ts) / 1000, tz=UTC),
                 open=float(r.open), high=float(r.high), low=float(r.low),
                 close=float(r.close), volume=float(r.vol))
        for r in df.itertuples(index=False)
    ]


def metrics_from_curve(curve) -> dict:
    values = [float(v) for _t, v in curve]
    pm = PerformanceMetrics()
    pm.add_value(values[0])
    for v in values[1:]:
        pm.add_value(v)
    rets = [values[i] / values[i - 1] - 1.0 for i in range(1, len(values))]
    return {
        "ret": values[-1] / values[0] - 1.0,
        "sharpe": float(pm.calculate_sharpe_ratio(rets)),
        "mdd": float(pm.calculate_drawdown(pd.Series(values))) / 100.0,  # metric returns %
        "n": len(values),
    }


async def full_run(bars, params, symbol):
    strat = make_strategy("dual_ma", **params)
    res = await run_backtest(bars, strat, symbol=symbol,
                             initial_capital=Decimal("10000"),
                             risk_fraction=1.0, slippage_bps=3, commission_bps=5)
    return res


def main():
    curves = {}
    print(f"{'asset':<5} {'best(fast,slow)':<16} {'trainSharpe':>11} "
          f"{'OOS sharpe':>10} {'OOS ret':>9}   full-period (ret / sharpe / mdd)")
    print("-" * 88)

    for sym, path in ASSETS.items():
        bars = load(path)
        opt = optimize_strategy(
            bars, PARAMS, symbol=f"{sym}USDT", metric="sharpe",
            n_trials=1, oos_fraction=0.35, risk_fraction=1.0,
            strategy_name="dual_ma", slippage_bps=3, commission_bps=5,
        )
        res = asyncio.run(full_run(bars, opt.best_params, f"{sym}USDT"))
        m = metrics_from_curve(res.equity_curve)
        curves[sym] = [float(v) for _t, v in res.equity_curve]
        p = opt.best_params
        print(f"{sym:<5} ({p['fast']:>2},{p['slow']:>3}){'':<8} {opt.best_score:>11.2f} "
              f"{opt.oos_score:>10.2f} {opt.oos_return:>8.1%}   "
              f"{m['ret']:>7.1%} / {m['sharpe']:>5.2f} / {m['mdd']:>5.1%}")

    # --- 50/50 portfolio of the two winner equity curves ---
    n = min(len(curves["BTC"]), len(curves["ETH"]))
    port = [(curves["BTC"][i] + curves["ETH"][i]) / 2.0 for i in range(n)]
    pm = PerformanceMetrics()
    pm.add_value(port[0])
    for v in port[1:]:
        pm.add_value(v)
    rets = [port[i] / port[i - 1] - 1.0 for i in range(1, n)]
    mdd = float(pm.calculate_drawdown(pd.Series(port))) / 100.0  # metric returns %
    print("-" * 88)
    print(f"PORT 50/50 BTC+ETH (daily rebal): ret={port[-1] / port[0] - 1:.1%} "
          f"sharpe={float(pm.calculate_sharpe_ratio(rets)):.2f} mdd={mdd:.1%}")


if __name__ == "__main__":
    main()
