"""Bug-3, transparent: reproduce the engine's own arithmetic step by step.

Instead of inferring turnover from the ffilled ``weights``, this recomputes exactly
what ``run_backtest`` computes — same ``build_rebalance_weights``, same
``apply_turnover_budget``, same ``tgt`` matrix — and prints each quantity. Nothing is
inferred from the ffill, so the one-way vs total-turnover question is settled
directly on the objects the engine actually trades off.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from nsealgo.backtest.engine import (  # noqa: E402
    REF_POSITION_NOTIONAL,
    PortfolioConfig,
    _d,
    _rebalance_dates,
    apply_turnover_budget,
    build_rebalance_weights,
    run_backtest,
)
from nsealgo.costs import CostModel  # noqa: E402


def main() -> None:
    cm = CostModel(segment="delivery", slippage_bps=5)
    allin = float(cm.all_in_round_trip_bps(_d(REF_POSITION_NOTIONAL)))
    rate = allin / 10_000.0
    print(f"all_in_round_trip_bps = {allin}  ->  rate = {rate}")
    print("  engine.py:411-412  rate = all_in / 1e4, where all_in is bps of "
          "TOTAL turnover\n")

    # One symbol, fully long, then flat at the end. Guarantees a real target book.
    idx = pd.date_range("2024-01-31", periods=400, freq="B", tz="Asia/Kolkata")
    px = pd.DataFrame({"AAA": np.linspace(100, 200, 400)}, index=idx)
    score = pd.DataFrame(1.0, index=idx, columns=["AAA"])
    score.iloc[-1] = 0.0  # go to cash on the final bar

    cfg = PortfolioConfig(n_positions=1, max_weight=1.0, max_sector_weight=1.0,
                          cash_buffer=0.0, turnover_budget=1.0, max_names=1)

    res = run_backtest(px, score, cm, cfg, rebalance="M", initial_capital=100_000.0)
    print(f"engine diag: {res.diag}")
    print(f"engine costs_paid = Rs {res.costs_paid:,.4f}\n")

    # Rebuild the engine's tgt exactly as run_backtest does.
    rets = px.pct_change(fill_method=None).fillna(0.0)
    vol = rets.rolling(cfg.vol_lookback, min_periods=20).std()
    rb = [d for d in _rebalance_dates(px.index, "M") if d in score.index][1:]
    tgt_raw = build_rebalance_weights(score.loc[rb], rb, vol.loc[rb], cfg)
    tgt = tgt_raw.copy()
    for i in range(len(tgt)):
        prev = tgt.iloc[i - 1] if i else None
        tgt.iloc[i] = apply_turnover_budget(tgt_raw.iloc[i], prev,
                                            cfg.turnover_budget, cfg.max_names)

    print("target book at each rebalance:")
    for d, row in tgt.iterrows():
        print(f"   {d.date()}  {dict(row.round(4))}")
    print()

    turn = ((tgt - tgt.shift(1).fillna(0.0)).abs().sum(axis=1) / 2.0)
    turn = turn[turn > 0]
    one_way = float(turn.sum())
    total_turn = 2.0 * one_way

    print(f"engine's turnover_by_date (one-way, /2) = {dict(turn.round(6))}")
    print(f"one-way turnover total     {one_way:.6f}")
    print(f"total turnover (= 2x)     {total_turn:.6f}")
    print(f"\nengine charge  = one_way x rate x equity = {one_way:.6f} x {rate} "
          f"= {one_way * rate:.6f} normalised")
    print(f"                   engine costs_paid / 1e5 = "
          f"{res.costs_paid / 100_000.0:.6f}   (match: "
          f"{abs(one_way * rate - res.costs_paid / 100_000.0) < 1e-9})\n")
    print(f"correct charge = total_turn x rate        = "
          f"{total_turn * rate:.6f} normalised")
    print(f"\nratio engine/correct = {one_way / total_turn:.6f}  "
          f"(expect 0.5 -> engine charges HALF)")
    print(f"\nengine bills {one_way / total_turn * allin:.2f} bps of total turnover "
          f"instead of {allin:.2f} bps.")


if __name__ == "__main__":
    main()
