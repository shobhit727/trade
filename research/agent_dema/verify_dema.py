"""Correctness proof for `dema_lib.dema_panel`.

Three properties must hold before any backtest number means anything:

  1. EXACTNESS  — our vectorised panel equals `cryptobot.strategies.indicators.dema`
                  applied to the same (NaN-trimmed) history, to ~1e-9.
  2. NO LOOKAHEAD — the value at date t equals the value the strategy would compute
                  from a history truncated at t.
  3. LIVENESS — the panel is not accidentally dead (NaN everywhere) as an earlier
                  version of this file was. Every probe must produce a finite number;
                  an empty comparison set is a FAILURE, not a pass.

The reference is O(n) per call, so we probe a stratified sample of bars rather than
every bar of a 4.6k-bar history.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dema_lib import _ema_series, _indicator_input, dema_panel  # noqa: E402

from cryptobot.strategies.indicators import dema as ref_dema  # noqa: E402
from nsealgo.data.loader import load_universe  # noqa: E402

N_PROBE_BARS = 20
PERIODS = (10, 20, 50, 100, 200)


def main() -> None:
    panel, symbols, _ = load_universe("data/nse")
    print(f"loaded {len(symbols)} symbols, {len(panel)} bars "
          f"({panel.index[0].date()} -> {panel.index[-1].date()})\n")

    probe_syms = sorted(set(symbols[:6] + symbols[-4:] + ["coalindia", "eternal"]))
    ok = True
    n_compared = 0

    print("--- 1. EXACTNESS vs cryptobot.strategies.indicators.dema ---")
    for period in PERIODS:
        dp = dema_panel(panel, period)
        worst = 0.0
        checked = 0
        missing = []
        for sym in probe_syms:
            col = _indicator_input(panel)[sym].dropna()
            n = len(col)
            positions = np.unique(np.linspace(int(n * 0.10), n - 1, N_PROBE_BARS).astype(int))
            for i in positions:
                ref = ref_dema(col.to_numpy()[: i + 1], period)
                ours = float(dp.loc[col.index[i], sym])
                if not np.isfinite(ours):
                    missing.append(f"{sym}@{col.index[i].date()}")
                    continue
                worst = max(worst, abs(ref - ours) / max(abs(ref), 1.0))
                checked += 1
        good = worst < 1e-9 and checked > 0 and not missing
        ok &= good
        n_compared += checked
        print(f"  [{'OK ' if good else 'FAIL'}] period={period:<4} "
              f"{checked:>4} comparisons, max rel err {worst:.3e}"
              + (f", MISSING: {missing[:3]}" if missing else ""))

    print("\n--- 2. NO LOOKAHEAD (truncated-history reference) ---")
    for period in (20, 200):
        dp = dema_panel(panel, period)
        for sym in ("reliance", "hdfcbank", "tcs"):
            col = _indicator_input(panel)[sym].dropna()
            for frac in (0.4, 0.7, 0.95):
                i = int(len(col) * frac)
                d = col.index[i]
                ref = ref_dema(col.loc[:d].to_numpy(), period)
                ours = float(dp.loc[d, sym])
                diff = abs(ref - ours) / max(abs(ref), 1.0)
                good = diff < 1e-8
                ok &= good
                print(f"  [{'OK ' if good else 'FAIL'}] period={period:<4} {sym:<9} "
                      f"{d.date()}: truncated={ref:,.4f} panel={ours:,.4f} "
                      f"rel diff {diff:.1e}")

    print("\n--- 3. SEED / PRE-HISTORY INSENSITIVITY (how much warmup the DEMA needs) ---")
    # A DEMA is an EMA pair, so the seed's influence decays as ~(1-k)^(2n). This is a
    # TRUE property of the indicator, not a defect: it says how much history the live
    # engine must accumulate before the seed choice stops mattering. Check 2 already
    # proved point-in-time correctness; this quantifies the warmup.
    dp = dema_panel(panel, 200)
    base = _indicator_input(panel)["reliance"].to_numpy()
    ref = dp["reliance"].to_numpy()
    rng = np.random.default_rng(7)
    n_noise = 500
    noise = rng.uniform(-5, 5, n_noise)
    padded = np.concatenate([noise, base])
    e1 = _ema_series(padded, 200)
    shifted = (2.0 * e1 - _ema_series(e1, 200))[n_noise:]
    fin = np.isfinite(ref) & np.isfinite(shifted)
    for bars in (200, 400, 600, 800, 1000, 1200, 1600, 2000):
        sel = fin.copy()
        sel[:bars] = False
        d = float(np.max(np.abs(shifted[sel] - ref[sel]) / np.abs(ref[sel])))
        print(f"    after {bars:>4} real bars ({bars / 200:.1f}x period): "
              f"max rel shift {d:.2e}"
              + ("  <- washed out" if d < 1e-5 else ""))

    # The decision-relevant version: is the seed washed out by the time TRAIN begins?
    # The panel starts 2008-01-01 and TRAIN starts 2016-01-01, ~1950 bars later.
    first_train = int(panel.index.searchsorted(pd.Timestamp("2016-01-01", tz="Asia/Kolkata")))
    sel = fin.copy()
    sel[:first_train] = False
    d = float(np.max(np.abs(shifted[sel] - ref[sel]) / np.abs(ref[sel])))
    good = d < 1e-5
    ok &= good
    print(f"  [{'OK ' if good else 'FAIL'}] at the TRAIN start ({first_train} bars of "
          f"history = {first_train / 200:.1f}x the period-200 period): "
          f"seed influence {d:.2e} -- seed is immaterial for every traded bar")

    print("\n--- 4. LIVENESS: fraction of (day,name) with a finite DEMA ---")
    for period in PERIODS:
        frac = float(np.isfinite(dema_panel(panel, period).to_numpy()).mean())
        print(f"  period={period:<4} finite DEMA on {frac * 100:5.1f}% of cells")

    print(f"\n{n_compared} exactness comparisons total")
    print("ALL CHECKS PASSED" if ok else "CHECKS FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
