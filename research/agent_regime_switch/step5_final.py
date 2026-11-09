"""STEP 5 — final checks.

1. Is the strategy just "hold less market"? Compare against constant-beta static books
   charged the SAME costs as buy-and-hold (a static book still pays to go in and out).
2. Is the negative-control result statistically distinguishable from a coin flip?
3. GOAL.md section 5 gates on TEST.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import pandas as pd
from scipy import stats as sps  # noqa: F401  (only used if available)

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness import (  # noqa: E402
    TEST_END,
    TEST_START,
    buy_and_hold,
    compute_metrics,
    cost_model,
    load,
    window,
)


def static_beta_book(px: pd.DataFrame, cm, b: float) -> pd.Series:
    """Hold a constant fraction `b` of equal-weight NIFTY-50, charged two round trips."""
    mkt = px.pct_change(fill_method=None).fillna(0.0).mean(axis=1)
    rate = float(cm.all_in_round_trip_bps(Decimal("100000"))) / 1e4
    daily = pd.Series(0.0, index=px.index)
    eq = 1.0
    for i, dt in enumerate(px.index):
        prev = eq
        eq *= 1.0 + b * float(mkt.loc[dt])
        if i == 0 or i == len(px.index) - 1:
            eq -= 0.5 * b * eq * rate
        daily.loc[dt] = eq / prev - 1.0
    return daily


def main() -> None:
    panel, _, _ = load()
    px = window(panel, TEST_START, TEST_END)
    cm = cost_model()

    print("=== 1. is it just 'hold less market'? TEST, all net of the same costs ===")
    bh = buy_and_hold(panel, cm, TEST_START, TEST_END)
    strat = pd.read_csv(HERE / "test_summary.csv")
    s = strat[strat.book == "regime_switch"].iloc[0]
    print(f"{'book':<26}{'CAGR':>9}{'Sharpe':>9}{'MaxDD':>10}{'Calmar':>9}")
    print(f"{'regime_switch (selected)':<26}{s.cagr * 100:>8.2f}%{s.sharpe:>9.2f}"
          f"{s.max_dd * 100:>9.2f}%{s.calmar:>9.2f}")
    for b in (0.4, 0.5, 0.6, 0.7):
        d = static_beta_book(px, cm, b)
        m = compute_metrics(d, (1.0 + d).cumprod())
        print(f"{'static ' + f'{b:.0%}' + ' beta, same costs':<26}{m.cagr * 100:>8.2f}%"
              f"{m.sharpe:>9.2f}{m.max_drawdown * 100:>9.2f}%{m.calmar:>9.2f}")
    print(f"{'buy-and-hold':<26}{bh['metrics'].cagr * 100:>8.2f}%"
          f"{bh['metrics'].sharpe:>9.2f}{bh['metrics'].max_drawdown * 100:>9.2f}%"
          f"{bh['metrics'].calmar:>9.2f}")

    print("\n=== 2. negative control: is 'beats 85% of random' distinguishable "
          "from a coin flip? ===")
    rnd = pd.read_csv(HERE / "test_random_control.csv")
    n = len(rnd)
    for col, val in (("sharpe", s.sharpe), ("cagr", s.cagr)):
        frac = float((rnd[col] < val).mean())
        # one-sided binomial test of H0: strategy sits at the median of the null
        k = int((rnd[col] < val).sum())
        p = float(1 - sps.binom.cdf(k - 1, n, 0.5)) if k > 0 else 1.0
        print(f"  {col:<7} strategy {val:>7.3f} beats {k}/{n} = {frac * 100:>5.1f}% "
              f"of random; one-sided binom p vs coin-flip median = {p:.3f}")
    print(f"  random null: CAGR {rnd.cagr.mean() * 100:.2f}% +/- {rnd.cagr.std() * 100:.2f}"
          f"   Sharpe {rnd.sharpe.mean():.2f} +/- {rnd.sharpe.std():.2f}")
    print("  Interpretation: the brief's bar is 90%. "
          f"{'PASS' if (rnd.sharpe < s.sharpe).mean() >= 0.90 else 'FAIL — not separable from a coin flip'}.")

    print("\n=== 3. GOAL.md section 5 gates on TEST ===")
    yrs = None
    gates = [
        ("1 — CAGR >= 3%/month net (~43%/yr)", f"{s.cagr * 100:.2f}%/yr", s.cagr >= 0.43),
        ("2 — Sharpe >= 1.0", f"{s.sharpe:.2f}", s.sharpe >= 1.0),
        ("4 — MaxDD <= 20%", f"{s.max_dd * 100:.2f}%", s.max_dd >= -0.20),
    ]
    for g, v, ok in gates:
        print(f"  {g:<42} {v:>10}  {'PASS' if ok else 'FAIL'}")
    print("  gates 5-7 (cost stress / capacity / robustness) not pursued: "
          "gates 1 and 2 already fail by a wide margin.")
    _ = yrs


if __name__ == "__main__":
    main()
