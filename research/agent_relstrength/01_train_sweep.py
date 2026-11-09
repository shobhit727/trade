"""Step 01 -- TRAIN sweep over the 5 declared variants, plus references.

Selection rule fixed in advance (REPORT.md section 1): highest TRAIN Sharpe,
ties broken by TRAIN Calmar then TRAIN CAGR. TEST is NOT touched here.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pandas as pd
from common import (
    COST,
    TRAIN,
    VARIANTS,
    build_score,
    build_signal,
    buy_and_hold,
    composite_score,
    panel,
    row,
    run,
    table,
)

OUT: dict = {"window": TRAIN, "cost_bps": None, "rows": [], "variants": {}}


def main() -> None:
    px = panel()
    OUT["cost_bps"] = float(COST.all_in_round_trip_bps(Decimal("100000")))

    n_train = int(((px.index >= pd.Timestamp(TRAIN[0], tz=px.index.tz))
                   & (px.index <= pd.Timestamp(TRAIN[1], tz=px.index.tz))).sum())
    print("=" * 96)
    print(f"STEP 01 -- TRAIN sweep {TRAIN[0]} -> {TRAIN[1]}  ({n_train} bars, "
          f"{px.shape[1]} names), net of {OUT['cost_bps']:.2f} bps/rotation")
    print("=" * 96)

    for v in VARIANTS:
        sig = build_signal(px, v["period"], v["threshold"])
        score = build_score(px, sig)
        res = run(px, score, TRAIN)
        m = res.metrics
        OUT["variants"][v["name"]] = {
            **v,
            **{k: float(x) for k, x in m.as_dict().items()},
            "avg_names": float(res.diag["avg_names"]),
            "avg_top_weight": float(res.diag["avg_top_weight"]),
            "n_rebalances": float(res.diag["n_rebalances"]),
            "cost_paid": float(res.costs_paid),
            "nan_score_rows": int(score.loc[score.index >= pd.Timestamp(
                TRAIN[0], tz=score.index.tz)].isna().all(axis=1).sum()),
        }

    # references -- same engine, same window
    comp = run(px, composite_score(px), TRAIN)
    OUT["composite"] = {**row("composite", comp.metrics, comp)}
    OUT["buy_hold"] = {**row("buy_and_hold", buy_and_hold(px, TRAIN))}

    print()
    print(table([OUT["composite"], OUT["buy_hold"]]) + "   <- references (TRAIN)")
    print()
    print(f"{'variant':<16}{'CAGR':>9}{'Sharpe':>8}{'Sortino':>8}{'MaxDD':>9}"
          f"{'Calmar':>8}{'Turn':>7}{'Cost/y':>8}{'Names':>7}")
    print("-" * 79)
    for v in VARIANTS:
        d = OUT["variants"][v["name"]]
        print(f"{v['name']:<16}{d['cagr'] * 100:>8.2f}%{d['sharpe']:>8.2f}"
              f"{d['sortino']:>8.2f}{d['max_drawdown'] * 100:>8.2f}%{d['calmar']:>8.2f}"
              f"{d['annual_turnover']:>7.2f}{d['cost_drag_annual'] * 100:>7.2f}%"
              f"{d['avg_names']:>7.1f}")

    # --- selection, by the rule declared before any run
    sel = max(
        OUT["variants"].items(),
        key=lambda kv: (kv[1]["sharpe"], kv[1]["calmar"], kv[1]["cagr"]),
    )
    OUT["selected"] = sel[0]
    print("\n  selection rule: max TRAIN Sharpe (tie: Calmar, then CAGR)")
    print(f"  SELECTED -> {sel[0]}  (Sharpe {sel[1]['sharpe']:.3f})")

    best = max(OUT["variants"].values(), key=lambda d: d["sharpe"])
    print(f"  TRAIN Sharpe range across variants: "
          f"{min(d['sharpe'] for d in OUT['variants'].values()):.3f} .. {best['sharpe']:.3f}")

    with open("train_result.json", "w") as fh:
        json.dump(OUT, fh, indent=2, default=float)
    print("\nwrote train_result.json")


if __name__ == "__main__":
    main()
