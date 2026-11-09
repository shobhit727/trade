"""Exhaustive equivalence check: vectorised %K panel vs the ACTUAL catalog strategy.

Runs `StochasticStrategy.signal` bar-by-bar on the real CSV bars for EVERY symbol
and EVERY declared variant, and requires byte-equality with the panel used by the
backtest. If this fails, the backtest is testing something other than the assigned
strategy.

Warmup convention (verified against `src/cryptobot/strategies/signal_base.py:102`):
a signal is actionable once `len(closes) >= warmup`, so the first actionable bar is
index `warmup - 1` (0-based). Masking index `warmup` as well would wrongly blank one
good bar.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, "src")

from cryptobot.strategies.catalog.stochastic_strategy import (  # noqa: E402
    StochasticConfig,
    StochasticStrategy,
)
from nsealgo.data.loader import load_symbol, load_universe  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import signal_panel, stoch_k_panel  # noqa: E402

VARIANTS = [
    dict(period=14, lower=20.0, upper=80.0),   # V1
    dict(period=5, lower=20.0, upper=80.0),    # V2
    dict(period=21, lower=20.0, upper=80.0),   # V3
    dict(period=14, lower=10.0, upper=80.0),   # V4
    dict(period=14, lower=30.0, upper=70.0),   # V5
]


def main() -> None:
    panel, symbols, _ = load_universe("data/nse")
    total_bad = 0
    total_bars = 0

    for vi, p in enumerate(VARIANTS, start=1):
        period = int(p["period"])
        lower, upper = float(p["lower"]), float(p["upper"])
        bad_v = bars_v = 0
        for sym in symbols:
            df = load_symbol(f"data/nse/{sym}_1d.csv", sym)
            strat = StochasticStrategy(
                StochasticConfig(period=period, lower=lower, upper=upper))
            closes = df["close"].tolist()
            highs = df["high"].tolist()
            lows = df["low"].tolist()
            vols = df["vol"].tolist()
            w = strat.warmup(closes)

            emitted = np.array(
                [strat.signal(closes[: i + 1], highs[: i + 1], lows[: i + 1],
                              vols[: i + 1])
                 for i in range(len(closes))], dtype=float)
            # First actionable bar is index w-1 (see module docstring).
            emitted = np.where(np.arange(len(emitted)) < w - 1, 0.0, emitted)

            k = stoch_k_panel(
                pd.DataFrame({sym: highs}), pd.DataFrame({sym: lows}),
                pd.DataFrame({sym: closes}), period)
            mine = signal_panel(k, lower, upper).values[:, 0]

            bad = np.nonzero(~np.isclose(emitted, mine, equal_nan=True))[0]
            bad_v += bad.size
            bars_v += len(emitted)
            if bad.size and bad_v <= 6:
                for i in bad[:3]:
                    print(f"   MISMATCH {sym} idx={i} date={df.index[i].date()} "
                          f"catalog={emitted[i]} mine={mine[i]} k={k.values[i, 0]!r}")
        total_bad += bad_v
        total_bars += bars_v
        tag = "OK      " if bad_v == 0 else "MISMATCH"
        print(f"{tag} V{vi} period={period:2d} lower={lower} upper={upper}  "
              f"bars={bars_v}  mismatches={bad_v}")

    print(f"\nTOTAL bars compared={total_bars}  mismatches={total_bad}")
    if total_bad == 0:
        print("VERDICT: vectorised panel is byte-identical to the catalog strategy.")
    else:
        print("VERDICT: DIVERGENT -- the backtest is not testing the assigned strategy.")

    # --- interior NaN audit: does a hole poison the rolling window forever?
    print("\n--- interior-hole audit (shared panel) ---")
    exact_interior = 0
    for s in symbols:
        v = panel[s].notna().to_numpy()
        exact_interior += int((~v[1:-1] & v[:-2] & v[2:]).sum())
    print(f"exact interior holes across {len(symbols)} symbols: {exact_interior}")


if __name__ == "__main__":
    main()
