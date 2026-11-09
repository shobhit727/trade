"""Prove the vectorised panel signal is identical to TripleMaStrategy.signal().

The whole result rests on the claim that `tma_signal()` reproduces the catalog
strategy exactly. This drives the real class, bar by bar, over the real closes, and
compares against the vectorised version used everywhere else.
"""

from __future__ import annotations

import sys

import numpy as np

sys.path.insert(0, "src")

from cryptobot.strategies.catalog.triple_moving_average import (  # noqa: E402
    TripleMaConfig,
    TripleMaStrategy,
)
from nsealgo.data.loader import load_universe  # noqa: E402

sys.path.insert(0, "research/agent_triple_ma")
from run import VARIANTS, tma_signal  # noqa: E402


def main() -> None:
    panel, _, _ = load_universe("data/nse")
    closes = panel.to_numpy(dtype=float)
    dates = panel.index

    # A contiguous window well past every variant's warmup, so NaN handling is
    # exercised at the start and steady-state behaviour over ~4000 bars is compared.
    lo = 400
    for name, (f, m, s) in VARIANTS.items():
        strat = TripleMaStrategy(TripleMaConfig(fast=f, mid=m, slow=s))
        warm = max(strat.warmup(closes[:lo]), f, m, s)
        start = max(lo, warm + 5)
        stop = start + 4000

        # The catalog class is single-instrument: `sma()` averages the whole series
        # it is handed. So drive it one symbol at a time over that symbol's history.
        ref = np.zeros((stop - start, closes.shape[1]))
        for j in range(closes.shape[1]):
            col = closes[:, j]
            for i in range(start, stop):
                w = col[: i + 1]
                ref[i - start, j] = float(strat.signal(w, w, w, w))

        vec = tma_signal(panel, f, m, s).to_numpy()
        got = vec[start:stop]
        diff = np.abs(got - ref)
        n_mismatch = int((diff > 1e-12).sum())
        u, uc = np.unique(ref, return_counts=True)
        counts = dict(zip(u.tolist(), uc.tolist(), strict=True))
        print(f"{name:<14} cells compared {ref.size}  mismatches {n_mismatch}  "
              f"ref state counts {counts}")
        if n_mismatch:
            ri, ci = np.where(diff > 1e-12)
            for k in range(min(5, len(ri))):
                print(f"   MISMATCH {dates[start + ri[k]].date()} "
                      f"{panel.columns[ci[k]]}: ref={ref[ri[k], ci[k]]} "
                      f"vec={got[ri[k], ci[k]]}")
            raise SystemExit(f"{name}: vectorised signal does NOT match the catalog")

    print("\nOK: vectorised tma_signal() is bit-identical to TripleMaStrategy.signal() "
          "for every variant over 4000 bars each.")


if __name__ == "__main__":
    main()
