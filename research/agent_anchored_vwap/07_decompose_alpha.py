"""Step 07 — WHY does a flat arithmetic excess produce a positive CAGR gap?

Run: .venv/bin/python research/agent_anchored_vwap/07_decompose_alpha.py

Step 5 found TEST daily excess = -0.01%/yr with t = -0.00, yet TEST CAGR beats
buy-and-hold by +0.31 pp. Those cannot both describe an edge. They are consistent if
the gap is a *compounding* effect, not a mean-return effect:

    CAGR ~ daily_mean - 0.5 * sigma^2 / 244

The book is ~67% deployed across ~24 names where buy-and-hold is 90% deployed across 48,
so its daily volatility is materially lower. Lower sigma raises geometric return at an
unchanged arithmetic mean. That is a real benefit to a holder, but it is not alpha and it
is not produced by the VWAP signal.

This file separates the two, and adds the benchmark the brief's like-for-like rule
actually calls for: buy-and-hold run at the SAME cash level as the strategy. Comparing a
67%-deployed book against a 90%-deployed benchmark conflates "the signal worked" with
"the book held less stock".

TEST numbers only.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from common import (
    BASE_COSTS,
    CFG,
    ONE_WAY_RATE,
    TEST,
    TRAIN,
    VARIANTS,
    build_score,
    buy_and_hold,
    deviation,
    full_backtest,
    load,
)

pd.set_option("display.width", 200)


def cagr(s: pd.Series) -> float:
    return float((1 + s).prod() ** (244 / len(s)) - 1)


def daily_vol(s: pd.Series) -> float:
    return float(s.std(ddof=1) * np.sqrt(244))


def bh_at_deployment(close: pd.DataFrame, window, deployed: float) -> pd.Series:
    """Equal-weight buy-and-hold held at an arbitrary deployment level.

    Nothing is sold inside the window, so the single entry charge is one-way.
    """
    lo, hi = window
    ew = close.loc[lo:hi].pct_change(fill_method=None).mean(axis=1).fillna(0.0)
    out = deployed * ew
    out.iloc[0] -= deployed * ONE_WAY_RATE
    return out


def main() -> None:
    u = load()
    close = u.close
    wvar = next(v for v in VARIANTS if v.name == "V1_p50_t2.0_mom")
    dev = deviation(close, wvar.period)
    score = build_score(close, dev, wvar.threshold, wvar.score_kind)
    strat = full_backtest(close, score).returns

    print("=" * 84)
    print("TEST 2024-01-01 -> 2026-10-01 — separating alpha from volatility")
    print("=" * 84)

    rows = []
    for name, window in (("TRAIN", TRAIN), ("TEST", TEST)):
        lo, hi = window
        sel = (strat.index >= lo) & (strat.index <= hi)
        s = strat.loc[sel]
        dep = float(full_backtest(close, score).weights.loc[sel].sum(axis=1).mean())

        b90 = buy_and_hold(close, window)
        b_match = bh_at_deployment(close, window, dep)
        b_cash_only = bh_at_deployment(close, window, 1.0 - dep)

        print(f"\n{name}   mean deployment {dep:.1%}")
        print(f"  {'':<34}{'CAGR':>9}{'annVol':>9}{'dailyMean':>11}{'MaxDD':>10}")
        print(f"  {'anchored_vwap V1':<34}{cagr(s) * 100:>8.2f}%{daily_vol(s) * 100:>8.2f}%"
              f"{s.mean() * 1e4:>9.2f}bp{s.min() * 100:>9.2f}%")
        for label, b in (
            ("buy&hold @90% (brief default)", b90),
            (f"buy&hold @{dep:.0%} (cash-matched)", b_match),
            (f"cash only ({1 - dep:.0%} @ T-bill)", b_cash_only),
        ):
            print(f"  {label:<34}{cagr(b) * 100:>8.2f}%{daily_vol(b) * 100:>8.2f}%"
                  f"{b.mean() * 1e4:>9.2f}bp{(1 + b).cumprod().min() - 1:>9.2%}")

        excess = (s - b_match).dropna()
        t = float(excess.mean() / excess.std(ddof=1) * np.sqrt(len(excess)))
        print("\n  vs CASH-MATCHED buy-and-hold (the fair comparison):")
        print(f"    CAGR delta          : {(cagr(s) - cagr(b_match)) * 100:+.2f} pp")
        print(f"    arithmetic excess   : {excess.mean() * 244 * 100:+.2f}%/yr  t={t:+.2f}  "
              f"({'significant' if abs(t) > 1.96 else 'NOT significant'} at 5%)")

        # The arithmetic decomposition of geometric return.
        mu = float(s.mean()) * 244
        var = float(s.var(ddof=1))
        drag = 0.5 * var * 244  # variance drag in the same annualised units
        print(f"    arithmetic return   : {mu * 100:+.2f}%/yr")
        print(f"    variance drag term  : {-drag * 100:+.2f}%/yr  (0.5*sigma^2)")
        print(f"    => geometric growth : {(mu - drag) * 100:+.2f}%/yr, "
              f"observed {cagr(s) * 100:+.2f}%")

        mu_b = float(b_match.mean()) * 244
        drag_b = 0.5 * float(b_match.var(ddof=1)) * 244
        print(f"    buy&hold cash-matched: arithmetic {mu_b * 100:+.2f}%, "
              f"variance drag {-drag_b * 100:+.2f}%, geometric {cagr(b_match) * 100:+.2f}%")
        print(f"    => of the {(cagr(s) - cagr(b_match)) * 100:+.2f} pp CAGR gap: "
              f"{(mu - mu_b) * 100:+.2f} pp is return, "
              f"{(-drag + drag_b) * 100:+.2f} pp is lower volatility")

        rows.append((name, cagr(s), cagr(b90), cagr(b_match), dep))

    print("\n" + "=" * 84)
    print("SUMMARY")
    print("=" * 84)
    print(f"{'':<8}{'strategy':>11}{'B&H 90%':>11}{'B&H cash-mat':>15}{'deploy':>9}")
    for name, cs, c90, cm, dep in rows:
        print(f"{name:<8}{cs * 100:>10.2f}%{c90 * 100:>10.2f}%{cm * 100:>14.2f}%"
              f"{dep * 100:>8.1f}%")

    print(
        "\nThe cash-matched column is the honest benchmark. Any gap that survives there\n"
        "is signal; any gap that only appears against the 90%-deployed benchmark is a\n"
        "statement about how much stock the book held, not about the VWAP signal."
    )
    _ = (BASE_COSTS, CFG)


if __name__ == "__main__":
    main()
