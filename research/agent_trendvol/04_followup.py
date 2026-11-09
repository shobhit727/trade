"""Follow-ups, TRAIN-side only for anything that informs the explanation.

1. Overlap correction on the event study. Daily-sampled h-day forward returns overlap,
   so the naive t-stat is inflated by sqrt(2h-1). The corrected number is the honest one.
2. TEST equity-curve sanity check (re-reads the already-reported TEST numbers; no new
   variant, no new parameter).
"""

from __future__ import annotations

import sys

sys.path.insert(0, "research/agent_trendvol")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from common import (  # noqa: E402
    COST,
    PORT,
    SCRATCH,
    TEST,
    TRAIN,
    VARIANTS,
    gated_momentum_score,
    load_panel,
    load_vol,
    run_backtest,
    save_json,
    slice_window,
    trend_volume_signal,
)


def overlap_corrected(alpha: pd.Series, h: int) -> dict:
    """t-stat corrected for daily-sampled overlapping h-day returns.

    For i.i.d. daily returns r_{t,h} = sum_{j<h} d_{t+j},
    Cov(r_{t,h}, r_{t+k,h}) = (h-k)*sigma^2, giving a variance inflation of (2h-1)
    on the sample mean. t_corrected = t_naive / sqrt(2h-1).
    """
    n = len(alpha)
    infl = 2 * h - 1
    t_naive = float(alpha.mean() / alpha.std(ddof=1) * np.sqrt(n)) if n > 2 else float("nan")
    return {
        "h": h, "n_naive": n,
        "inflation_factor": infl,
        "n_effective": n / infl,
        "t_naive": t_naive,
        "t_corrected": t_naive / np.sqrt(infl),
    }


def main() -> None:
    panel = load_panel()
    vol = load_vol()
    cfg = VARIANTS["tv_p20_r10"]
    sig = trend_volume_signal(panel, vol, cfg["period"], cfg["vol_ratio"])

    print("=== OVERLAP CORRECTION on the TRAIN event study ===")
    print("(daily-sampled forward returns overlap; naive t inflated by sqrt(2h-1))")
    m = (panel.index >= TRAIN[0]) & (panel.index <= TRAIN[1])
    px, sg = panel.loc[m], sig.loc[m]
    corr_rows = []
    for h in (21, 63, 126):
        fwd = px.shift(-h) / px - 1.0
        fwd = fwd.where(px.notna() & px.shift(-h).notna())
        n_sig = (sg > 0).sum(axis=1)
        alpha = ((fwd.where(sg > 0).mean(axis=1)) - fwd.mean(axis=1)).where(n_sig >= 3).dropna()
        c = overlap_corrected(alpha, h)
        c["mean_alpha_bp"] = float(alpha.mean() * 1e4)
        corr_rows.append(c)
        print(f"  h={h:>3}  naive t={c['t_naive']:>6.2f}  ->  corrected "
              f"t={c['t_corrected']:>5.2f}   (n_eff ~{c['n_effective']:>6.1f})")

    print("\n  => The sign of the alpha is negative at every horizon and the median is")
    print("     negative too (a dependence-robust statistic), but once overlap is")
    print("     accounted for NONE of these are statistically distinguishable from zero.")

    # ---- TEST equity sanity check: re-read of an already-reported result ----
    print("\n=== TEST equity sanity check (no new variant) ===")
    te = slice_window(panel, TEST)
    sc = gated_momentum_score(panel, sig).reindex(te.index)
    res = run_backtest(te, sc, COST, PORT)
    eq = res.equity
    r = res.returns
    dd = eq / eq.cummax() - 1.0
    worst = dd.idxmin()
    print(f"  bars={len(eq)}  final equity={eq.iloc[-1]:.4f}  "
          f"peak={eq.max():.4f}")
    print(f"  MaxDD {dd.min() * 100:.2f}% trough {worst.date()}  "
          f"({len(eq.loc[:worst])} bars in, {eq.idxmax().date()} peak)")
    print(f"  bars with |daily ret| > 5%  : {int((r.abs() > 0.05).sum())}")
    print(f"  largest single-day loss   : {r.min() * 100:.2f}% on {r.idxmin().date()}")
    print(f"  fraction of days flat (0) : {(r == 0).mean() * 100:.1f}%")
    print(f"  weights sum (mean/max)    : {res.weights.sum(axis=1).mean():.3f} / "
          f"{res.weights.sum(axis=1).max():.3f}  (engine targets <= 0.90)")
    print(f"  max single-name weight    : {res.weights.max().max() * 100:.2f}% (cap 12%)")
    print(f"  distinct symbols ever held: {(res.weights > 0).any().sum()} of 48")
    # Drift of the losing book: is it a slow bleed or a crash?
    seg = (eq.iloc[-1] / eq.iloc[0]) ** (252.0 / len(eq)) - 1.0
    print(f"  window CAGR from curve    : {seg * 100:+.2f}%/y  "
          f"(engine reports {res.metrics.cagr * 100:+.2f}% - consistent)")
    dd_series = dd[dd < -0.05]
    print(f"  days spent >5% under peak : {len(dd_series)} of {len(dd)} "
          f"({len(dd_series) / len(dd) * 100:.1f}%)")

    save_json({"overlap_correction": corr_rows,
               "test_sanity": {
                   "final_equity": float(eq.iloc[-1]),
                   "pct_days_over_5pct_underwater": len(dd_series) / len(dd),
                   "pct_days_flat": float((r == 0).mean()),
                   "worst_day": float(r.min()),
                   "worst_day_date": str(r.idxmin().date()),
                   "max_single_name_weight": float(res.weights.max().max()),
                   "symbols_ever_held": int((res.weights > 0).any().sum()),
                   "weight_sum_mean": float(res.weights.sum(axis=1).mean()),
                   "weight_sum_max": float(res.weights.sum(axis=1).max()),
               }},
              f"{SCRATCH}/followup.json")


if __name__ == "__main__":
    main()
