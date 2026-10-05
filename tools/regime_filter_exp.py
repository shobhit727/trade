"""Regime-filter experiment: does trading only above the 200d SMA cut MDD
without killing returns? (Seed Phase RESEARCH-a)

Runs the validated walk-forward winners (BTC 5/50, ETH 15/80) with and
without a 200-day SMA regime gate, full period + per-year split.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from decimal import Decimal

import pandas as pd

logging.disable(logging.CRITICAL)

from cryptobot.backtest.metrics import PerformanceMetrics
from cryptobot.backtest.runner import OhlcvBar, make_strategy, run_backtest

ASSETS = {
    "BTC": ("data/btcusdt_1d.csv", {"fast": 5, "slow": 50}),
    "ETH": ("data/ethusdt_1d.csv", {"fast": 15, "slow": 80}),
}
SMA_WINDOW = 200


def load(path: str) -> pd.DataFrame:
    return pd.read_csv(path)


def bars_from(df: pd.DataFrame, mask=None) -> list[OhlcvBar]:
    if mask is not None:
        df = df[mask].reset_index(drop=True)
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
    sharpe = float(pm.calculate_sharpe_ratio(rets))
    mdd = float(pm.calculate_drawdown(pd.Series(values))) / 100.0
    return values[-1] / values[0] - 1.0, sharpe, mdd


async def run_case(name, params, bars):
    res = await run_backtest(bars, make_strategy("dual_ma", **params),
                             symbol="X", initial_capital=Decimal("10000"),
                             risk_fraction=1.0, slippage_bps=3, commission_bps=5)
    return metrics(res.equity_curve)


def main():
    print(f"{'asset':<5}{'variant':<14}{'ret':>9}{'sharpe':>8}{'mdd':>8}   days")
    print("-" * 56)
    for asset, (path, params) in ASSETS.items():
        df = load(path)
        sma = df["close"].rolling(SMA_WINDOW).mean()
        above = df["close"] > sma

        variants = {
            "always-in": bars_from(df),
            "sma200-only": bars_from(df, above),
            "below-200": bars_from(df, ~above),
        }
        for vname, bars in variants.items():
            ret, sharpe, mdd = asyncio.run(run_case(vname, params, bars))
            print(f"{asset:<5}{vname:<14}{ret:>8.1%}{sharpe:>8.2f}{mdd:>7.1%}   {len(bars)}")
    print("\nNote: filtered runs trade only the subset of days; compare MDD and"
          "\nSharpe, not raw returns (fewer days = fewer compounding periods).")


if __name__ == "__main__":
    main()
