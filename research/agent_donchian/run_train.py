"""TRAIN-window run over the 5 declared variants. Selects one, by the rule
frozen in PARAMETER_BUDGET.md: highest TRAIN Sharpe, tie-break Calmar.

This script never touches TEST.

Usage: .venv/bin/python research/agent_donchian/run_train.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (  # noqa: E402
    TEST_END,
    TEST_START,
    TRAIN_END,
    TRAIN_START,
    backtest,
    breakout_signal,
    build_composite_score,
    build_score,
    equal_weight_bh,
    literal_signal,
    liveness,
    load_all,
    metrics_table,
    slice_panel,
)

VARIANTS = [
    ("literal_p20", "literal", 20),
    ("breakout_p20", "breakout", 20),
    ("breakout_p55", "breakout", 55),
    ("breakout_p10", "breakout", 10),
    ("breakout_p100", "breakout", 100),
]


def main() -> None:
    close, high, low, symbols, _ = load_all()
    tr = (str(TRAIN_START.date()), str(TRAIN_END.date()))
    p_tr = slice_panel(close, *tr)

    print(f"TRAIN window {tr[0]} -> {tr[1]}  ({len(p_tr)} bars, {len(symbols)} names)")
    print("CostModel(delivery, 5bps) | PortfolioConfig() defaults | monthly rebalance\n")

    rows, results = [], {}
    for label, kind, period in VARIANTS:
        sig = (
            literal_signal(close, high, low, period)
            if kind == "literal"
            else breakout_signal(close, high, low, period)
        )
        sc = build_score(sig, close)
        res = backtest(p_tr, sc.loc[p_tr.index])
        frac_long, frac_short, frac_flat = liveness(sig, *tr)
        rows.append({"label": label, "metrics": res.metrics, "avg_names": res.diag["avg_names"]})
        results[label] = {
            "period": period,
            "kind": kind,
            "cagr": res.metrics.cagr,
            "sharpe": res.metrics.sharpe,
            "maxdd": res.metrics.max_drawdown,
            "calmar": res.metrics.calmar,
            "turnover": res.metrics.annual_turnover,
            "cost_drag": res.metrics.cost_drag_annual,
            "avg_names": res.diag["avg_names"],
            "total_return": res.metrics.total_return,
            "live_long": frac_long,
            "live_short": frac_short,
            "live_flat": frac_flat,
        }
        print(f"  ran {label:<14} CAGR {res.metrics.cagr * 100:>7.2f}%  "
              f"Sharpe {res.metrics.sharpe:>6.2f}  long {frac_long:>6.2%}")

    print("\n" + "=" * 82)
    print("TRAIN results (2016-01-01 -> 2023-12-31), net of full delivery costs")
    print("=" * 82)
    print(metrics_table(rows))

    # ---- reference points on TRAIN
    bm_rets, bm_m, bm_cost = equal_weight_bh(p_tr)
    comp = backtest(p_tr, build_composite_score(p_tr).reindex(p_tr.index))
    print("\n" + metrics_table([
        {"label": "REFERENCE buy&hold", "metrics": bm_m, "avg_names": len(symbols)},
        {"label": "REFERENCE composite", "metrics": comp.metrics,
         "avg_names": comp.diag["avg_names"]},
    ]))
    print(f"\n  buy&hold one-time round-trip cost charged on day 1: {bm_cost:.4%}")

    # ---- selection: highest TRAIN Sharpe, tie-break Calmar
    best = max(
        results.items(),
        key=lambda kv: (round(kv[1]["sharpe"], 6), round(kv[1]["calmar"], 6)),
    )
    print("\n" + "=" * 82)
    print(f"SELECTED (rule: max TRAIN Sharpe, tie-break Calmar): {best[0]}")
    print("=" * 82)

    out = {
        "window": "TRAIN",
        "variants": results,
        "selected": best[0],
        "buy_hold": {"cagr": bm_m.cagr, "sharpe": bm_m.sharpe,
                     "maxdd": bm_m.max_drawdown, "calmar": bm_m.calmar},
        "composite": {"cagr": comp.metrics.cagr, "sharpe": comp.metrics.sharpe,
                      "maxdd": comp.metrics.max_drawdown,
                      "calmar": comp.metrics.calmar},
        "test_window_declaration": [str(TEST_START.date()), str(TEST_END.date())],
    }
    Path(__file__).with_name("train_results.json").write_text(json.dumps(out, indent=2))
    print("\nwrote research/agent_donchian/train_results.json")


if __name__ == "__main__":
    main()
