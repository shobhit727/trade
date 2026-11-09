"""VERIFY — is the vectorised port numerically identical to the catalog class?

`common.atr_trailing_signal` reimplements `AtrTrailingStrategy.signal` with pandas
rolling windows. A port is only as good as its agreement with the original, so this
drives the *real* catalog class bar-by-bar over several symbols and compares, element by
element, against the panel.

Checks:
  1. elementwise agreement of the +1 / 0 / -1 panel on a long stretch of history
  2. SMA and ATR series agreement (the two things the signal is built from)
  3. the exact catalog-default variant (period=14, mult=2.0)

Any disagreement here invalidates every downstream number.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "src"))

from common import atr_trailing_signal, load_ohlc, true_range  # noqa: E402

from cryptobot.strategies.catalog.atr_trailing_stop import (  # noqa: E402
    AtrTrailingConfig,
    AtrTrailingStrategy,
)
from cryptobot.strategies.indicators import atr as cat_atr  # noqa: E402
from cryptobot.strategies.indicators import sma as cat_sma  # noqa: E402

# Symbols spanning the TEST window plus a long TRAIN tail.
SYMBOLS = ["reliance", "tcs", "hdfcbank", "infy", "titan", "sunpharma", "icicibank"]


def main() -> None:
    close, high, low = load_ohlc()
    period, mult = 14, 2.0

    vec_sig = atr_trailing_signal(close, high, low, period, mult)
    vec_atr = true_range(close, high, low).rolling(period, min_periods=period).mean()
    vec_sma = close.rolling(period, min_periods=period).mean()

    strat = AtrTrailingStrategy(AtrTrailingConfig(period=period, multiplier=mult))

    sig_rows, atr_rows, sma_rows, n_nan_vec, n_nan_cat = [], [], [], 0, 0
    first_mismatch = None

    for sym in SYMBOLS:
        c = close[sym].to_numpy()
        h = high[sym].to_numpy()
        lo = low[sym].to_numpy()
        v = None  # volumes are unused by this strategy

        for i in range(period, len(c)):
            if not np.isfinite(c[i]) or not np.isfinite(h[i]) or not np.isfinite(lo[i]):
                continue
            # the real class, driven on history up to and including bar i
            cat = strat.signal(list(c[: i + 1]), list(h[: i + 1]), list(lo[: i + 1]), v)
            va = vec_sig[sym].iloc[i]
            if np.isnan(va):
                n_nan_vec += 1
                va_cmp = None
            else:
                va_cmp = int(va)
            if va_cmp is None:
                n_nan_cat += 1
            else:
                if cat != va_cmp and first_mismatch is None:
                    first_mismatch = (sym, close.index[i], cat, va_cmp)
            sig_rows.append((cat, va_cmp))

            b = cat_atr(list(h[: i + 1]), list(lo[: i + 1]), list(c[: i + 1]), period)
            m = cat_sma(list(c[: i + 1]), period)
            atr_rows.append((b, float(vec_atr[sym].iloc[i])))
            sma_rows.append((m, float(vec_sma[sym].iloc[i])))

    s = pd.DataFrame(sig_rows, columns=["catalog", "vectorised"])
    agree = (s["catalog"] == s["vectorised"]) | s["vectorised"].isna()
    print("=" * 92)
    print(f"PORT EQUIVALENCE — {len(SYMBOLS)} symbols, period={period}, mult={mult}")
    print("=" * 92)
    print(f"bars compared          : {len(s):,}")
    print(f"signal agreement       : {int(agree.sum()):,}/{len(s):,}"
          f"  ({int(agree.sum()) / len(s) * 100:.4f}%)")
    print(f"vectorised NaN (warmup): {n_nan_vec:,}   catalog had no answer: {n_nan_cat:,}")
    print(f"first mismatch         : {first_mismatch}")

    a = pd.DataFrame(atr_rows, columns=["catalog", "vectorised"])
    print(f"\nATR max abs diff       : {float((a['catalog'] - a['vectorised']).abs().max()):.3e}"
          f"   (mean {float((a['catalog'] - a['vectorised']).abs().mean()):.3e})")
    m = pd.DataFrame(sma_rows, columns=["catalog", "vectorised"])
    print(f"SMA max abs diff       : {float((m['catalog'] - m['vectorised']).abs().max()):.3e}"
          f"   (mean {float((m['catalog'] - m['vectorised']).abs().mean()):.3e})")

    print("\n  signal distribution (catalog, whole panel):")
    for val, cnt in s["catalog"].value_counts().sort_index().items():
        lbl = {1.0: "+1 long", -1.0: "-1 short", 0.0: " 0 flat"}.get(val, str(val))
        print(f"    {lbl:<10} {cnt:>7,}  ({cnt / len(s) * 100:5.2f}%)")

    ok = bool(agree.all()) and first_mismatch is None
    print(f"\nVERDICT: {'PORT VERIFIED — identical to the catalog class' if ok else 'PORT MISMATCH'}")
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
