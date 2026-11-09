"""TRAIN-window sweep over the 5 declared variants (see PLAN.md).

TRAIN = 2016-01-01 .. 2023-12-31. TEST is not touched here.

Scores are built on the FULL panel (all point-in-time, so this is not lookahead) and
then the *price* window handed to `run_backtest` is sliced to TRAIN. That matters:
slicing the panel first would leave `momentum_6m` NaN for its first 126 bars and
throw away the first ~4 monthly rebalances for no reason.

Selection rule, fixed in advance: best TRAIN Sharpe, ties broken by best TRAIN MaxDD.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from dema_lib import (  # noqa: E402
    TEST_END,
    TEST_START,
    TRAIN_END,
    TRAIN_START,
    backtest,
    buy_and_hold,
    dema_distance_panel,
    score_from_gate,
    score_pure_dema,
    table,
)

from nsealgo.data.loader import load_universe  # noqa: E402

VARIANTS = [
    ("V1", 20, "gate+mom126"),
    ("V2", 50, "gate+mom126"),
    ("V3", 100, "gate+mom126"),
    ("V4", 200, "gate+mom126"),
    ("V5", 20, "pure_dema"),
]


def main() -> None:
    panel, symbols, _ = load_universe("data/nse")
    train_px = panel.loc[TRAIN_START:TRAIN_END]

    print(f"TRAIN window {TRAIN_START.date()} -> {TRAIN_END.date()} "
          f"({len(train_px)} bars, {len(symbols)} symbols)\n")

    _, bm = buy_and_hold(train_px)
    print("TRAIN BENCHMARK")
    print("  " + table("equal-weight buy & hold", bm))

    print("\nSIGNAL LIVENESS on TRAIN (fraction of name-days above DEMA)")
    live: dict[int, float] = {}
    for _, p, _ in VARIANTS:
        dist = dema_distance_panel(train_px, p)
        live[p] = float((dist > 0).to_numpy().mean())
        n_above = int((dist > 0).to_numpy().sum())
        print(f"  period={p:<4} long {live[p] * 100:5.1f}% of name-days "
              f"({n_above:,} cells)")

    rows = []
    print("\n" + "=" * 100)
    print("TRAIN RESULTS (net of full Indian delivery stack: 11.9 bps round trip + 10 bps slippage)")
    print("=" * 100)
    for name, period, score_kind in VARIANTS:
        sc = score_from_gate(panel, period) if score_kind == "gate+mom126" \
            else score_pure_dema(panel, period)
        res = backtest(train_px, sc)
        m = res.metrics
        # how much of the universe is buyable on a typical rebalance day
        rb_days = res.diag["n_rebalances"]
        eligible = float(sc.loc[train_px.index].notna().to_numpy().mean())
        rows.append(
            {
                "variant": name,
                "period": period,
                "score": score_kind,
                "sharpe": m.sharpe,
                "cagr": m.cagr,
                "maxdd": m.max_drawdown,
                "calmar": m.calmar,
                "total": m.total_return,
                "turnover": m.annual_turnover,
                "drag": m.cost_drag_annual,
                "avg_names": res.diag["avg_names"],
                "eligible_frac": eligible,
                "live_frac": live[period],
                "rebalances": rb_days,
                "costs_paid": res.costs_paid,
            }
        )
        print(f"\n{name}  period={period}  score={score_kind}")
        print("  " + table("TRAIN", m))
        print(f"    avg names held {res.diag['avg_names']:.1f} | "
              f"eligible (buyable) names {eligible * len(symbols):.1f}/{len(symbols)} "
              f"| rebalances {rb_days}")

    df = pd.DataFrame(rows)
    print("\n" + "=" * 100)
    print("TRAIN SUMMARY (sorted by Sharpe)")
    print("=" * 100)
    cols = ["variant", "period", "score", "cagr", "sharpe", "maxdd", "calmar",
            "turnover", "drag", "avg_names", "live_frac"]
    show = df.sort_values("sharpe", ascending=False)[cols].copy()
    for c in ("cagr", "maxdd", "drag", "live_frac"):
        show[c] = (show[c] * 100).round(2)
    print(show.to_string(index=False, float_format=lambda v: f"{v:>8.3f}"))

    best = df.sort_values(["sharpe", "maxdd"], ascending=[False, False]).iloc[0]
    print(f"\nSELECTED ON TRAIN: {best['variant']} (period={int(best['period'])}, "
          f"score={best['score']}, TRAIN Sharpe {best['sharpe']:.2f}, "
          f"TRAIN CAGR {best['cagr'] * 100:.2f}%)")

    out = HERE / "train_results.json"
    out.write_text(json.dumps(rows, indent=2))
    (HERE / "selected.json").write_text(
        json.dumps(
            {"variant": best["variant"], "period": int(best["period"]),
             "score": best["score"]}, indent=2
        )
    )
    print(f"\nwrote {out.name} and selected.json")
    print(f"\nTEST window is {TEST_START.date()} -> {TEST_END.date()} and has NOT been "
          f"touched in this script.")


if __name__ == "__main__":
    main()
