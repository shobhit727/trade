"""Step 3 — negative controls and ablations. Diagnostic; not used for selection.

Controls
--------
A. Random flag at the SAME unconditional frequency as the real signal, ranking held
   fixed (V5's 126d momentum). Isolates the flag: does the *flag* carry information?
B. Pure random signal, same % of name-days flagged, no ranking. The coin floor.

Ablations
---------
C1. No flag at all, momentum rank only  -> what the flag costs.
C2. Flag only, equal weight across eligible -> what the flag alone does.
C3. The vol-regime half alone (no 1-bar direction), momentum rank.
C4. The direction half alone (no vol filter), momentum rank.
C5. Frozen variant.
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research/agent_voltarget")

from harness import (  # noqa: E402
    PORTFOLIO,
    TEST_END,
    TEST_START,
    TRAIN_END,
    TRAIN_START,
    assert_engine_pinned,
    bh_row,
    build_score,
    buy_and_hold,
    load_panel,
    random_score,
    random_score_no_rank,
    row_of,
    run,
    source_flag,
    up_day,
    vol_regime,
)

from nsealgo.backtest.engine import run_backtest  # noqa: E402
from nsealgo.costs import STRESS_MODELS  # noqa: E402

SEEDS = list(range(1, 21))


def _binom_p(wins: int, n: int) -> float:
    """Two-sided exact binomial p-value under a fair coin."""
    from math import comb

    probs = [comb(n, k) * 0.5 ** n for k in range(n + 1)]
    obs = probs[wins]
    return min(1.0, sum(pr for pr in probs if pr <= obs + 1e-15))


def main() -> None:
    assert_engine_pinned()
    with open("research/agent_voltarget/frozen.txt") as f:
        frozen = f.read().strip()
    panel, _ = load_panel()

    print("=" * 92)
    print(f"STEP 3 — CONTROLS + ABLATIONS. Frozen variant: {frozen}")
    print("=" * 92)

    strat = row_of(frozen, "TEST", run(panel, build_score(frozen, panel),
                                        TEST_START, TEST_END))
    print(f"strategy TEST CAGR {strat.cagr * 100:.2f}%")
    print()

    # ------------------------------------------------------------------ #
    elig = (build_score(frozen, panel).notna().sum(axis=1).loc[TEST_START:TEST_END])
    print(f"STRUCTURAL NOTE: the frozen variant's eligibility mask admits a mean of "
          f"{elig.mean():.1f} names/bar against a 22-name target; "
          f"{(elig < 22).mean() * 100:.0f}% of TEST bars have fewer eligible names "
          f"than the target. When every eligible name is held, the ranking is a no-op,")
    print("which is why controls A and B below return identical numbers -- they differ")
    print("only in the score, and the score does not get to choose.")
    print()

    print("NEGATIVE CONTROL A — random flag, same frequency, ranking fixed")
    a = []
    for s in SEEDS:
        r = run(panel, random_score(panel, s), TEST_START, TEST_END)
        a.append(r.metrics.cagr)
    a = np.array(a)
    wins = int((strat.cagr > a).sum())
    print(f"  n=20  mean {a.mean() * 100:6.2f}%  median {np.median(a) * 100:6.2f}%  "
          f"p5 {np.percentile(a, 5) * 100:6.2f}%  p95 {np.percentile(a, 95) * 100:6.2f}%")
    print(f"  strategy beats {wins}/20 random-flag runs")
    print(f"  flag p-value (two-sided, exact binomial vs 0.5): "
          f"{_binom_p(wins, 20):.3f}")
    print()

    print("NEGATIVE CONTROL B — pure random signal, no ranking")
    bb = []
    for s in SEEDS:
        r = run(panel, random_score_no_rank(panel, s), TEST_START, TEST_END)
        bb.append(r.metrics.cagr)
    bb = np.array(bb)
    winsb = int((strat.cagr > bb).sum())
    print(f"  n=20  mean {bb.mean() * 100:6.2f}%  median {np.median(bb) * 100:6.2f}%  "
          f"p5 {np.percentile(bb, 5) * 100:6.2f}%  p95 {np.percentile(bb, 95) * 100:6.2f}%")
    print(f"  strategy beats {winsb}/20  p-value {_binom_p(winsb, 20):.3f}")
    print()

    # ------------------------------------------------------------------ #
    print("ABLATIONS (both windows; TRAIN then TEST)")
    mom = panel / panel.shift(126) - 1.0

    abl = {
        "C1 no flag, mom126 rank": mom,
        "C2 flag only, equal-wt": source_flag(panel).replace(0.0, np.nan),
        "C3 vol regime only, mom126": mom.where(vol_regime(panel) > 0),
        "C4 direction only, mom126": mom.where(up_day(panel) > 0),
        f"C5 frozen {frozen}": build_score(frozen, panel),
    }
    hdr = (f"{'ablation':<30}{'TRAIN CAGR%':>12}{'TR Sharpe':>11}"
           f"{'TEST CAGR%':>12}{'TE Sharpe':>11}{'TE MaxDD%':>11}{'TE turn':>9}")
    print(hdr)
    print("-" * len(hdr))
    for name, sc in abl.items():
        rt = run(panel, sc, TRAIN_START, TRAIN_END)
        re_ = run(panel, sc, TEST_START, TEST_END)
        m1, m2 = rt.metrics, re_.metrics
        print(f"{name:<30}{m1.cagr * 100:>12.2f}{m1.sharpe:>11.2f}"
              f"{m2.cagr * 100:>12.2f}{m2.sharpe:>11.2f}"
              f"{m2.max_drawdown * 100:>11.2f}{m2.annual_turnover:>9.2f}")
    b = bh_row("C6 buy-and-hold", "TEST", panel, TEST_START, TEST_END)
    rt = run(panel, mom, TRAIN_START, TRAIN_END)
    print(f"{'C6 buy-and-hold':<30}{rt.metrics.cagr * 100:>12.2f}"
          f"{rt.metrics.sharpe:>11.2f}{b.cagr * 100:>12.2f}{b.sharpe:>11.2f}"
          f"{b.maxdd * 100:>11.2f}{b.turnover:>9.2f}")
    print()

    # ------------------------------------------------------------------ #
    print("COST STRESS on the frozen variant (TEST)")
    sc = build_score(frozen, panel).loc[TEST_START:TEST_END]
    px = panel.loc[TEST_START:TEST_END]
    for name, cm in STRESS_MODELS.items():
        res = run_backtest(px, sc, cm, PORTFOLIO, rebalance="M")
        print(f"  {name:<18} rt={float(cm.all_in_round_trip_bps(100000)):6.2f}bps  "
              f"CAGR {res.metrics.cagr * 100:6.2f}%  Sharpe {res.metrics.sharpe:6.2f}  "
              f"MaxDD {res.metrics.max_drawdown * 100:7.2f}%")
    print()

    # ------------------------------------------------------------------ #
    print("BETA vs equal-weight market (TEST)")
    mkt = buy_and_hold(panel, TEST_START, TEST_END)["equity"].pct_change(
        fill_method=None).fillna(0.0)
    sr = run(panel, build_score(frozen, panel), TEST_START, TEST_END).returns
    j = pd.concat([sr, mkt], axis=1, keys=["s", "m"]).dropna()
    beta = float(np.cov(j["s"], j["m"])[0, 1] / np.var(j["m"], ddof=1))
    corr = float(j["s"].corr(j["m"]))
    print(f"  beta {beta:.2f}   daily corr {corr:.2f}   n {len(j)}")
    print()

    # ------------------------------------------------------------------ #
    print("SUB-PERIOD STABILITY of the flag itself (TEST)")
    p = panel.loc[TEST_START:TEST_END]
    rets = p.pct_change(fill_method=None)
    flag = source_flag(panel, 3.0 / 100).loc[TEST_START:TEST_END] > 0
    calm = vol_regime(panel, 0.03).loc[TEST_START:TEST_END] > 0
    up = up_day(panel).loc[TEST_START:TEST_END] > 0
    print("  next-day mean return by group (bps/day):")
    for nm, mask in [
        ("flagged (up-day & NATR<3%)", flag),
        ("up-day but HIGH vol", up & ~calm),
        ("calm but DOWN day", calm & ~up),
        ("neither", ~calm & ~up),
    ]:
        fwd = rets.shift(-1).where(mask)
        v = fwd.to_numpy()[np.isfinite(fwd.to_numpy())]
        print(f"    {nm:<28} n={len(v):6d}  mean {v.mean() * 10000:+7.2f} bps")

    print()
    print("  by calendar year (group mean next-day return, bps/day):")
    groups = {
        "flagged (up & NATR<3%)": flag,
        "up-day but HIGH vol": up & ~calm,
        "calm but DOWN day": calm & ~up,
        "neither": ~calm & ~up,
    }
    fwd_all = rets.shift(-1)
    year_arr = p.index.year.to_numpy()
    print(f"    {'year':<8}" + "".join(f"{g[:22]:>26}" for g in groups))
    for y in sorted(set(p.index.year)):
        sub = year_arr == y
        row = f"    {y:<8}"
        for _gname, gmask in groups.items():
            m = gmask.to_numpy(dtype=bool) & sub[:, None]
            v = fwd_all.to_numpy()[m]
            v = v[np.isfinite(v)]
            row += f"{(v.mean() * 10000) if len(v) else float('nan'):>16.2f}(n={len(v):>6d})"
        print(row)
    print()
    print("  TRAIN counterpart of the same table (diagnostic, TRAIN only):")
    pt = panel.loc[TRAIN_START:TRAIN_END]
    rt_ = pt.pct_change(fill_method=None)
    ft = source_flag(panel, 0.03).loc[TRAIN_START:TRAIN_END] > 0
    ct = vol_regime(panel, 0.03).loc[TRAIN_START:TRAIN_END] > 0
    ut = up_day(panel).loc[TRAIN_START:TRAIN_END] > 0
    fwd_t = rt_.shift(-1)
    for gname, gmask in [
        ("flagged (up & NATR<3%)", ft),
        ("up-day but HIGH vol", ut & ~ct),
        ("calm but DOWN day", ct & ~ut),
        ("neither", ~ct & ~ut),
    ]:
        v = fwd_t.where(gmask).to_numpy()
        v = v[np.isfinite(v)]
        print(f"    {gname:<28} n={len(v):7d}  mean {v.mean() * 10000:+7.2f} bps")


if __name__ == "__main__":
    main()
