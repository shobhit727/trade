"""Step 03 — TEST window, touched once (2024-01-01 .. 2026-10-01).

The variant was selected on TRAIN in 02_train.py and is carried here UNCHANGED:

    SELECTED ON TRAIN = V3_w60_delta_rank
      TRAIN  CAGR 18.94%  Sharpe 0.81  MaxDD -34.33%  (best Sharpe AND best CAGR
             of the 5 declared variants)

Nothing below is used to choose anything. This is the only place TEST is read.
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
    VARIANTS,
    Variant,
    avg_names_held,
    buy_and_hold,
    composite_score,
    cost_drag_split,
    cost_model,
    delta_panel,
    liveness,
    load_panels,
    portfolio_config,
    random_control_score,
    row,
    run_backtest,
    signal_panel,
    strategy_score,
    window,
    yearly_returns,
)

SELECTED = Variant("V3_w60_delta_rank", 60, "delta_rank")
N_RANDOM = 20


def main() -> None:
    close, vol, symbols, _ = load_panels()
    px = window(close, TEST_START, TEST_END)
    cm = cost_model()
    cfg = portfolio_config()

    assert SELECTED in VARIANTS, "selected variant is not in the declared budget"

    print("=" * 118)
    print(f"TEST (OUT-OF-SAMPLE)  {TEST_START.date()} .. {TEST_END.date()}   "
          f"{len(px)} sessions")
    print(f"selected on TRAIN (ended {TRAIN_END.date()}), carried unchanged: "
          f"{SELECTED.name}")
    print("=" * 118)

    # ---- the strategy, net and gross
    score = strategy_score(close, vol, SELECTED)
    res = run_backtest(px, score.reindex(px.index), cm, cfg, "M")
    net, gross = cost_drag_split(close, score, TEST_START, TEST_END)
    live = liveness(delta_panel(close, vol, SELECTED.window), TEST_START, TEST_END)

    # ---- buy-and-hold, identical window, same cost stack
    bh = buy_and_hold(close, cm, TEST_START, TEST_END)

    # ---- nsealgo composite, identical window
    comp = run_backtest(px, composite_score(close).reindex(px.index), cm, cfg, "M")

    print("-" * 118)
    print("TEST RESULTS (net of full Indian delivery cost stack)")
    print(row("cumulative_delta", res.metrics,
              f"  names {avg_names_held(res):4.1f}"))
    print(row("BUY-AND-HOLD", bh["metrics"]))
    print(row("nsealgo composite", comp.metrics,
              f"  names {avg_names_held(comp):4.1f}"))

    m, b = res.metrics, bh["metrics"]
    print("-" * 118)
    print("COST DIAGNOSTIC")
    print(f"  gross CAGR (0 cost)  {gross.metrics.cagr * 100:6.2f}%")
    print(f"  net   CAGR (11.9bps) {net.metrics.cagr * 100:6.2f}%")
    print(f"  drag                 {(gross.metrics.cagr - net.metrics.cagr) * 100:6.2f} pp/yr"
          f"   (cost_drag_annual {m.cost_drag_annual * 100:.2f}%/y, "
          f"turnover {m.annual_turnover:.2f}x/y)")
    print(f"  signal liveness      {live['long_frac'] * 100:.1f}% of name-days long, "
          f"{live['avg_flagged_names']:.1f} names flagged/day, "
          f"{live['days_below_n_positions'] * 100:.1f}% of days <22 eligible")
    print(f"  avg names held       {avg_names_held(res):.1f}")

    print("-" * 118)
    print("YEARLY RETURNS (net)")
    for label, r in (("cumulative_delta", res.returns), ("BUY-AND-HOLD", bh["returns"]),
                     ("nsealgo composite", comp.returns)):
        yr = yearly_returns(r)
        print(f"  {label:<20} " + "  ".join(f"{k}:{v * 100:7.2f}%" for k, v in yr.items()))

    print("-" * 118)
    print("HEAD-TO-HEAD vs BUY-AND-HOLD (TEST)")
    dc = (m.cagr - b.cagr) * 100
    dd = (m.max_drawdown - b.max_drawdown) * 100
    print(f"  return:   strategy {m.cagr * 100:6.2f}% vs B&H {b.cagr * 100:6.2f}%  "
          f"-> {dc:+6.2f} pp {'BETTER' if dc > 0 else 'WORSE'}")
    print(f"  drawdown: strategy {m.max_drawdown * 100:6.2f}% vs B&H "
          f"{b.max_drawdown * 100:6.2f}%  -> {dd:+6.2f} pp "
          f"{'BETTER (shallower)' if dd > 0 else 'WORSE (deeper)'}")
    print(f"  sharpe:   strategy {m.sharpe:6.2f} vs B&H {b.sharpe:6.2f}")

    # ---- negative control
    print("-" * 118)
    print(f"NEGATIVE CONTROL — {N_RANDOM} random seeds, eligible-name count matched "
          f"per day to {SELECTED.name}")
    n_flagged = signal_panel(delta_panel(close, vol, SELECTED.window)).notna().sum(axis=1)
    rows = []
    for s in range(N_RANDOM):
        rc = run_backtest(px, random_control_score(n_flagged, px.index,
                                                  list(px.columns), s),
                          cm, cfg, "M")
        rows.append(rc.metrics)
    f = pd.DataFrame([m_.as_dict() for m_ in rows])
    print(f"  random    CAGR {f.cagr.mean() * 100:6.2f}% (sd {f.cagr.std() * 100:4.2f})  "
          f"Sharpe {f.sharpe.mean():5.2f} (sd {f.sharpe.std():4.2f})  "
          f"MaxDD {f.max_drawdown.mean() * 100:6.2f}%")
    print(f"  strategy  CAGR {m.cagr * 100:6.2f}%                     "
          f"Sharpe {m.sharpe:5.2f}              MaxDD {m.max_drawdown * 100:6.2f}%")
    print(f"  strategy beats {sum(1 for x in rows if m.sharpe > x.sharpe)}/{N_RANDOM} "
          f"random seeds on Sharpe, {sum(1 for x in rows if m.cagr > x.cagr)}/{N_RANDOM} "
          f"on CAGR")

    print("-" * 118)
    print("VERDICT")
    beat_bh = m.cagr > b.cagr
    beat_rnd = sum(1 for x in rows if m.sharpe > x.sharpe) > N_RANDOM / 2
    beat_comp = m.sharpe > comp.metrics.sharpe
    print(f"  beats buy-and-hold on CAGR : {beat_bh}")
    print(f"  beats random coin on Sharpe: {beat_rnd}")
    print(f"  beats nsealgo composite    : {beat_comp}")
    print(f"  => cumulative_delta on NSE makes money out-of-sample: "
          f"{'YES' if (beat_bh and beat_rnd) else 'NO'}")


if __name__ == "__main__":
    main()
