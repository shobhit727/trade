"""Step 4 — ATTRIBUTION. Is the VWAP filter adding anything over a plain book?

This is NOT a 6th parameter variant and is NOT used to select anything — V1 is already
frozen and reported (see 03). It is a benchmark, in the same family as buy-and-hold and
the composite: it answers "where does the return actually come from?".

Motivation: on TEST the eligible-count spread across the 5 variants was enormous
(V1 holds 24 names at a 2% threshold, the rest hold 12-16 at 3-5% thresholds). If V1's
outperformance is just *holding more names*, then the VWAP signal is decorative.

Two corrections applied vs the first attempt at this file, both material:
  * the eligible-vs-ineligible forward-return test uses a NON-OVERLAPPING month grid.
    With 21-day overlapping forward returns a naive daily t-stat is inflated by about
    sqrt(21) ~ 4.6x, which turns a null result into a fake "significant at 5%".
  * the equal-weight benchmark is computed directly over all 48 names. Pushing a
    constant score through the engine does NOT give equal weight — it sorts ties
    alphabetically and then holds only `n_positions` names.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from common import (
    BASE_COSTS,
    CFG,
    HEADER,
    ONE_WAY_RATE,
    SEP,
    TEST,
    VARIANTS,
    ZeroCostModel,
    _slice_metrics,
    build_score,
    buy_and_hold,
    deviation,
    eligible,
    load,
    momentum_6m,
    rebalance_dates,
    row,
)

from nsealgo.backtest.engine import run_backtest
from nsealgo.backtest.metrics import compute_metrics
from nsealgo.factors.core import rank_cross_sectional, zscore_cross_sectional

pd.set_option("display.width", 240)

FWD = 21  # ~1 month forward return


def _bench(name: str, score: pd.DataFrame, close: pd.DataFrame) -> pd.DataFrame:
    """Engine backtest on a score panel, reported over TEST. Prints the row."""
    r = run_backtest(close, score, BASE_COSTS, CFG, rebalance="M")
    g = run_backtest(close, score, ZeroCostModel(), CFG, rebalance="M")
    ones = pd.DataFrame(1.0, index=score.index, columns=score.columns)
    w = _slice_metrics("TEST", r.returns, r.weights, g.returns, ones, TEST)
    print(row(w, name))
    return pd.Series(
        {
            "cagr": w.metrics.cagr,
            "sharpe": w.metrics.sharpe,
            "maxdd": w.metrics.max_drawdown,
            "calmar": w.metrics.calmar,
            "turnover": w.annual_turnover,
            "drag": w.cost_drag_annual,
            "names": w.avg_names,
            "gross_cagr": w.gross_cagr,
        }
    )


def equal_weight_all(close: pd.DataFrame, window=TEST) -> pd.Series:
    """True equal-weight hold of every name, net of one entry cost.

    Constant weights, so turnover is zero after the initial purchase. This is the
    benchmark the engine cannot express.
    """
    lo, hi = window
    sub = close.loc[lo:hi]
    deployed = 1.0 - CFG.cash_buffer
    w = deployed / len(sub.columns)
    rets = sub.pct_change(fill_method=None).fillna(0.0)
    daily = (w * rets).sum(axis=1)
    daily.iloc[0] -= deployed * ONE_WAY_RATE
    return daily


def nonoverlap_edge_test(close: pd.DataFrame, mask: pd.DataFrame) -> None:
    """Eligible vs ineligible mean forward return on a NON-OVERLAPPING month grid.

    For each month-end rebalance date d we take the mean 21-trading-day forward return
    of the eligible names and of the ineligible names, and difference them. Because
    consecutive 21-day windows on a monthly grid do not overlap, the spread series is
    (close to) serially independent and its t-stat is meaningful.
    """
    fwd = close.shift(-FWD) / close - 1.0
    grid = [d for d in rebalance_dates(close.index) if d in mask.index][1:]
    grid = [d for d in grid if d in fwd.index and fwd.loc[d].notna().any()]
    rows = []
    for d in grid:
        e = mask.loc[d] > 0
        f = fwd.loc[d]
        me = float(f[e].mean()) if e.any() else np.nan
        mi = float(f[~e].mean()) if (~e).any() else np.nan
        rows.append({"date": d, "n_elig": int(e.sum()), "elig": me, "inelig": mi,
                     "spread": me - mi})
    df = pd.DataFrame(rows).set_index("date").dropna(subset=["spread"])

    t = float(df["spread"].mean() / df["spread"].std(ddof=1) * np.sqrt(len(df)))
    print(f"\n  non-overlapping month grid: {len(df)} observations, {FWD}d forward returns")
    print(f"  mean forward return, ELIGIBLE   : {df['elig'].mean() * 100:>7.2f}%")
    print(f"  mean forward return, INELIGIBLE : {df['inelig'].mean() * 100:>7.2f}%")
    print(f"  raw edge (elig - inelig)       : {df['spread'].mean() * 100:>+7.2f} pp per {FWD}d")
    print(f"  t-stat of the monthly spread   : {t:>7.2f}  "
          f"({'significant at 5%' if abs(t) > 1.96 else 'NOT significant at 5%'})")
    print(f"  annualised (x244/{FWD}) if it were real: "
          f"{df['spread'].mean() * 244 / FWD * 100:>+7.2f} pp/yr")
    df.to_csv("monthly_edge.csv")


def main() -> None:
    u = load()
    close = u.close
    wvar = next(v for v in VARIANTS if v.name == "V1_p50_t2.0_mom")
    dev = deviation(close, wvar.period)
    mask = eligible(dev, wvar.threshold)

    print("=" * 96)
    print("ATTRIBUTION on TEST — is the VWAP filter doing any work?")
    print("=" * 96)
    print("All engine rows net of the full Indian delivery stack + 5bps/side slippage.")
    print(
        f"Book: {CFG.n_positions} names, {CFG.cash_buffer * 100:.0f}% cash, monthly rebalance, "
        f"{CFG.turnover_budget} one-way turnover budget.\n"
    )
    print(HEADER)
    print(SEP)

    vwap_score = build_score(close, dev, wvar.threshold, wvar.score_kind)
    a = _bench("anchored_vwap V1 (strategy)", vwap_score, close)

    mom_all = rank_cross_sectional(zscore_cross_sectional(momentum_6m(close)))
    b = _bench("6m momentum, NO vwap filter", mom_all, close)

    eq_elig = mask.replace(0.0, np.nan).rank(axis=1, pct=True, na_option="keep")
    c = _bench("vwap filter only (no momentum)", eq_elig, close)

    bh = buy_and_hold(close, TEST)
    mbh = compute_metrics(bh)
    print(
        f"| {'buy & hold (EW net, brief §4.5)':<26} | {mbh.cagr * 100:>7.2f}% | "
        f"{mbh.sharpe:>6.2f} | {mbh.max_drawdown * 100:>7.2f}% | {mbh.calmar:>6.2f} | "
        f"   0.00x |  0.01% | {len(close.columns):>5.0f} |      n/a |"
    )

    ew = equal_weight_all(close)
    mew = compute_metrics(ew)
    print(
        f"| {'equal-weight all 48 (direct)':<26} | {mew.cagr * 100:>7.2f}% | "
        f"{mew.sharpe:>6.2f} | {mew.max_drawdown * 100:>7.2f}% | {mew.calmar:>6.2f} | "
        f"   0.00x |  0.01% | {len(close.columns):>5.0f} |      n/a |"
    )

    print("\n" + "-" * 96)
    print("DECOMPOSITION (TEST CAGR, net)")
    print("-" * 96)
    print(f"  strategy (vwap filter + momentum score) : {a.cagr * 100:>7.2f}%")
    print(f"  momentum score alone, filter removed     : {b.cagr * 100:>7.2f}%")
    print(f"  vwap filter alone, momentum removed      : {c.cagr * 100:>7.2f}%")
    print(f"  buy & hold (equal weight, net)           : {mbh.cagr * 100:>7.2f}%")
    print(f"  equal-weight all 48, held directly       : {mew.cagr * 100:>7.2f}%")
    d = (a.cagr - b.cagr) * 100
    print(f"\n  VWAP filter marginal contribution = strategy - momentum-alone = {d:+.2f} pp/yr")
    print(f"  vs plain buy & hold                      = {a.cagr * 100 - mbh.cagr * 100:+.2f} pp/yr")
    print(f"  vs equal-weight-all-48                   = {a.cagr * 100 - mew.cagr * 100:+.2f} pp/yr")

    print("\n" + "-" * 96)
    print("RAW SIGNAL CHECK — does the eligible set even have forward edge?")
    print("-" * 96)
    nonoverlap_edge_test(close, mask)

    print("\nInterpretation:")
    if abs(d) < 1.0:
        print("  The VWAP filter contributes ~nothing once a momentum score is in place.")
    else:
        print(f"  The VWAP filter contributes {d:+.2f} pp/yr on top of the momentum score.")
    if a.cagr < mew.cagr:
        print("  But the strategy is beaten by a naive equal-weight book — so even that")
        print("  contribution is not enough to justify the turnover it costs.")


if __name__ == "__main__":
    main()
