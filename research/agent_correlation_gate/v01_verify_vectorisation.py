"""Verify the vectorised signal against the REAL CorrGateStrategy class, bar by bar.

The point is to catch index/offset mistakes, so this drives the actual catalog class
over real OHLC arrays and compares to the vectorised panel, bar by bar, on the full
history of several symbols.

Note roc() in indicators.py is:
    prev = closes[-period - 1]  ->  (c[t] - c[t-period-1]) / c[t-period-1]
i.e. a shift of period+1 bars, NOT period. A vectorised `panel/shift(period)` is
off by one bar and will disagree with the class.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "src")
sys.path.insert(0, "research/agent_correlation_gate")

from common import load  # noqa: E402

from cryptobot.strategies.catalog.correlation_gate import (  # noqa: E402
    CorrGateConfig,
    CorrGateStrategy,
)

period, thr = 20, 0.01

# ---- build the vectorised candidate under BOTH conventions ------------------
panel, symbols, _ = load()
sma_ = panel.rolling(period, min_periods=period).mean()


def build(shift: int) -> pd.DataFrame:
    roc_ = panel / panel.shift(shift) - 1.0
    long_ = (roc_ > thr) & (panel > sma_)
    short_ = (roc_ < -thr) & (panel < sma_)
    sig = pd.DataFrame(0.0, index=panel.index, columns=panel.columns)
    sig = sig.mask(long_, 1.0).mask(short_, -1.0)
    sig[sma_.isna() | roc_.isna()] = 0.0
    return sig


# ---- drive the real class over a few symbols --------------------------------
hist = {}
for sym in list(panel.columns)[:6]:
    s = panel[sym].dropna()
    hist[sym] = s

strategies = {sym: CorrGateStrategy(CorrGateConfig(period=period, threshold=thr))
              for sym in hist}

class_sig = pd.DataFrame(0.0, index=panel.index, columns=panel.columns)
for sym, s in hist.items():
    closes = s.to_numpy(dtype=float)
    vals = []
    for i in range(len(closes)):
        if i < period:
            vals.append(0.0)
            continue
        st = strategies[sym]
        vals.append(float(st.signal(closes[: i + 1], None, None, None)))
    # align the class output back onto the panel index
    class_sig.loc[s.index, sym] = vals

print(f"comparing period={period} threshold={thr} over {len(hist)} symbols "
      f"({len(panel)} bars each)\n")

for shift in (period, period + 1):
    v = build(shift)
    diff = v[list(hist)].ne(class_sig[list(hist)])
    print(f"  shift={shift:<3} (shift {shift - period:+d} vs the class)  "
          f"mismatching (symbol,bar) cells: {int(diff.sum().sum()):>8}  "
          f"of {diff.size}")
    if int(diff.sum().sum()):
        per = diff.sum()[diff.sum() > 0].sort_values(ascending=False)
        print(f"      worst symbols: {dict(per.head(4))}")

# also confirm the roc offset analytically
closes = np.array([1.0 * (1.01**i) for i in range(60)])
st = CorrGateStrategy(CorrGateConfig(period=period, threshold=0.0))
k = len(closes) - 1
true_roc = (closes[k] - closes[k - period - 1]) / closes[k - period - 1]
off1_roc = (closes[k] - closes[k - period]) / closes[k - period]
print(f"\n  analytic ROC at last bar: class={true_roc:.6f}  "
      f"shift(period)={off1_roc:.6f}  equal={np.isclose(true_roc, off1_roc)}")
print(f"  warmup() returns {st.warmup(closes)} but roc() needs period+1={period + 1} bars")
