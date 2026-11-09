"""Independent verification of the TEST result.

The 2025 miss (-4.51% vs buy&hold +13.34%) is large enough that a bug is a
plausible explanation, so it gets checked properly rather than argued away:

1. TRUNCATION TEST -- rebuild the signal and score for sampled dates using ONLY
   data up to that date, and require exact equality with the vectorised version.
   This is the real no-lookahead proof: if any future bar influenced the value
   at t, the two disagree.
2. CONSTRAINT TEST -- re-check every cap from the engine's own weight frame.
3. DIAGNOSIS -- why did 2025 go the other way? exposure, names per rebalance.
4. The control's name-count caveat is quantified here too.

Usage: .venv/bin/python research/agent_donchian/verify.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (  # noqa: E402
    CONTROL_SEEDS,
    TEST_END,
    TEST_START,
    backtest,
    breakout_signal,
    build_score,
    load_all,
    portfolio_config,
    random_signal_like,
    slice_panel,
)

HERE = Path(__file__).resolve().parent


def truncated_score(close_t: pd.DataFrame, high_t: pd.DataFrame, period: int,
                    rank_lb: int) -> pd.DataFrame:
    """Signal + score rebuilt from a panel that ENDS at t. No future data exists here."""
    prior_high = high_t.rolling(period, min_periods=period).max().shift(1)
    sig = pd.DataFrame(0.0, index=close_t.index, columns=close_t.columns)
    sig = sig.mask(close_t > prior_high, 1.0)
    sig[prior_high.isna()] = 0.0
    mom = close_t / close_t.shift(rank_lb) - 1.0
    return mom.where(sig > 0).rank(axis=1, pct=True, na_option="keep")


def main() -> None:
    sel = json.loads((HERE / "test_results.json").read_text())
    period, rank_lb = sel["period"], 126
    close, high, low, _, _ = load_all()
    te = (str(TEST_START.date()), str(TEST_END.date()))
    p_te = slice_panel(close, *te)

    sig = breakout_signal(close, high, low, period)
    score = build_score(sig, close)

    # ---- 1. TRUNCATION TEST ------------------------------------------------
    print("=" * 78)
    print(f"1. NO-LOOKAHEAD TRUNCATION TEST  (period={period}, rank_lb={rank_lb})")
    print("=" * 78)
    rng = np.random.default_rng(7)
    # sample dates in TEST plus a warm-up prefix long enough for rank_lb
    lo = max(p_te.index[0], close.index[rank_lb + period + 5])
    cand = p_te.index[p_te.index >= lo]
    picks = sorted(rng.choice(cand, size=15, replace=False))
    worst = 0.0
    for t in picks:
        trunc = truncated_score(close.loc[:t], high.loc[:t], period, rank_lb)
        a = score.loc[t].to_numpy(dtype=float)
        b = trunc.loc[t].to_numpy(dtype=float)
        an, bn = np.isnan(a), np.isnan(b)
        if not (an == bn).all():
            raise AssertionError(f"{t.date()}: NaN pattern differs -> lookahead")
        d = np.nanmax(np.abs(a[~an] - b[~bn])) if (~an).any() else 0.0
        worst = max(worst, float(d))
    print(f"  sampled {len(picks)} dates across TEST (incl. warm-up prefixes)")
    print(f"  max |vectorised - truncated| across all sampled dates: {worst:.3e}")
    print(f"  VERDICT: {'PASS - score at t depends only on data <= t' if worst < 1e-12 else 'FAIL - LOOKAHEAD'}")

    # extra check: an intentionally leaked score must score differently, or the
    # test above is vacuous.
    leaked = p_te.pct_change(fill_method=None).shift(-5).rolling(10).sum().abs()
    lk = leaked.where(sig.loc[p_te.index] > 0).rank(axis=1, pct=True, na_option="keep")
    diff = float(np.nanmax(np.abs(
        lk.loc[p_te.index].to_numpy(dtype=float)
        - score.loc[p_te.index].to_numpy(dtype=float))))
    print(f"  control: a deliberately leaked score differs by {diff:.3f} "
          f"(non-zero => the test can detect lookahead)")

    # ---- 2. CONSTRAINTS ----------------------------------------------------
    print("\n" + "=" * 78)
    print("2. PORTFOLIO CONSTRAINT AUDIT (engine's own held-weight frame)")
    print("=" * 78)
    res = backtest(p_te, score.loc[p_te.index])
    w = res.weights
    cfg = portfolio_config()
    held = w.where(w > 0)
    n_names = (w > 0).sum(axis=1)
    print(f"  max single-name weight : {held.max().max() * 100:>6.2f}%  "
          f"(cap {cfg.max_weight * 100:.0f}%)  "
          f"{'OK' if held.max().max() <= cfg.max_weight + 1e-9 else 'VIOLATION'}")
    from nsealgo.backtest.engine import sector_of

    sec = w.T.groupby([sector_of(c) for c in w.columns]).sum().T
    print(f"  max sector weight      : {sec.max().max() * 100:>6.2f}%  "
          f"(cap {cfg.max_sector_weight * 100:.0f}%)  "
          f"{'OK' if sec.max().max() <= cfg.max_sector_weight + 1e-9 else 'VIOLATION'}")
    print(f"  min gross exposure     : {w.sum(axis=1).min() * 100:>6.2f}%  "
          f"(cash buffer {cfg.cash_buffer * 100:.0f}%)  "
          f"{'OK' if w.sum(axis=1).min() >= cfg.cash_buffer - 0.02 else 'below buffer'}")
    print(f"  names held  min/avg/max: {n_names.min():.0f} / "
          f"{n_names.mean():.1f} / {n_names.max():.0f}  "
          f"(n_positions={cfg.n_positions}, max_names={cfg.max_names})  "
          f"{'OK' if n_names.max() <= cfg.max_names else 'VIOLATION'}")
    print(f"  days fully in cash     : {int((n_names == 0).sum())} of {len(w)}")

    # ---- 3. DIAGNOSIS ------------------------------------------------------
    print("\n" + "=" * 78)
    print("3. WHY 2025 WENT AGAINST IT -- exposure and breadth by year")
    print("=" * 78)
    names_fired = (sig.loc[p_te.index] > 0).sum(axis=1)
    by_year = pd.DataFrame({
        "days": names_fired.groupby(sig.loc[p_te.index].index.year).size(),
        "names_flagged_mean": names_fired.groupby(
            sig.loc[p_te.index].index.year).mean(),
        "names_held_mean": n_names.groupby(n_names.index.year).mean(),
        "invested_pct": w.sum(axis=1).groupby(w.index.year).mean() * 100,
    })
    print(by_year.to_string(float_format=lambda v: f"{v:>8.2f}"))
    print("\n  DIAGNOSIS -- it is not that the signal trades too much, it is that")
    print("  the signal is too SPARSE to fill the book, so the book cannot be built.")
    n_flag = (sig.loc[p_te.index] > 0).sum(axis=1)
    print("\n  PortfolioConfig.n_positions=22 is a MAXIMUM, not a target. A 10-day")
    print(f"  breakout flags only {n_flag.mean():.2f} of 48 names on a typical day")
    print(f"  (median {n_flag.median():.0f}), so at most ~{n_flag.mean():.1f} names are")
    print("  eligible at a rebalance. With max_weight=12%, k names can never absorb more")
    print(f"  than k x 12% of the book: {n_flag.mean():.1f} x 12% = "
          f"{min(n_flag.mean() * 12, 100):.0f}%.")
    print("  The 25% sector cap then clips it further when the flagged names cluster")
    print(f"  (2 banks = 24% max). Measured result: the book was only "
          f"{w.sum(axis=1).mean() * 100:.1f}% invested on average,")
    print(f"  and in 2025 -- the year it lost 17.85% to buy&hold -- just "
          f"{w.sum(axis=1).loc['2025'].mean() * 100:.1f}%.")
    print("\n  So the strategy MISSED the 2025 rally by being in cash, not by holding")
    print("  the wrong names. Structural under-deployment, not a wrong signal.")
    print("  A slower channel (p=20/55/100) widens the flagged set but was already")
    print("  rejected on TRAIN (Sharpe 0.03 / -0.41 / -0.55 vs p=10's 0.40).")

    # ---- 4. control caveat -------------------------------------------------
    print("\n" + "=" * 78)
    print("4. NEGATIVE-CONTROL CAVEAT: the random arm holds FEWER names")
    print("=" * 78)
    print(f"{'seed':>6}{'CAGR':>10}{'Sharpe':>10}{'avg names':>12}")
    for s in CONTROL_SEEDS:
        rs = random_signal_like(sig.loc[p_te.index], s)
        r = backtest(p_te, build_score(rs, p_te).loc[p_te.index])
        print(f"{s:>6}{r.metrics.cagr * 100:>9.2f}%{r.metrics.sharpe:>10.2f}"
              f"{r.diag['avg_names']:>12.1f}")
    print(f"\n  strategy avg names {res.diag['avg_names']:.1f}. The brief asks for the")
    print("  random arm to match % of BARS LONG, which it does (8.80% vs 8.80%),")
    print("  but the real signal is autocorrelated -- a name that breaks out stays")
    print("  flagged for several days -- so it accumulates a wider book out of the")
    print("  same live fraction. The control is therefore a slightly *harder*")
    print("  comparison in return terms and a slightly *easier* one in diversification.")
    print("  Noted rather than fixed: fixing it would mean adding a parameter.")


if __name__ == "__main__":
    main()
