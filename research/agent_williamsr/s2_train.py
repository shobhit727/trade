"""Step 2 — TRAIN sweep over the 5 DECLARED variants, plus all controls on TRAIN.

Method note: `run_backtest` runs on the FULL panel so every variant gets identical
warmup (126d momentum, 60d vol), then the daily return series is sliced to the window
and metrics are recomputed for that window. Weights depend only on the score at their
own rebalance date, so a TRAIN metric computed this way cannot see anything after
2023-12-31.
"""

from __future__ import annotations

import os
import sys

import pandas as pd

sys.path.insert(0, "src")
sys.path.insert(0, os.path.dirname(__file__))

from harness import (  # noqa: E402
    HDR,
    TRAIN,
    bh_score,
    load_panel,
    random_score,
    row,
    run,
    signal_panel,
    wr_score,
    year_ret,
)

from nsealgo.backtest.metrics import compute_metrics  # noqa: E402
from nsealgo.factors.core import build_composite_score  # noqa: E402
from nsealgo.provenance import provenance  # noqa: E402

VARIANTS = [
    ("V1 canonical-state", 14, -80.0, None),
    ("V2 canonical-touch21", 14, -80.0, 21),
    ("V3 deep-touch21", 14, -90.0, 21),
    ("V4 fast-touch21", 5, -80.0, 21),
    ("V5 slow-touch21", 28, -80.0, 21),
]


def slice_metrics(res, win, panel, cost_rate_bps):
    """Metrics for `win` only, from a full-history run. Costs recomputed on the slice."""
    lo, hi = win
    idx = panel.index.intersection(res.returns.index)
    idx = idx[(idx.tz_localize(None) >= lo) & (idx.tz_localize(None) <= hi)]
    r = res.returns.loc[idx]
    eq = (1.0 + r).cumprod()
    years = len(r) / 244.0
    # one-way turnover per date, from the ffill'd weight path
    turn = (res.weights.diff().abs().sum(axis=1) / 2.0).loc[idx]
    rate = cost_rate_bps / 10_000.0
    eq_full = (1.0 + r).cumprod()
    costs = float((2.0 * turn * eq_full * rate).sum())
    m = compute_metrics(r, eq, annual_turnover=float(turn.sum()) / years,
                        cost_drag_annual=costs / years,
                        trades_per_year=float((turn > 0).sum()) / years)
    out = {
        "CAGR%": m.cagr * 100, "Sharpe": m.sharpe, "MaxDD%": m.max_drawdown * 100,
        "Calmar": m.calmar, "Vol%": m.volatility * 100,
        "Turnover/y": m.annual_turnover, "CostDrag%/y": m.cost_drag_annual * 100,
        "AvgNames": float((res.weights.loc[idx] > 0).sum(axis=1).mean()),
        "TotalRet%": m.total_return * 100,
        "RupeesOn21L": float(eq.iloc[-1]) * 2_100_000.0 - 2_100_000.0,
    }
    return out, r, eq


def main():
    from nsealgo.data.loader import load_symbol

    panel, symbols, _ = load_panel()
    H = pd.DataFrame({s: load_symbol(f"data/nse/{s}_1d.csv", s)["high"]
                      for s in symbols}).reindex(panel.index)[symbols]
    L = pd.DataFrame({s: load_symbol(f"data/nse/{s}_1d.csv", s)["low"]
                      for s in symbols}).reindex(panel.index)[symbols]

    cost_rate = 21.92
    print("PROVENANCE:", provenance())
    print(f"\nRunning {len(VARIANTS)} DECLARED variants + controls on TRAIN "
          f"{TRAIN[0].date()} -> {TRAIN[1].date()}  (net of {cost_rate} bps)\n")
    print(HDR)
    print("-" * len(HDR))

    store = {}
    for name, period, lower, pers in VARIANTS:
        sig = signal_panel(panel, H, L, period, lower, pers)
        sc = wr_score(panel, sig)
        res = run(sc, panel)
        m, r, eq = slice_metrics(res, TRAIN, panel, cost_rate)
        store[name] = dict(res=res, sig=sig, score=sc, m=m, r=r)
        print(row(name, m))

    # ---- controls ------------------------------------------------------------
    ctrl = {}
    res_bh = run(bh_score(panel), panel)
    ctrl["CONTROL buy-and-hold"] = slice_metrics(res_bh, TRAIN, panel, cost_rate)[0]

    res_cmp = run(build_composite_score(panel), panel)
    ctrl["CONTROL nsealgo composite"] = slice_metrics(res_cmp, TRAIN, panel, cost_rate)[0]

    for seed in (1, 2, 3, 4, 5):
        sig = store["V2 canonical-touch21"]["sig"]
        res_r = run(random_score(panel, sig, seed), panel)
        ctrl[f"CONTROL random (seed {seed})"] = slice_metrics(res_r, TRAIN, panel, cost_rate)[0]

    for k, v in ctrl.items():
        print(row(k, v))

    print()
    best = max(store.items(), key=lambda kv: kv[1]["m"]["Sharpe"])
    print(f">>> TRAIN winner by Sharpe: {best[0]}  "
          f"(Sharpe {best[1]['m']['Sharpe']:.2f}, CAGR {best[1]['m']['CAGR%']:.2f}%)")

    print("\n--- TRAIN calendar-year returns ---")
    for k, v in store.items():
        print(f"{k:<26}{year_ret(v['r'])}")
    bh_r = slice_metrics(res_bh, TRAIN, panel, cost_rate)[1]
    cmp_r = slice_metrics(res_cmp, TRAIN, panel, cost_rate)[1]
    print(f"{'CONTROL buy-and-hold':<26}{year_ret(bh_r)}")
    print(f"{'CONTROL nsealgo composite':<26}{year_ret(cmp_r)}")

    pd.to_pickle({k: {"score": v["score"], "sig": v["sig"]} for k, v in store.items()},
                 os.path.join(os.path.dirname(__file__), "train_scores.pkl"))


if __name__ == "__main__":
    main()
