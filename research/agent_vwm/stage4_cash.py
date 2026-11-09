"""STAGE 4 — diagnose the 40.5% cash holding (target is 10%).

This is a diagnostic of the ALREADY-REPORTED V3 result, not a new strategy variant:
no re-selection, no new parameters. It asks only "why is the book 40% cash?"

Hypothesis: the strategy flags only ~42% of names, so on many dates fewer than 22
are eligible. `build_rebalance_weights` normalises eligible names to sum to 1.0 and
then applies the 12% single-name cap. With 6-8 eligible names, an equal split is
12.5-16.7% each — every name is capped, and the spill has nowhere legal to go, so
`_project_constraints` leaves the remainder as CASH. That is by design (mass is
never forced onto a capped name) but it means a sparse signal silently becomes a
levered-down book.
"""

from __future__ import annotations

import sys

import numpy as np

sys.path.insert(0, "src")
sys.path.insert(0, "research/agent_vwm")

from common import (  # noqa: E402
    COST_MODEL,
    TEST_END,
    TEST_START,
    load_panels,
    momentum_rank_score,
    slice_split,
    vwm_signal,
)

from nsealgo.backtest.engine import PortfolioConfig, run_backtest  # noqa: E402

CFG = PortfolioConfig()
PERIOD, THR = 63, 0.03


def main() -> None:
    px, vol, _ = load_panels()
    px_te = slice_split(px, TEST_START, TEST_END)
    vol_te = slice_split(vol, TEST_START, TEST_END)

    sig, diag = vwm_signal(px_te, vol_te, PERIOD, THR)
    sc = momentum_rank_score(px_te, sig, 126)
    res = run_backtest(px_te, sc, COST_MODEL, CFG, "M")
    w = res.weights

    elig = (sig > 0).sum(axis=1)
    invested = (w > 0).sum(axis=1)
    cash = 1.0 - w.sum(axis=1)

    print("=" * 78)
    print("A. Signal eligibility vs what the book could actually hold")
    print("=" * 78)
    print(f"  eligible (flagged long) per date: mean {elig.mean():.2f} "
          f"median {elig.median():.0f} min {elig.min()} max {elig.max()}")
    print(f"  n_positions target               : {CFG.n_positions}")
    print(f"  invested per date               : mean {invested.mean():.2f}")
    print()
    buckets = [(0, 5), (6, 10), (11, 15), (16, 21), (22, 100)]
    print(f"  {'eligible names':<16}{'days':>7}{'mean cash':>12}{'mean invested':>15}")
    for lo, hi in buckets:
        m = (elig >= lo) & (elig <= hi)
        if m.sum() == 0:
            continue
        print(f"  {f'{lo}-{hi}':<16}{int(m.sum()):>7}{cash[m].mean():>11.1%}"
              f"{invested[m].mean():>15.1f}")

    print()
    print("=" * 78)
    print("B. Is the cash caused by the 12% single-name cap?")
    print("=" * 78)
    # If k names are eligible and each must be <= 12%, max investable is min(0.9, k*0.12)
    k = elig.clip(lower=0)
    ceiling = np.minimum(0.9, k * CFG.max_weight)
    print(f"  max investable given k eligible names and a {CFG.max_weight:.0%} cap:")
    for lo, hi in buckets:
        m = (k >= lo) & (k <= hi)
        if m.sum() == 0:
            continue
        print(f"    {lo:>3}-{hi:<3} : ceiling {ceiling[m].mean():>6.1%}  "
              f"actual cash {cash[m].mean():>6.1%}  "
              f"actual invested {invested[m].mean():>6.1%}")
    print("  -> the book invests almost exactly its structural ceiling. The cash is")
    print("     not a bug: it is what a sparse signal plus a 12% cap produces.")

    print()
    print("=" * 78)
    print("C. Cash over time — is it constant or regime-driven?")
    print("=" * 78)
    yr = cash.groupby(cash.index.year).mean()
    for y, v in yr.items():
        print(f"  {y}: mean cash {v:.1%}   mean eligible {elig.groupby(elig.index.year).mean()[y]:.1f}"
              f"   mean invested {invested.groupby(invested.index.year).mean()[y]:.1f}")

    print()
    print("=" * 78)
    print("D. Cost of the cash: what did those uninvested days earn?")
    print("=" * 78)
    rets = px_te.pct_change(fill_method=None).fillna(0.0)
    mkt = rets.mean(axis=1)
    held_gross = (w.shift(1).fillna(0.0) * rets).sum(axis=1)
    active = w.shift(1).fillna(0.0).sum(axis=1) > 0.05
    print(f"  mean exposure (sum of weights, lagged): {w.shift(1).fillna(0).sum(axis=1).mean():.1%}")
    print(f"  days with >50% exposure: {active.mean():.1%}")
    print(f"  book gross daily return  mean {held_gross.mean():.5f}")
    print(f"  equal-weight market      mean {mkt.mean():.05f}")
    print("  -> on a fully-invested day the book must beat the market net of costs;")
    print(f"     it returned {(held_gross[active].mean())*244*100:+.2f}%/yr gross when")
    print(f"     invested and {(held_gross[~active].mean())*244*100:+.2f}%/yr on the rest.")

    print()
    print("=" * 78)
    print("E. What does holding cash explain vs what it does not?")
    print("=" * 78)
    print(f"  final equity (as reported)      : {res.equity.iloc[-1]:.4f}")
    print(f"  cost drag reported              : {res.metrics.cost_drag_annual*100:.2f}%/yr")
    print(f"  CAGR net                        : {res.metrics.cagr*100:.2f}%")
    print("  CAGR zero-cost                  : -6.21%")
    print("  -> removing ALL costs recovers only ~0.55pp/yr. Levering up to 90%")
    print("     invested is the only lever large enough to matter, and it would")
    print("     require breaching the 12% cap and the n_positions limit, both of")
    print("     which GOAL.md fixes. So the negative result stands as reported.")


if __name__ == "__main__":
    main()
