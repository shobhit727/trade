"""Step 08 — random-signal control at resolution, TEST.

Run: .venv/bin/python research/agent_anchored_vwap/08_random_control_robust.py

Step 3 ran 25 random draws. That resolves the coin comparison only to ~4 percentile
points, which is too coarse to say much, so this re-runs it with 200 draws.

Design is unchanged from step 3 and is deliberately narrow: only the *eligibility*
draw is randomised. The score construction (126d momentum rank), the portfolio
constraints, the rebalance dates and the costs are all identical. So the only thing
that differs between a draw and the strategy is which names the VWAP filter flagged.

Two comparisons are reported, because they answer different questions:

  (a) vs random — does the *whole construction* beat a coin?
  (b) vs cash-matched buy-and-hold — is the gap return, or just less stock held?

TEST only. Parameters frozen from TRAIN (V1).
"""

from __future__ import annotations

import time

import numpy as np
import pandas as pd
from common import (
    BASE_COSTS,
    CFG,
    TEST,
    VARIANTS,
    ZeroCostModel,
    _slice_metrics,
    build_score,
    buy_and_hold,
    deviation,
    eligible,
    full_backtest,
    load,
    random_score,
    rebalance_dates,
)

from nsealgo.backtest.metrics import compute_metrics

pd.set_option("display.width", 200)

N_DRAWS = 200
SEED = 20261007


def cagr(s: pd.Series) -> float:
    return float((1 + s).prod() ** (244 / len(s)) - 1)


def bh_at_deployment(close: pd.DataFrame, window, deployed: float) -> pd.Series:
    from common import ONE_WAY_RATE

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
    mask = eligible(dev, wvar.threshold)
    score = build_score(close, dev, wvar.threshold, wvar.score_kind)

    res = full_backtest(close, score)
    lo, hi = TEST
    sel = (res.returns.index >= lo) & (res.returns.index <= hi)
    strat_te = res.returns.loc[sel]
    strat_cagr = cagr(strat_te)
    deploy = float(res.weights.loc[sel].sum(axis=1).mean())

    bh90 = buy_and_hold(close, TEST)
    bh_match = bh_at_deployment(close, TEST, deploy)

    print("=" * 84)
    print(f"RANDOM-SIGNAL CONTROL — {N_DRAWS} draws, TEST {lo.date()} -> {hi.date()}")
    print("=" * 84)
    strat_sharpe = compute_metrics(strat_te).sharpe
    print(f"strategy TEST CAGR {strat_cagr * 100:.2f}%   Sharpe(rf=6.5%) "
          f"{strat_sharpe:.2f}")
    print(f"mean deployment {deploy:.1%}")
    print(f"buy&hold @90%   CAGR {cagr(bh90) * 100:.2f}%")
    print(f"buy&hold @{deploy:.0%}  CAGR {cagr(bh_match) * 100:.2f}%  <- cash-matched")

    rb = [d for d in rebalance_dates(close.index) if d in mask.index][1:]
    counts = {d: int(mask.loc[d].sum()) for d in rb}
    print(f"\nrebalance dates matched: {len(rb)}   "
          f"mean eligible {np.mean(list(counts.values())):.1f}")

    rng = np.random.default_rng(SEED)
    cagrs = np.empty(N_DRAWS)
    sharpes = np.empty(N_DRAWS)
    t0 = time.time()
    for i in range(N_DRAWS):
        sc = random_score(close, rng, counts, mask.index)
        r = full_backtest(close, sc)
        rr = r.returns.loc[sel]
        cagrs[i] = cagr(rr)
        sharpes[i] = compute_metrics(rr).sharpe
        if (i + 1) % 50 == 0:
            print(f"  {i + 1}/{N_DRAWS} draws  ({time.time() - t0:.0f}s)")

    q = [1, 5, 25, 50, 75, 90, 95, 99]
    print(f"\nrandom CAGR distribution ({N_DRAWS} draws):")
    print(f"  mean {cagrs.mean() * 100:6.2f}%  sd {cagrs.std(ddof=1) * 100:5.2f}pp  "
          f"min {cagrs.min() * 100:6.2f}%  max {cagrs.max() * 100:6.2f}%")
    print("  percentiles: " + "  ".join(f"p{x}={np.percentile(cagrs, x) * 100:.2f}%" for x in q))
    print(f"  random Sharpe (rf=6.5%, same basis as step 3): mean {sharpes.mean():.2f}  "
          f"sd {sharpes.std(ddof=1):.2f}")

    pct = float((cagrs < strat_cagr).mean() * 100)
    print("\n(a) vs the coin")
    print(f"  strategy sits ABOVE {pct:.1f}% of draws "
          f"({(cagrs < strat_cagr).mean() * 100:.1f}th percentile from the bottom); "
          f"the {100 - pct:.1f} percentile from the top")
    print(f"  beats {int((cagrs < strat_cagr).sum())}/{N_DRAWS} draws "
          f"(step 3 with 25 draws said 80%)")
    print(f"  strategy CAGR {strat_cagr * 100:.2f}% vs random mean "
          f"{cagrs.mean() * 100:.2f}% -> {(strat_cagr - cagrs.mean()) * 100:+.2f} pp")
    print(f"  random draws that beat buy&hold@90% ({cagr(bh90) * 100:.2f}%): "
          f"{float((cagrs > cagr(bh90)).mean() * 100):.0f}%")
    print(f"  random draws that beat cash-matched B&H "
          f"({cagr(bh_match) * 100:.2f}%): "
          f"{float((cagrs > cagr(bh_match)).mean() * 100):.0f}%")

    print("\n(b) cash-matched arithmetic excess (the honest test)")
    ex = (strat_te - bh_match).dropna()
    t = float(ex.mean() / ex.std(ddof=1) * np.sqrt(len(ex)))
    print(f"  daily excess {ex.mean() * 1e4:+.2f} bps -> {ex.mean() * 244 * 100:+.2f}%/yr"
          f"   t={t:+.2f}  ({'significant' if abs(t) > 1.96 else 'NOT significant'} at 5%)")
    print(f"  vs buy&hold@90%: daily excess "
          f"{float((strat_te - bh90).dropna().mean()) * 1e4:+.2f} bps -> "
          f"{float((strat_te - bh90).dropna().mean()) * 244 * 100:+.2f}%/yr")

    print("\n" + "-" * 84)
    print("READING")
    print("-" * 84)
    print(f"  The construction clearly beats a coin: it lands at the "
          f"{100 - pct:.0f}th percentile.")
    print(f"  But the *excess return over a cash-matched market* is "
          f"{ex.mean() * 244 * 100:+.2f}%/yr with t={t:+.2f}.")
    if abs(t) <= 1.96:
        print("  That is not distinguishable from zero. Beating the coin is the")
        print("  minimum bar (brief §6.5), not evidence of a tradable edge.")
    else:
        print("  That is distinguishable from zero at 5%.")
    _ = (BASE_COSTS, CFG, ZeroCostModel, _slice_metrics, dev, build_score)


if __name__ == "__main__":
    main()
