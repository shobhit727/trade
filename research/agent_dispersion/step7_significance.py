"""Step 7: is the underperformance statistically distinguishable from noise?

The headline gap to buy-and-hold (-4.33 pp/yr) is large. The gap to the *random*
control (-0.50 pp/yr) is not obviously large, and a strategy that merely ties a coin
flip is a different claim from one that loses to it. Test both properly on TEST:

  1. paired t-test, strategy vs buy-and-hold daily returns
  2. one-sample t-test, strategy daily return vs 0
  3. strategy vs each random seed, paired
  4. bootstrap CI on the CAGR difference vs buy-and-hold

Significance is judged on the TEST window only as a *description of the already
reported result*, not as a selection surface.
"""

from __future__ import annotations

import sys

sys.path.insert(0, "src")
sys.path.insert(0, "research/agent_dispersion")

from signal import dispersion_score, dispersion_signal  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import stats  # noqa: E402
from step2_run import (  # noqa: E402
    COST,
    TEST_END,
    TEST_START,
    buy_and_hold,
    slice_window,
)

from nsealgo.backtest.engine import PortfolioConfig, run_backtest  # noqa: E402
from nsealgo.data.loader import load_universe  # noqa: E402

SEL = {"period": 250, "entry": 1.0}
RNG = np.random.default_rng(12345)
BOOT = 20_000


def cagr_from(r: pd.Series, eq: pd.Series | None = None) -> float:
    if eq is None:
        eq = (1.0 + r.fillna(0.0)).cumprod()
    return float(eq.iloc[-1] ** (244.0 / len(r)) - 1.0)


def main() -> None:
    panel, _, _ = load_universe("data/nse")
    long_sig, _ = dispersion_signal(panel, period=SEL["period"], entry=SEL["entry"])
    score_full = dispersion_score(panel, long_sig, mom_days=126)

    win = slice_window(panel, TEST_START, TEST_END)
    score = slice_window(score_full, TEST_START, TEST_END)
    strat = run_backtest(win, score, COST, config=PortfolioConfig())
    r_s = strat.returns

    bh = buy_and_hold(panel, TEST_START, TEST_END)
    r_b = bh["_returns"]

    # random controls at the TEST liveness, same recipe
    lf = float(slice_window(long_sig.astype(float), TEST_START,
                            TEST_END).mean().mean())
    ctrl = []
    for _seed in (11, 22, 33):
        mask = RNG.random(panel.shape) < lf
        ls = pd.DataFrame(mask, index=panel.index, columns=panel.columns)
        sc = slice_window(dispersion_score(panel, ls, mom_days=126),
                          TEST_START, TEST_END)
        ctrl.append(run_backtest(win, sc, COST,
                                 config=PortfolioConfig()).returns)

    print("=" * 88)
    print(f"TEST {TEST_START.date()} -> {TEST_END.date()}, {len(r_s)} sessions")
    print(f"strategy CAGR {cagr_from(r_s, strat.equity):.2%}   "
          f"buy&hold CAGR {bh['cagr']:.2%}   random mean CAGR "
          f"{np.mean([cagr_from(c) for c in ctrl]):.2%}")
    print("=" * 88)

    # Align every series on the strategy's own index. `run_backtest` and
    # `buy_and_hold` can differ by a session, so never t-test raw arrays.
    idx = r_s.index
    a_s = r_s.reindex(idx)
    a_b = r_b.reindex(idx)

    # 1 + 2
    pair_bh = pd.concat([a_s, a_b], axis=1, keys=["s", "b"]).dropna()
    a_s, a_b = pair_bh["s"], pair_bh["b"]
    d_bh = a_s - a_b
    t1, p1 = stats.ttest_rel(a_s, a_b)
    t2, p2 = stats.ttest_1samp(a_s, 0.0)
    print("\n1. strategy MINUS buy-and-hold, daily (paired)")
    print(f"   mean daily gap {d_bh.mean():.5f}  t={t1:.2f}  p={p1:.2e}  "
          f"-> {'SIGNIFICANT' if p1 < 0.05 else 'not significant'} at 5%")
    print("2. strategy daily return vs 0 (one-sample)")
    print(f"   mean daily {r_s.mean():.5f}  t={t2:.2f}  p={p2:.4f}  "
          f"-> {'SIGNIFICANT' if p2 < 0.05 else 'NOT significant'} at 5%")

    # 3
    print("\n3. strategy MINUS each random control, daily (paired)")
    for seed, c in zip((11, 22, 33), ctrl, strict=True):
        pair = pd.concat([a_s, c.reindex(idx)], axis=1,
                         keys=["s", "c"]).dropna()
        d = pair["s"] - pair["c"]
        t, p = stats.ttest_rel(pair["s"], pair["c"])
        print(f"   seed {seed}: mean daily gap {d.mean():+.5f}  t={t:+.2f}  "
              f"p={p:.3f}  -> {'sig' if p < 0.05 else 'NOT sig'}")
    print("   -> a tie with a coin flip is the honest description if these are "
          "not significant.")

    # 4
    print(f"\n4. bootstrap ({BOOT:,} resamples) on CAGR gap vs buy-and-hold")
    a = a_s.to_numpy()
    b = a_b.to_numpy()
    n = len(a)
    diffs = np.empty(BOOT)
    for i in range(BOOT):
        idx = RNG.integers(0, n, n)
        diffs[i] = (cagr_from(pd.Series(a[idx])) - cagr_from(pd.Series(b[idx])))
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    print(f"   observed gap {cagr_from(r_s, strat.equity) - bh['cagr']:+.2%}")
    print(f"   bootstrap mean {diffs.mean():+.2%}   95% CI [{lo:+.2%}, {hi:+.2%}]")
    print(f"   P(strategy beats buy-and-hold) = {(diffs > 0).mean():.4f}")

    # 5. how much of the gap is the cash buffer + caps vs the signal itself
    print("\n5. Decomposition of the gap to buy-and-hold (from step6 ladder)")
    naive = 0.0467  # step6 row 1: equal weight, no caps, no budget, fully costed
    print(f"   naive construction of the SAME signal : {naive:.2%}")
    print(f"   engine (all constraints)              : {cagr_from(r_s, strat.equity):.2%}")
    print(f"   buy-and-hold                          : {bh['cagr']:.2%}")
    print(f"   -> signal loses {bh['cagr'] - naive:+.2%} vs market; engine features "
          f"cost a further {naive - cagr_from(r_s, strat.equity):.2%}")
    print("   -> most of the shortfall is the SIGNAL, not the portfolio machinery.")


if __name__ == "__main__":
    main()
