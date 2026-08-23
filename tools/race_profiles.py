"""Race the agreed risk profiles on real data (Seed Phase SEED-6e).

Profiles (PROJECT_MEMORY/28):
  realistic  : spot-only long/flat, risk_fraction = 1.0
  aggressive : same signals, long-SHORT with leverage, perp funding paid,
               approximate liquidation enforced

Leverage is expressed through risk_fraction (engine rescales qty =
rf * equity / price; flip orders carry 2x). max_leverage enables the
isolated-margin liquidation check.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from decimal import Decimal

import pandas as pd

logging.disable(logging.CRITICAL)

from cryptobot.backtest.funding import FixedFundingProvider
from cryptobot.backtest.metrics import PerformanceMetrics
from cryptobot.backtest.runner import OhlcvBar, make_strategy, run_backtest

ASSETS = {
    "BTC": ("data/btcusdt_1d.csv", {"fast": 5, "slow": 50}),
    "ETH": ("data/ethusdt_1d.csv", {"fast": 15, "slow": 80}),
}
PROFILES = [
    ("realistic spot", dict(risk_fraction=1.0, max_leverage=None, funding=None)),
    ("aggressive 2x", dict(risk_fraction=2.0, max_leverage=Decimal(2),
                           funding=FixedFundingProvider(rate=Decimal("0.0001")))),
    ("aggressive 3x", dict(risk_fraction=3.0, max_leverage=Decimal(3),
                           funding=FixedFundingProvider(rate=Decimal("0.0001")))),
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


async def run_case(name, params, bars, symbol, cfg):
    res = await run_backtest(bars, make_strategy("dual_ma", **params),
                             symbol=symbol, initial_capital=Decimal("10000"),
                             slippage_bps=3, commission_bps=5,
                             collect_trades=True, **cfg)
    ret, sharpe, mdd = metrics(res.equity_curve)
    liq = sum(1 for t in res.trades if t.get("strategy") == "liquidation")
    shorts = sum(1 for t in res.trades if t.get("side") == "short")
    return ret, sharpe, mdd, len(res.trades), shorts, liq


def main():
    print(f"{'asset':<5}{'profile':<16}{'ret':>9}{'sharpe':>8}{'mdd':>7}"
          f"{'trades':>8}{'shorts':>8}{'liq':>5}")
    print("-" * 66)
    curves = {}
    for asset, (path, params) in ASSETS.items():
        bars = load(path)
        symbol = f"{asset}USDT"
        for pname, cfg in PROFILES:
            ret, sharpe, mdd, n, shorts, liq = asyncio.run(
                run_case(pname, params, bars, symbol, cfg))
            print(f"{asset:<5}{pname:<16}{ret:>8.1%}{sharpe:>8.2f}{mdd:>6.1%}"
                  f"{n:>8}{shorts:>8}{liq:>5}")
            if pname == "realistic spot":
                _r = asyncio.run(run_backtest(
                    bars, make_strategy("dual_ma", **params), symbol=symbol,
                    initial_capital=Decimal("10000"), risk_fraction=1.0))
                curves[asset] = [float(v) for _t, v in _r.equity_curve]


if __name__ == "__main__":
    main()
