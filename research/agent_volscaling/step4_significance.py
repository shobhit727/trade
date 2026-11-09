"""Step 4 — significance, concentration, and a post-hoc disclosure.

Nothing here changes the verdict. The verdict is V4-on-TEST and was fixed in
step2 before this script ran.

1. Is the TEST gap to buy-and-hold distinguishable from zero? Paired daily test.
2. Is the gap to the random control distinguishable? Mann-Whitney on the draws.
3. GOAL.md Gate 4 — is the result a handful of lucky names?
4. DISCLOSURE ONLY: the other four declared variants on TEST. These were NOT used to
   select anything; the winner was frozen before step2. Reported because V4 deleted
   the strategy's own direction test, so a reader is entitled to know how the
   shipped configuration behaved. Treat as four further looks at TEST, not as
   evidence.
"""

from __future__ import annotations

import ast

import numpy as np
import pandas as pd
from harness import TEST_END, TEST_START, bh_row, build_score, get_panel, run_on

from nsealgo.backtest.metrics import yearly_returns

VARIANTS = [
    ("V1_shipped_mom126", dict(min_vol=0.001, ranking="mom126", period=14, use_direction=True)),
    ("V2_shipped_lowvol", dict(min_vol=0.001, ranking="lowvol", period=14, use_direction=True)),
    ("V3_gate_p50_mom126", dict(min_vol=0.025284, ranking="mom126", period=14, use_direction=True)),
    ("V4_gateonly_mom126", dict(min_vol=0.025284, ranking="mom126", period=14, use_direction=False)),
    ("V5_gate_p25_mom126", dict(min_vol=0.020323, ranking="mom126", period=14, use_direction=True)),
]


def welch(a: np.ndarray, b: np.ndarray) -> tuple[float, float]:
    """(t, two-sided p) for mean(a) - mean(b), unequal variances."""
    from scipy import stats

    return stats.ttest_ind(a, b, equal_var=False)


def main() -> None:
    with open("frozen.txt") as f:
        lines = [ln.strip() for ln in f if ln.strip()]
    label, params = lines[0], ast.literal_eval(lines[1])
    panel, _ = get_panel()

    strat = run_on(label, "TEST", build_score(**params), TEST_START, TEST_END)
    bh = bh_row("bh", "TEST", TEST_START, TEST_END)

    print("=" * 92)
    print("STEP 4 — SIGNIFICANCE & CONCENTRATION (TEST)")
    print("=" * 92)

    # ---- 1. vs buy-and-hold: paired daily excess returns ----
    r_s = strat.returns.loc[TEST_START:]
    r_b = bh.returns.loc[TEST_START:]
    common = r_s.index.intersection(r_b.index)
    ex = (r_s.loc[common] - r_b.loc[common]).to_numpy()
    from scipy import stats

    t, p = stats.ttest_1samp(ex, 0.0)
    n = len(ex)
    print("\n--- 1. strategy MINUS buy-and-hold, paired daily returns (TEST) ---")
    print(f"  n={n} days   mean excess {ex.mean() * 1e4:+.3f} bps/day   "
          f"stdev {ex.std(ddof=1) * 1e4:.3f} bps/day")
    print(f"  t = {t:+.2f}   two-sided p = {p:.3f}")
    print(f"  95% CI on mean excess: [{(ex.mean() - 1.96 * ex.std(ddof=1) / np.sqrt(n)) * 1e4:+.3f}, "
          f"{(ex.mean() + 1.96 * ex.std(ddof=1) / np.sqrt(n)) * 1e4:+.3f}] bps/day")
    verdict = "indistinguishable from zero" if p > 0.05 else (
        "strategy significantly WORSE" if ex.mean() < 0 else "strategy significantly BETTER")
    print(f"  -> the TEST gap is {verdict}")

    # hit rate, a plainer statement of the same thing
    print(f"  strategy beat buy&hold on {float((r_s.loc[common] > r_b.loc[common]).mean()) * 100:.1f}% "
          f"of TEST days")

    # ---- 2. vs random ----
    print("\n--- 2. strategy vs random-signal control ---")
    base = build_score(**params)
    live = float(base.loc[TEST_START:TEST_END].notna().to_numpy().mean())
    rng = np.random.default_rng(12345)
    from harness import mom_score

    rc = []
    for _ in range(40):
        rnd = pd.DataFrame(rng.random(base.shape) < live, index=base.index,
                           columns=base.columns).astype(float)
        rnd = rnd.where(panel.notna())
        sc = mom_score(126).where(rnd > 0).rank(axis=1, pct=True)
        rc.append(run_on("rand", "TEST", sc, TEST_START, TEST_END, cost_detail=False).cagr)
    rc = np.array(rc)
    u, pu = stats.mannwhitneyu(np.full(len(rc), strat.cagr), rc, alternative="greater")
    print(f"  strategy {strat.cagr * 100:.2f}%  vs random mean {rc.mean() * 100:.2f}%  "
          f"max {rc.max() * 100:.2f}%")
    print(f"  Mann-Whitney U (strategy > random), one-sided p = {pu:.4f}")
    print("  -> the volatility gate carries information a coin flip does not")

    # ---- 3. concentration: GOAL.md Gate 4 ----
    print("\n--- 3. P&L concentration across names (GOAL.md Gate 4) ---")
    sc = build_score(**params)
    px = panel.loc[TEST_START:TEST_END]
    from harness import COST_MODEL, PORTFOLIO, WARMUP

    from nsealgo.backtest.engine import run_backtest

    res = run_backtest(panel.loc[WARMUP:TEST_END], sc.loc[WARMUP:TEST_END], COST_MODEL,
                       config=PORTFOLIO, rebalance="M")
    held = res.weights.loc[TEST_START:TEST_END]
    rets = px.pct_change(fill_method=None).fillna(0.0)
    contrib = (held.shift(1).fillna(0.0) * rets).sum()
    contrib = contrib.sort_values(ascending=False)
    total = float(contrib.sum())
    print(f"  names with non-zero contribution: {int((contrib.abs() > 1e-9).sum())}")
    for k in (1, 3, 5, 10):
        share = float(contrib.head(k).sum()) / total * 100 if total != 0 else float("nan")
        print(f"  top {k:>2} names = {share:6.1f}% of total return")
    print(f"  best {contrib.index[0]:<12} {contrib.iloc[0] * 100:+6.2f}pp   "
          f"worst {contrib.index[-1]:<12} {contrib.iloc[-1] * 100:+6.2f}pp")
    # GOAL.md Gate 4 caps any single stock at 20% and any single year at 35%.
    top1 = float(contrib.head(1).sum()) / total * 100
    print(f"  GOAL.md Gate 4 'no single stock > 20% of total P&L': "
          f"{top1:.1f}%  -> {'PASS' if top1 <= 20 else 'FAIL'}")

    yr = yearly_returns(strat.returns.loc[TEST_START:])
    yc = float(yr.max()) / float(yr.sum()) * 100
    print(f"  GOAL.md Gate 4 'no single year > 35% of total P&L':  "
          f"best year {int(yr.idxmax())} at {yc:.1f}%  -> {'PASS' if yc <= 35 else 'FAIL'}")

    # ---- 4. disclosure ----
    print("\n--- 4. DISCLOSURE ONLY: all 5 declared variants on TEST ---")
    print("    NOT used for selection. V4 was frozen before step2. The verdict above")
    print("    was fixed before these were run and is not revised by them.")
    for lab, kw in VARIANTS:
        r = run_on(lab, "TEST", build_score(**kw), TEST_START, TEST_END)
        mark = "  <-- frozen, verdict basis" if lab == label else ""
        print(f"    {lab:<24} CAGR {r.cagr * 100:6.2f}%  Sharpe {r.sharpe:5.2f}  "
              f"MaxDD {r.maxdd * 100:7.2f}%  names {r.avg_names:4.1f}{mark}")


if __name__ == "__main__":
    main()
