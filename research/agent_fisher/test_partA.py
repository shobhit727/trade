"""PART A — the official out-of-sample evaluation.

V2 (period=20, entry=0.50) was selected on TRAIN in train.py and is frozen here.
TEST (2024-01-01 -> 2026-10-01) is touched exactly once by this script, unchanged.
Controls (buy-and-hold, random signal, nsealgo composite) are comparisons, not
strategy variants.
"""

from __future__ import annotations

import json
from decimal import Decimal

from common import (
    TEST,
    bh_returns,
    bt,
    cost_model,
    fisher_score,
    load,
    random_signal_score,
    slice_metrics,
    window_diag,
)

PERIOD, ENTRY = 20, 0.50  # frozen from train.py -> train_selection.json == "V2"
RATE = float(cost_model().all_in_round_trip_bps(Decimal("100000"))) / 1e4


def line(name: str, m, dg: dict) -> str:
    return (
        f"{name:<28} CAGR {m.cagr*100:>7.2f}%  Sharpe {m.sharpe:>5.2f}  "
        f"MaxDD {m.max_drawdown*100:>7.2f}%  Calmar {m.calmar:>5.2f}  "
        f"Turn {dg.get('annual_turnover', 0.0):>5.2f}x/y  "
        f"CostDrag {dg.get('cost_drag_annual', 0.0)*100:>5.2f}%/y  "
        f"Total {m.total_return*100:>8.2f}%  "
        f"names {dg.get('avg_material_names', float('nan')):.1f}"
    )


def main() -> None:
    with open("train_selection.json") as fh:
        sel = json.load(fh)
    assert sel["selected"] == "V2", f"train selection changed: {sel}"
    print(f"frozen selection from TRAIN: {sel['selected']} "
          f"(period={PERIOD}, entry={ENTRY})")
    print(f"TEST window {TEST[0]} -> {TEST[1]}, net of {RATE*1e4:.2f} bps round-trip\n")

    panel, _ = load()
    out: dict = {}

    # ---------------- STRATEGY (frozen V2) ----------------
    score, sig = fisher_score(panel, PERIOD, ENTRY)
    res = bt(panel, score)
    gross = bt(panel, score, zero_cost=True)
    m = slice_metrics(res.equity, res.returns, *TEST)
    dg = window_diag(res, *TEST, gross_result=gross)
    gm = slice_metrics(gross.equity, gross.returns, *TEST)
    nbar = int(res.equity.loc[TEST[0]:TEST[1]].shape[0])
    w = res.weights
    purity = float(
        (w.where((sig > 0).reindex(w.index).fillna(False), 0.0).sum(axis=1)
         / w.sum(axis=1)).mean()
    )
    out["strategy"] = {
        "cagr": m.cagr, "sharpe": m.sharpe, "max_dd": m.max_drawdown,
        "calmar": m.calmar, "vol": m.volatility, "gross_cagr": gm.cagr,
        "signal_purity": purity, "bars": nbar, **dg,
    }

    print("=== TEST — Fisher V2 (period=20, entry=0.50) ===")
    print(line("Fisher V2 (NET)", m, dg))
    print(f"{'':28} gross @0 cost CAGR {gm.cagr*100:>7.2f}%  -> net cost drag "
          f"{dg['cost_drag_annual']*100:.2f}%/y")
    print(f"{'':28} vol {m.volatility*100:.1f}%  win {m.win_rate*100:.1f}%  "
          f"book wt {dg['avg_book_weight']:.3f}  "
          f"long-frac {float((sig > 0).to_numpy().mean())*100:.1f}%")
    print(f"{'':28} bars {nbar}  ({nbar/244:.2f}y)  "
          f"signal purity {purity*100:.0f}%")

    # ---------------- BUY AND HOLD ----------------
    print("\n=== TEST — buy-and-hold, identical window, net of the same costs ===")
    print(f"{'':28}(equal-weight all 48 names; exact weight-drift turnover)")
    out["bh"] = {}
    bh_series: dict = {}
    for label, rb in (("BH buy & hold (1 entry)", None),
                      ("BH equal-wt monthly", "M"),
                      ("BH brief recipe (daily)", "D")):
        d, e, tot = bh_returns(panel, rb, RATE)
        bh_series[label] = d
        bm = slice_metrics(e, d, *TEST)
        nb = int(e.loc[TEST[0]:TEST[1]].shape[0])
        yrs = nb / 244.0
        dgb = {"annual_turnover": tot / yrs,
               "cost_drag_annual": tot / yrs * RATE,
               "avg_material_names": float(panel.shape[1])}
        out["bh"][label] = {"cagr": bm.cagr, "sharpe": bm.sharpe,
                            "max_dd": bm.max_drawdown, "calmar": bm.calmar,
                            "turnover": tot / yrs}
        print(line(label, bm, dgb))

    # ---------------- RANDOM-SIGNAL CONTROL ----------------
    rscore = random_signal_score(panel, sig)
    rres = bt(panel, rscore)
    rm = slice_metrics(rres.equity, rres.returns, *TEST)
    rdg = window_diag(rres, *TEST, gross_result=bt(panel, rscore, zero_cost=True))
    out["random"] = {"cagr": rm.cagr, "sharpe": rm.sharpe, "max_dd": rm.max_drawdown,
                     "calmar": rm.calmar, **rdg}
    print("\n=== TEST — negative control: random gate, same % of bars long ===")
    print(line("Random signal (NET)", rm, rdg))
    print(f"{'':28} Sharpe edge over random: {m.sharpe - rm.sharpe:+.2f}   "
          f"CAGR edge: {(m.cagr - rm.cagr)*100:+.2f} pp")

    # ---------------- NSEALGO COMPOSITE ----------------
    from nsealgo.backtest.metrics import yearly_returns
    from nsealgo.factors.core import build_composite_score

    comp = build_composite_score(panel)
    cres = bt(panel, comp)
    cm = slice_metrics(cres.equity, cres.returns, *TEST)
    cdg = window_diag(cres, *TEST, gross_result=bt(panel, comp, zero_cost=True))
    out["composite"] = {"cagr": cm.cagr, "sharpe": cm.sharpe,
                        "max_dd": cm.max_drawdown, "calmar": cm.calmar, **cdg}
    print("\n=== TEST — benchmark: nsealgo composite ===")
    print(line("nsealgo composite (NET)", cm, cdg))
    print(f"{'':28} Sharpe edge over composite: {m.sharpe - cm.sharpe:+.2f}   "
          f"CAGR edge: {(m.cagr - cm.cagr)*100:+.2f} pp")

    # ---------------- YEARLY ----------------
    print("\n=== TEST calendar-year returns (net) ===")
    ys = yearly_returns(res.returns.loc[TEST[0]:TEST[1]])
    yb = yearly_returns(bh_series["BH buy & hold (1 entry)"].loc[TEST[0]:TEST[1]])
    for y in sorted(set(ys.index) | set(yb.index)):
        a = f"{ys.get(y, float('nan'))*100:>7.2f}%" if y in ys.index else "      -"
        b = f"{yb.get(y, float('nan'))*100:>7.2f}%" if y in yb.index else "      -"
        print(f"  {y}   strategy {a}   buy&hold {b}")

    with open("test_partA.json", "w") as fh:
        json.dump(out, fh, indent=2, default=float)
    print("\nsaved test_partA.json")


if __name__ == "__main__":
    main()
