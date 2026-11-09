"""Verify my vectorised kama_panel() == cryptobot.strategies.indicators.kama(), bar for bar.

Research/agent_kama/ -- no src/ or test/ modification.
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "src")

from cryptobot.strategies.indicators import kama as lib_kama  # noqa: E402

PERIODS = [10, 20, 30, 55, 75]  # the 5 declared variants (V1=20 default)


def kama_panel(x: pd.DataFrame, period: int, fast: int = 2, slow: int = 30) -> pd.DataFrame:
    """Vectorised-across-symbols equivalent of indicators.kama on one column."""
    a = x.to_numpy(dtype=float)
    T, N = a.shape
    out = np.full((T, N), np.nan)
    if T < period + 1:
        return pd.DataFrame(out, index=x.index, columns=x.columns)

    fast_sc = 2.0 / (fast + 1)
    slow_sc = 2.0 / (slow + 1)
    # library: vol = sum_{j=1..period} |a[j]-a[j-1]|
    vol = np.abs(np.diff(a[: period + 1], axis=0)).sum(axis=0)
    kp = a[period].copy()
    out[period] = kp
    with np.errstate(invalid="ignore", divide="ignore"):
        for i in range(period + 1, T):
            vol = vol - np.abs(a[i - period] - a[i - period - 1]) + np.abs(a[i] - a[i - 1])
            change = np.abs(a[i] - a[i - period])
            er = np.where(vol == 0.0, 0.0, change / np.where(vol == 0.0, 1.0, vol))
            sc = (er * (fast_sc - slow_sc) + slow_sc) ** 2
            kp = kp + sc * (a[i] - kp)
            out[i] = kp
    return pd.DataFrame(out, index=x.index, columns=x.columns)


def synth(n: int, seed: int, cols: int = 4) -> pd.DataFrame:
    """A trending + choppy + regime-flipping synthetic panel with NaN gaps."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2015-01-01", periods=n)
    data = {}
    for c in range(cols):
        drift = rng.normal(0.0004, 0.0006)
        vol = 0.012 + 0.006 * rng.random()
        # regime flip at 40% so the ER actually moves
        r = np.concatenate([rng.normal(drift, vol, int(n * 0.4)),
                            rng.normal(-drift * 0.5, vol * 1.8, n - int(n * 0.4))])
        p = 100.0 * np.exp(np.cumsum(r))
        if c == 1:  # a flat series -> vol == 0 branch must be exercised
            p[:20] = 50.0
        data[f"S{c}"] = p
    df = pd.DataFrame(data, index=dates)
    df.iloc[[5, 6, 300], 0] = np.nan  # gaps -> NaN propagation
    df.iloc[7:, 2] = df.iloc[7:, 2].ffill()
    return df


def main() -> None:
    df = synth(900, seed=7)
    print(f"synthetic panel {df.shape}  {df.index[0].date()} -> {df.index[-1].date()}\n")
    ok = True
    for p in PERIODS:
        mine = kama_panel(df, p)
        worst = 0.0
        first_finite = None
        for col in df.columns:
            s = df[col].to_numpy(dtype=float)
            # library needs a contiguous, NaN-free window: feed it each suffix
            # the same way the streaming wrapper would (nan -> skip).
            lib_vals = []
            first_fin_col = None
            for t in range(len(s)):
                w = s[: t + 1]
                w = w[~np.isnan(w)]
                v = lib_kama(w, p) if len(w) >= p + 1 else float("nan")
                lib_vals.append(v)
                if not np.isnan(v) and first_fin_col is None:
                    first_fin_col = t
            lib = np.array(lib_vals, dtype=float)
            # my version propagates NaN from the start; the library skips gaps.
            # Compare only where BOTH are finite, which is the meaningful overlap.
            both = np.isfinite(mine[col].to_numpy()) & np.isfinite(lib)
            if both.sum() == 0:
                continue
            rel = np.abs(mine[col].to_numpy()[both] - lib[both]) / np.maximum(
                np.abs(lib[both]), 1e-12
            )
            worst = max(worst, float(rel.max()))
            fin = np.flatnonzero(np.isfinite(mine[col].to_numpy()))
            if len(fin) and first_finite is None:
                first_finite = int(fin[0])
            if first_fin_col is not None and first_finite is None:
                first_finite = first_fin_col
        flag = "OK " if worst < 1e-9 else "FAIL"
        if worst >= 1e-9:
            ok = False
        print(f"period={p:>3}  max_rel_diff={worst:.3e}  first_finite_bar={first_finite}  {flag}")

    print("\nOK: vectorised kama_panel == catalog kama (to float precision)"
          if ok else "\nMISMATCH -- do not trust the panel implementation")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
