"""TRAIN-window sweep for the cointegration strategy.

PARAMETER BUDGET — declared before any result was read, 5 distinct variants.
(This list was first written in the interrupted run's ``train_sweep.py``; adopted
unchanged and re-verified here. TRAIN-only — TEST is not touched by this file.)

    V1  W=252  entry=1.0  rule=depth      (long window, shallow trigger)
    V2  W=252  entry=1.5  rule=depth      (long window, deeper trigger)
    V3  W=126  entry=1.0  rule=depth
    V4  W=126  entry=1.5  rule=depth
    V5  W=126  entry=1.0  rule=momentum   (brief's ranking, same signal)

Rationale: the catalog default is a ~300-bar buffer with entry=1.0. A 126-bar window
is the shortest that still spans a quarter; 252 is one year. entry in {1.0, 1.5}
brackets the catalog default. V5 isolates the score-ranking rule against V3.

Indicators are warmed up on bars *before* the window opens (``build_score_window``),
so the window does not start blind for 126 bars. Nothing outside TRAIN is touched.

Both cost bases are reported (see REPORT.md Bug-3):
  corrected  21.92 bps of total turnover  <- HEADLINE, the intended stack
  as-is      10.96 bps                     <- what run_backtest really charges
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from coinlib import (  # noqa: E402
    BASE_COSTS,
    TRAIN_END,
    TRAIN_START,
    build_score_window,
    composite_score,
    evaluate,
    fmt,
    panel,
    random_score_like,
)

TRAIN = (TRAIN_START, TRAIN_END)
VARIANTS = [
    ("V1 W252 e1.0 depth", 252, 1.0, "depth"),
    ("V2 W252 e1.5 depth", 252, 1.5, "depth"),
    ("V3 W126 e1.0 depth", 126, 1.0, "depth"),
    ("V4 W126 e1.5 depth", 126, 1.5, "depth"),
    ("V5 W126 e1.0 moment", 126, 1.0, "momentum"),
]


def main() -> None:
    full = panel()
    print(f"TRAIN window {TRAIN_START.date()} -> {TRAIN_END.date()}")
    print(f"panel {full.shape[0]} bars x {full.shape[1]} symbols, "
          f"{full.index[0].date()} -> {full.index[-1].date()}\n")

    rows = []
    for label, w, e, rule in VARIANTS:
        px, score = build_score_window(TRAIN, w, e, rule)
        cor = evaluate(label, px, score)
        asi = evaluate(label, px, score, cost_model=BASE_COSTS)
        print(f"{label}")
        print(f"  corrected  {fmt(cor.metrics)}")
        print(f"  as-is      {fmt(asi.metrics)}")
        print(f"  live {cor.liveness * 100:5.2f}%  avg names {cor.diag['avg_names']:5.1f}  "
              f"exposure {cor.diag['avg_exposure'] * 100:5.1f}%  "
              f"cost-gap {(asi.metrics.cagr - cor.metrics.cagr) * 100:5.2f} pp/yr")
        rows.append(dict(variant=label, cagr=cor.metrics.cagr,
                         sharpe=cor.metrics.sharpe, maxdd=cor.metrics.max_drawdown,
                         calmar=cor.metrics.calmar, turn=cor.metrics.annual_turnover,
                         drag=cor.metrics.cost_drag_annual, live=cor.liveness,
                         names=cor.diag["avg_names"], exposure=cor.diag["avg_exposure"],
                         total=cor.metrics.total_return,
                         cagr_asis=asi.metrics.cagr, sharpe_asis=asi.metrics.sharpe))

    print("\nCONTROLS (TRAIN, corrected costs)")
    px, s3 = build_score_window(TRAIN, 126, 1.0, "depth")
    comp = evaluate("composite", px, composite_score(full).loc[px.index])
    print(f"  composite   {fmt(comp.metrics)}  names {comp.diag['avg_names']:.1f}  "
          f"exposure {comp.diag['avg_exposure'] * 100:.1f}%")

    from coinlib import buy_and_hold
    bh = buy_and_hold(px)
    print(f"  buy&hold    {fmt(bh)}")

    for seed in (1, 2, 3):
        rc = evaluate(f"rand{seed}", px, random_score_like(s3, seed))
        print(f"  random s{seed}  {fmt(rc.metrics)}  names {rc.diag['avg_names']:.1f}  "
              f"exposure {rc.diag['avg_exposure'] * 100:.1f}%  live {rc.liveness * 100:.1f}%")

    print("\n--- TRAIN summary (corrected costs, the headline basis) ---")
    tab = pd.DataFrame(rows)
    print(tab.to_string(index=False, float_format=lambda x: f"{x:,.4f}"))
    (Path(__file__).parent / "_train_results.csv").write_text(tab.to_csv(index=False))

    best = tab.loc[tab.sharpe.idxmax(), "variant"]
    print(f"\nSELECTED ON TRAIN BY SHARPE: {best}")


if __name__ == "__main__":
    main()
