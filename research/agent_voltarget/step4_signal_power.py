"""Step 4 — is the flag's information content distinguishable from zero?

TEST has already been consumed for the headline number, so this is a DIAGNOSTIC and
is labelled as such. It asks one question: are the four regime groups' mean next-day
returns actually distinguishable, and does the flagged group rank where a
low-volatility + continuation signal should rank?

Also records the group-level spread on TRAIN, where the same test can be run without
touching TEST at all, to show whether the TEST picture is a regime change or was
always there.
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, "research/agent_voltarget")

from harness import (  # noqa: E402
    TEST_END,
    TEST_START,
    TRAIN_END,
    TRAIN_START,
    assert_engine_pinned,
    load_panel,
    natr,
    up_day,
    vol_regime,
)


def table(panel: pd.DataFrame, lo, hi, thresh: float, label: str) -> None:
    p = panel.loc[lo:hi]
    rets = p.pct_change(fill_method=None)
    fwd = rets.shift(-1).to_numpy().ravel()
    groups = {
        "flagged (up-day & calm)": (up_day(panel).loc[lo:hi] > 0).to_numpy().ravel()
        & (vol_regime(panel, thresh).loc[lo:hi] > 0).to_numpy().ravel(),
        "up-day but HIGH vol": (up_day(panel).loc[lo:hi] > 0).to_numpy().ravel()
        & ~(vol_regime(panel, thresh).loc[lo:hi] > 0).to_numpy().ravel(),
        "calm but DOWN day": ~(up_day(panel).loc[lo:hi] > 0).to_numpy().ravel()
        & (vol_regime(panel, thresh).loc[lo:hi] > 0).to_numpy().ravel(),
        "neither": ~(up_day(panel).loc[lo:hi] > 0).to_numpy().ravel()
        & ~(vol_regime(panel, thresh).loc[lo:hi] > 0).to_numpy().ravel(),
    }
    print(f"--- {label} (NATR14 < {thresh * 100:.0f}%) ---")
    print(f"{'group':<26}{'n':>8}{'mean bps':>11}{'t-stat':>9}{'p':>10}")
    vals = {}
    for g, m in groups.items():
        v = fwd[m]
        v = v[np.isfinite(v)]
        vals[g] = v
        t, p_ = stats.ttest_1samp(v, 0.0)
        print(f"{g:<26}{len(v):>8}{v.mean() * 1e4:>11.2f}{t:>9.2f}{p_:>10.3f}")
    # Welch t-test: flagged vs the union of everything else
    other = np.concatenate([vals[g] for g in list(vals)[1:]])
    other = other[np.isfinite(other)]
    t, p_ = stats.ttest_ind(vals["flagged (up-day & calm)"], other, equal_var=False)
    d = vals["flagged (up-day & calm)"].mean() - other.mean()
    print(f"  flagged MINUS all-other-groups: {d * 1e4:+.2f} bps/day  "
          f"Welch t={t:.2f}  p={p_:.4f}")
    print()


def main() -> None:
    assert_engine_pinned()
    panel, _ = load_panel()
    print("=" * 78)
    print("STEP 4 — is the flag's information content non-zero? (DIAGNOSTIC)")
    print("=" * 78)
    print()
    table(panel, TRAIN_START, TRAIN_END, 0.03, "TRAIN")
    table(panel, TEST_START, TEST_END, 0.03, "TEST")
    table(panel, TRAIN_START, TRAIN_END, 0.02, "TRAIN, default target=0.01 (2%)")
    table(panel, TEST_START, TEST_END, 0.02, "TEST, default target=0.01 (2%)")

    print("=" * 78)
    print("DISTRIBUTION OF NATR — why 2% and 3% are not equivalent thresholds")
    print("=" * 78)

    for label, lo, hi in [("TRAIN", TRAIN_START, TRAIN_END),
                          ("TEST", TEST_START, TEST_END)]:
        v = natr(panel, 14).loc[lo:hi].to_numpy().ravel()
        v = v[np.isfinite(v)]
        print(f"  {label}: " + "  ".join(
            f"p{q}={np.percentile(v, q) * 100:.2f}%" for q in (5, 25, 50, 75, 95)))

    print()
    print("  fraction of name-days below each candidate threshold:")
    for thresh in (0.015, 0.02, 0.025, 0.03, 0.04, 0.05):
        fr_t = float((natr(panel, 14).loc[TRAIN_START:TRAIN_END] < thresh).to_numpy().mean())
        fr_e = float((natr(panel, 14).loc[TEST_START:TEST_END] < thresh).to_numpy().mean())
        print(f"    NATR < {thresh * 100:4.1f}%   TRAIN {fr_t * 100:5.1f}%   TEST {fr_e * 100:5.1f}%")


if __name__ == "__main__":
    main()
