"""End-to-end trading-logic test: catalog strategies vs synthetic bars."""

from __future__ import annotations

import asyncio
import logging
import math
from datetime import UTC, datetime

from cryptobot.backtest.runner import OhlcvBar, make_strategy, run_backtest
from cryptobot.backtest.validation import run_validation

logging.disable(logging.CRITICAL)


def synthetic(n=2000, seed=42, drift=0.0, vol=0.02):
    import numpy as np

    rng = np.random.default_rng(seed)
    z = rng.normal(0, 1, n)
    px = 100.0
    out = []
    for i in range(n):
        ret = drift + vol * z[i]
        new_px = px * math.exp(ret)
        h = new_px * (1 + abs(z[i]) * 0.003)
        lo = new_px * (1 - abs(z[i]) * 0.003)
        out.append(
            OhlcvBar(
                timestamp=datetime(2026, 1, 1, tzinfo=UTC),
                open=px,
                high=h,
                low=lo,
                close=new_px,
                volume=1000.0,
            )
        )
        px = new_px
    return out


def run_one(bars, name):
    strat = make_strategy(name)
    result = asyncio.run(run_backtest(bars, strat, collect_trades=False))
    ec = result.equity_curve
    rets = []
    for i in range(1, len(ec)):
        prev, cur = float(ec[i - 1][1]), float(ec[i][1])
        if prev > 0:
            rets.append((cur - prev) / prev)
    if len(rets) < 30:
        return {
            "name": name,
            "trades": result.n_trades,
            "total_return": result.total_return,
            "n_rets": len(rets),
        }
    v = run_validation(rets, n_splits=5, n_permutations=100, n_trials=10)
    return {
        "name": name,
        "trades": result.n_trades,
        "ret": result.total_return,
        "wf": v["walk_forward"]["oos_sharpe"],
        "ds": v["deflated_sharpe"]["deflated_sharpe"]
        if isinstance(v["deflated_sharpe"], dict)
        else v["deflated_sharpe"],
        "mc_p": v["monte_carlo"]["p_value"],
        "passed": bool(v["passed"]),
    }


NAMES = sorted(
    {
        "macd",
        "ma_cross",
        "donchian",
        "bollinger",
        "stochastic",
        "rsi",
        "ema_cross",
        "supertrend",
        "volume_spike",
        "vwap",
        "atr_breakout",
        "breakout_momentum",
        "trend_momentum",
        "mfi",
        "obv",
        "roc",
        "trend_following",
        "mean_reversion",
    }
)


def main():
    bars = synthetic()
    print(f"{'name':<22} {'ret':>8} {'wf_sharpe':>9} {'ds':>7} {'mc_p':>7} {'passed':>7}  trades")
    print("-" * 75)
    passed = 0
    for name in NAMES:
        r = run_one(bars, name)
        if "wf" not in r:
            print(f"{name:<22}  ret={r['total_return']:+.3f}  n_rets={r['n_rets']}")
            continue
        passed += int(r["passed"])
        print(
            f"{name:<22} {r['ret']:+8.3f} {r['wf']:+9.2f} {r['ds']:+7.2f} {r['mc_p']:>7.3f} {str(r['passed']):>7}  {r['trades']:>6d}"
        )
    print(f"\n{passed}/{len(NAMES)} survived walk-forward + Monte Carlo gauntlet")


if __name__ == "__main__":
    main()
