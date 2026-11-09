"""Build + cache the close and volume panels for the trend_volume study.

`load_universe` returns closes only, but this strategy needs volume. Volume is obtained
by running every symbol through the SAME `load_symbol` (cleaning rules C1-C9) and then
reindexing onto the close panel's index. The close column recovered on that second path
is asserted identical to the `load_universe` close: if the two cleaning paths ever
disagree, the run aborts rather than silently mixing two data definitions.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, "src")

import numpy as np
import pandas as pd

from nsealgo.data.loader import EXCLUDE_SYMBOLS, load_symbol, load_universe
from nsealgo.provenance import provenance

SCRATCH = "research/agent_trendvol"
DATA = "data/nse"

TRAIN = ("2016-01-01", "2023-12-31")
TEST = ("2024-01-01", "2026-10-01")


def main() -> None:
    os.makedirs(SCRATCH, exist_ok=True)

    panel, symbols, report = load_universe(DATA)
    print("=== load_universe ===")
    print(report.describe())

    closes = {}
    vols = {}
    for sym in symbols:
        path = os.path.join(DATA, f"{sym}_1d.csv")
        df = load_symbol(path, sym, None)
        # Reindex onto the authoritative panel's index/columns.
        closes[sym] = df["close"].reindex(panel.index)
        vols[sym] = df["vol"].reindex(panel.index)

    close2 = pd.DataFrame(closes)[panel.columns]
    vol = pd.DataFrame(vols)[panel.columns]

    # The two cleaning paths must agree on price, or the study is not reproducible.
    bad = int((close2.notna() != panel.notna()).to_numpy().sum())
    maxdiff = float(np.nanmax(np.abs(close2.to_numpy() - panel.to_numpy())))
    print(f"\nclose cross-check: shape-mismatch cells={bad}  max|diff|={maxdiff:.6g}")
    if bad or not np.isfinite(maxdiff) or maxdiff > 1e-9:
        raise SystemExit("FATAL: load_symbol and load_universe disagree on closes")

    panel.to_pickle(f"{SCRATCH}/panel.pkl")
    vol.to_pickle(f"{SCRATCH}/vol.pkl")

    meta = {
        "provenance": provenance(),
        "shape": list(panel.shape),
        "start": str(panel.index[0].date()),
        "end": str(panel.index[-1].date()),
        "symbols": len(symbols),
        "excluded_symbols": list(EXCLUDE_SYMBOLS),
        "vol_notna_frac": float(vol.notna().to_numpy().mean()),
        "close_notna_frac": float(panel.notna().to_numpy().mean()),
        "train_rows": int(((panel.index >= TRAIN[0]) & (panel.index <= TRAIN[1])).sum()),
        "test_rows": int(((panel.index >= TEST[0]) & (panel.index <= TEST[1])).sum()),
        "close_crosscheck_maxdiff": maxdiff,
    }
    with open(f"{SCRATCH}/data_provenance.json", "w") as fh:
        json.dump(meta, fh, indent=2)

    print("\n=== meta ===")
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
