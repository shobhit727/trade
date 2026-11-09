"""Step 3 — protocol run: 5 declared variants on TRAIN, then TEST exactly once.

DECLARED PARAMETER BUDGET (fixed before any performance number was produced,
chosen from TRAIN liveness diagnostics in 01/02 only):

  V1  period=20  thr=0.050  momentum   <- catalog defaults verbatim (baseline)
  V2  period=20  thr=0.020  momentum   <- selective (31% gate, ~7.7 names/day)
  V3  period=20  thr=0.012  momentum   <- very selective (6% gate, ~1.5 names/day)
  V4  period=40  thr=0.030  momentum   <- longer squeeze window (~median CV40)
  V5  period=20  thr=0.020  roc        <- V2 with the strategy's own ROC ranking

Selection rule, fixed in advance: pick the TRAIN variant with the best TRAIN
Sharpe, subject to TRAIN avg-names >= 5 (a book of 1-2 names is not a book).
Then that variant goes to TEST unchanged. No other tuning.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pandas as pd
from common import (
    BASE,
    DATA,
    TEST,
    TRAIN,
    Metrics,
    Variant,
    buy_and_hold,
    composite_returns,
    hr,
    liveness,
    load_universe,
    metrics_for,
    run_variant,
    sector_exposure,
    squeeze_signal,
    table,
    yearly_returns,
)

from nsealgo.backtest.engine import PortfolioConfig
from nsealgo.backtest.metrics import compute_metrics
from nsealgo.costs import STRESS_MODELS

VARIANTS: list[Variant] = [
    Variant("V1 p20 t.050 mom", 20, 0.050, "momentum", note="catalog defaults"),
    Variant("V2 p20 t.020 mom", 20, 0.020, "momentum", note="selective"),
    Variant("V3 p20 t.012 mom", 20, 0.012, "momentum", note="very selective"),
    Variant("V4 p40 t.030 mom", 40, 0.030, "momentum", note="longer window"),
    Variant("V5 p20 t.020 roc", 20, 0.020, "roc", note="strategy-native rank"),
]

OUT = Path(__file__).resolve().parent
CFG = PortfolioConfig()


def line(label: str, m: Metrics, names: float, lf: float, extra: str = "") -> str:
    return (
        f"{label:<20} CAGR {m.cagr * 100:>7.2f}%  Sharpe {m.sharpe:>6.2f}  "
        f"MaxDD {m.max_drawdown * 100:>7.2f}%  Calmar {m.calmar:>6.2f}  "
        f"turn {m.annual_turnover:>5.2f}x/y  drag {m.cost_drag_annual * 100:>5.2f}%/y  "
        f"names {names:>5.1f}  long {lf * 100:>5.1f}%{extra}"
    )


def main() -> None:
    panel, symbols, _ = load_universe(str(DATA))
    store: dict = {"variants": {}}

    # ------------------------------------------------------------------ #
    hr("1. TRAIN (2016-01-01 -> 2023-12-31) — selection only, 5 declared variants")
    tr_rows, tr_results = [], {}
    for v in VARIANTS:
        r, w, m, d = run_variant(panel, v, TRAIN, CFG)
        px = panel.loc[TRAIN[0] : TRAIN[1]]
        _, lng, _ = squeeze_signal(px, v.period, v.threshold,
                                                         v.roc_lookback)
        lv = liveness(px, lng)
        tr_results[v.name] = (r, m, w, lv)
        tr_rows.append(line(v.name, m, d["avg_names"], lv["bar_frac"],
                            f"  [{v.note}]"))
    table(tr_rows, "TRAIN results:")
    print("\n  avg names is the key sanity number: brief §6.2 says ~22 expected.")

    eligible = {
        k: v for k, v in tr_results.items()
        if float((v[2] > 0).sum(axis=1).mean()) >= 5.0
    }
    if not eligible:
        eligible = tr_results
    chosen = max(eligible, key=lambda k: eligible[k][1].sharpe)
    print(f"\n  SELECTION (best TRAIN Sharpe, avg names >= 5): -> {chosen}")
    store["chosen"] = chosen

    # ------------------------------------------------------------------ #
    hr("2. TEST (2024-01-01 -> 2026-10-01) — touched once, nothing tuned after this")
    te_rows, te_results = [], {}
    for v in VARIANTS:
        r, w, m, d = run_variant(panel, v, TEST, CFG)
        px = panel.loc[TEST[0] : TEST[1]]
        _, lng, _ = squeeze_signal(px, v.period, v.threshold,
                                                         v.roc_lookback)
        lv = liveness(px, lng)
        te_results[v.name] = (r, m, w, lv, d)
        mark = " <<< PROTOCOL-SELECTED" if v.name == chosen else ""
        te_rows.append(line(v.name, m, d["avg_names"], lv["bar_frac"],
                            f"{mark}  [{v.note}]"))
    table(te_rows, "TEST results (all 5 shown for transparency; only "
                   f"'{chosen}' was selected on TRAIN):")

    sel = chosen
    sr, sm, sw, slv, sd = te_results[sel]

    # ------------------------------------------------------------------ #
    hr("3. TEST BENCHMARKS over the identical window")
    bh = buy_and_hold(panel)
    bh_test = bh.loc[TEST[0] : TEST[1]]
    bm = metrics_for(bh_test, TEST, turnover=1.80)
    comp = composite_returns(panel, TEST)
    cm = compute_metrics(comp)

    rows = [
        line("STRATEGY", sm, sd["avg_names"], slv["bar_frac"]),
        line("buy&hold", bm, 48.0, 1.0, "  [equal-weight, 100% inv]"),
        line("nsealgo composite", cm, 22.0, 1.0, "  [the thing to beat]"),
    ]
    table(rows, "TEST head-to-head:")
    rt = float(BASE.all_in_round_trip_bps(Decimal("100000")))
    st = float(BASE.round_trip_bps(Decimal("100000")))
    print(f"\n  round-trip cost applied: {rt:.2f} bps "
          f"(statutory {st:.2f} + 2x5 bps slippage)")

    # ------------------------------------------------------------------ #
    hr("4. TEST vs BUY-AND-HOLD — return AND drawdown")
    print(f"{'':>22} {'CAGR':>9} {'Sharpe':>8} {'Sortino':>9} {'MaxDD':>9} {'Calmar':>8}")
    for lab, m in (("strategy", sm), ("buy&hold", bm), ("composite", cm)):
        print(f"{lab:>22} {m.cagr * 100:>8.2f}% {m.sharpe:>8.2f} {m.sortino:>9.2f} "
              f"{m.max_drawdown * 100:>8.2f}% {m.calmar:>8.2f}")
    print(f"{'ALPHA vs B&H':>22} {(sm.cagr - bm.cagr) * 100:>+8.2f}% "
          f"{sm.sharpe - bm.sharpe:>+8.2f} {sm.sortino - bm.sortino:>+9.2f} "
          f"{(sm.max_drawdown - bm.max_drawdown) * 100:>+8.2f}% "
          f"{sm.calmar - bm.calmar:>+8.2f}")
    print(f"{'ALPHA vs composite':>22} {(sm.cagr - cm.cagr) * 100:>+8.2f}% "
          f"{sm.sharpe - cm.sharpe:>+8.2f} {sm.sortino - cm.sortino:>+9.2f} "
          f"{(sm.max_drawdown - cm.max_drawdown) * 100:>+8.2f}% "
          f"{sm.calmar - cm.calmar:>+8.2f}")

    yr = pd.concat(
        [
            yearly_returns(bh_test).rename("buy&hold"),
            yearly_returns(sr).rename("strategy"),
            yearly_returns(comp).rename("composite"),
        ],
        axis=1,
    )
    print("\nTEST yearly returns:")
    print(yr.to_string(float_format=lambda v: f"{v * 100:>8.2f}%"))
    pos = int((yr["strategy"] > 0).sum())
    print(f"\n  positive years: strategy {pos}/{len(yr)}  "
          f"buy&hold {int((yr['buy&hold'] > 0).sum())}/{len(yr)}  "
          f"composite {int((yr['composite'] > 0).sum())}/{len(yr)}")

    # ------------------------------------------------------------------ #
    hr("5. SANITY CHECKS (brief §6)")
    invested = float(sw.sum(axis=1).mean())
    print(f"1. Plausibility   CAGR {sm.cagr * 100:.2f}%  (40-50% is the unlevered ceiling)")
    print(f"2. Weight count   avg names {sd['avg_names']:.1f}  avg invested "
          f"{invested * 100:.1f}% (cash buffer 10% => ~90% max)")
    print(f"   top single-name weight max {float(sw.max(axis=1).max()) * 100:.2f}% "
          f"(cap 12%)")
    print(f"3. Signal liveness {slv['bar_frac'] * 100:.2f}% of (name,day) pairs long; "
          f"{slv['day_frac'] * 100:.2f}% breadth/day; "
          f"{slv['days_any'] * 100:.1f}% of days with >=1 name")
    gross = compute_metrics(sr + sm.cost_drag_annual / 244.0)
    print(f"4. Cost drag      {sm.cost_drag_annual * 100:.2f}%/y.  "
          f"gross CAGR {gross.cagr * 100:.2f}% vs net {sm.cagr * 100:.2f}%  -> "
          f"{'VIABLE gross, killed by costs' if gross.cagr > 0 and sm.cagr < 0 else 'gross and net same sign'}")

    print("\nSector exposure of the TEST book (fraction of invested capital):")
    for k, v in sorted(sector_exposure(sw).items(), key=lambda x: -x[1]):
        if v > 0.005:
            print(f"   {k:<10} {v * 100:>6.2f}%")

    # cost stress (GOAL.md §5 Gate 4)
    print("\nCost stress on the selected variant (GOAL.md §5 Gate 4):")
    for name, model in STRESS_MODELS.items():
        r2, _, m2, _ = run_variant(panel, next(v for v in VARIANTS if v.name == sel),
                                   TEST, CFG, cost_model=model)
        print(f"   {name:<16} CAGR {m2.cagr * 100:>7.2f}%  Sharpe {m2.sharpe:>6.2f}  "
              f"MaxDD {m2.max_drawdown * 100:>7.2f}%")

    store["test"] = {
        sel: {"cagr": sm.cagr, "sharpe": sm.sharpe, "maxdd": sm.max_drawdown,
              "calmar": sm.calmar, "turn": sm.annual_turnover,
              "drag": sm.cost_drag_annual, "names": sd["avg_names"]},
        "buyhold": {"cagr": bm.cagr, "sharpe": bm.sharpe, "maxdd": bm.max_drawdown},
        "composite": {"cagr": cm.cagr, "sharpe": cm.sharpe, "maxdd": cm.max_drawdown},
    }
    for v in VARIANTS:
        store["variants"].setdefault(v.name, {})
        _, mt, _, lvt, dt = te_results[v.name]
        store["variants"][v.name]["test"] = {
            "cagr": mt.cagr, "sharpe": mt.sharpe, "maxdd": mt.max_drawdown,
            "calmar": mt.calmar, "names": dt["avg_names"], "long": lvt["bar_frac"]}
        store["variants"][v.name]["train"] = {
            "cagr": tr_results[v.name][1].cagr,
            "sharpe": tr_results[v.name][1].sharpe,
            "maxdd": tr_results[v.name][1].max_drawdown,
            "names": float((tr_results[v.name][2] > 0).sum(axis=1).mean()),
            "long": tr_results[v.name][3]["bar_frac"]}

    (OUT / "results.json").write_text(json.dumps(store, indent=2, default=str))
    print(f"\nwrote {OUT / 'results.json'}")


if __name__ == "__main__":
    main()
