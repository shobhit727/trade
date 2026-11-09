"""Step 02 — TRAIN-only diagnostics. No backtest, no TEST data.

1. Signal liveness: what fraction of bars does CMF exceed each threshold?
2. Cross-sectional IC of CMF vs forward return (TRAIN only) — is there any
   predictive content at all, before we spend a backtest on it?
3. How many names are flagged on a typical monthly rebalance date?
"""

from __future__ import annotations

import sys

sys.path.insert(0, "src")

import numpy as np
import pandas as pd

pd.set_option("display.width", 200)

TRAIN = ("2016-01-01", "2023-12-31")
TEST = ("2024-01-01", "2026-10-01")


def cmf_panel(closes, highs, lows, vols, period):
    rng = (highs - lows).replace(0.0, np.nan)
    mfm = ((closes - lows) - (highs - closes)) / rng
    num = (mfm * vols).rolling(period, min_periods=period).sum()
    den = vols.rolling(period, min_periods=period).sum()
    return num / den.replace(0.0, np.nan)


def ics(factor: pd.DataFrame, fwd: pd.DataFrame) -> pd.Series:
    """Per-day Spearman IC, then mean / t-stat / hit-rate."""
    rows = {}
    for d in factor.index:
        a = factor.loc[d]
        b = fwd.loc[d]
        m = a.notna() & b.notna()
        if m.sum() < 10:
            continue
        ra = a[m].rank()
        rb = b[m].rank()
        if ra.std() == 0 or rb.std() == 0:
            continue
        rows[d] = float(ra.corr(rb))
    s = pd.Series(rows)
    return s


def main() -> None:
    closes = pd.read_pickle("research/agent_cmf/_closes.pkl")
    highs = pd.read_pickle("research/agent_cmf/_highs.pkl")
    lows = pd.read_pickle("research/agent_cmf/_lows.pkl")
    vols = pd.read_pickle("research/agent_cmf/_vols.pkl")

    tr0 = pd.Timestamp(TRAIN[0], tz="Asia/Kolkata")
    tr1 = pd.Timestamp(TRAIN[1], tz="Asia/Kolkata")
    print("=" * 78)
    print("TRAIN WINDOW:", TRAIN, " (TEST is never touched in this script)")
    print("=" * 78)

    for period in (10, 20, 60):
        c = cmf_panel(closes, highs, lows, vols, period)
        ctr = c.loc[tr0:tr1]
        print(f"\n--- CMF period={period} ---")
        print(f"  coverage (non-NaN, TRAIN): {ctr.notna().mean().mean() * 100:5.1f}%")
        for thr in (0.10, 0.05, 0.00):
            long_frac = float((ctr > thr).sum().sum() / ctr.notna().sum().sum())
            short_frac = float((ctr < -thr).sum().sum() / ctr.notna().sum().sum())
            print(f"  thr={thr:+.2f}: long {long_frac * 100:5.2f}%  "
                  f"short {short_frac * 100:5.2f}%  "
                  f"either {100 * (long_frac + short_frac):5.2f}%")

        # ---- forward-return IC (TRAIN only)
        for h in (5, 21, 63):
            fwd = closes.shift(-h) / closes - 1.0
            ic = ics(c, fwd)
            ic = ic.loc[tr0:tr1]
            t = ic.mean() / (ic.std(ddof=1) / np.sqrt(len(ic))) if len(ic) > 2 else np.nan
            print(f"  IC({h:>2}d fwd, all names) n={len(ic):>4}  "
                  f"mean {ic.mean():+.5f}  t={t:+.2f}  "
                  f"hit {float((ic > 0).mean()) * 100:4.1f}%")

    # ---- how many names flagged per monthly rebalance date?
    print("\n--- flagged names per monthly rebalance date (TRAIN) ---")
    mom = closes / closes.shift(126) - 1.0
    for period, thr in ((20, 0.10), (20, 0.05), (20, 0.00), (10, 0.10), (60, 0.10)):
        c = cmf_panel(closes, highs, lows, vols, period)
        sig = (c > thr).loc[tr0:tr1]
        keys = sig.index.tz_localize(None).to_period("M")
        rb = [g.index[0] for _, g in pd.Series(sig.index, index=sig.index).groupby(keys)]
        n = sig.loc[rb].sum(axis=1)
        print(f"  period={period} thr={thr:+.2f}: rebalances={len(rb)}  "
              f"flagged min={int(n.min())} med={int(n.median())} "
              f"mean={n.mean():5.1f} max={int(n.max())}  "
              f"(<22 on {float((n < 22).mean()) * 100:.0f}% of dates)")

    # ---- benchmark sanity: equal-weight universe TRAIN
    r = closes.pct_change(fill_method=None).loc[tr0:tr1]
    ew = r.mean(axis=1)
    yrs = len(ew) / 244
    print("\n--- equal-weight universe, TRAIN ---")
    print(f"  total {((1 + ew.fillna(0)).prod() - 1) * 100:6.2f}%  "
          f"CAGR {(((1 + ew.fillna(0)).prod()) ** (1 / yrs) - 1) * 100:6.2f}%  "
          f"vol {ew.std() * np.sqrt(244) * 100:5.2f}%")


if __name__ == "__main__":
    main()
