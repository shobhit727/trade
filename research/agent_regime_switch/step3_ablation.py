"""STEP 3 — attribution. Where did the return come from?

Decomposes the book into: the strategy's gate (time-series trend state), the
cross-sectional ranking, and raw market beta. Reported on TRAIN *and* TEST for every
comparison, so no attribution rests on a single window.

This is ablation of the already-frozen selected variant. It cannot change it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness import (  # noqa: E402, PLC0415
    TEST_END,
    TEST_START,
    TRAIN_END,
    TRAIN_START,
    beta_alpha,
    buy_and_hold,
    cost_model,
    gate_only_score,
    load,
    long_flag,
    portfolio_config,
    rank_only_score,
    run_backtest,
    strategy_score,
    window,
)

ABLATION_SEEDS = list(range(20))


def exposure(sc: pd.DataFrame, px: pd.DataFrame, seed: int) -> pd.DataFrame:
    """A *pure random* gate: same fraction of names eligible per day, random which."""
    rng = np.random.default_rng(10_000 + seed)
    noise = pd.DataFrame(rng.random(px.shape), index=px.index, columns=px.columns)
    order = noise.rank(axis=1, ascending=False)
    n_keep = long_flag(px, 200).sum(axis=1)
    return (1.0 - noise).where(order.le(n_keep, axis=0))


def main() -> None:
    panel, _, _ = load()
    period = 200
    cm, cfg = cost_model(), portfolio_config()

    books = {
        "GATE + RANK (selected)": strategy_score(panel, period),
        "GATE + RANDOM RANK": gate_only_score(panel, period, 1),
        "RANK ONLY (no gate)": rank_only_score(panel, period),
        "RANDOM GATE + RANDOM RANK": exposure(None, panel, 0),
        "BUY-AND-HOLD": None,
    }

    for label, (start, end, _wname) in {
        "TRAIN": (TRAIN_START, TRAIN_END, "TRAIN"),
        "TEST": (TEST_START, TEST_END, "TEST"),
    }.items():
        px = window(panel, start, end)
        bh = buy_and_hold(panel, cm, start, end)
        print(f"\n=== {label}  {px.index[0].date()} -> {px.index[-1].date()} ===")
        print(f"{'book':<28}{'CAGR':>9}{'Sharpe':>9}{'MaxDD':>9}{'Calmar':>8}"
              f"{'Beta':>7}{'Alpha/y':>9}{'Names':>7}{'Turn':>7}")
        for name, sc in books.items():
            if sc is None:
                m, beta, alpha, nm = bh["metrics"], 1.0, 0.0, 48.0
                beta, alpha, _ = beta_alpha(bh["returns"], panel, start, end)
                m, nm = bh["metrics"], 48.0
                turn = m.annual_turnover
            else:
                r = run_backtest(px, sc.reindex(px.index), cm, cfg, rebalance="M")
                m = r.metrics
                beta, alpha, _ = beta_alpha(r.returns, panel, start, end)
                nm, turn = r.diag["avg_names"], m.annual_turnover
            print(f"{name:<28}{m.cagr * 100:>8.2f}%{m.sharpe:>9.2f}"
                  f"{m.max_drawdown * 100:>8.2f}%{m.calmar:>8.2f}"
                  f"{beta:>7.2f}{alpha * 100:>+8.2f}%{nm:>7.1f}{turn:>6.2f}x")

    # ---- how much of the gap is simply "hold less of the market"? ------- #
    print("\n=== is it just under-investment? TEST ===")
    px = window(panel, TEST_START, TEST_END)
    mkt = px.pct_change(fill_method=None).fillna(0.0).mean(axis=1)
    from harness import compute_metrics  # noqa: PLC0415

    for target_beta in (0.6, 0.7, 0.8):
        daily = (target_beta * mkt).fillna(0.0)
        m = compute_metrics(daily, (1.0 + daily).cumprod())
        print(f"  constant-beta {target_beta:.1f} static: CAGR {m.cagr * 100:>6.2f}%  "
              f"Sharpe {m.sharpe:>6.2f}  MaxDD {m.max_drawdown * 100:>7.2f}%")

    # ---- cash timing: is the gate in the market at the right times? ---- #
    print("\n=== cash timing. Fraction of the universe the gate holds, by year (TEST) ===")
    px = window(panel, TEST_START, TEST_END)
    flag = long_flag(panel, period).loc[px.index]
    for y, g in flag.groupby(flag.index.year):
        m = px.loc[g.index].pct_change(fill_method=None).fillna(0.0).mean(axis=1)
        h = g.to_numpy().mean()
        print(f"  {y}: held {h * 100:>5.1f}% of names;  equal-weight market that year "
              f"{(m.mean()) * 244 * 100:>+6.1f}%")
    print("  (If the gate is doing real work, it should be holding LESS into the "
          "down years and MORE into the up years.)")


if __name__ == "__main__":
    main()
