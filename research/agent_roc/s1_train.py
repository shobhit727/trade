"""Step 1 — TRAIN selection. All 5 declared variants on 2016-01-01..2023-12-31.

TEST is NOT touched here.
"""

from __future__ import annotations

import json

from common import (
    CFG,
    COST,
    ENGINE_SHA,
    HEADER,
    TRAIN_END,
    TRAIN_START,
    build_score,
    load,
    roc_signal,
    row,
    run_backtest,
)

#: name -> (period, threshold, rebalance, rank_by)
VARIANTS: dict[str, tuple[int, float, str, str]] = {
    "V1_base": (10, 0.01, "M", "mom126"),
    "V2_tight": (20, 0.01, "M", "mom126"),
    "V3_wide": (10, 0.0, "M", "mom126"),
    "V4_week": (10, 0.01, "W", "mom126"),
    "V5_raw": (10, 0.01, "M", "roc10"),
}

RESULTS: dict[str, dict] = {}


def main() -> None:
    panel, symbols, _ = load()
    train = panel.loc[TRAIN_START:TRAIN_END]

    print("=" * 78)
    print(f"TRAIN SELECTION  {TRAIN_START.date()} -> {TRAIN_END.date()}   "
          f"engine {ENGINE_SHA}")
    print("=" * 78)
    print(f"panel {train.shape[0]} bars x {train.shape[1]} symbols")
    print()

    print(HEADER)
    for name, (p, thr, reb, rank) in VARIANTS.items():
        # signal + score built on the FULL panel, sliced after (no warm-up dead time)
        sig = roc_signal(panel, p, thr)
        score = build_score(panel, sig, rank).loc[TRAIN_START:TRAIN_END]
        res = run_backtest(train, score, COST, CFG, rebalance=reb)
        m = res.metrics
        RESULTS[name] = {
            "period": p,
            "threshold": thr,
            "rebalance": reb,
            "rank_by": rank,
            "cagr": m.cagr,
            "sharpe": m.sharpe,
            "max_dd": m.max_drawdown,
            "calmar": m.calmar,
            "turnover": m.annual_turnover,
            "cost_drag": m.cost_drag_annual,
            "avg_names": res.diag["avg_names"],
            "rt_bps": res.diag["round_trip_bps"],
            "engine_sha": res.engine_sha,
        }
        print(row(name, m, {"names": f"{res.diag['avg_names']:.1f}"}))
    print()

    # -------- reference book on TRAIN (comparator, NOT selectable) --------------
    mom = (panel / panel.shift(126) - 1.0).loc[TRAIN_START:TRAIN_END]
    res_mom = run_backtest(train, mom.rank(axis=1, pct=True), COST, CFG)
    print("TRAIN comparators (never selected on):")
    print(row("momentum126_only", res_mom.metrics,
              {"names": f"{res_mom.diag['avg_names']:.1f}"}))
    print()

    winner = max(VARIANTS, key=lambda n: (RESULTS[n]["sharpe"], RESULTS[n]["calmar"]))
    print("-" * 78)
    print(f"WINNER (frozen on TRAIN, selection rule = highest TRAIN Sharpe, tie->Calmar):"
          f"  {winner}")
    print(f"  {VARIANTS[winner]}")
    print(f"  TRAIN Sharpe {RESULTS[winner]['sharpe']:.3f}  Calmar "
          f"{RESULTS[winner]['calmar']:.3f}")
    print("-" * 78)

    RESULTS["_winner"] = winner
    RESULTS["_engine_sha"] = ENGINE_SHA
    with open("train_results.json", "w") as f:
        json.dump(RESULTS, f, indent=2, default=str)
    print("wrote train_results.json")


if __name__ == "__main__":
    main()
