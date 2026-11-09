"""Step 06 — BOOK DECOMPOSITION on TRAIN. No TEST numbers here.

Run: .venv/bin/python research/agent_anchored_vwap/06_book_decomposition.py

Why this file exists
--------------------
Step 0 checked that `build_rebalance_weights` never selects an ineligible name. That
check was aimed at the wrong function. The engine's *actual* book is

    tgt[i] = apply_turnover_budget(build_rebalance_weights(...)[i], tgt[i-1], 0.35, 30)

and `apply_turnover_budget` returns `cur + lam*(tgt - cur)`, where `cur` is the
PREVIOUS target. A name that has dropped out of the eligible set has tgt = 0, so it
decays geometrically toward zero instead of leaving on the rebalance it stops being
flagged. With a turnover budget of only 0.35 and an eligible set that averages ~13 of
48 names, the decay is slow and stale names accumulate up to `max_names = 30`.

So the reported "23.4 names held" against "12.8 eligible" is not a typo. This file
quantifies what the book actually is:

  * deployed weight (how much of the book is even at risk),
  * cash,
  * weight sitting on names eligible TODAY vs. stale residuals,
  * effective weight on the flagged set at rebalance instants.

Everything here is TRAIN. TEST is untouched until step 03.
"""

from __future__ import annotations

import pandas as pd
from common import (
    CFG,
    TRAIN,
    VARIANTS,
    build_score,
    deviation,
    eligible,
    full_backtest,
    load,
    momentum_6m,
)

pd.set_option("display.width", 200)


def main() -> None:
    u = load()
    close = u.close
    wvar = next(v for v in VARIANTS if v.name == "V1_p50_t2.0_mom")
    dev = deviation(close, wvar.period)
    mask = eligible(dev, wvar.threshold)
    score = build_score(close, dev, wvar.threshold, wvar.score_kind)

    res = full_backtest(close, score)
    held = res.weights
    lo, hi = TRAIN
    h = held.loc[lo:hi]
    mk = mask.loc[lo:hi]

    print("=" * 84)
    print("BOOK DECOMPOSITION — TRAIN 2016-01-01 -> 2023-12-31")
    print("=" * 84)
    print(f"config: n_positions={CFG.n_positions} max_names={CFG.max_names} "
          f"cash_buffer={CFG.cash_buffer} turnover_budget={CFG.turnover_budget}")
    print(f"V1 flagged set: {wvar.period}d VWAP, threshold {wvar.threshold:.0%}")

    deployed = h.sum(axis=1)
    print("\n1. DEPLOYMENT")
    print(f"   mean deployed weight : {deployed.mean():.4f}  "
          f"(target {1 - CFG.cash_buffer:.2f})")
    print(f"   mean cash            : {1 - deployed.mean():.4f}")
    print(f"   min / max deployed   : {deployed.min():.4f} / {deployed.max():.4f}")
    print(f"   days fully in cash   : {int((deployed < 1e-6).sum())}")

    print("\n2. NAMES HELD vs NAMES FLAGGED")
    print(f"   mean names held          : {float((h > 0).sum(axis=1).mean()):.2f}")
    print(f"   mean names flagged today : {float((mk > 0).sum(axis=1).mean()):.2f}")
    print(f"   days held >= max_names   : {int(((h > 0).sum(axis=1) >= CFG.max_names).sum())}"
          f" of {len(h)}")

    print("\n3. WHERE THE WEIGHT ACTUALLY SITS")
    # Weight on names eligible TODAY vs. weight on names that are only still held
    # because the turnover budget has not finished liquidating them.
    w_today = h.where(mk > 0).sum(axis=1)
    w_stale = h.where(mk <= 0).sum(axis=1)
    print(f"   weight on TODAY-flagged names : {w_today.mean():.4f} "
          f"({w_today.mean() / deployed.mean() * 100:.1f}% of deployed)")
    print(f"   weight on STALE residuals     : {w_stale.mean():.4f} "
          f"({w_stale.mean() / deployed.mean() * 100:.1f}% of deployed)")
    print(f"   mean names stale             : {float((h.where(mk <= 0) > 0).sum(axis=1).mean()):.2f}")

    print("\n4. SIZE OF THE STALE TAIL")
    sw = h.where(mk <= 0)
    sz = sw.stack()
    sz = sz[sz > 0]
    print(f"   stale positions observed     : {len(sz):,}")
    for q in (0.25, 0.5, 0.75, 0.9, 0.99):
        print(f"     p{int(q * 100):>2} stale weight : {float(sz.quantile(q)):.5f}")
    print(f"     share of stale weight below 1% of book: "
          f"{float((sz < 0.01).mean()) * 100:.1f}%")
    print("   DEAD_WEIGHT_EPS in the engine is 1e-4, i.e. far below 1% — so these")
    print("   residuals are 'material' to the engine while being economically noise.")

    print("\n5. AT REBALANCE INSTANTS ONLY (the moments the signal is expressed)")
    from nsealgo.backtest.engine import _rebalance_dates

    rb = [d for d in _rebalance_dates(close.index, "M") if d in h.index]
    hh, mm = h.loc[rb], mk.loc[rb]
    print(f"   rebalance dates in TRAIN: {len(rb)}")
    print(f"   mean weight on flagged names at rebalance : {hh.where(mm > 0).sum(axis=1).mean():.4f}")
    print(f"   mean weight on stale at rebalance         : {hh.where(mm <= 0).sum(axis=1).mean():.4f}")

    print("\n6. DOES THE FILTER CHANGE THE BOOK AT ALL?")
    # Counterfactual book: the same momentum score with NO vwap filter. If the two
    # books hold nearly the same names, the filter is decorative.
    mom_only = momentum_6m(close).rank(axis=1, pct=True)
    res_mom = full_backtest(close, mom_only)
    hm = res_mom.weights.loc[lo:hi]
    names_h = set(h.columns[h.iloc[-1] > 0])
    names_m = set(hm.columns[hm.iloc[-1] > 0])
    print(f"   last-rebalance overlap V1 vs momentum-only : "
          f"{len(names_h & names_m)} shared names")
    ov = pd.DataFrame({"v1": (h > 0).sum(axis=1), "mom_only": (hm > 0).sum(axis=1)})
    print(f"   mean names: V1 {ov.v1.mean():.2f}  momentum-only {ov.mom_only.mean():.2f}")
    print(f"   V1 turnover {res.metrics.annual_turnover:.2f}x/y, "
          f"momentum-only {res_mom.metrics.annual_turnover:.2f}x/y")

    print("\n" + "-" * 84)
    print("CONCLUSION (TRAIN)")
    print("-" * 84)
    stale_share = w_stale.mean() / deployed.mean()
    print(f"   {stale_share * 100:.0f}% of the deployed book sits on names the strategy")
    print("   stopped flagging, purely as a turnover-budget artefact. Combined with")
    print(f"   {1 - deployed.mean():.0%} average cash, the effective exposure to the")
    print("   VWAP signal is far smaller than the config's 22-name / 90% targets imply.")


if __name__ == "__main__":
    main()
