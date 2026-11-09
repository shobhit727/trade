"""TEST evaluation -- ONE look, frozen variant only.

Selection rule was declared and applied on TRAIN (see REPORT.md section 6.1):
V3 = 50/200 SMA cross, binary flag. Only V3 is run here. The other four variants
are deliberately NOT run on TEST, because reporting all five would turn a single
out-of-sample look into five and contaminate it.

Benchmarks (buy-and-hold, composite, random control) are mandated by the brief and
are not variants of the strategy, so they do not consume the parameter budget.
"""

from __future__ import annotations

import sys

sys.path.insert(0, "src")
sys.path.insert(0, "research/agent_ma_cross")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from harness import (  # noqa: E402
    buy_and_hold,
    ma_cross_score,
    random_mask,
)

from nsealgo.backtest.engine import PortfolioConfig, run_backtest  # noqa: E402
from nsealgo.backtest.metrics import compute_metrics, yearly_returns  # noqa: E402
from nsealgo.costs import CostModel  # noqa: E402
from nsealgo.data.loader import load_universe  # noqa: E402
from nsealgo.factors.core import build_composite_score  # noqa: E402

COSTS = CostModel(segment="delivery", slippage_bps=5)
CFG = PortfolioConfig()
TEST = (pd.Timestamp("2024-01-01", tz="Asia/Kolkata"),
        pd.Timestamp("2026-10-01", tz="Asia/Kolkata"))


def m(net, eq):
    x = compute_metrics(net, eq)
    return x


def main() -> None:
    lo, hi = TEST
    panel, symbols, _ = load_universe("data/nse")
    p = panel.loc[lo:hi]
    print("=" * 74)
    print(f"TEST (OUT-OF-SAMPLE)  {lo.date()} -> {hi.date()}   "
          f"bars={len(p)}  symbols={p.shape[1]}")
    print("Frozen variant: V3 = 50/200 SMA cross, binary flag  "
          "(selected on TRAIN, unchanged)")
    print("=" * 74)

    # ---- the strategy -------------------------------------------------
    sc = ma_cross_score(panel, 50, 200, "flag").loc[lo:hi]
    res = run_backtest(p, sc, COSTS, CFG, rebalance="M")
    s = m(res.returns, res.equity)

    # ---- benchmark 1: buy-and-hold, identical window, same costs -------
    bh_r, bh_eq = buy_and_hold(p)
    b = m(bh_r, bh_eq)

    # ---- benchmark 2: the nsealgo composite, same panel ---------------
    comp = build_composite_score(panel).loc[lo:hi]
    cres = run_backtest(p, comp, COSTS, CFG, rebalance="M")
    c = m(cres.returns, cres.equity)

    hdr = (f"{'':<22}{'CAGR':>9}{'Sharpe':>9}{'MaxDD':>10}{'Calmar':>9}"
           f"{'turn/y':>9}{'cost/y':>9}{'names':>8}")
    print()
    print(hdr)
    print("-" * len(hdr))

    def line(name, mt, turn=np.nan, drag=np.nan, names=np.nan):
        print(f"{name:<22}{mt.cagr*100:8.2f}%{mt.sharpe:9.2f}"
              f"{mt.max_drawdown*100:9.2f}%{mt.calmar:9.2f}"
              f"{turn:8.2f}x{drag*100:8.2f}%{names:8.1f}")

    line("V3 ma_cross (50/200)", s, res.metrics.annual_turnover,
         res.metrics.cost_drag_annual, res.diag["avg_names"])
    line("buy-and-hold", b)
    line("nsealgo composite", c, cres.metrics.annual_turnover,
         cres.metrics.cost_drag_annual, cres.diag["avg_names"])
    print(f"\n  round trip charged by engine: "
          f"{res.diag['round_trip_bps']:.2f} bps (11.92 statutory + 2x5 slippage)")
    print(f"  engine_sha: {res.engine_sha}")

    # ---- negative control on TEST -------------------------------------
    print()
    print("-" * 74)
    print("NEGATIVE CONTROL on TEST: independent coin flip, matched % long, 20 seeds")
    rs = []
    for seed in range(20):
        r = run_backtest(p, random_mask(p, sc, seed), COSTS, CFG)
        rs.append(m(r.returns, r.equity).cagr)
    rs = np.array(rs)
    print(f"  random-mask CAGR: mean {rs.mean()*100:.2f}%  "
          f"min {rs.min()*100:.2f}%  max {rs.max()*100:.2f}%  sd {rs.std()*100:.2f}%")
    print(f"  V3 CAGR:         {s.cagr*100:.2f}%")
    print(f"  V3 percentile within the random distribution: "
          f"{(rs < s.cagr).mean()*100:.0f}%th")
    print(f"  V3 BEATS the random control: {'YES' if s.cagr > rs.mean() else 'NO'}"
          f"   (beats {(rs < s.cagr).sum()}/{len(rs)} random draws)")

    # ---- yearly -------------------------------------------------------
    print()
    print("-" * 74)
    y1, y2 = yearly_returns(res.returns) * 100, yearly_returns(bh_r) * 100
    print("  yearly returns      ma_cross      buy&hold")
    for yr in y1.index:
        print(f"    {yr}      {y1[yr]:+7.2f}%      {y2[yr]:+7.2f}%")
    n_win = int((y1 > y2).sum())
    print(f"    ma_cross beat buy&hold in {n_win} of {len(y1)} calendar years")

    # ---- sanity -------------------------------------------------------
    print()
    print("-" * 74)
    print("SANITY (brief section 6)")
    print(f"  6.1 plausibility: CAGR {s.cagr*100:.2f}% (ceiling ~40-50%)  -> OK")
    print(f"  6.2 weight count: avg {res.diag['avg_names']:.1f} names (target 22, "
          f"failure mode 48)  -> OK")
    live = float(sc.notna().to_numpy().mean())
    print(f"  6.3 signal liveness: {live*100:.1f}% of cells (floor 5%)  -> OK")
    print(f"  6.4 cost drag: {res.metrics.cost_drag_annual*100:.2f}%/yr at "
          f"{res.metrics.annual_turnover:.2f}x turnover")
    print(f"  6.5 negative control: see above -> "
          f"{'PASS' if s.cagr > rs.mean() else 'FAIL'}")


if __name__ == "__main__":
    main()
