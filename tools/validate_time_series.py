"""Walk-forward validation for time_series momentum (Seed Phase candidate).

Same protocol as the dual_ma validation:
  - tune period/threshold on the leading 65% of daily bars
  - report the winner's Sharpe/return on the untouched final 35%
  - neighborhood plateau check around the winner
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from decimal import Decimal

import pandas as pd

logging.disable(logging.CRITICAL)

from cryptobot.backtest.metrics import PerformanceMetrics
from cryptobot.backtest.optimize import ParamSpec, optimize_strategy
from cryptobot.backtest.runner import OhlcvBar, make_strategy, run_backtest

ASSETS = {"BTC": "data/btcusdt_1d.csv", "ETH": "data/ethusdt_1d.csv"}
PARAMS = [
    ParamSpec("period", 0, 0, "categorical",
              choices=[10, 15, 20, 25, 30, 40, 50, 60, 80, 100]),
    ParamSpec("threshold", 0, 0, "categorical",
              choices=[-0.02, 0.0, 0.02, 0.05]),
]


def load(path: str) -> list[OhlcvBar]:
    df = pd.read_csv(path)
    return [
        OhlcvBar(timestamp=datetime.fromtimestamp(int(r.ts) / 1000, tz=UTC),
                 open=float(r.open), high=float(r.high), low=float(r.low),
                 close=float(r.close), volume=float(r.vol))
        for r in df.itertuples(index=False)
    ]


def metrics(curve) -> tuple[float, float, float]:
    values = [float(v) for _t, v in curve]
    pm = PerformanceMetrics()
    pm.add_value(values[0])
    for v in values[1:]:
        pm.add_value(v)
    rets = [values[i] / values[i - 1] - 1.0 for i in range(1, len(values))]
    return (values[-1] / values[0] - 1.0,
            float(pm.calculate_sharpe_ratio(rets)),
            float(pm.calculate_drawdown(pd.Series(values))) / 100.0)


def plateau(bars, symbol, base: dict) -> list[tuple]:
    """Sharpe of neighbors around the winning params (plateau == robust)."""
    out = []
    p0, t0 = base["period"], base["threshold"]
    for p in sorted({max(5, int(p0 * f)) for f in (0.5, 0.75, 1.0, 1.33, 2.0)}):
        for th in (-0.02, 0.0, 0.02):
            strat = make_strategy("time_series", period=p, threshold=th)
            res = asyncio.run(run_backtest(bars, strat, symbol=symbol,
                                           initial_capital=Decimal("10000"),
                                           risk_fraction=1.0,
                                           slippage_bps=3, commission_bps=5))
            ret, sharpe, mdd = metrics(res.equity_curve)
            out.append((p, th, ret, sharpe, mdd))
    return out


def main():
    print(f"{'asset':<5} {'best(period,thr)':<18} {'trainShp':>8} "
          f"{'OOS shp':>8} {'OOS ret':>8}   full-period ret/shp/mdd")
    print("-" * 84)

    winners = {}
    for sym, path in ASSETS.items():
        bars = load(path)
        opt = optimize_strategy(
            bars, PARAMS, symbol=f"{sym}USDT", metric="sharpe",
            n_trials=1, oos_fraction=0.35, risk_fraction=1.0,
            strategy_name="time_series", slippage_bps=3, commission_bps=5,
        )
        res = asyncio.run(run_backtest(
            bars, make_strategy("time_series", **opt.best_params),
            symbol=f"{sym}USDT", initial_capital=Decimal("10000"),
            risk_fraction=1.0, slippage_bps=3, commission_bps=5))
        ret, sharpe, mdd = metrics(res.equity_curve)
        winners[sym] = opt.best_params
        p, th = opt.best_params["period"], opt.best_params["threshold"]
        print(f"{sym:<5} ({p:>3},{th:>5}){'':<6} {opt.best_score:>8.2f} "
              f"{opt.oos_score:>8.2f} {opt.oos_return:>7.1%}   "
              f"{ret:>7.1%} / {sharpe:>5.2f} / {mdd:>5.1%}")

        print(f"      plateau (period, thr, ret, sharpe, mdd):")
        for p2, th2, r2, s2, m2 in plateau(bars, f"{sym}USDT", opt.best_params):
            mark = " <-- winner" if (p2 == p and abs(th2 - th) < 1e-9) else ""
            print(f"        ({p2:>3},{th2:>5})  {r2:>7.1%} {s2:>6.2f} {m2:>6.1%}{mark}")


if __name__ == "__main__":
    main()
