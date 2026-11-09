"""STAGE 1 — TRAIN-only sweep of the 5 DECLARED variants.

TRAIN = 2016-01-01 .. 2023-12-31. TEST is not loaded, not sliced, not peeked at.

Selection rule (declared in REPORT.md before any run): highest TRAIN Sharpe,
ties broken by lower TRAIN MaxDD. Only the winner advances to TEST.
"""

from __future__ import annotations

import json
import sys

import pandas as pd

sys.path.insert(0, "src")
sys.path.insert(0, "research/agent_vwm")

from common import (  # noqa: E402
    COST_MODEL,
    TEST_END,
    TEST_START,
    TRAIN_END,
    TRAIN_START,
    load_panels,
    momentum_rank_score,
    slice_split,
    vwm_signal,
)

from nsealgo.backtest.engine import PortfolioConfig, run_backtest  # noqa: E402
from nsealgo.backtest.metrics import yearly_returns  # noqa: E402
from nsealgo.factors.core import build_composite_score  # noqa: E402
from nsealgo.provenance import provenance  # noqa: E402

VARIANTS = [
    ("V1", 20, 0.01),
    ("V2", 20, 0.05),
    ("V3", 63, 0.03),
    ("V4", 126, 0.06),
    ("V5", 252, 0.10),
]

CFG = PortfolioConfig()
OUT = "research/agent_vwm/stage1_train.json"


def rows_stats(res) -> dict:
    m = res.metrics
    return {
        "cagr": m.cagr,
        "sharpe": m.sharpe,
        "max_dd": m.max_drawdown,
        "calmar": m.calmar,
        "turnover_yr": m.annual_turnover,
        "cost_drag_yr": m.cost_drag_annual,
        "trades_yr": m.trades_per_year,
        "avg_names": res.diag["avg_names"],
        "avg_top_weight": res.diag["avg_top_weight"],
        "rt_bps": res.diag["round_trip_bps"],
        "total_return": m.total_return,
        "vol": m.volatility,
    }


def main() -> None:
    px, vol, symbols = load_panels()
    px_tr = slice_split(px, TRAIN_START, TRAIN_END)
    vol_tr = slice_split(vol, TRAIN_START, TRAIN_END)
    print(f"TRAIN panel: {px_tr.index[0].date()} -> {px_tr.index[-1].date()} "
          f"({len(px_tr)} bars, {px_tr.shape[1]} symbols)")
    print(f"TEST window deliberately NOT loaded: "
          f"{TEST_START.date()} .. {TEST_END.date()}")

    # ---- volume-free control: identical construction, volume term deleted.
    from common import roc_panel

    results = {}
    print()
    print("=" * 100)
    print("TRAIN SWEEP — 5 declared variants (selection: highest TRAIN Sharpe)")
    print("=" * 100)
    print(f"{'id':<4}{'period':>7}{'thr':>7}{'CAGR':>9}{'Sharpe':>9}{'MaxDD':>9}"
          f"{'Calmar':>8}{'Turn/y':>8}{'Cost/y':>8}{'Names':>7}{'Long%':>8}")
    print("-" * 100)

    for vid, period, thr in VARIANTS:
        sig, diag = vwm_signal(px_tr, vol_tr, period, thr, long_only=True)
        score = momentum_rank_score(px_tr, sig, mom_days=126)
        res = run_backtest(px_tr, score, COST_MODEL, CFG, rebalance="M")
        r = rows_stats(res)
        r["diag"] = diag
        results[vid] = {
            "period": period, "threshold": thr, **r,
            "yearly": {str(k): float(v) for k, v in yearly_returns(res.returns).items()},
        }
        print(f"{vid:<4}{period:>7}{thr:>7}{r['cagr']*100:>8.2f}%{r['sharpe']:>9.2f}"
              f"{r['max_dd']*100:>8.2f}%{r['calmar']:>8.2f}{r['turnover_yr']:>8.2f}"
              f"{r['cost_drag_yr']*100:>7.2f}%{r['avg_names']:>7.1f}"
              f"{diag['frac_cells_long']*100:>7.1f}%")

    # ---- control A: is volume doing anything? compare against pure ROC gate.
    print()
    print("=" * 100)
    print("CONTROL A — volume-free version of each variant (identical except the")
    print("volume term is deleted). If TRAIN results match, volume contributes nothing.")
    print("=" * 100)
    print(f"{'id':<4}{'CAGR':>9}{'Sharpe':>9}{'MaxDD':>9}   vs volume version")
    print("-" * 100)
    for vid, period, thr in VARIANTS:
        m = roc_panel(px_tr, period)
        sig = pd.DataFrame(0.0, index=px_tr.index, columns=px_tr.columns)
        sig[m > thr] = 1.0
        sig[m.isna()] = 0.0
        score = momentum_rank_score(px_tr, sig, mom_days=126)
        res = run_backtest(px_tr, score, COST_MODEL, CFG, rebalance="M")
        r = rows_stats(res)
        v = results[vid]
        results[vid]["novol"] = r
        same = "IDENTICAL" if abs(r["cagr"] - v["cagr"]) < 1e-12 else "DIFFERS"
        print(f"{vid:<4}{r['cagr']*100:>8.2f}%{r['sharpe']:>9.2f}{r['max_dd']*100:>8.2f}%"
              f"   {same} (dCAGR={abs(r['cagr']-v['cagr'])*100:+.4f}pp)")

    # ---- control B: the nsealgo composite on the same TRAIN panel.
    print()
    print("=" * 100)
    print("CONTROL B — nsealgo composite (build_composite_score) on the same TRAIN panel")
    print("=" * 100)
    comp = build_composite_score(px_tr)
    res_c = run_backtest(px_tr, comp, COST_MODEL, CFG, rebalance="M")
    rc = rows_stats(res_c)
    results["composite"] = rc
    print(f"{'composite':<4}{rc['cagr']*100:>8.2f}%{rc['sharpe']:>9.2f}"
          f"{rc['max_dd']*100:>8.2f}%{rc['calmar']:>8.2f}{rc['turnover_yr']:>8.2f}"
          f"{rc['cost_drag_yr']*100:>7.2f}%{rc['avg_names']:>7.1f}")

    # ---- winner selection, by the pre-declared rule.
    ranked = sorted(
        (k for k in results if k.startswith("V")),
        key=lambda k: (-results[k]["sharpe"], results[k]["max_dd"]),
    )
    winner = ranked[0]
    results["_winner"] = winner
    results["_ranking"] = ranked
    results["_provenance"] = provenance()
    print()
    print(f"SELECTION (pre-declared: max TRAIN Sharpe) -> winner = {winner} "
          f"(period={results[winner]['period']}, threshold={results[winner]['threshold']})")
    print(f"  ranking by TRAIN Sharpe: {ranked}")

    with open(OUT, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
