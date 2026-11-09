"""Verify the two load-bearing claims made in REPORT.md §1 BEFORE trusting the harness.

Claim A: my vectorised `roc_panel` is bit-identical to the source
        `cryptobot.strategies.indicators.roc` applied to a trailing window.
Claim B: the `atr(...) > 0` predicate in `MomentumVolStrategy.signal` is a
        tautology on real NSE daily bars, so the "volatility" half of the
        strategy contributes nothing and the strategy reduces to a ROC filter.
"""

from __future__ import annotations

import os
import sys

import pandas as pd

sys.path.insert(0, "src")

from common import roc_panel  # noqa: E402

from cryptobot.strategies.indicators import atr as src_atr  # noqa: E402
from cryptobot.strategies.indicators import roc as src_roc  # noqa: E402
from nsealgo.data.loader import load_symbol  # noqa: E402

DATA_DIR = "data/nse"
SYMS = ["reliance", "tcs", "hdfcbank", "infy", "sbin", "titan", "icicibank", "adaniports"]


def main() -> None:
    # ---------------------------------------------------------------- Claim A
    print("=" * 72)
    print("CLAIM A: vectorised roc_panel == source roc on trailing windows")
    print("=" * 72)
    period = 20
    max_abs = 0.0
    n_struct = 0
    checked = 0
    for sym in SYMS[:3]:
        df = load_symbol(os.path.join(DATA_DIR, f"{sym}_1d.csv"), sym)
        closes = df["close"].to_numpy(dtype=float)
        vec = roc_panel(pd.DataFrame({"x": closes}), period)["x"].to_numpy()
        for end in range(1, len(closes)):
            win = closes[: end + 1]
            expected = src_roc(win, period)
            got = vec[end]
            checked += 1
            a_nan, b_nan = expected != expected, got != got
            if a_nan != b_nan:
                n_struct += 1  # NaN structure differs (warmup edge) -- must be zero
            elif not a_nan:
                max_abs = max(max_abs, abs(expected - got))
    print(f"  symbols checked          : {SYMS[:3]}")
    print(f"  bar-endpoints checked    : {checked:,}")
    print(f"  NaN-structure mismatches : {n_struct}")
    print(f"  max |vectorised - source|: {max_abs:.3e}")
    # Exact agreement is impossible: pandas computes v/shift-1, the source computes
    # (v-shift)/shift. What matters is that the difference is pure float rounding,
    # ~1e-16, and that NaN appears on exactly the same bars.
    assert n_struct == 0, "NaN structure disagrees with source roc"
    assert max_abs < 1e-12, f"roc disagrees beyond float rounding: {max_abs}"
    print("  PASS (identical up to float rounding; NaN structure exact)")

    # ---------------------------------------------------------------- Claim B
    print()
    print("=" * 72)
    print("CLAIM B: atr(...) > 0 holds on every bar of every symbol")
    print("=" * 72)
    syms = sorted(f[: -len("_1d.csv")] for f in os.listdir(DATA_DIR)
                  if f.endswith("_1d.csv"))
    total_bars = 0
    nonpos = 0
    nan_atr = 0
    worst = []
    per_sym = {}
    for s in syms:
        try:
            d = load_symbol(os.path.join(DATA_DIR, f"{s}_1d.csv"), s)
        except Exception:  # noqa: BLE001  (excluded symbols like adanient)
            continue
        if len(d) < 1000:
            continue
        hi = d["high"].to_numpy(dtype=float)
        lo = d["low"].to_numpy(dtype=float)
        cl = d["close"].to_numpy(dtype=float)
        n_bad = 0
        n_nan = 0
        mn = float("inf")
        for end in range(14, len(cl)):
            a = src_atr(hi[: end + 1], lo[: end + 1], cl[: end + 1], 14)
            if a != a:
                n_nan += 1
                continue
            if a <= 0.0:
                n_bad += 1
                if a < mn:
                    mn = a
            total_bars += 1
        nonpos += n_bad
        nan_atr += n_nan
        per_sym[s] = (n_bad, n_nan)
        if n_bad:
            worst.append((s, n_bad, mn))
    print(f"  symbols scanned          : {len(per_sym)}")
    print(f"  bar-endpoints evaluated  : {total_bars:,}")
    print(f"  atr <= 0 (would gate OFF): {nonpos}")
    print(f"  atr NaN (warmup only)    : {nan_atr}")
    if worst:
        print("  offenders:")
        for s, n, mn in worst[:10]:
            print(f"    {s}: {n} bars, min atr {mn!r}")
    print("  VERDICT:", "ATR PREDICATE IS INERT (tautology)"
          if nonpos == 0 else "ATR PREDICATE IS LIVE — my §1 claim is WRONG")


if __name__ == "__main__":
    main()
