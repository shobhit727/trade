"""Cross-check: my vectorised %R vs the real cryptobot indicator, bar for bar."""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "src")
from cryptobot.strategies.indicators import williams_r  # noqa: E402
from nsealgo.data.loader import load_symbol  # noqa: E402

sys.path.insert(0, os.path.dirname(__file__))
from harness import williams_r as vec_wr  # noqa: E402

rng = np.random.default_rng(0)
for sym in ["reliance", "tcs", "infy", "hdfcbank"]:
    df = load_symbol(f"data/nse/{sym}_1d.csv", sym)
    c, hi_, lo_ = (df["close"].to_numpy(), df["high"].to_numpy(),
                   df["low"].to_numpy())
    for period in (5, 14, 28):
        mine = vec_wr(pd.Series(hi_, index=df.index), pd.Series(lo_, index=df.index),
                      pd.Series(c, index=df.index), period).to_numpy()
        ref = np.array([williams_r(c[: i + 1], hi_[: i + 1], lo_[: i + 1], period)
                        for i in range(len(c))])
        both = ~(np.isnan(mine) & np.isnan(ref))
        agree = np.isclose(mine[both], ref[both], atol=1e-9)
        # the real impl returns -50.0 on hh==ll where mine returns NaN; both are
        # "not flagged" (0.0 / 0 signal), so compare the *signalled* sets, not raw values
        mflag = set(np.flatnonzero(mine <= -80.0).tolist())
        rflag = set(np.flatnonzero(ref <= -80.0).tolist())
        print(f"{sym:<10} p={period:<3} value-match {agree.all()} "
              f"maxdiff {np.nanmax(np.abs(mine[both] - ref[both])):.2e} "
              f"| flag@<-80 identical: {mflag == rflag} (n={len(mflag)})")
