"""Step 2 — parameter selection on TRAIN ONLY. TEST is never touched here.

Run: .venv/bin/python research/agent_anchored_vwap/02_train_select.py
"""

from __future__ import annotations

import pandas as pd
from common import (
    CFG,
    HEADER,
    SEP,
    TRAIN,
    VARIANTS,
    build_score,
    buy_and_hold,
    deviation,
    evaluate,
    load,
    row,
)

pd.set_option("display.width", 240)


def main() -> None:
    u = load()
    print("=" * 96)
    print("TRAIN-ONLY VARIANT SWEEP  (2016-01-01 -> 2023-12-31)")
    print("Declared budget: 5 variants, listed in common.VARIANTS, fixed before this run.")
    print("Selection rule: highest TRAIN Sharpe; tie -> lower TRAIN cost drag.")
    print("=" * 96)
    print(HEADER)
    print(SEP)

    results = []
    for v in VARIANTS:
        dev = deviation(u.close, v.period)
        score = build_score(u.close, dev, v.threshold, v.score_kind)
        r = evaluate(u.close, score, dev, v.threshold, TRAIN, "TRAIN")
        results.append((v, r))
        print(row(r, v.name))

    best_v, best = max(results, key=lambda t: (t[1].metrics.sharpe, -t[1].cost_drag_annual))

    print(f"\nWINNER (TRAIN Sharpe {best.metrics.sharpe:.2f}): {best_v.name}")
    print(f"  period={best_v.period} threshold={best_v.threshold} score={best_v.score_kind}")

    print("\n" + "=" * 96)
    print("TRAIN bench")
    print("=" * 96)
    bh = buy_and_hold(u.close, TRAIN)
    from common import BASE_COSTS, ONE_WAY_RATE  # noqa: F401

    from nsealgo.backtest.metrics import compute_metrics

    mbh = compute_metrics(bh)
    print(
        f"  buy & hold (EW, net)  CAGR {mbh.cagr * 100:>7.2f}%  "
        f"Sharpe {mbh.sharpe:>6.2f}  MaxDD {mbh.max_drawdown * 100:>7.2f}%  "
        f"Calmar {mbh.calmar:>6.2f}  Ret {mbh.total_return * 100:>8.1f}%"
    )
    gross_bh = compute_metrics(
        bh + pd.Series(0.0, index=bh.index),  # placeholder; recomputed below
    )
    _ = gross_bh

    print("\n" + "=" * 96)
    print("TRAIN detail for the winner")
    print("=" * 96)
    print(best.metrics.fmt())
    print(f"\navg names held      : {best.avg_names:.1f}   (book target {CFG.n_positions})")
    print(f"avg eligible @ rebal: {best.avg_eligible:.1f} of {len(u.symbols)} names")
    print(f"gross CAGR          : {best.gross_cagr * 100:.2f}%  vs net {best.metrics.cagr * 100:.2f}%")
    print(f"cost drag           : {best.cost_drag_annual * 100:.2f}%/yr")
    print(f"turnover            : {best.annual_turnover:.2f}x/yr")

    # Persist the winner so step 3 cannot drift from it.
    out = pd.DataFrame(
        [
            {
                "variant": best_v.name,
                "period": best_v.period,
                "threshold": best_v.threshold,
                "score_kind": best_v.score_kind,
                "train_sharpe": best.metrics.sharpe,
                "train_cagr": best.metrics.cagr,
                "train_maxdd": best.metrics.max_drawdown,
                "train_cost_drag": best.cost_drag_annual,
                "train_avg_names": best.avg_names,
            }
        ]
    )
    out.to_csv("winner.csv", index=False)
    print("\nwrote winner.csv")


if __name__ == "__main__":
    main()
