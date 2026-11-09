"""Step 5 — the definitive test: is the TEST edge over buy-and-hold real, or noise?

Daily returns do not overlap, so a daily t-stat on the excess series is honest (unlike
the 21-day forward-return grid, which needs blocking). We also block-bootstrap the
CAGR difference in 21-day blocks, and re-state the TRAIN picture for contrast.

Run: .venv/bin/python research/agent_anchored_vwap/05_significance.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from common import (
    TEST,
    TRAIN,
    VARIANTS,
    build_score,
    buy_and_hold,
    deviation,
    full_backtest,
    load,
)

pd.set_option("display.width", 240)

RNG = np.random.default_rng(20261007)
N_BOOT = 20_000
BLOCK = 21


def daily_excess_test(sr: pd.Series, br: pd.Series, label: str) -> tuple[float, float]:
    """t-stat on the daily excess return series (non-overlapping, so valid)."""
    ex = (sr - br).dropna()
    t = float(ex.mean() / ex.std(ddof=1) * np.sqrt(len(ex)))
    print(
        f"  {label:<14} daily excess {ex.mean() * 1e4:>7.2f} bps  "
        f"ann. {ex.mean() * 244 * 100:>6.2f}%  t={t:>6.2f}  "
        f"({'significant' if abs(t) > 1.96 else 'NOT significant'} at 5%)"
    )
    return t, float(ex.mean() * 244)


def block_bootstrap(sr: pd.Series, br: pd.Series, label: str) -> None:
    """Stationary-ish block bootstrap on the excess series -> CI for annualised alpha.

    Blocks of 21 trading days (one month) preserve the monthly rebalance and the
    momentum autocorrelation that a naive i.i.d. bootstrap would destroy.
    """
    ex = (sr - br).dropna().to_numpy()
    n = len(ex)
    n_blocks = int(np.ceil(n / BLOCK))
    max_start = n - BLOCK + 1
    means = np.empty(N_BOOT)
    for i in range(N_BOOT):
        starts = RNG.integers(0, max_start, size=n_blocks)
        idx = (starts[:, None] + np.arange(BLOCK)[None, :]).ravel()[:n]
        means[i] = ex[idx].mean() * 244
    lo, hi = np.percentile(means, [5, 95])
    point = ex.mean() * 244
    print(
        f"  {label:<14} point {point * 100:>+6.2f}%/yr   "
        f"90% CI [{lo * 100:>+6.2f}%, {hi * 100:>+6.2f}%]   "
        f"P(alpha<=0) = {float((means <= 0).mean()) * 100:.1f}%"
    )


def main() -> None:
    u = load()
    close = u.close
    wvar = next(v for v in VARIANTS if v.name == "V1_p50_t2.0_mom")
    dev = deviation(close, wvar.period)
    score = build_score(close, dev, wvar.threshold, wvar.score_kind)

    print("=" * 96)
    print("IS THE TEST EDGE REAL?  strategy minus buy-and-hold, net of costs")
    print("=" * 96)

    # One backtest over full history, sliced per window — the book enters each window
    # already invested, and the parameter set is never refit at the boundary. Booting
    # the engine separately per window (and three times per window) was both slow and
    # needlessly easy to get inconsistent.
    full = full_backtest(close, score).returns
    bh_full = buy_and_hold(close, (close.index[0], close.index[-1]))

    def cagr(s: pd.Series) -> float:
        return float((1 + s).prod() ** (244 / len(s)) - 1)

    sliced: dict[str, tuple[pd.Series, pd.Series]] = {}
    for name, (lo, hi) in (("TRAIN", TRAIN), ("TEST", TEST)):
        in_win = (full.index >= lo) & (full.index <= hi)
        r_sliced = full.loc[in_win]
        b_sliced = bh_full.loc[in_win]
        sliced[name] = (r_sliced, b_sliced)
        print(f"\n{name}  {lo.date()} -> {hi.date()}")
        print(
            f"  strategy CAGR {cagr(r_sliced) * 100:>6.2f}%   "
            f"buy&hold CAGR {cagr(b_sliced) * 100:>6.2f}%   "
            f"delta {(cagr(r_sliced) - cagr(b_sliced)) * 100:>+6.2f} pp"
        )
        daily_excess_test(r_sliced, b_sliced, name)
        block_bootstrap(r_sliced, b_sliced, name)

    print("\n" + "=" * 96)
    print("SUMMARY OF THE ARITHMETIC")
    print("=" * 96)
    print(f"{'':<10}{'strategy':>12}{'buy&hold':>12}{'delta':>11}")
    for name, (rs, bs) in sliced.items():
        cs, cb = cagr(rs), cagr(bs)
        print(f"{name:<10}{cs * 100:>11.2f}%{cb * 100:>11.2f}%{(cs - cb) * 100:>10.2f}pp")

    print(
        f"\nTRAIN->TEST degradation: strategy CAGR "
        f"{(cagr(sliced['TRAIN'][0]) - cagr(sliced['TEST'][0])) * 100:.2f} pp"
    )


if __name__ == "__main__":
    main()
