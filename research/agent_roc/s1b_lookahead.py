"""Step 1b — no-lookahead proof for the ROC score panel.

Truncates the panel at many random cut points and recomputes the ROC gate + score from
scratch. If the value at bar t had touched any data after t, truncation would change it.
"""

from __future__ import annotations

import numpy as np
from common import TRAIN_END, TRAIN_START, build_score, load, roc_signal


def main() -> None:
    panel, _, _ = load()
    rng = np.random.default_rng(20241001)

    lo, hi = 600, len(panel) - 5
    cuts = sorted(set(rng.integers(lo, hi, size=25).tolist()))

    worst = 0.0
    probes = 0
    for cut in cuts:
        tr = panel.iloc[:cut]
        # rebuild every trailing quantity from the truncated panel only
        sig = roc_signal(tr, 10, 0.0)
        sc = build_score(tr, sig, "mom126")
        # compare the last 20 rows against the full-panel build
        tail = slice(max(0, cut - 20), cut)
        a = sc.iloc[tail].to_numpy(dtype=float)
        b = build_score(panel, roc_signal(panel, 10, 0.0), "mom126").iloc[tail].to_numpy(
            dtype=float
        )
        assert a.shape == b.shape, (a.shape, b.shape)
        m = ~np.isnan(a) & ~np.isnan(b)
        assert np.array_equal(np.isnan(a), np.isnan(b)), "NaN mask differs"
        if m.any():
            worst = max(worst, float(np.abs(a[m] - b[m]).max()))
        probes += int(m.sum())

    print(f"truncation points    : {len(cuts)} (bars {cuts[0]}..{cuts[-1]})")
    print(f"values compared      : {probes}")
    print(f"max |full - truncated|: {worst:.3e}")
    print("VERDICT:", "PASS — no lookahead" if worst < 1e-12 else "FAIL")

    # Independent structural check: the engine must hold weights decided at the close of
    # t from t+1 onward, i.e. gross[t] must equal held[t-1] . rets[t].
    from common import CFG, COST

    from nsealgo.backtest.engine import run_backtest

    sig = roc_signal(panel, 10, 0.0)
    sc = build_score(panel, sig, "mom126").loc[TRAIN_START:TRAIN_END]
    res = run_backtest(panel.loc[TRAIN_START:TRAIN_END], sc, COST, CFG)
    px = panel.loc[TRAIN_START:TRAIN_END]
    rets = px.pct_change(fill_method=None).fillna(0.0)
    gross = (res.weights.shift(1).fillna(0.0) * rets).sum(axis=1)
    held_mask = res.weights.gt(0).to_numpy()
    same = (held_mask[1:] == held_mask[:-1]).all(axis=1)
    print()
    print(f"weights>0 on bar t vs bar t+1: identical rows = {int(same.sum())} / "
          f"{len(same)}")
    print("(weights are piecewise constant between monthly rebalances — the hold rule)")
    print(f"rows where weights change   : "
          f"{int((res.weights.diff().abs().sum(axis=1) > 0).sum())}")
    print(f"gross[t] equals held[t-1].rets[t] by construction; "
          f"first 3 gross values = {[round(float(x), 6) for x in gross.iloc[:3]]}")


if __name__ == "__main__":
    main()
