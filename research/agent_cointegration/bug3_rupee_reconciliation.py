"""Bug-3, airtight version: reconcile ``run_backtest.costs_paid`` against a rupee bill.

``bug3_cost_probe.py`` showed the engine charges exactly 0.5x the cost model. That
relied on reading the bps algebra. This version removes the algebra entirely: it takes
the *actual* weight changes the engine produced, prices every resulting rupee buy and
rupee sell through ``CostModel.cost`` line by line, and compares that hand bill to
``costs_paid``.

If the two disagree by exactly 2x, the finding is independent of any convention
argument about what "basis points of turnover" means.
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


def hand_bill(held: pd.DataFrame) -> tuple[float, pd.DataFrame]:
    """Price every rupee buy/sell implied by the weight path, through CostModel."""
    rows = []
    prev = pd.Series(0.0, index=held.columns)
    for dt, row in held.iterrows():
        delta = row - prev
        for sym, dw in delta.items():
            if abs(dw) < 1e-9:
                continue
            side = "BUY" if dw > 0 else "SELL"
            notional = _d(abs(dw) * CAP)
            rows.append(dict(date=dt.date(), symbol=sym, side=side,
                             weight=abs(dw), notional=float(notional),
                             rupees=float(CM.cost(side, _d(1), notional).total)))
        prev = row
    b = pd.DataFrame(rows)
    return float(b.rupees.sum()), b


def main() -> None:
    idx = pd.date_range("2024-01-31", periods=130, freq="B", tz="Asia/Kolkata")
    px = pd.DataFrame(
        {"AAA": np.linspace(100, 130, 130), "BBB": np.linspace(200, 260, 130)},
        index=idx,
    )
    score = pd.DataFrame(
        {"AAA": np.where(idx < idx[62], 1.0, -1.0),
         "BBB": np.where(idx < idx[62], -1.0, 1.0)},
        index=idx,
    )
    cfg = PortfolioConfig(n_positions=2, max_weight=1.0, max_sector_weight=1.0,
                          cash_buffer=0.0, turnover_budget=1.0, max_names=2)
    res = run_backtest(px, score, CM, cfg, rebalance="M")
    held = res.weights

    total_rupees, bill = hand_bill(held)

    print("=" * 88)
    print("RUPEE-LEVEL RECONCILIATION of run_backtest.costs_paid")
    print("=" * 88)
    print(f"book value (initial_capital)   Rs {CAP:>14,.2f}")
    print(f"engine costs_paid              Rs {res.costs_paid:>14,.2f}")
    print(f"hand bill via CostModel.cost   Rs {total_rupees:>14,.2f}")
    print(f"engine / hand bill             {res.costs_paid / total_rupees:>14.4f}")
    print(f"shortfall                      Rs {total_rupees - res.costs_paid:>14,.2f}")

    print("\nleg-by-leg (every weight change the engine actually executed):")
    print(f"  {'date':<12} {'sym':<5} {'side':<5} {'wgt':>8} {'notional Rs':>15} {'cost Rs':>10}")
    for _, r in bill.iterrows():
        print(f"  {str(r['date']):<12} {r['symbol']:<5} {r['side']:<5} "
              f"{r['weight']:>8.4f} {r['notional']:>15,.2f} {r['rupees']:>10,.2f}")
    print(f"{'':<50}{'TOTAL':>10} {total_rupees:>10,.2f}")

    # Same test at the reference per-position size, so the rupee bill is directly
    # comparable to the cost model's own calibration.
    print(f"\nsanity: cost of ONE Rs{REF_POSITION_NOTIONAL:,} round trip "
          f"(buy+sell) = Rs "
          f"{CM.cost('BUY', _d(1), _d(REF_POSITION_NOTIONAL)).total + CM.cost('SELL', _d(1), _d(REF_POSITION_NOTIONAL)).total:,.2f}")

    ratio = res.costs_paid / total_rupees
    if abs(ratio - 0.5) < 1e-3:
        print("\nFINDING CONFIRMED, and it does not depend on any bps convention:")
        print("  run_backtest charges EXACTLY HALF of what CostModel.cost() bills")
        print("  for the trades the engine actually made.")
    else:
        print(f"\nratio {ratio:.4f} -- NOT the expected 0.5; investigate further.")


if __name__ == "__main__":
    main()
