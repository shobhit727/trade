"""STAGE 1b — TRAIN ONLY diagnostics for the selected variant (V4).

Answers, before TEST is ever touched:
  * how much of the book is actually invested (cash drag from selectivity)?
  * is the TRAIN Sharpe distinguishable from a random signal with the same number
    of names long? (negative control, matched turnover + matched costs)
  * how does it compare with the nsealgo composite on TRAIN?

TEST remains untouched here.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from common import (
    TRAIN_END,
    TRAIN_START,
    atr_trailing_signal,
    buy_and_hold,
    composite,
    fmt_row,
    load_ohlc,
    momentum_score,
    random_control,
    run,
    summarise,
)

from nsealgo.backtest.metrics import yearly_returns

HERE = Path(__file__).resolve().parent
SELECTED = json.loads((HERE / "stage1_train.json").read_text())["selected"]
PARAMS = {"V1_period14_mult2.0": (14, 2.0), "V2_period14_mult1.5": (14, 1.5),
          "V3_period20_mult2.5": (20, 2.5), "V4_period55_mult2.0": (55, 2.0),
          "V5_period10_mult3.0": (10, 3.0)}


def main() -> None:
    close, high, low = load_ohlc()
    period, mult = PARAMS[SELECTED]
    print(f"selected on TRAIN: {SELECTED}  period={period} multiplier={mult}\n")

    sig = atr_trailing_signal(close, high, low, period, mult)
    score = momentum_score(close, sig)
    res = run(close, score, TRAIN_START, TRAIN_END)
    strat = summarise(res, close, SELECTED)

    print(fmt_row(strat))
    w = res.weights
    print(f"  invested: mean {w.sum(axis=1).mean() * 100:.1f}%  "
          f"median {w.sum(axis=1).median() * 100:.1f}%  "
          f"min {w.sum(axis=1).min() * 100:.1f}%  "
          f"days below 50% invested: {(w.sum(axis=1) < 0.5).mean() * 100:.1f}%")

    bench = buy_and_hold(close, TRAIN_START, TRAIN_END)
    print("\n" + fmt_row(bench))

    comp = run(close, composite(close), TRAIN_START, TRAIN_END)
    print("\n" + fmt_row(summarise(comp, close, "nsealgo_composite")))

    # ---- random control, matched name count per rebalance -------------------
    elig = (sig > 0).sum(axis=1)
    rb = elig.groupby(elig.index.tz_localize(None).to_period("M")).first()
    ctrl = random_control(close, rb, TRAIN_START, TRAIN_END, seeds=30)
    sh = np.array([c["sharpe"] for c in ctrl])
    cg = np.array([c["cagr"] for c in ctrl])
    dd = np.array([c["max_drawdown"] for c in ctrl])
    nm = np.array([c["avg_names"] for c in ctrl])
    print("\nRANDOM-SIGNAL CONTROL (TRAIN, 30 seeds, same #names long, same costs)")
    print(f"  CAGR    mean {cg.mean() * 100:6.2f}%  sd {cg.std() * 100:5.2f}%  "
          f"range [{cg.min() * 100:6.2f}%, {cg.max() * 100:6.2f}%]")
    print(f"  Sharpe  mean {sh.mean():6.2f}  sd {sh.std():5.2f}  "
          f"range [{sh.min():5.2f}, {sh.max():5.2f}]")
    print(f"  MaxDD   mean {dd.mean() * 100:6.2f}%")
    print(f"  names   mean {nm.mean():.1f}  (strategy {strat['avg_names']:.1f})")
    beats = float((sh > strat["sharpe"]).mean())
    print(f"  P(random Sharpe > strategy Sharpe) = {beats * 100:.0f}%  "
          f"-> strategy percentile = {(1 - beats) * 100:.0f}th")

    y = pd.DataFrame({
        "strategy": yearly_returns(res.returns),
        "equal_weight": yearly_returns(bench["returns"]),
        "composite": yearly_returns(comp.returns),
    })
    y["alpha_vs_ew"] = y["strategy"] - y["equal_weight"]
    print("\nTRAIN yearly returns:")
    print(y.to_string(float_format=lambda v: f"{v * 100:>7.2f}%"))

    (HERE / "stage1b_diag.json").write_text(json.dumps({
        "selected": SELECTED, "strategy": strat, "random": {
            "sharpe_mean": float(sh.mean()), "sharpe_sd": float(sh.std()),
            "cagr_mean": float(cg.mean()), "p_random_beats": beats,
        },
    }, indent=2, default=str))


if __name__ == "__main__":
    main()
