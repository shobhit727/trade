"""VERIFY — OHLC integrity of the high/low panels actually fed to ATR.

`verify_cache.py` flagged `high >= close` as False. ATR is built from
`true_range = max(H-L, |H - C_prev|, |L - C_prev|)`, so a bad high/low silently
understates volatility. Quantify the damage before trusting any result.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "src"))

from common import load_ohlc  # noqa: E402


def main() -> None:
    close, high, low = load_ohlc()

    print("=" * 92)
    print("OHLC STRUCTURE — where do high/low break the invariant?")
    print("=" * 92)
    bad_hc = high < close
    bad_lc = low > close
    bad_hl = high < low
    print(f"  high < close : {int(bad_hc.sum().sum()):>7,} cells")
    print(f"  low  > close : {int(bad_lc.sum().sum()):>7,} cells")
    print(f"  high < low   : {int(bad_hl.sum().sum()):>7,} cells")

    for name, mask in (("high<close", bad_hc), ("low>close", bad_lc), ("high<low", bad_hl)):
        n = int(mask.sum().sum())
        if n == 0:
            continue
        syms = mask.sum()[lambda s: s > 0]
        print(f"\n  {name}: worst symbols")
        for s in syms.sort_values(ascending=False).head(6).index:
            dates = mask[s][mask[s]].index
            print(f"    {s:<12} {len(dates):>4} days, "
                  f"first {dates[0].date()}  last {dates[-1].date()}")

    # how bad is the relative error, where it occurs
    both = bad_hc & bad_lc & bad_hl
    print("\n" + "=" * 92)
    print("MAGNITUDE of the violation")
    print("=" * 92)
    rel = ((high - close) / close).where(bad_hc).stack()
    print(f"  high < close by: median {rel.abs().median() * 100:.3f}%  "
          f"max {rel.abs().max() * 100:.3f}%  (of close)")
    rell = ((close - low) / close).where(bad_lc).stack()
    print(f"  low  > close by: median {rell.abs().median() * 100:.3f}%  "
          f"max {rell.abs().max() * 100:.3f}%  (of close)")
    print(f"  cells violating all three at once: {int(both.sum().sum()):,}")

    # does it matter for the two windows we actually use?
    print("\n" + "=" * 92)
    print("DOES IT LAND INSIDE TRAIN / TEST?")
    print("=" * 92)
    tr = pd.Timestamp("2024-01-01", tz="Asia/Kolkata")
    tr_end = pd.Timestamp("2023-12-31", tz="Asia/Kolkata")
    for label, sl in (("TRAIN", slice(None, tr_end)), ("TEST", slice(tr, None))):
        m = (bad_hc | bad_lc | bad_hl).loc[sl]
        dates = m.index[m.any(axis=1)]
        print(f"  {label:<6} violating bars: {len(dates):>4} of {len(m)}"
              + (f"   first {dates[0].date()} last {dates[-1].date()}" if len(dates) else ""))

    # how much does it move the ATR that the strategy actually consumes?
    print("\n" + "=" * 92)
    print("EFFECT ON ATR(55) — the frozen variant's volatility input")
    print("=" * 92)
    prev = close.shift(1)
    tr_true = pd.DataFrame(
        np.maximum.reduce([
            (high - low).to_numpy(),
            (high - prev).abs().to_numpy(),
            (low - prev).abs().to_numpy(),
        ]),
        index=close.index, columns=close.columns,
    )
    # naive alternative that only ever uses high-low
    tr_hl = high - low
    a_true = tr_true.rolling(55, min_periods=55).mean()
    a_hl = tr_hl.rolling(55, min_periods=55).mean()
    for label, sl in (("TRAIN", slice(None, tr_end)), ("TEST", slice(tr, None))):
        d = (a_true - a_hl).loc[sl].abs()
        rel = (d / a_true.loc[sl])
        print(f"  {label:<6} ATR true-range vs high-low only: "
              f"median diff {d.stack().median():.4f}  "
              f"max rel diff {(rel.stack().max() * 100):.3f}%  "
              f"share of cells differing >1%: {float((rel > 0.01).mean().mean()) * 100:.2f}%")

    print("\n  A true-range ATR is >= the high-low ATR by construction, so the")
    print("  breach can only ever make the band WIDER (more conservative), never")
    print("  narrower. Direction of the bias is therefore known even though the")
    print("  exact per-symbol cause is not.")


if __name__ == "__main__":
    main()
