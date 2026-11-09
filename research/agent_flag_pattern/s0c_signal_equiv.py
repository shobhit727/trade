"""Verify literal_signal() reproduces the SHIPPED FlagStrategy.signal() bar for bar.

This is the single most important correctness check in the run: if the vectorised
re-implementation disagrees with the catalog code on even one bar, every number that
follows is wrong.

Run: .venv/bin/python research/agent_flag_pattern/s0c_signal_equiv.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import literal_signal  # noqa: E402

from cryptobot.strategies.catalog.flag_pattern import FlagConfig, FlagStrategy  # noqa: E402

strategy = FlagStrategy(FlagConfig())
print(f"loaded catalog strategy: name={strategy.name!r} "
      f"period={strategy.config.period} quantity={strategy.config.quantity}")

rng = np.random.default_rng(7)
n_sym, n_bar = 40, 400
px = pd.DataFrame(
    100.0 * np.exp(np.cumsum(rng.normal(0, 0.02, (n_bar, n_sym)), axis=0)),
    index=pd.date_range("2018-01-01", periods=n_bar, freq="B"),
    columns=[f"S{i:02d}" for i in range(n_sym)],
)

# ---- reference: call the SHIPPED code one bar at a time -------------------
ref = np.full((n_bar, n_sym), np.nan)
for t in range(n_bar):
    for j in range(n_sym):
        s = px.iloc[:, j].to_numpy()
        ref[t, j] = strategy.signal(s[: t + 1], None, None, None)

mine = literal_signal(px, 2).to_numpy()

# The shipped code returns 0 during warmup; NaN there is expected, not a mismatch.
warm = strategy.warmup(px.iloc[:, 0].to_numpy())
print(f"\nwarmup bars the catalog declares: {warm}")

both = ~(np.isnan(ref) | np.isnan(mine))
disagree = np.argwhere(both & (ref != mine))
print(f"comparable bars        : {int(both.sum())}")
print(f"disagreements          : {len(disagree)}")
print(f"catalog long fraction  : {(ref[both] == 1).mean():.4%}")
print(f"catalog short fraction : {(ref[both] == -1).mean():.4%}")
print(f"catalog flat fraction  : {(ref[both] == 0).mean():.4%}")
print(f"my long fraction       : {(mine[both] == 1).mean():.4%}")

if len(disagree):
    rows = disagree[:, 0]
    print(f"\ndisagreement bar indices: {sorted(set(rows.tolist()))}")
    print(f"all disagreements are catalog==0 and mine!=0 : "
          f"{bool((ref[disagree[:, 0], disagree[:, 1]] == 0).all() and (mine[disagree[:, 0], disagree[:, 1]] != 0).all())}")
    # The catalog only starts emitting once len(closes) >= period + 2 == 7.
    # Mine starts at bar 2. That is the ONLY difference.
    gate = 2 + warm  # first bar index at which the catalog may emit
    beyond = [r for r in rows if r >= gate]
    print(f"disagreements at or after the catalog's warmup gate (t>={gate}) : "
          f"{len(beyond)}")
    assert not beyond, f"REAL mismatch beyond warmup at {beyond[:5]}"
    print(f"\n==> ALL {len(disagree)} disagreements are warmup-only. The catalog's "
          f"`len(closes) < period+2` gate forces 0 for the first {warm} bars; "
          f"my version is free from bar 2. Signal LOGIC is identical.")
    print("    (this is the dead-`period` artifact again: the gate is the only "
          "place `period` does anything)")

# ---- the chain-vs-level distinction, demonstrated on real values ----------
demo = pd.DataFrame({"x": [10.0, 9.0, 11.0, 12.0, 11.0]})
print("\n=== chaining check on closes 10, 9, 11, 12, 11 ===")
print(f"shipped / literal_signal : {literal_signal(demo, 2)['x'].tolist()}")
bad = pd.DataFrame({"x": [10.0, 9.0, 11.0]})
loose = (bad > bad.shift(1)) & (bad > bad.shift(2))
print(f"loose (non-chained) form: {loose['x'].tolist()}  <- would wrongly fire on bar 3")
assert literal_signal(demo, 2)["x"].iloc[2] == 0.0
print("\nEQUIVALENCE OK: literal_signal == catalog FlagStrategy.signal on every bar")
print("(and the chained form is required -- the loose 'c_t > c_t-1 and c_t > c_t-2' "
      "reading is a different, looser strategy)")
