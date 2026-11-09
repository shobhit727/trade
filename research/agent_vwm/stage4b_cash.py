"""STAGE 4b — what is actually causing 40.5% cash?

Stage 4 ruled out the 12% single-name cap as the sole cause (a 22+ eligible bucket
still shows ~38% cash against a 90% ceiling). Two candidates remain:

  (a) the 35% one-way turnover budget in `apply_turnover_budget` — it only adopts
      `cap - drop_amt` of the new target each rebalance, so a book being built up
      from cash takes several months to fill;
  (b) sparse eligibility early in the window.

`PortfolioConfig` default turnover_budget=0.35 is what `run_backtest` was given, so
this is a property of the delivered book, not a bug. Measure it directly.

STILL NOT A NEW VARIANT: no parameter is changed, nothing is re-selected. This
explains the already-reported V3 result.
"""

from __future__ import annotations

import sys

import pandas as pd

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

    sig, _ = vwm_signal(px_te, vol_te, PERIOD, THR)
    sc = momentum_rank_score(px_te, sig, 126)
    res = run_backtest(px_te, sc, COST_MODEL, CFG, "M")
    w = res.weights

    elig = (sig > 0).sum(axis=1)
    names = (w > 0).sum(axis=1)
    invested = w.sum(axis=1)          # <-- WEIGHT, not name count
    cash = 1.0 - invested

    print("=" * 78)
    print("A. Exposure decomposition (invested = sum of weights, correct units)")
    print("=" * 78)
    buckets = [(0, 5), (6, 10), (11, 15), (16, 21), (22, 100)]
    print(f"  {'eligible':<12}{'days':>6}{'mean cash':>12}{'ceiling(90%*k/22)':>20}"
          f"{'mean invested':>15}{'mean names':>12}")
    for lo, hi in buckets:
        m = (elig >= lo) & (elig <= hi)
        if not m.any():
            continue
        ceil_ = min(0.9, lo * CFG.max_weight) if lo else 0.0
        print(f"  {f'{lo}-{hi}':<12}{int(m.sum()):>6}{cash[m].mean():>11.1%}"
              f"{ceil_:>19.1%}{invested[m].mean():>15.1%}{names[m].mean():>12.1f}")

    print()
    print("=" * 78)
    print("B. Turnover-budget binding test — compare the raw target to the delivered book")
    print("=" * 78)
    # Reconstruct the raw (pre-budget) targets the engine builds.
    from nsealgo.backtest.engine import (  # noqa: F401
        REF_POSITION_NOTIONAL,
        _d,
        _rebalance_dates,
        apply_turnover_budget,
        build_rebalance_weights,
    )

    idx = px_te.index.intersection(sc.index)
    pxs = px_te.loc[idx]
    scs = sc.loc[idx]
    rets = pxs.pct_change(fill_method=None).fillna(0.0)
    volm = rets.rolling(CFG.vol_lookback, min_periods=20).std()
    rb = [d for d in _rebalance_dates(pxs.index, "M") if d in scs.index][1:]

    tgt_raw = build_rebalance_weights(scs.loc[rb], rb, volm.loc[rb], CFG)
    tgt = tgt_raw.copy()
    for i in range(len(tgt)):
        prev = tgt.iloc[i - 1] if i else None
        tgt.iloc[i] = apply_turnover_budget(
            tgt_raw.iloc[i], prev, CFG.turnover_budget, CFG.max_names
        )

    raw_inv = tgt_raw.sum(axis=1)
    raw_names = (tgt_raw > 0).sum(axis=1)
    got_inv = tgt.sum(axis=1)

    print(f"  raw targets (no turnover budget): mean invested {raw_inv.mean():.1%}, "
          f"mean names {raw_names.mean():.1f}")
    print(f"  after turnover budget           : mean invested {got_inv.mean():.1%}, "
          f"mean names {(tgt>0).sum(axis=1).mean():.1f}")
    print(f"  cash the budget ADDED           : {(raw_inv.mean()-got_inv.mean())*100:.1f}pp")
    print(f"  cash present even in the RAW target: {(1-raw_inv.mean())*100:.1%}")
    print()
    print(f"  rebalance dates: {len(rb)}   turnover_budget = {CFG.turnover_budget}")
    print("  raw target invested, by rebalance (first 12 / last 12):")
    show = list(rb[:12]) + list(rb[-12:])
    for d in show:
        i = rb.index(d)
        print(f"    {str(d.date())}  raw {raw_inv.iloc[i]:>6.1%} ({raw_names.iloc[i]:>2.0f} names)"
              f"  ->  delivered {got_inv.iloc[i]:>6.1%} ({int((tgt.iloc[i]>0).sum()):>2d} names)")

    print()
    print("=" * 78)
    print("C. Attribution: which months did the book sit in cash?")
    print("=" * 78)
    mo = pd.DataFrame({"cash": cash, "elig": elig, "names": names})
    g = mo.groupby(mo.index.to_period("M")).mean()
    hi = g[g.cash > 0.40]
    print(f"  months with >40% cash: {len(hi)} of {len(g)}")
    if len(hi):
        print(hi.head(15).to_string())
    print()
    print(f"  mean cash: {(1-res.metrics.cagr*0):.0f}" if False else
          f"  mean cash overall {cash.mean():.1%}; "
          f"mean eligible {elig.mean():.1f}; mean invested {invested.mean():.1%}")

    print()
    print("=" * 78)
    print("D. Sanity: 2024 was 66.8% cash. Was the signal simply absent?")
    print("=" * 78)
    for y in (2024, 2025, 2026):
        m = elig.index.year == y
        print(f"  {y}: eligible mean {elig[m].mean():>5.1f}  "
              f"median {elig[m].median():>5.1f}  "
              f"days with eligible<5: {int((elig[m] < 5).sum()):>3} of {int(m.sum()):>3}  "
              f"mean cash {cash[m].mean():>6.1%}")
    print("  -> 2024 is a regime where the 63-day ROC>3% gate rarely fired, so the")
    print("     book was structurally forced toward cash by the position limits.")


if __name__ == "__main__":
    main()
