"""Step 12 — TRAIN-only run of the 5 declared variants + pre-declared selection.

Selection happens strictly inside TRAIN. TEST is not opened by this script except to
assert that the selected winner's score panel is well-formed (no metric read).
"""

from __future__ import annotations

import json
import sys

sys.path.insert(0, "research/agent_cmf")

import pandas as pd
from cmflib import (
    SPECS,
    TRAIN0,
    TRAIN1,
    build_score,
    load_panels,
    metrics_on,
    row,
    run_window,
    show,
)

from nsealgo.backtest.metrics import yearly_returns
from nsealgo.factors.core import build_composite_score


def main() -> None:
    lo, hi = TRAIN0, TRAIN1
    closes, highs, lows, vols = load_panels()
    print(f"TRAIN window {lo.date()} -> {hi.date()}   symbols {closes.shape[1]}   "
          f"bars {int(((closes.index >= lo) & (closes.index <= hi)).sum())}")

    rows, panels = [], {}
    for spec in SPECS:
        name = spec[0]
        score, mask = build_score(closes, closes, highs, lows, vols, spec)
        res = run_window(closes, score, lo, hi)
        m = metrics_on(res, lo, hi)
        frac = float((mask.loc[lo:hi] > 0).sum().sum() / mask.loc[lo:hi].notna().sum().sum())
        yr = yearly_returns(res.returns.loc[lo:hi])
        rows.append(row(name, m, res, frac_bars_flagged=round(frac, 4),
                        pos_years_pct=round(float((yr > 0).mean()) * 100, 1)))
        panels[name] = (score, mask, res, m, yr)
        print(f"  {name:24s} CAGR {m.cagr * 100:7.2f}%  Sh {m.sharpe:6.3f}  "
              f"MaxDD {m.max_drawdown * 100:7.2f}%  Cal {m.calmar:5.3f}  "
              f"names {res.diag['avg_names']:5.1f}  drag {m.cost_drag_annual * 100:5.2f}%/y")

    # ---- TRAIN benchmark: the project's own composite
    comp = build_composite_score(closes)
    rc = run_window(closes, comp, lo, hi)
    mc = metrics_on(rc, lo, hi)
    rows.append(row("BENCH_nsealgo_composite", mc, rc))
    print(f"  {'BENCH_nsealgo_composite':24s} CAGR {mc.cagr * 100:7.2f}%  "
          f"Sh {mc.sharpe:6.3f}  MaxDD {mc.max_drawdown * 100:7.2f}%  "
          f"Cal {mc.calmar:5.3f}  names {rc.diag['avg_names']:5.1f}")

    df = pd.DataFrame(rows)
    show(df, "TRAIN (2016-01-01 -> 2023-12-31) — all 5 declared variants + benchmark\n"
             "net of 21.92 bps round trip (all_in delivery, 5 bps slippage)")

    # ---- pre-declared selection: max TRAIN Sharpe among V1..V5 only
    cands = df[~df.variant.str.startswith("BENCH")].sort_values(
        ["sharpe", "calmar"], ascending=[False, False])
    winner = cands.iloc[0]["variant"]
    runner_up = cands.iloc[1]["variant"]
    print("\nPRE-DECLARED SELECTION (max TRAIN Sharpe, tie-break Calmar then MaxDD):")
    print(f"  winner    = {winner}   (Sharpe {cands.iloc[0]['sharpe']:.3f})")
    print(f"  runner-up = {runner_up}   (Sharpe {cands.iloc[1]['sharpe']:.3f})")
    print(f"  margin    = {cands.iloc[0]['sharpe'] - cands.iloc[1]['sharpe']:+.3f} Sharpe")

    show(cands[["variant", "sharpe", "calmar", "maxdd_pct", "cagr_pct"]],
         "SELECTION TABLE (TRAIN only)")

    with open("research/agent_cmf/v_train_results.json", "w") as f:
        json.dump({"rows": rows, "winner": winner, "runner_up": runner_up}, f, indent=2)
    print("\nwrote research/agent_cmf/v_train_results.json")

    # ---- calendar years of the winner, for context
    score, mask, res, m, yr = panels[winner]
    print("\nwinner calendar-year TRAIN returns: "
          + ", ".join(f"{int(y)} {v * 100:+.1f}%" for y, v in yr.items()))

    # ---- is the winner meaningfully distinguishable from the composite?
    print(f"\nTRAIN Sharpe  winner {m.sharpe:.3f}  vs composite {mc.sharpe:.3f}  "
          f"-> delta {m.sharpe - mc.sharpe:+.3f}")


if __name__ == "__main__":
    main()
