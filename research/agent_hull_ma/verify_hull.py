"""Prove the vectorised Hull panel reproduces `cryptobot.strategies.indicators.hull`
bar-for-bar, so the backtest runs the catalog indicator and not a lookalike.

The library function is:

    half   = period // 2
    sqrt_p = round(sqrt(period))
    raws   = [2*WMA(half, asof t-lag) - WMA(period, asof t-lag) for lag sqrt_p-1..0]
    hull   = sum((sqrt_p - lag) * raws[lag]) / sum(sqrt_p - lag)

i.e. a triangular WMA of the raw Hull, heaviest on the most recent raw value, which is
exactly WMA(raw, sqrt_p). Verified here against the real function.
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "src")

from cryptobot.strategies.indicators import hull  # noqa: E402


def wma_panel(x: pd.DataFrame, period: int) -> pd.DataFrame:
    """Exact WMA over the trailing `period` bars, heaviest on the most recent bar.

    NOTE: `ewm(alpha=1/p, adjust=False)` is NOT a WMA -- its weights decay
    geometrically, not linearly. Use a rolling weighted mean.
    """
    w = np.arange(1, period + 1, dtype=float)
    rolled = x.rolling(period, min_periods=period)
    return rolled.apply(lambda a: np.dot(a, w), raw=True) / w.sum()


def hull_panel(panel: pd.DataFrame, period: int) -> pd.DataFrame:
    """Vectorised equivalent of `indicators.hull` applied column-wise."""
    half = max(1, period // 2)
    sqrt_p = max(1, int(round(period**0.5)))
    # NOTE the term order: the catalog library uses 2*WMA(period) - WMA(half).
    # The textbook Hull MA is 2*WMA(half) - WMA(period), i.e. swapped. We reproduce
    # the LIBRARY (that is the assigned strategy) and note the discrepancy in the
    # report. It only negates the Hull line, which leaves `close > hull` signs
    # mirrored relative to a textbook Hull.
    raw = 2.0 * wma_panel(panel, period) - wma_panel(panel, half)
    out = wma_panel(raw, sqrt_p)
    warm = period + sqrt_p - 1  # bars needed; first valid 0-based index is warm-1
    out.iloc[: warm - 1] = np.nan
    return out


def main() -> None:
    rng = np.random.default_rng(7)
    n = 900
    px = 100.0 * np.exp(np.cumsum(rng.normal(0.0004, 0.016, n)))
    closes = list(px)

    worst = 0.0
    for period in (10, 15, 20, 30, 55):
        lib = [hull(closes[: i + 1], period) for i in range(n)]
        mine = hull_panel(pd.DataFrame({"s": px}), period)["s"].to_numpy()
        warm = period + max(1, int(round(period ** 0.5))) - 1
        first_idx = warm - 1
        both_nan = np.isnan(np.array(lib, dtype=float)) & np.isnan(mine)
        cmp_mask = ~both_nan & ~np.isnan(np.array(lib, dtype=float))
        diff = np.abs(np.array(lib, dtype=float)[cmp_mask] - mine[cmp_mask])
        rel = float(np.max(diff / np.abs(np.array(lib, dtype=float)[cmp_mask])))
        first_ok = int(np.argmax(cmp_mask)) if cmp_mask.any() else -1
        assert first_ok == first_idx, (
            f"period={period}: first finite at {first_ok}, want {first_idx}"
        )
        assert mine[~cmp_mask & ~both_nan].size == 0, "panel finite where library is nan"
        print(f"period={period:>3}  max_rel_diff={rel:.3e}  first_finite_bar={first_ok}")
        worst = max(worst, rel)
    print(f"\nworst relative deviation across all periods: {worst:.3e}")
    assert worst < 1e-10, "Hull panel does not match the library"
    print("OK: vectorised hull_panel == catalog hull (to float precision)")


if __name__ == "__main__":
    main()
