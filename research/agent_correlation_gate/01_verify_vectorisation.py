"""Prove the vectorised signal == CorrGateStrategy.signal, bar for bar.

Parity is checked on each symbol's *contiguous* (NaN-dropped) close series, so the
catalog class and the vectorised maths see identical input. On the real panel the
vectorised version additionally refuses to emit a signal on a bar whose price is
missing (a bar you cannot trade) -- that is a strictness addition, not a
divergence, and is reported separately.
"""
from decimal import Decimal

import numpy as np
from common import load, signal_panel

from cryptobot.strategies.catalog.correlation_gate import CorrGateConfig, CorrGateStrategy

panel, symbols, _ = load()
period, thr = 20, 0.01
st = CorrGateStrategy(CorrGateConfig(period=period, threshold=thr, quantity=Decimal("1")))

rng = np.random.default_rng(0)
pick = list(symbols)[:8] + rng.choice(symbols, 6, replace=False).tolist()
bad = checked = 0
for sym in pick:
    closes = panel[sym].dropna()
    vec = signal_panel(closes.to_frame(sym), period, thr)[sym].to_numpy(dtype=float)
    arr = closes.to_numpy(dtype=float)
    got = np.array([st.signal(arr[:i+1], None, None, None) for i in range(len(arr))], float)
    exp = vec.copy()
    exp[: st.warmup(None)] = 0.0          # warmup bars produce no signal
    d = int((got != exp).sum())
    bad += d
    checked += len(arr)
    if d:
        i = int(np.nonzero(got != exp)[0][0])
        print(f"  MISMATCH {sym}: {d} bars, first {closes.index[i].date()} got={got[i]} exp={exp[i]}")
print(f"parity: checked {checked:,} bars / 14 symbols | mismatches = {bad}")
assert bad == 0
print("PARITY OK")

# how much data is untradeable (missing price) on the real panel
miss = panel.isna().mean(axis=0).sort_values(ascending=False)
print("\nmissing-price fraction per symbol (top 8):")
print((miss.head(8) * 100).round(2).to_string())
print(f"universe median missing fraction: {miss.median() * 100:.2f}%  max {miss.max() * 100:.2f}%")
print(f"names with >1% missing bars: {int((miss > 0.01).sum())} / {len(miss)}")
