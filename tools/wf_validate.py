"""Generic walk-forward validation for any algo on any timeframe (phase 3).

Usage:
  python3 tools/wf_validate.py --algo ema_cross --tf 5m --symbol BTCUSDT \
      --param period=20 --param threshold=0.0

Tunes the given ParamSpecs on the leading 65% of bars, scores the winner on
the untouched 35% tail, prints train/OOS sharpe + return, and appends a line
to PROJECT_MEMORY/32_WF_Validation_Log.md.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd

logging.disable(logging.CRITICAL)

from cryptobot.backtest.metrics import PerformanceMetrics  # noqa: E402
from cryptobot.backtest.optimize import ParamSpec, optimize_strategy  # noqa: E402
from cryptobot.backtest.runner import OhlcvBar, make_strategy, run_backtest  # noqa: E402

LOG = Path("PROJECT_MEMORY/32_WF_Validation_Log.md")


def load(symbol: str, tf: str) -> list[OhlcvBar]:
    df = pd.read_csv(f"data/{symbol.lower()}_{tf}.csv")
    return [
        OhlcvBar(timestamp=datetime.fromtimestamp(int(r.ts) / 1000, tz=UTC),
                 open=float(r.open), high=float(r.high), low=float(r.low),
                 close=float(r.close), volume=float(r.vol))
        for r in df.itertuples(index=False)
    ]


def metrics(curve) -> tuple[float, float, float]:
    v = [float(x) for _t, x in curve]
    pm = PerformanceMetrics()
    pm.add_value(v[0])
    for x in v[1:]:
        pm.add_value(x)
    rets = [v[i] / v[i - 1] - 1.0 for i in range(1, len(v))]
    return (v[-1] / v[0] - 1.0,
            float(pm.calculate_sharpe_ratio(rets)),
            float(pm.calculate_drawdown(pd.Series(v))) / 100.0)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--algo", required=True)
    ap.add_argument("--tf", default="1d")
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--oos", type=float, default=0.35)
    ap.add_argument("--param", action="append", default=[],
                    help="name=value; int if integer else float")
    args = ap.parse_args()

    specs = []
    for kv in args.param:
        k, v = kv.split("=", 1)
        val = float(v)
        lo, hi = val * 0.6, val * 1.6
        if float(val).is_integer():
            specs.append(ParamSpec(k, max(1, round(lo)), round(hi), "int"))
        else:
            specs.append(ParamSpec(k, lo, hi, "float"))

    bars = load(args.symbol, args.tf)
    # All --param entries become tuned ParamSpecs (±40%); nothing is passed
    # through as a fixed kwarg — optimize_strategy only accepts its own
    # signature plus ParamSpecs (#fixed was a bug: TypeError + n_trials=1
    # made "tuning" a single random draw).
    opt = optimize_strategy(
        bars, specs, symbol=args.symbol, metric="sharpe",
        n_trials=30, oos_fraction=args.oos, risk_fraction=1.0,
        strategy_name=args.algo, slippage_bps=3, commission_bps=5,
    )
    res = asyncio.run(run_backtest(
        bars, make_strategy(args.algo, **opt.best_params), symbol=args.symbol,
        initial_capital=Decimal("10000"), risk_fraction=1.0,
        slippage_bps=3, commission_bps=5))
    ret, sharpe, mdd = metrics(res.equity_curve)

    verdict = "PASS" if (opt.oos_score or -9) > 0.3 and (opt.oos_return or -9) > 0 else "FAIL"
    print(f"{args.algo} {args.symbol} {args.tf} params={opt.best_params}")
    print(f"  train sharpe : {opt.best_score:.2f}")
    print(f"  OOS   sharpe : {opt.oos_score:.2f}")
    print(f"  OOS   return : {(opt.oos_return or 0):.1%}")
    print(f"  full period  : {ret:.1%} / {sharpe:.2f} / mdd {mdd:.1%}")
    print(f"  VERDICT      : {verdict}")

    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(
            f"| {args.algo} | {args.symbol} | {args.tf} | "
            f"`{json_dumps(opt.best_params)}` | {opt.best_score:.2f} | "
            f"{opt.oos_score:.2f} | {(opt.oos_return or 0):.1%} | {verdict} |\n")


def json_dumps(d: dict) -> str:
    import json

    return json.dumps(d)


if __name__ == "__main__":
    main()
