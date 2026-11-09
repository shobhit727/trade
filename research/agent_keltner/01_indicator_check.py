"""Step 01 — prove the vectorised port IS the catalog strategy, bar for bar.

The whole result rests on the claim that `common.keltner_depth` reproduces
`KeltnerStrategy.signal`. That claim is verified here against the real catalog object
on real NSE bars, for every declared period, before any backtest is run.

Compares two things per bar:
  * the catalog's returned signal (+1 / 0 / -1), and
  * the boolean `depth > multiplier` my port derives.
"""

from __future__ import annotations

import sys

sys.path.insert(0, "research/agent_keltner")
sys.path.insert(0, "src")

import numpy as np
from common import keltner_depth, load_ohlc, load_panel  # noqa: E402

from cryptobot.strategies.catalog.keltner_channel import (  # noqa: E402
    KeltnerConfig,
    KeltnerStrategy,
)

panel = load_panel()
ohlc = load_ohlc()
close, high, low = panel, ohlc["high"], ohlc["low"]

# Bounded scan: 250 bars per symbol ending at the TRAIN boundary. Enough to exercise the
# indicator's whole state, cheap enough to leave running.
N_BARS = 250
END = "2023-12-31"
SYMBOLS = list(panel.columns)

#: `SignalStrategy` feeds the subclass a `deque(maxlen=300)` of history, so the catalog
#: sees at most the last 300 bars -- and `ema()` seeds its recursion at values[0], so
#: that seed sits 300 bars back. At period=20, k = 2/21, so the seed's remaining weight
#: is (1-k)**300 = 8.5e-14: a full-history EMA and a 300-bar-buffered EMA are the same
#: number to 13 decimals. This window reproduces what the catalog is actually given; a
#: short slice would reseed the EMA and manufacture mismatches that mean nothing.
WINDOW = 300

for period, multiplier in [(20, 2.0), (40, 2.0)]:
    depth = keltner_depth(close, high, low, period)
    strat = KeltnerStrategy(KeltnerConfig(period=period, multiplier=multiplier))
    warm = strat.warmup(None)

    n_checked = n_mismatch = n_nan_agree = 0
    mismatches: list[str] = []
    per_sym_mismatch: dict[str, int] = {}

    for sym in SYMBOLS:
        c = close[sym].loc[:END].to_numpy(dtype=float)
        h = high[sym].loc[:END].to_numpy(dtype=float)
        lo = low[sym].loc[:END].to_numpy(dtype=float)
        d = depth[sym].loc[:END].to_numpy(dtype=float)

        start = max(warm + 1, len(c) - N_BARS)
        for i in range(start, len(c)):
            w = slice(max(0, i - (WINDOW - 1)), i + 1)   # == the deque(maxlen=300) feed
            sig = strat.signal(c[w], h[w], lo[w], None)
            my_long = (not np.isnan(d[i])) and d[i] > multiplier
            n_checked += 1
            if np.isnan(d[i]):
                n_nan_agree += int(sig == 0)
                continue
            # catalog +1 == close < mid - mult*b  <=>  my (mid-close)/b > mult
            if (sig == 1) != bool(my_long):
                n_mismatch += 1
                per_sym_mismatch[sym] = per_sym_mismatch.get(sym, 0) + 1
                if len(mismatches) < 5:
                    mismatches.append(
                        f"{sym} bar {i}: catalog={sig} mine_long={my_long} depth={d[i]:.6f}"
                    )

    print(f"period={period} multiplier={multiplier}")
    print(f"  bars checked          : {n_checked}")
    print(f"  mismatches            : {n_mismatch}")
    print(f"  NaN-depth bars (signal 0 expected): {n_nan_agree}")
    if mismatches:
        print("  examples:")
        for m in mismatches:
            print("   ", m)
        print("  per-symbol:", per_sym_mismatch)
    print()

# Also record the distribution of band depth -- this is the liveness input.
print("=" * 78)
print("BAND DEPTH DISTRIBUTION ((mid - close) / ATR, ATR units, period=20)")
print("=" * 78)
d20 = keltner_depth(close, high, low, 20)
fin = d20.stack()
print(fin.describe(percentiles=[0.01, 0.05, 0.10, 0.25, 0.5, 0.75, 0.95]))
print()
for m in (1.5, 2.0, 2.5, 3.0, 3.5):
    print(f"  P(depth > {m}) = {float((d20 > m).to_numpy().mean()) * 100:6.3f}% of cells")
print()
print("NOTE: gate is evaluated at rebalance dates only (monthly), so the relevant")
print("number is mean names flagged per rebalance bar, printed next.")
for period in (20, 40):
    dd = keltner_depth(close, high, low, period)
    for m in (2.0, 2.5):
        g = (dd > m).sum(axis=1)
        g_tr = g.loc["2016-01-01":"2023-12-31"]
        g_te = g.loc["2024-01-01":"2026-10-01"]
        print(
            f"  p={period} m={m}: names flagged/rebalance-bar  "
            f"TRAIN mean {g_tr.mean():5.2f} median {g_tr.median():5.1f} "
            f"p90 {g_tr.quantile(0.9):5.1f} max {g_tr.max():5.0f}  |  "
            f"TEST mean {g_te.mean():5.2f} median {g_te.median():5.1f}"
        )
