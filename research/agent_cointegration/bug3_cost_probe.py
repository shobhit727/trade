"""Bug-3 probe: does ``run_backtest`` charge the right amount of cost?

``CostModel.round_trip_bps`` is documented as **basis points of TOTAL turnover** — a
round trip on ``notional`` produces ``2 * notional`` of turnover, and the code
divides by exactly that (costs.py:198-217). So a charge must be
``rate * total_turnover``.

``run_backtest`` computes

    turnover_by_date = (tgt - tgt_prev).abs().sum(axis=1) / 2.0   # engine.py:415-419
    cost_amt         = turn_t * eq * rate                        # engine.py:432

i.e. it charges ``rate`` times *one-way* turnover (half of total turnover). For a
complete rotation that is ``1.0 * rate`` where the cost model says ``2.0 * rate``.

This script settles it empirically with an independent hand-computed bill, so the
finding does not rest on reading the algebra alone.
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
    run_backtest,
)
from nsealgo.costs import CostModel  # noqa: E402

CAP = 2_100_000.0
CM = CostModel(segment="delivery", slippage_bps=5)
RATE = float(CM.all_in_round_trip_bps(_d(REF_POSITION_NOTIONAL))) / 10_000.0


def main() -> None:
    print(f"REF_POSITION_NOTIONAL = {REF_POSITION_NOTIONAL:,}")
    print(f"all_in_round_trip_bps = {CM.all_in_round_trip_bps(_d(REF_POSITION_NOTIONAL))} "
          f"-> rate {RATE:.8f} per unit of TOTAL turnover (model's own definition)")
    print(f"initial_capital       = {CAP:,.0f}\n")

    # Two symbols, 6 months, so exactly two monthly rebalances with a full rotation
    # between them: long AAA, then long only BBB.
    idx = pd.date_range("2024-01-31", periods=130, freq="B", tz="Asia/Kolkata")
    px = pd.DataFrame(
        {"AAA": np.linspace(100, 130, 130), "BBB": np.linspace(200, 260, 130)},
        index=idx,
    )
    score = pd.DataFrame(
        {"AAA": np.where(idx < idx[62], 1.0, -1.0), "BBB": np.where(idx < idx[62], -1.0, 1.0)},
        index=idx,
    )
    # Disable every constraint so the book is a clean 100% rotation between names.
    cfg = PortfolioConfig(
        n_positions=2, max_weight=1.0, max_sector_weight=1.0,
        cash_buffer=0.0, turnover_budget=1.0, max_names=2,
    )
    res = run_backtest(px, score, CM, cfg, rebalance="M")
    held = res.weights
    tgt_changes = (held.diff().abs().sum(axis=1) / 2.0)
    tgt_changes.iloc[0] = float(held.iloc[0].sum())
    tgt_changes = tgt_changes[tgt_changes > 0]

    one_way = float(tgt_changes.sum())
    total_turn = 2.0 * one_way

    print(f"rebalances that changed the book: {len(tgt_changes)}")
    for d, t in tgt_changes.items():
        print(f"   {d.date()}  one-way turnover {t:.4f}")
    print(f"\none-way turnover total    {one_way:.4f}")
    print(f"total turnover (x2)       {total_turn:.4f}")

    engine_cost = res.costs_paid
    engine_cost_norm = engine_cost / CAP  # back to normalised-equity units
    model_one_way = one_way * RATE
    model_total = total_turn * RATE

    print("\n--- independent bill -------------------------------------------")
    print(f"engine costs_paid                     Rs {engine_cost:>12,.2f}"
          f"   (normalised {engine_cost_norm:.6f})")
    print(f"model, charged on ONE-WAY turnover    Rs {model_one_way * CAP:>12,.2f}"
          f"   (normalised {model_one_way:.6f})")
    print(f"model, charged on TOTAL turnover      Rs {model_total * CAP:>12,.2f}"
          f"   (normalised {model_total:.6f})")
    print(f"engine / total-turnover model         {engine_cost_norm / model_total:.4f}")

    # Line-by-line cross-check on a single leg, independent of any engine algebra.
    leg = CM.cost("BUY", _d(1), _d(REF_POSITION_NOTIONAL))
    leg2 = CM.cost("SELL", _d(1), _d(REF_POSITION_NOTIONAL))
    print(f"\nsingle Rs{REF_POSITION_NOTIONAL:,} round trip, itemised by the model itself:")
    print(f"   buy  total Rs {leg.total}")
    print(f"   sell total Rs {leg2.total}")
    print(f"   combined Rs  {leg.total + leg2.total} on 2x notional turnover "
          f"-> {RATE * 10_000:.2f} bps")

    verdict = abs(engine_cost_norm - model_total) < 1e-9
    print("\nVERDICT: engine matches the model's own bps-of-TOTAL-turnover "
          f"definition: {verdict}")
    if not verdict:
        short = model_total - engine_cost_norm
        print(f"  engine UNDERCHARGES by {short:.6f} normalised "
              f"({short / model_total * 100:.1f}% of the correct bill)")
        print(f"  = {short * CAP:,.0f} rupees over this tiny 6-month 2-name test.")
        print("\n  Consequence: every nsealgo backtest pays HALF the intended cost.")
        print("  This is NOT a rounding issue -- it is a factor of 2 on the whole")
        print("  cost stack, and it inflates every CAGR in the project.")


if __name__ == "__main__":
    main()
