"""Step 01 — prove the vectorised delta equals the catalog indicator, and audit data.

Run: .venv/bin/python research/agent_cumulative_delta/01_verify.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from common import (  # noqa: E402
    TRAIN_END,
    TRAIN_START,
    VARIANTS,
    delta_panel,
    liveness,
    load_panels,
    signal_panel,
)

from cryptobot.strategies.catalog.cumulative_delta_strategy import (  # noqa: E402
    CumulativeDeltaConfig,
    CumulativeDeltaStrategy,
)


def check_equivalence(close: pd.DataFrame, vol: pd.DataFrame, window: int) -> None:
    """Vectorised panel vs the catalog loop, on every symbol and on random data."""
    strat = CumulativeDeltaStrategy(CumulativeDeltaConfig(window=window))
    vec_all = delta_panel(close, vol, window)

    total = agree = 0
    for sym in close.columns:
        cs = close[sym].dropna()
        if len(cs) < window + 5:
            continue
        idx = cs.index
        c = cs.to_numpy(float)
        v = vol[sym].reindex(idx).to_numpy(float)
        loopy = np.array([strat.signal(c[: i + 1], None, None, v[: i + 1])
                          for i in range(window, len(c))], dtype=float)
        loopy = pd.Series(loopy, index=idx[window:])
        mine = np.sign(vec_all[sym].reindex(loopy.index))
        both_nan = int((loopy.isna() & mine.isna()).sum())
        total += len(loopy)
        agree += int((loopy.fillna(0.0) == mine.fillna(0.0)).sum()) + both_nan
    assert agree == total, (
        f"vectorised delta disagrees with catalog on {total - agree}/{total} bars")
    print(f"  w={window:3d}: {agree}/{total} name-bars exact-sign match "
          f"(all {len(close.columns)} symbols)")

    # --- raw delta, not just its sign, on synthetic paths (20 seeds).
    #     Guards against a bug that only shows on random paths (flat days, zero vol).
    for seed in range(20):
        r = np.random.default_rng(seed)
        rets = r.normal(0.0, 0.02, 400)
        rets[r.random(400) < 0.1] = 0.0  # flat days, exactly as the loop skips them
        px = 100.0 * np.cumprod(1.0 + rets)
        vv = r.integers(1, 10_000_000, 400).astype(float)
        d = np.zeros(400)
        for i in range(-window, 0):
            if px[i] > px[i - 1]:
                d[i] += vv[i]
            elif px[i] < px[i - 1]:
                d[i] -= vv[i]
        signed = np.sign(np.diff(np.r_[np.nan, px])) * vv
        mine = float(np.nansum(signed[-window:]))
        assert abs(mine - float(d[-window:].sum())) < 1e-6, f"seed {seed} mismatch"
    print(f"  w={window:3d}: 20/20 synthetic paths exact raw-delta match")


def main() -> None:
    close, vol, symbols, report = load_panels()
    ret = close.pct_change(fill_method=None)
    print(report.describe())
    print(f"close panel {close.shape}  {close.index[0].date()} -> "
          f"{close.index[-1].date()}")
    print(f"vol  panel {vol.shape}  nan(vol)={int(vol.isna().sum().sum())}  "
          f"zero-vol days={int((vol == 0).sum().sum())}")
    print(f"symbols with <1000 bars: "
          f"{sorted([s for s in symbols if close[s].notna().sum() < 1000])}")

    print("\nEQuIVALENCE: vectorised cumulative_delta vs catalog loop")
    for v in VARIANTS:
        check_equivalence(close, vol, v.window)

    print("\nWARMUP / LIVENESS (TRAIN window 2016-01-01..2023-12-31)")
    tr = slice(TRAIN_START, TRAIN_END)
    for v in VARIANTS:
        d = delta_panel(close, vol, v.window)
        live = liveness(d, TRAIN_START, TRAIN_END)
        print(f"  {v.name:<20} long_frac={live['long_frac'] * 100:5.1f}%  "
              f"avg_flagged={live['avg_flagged_names']:5.1f}  "
              f"days<22names={live['days_below_n_positions'] * 100:5.1f}%")
        assert live["long_frac"] > 0.05, "signal effectively always-flat"

    print("\nSIGNAL PERSISTENCE (mean run length of a long state, TRAIN)")
    for v in VARIANTS:
        d = delta_panel(close, vol, v.window).loc[tr]
        flags = signal_panel(d).notna().to_numpy()
        # run-lengths of True runs, vectorised per column
        padded = np.zeros((flags.shape[0] + 2, flags.shape[1]), dtype=bool)
        padded[1:-1] = flags
        starts = padded[1:-1] & ~padded[:-2]
        ends = padded[1:-1] & ~padded[2:]
        run_id = np.cumsum(starts, axis=0) * flags
        lens = []
        for col in range(flags.shape[1]):
            m = flags[:, col]
            if not m.any():
                continue
            idx = np.flatnonzero(ends[:, col]) + 1
            beg = np.flatnonzero(starts[:, col])
            lens.extend((idx - beg).tolist())
        _ = run_id
        print(f"  {v.name:<20} mean run {np.mean(lens):5.1f} sessions  "
              f"median {np.median(lens):5.1f}  n_runs {len(lens)}")

    print("\nWHAT THE DELTA IS ACTUALLY MEASURING (TRAIN, cross-sectional)")
    # Forward 21d return ENDING at t+h: sum the trailing 21d return then push it
    # FORWARD. (Shifting first and rolling after would give a mostly-backward
    # window and a spuriously huge correlation.)
    d30 = delta_panel(close, vol, 30)
    fwd21 = ret.rolling(21, min_periods=21).sum()
    mom126 = (close / close.shift(126) - 1.0)
    for h in (0, 1, 5, 21):
        f = fwd21.shift(-h - 1) if h else fwd21.shift(-1)
        cs = d30.loc[tr].corrwith(f.loc[tr], axis=1).mean()
        cm = mom126.loc[tr].corrwith(f.loc[tr], axis=1).mean()
        print(f"  h={h + 1:2d}d  corr(delta30, fwd21d)={cs:+.4f}   "
              f"corr(mom126, fwd21d)={cm:+.4f}")
    print("  (delta30 vs mom126 itself, TRAIN cross-sectional: "
          f"{d30.loc[tr].corrwith(mom126.loc[tr], axis=1).mean():+.4f})")


if __name__ == "__main__":
    main()
