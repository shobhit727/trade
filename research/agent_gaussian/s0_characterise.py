"""Step 0 — data audit + characterisation of the gaussian signal.

Two jobs:
  1. Load and audit the cleaned daily panel (mandatory first step).
  2. Characterise the signal: how often is it long, what is the z distribution,
     and does the declared `period` actually do anything?
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "src")

from nsealgo.data.loader import load_universe  # noqa: E402

pd.set_option("display.width", 200)


def rolling_zscore(panel: pd.DataFrame, period: int) -> pd.DataFrame:
    """z of close vs its own trailing `period`-bar mean/stdev.

    Population stdev (ddof=0) to match `numpy.std` in
    `cryptobot.strategies.indicators.zscore`. Strictly trailing: the value at t uses
    closes[0..t] only, so no lookahead.
    """
    win = panel.rolling(period, min_periods=period)
    mu = win.mean()
    sd = win.std(ddof=0).replace(0.0, np.nan)
    return (panel - mu) / sd


def main() -> None:
    panel, symbols, report = load_universe("data/nse")
    print(report.describe())
    print(f"symbols      : {len(symbols)}")
    print(f"panel shape  : {panel.shape}")
    print(f"panel span   : {panel.index[0].date()} -> {panel.index[-1].date()}")
    print(f"n dates      : {len(panel)}")
    print()

    train = panel.loc["2016-01-01":"2023-12-31"]
    test = panel.loc["2024-01-01":"2026-10-01"]
    print(f"TRAIN rows {len(train)}  {train.index[0].date()} -> {train.index[-1].date()}")
    print(f"TEST  rows {len(test)}  {test.index[0].date()} -> {test.index[-1].date()}")
    print()

    # ---- how often is each variant long, over TRAIN only -------------------
    print("=== signal liveness (fraction of symbol-bars signalled LONG) ===")
    print(f"{'id':<4} {'period':>7} {'entry':>6} {'TRAIN long%':>12} {'TEST long%':>11}")
    variants = [("V1", 30, 0.8), ("V2", 30, 1.2), ("V3", 126, 0.8), ("V4", 10, 0.8)]
    zcache: dict[int, pd.DataFrame] = {}
    for vid, per, ent in variants:
        if per not in zcache:
            zcache[per] = rolling_zscore(panel, per)
        z = zcache[per]
        long_tr = (z.loc[train.index] <= -ent).to_numpy().mean()
        long_te = (z.loc[test.index] <= -ent).to_numpy().mean()
        print(f"{vid:<4} {per:>7} {ent:>6.1f} {long_tr * 100:>11.2f}% {long_te * 100:>10.2f}%")
    print()

    # ---- z distribution (pooled over TRAIN) --------------------------------
    z30 = zcache[30].loc[train.index]
    flat = z30.to_numpy().ravel()
    flat = flat[np.isfinite(flat)]
    print("=== z(period=30) distribution over TRAIN, pooled across symbols ===")
    print(f"  n         : {flat.size:,}")
    print(f"  mean      : {flat.mean(): .4f}   (0 by construction)")
    print(f"  std       : {flat.std(): .4f}   (<1 => fat tails vs normal)")
    print(f"  skew      : {float(pd.Series(flat).skew()): .4f}")
    print(f"  kurtosis  : {float(pd.Series(flat).kurt()): .4f}  (normal = 0)")
    for q in (0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99):
        print(f"  q{q:<7.2f}: {np.quantile(flat, q): .4f}")
    print()

    # ---- forward-return of the signal: does the dip actually bounce? -------
    print("=== unconditional forward 5d return, TRAIN, by z30 bucket ===")
    fwd = panel.shift(-5) / panel - 1.0
    buckets = [
        ("z <= -1.5", z30 <= -1.5),
        ("-1.5 < z <= -1.0", (z30 <= -1.0) & (z30 > -1.5)),
        ("-1.0 < z <= -0.8", (z30 <= -0.8) & (z30 > -1.0)),
        ("-0.8 < z <= -0.5", (z30 <= -0.5) & (z30 > -0.8)),
        ("-0.5 < z <  +0.8", (z30 > -0.5) & (z30 < 0.8)),
        ("+0.8 < z <  +1.0", (z30 >= 0.8) & (z30 < 1.0)),
        ("+1.0 < z <= +1.5", (z30 >= 1.0) & (z30 < 1.5)),
        ("z >  +1.5", z30 > 1.5),
    ]
    print(f"{'bucket':<22} {'n':>9} {'mean 5d fwd':>13} {'win%':>7}")
    for label, mask in buckets:
        m = (mask & fwd.notna()).loc[train.index]
        r = fwd.where(m).to_numpy().ravel()
        r = r[np.isfinite(r)]
        if r.size == 0:
            print(f"{label:<22} {0:>9} {'n/a':>13} {'n/a':>7}")
            continue
        print(f"{label:<22} {r.size:>9,} {r.mean() * 100:>12.3f}% {(r > 0).mean() * 100:>6.1f}%")
    print(f"(universe mean 5d fwd over TRAIN: {fwd.loc[train.index].stack().mean() * 100:.3f}%)")
    print()

    # ---- does `period` change anything at all? (original-code bug check) ----
    print("=== does the ORIGINAL code's `period` affect the z at all? ===")
    from cryptobot.strategies.catalog.gaussian_strategy import GaussianConfig, GaussianStrategy

    for per in (10, 30, 126):
        cfg = GaussianConfig(period=per, entry=0.8)
        st = GaussianStrategy(cfg)
        # Feed exactly `per` bars so the buffer is exactly period long.
        bars = [100.0 + i for i in range(per)]
        sig = st.signal(bars, bars, bars, [0.0] * per)
        # Feed per + 200 bars: buffer is now capped at maxlen=300, not period.
        bars2 = [100.0 + i for i in range(per + 200)]
        sig2 = st.signal(bars2, bars2, bars2, [0.0] * len(bars2))
        z_exact = (bars[-1] - np.mean(bars)) / np.std(bars)
        z_full = (bars2[-1] - np.mean(bars2)) / np.std(bars2)
        print(
            f"  period={per:<4} buffer=[period] bars -> z={z_exact: .4f} sig={sig} | "
            f"buffer=[period+200] bars -> z={z_full: .4f} sig={sig2}"
        )
    print()
    print("  maxlen of the SignalStrategy buffer:", GaussianStrategy()._maxlen)
    print("  -> z is computed over the WHOLE buffer, so `period` only gates warmup.")


if __name__ == "__main__":
    main()
