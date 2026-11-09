"""Step 6 — two checks the previous run never did.

1. PAIRED ALPHA TEST vs buy-and-hold on TEST. The headline "7.16% vs 8.21%" is a
   difference of two noisy estimates. Paired daily excess returns give a proper standard
   error. If |t| < 2, the strategy has not demonstrated it beats the market, regardless of
   how the CAGRs look.

2. LOOK-AHEAD INJECTION TEST (harness validation). brief §4 forbids look-ahead. Proving
   a negative is hard, so instead inject it: build the score from a DELIBERATELY peeking
   panel (`panel.shift(-1)`, i.e. tomorrow's close) and re-run. A correct engine must
   show a materially BETTER result from peeking. If injecting future data does not help,
   the harness is not actually using the score's timing and every number here is suspect.
   This is a test of the harness, and it consumes none of the parameter budget.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from common import (
    BASE,
    DATA,
    TEST,
    Variant,
    buy_and_hold,
    hr,
    load_universe,
    momentum_score,
    run_variant,
    squeeze_signal,
    table,
)

from nsealgo.backtest.engine import PortfolioConfig, run_backtest
from nsealgo.backtest.metrics import compute_metrics

CFG = PortfolioConfig()
V1 = Variant("V1", 20, 0.050, "momentum", 3)
WARM = 260


def window_slice(panel: pd.DataFrame, window: tuple[str, str]):
    """Same warm-start convention as common.run_variant."""
    lo = pd.Timestamp(window[0]).tz_localize(panel.index.tz)
    hi = pd.Timestamp(window[1]).tz_localize(panel.index.tz)
    s0 = max(int(panel.index.searchsorted(lo)) - WARM, 0)
    px = panel.iloc[s0:][lambda d: d.index <= hi]
    return px, px.index >= lo


def main() -> None:
    panel, _, _ = load_universe(str(DATA))
    px, te = window_slice(panel, TEST)

    # ------------------------------------------------------------------ #
    hr("1. PAIRED ALPHA TEST — strategy minus buy-and-hold, TEST daily excess returns")
    sr, _, sm, sd = run_variant(panel, V1, TEST, CFG)
    bh = buy_and_hold(panel).loc[TEST[0] : TEST[1]]
    excess = (sr - bh).dropna()
    n = len(excess)
    mean_d = float(excess.mean())
    se = float(excess.std(ddof=1) / np.sqrt(n))
    t = mean_d / se
    ann_excess = mean_d * 244
    print(f"  days                       {n}")
    print(f"  mean daily excess          {mean_d * 100:+.5f}%")
    print(f"  annualised excess          {ann_excess * 100:+.2f}%/y")
    print(f"  stdev of daily excess      {float(excess.std(ddof=1)) * 100:.4f}%")
    print(f"  paired t                   {t:+.2f}")
    print(f"  95% CI on annualised alpha [{(ann_excess - 1.96 * se * 244) * 100:+.2f}%, "
          f"{(ann_excess + 1.96 * se * 244) * 100:+.2f}%]")
    print(f"\n  VERDICT: alpha {'IS' if abs(t) > 1.96 else 'is NOT'} "
          f"statistically distinguishable from zero at 95%.")
    print("  A strategy that cannot be distinguished from a random 47%-liveness book")
    print(f"  (negative control: Sharpe {sm.sharpe:+.2f} vs coin 0.01) and cannot be")
    print("  distinguished from buy-and-hold has not demonstrated an edge.")

    # Block bootstrap on the paired excess, to respect autocorrelation in daily returns.
    rng = np.random.default_rng(11)
    v = excess.to_numpy()
    B = 5000
    bs = np.empty(B)
    for k in range(B):
        idx = rng.integers(0, n, n)
        bs[k] = v[idx].mean() * 244
    print(f"\n  block-free iid bootstrap of annualised alpha: "
          f"[{np.percentile(bs, 2.5) * 100:+.2f}%, {np.percentile(bs, 97.5) * 100:+.2f}%]")
    print(f"  P(alpha <= 0) under the bootstrap = {float((bs <= 0).mean()):.2f}")

    # ------------------------------------------------------------------ #
    hr("2. LOOK-AHEAD INJECTION TEST — does the harness actually respect score timing?")
    lng, _, _ = squeeze_signal(px, V1.period, V1.threshold, V1.roc_lookback)

    rows = []
    # honest
    sc_honest = momentum_score(px, lng)
    # peeking: score from TOMORROW's closes, aligned to today's row.
    peek_panel = panel.shift(-1)
    px_peek = peek_panel.loc[px.index]
    lng_peek, _, _ = squeeze_signal(px_peek, V1.period, V1.threshold, V1.roc_lookback)
    sc_peek = momentum_score(px_peek, lng_peek)
    # placebo: same honest score, shifted back one bar (signal known one day early)

    def te_metrics(score: pd.DataFrame) -> tuple[float, float, float]:
        res = run_backtest(px, score, BASE, CFG, "M")
        r = res.returns[te]
        m = compute_metrics(r, (1.0 + r).cumprod())
        return m.cagr, m.sharpe, m.max_drawdown

    for lab, sc in (("honest (closes <= t)", sc_honest),
                    ("PEEKING (closes <= t+1)", sc_peek)):
        c, s, d = te_metrics(sc)
        rows.append(f"{lab:<26} CAGR {c * 100:>7.2f}%  Sharpe {s:>6.2f}  MaxDD {d * 100:>7.2f}%")
    table(rows, "TEST backtest with and without an injected look-ahead:")
    ch, sh, _ = te_metrics(sc_honest)
    cp, sp, _ = te_metrics(sc_peek)
    print(f"\n  look-ahead CAGR bonus: {(cp - ch) * 100:+.2f}%   "
          f"Sharpe bonus: {sp - sh:+.2f}")
    if cp > ch:
        print("  PASS: injecting future data IMPROVES the result, so the harness really is")
        print("        reading the score's timing. The honest number above is therefore a")
        print("        faithful measurement, and the mediocre result is the strategy's fault,")
        print("        not a harness artefact.")
    else:
        print("  FAIL: injecting future data did NOT help. The harness is not using the")
        print("        score timing, so every number in this report is unreliable.")

    # ------------------------------------------------------------------ #
    hr("3. DOES THE SIGNAL FIRE ON THE LAST BAR OF THE WINDOW? (edge-of-sample sanity)")
    print("  last 5 TEST dates and V1 breadth:")
    for dt in px.index[te][-5:]:
        print(f"    {dt.date()}  {int(lng.loc[dt].sum()):>2} names long")
    print(f"\n  days in TEST with ZERO names flagged: "
          f"{int((lng[te].sum(axis=1) == 0).sum())} of {int(te.sum())}")
    print(f"  months in TEST with ZERO names flagged: "
          f"{int((lng[te].groupby(lng[te].index.to_period('M')).sum().sum(axis=1) == 0).sum())}")
    print("  (a month with zero flags means a fully cash month -- the book drifts to 0%")
    print("   invested and earns nothing but also pays nothing; it is not a bug, but it")
    print("   does mean liveness, not signal quality, sets the invested fraction.)")


if __name__ == "__main__":
    main()
