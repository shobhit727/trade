"""VERIFY — is the inherited `_ohlc.pkl` cache trustworthy?

The prior run's `common.py` was edited after `stage1_train.py` executed, so nothing
written by that run is trusted. This script rebuilds the panels from the raw CSVs via
the mandatory `load_universe` path and compares them to the pickle.

Also runs the mandatory first step from the brief (§2) and prints the cleaning report.

Usage:  python verify_cache.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "src"))

from nsealgo.data.loader import load_symbol, load_universe  # noqa: E402

DATA = str(HERE.parents[1] / "data" / "nse")
CACHE = HERE / "_ohlc.pkl"


def main() -> None:
    print("=" * 90)
    print("MANDATORY FIRST STEP — load_universe('data/nse')")
    print("=" * 90)
    panel, symbols, report = load_universe(DATA)
    print(report.describe())
    print(f"Universe: {len(symbols)} symbols")
    print(f"Index   : {panel.index[0].date()} -> {panel.index[-1].date()}  "
          f"({len(panel)} bars)")
    print(f"TEST tail: {panel.loc['2026-09-25':].index[-1].date()}")

    hi, lo = {}, {}
    for sym in symbols:
        df = load_symbol(os.path.join(DATA, f"{sym}_1d.csv"), sym)
        hi[sym] = df["high"].rename(sym)
        lo[sym] = df["low"].rename(sym)
    high = pd.DataFrame(hi).reindex(panel.index)
    low = pd.DataFrame(lo).reindex(panel.index)

    print("\n" + "=" * 90)
    print("CACHE CHECK vs _ohlc.pkl")
    print("=" * 90)
    if not CACHE.exists():
        print("no cache present -> fresh load is the only source of truth")
        pd.to_pickle({"close": panel, "high": high, "low": low}, CACHE)
        print(f"wrote fresh cache {CACHE}")
        return

    old = pd.read_pickle(CACHE)
    ok = True
    for k, new in (("close", panel), ("high", high), ("low", low)):
        o = old[k]
        same_shape = o.shape == new.shape
        same_index = same_shape and o.index.equals(new.index)
        same_cols = same_shape and list(o.columns) == list(new.columns)
        if same_shape and same_index and same_cols:
            d = (o.to_numpy() - new.to_numpy())
            d = d[~pd.isna(d)]
            max_abs = float(abs(d).max()) if d.size else 0.0
            n_mismatch = int((abs(d) > 1e-9).sum()) if d.size else 0
        else:
            max_abs, n_mismatch = float("nan"), -1
        verdict = "IDENTICAL" if (same_index and same_cols and n_mismatch == 0) else "DIFFERS"
        if verdict != "IDENTICAL":
            ok = False
        print(f"  {k:<6} shape {o.shape} vs {new.shape}  "
              f"idx_match={same_index} cols_match={same_cols}  "
              f"max_abs_diff={max_abs:.3e}  n_diff={n_mismatch}  -> {verdict}")

    if ok:
        print("\nCACHE VERIFIED — inherited pickle matches a fresh load.")
    else:
        print("\nCACHE REJECTED — rebuilt and overwrote the pickle.")
        pd.to_pickle({"close": panel, "high": high, "low": low}, CACHE)

    # sanity on the ATR inputs actually used
    print("\n" + "=" * 90)
    print("HIGH/LOW SANITY")
    print("=" * 90)
    print(f"  high >= close everywhere : {bool((high >= panel).all().all())}")
    print(f"  low  <= close everywhere : {bool((low <= panel).all().all())}")
    print(f"  high >= low  everywhere  : {bool((high >= low).all().all())}")
    nan_h = int(high.isna().sum().sum())
    nan_l = int(low.isna().sum().sum())
    print(f"  NaNs: high {nan_h}, low {nan_l} (expected: only pre-listing history)")
    print(f"  window bar counts: TRAIN "
          f"{int(((panel.index >= '2016-01-01') & (panel.index <= '2023-12-31')).sum())}, "
          f"TEST "
          f"{int(((panel.index >= '2024-01-01') & (panel.index <= '2026-10-01')).sum())}")


if __name__ == "__main__":
    main()
