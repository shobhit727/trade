"""Step 11 — TRAIN-only: reproduce the diagnostics that justified the budget.

Verifies the IC / liveness table quoted in REPORT.md §2 against a fresh rebuild.
TEST is not read for anything except its date bound.
"""

from __future__ import annotations

import sys

sys.path.insert(0, "research/agent_cmf")

import numpy as np
import pandas as pd
from cmflib import TRAIN0, TRAIN1, banner, cmf_panel, ic_summary, load_panels, show, spearman_ic


def main() -> None:
    closes, highs, lows, vols = load_panels()
    lo, hi = TRAIN0, TRAIN1

    banner("TRAIN-ONLY DIAGNOSTIC — CMF liveness and information coefficient\n"
           "window 2016-01-01 -> 2023-12-31   (TEST untouched)")

    ic_rows, live_rows = [], []
    fwd = {h: closes.shift(-h) / closes - 1.0 for h in (5, 21, 63)}

    for period in (10, 20, 60):
        c = cmf_panel(closes, highs, lows, vols, period)
        ctr = c.loc[lo:hi]
        cov = float(ctr.notna().mean().mean() * 100)
        for thr in (0.10, 0.05, 0.00):
            lf = float((ctr > thr).sum().sum() / ctr.notna().sum().sum())
            sf = float((ctr < -thr).sum().sum() / ctr.notna().sum().sum())
            live_rows.append({"period": period, "thr": f"{thr:+.2f}",
                              "coverage_pct": round(cov, 1),
                              "long_pct": round(lf * 100, 2),
                              "short_pct": round(sf * 100, 2),
                              "either_pct": round((lf + sf) * 100, 2)})
        for h in (5, 21, 63):
            ic = spearman_ic(c, fwd[h]).loc[lo:hi]
            s = ic_summary(ic)
            ic_rows.append({"period": period, "fwd_h": f"{h:>2}d", **{
                k: (round(v, 5) if k == "mean" else round(v, 2) if k == "t"
                    else round(v, 1) if k == "hit_pct" else v)
                for k, v in s.items()}})

    show(pd.DataFrame(live_rows), "SIGNAL LIVENESS — fraction of TRAIN bars long/short")
    show(pd.DataFrame(ic_rows),
         "INFORMATION COEFFICIENT (Spearman, all names, TRAIN only)\n"
         "negative = LOW CMF predicts HIGHER forward return")

    # ---- how many names are flagged on a monthly rebalance date?
    banner("FLAGGED NAMES PER MONTHLY REBALANCE DATE (TRAIN)")
    rows = []
    for period, thr in ((20, 0.10), (20, 0.05), (20, 0.00), (10, 0.10), (60, 0.10)):
        c = cmf_panel(closes, highs, lows, vols, period)
        sig = (c > thr).loc[lo:hi]
        keys = sig.index.tz_localize(None).to_period("M")
        rb = [g.index[0] for _, g in pd.Series(sig.index, index=sig.index).groupby(keys)]
        n = sig.loc[rb].sum(axis=1)
        rows.append({"period": period, "thr": f"{thr:+.2f}", "rebalances": len(rb),
                     "min": int(n.min()), "median": int(n.median()),
                     "mean": round(float(n.mean()), 1), "max": int(n.max()),
                     "pct_dates_lt22": f"{float((n < 22).mean()) * 100:.0f}%"})
    show(pd.DataFrame(rows), "capacity check vs the 22-name book")

    # ---- equal-weight universe TRAIN, no costs
    r = closes.pct_change(fill_method=None).loc[lo:hi].mean(axis=1).fillna(0.0)
    yrs = len(r) / 244
    banner("TRAIN equal-weight universe (no costs, no selection) — market context")
    print(f"  total {(float((1 + r).prod()) - 1) * 100:7.2f}%   "
          f"CAGR {(float((1 + r).prod()) ** (1 / yrs) - 1) * 100:6.2f}%   "
          f"vol {r.std() * np.sqrt(244) * 100:5.2f}%")


if __name__ == "__main__":
    main()
