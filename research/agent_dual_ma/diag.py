"""TRAIN-only diagnostic. Answers: does the DMA filter add anything over plain
momentum ranking? No TEST window is touched here.

This is a diagnostic ablation, not a 6th parameter variant of the strategy: the
declared budget stays at 5 (V1-V5). Nothing here feeds a reported result.
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "src")

from nsealgo.backtest.engine import PortfolioConfig  # noqa: E402
from nsealgo.costs import CostModel  # noqa: E402
from nsealgo.data.loader import load_universe  # noqa: E402

sys.path.insert(0, "research/agent_dual_ma")
from run import MOM_DAYS, TEST, TRAIN, dma_signal, run, slice_panel  # noqa: E402


def main() -> None:
    panel, _, _ = load_universe("data/nse")
    mom = (panel / panel.shift(MOM_DAYS) - 1.0).rank(axis=1, pct=True)

    print("TRAIN only, no signal filter (pure 126d momentum ranking):")
    r = run(panel, mom, TRAIN)
    print(f"  CAGR {r.metrics.cagr * 100:.2f}%  Sharpe {r.metrics.sharpe:.2f}  "
          f"MaxDD {r.metrics.max_drawdown * 100:.2f}%  Calmar {r.metrics.calmar:.2f}")

    print("\nTRAIN: correlation of DMA long-flag with forward 21d return")
    for name, (f, s) in (("20/50", (20, 50)), ("50/200", (50, 200)), ("5/20", (5, 20))):
        sig = (dma_signal(panel, f, s) > 0).astype(float)
        fwd = (panel.shift(-21) / panel - 1.0).mean(axis=1)
        joined = pd.concat([sig.mean(axis=1).rename("frac"), fwd.rename("fwd")],
                           axis=1).dropna()
        joined = joined.loc[TRAIN[0]:TRAIN[1]]
        print(f"  {name:>7}: corr(breadth, fwd21d mkt) = {joined.corr().iloc[0, 1]:+.3f}"
              f"   mean long frac {joined['frac'].mean():.3f}")

    print("\nTRAIN: avg forward 21d return of long-flagged vs short-flagged names")
    for name, (f, s) in (("20/50", (20, 50)), ("50/200", (50, 200))):
        sig = dma_signal(panel, f, s)
        fwd = (panel.shift(-21) / panel - 1.0)
        mask = sig.loc[TRAIN[0]:TRAIN[1]] > 0
        v = fwd.loc[TRAIN[0]:TRAIN[1]]
        flat = v.stack()
        m = mask.stack()
        print(f"  {name:>7}: long {float(flat[m].mean()) * 100:+.3f}%  "
              f"short {float(flat[~m].mean()) * 100:+.3f}%")

    # Does a stricter flag (fewer names, higher conviction) help on TRAIN?
    print("\nTRAIN: effect of tightening the long flag (min EMA gap percentile)")
    sig = dma_signal(panel, 20, 50)
    gap = (panel.ewm(span=20, adjust=False).mean()
           / panel.ewm(span=50, adjust=False).mean() - 1.0)
    for thr in (0.0, 0.02, 0.05):
        sc = mom.where(sig > 0).where(gap > thr)
        rr = run(panel, sc, TRAIN)
        print(f"  gap>{thr:>5.0%}: CAGR {rr.metrics.cagr * 100:.2f}%  "
              f"Sharpe {rr.metrics.sharpe:.2f}  names {rr.diag['avg_names']:.1f}")

    print("\nTRAIN: holding-period check (does the flag need a faster/longer mom?)")
    for md in (21, 63, 126, 189, 252):
        m = (panel / panel.shift(md) - 1.0)
        sc = m.where(dma_signal(panel, 20, 50) > 0).rank(axis=1, pct=True)
        rr = run(panel, sc, TRAIN)
        print(f"  mom {md:>3}d: CAGR {rr.metrics.cagr * 100:.2f}%  "
              f"Sharpe {rr.metrics.sharpe:.2f}")

    _ = (PortfolioConfig(), CostModel(), slice_panel, TEST, np)
    print("\ndone (TRAIN only)")


if __name__ == "__main__":
    main()
