"""TRAIN-stage diagnostics: controls, cost decomposition, lookahead test.

None of this consumes the 5-variant parameter budget -- these are the brief's
mandated sanity checks (section 6) plus a determinism/no-lookahead proof.
"""

from __future__ import annotations

import sys

sys.path.insert(0, "src")
sys.path.insert(0, "research/agent_ma_cross")

import numpy as np  # noqa: E402
from harness import (  # noqa: E402
    CFG,
    TRAIN,
    WINDOWS,
    ma_cross_score,
    random_among_flagged,
    random_mask,
)

from nsealgo.backtest.engine import run_backtest  # noqa: E402
from nsealgo.backtest.metrics import compute_metrics  # noqa: E402
from nsealgo.costs import CostModel  # noqa: E402
from nsealgo.data.loader import load_universe  # noqa: E402

COSTS = CostModel(segment="delivery", slippage_bps=5)
# NOTE: must be int 0, NOT 0.0. CostModel stores slippage_bps uncoerced, so a float
# reaches `Decimal + float` in all_in_round_trip_bps and raises TypeError, which
# kills every run_backtest call. See BUG_costs_float_slippage.md.
FREE = CostModel(segment="delivery", slippage_bps=0)


def m(net, eq):
    x = compute_metrics(net, eq)
    return x.cagr, x.sharpe, x.max_drawdown


def main() -> None:
    lo, hi = TRAIN
    panel, symbols, _ = load_universe("data/nse")

    # ---------------------------------------------------------------- #
    print("=" * 72)
    print("A. NO-LOOKAHEAD PROOF")
    print("=" * 72)
    # If a signal at date t depended on anything after t, truncating the panel at t
    # would change it. Compute the full-history score, then recompute it from a
    # panel physically truncated at t, and compare.
    for t in ["2018-06-29", "2020-03-16", "2022-09-30"]:
        full = ma_cross_score(panel, 50, 200, "flag")
        cut = ma_cross_score(panel.loc[:t], 50, 200, "flag").loc[t]
        same = bool(np.allclose(
            full.loc[t].fillna(-1).to_numpy(), cut.fillna(-1).to_numpy()))
        print(f"  {t}: score at t identical when panel is truncated at t -> {same}")
    print("  (weights are held from t+1 by construction: engine.py `held.shift(1)`)")

    p = panel.loc[lo:hi]

    # ---------------------------------------------------------------- #
    print()
    print("=" * 72)
    print("B. COST DECOMPOSITION -- is the loss signal or friction?")
    print("=" * 72)
    print(f"  {'variant':<20} {'net CAGR':>10} {'gross CAGR':>11} "
          f"{'drag/y':>9} {'turn/y':>8}")
    for name, (fast, slow) in WINDOWS.items():
        kind = ("flag" if name.endswith("_flag")
                else "strength" if name.endswith("_strength") else "momrank")
        sc = ma_cross_score(panel, fast, slow, kind).loc[lo:hi]
        net = run_backtest(p, sc, COSTS, CFG, rebalance="M")
        gross = run_backtest(p, sc, FREE, CFG, rebalance="M")
        cn, _, _ = m(net.returns, net.equity)
        cg, _, _ = m(gross.returns, gross.equity)
        print(f"  {name:<20} {cn*100:9.2f}% {cg*100:10.2f}% "
              f"{net.metrics.cost_drag_annual*100:8.2f}% "
              f"{net.metrics.annual_turnover:7.2f}x")

    # ---------------------------------------------------------------- #
    print()
    print("=" * 72)
    print("C. NEGATIVE CONTROLS")
    print("=" * 72)

    def summarise(label, nets):
        c = [cagr for cagr, _, _ in nets]
        return (f"{label:<34} CAGR mean {np.mean(c)*100:6.2f}%  "
                f"min {np.min(c)*100:6.2f}%  max {np.max(c)*100:6.2f}%")

    # Control A: independent coin flip per name per day, matched % long (brief 6.5)
    for name, (fast, slow) in WINDOWS.items():
        if not name.endswith("_flag"):
            continue
        sc = ma_cross_score(panel, fast, slow, "flag").loc[lo:hi]
        res = []
        for s in range(20):
            r = run_backtest(p, random_mask(panel.loc[lo:hi], sc, s), COSTS, CFG)
            res.append(m(r.returns, r.equity))
        print("  " + summarise(f"A random-mask   {name}", res))

    # Control B: SAME flagged names, ties broken at random. Isolates the ranking.
    print()
    for name, (fast, slow) in WINDOWS.items():
        if not name.endswith("_flag"):
            continue
        sc = ma_cross_score(panel, fast, slow, "flag").loc[lo:hi]
        res = []
        for s in range(20):
            r = run_backtest(p, random_among_flagged(panel.loc[lo:hi], sc, s),
                             COSTS, CFG)
            res.append(m(r.returns, r.equity))
        print("  " + summarise(f"B random-among-flagged {name}", res))

    # ---------------------------------------------------------------- #
    print()
    print("=" * 72)
    print("D. WHAT IS THE FLAG ACTUALLY DOING? (V3 = 50/200 flag)")
    print("=" * 72)
    sc = ma_cross_score(panel, 50, 200, "flag")
    n_flagged = sc.notna().sum(axis=1)
    print(f"  names flagged per bar: mean {n_flagged.mean():.1f} "
          f"min {n_flagged.min()} max {n_flagged.max()}  (universe {p.shape[1]})")
    print(f"  bars where < 22 names flag (book under-filled): "
          f"{int((n_flagged.loc[lo:hi] < 22).sum())} of {len(p)}")

    # Does being flagged predict the next month? Per (bar, symbol) cell.
    r = panel.pct_change(fill_method=None).shift(-21)
    fwd = r.stack().loc[lo:hi]
    flag_stacked = sc.stack().loc[lo:hi]
    up = fwd[flag_stacked > 0]
    dn = fwd[flag_stacked.isna()]
    print(f"  mean next-21d return when flagged    : {up.mean()*100:6.3f}% "
          f"(n={len(up)})")
    print(f"  mean next-21d return when NOT flagged: {dn.mean()*100:6.3f}% "
          f"(n={len(dn)})")
    print(f"  spread                              : "
          f"{(up.mean()-dn.mean())*100:+6.3f} pp")
    print(f"  unconditional mean                  : {fwd.mean()*100:6.3f}%")
    print("  -> the flag's job is RANKING, not market timing; check the two "
          "above are not simply the market beta.")


if __name__ == "__main__":
    main()
