"""Stage 1 — TRAIN-only exploration. No TEST data is touched here.

Questions answered, all on 2016-01-01 .. 2023-12-31 only:
  1. How often is the strategy long (liveness)? The brief's sanity check #3.
  2. How many names are signalled per bar (book breadth)?
  3. Is the raw time-series signal any good on its own (before construction)?

Nothing here selects on TEST.
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "src")

import signal as sigmod  # noqa: E402

import common  # noqa: E402

TRAIN = (pd.Timestamp("2016-01-01", tz="Asia/Kolkata"),
         pd.Timestamp("2023-12-31", tz="Asia/Kolkata"))

#: Declared parameter budget: exactly 5 variants, fixed before any run.
VARIANTS = [
    ("V1", 10, 1.0),
    ("V2", 14, 1.5),
    ("V3", 20, 2.0),
    ("V4", 14, 2.5),
    ("V5", 20, 3.0),
]


def main() -> None:
    o, h, lo, c, syms = common.load()
    tr0, tr1 = TRAIN
    print(f"universe: {len(syms)} symbols, {c.index[0].date()} -> {c.index[-1].date()}")
    print(f"TRAIN window: {tr0.date()} -> {tr1.date()}")

    # interior-gap check: a symbol should be NaN only before its listing
    gaps = int(c.loc["2016-01-01":"2023-12-31"].isna().sum().sum())
    print(f"TRAIN NaN cells in close panel: {gaps:,}")

    for name, period, mult in VARIANTS:
        sig = sigmod.signal_panel(h, lo, c, period, mult)
        tr = sig.loc[tr0:tr1]
        sub = tr.to_numpy()
        live = float(np.nanmean(sub > 0))
        flat = float(np.nanmean(sub == 0))
        n_flag = (tr > 0).sum(axis=1)
        # forward-looking mark-to-market of the raw time-series signal, as a
        # diagnostic only (not the deliverable): mean next-day return when long
        fwd = c.pct_change(fill_method=None).shift(-1)
        long_fwd = fwd.where(tr > 0)
        ew_fwd = fwd.where(tr < 0)
        ann = 244
        hit = float(long_fwd.stack().mean() * ann)
        hit_neg = float(ew_fwd.stack().mean() * ann)
        print(
            f"{name} p={period:>2} m={mult:.1f} | live={live:6.2%} "
            f"flat={flat:6.2%} flagged/bar={n_flag.mean():5.2f} "
            f"med={n_flag.median():5.1f} "
            f"annRet|next1d long={hit:7.2%} short={hit_neg:7.2%}"
        )


if __name__ == "__main__":
    main()
