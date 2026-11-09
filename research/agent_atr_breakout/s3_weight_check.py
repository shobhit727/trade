"""Sanity check — is the average held-name count legitimate, or residual accumulation?

The brief flags "48 names instead of ~22" as a bug that has happened here before.
`PortfolioConfig` sets n_positions=22 but max_names=30 (the engine thins blended
weights to at most max_names material positions, because blending toward a new
target never reaches zero on a dropped name). So 22-30 is the legitimate band.
This checks that the count is stable over time and bounded, rather than growing.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "src")

import signal as sigmod  # noqa: E402

import common  # noqa: E402
import s2_train_select as s2  # noqa: E402

from nsealgo.backtest.engine import PortfolioConfig, run_backtest  # noqa: E402
from nsealgo.costs import CostModel  # noqa: E402


def main() -> None:
    o, h, lo, c, syms = common.load()
    tr0, tr1 = s2.TRAIN
    te0, te1 = s2.TEST

    for tag, period, mult in s2.VARIANTS[:3]:
        sig = sigmod.signal_panel(h, lo, c, period, mult)
        score = s2.build_score(c, sig)
        for label, idx in (("TRAIN", (tr0, tr1)), ("TEST", (te0, te1))):
            res = run_backtest(c.loc[slice(*idx)], score.loc[slice(*idx)],
                               CostModel(segment="delivery", slippage_bps=5),
                               PortfolioConfig(), rebalance="M")
            n = (res.weights > 0).sum(axis=1)
            per_year = n.groupby(n.index.year).mean()
            growth = "RISING" if per_year.iloc[-1] > per_year.iloc[0] + 3 else "flat"
            print(f"{tag} {label:>5} names: mean={n.mean():5.1f} max={n.max():3d} "
                  f"first3y={per_year.iloc[:3].mean():5.1f} "
                  f"last3y={per_year.iloc[-3:].mean():5.1f} trend={growth} "
                  f"max_top_wt={res.diag['avg_top_weight'] * 100:.2f}%")
        print()

    print("Cap sanity: max_weight=12%, max_sector=25%, cash_buffer=10%")
    res = run_backtest(c.loc[slice(*idx)], score.loc[slice(*idx)],
                       CostModel(segment="delivery", slippage_bps=5),
                       PortfolioConfig(), rebalance="M")
    w = res.weights
    print(f"  observed max single-name weight : {w.max().max() * 100:.3f}%")
    print(f"  observed min daily weight sum   : {w.sum(axis=1).min() * 100:.2f}%")
    print(f"  observed max daily weight sum   : {w.sum(axis=1).max() * 100:.2f}%")


if __name__ == "__main__":
    main()
