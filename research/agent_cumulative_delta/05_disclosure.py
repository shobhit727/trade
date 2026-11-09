"""Step 05 — POST-HOC DISCLOSURE ONLY. Not a selection.

Runs all 5 declared variants on the TEST window so the reader can see whether V3 was a
lucky or unlucky TRAIN pick. The frozen selection (`V3_w60_delta_rank`, written in
REPORT.md §8 before TEST was read) does NOT change based on anything printed here.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (  # noqa: E402
    TEST_END,
    TEST_START,
    TRAIN_END,
    TRAIN_START,
    VARIANTS,
    avg_names_held,
    buy_and_hold,
    cost_model,
    load_panels,
    portfolio_config,
    row,
    run_backtest,
    window,
)


def main() -> None:
    close, vol, _, _ = load_panels()
    px = window(close, TEST_START, TEST_END)
    tr = window(close, TRAIN_START, TRAIN_END)
    cm = cost_model()
    cfg = portfolio_config()
    bh = buy_and_hold(close, cm, TEST_START, TEST_END)

    from common import composite_score  # noqa: PLC0415

    comp = run_backtest(px, composite_score(close).reindex(px.index), cm, cfg, "M")
    print("=" * 118)
    print("POST-HOC DISCLOSURE — all 5 declared variants on TEST. NOT a selection;")
    print("V3_w60_delta_rank was frozen on TRAIN (report section 8) and stands.")
    print("=" * 118)
    print(row("BUY-AND-HOLD (TEST)", bh["metrics"]))
    print(row("nsealgo composite", comp.metrics, f"  names {avg_names_held(comp):4.1f}"))

    print("-" * 118)
    print(f"{'variant':<20} {'TRAIN Shrp':>10} {'TRAIN CAGR':>11} | "
          f"{'TEST Shrp':>10} {'TEST CAGR':>10} {'TEST MaxDD':>11} {'names':>6} "
          f"{'live%':>6}")
    rows = []
    for v in VARIANTS:
        from common import strategy_score  # noqa: PLC0415

        score = strategy_score(close, vol, v)
        r_tr = run_backtest(tr, score.reindex(tr.index), cm, cfg, "M")
        r_te = run_backtest(px, score.reindex(px.index), cm, cfg, "M")
        rows.append((v.name, r_tr.metrics, r_te.metrics, avg_names_held(r_te)))
        print(f"{v.name:<20} {r_tr.metrics.sharpe:>10.2f} {r_tr.metrics.cagr * 100:>10.2f}% "
              f"| {r_te.metrics.sharpe:>10.2f} {r_te.metrics.cagr * 100:>9.2f}% "
              f"{r_te.metrics.max_drawdown * 100:>10.2f}% {avg_names_held(r_te):>6.1f} "
              f"{'':>6}")

    print("-" * 118)
    print("TRAIN-RANK vs TEST-RANK of the 5 variants (does the TRAIN pick generalise?)")
    tr_rank = [n for n, _, _, _ in sorted(rows, key=lambda t: -t[1].sharpe)]
    te_rank = [n for n, _, _, _ in sorted(rows, key=lambda t: -t[2].sharpe)]
    for i, (a, b) in enumerate(zip(tr_rank, te_rank, strict=True), 1):
        print(f"  #{i}  TRAIN {a:<20} TEST {b}")
    print(f"  TRAIN #1 was {tr_rank[0]}; on TEST it ranks "
          f"#{te_rank.index(tr_rank[0]) + 1} of 5 by Sharpe.")
    sp = pd.Series([t[1].sharpe for t in rows], index=[t[0] for t in rows])
    se = pd.Series([t[2].sharpe for t in rows], index=[t[0] for t in rows])
    print(f"  rank correlation TRAIN vs TEST Sharpe: "
          f"{sp.rank().corr(se.rank(), method='pearson'):+.3f} (n=5, not significant)")
    print(f"  every variant's TEST Sharpe below its TRAIN Sharpe: "
          f"{bool((se < sp).all())}")

    print("-" * 118)
    print("COMPARISON TO BENCHMARKS (TEST), all 5 variants")
    b, c = bh["metrics"], comp.metrics
    for name, _, m, _ in rows:
        print(f"  {name:<20} vs B&H {m.cagr * 100 - b.cagr * 100:+7.2f}pp   "
              f"vs composite {m.cagr * 100 - c.cagr * 100:+7.2f}pp   "
              f"Sharpe gap vs B&H {m.sharpe - b.sharpe:+6.2f}")
    print("-" * 118)
    print(f"  B&H TEST MaxDD {b.max_drawdown * 100:.2f}%   "
          f"composite {c.max_drawdown * 100:.2f}%   "
          f"best variant {min(t[2].max_drawdown for t in rows) * 100:.2f}%")
    print(f"  TRAIN_END = {TRAIN_END.date()}  TEST_END = {TEST_END.date()}  "
          f"({len(px)} sessions)")


if __name__ == "__main__":
    main()
