"""Resolve the residual mismatches and settle the ROC offset from the real indicator.

Part 1: call cryptobot.strategies.indicators.roc directly (no hand arithmetic) and
        compare against shift(period) and shift(period+1).
Part 2: characterise the residual mismatching bars from the vectorised comparison.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "src")
sys.path.insert(0, "research/agent_correlation_gate")

from common import load  # noqa: E402

from cryptobot.strategies.catalog.correlation_gate import CorrGateStrategy  # noqa: E402
from cryptobot.strategies.indicators import roc, sma  # noqa: E402

period, thr = 20, 0.01

# ---- Part 1: real roc() -----------------------------------------------------
rng = np.random.default_rng(0)
px = 100.0 * np.cumprod(1.0 + rng.normal(0.001, 0.02, 400))
k = len(px) - 1
real = roc(px, period)
cand_period = px[k] / px[k - period] - 1.0
cand_period1 = px[k] / px[k - period - 1] - 1.0
print("PART 1 -- offset of the real roc()")
print(f"  roc(px, {period})                 = {real:.10f}")
print(f"  close[t] / close[t-{period}] - 1   = {cand_period:.10f}  "
      f"match={np.isclose(real, cand_period)}")
print(f"  close[t] / close[t-{period + 1}] - 1 = {cand_period1:.10f}  "
      f"match={np.isclose(real, cand_period1)}")
print(f"  sma(px, {period}) mean check       = {sma(px, period):.6f} vs "
      f"{px[-period:].mean():.6f}  match={np.isclose(sma(px, period), px[-period:].mean())}")
print(f"  roc() warmup: nan at len<=period -> len={period} gives {roc(np.ones(period), period)}, "
      f"len={period + 1} gives {roc(np.ones(period + 1), period)}")

# ---- Part 2: characterise residual mismatches -------------------------------
panel, symbols, _ = load()
sma_ = panel.rolling(period, min_periods=period).mean()
roc_ = panel / panel.shift(period) - 1.0
long_ = (roc_ > thr) & (panel > sma_)
short_ = (roc_ < -thr) & (panel < sma_)
vec = pd.DataFrame(0.0, index=panel.index, columns=panel.columns)
vec = vec.mask(long_, 1.0).mask(short_, -1.0)
vec[sma_.isna() | roc_.isna()] = 0.0

hist = {s: panel[s].dropna() for s in list(panel.columns)[:6]}
st = CorrGateStrategy()
cls = pd.DataFrame(0.0, index=panel.index, columns=panel.columns)
for sym, s in hist.items():
    closes = s.to_numpy(dtype=float)
    cls.loc[s.index, sym] = [
        0.0 if i < period else float(st.signal(closes[: i + 1], None, None, None))
        for i in range(len(closes))
    ]

diff = vec[list(hist)].ne(cls[list(hist)])
print(f"\nPART 2 -- residual mismatches (shift=period vs class): "
      f"{int(diff.sum().sum())} of {diff.size} "
      f"({100 * diff.sum().sum() / diff.size:.4f}%)")

rows = []
for sym in hist:
    for d in diff.index[diff[sym]]:
        rows.append(dict(
            sym=sym, date=d.date(),
            close=panel.loc[d, sym], sma=sma_.loc[d, sym], roc=roc_.loc[d, sym],
            vec=vec.loc[d, sym], cls=cls.loc[d, sym],
        ))
df = pd.DataFrame(rows)
if len(df):
    print(f"  |roc| on mismatching bars: max={df.roc.abs().max():.6f}  "
          f"median={df.roc.abs().median():.6f}")
    print(f"  all mismatches have |roc| within 1e-9 of the {thr} threshold: "
          f"{bool((df.roc.abs() - thr).abs().lt(1e-9).all())}")
    print(f"  any mismatch with |roc| > {thr * 3}: "
          f"{bool((df.roc.abs() > thr * 3).any())}")
    print("\n  sample:")
    print(df.head(6).to_string(index=False))
else:
    print("  exact match everywhere")
