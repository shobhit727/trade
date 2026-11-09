"""Step 06 — is there ANY forward-return content in this signal? (TRAIN only)

Portfolio-level backtests are a blunt instrument for answering "does this signal carry
information at all?". The sharp question is the rank information coefficient: on each
day, do the more-oversold names go on to outperform the rest over the next month?

If IC is ~0 there is nothing for any portfolio construction to harvest, and the
recommendation is to stop rather than to tune. This is measured on TRAIN only, so it
does not touch the TEST read that has already been reported.

Also compares the *time-series* z (the catalog's own) against a *cross-sectional* z
(today's oversoldness relative to the rest of the board), because a time-series z on a
price level is heavily contaminated by an ongoing trend.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from common import train_panel, ts_zscore

HERE = Path(__file__).resolve().parent
SEL = json.loads((HERE / "selected_variant.json").read_text())
HORIZONS = (5, 21, 63)


def rank_ic(x: pd.DataFrame, fwd: pd.DataFrame) -> pd.Series:
    """Per-day Spearman rank correlation between x and forward return."""
    out = {}
    for d in x.index:
        a = x.loc[d]
        b = fwd.loc[d]
        m = a.notna() & b.notna()
        if int(m.sum()) < 20:
            continue
        av, bv = a[m].to_numpy(), b[m].to_numpy()
        if np.std(av) == 0 or np.std(bv) == 0:
            continue
        ra = pd.Series(av).rank().to_numpy()
        rb = pd.Series(bv).rank().to_numpy()
        out[d] = float(np.corrcoef(ra, rb)[0, 1])
    return pd.Series(out, dtype=float)


def tstat(x: pd.Series) -> tuple[float, float]:
    x = x.dropna()
    n = len(x)
    if n < 3:
        return float("nan"), float("nan")
    mu = float(x.mean())
    se = float(x.std(ddof=1) / np.sqrt(n))
    return mu, (mu / se if se > 0 else float("nan"))


def main() -> None:
    tr = train_panel()
    L = SEL["L"]

    # Signals. ts_z is the catalog's own. xs_z is the cross-sectional alternative.
    ts_z = ts_zscore(tr, L)
    # `tr - series` aligns on COLUMNS, not rows, so this must be explicit `.sub(axis=0)`
    # (as `zscore_cross_sectional` does). Getting it wrong yields an all-NaN panel and a
    # silently empty IC — which is what the first run of this script did.
    mu_x = tr.mean(axis=1)
    sd_x = tr.std(axis=1, ddof=0).replace(0.0, np.nan)
    xs_z = tr.sub(mu_x, axis=0).div(sd_x, axis=0)
    assert xs_z.notna().to_numpy().any(), "cross-sectional z is all NaN — alignment bug"

    print(f"TRAIN only: {tr.index[0].date()} .. {tr.index[-1].date()}")
    print(f"lookback L = {L} (selected variant {SEL['id']})\n")

    print("Rank IC — signal vs forward return.")
    print("Positive IC = the signal correctly predicts forward returns.")
    print("For a LONG-ONLY book we want to buy LOW-scoring names, so the")
    print("usable direction is: higher IC for the score we actually rank on.\n")

    results = {}
    for h in HORIZONS:
        fwd = tr.shift(-h) / tr - 1.0
        print(f"--- forward {h}d return ---")
        for name, sig in (("time-series z (catalog)", ts_z),
                          ("cross-sectional z", xs_z)):
            for direction, s in (("raw", sig), ("negated (-z, what we buy)", -sig)):
                ic = rank_ic(s, fwd)
                mu, t = tstat(ic)
                sig_star = "***" if abs(t) > 2.58 else ("**" if abs(t) > 1.96 else
                                                         ("*" if abs(t) > 1.645 else ""))
                print(f"  {name:<24} {direction:<24} IC {mu:+.4f}  t {t:>+6.2f} {sig_star:<3}"
                      f"  (n={len(ic)})")
                results[f"{name}|{direction}|{h}d"] = {"ic": mu, "t": t, "n": len(ic)}
        print()

    print("Reading: IC in the 'negated' row is the one the book monetises, because")
    print("score = percentile rank of -z. |t| > 1.65/1.96/2.58 ~ 10/5/1% significance.")
    print("An IC indistinguishable from 0 means there is no information content to")
    print("harvest, and no portfolio construction can manufacture any.")

    (HERE / "forward_ic.json").write_text(json.dumps(results, indent=2))
    print("\nwrote forward_ic.json")


if __name__ == "__main__":
    main()
