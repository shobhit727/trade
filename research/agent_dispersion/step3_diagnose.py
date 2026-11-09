"""Step 3: diagnostics for the negative result.

Four questions, each with one answer:

D1. Is the negative result an artifact of TRAIN-based selection, or does the whole
    declared grid lose out-of-sample? (report all 5 declared variants on TEST —
    selection is NOT changed, V5 remains the reported strategy)

D2. Does the dispersion *gate* add anything, or is the book just 126d momentum
    sitting on top of a filter that does nothing? (no-gate ablation)

D3. Are costs the cause, or is the signal itself the cause? (zero-cost control)

D4. Is the gate diluted in TEST specifically? (liveness time series)
"""

from __future__ import annotations

import json
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "research/agent_dispersion")

from signal import dispersion_score, dispersion_signal  # noqa: E402

import pandas as pd  # noqa: E402
from step2_run import (  # noqa: E402
    TEST_END,
    TEST_START,
    TRAIN_END,
    TRAIN_START,
    VARIANTS,
    buy_and_hold,
    slice_window,
)

from nsealgo.backtest.engine import PortfolioConfig, run_backtest  # noqa: E402
from nsealgo.costs import STRESS_MODELS, CostModel  # noqa: E402
from nsealgo.data.loader import load_universe  # noqa: E402

BASE_COST = CostModel(segment="delivery", slippage_bps=5)


def run_with_cost(panel, score_full, cost, lo, hi, mom_days=126):
    win = slice_window(panel, lo, hi)
    score = slice_window(score_full, lo, hi)
    res = run_backtest(win, score, cost, config=PortfolioConfig())
    m = res.metrics
    years = len(res.returns) / 244
    return {
        "cagr": m.cagr,
        "sharpe": m.sharpe,
        "maxdd": m.max_drawdown,
        "calmar": m.calmar,
        "turnover_yr": m.annual_turnover / years if years > 0 else 0.0,
        "cost_drag_annual": m.cost_drag_annual,
        "costs_paid": res.costs_paid,
        "avg_names": float((res.weights > 1e-6).sum(axis=1).mean()),
        "vol": m.volatility,
        "_returns": res.returns,
    }


def main() -> None:
    panel, symbols, _ = load_universe("data/nse")
    with open("research/agent_dispersion/results.json") as fh:
        prev = json.load(fh)
    sel = prev["selected"]
    print(f"selected on TRAIN (unchanged): {sel}\n")

    # ---- D1: full declared grid on TEST ---------------------------------
    print("=" * 96)
    print("D1. All 5 DECLARED variants on TEST (post-hoc reporting of the declared")
    print("    grid; selection is NOT revised — V5 stays the reported strategy)")
    print("=" * 96)
    print(f"{'label':<16}{'TRAIN Shp':>10}{'TEST CAGR':>11}{'TEST Shp':>10}"
          f"{'TEST MaxDD':>12}{'Names':>7}")
    grid = []
    for v in VARIANTS:
        long_sig, _ = dispersion_signal(
            panel, period=v["period"], entry=v["entry"]
        )
        score_full = dispersion_score(panel, long_sig, mom_days=126)
        d = run_with_cost(panel, score_full, BASE_COST, TEST_START, TEST_END)
        tr_shp = prev["train"][v["id"]]["sharpe"]
        grid.append((v, tr_shp, d))
        print(f"{v['id'] + ' p' + str(v['period']) + ' e' + str(v['entry']):<16}"
              f"{tr_shp:>10.2f}{d['cagr']:>10.2%}{d['sharpe']:>10.2f}"
              f"{d['maxdd']:>12.2%}{d['avg_names']:>7.1f}")

    bh = buy_and_hold(panel, TEST_START, TEST_END)
    print(f"{'buy&hold':<16}{'-':>10}{bh['cagr']:>10.2%}{bh['sharpe']:>10.2f}"
          f"{bh['maxdd']:>12.2%}{bh['avg_names']:>7.1f}")
    beaten = [v["id"] for v, _, d in grid if d["cagr"] > bh["cagr"]]
    print(f"\nvariants beating buy-and-hold on TEST return: {beaten or 'NONE'}")
    print("-> negative finding is a property of the STRATEGY FAMILY, not of one "
          "unlucky parameter choice.")

    # ---- D2: does the gate add anything? --------------------------------
    print()
    print("=" * 96)
    print("D2. Gate ablation: V5 gate vs NO gate (pure 126d momentum ranking).")
    print("    This is a diagnostic control, not a 6th tunable variant.")
    print("=" * 96)
    p = sel["period"]
    long_sig, _ = dispersion_signal(panel, period=p, entry=sel["entry"])
    gated = dispersion_score(panel, long_sig, mom_days=126)
    ungated = dispersion_score(panel, pd.DataFrame(True, index=panel.index,
                                                  columns=panel.columns),
                               mom_days=126)

    print(f"{'window':<26}{'gated CAGR':>12}{'gated Shp':>11}{'nogate CAGR':>13}"
          f"{'nogate Shp':>12}{'edge':>9}")
    for name, lo, hi in (("TRAIN 2016-2023", TRAIN_START, TRAIN_END),
                         ("TEST 2024-2026", TEST_START, TEST_END)):
        g = run_with_cost(panel, gated, BASE_COST, lo, hi)
        n = run_with_cost(panel, ungated, BASE_COST, lo, hi)
        edge = g["sharpe"] - n["sharpe"]
        print(f"{name:<26}{g['cagr']:>11.2%}{g['sharpe']:>11.2f}"
              f"{n['cagr']:>12.2%}{n['sharpe']:>12.2f}{edge:>9.2f}")
    print("-> positive 'edge' would mean the dispersion gate adds value on top of")
    print("   the momentum ranking. Zero or negative means the ranking does the work.")

    # ---- D3: is it costs or the signal? ----------------------------------
    print()
    print("=" * 96)
    print("D3. Cost stress on TEST (GOAL.md Gate 4 direction: strict costs up)")
    print("=" * 96)
    print(f"{'model':<20}{'round-trip bps':>16}{'CAGR':>10}{'Sharpe':>9}{'MaxDD':>10}")
    for name in ("zero_cost", "base", "double_slippage", "triple_slippage"):
        cm = STRESS_MODELS[name]
        d = run_with_cost(panel, gated, cm, TEST_START, TEST_END)
        rt = float(cm.all_in_round_trip_bps(100_000))
        print(f"{name:<20}{rt:>16.2f}{d['cagr']:>9.2%}{d['sharpe']:>9.2f}"
              f"{d['maxdd']:>10.2%}")
    print("-> if even zero_cost is weak, the signal is the problem, not the fees.")

    # ---- D4: gate liveness over time -------------------------------------
    print()
    print("=" * 96)
    print("D4. Gate liveness by year (fraction of (name,day) cells flagged long)")
    print("=" * 96)
    ann = long_sig.groupby(long_sig.index.year).mean().mean(axis=1)
    for y, v in ann.items():
        bar = "#" * int(v * 60)
        print(f"  {y}  {v:>6.2%} {bar}")
    tr_l = slice_window(long_sig.astype(float), TRAIN_START, TRAIN_END).mean().mean()
    te_l = slice_window(long_sig.astype(float), TEST_START, TEST_END).mean().mean()
    print(f"\n  TRAIN mean {tr_l:.2%}   TEST mean {te_l:.2%}")
    print("-> a gate that fires on most cells is not a filter; it is a near-no-op.")

    out = {
        "d1_variants_beating_bh_on_test": beaten,
        "d1_grid": [
            {"id": v["id"], "train_sharpe": s, "test_cagr": d["cagr"],
             "test_sharpe": d["sharpe"], "test_maxdd": d["maxdd"]}
            for v, s, d in grid
        ],
        "d4_liveness_by_year": {int(y): float(v) for y, v in ann.items()},
    }
    with open("research/agent_dispersion/diagnostics.json", "w") as fh:
        json.dump(out, fh, indent=2, default=float)
    print("\nwrote research/agent_dispersion/diagnostics.json")


if __name__ == "__main__":
    main()
