"""Step 2: TRAIN backtest for all 5 declared variants. TEST is not touched.

Selection rule fixed in DECLARED_BUDGET.md: highest TRAIN Sharpe net of costs wins.
"""

from __future__ import annotations

import pandas as pd
from common import (
    BUILDERS,
    COST,
    PORTFOLIO,
    TRAIN_END,
    TRAIN_START,
    load_panel,
    run_backtest,
    table,
)
from step1_signal_diag import VARIANTS


def slice_train(panel: pd.DataFrame) -> pd.DataFrame:
    return panel.loc[(panel.index >= TRAIN_START) & (panel.index <= TRAIN_END)]


def main() -> None:
    panel, symbols, _ = load_panel()
    train = slice_train(panel)
    print(f"TRAIN {TRAIN_START.date()} .. {TRAIN_END.date()}   bars={len(train)}")
    print(f"costs: {COST.all_in_round_trip_bps(__import__('decimal').Decimal('100000'))} bps "
          "all-in round trip\n")

    rows, invested, detail = [], [], []
    for label, con, period, thr in VARIANTS:
        score = BUILDERS[con](train, period, thr)
        r = run_backtest(train, score, COST, PORTFOLIO, rebalance="M")
        held = r.weights
        # Cash is the crux here: a sparse gate meets a 12% single-name cap and
        # the book simply cannot fill up.
        inv = float(held.sum(axis=1).mean())
        top = float(held.max(axis=1).mean())
        rows.append((label, r.metrics))
        invested.append((label, r.diag["avg_names"], inv, top))
        detail.append((label, r))
        print(f"{label:<24} avg_names={r.diag['avg_names']:>5.1f}  "
              f"invested={inv:>6.1%}  maxw={top:>5.2%}  "
              f"CAGR={r.metrics.cagr * 100:>7.2f}%  Sharpe={r.metrics.sharpe:>6.2f}")

    print()
    print(table(rows))
    print("\n--- why: the gate is sparse, the cap is 12% ---")
    print(f"{'variant':<24}{'avg names':>10}{'invested':>11}{'max w':>8}")
    for label, n, inv, top in invested:
        print(f"{label:<24}{n:>10.1f}{inv:>10.1%}{top:>8.2%}")

    # Reference points on the same TRAIN window, same engine.
    print("\n--- TRAIN reference points ---")
    from nsealgo.factors.core import build_composite_score

    for name, sc in (
        ("nsealgo_composite", build_composite_score(train)),
        ("rank_all_names_by_mom6m", (train / train.shift(126) - 1.0)),
    ):
        r = run_backtest(train, sc, COST, PORTFOLIO, rebalance="M")
        m = r.metrics
        print(f"{name:<28} CAGR {m.cagr * 100:>7.2f}%  Sharpe {m.sharpe:>6.2f}  "
              f"MaxDD {m.max_drawdown * 100:>7.2f}%  invested "
              f"{float(r.weights.sum(axis=1).mean()):>6.1%}")

    # Buy-and-hold on TRAIN, identical window, same 22-name universe as B&H in step3.
    from common import buy_and_hold_result

    bh = buy_and_hold_result(train, sorted(symbols)[:22], "buy_and_hold (EW 22)")
    m = bh["metrics"]
    print(f"{'buy_and_hold (EW 22)':<28} CAGR {m.cagr * 100:>7.2f}%  Sharpe {m.sharpe:>6.2f}  "
          f"MaxDD {m.max_drawdown * 100:>7.2f}%")

    best = max(rows, key=lambda x: x[1].sharpe)
    print(f"\nSELECTED ON TRAIN (max Sharpe): {best[0]}  Sharpe={best[1].sharpe:.2f}")


if __name__ == "__main__":
    main()
