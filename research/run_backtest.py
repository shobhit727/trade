"""First-look research run: does the composite factor survive real costs?

Run:  .venv/bin/python research/run_backtest.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nsealgo.backtest.engine import PortfolioConfig, run_backtest  # noqa: E402
from nsealgo.backtest.metrics import yearly_returns  # noqa: E402
from nsealgo.costs import STRESS_MODELS, CostModel  # noqa: E402
from nsealgo.data.loader import load_universe  # noqa: E402
from nsealgo.factors.core import build_composite_score  # noqa: E402

pd.set_option("display.width", 200)


def main() -> None:
    panel, symbols, report = load_universe("data/nse")
    print(report.describe())
    print(f"Universe: {len(symbols)} symbols | "
          f"{panel.index[0].date()} -> {panel.index[-1].date()} | {len(panel)} days\n")

    score = build_composite_score(panel)
    base = CostModel(segment="delivery", slippage_bps=5)
    cfg = PortfolioConfig(n_positions=22)

    print("=" * 78)
    print("COMPOSITE FACTOR — BASE COSTS (5bps slippage)")
    print("=" * 78)
    res = run_backtest(panel, score, base, cfg, rebalance="M")
    print(res.summary())
    print(f"\navg names held: {res.diag['avg_names']:.1f}   "
          f"rebalances: {res.diag['n_rebalances']}")
    print(f"costs paid: Rs {res.costs_paid:,.0f}")

    print("\n--- COST SENSITIVITY (Gate 4) ---")
    for name, cm in STRESS_MODELS.items():
        r = run_backtest(panel, score, cm, cfg, rebalance="M")
        m = r.metrics
        print(f"  {name:<18} CAGR {m.cagr * 100:>7.2f}%  Sharpe {m.sharpe:>6.2f}  "
              f"MaxDD {m.max_drawdown * 100:>7.2f}%  Ret {m.total_return * 100:>8.1f}%")

    print("\n--- REBALANCE FREQUENCY ---")
    for freq in ("M", "Q"):
        r = run_backtest(panel, score, base, cfg, rebalance=freq)
        m = r.metrics
        print(f"  {freq:<3}  CAGR {m.cagr * 100:>7.2f}%  Sharpe {m.sharpe:>6.2f}  "
              f"MaxDD {m.max_drawdown * 100:>7.2f}%  "
              f"Turnover {m.annual_turnover:>5.2f}x  CostDrag {m.cost_drag_annual * 100:>5.2f}%")

    print("\n--- BENCHMARK: equal-weight buy & hold all 48 ---")
    ew = panel.pct_change(fill_method=None).mean(axis=1).fillna(0.0)
    from nsealgo.backtest.metrics import compute_metrics

    bm = compute_metrics(ew)
    print(f"  CAGR {bm.cagr * 100:>7.2f}%  Sharpe {bm.sharpe:>6.2f}  "
          f"MaxDD {bm.max_drawdown * 100:>7.2f}%  Ret {bm.total_return * 100:>8.1f}%")

    print("\n--- YEARLY RETURNS: strategy vs benchmark ---")
    ys = yearly_returns(res.returns).rename("strategy")
    yb = yearly_returns(ew).rename("equal-weight")
    y = pd.concat([yb, ys], axis=1)
    y["alpha"] = y["strategy"] - y["equal-weight"]
    print(y.to_string(float_format=lambda v: f"{v * 100:>7.2f}%"))
    pos = (y["strategy"] > 0).sum()
    print(f"\npositive years: {pos}/{len(y)} = {pos / len(y) * 100:.0f}%  "
          f"(Gate 3 needs >=60%)")
    print(f"years beating benchmark: {(y['alpha'] > 0).sum()}/{len(y)}")


if __name__ == "__main__":
    main()
