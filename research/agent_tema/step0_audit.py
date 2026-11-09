"""Step 0 -- audit.

Three jobs, all before any parameter is chosen:

1. Reproduce the `load_universe` cleaning report.
2. **Verify** that my vectorised TEMA equals `cryptobot.strategies.indicators.tema`
   called bar-by-bar on the observed bar sequence. This is asserted numerically, not
   argued from reading the source.
3. Check the source `TemaStrategy.signal` really is `close > tema` by calling it.

Nothing here touches TEST results.
"""

from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "src")

from cryptobot.strategies.catalog.tema_strategy import TemaConfig, TemaStrategy  # noqa: E402
from cryptobot.strategies.indicators import tema as ref_tema  # noqa: E402
from nsealgo.data.loader import load_universe  # noqa: E402

OUT = {}


def audit_panel() -> pd.DataFrame:
    panel, symbols, report = load_universe("data/nse")
    print(report.describe())
    print("\npanel", panel.shape, panel.index[0], panel.index[-1])
    n_gaps = int(panel.isna().sum().sum())
    print(f"NaN cells: {n_gaps}  ({n_gaps / panel.size:.4%})")
    print(f"symbols with any NaN: {int(panel.isna().any().sum())}")
    # per-symbol first valid date
    fv = panel.apply(lambda s: s.first_valid_index())
    print(f"first valid date: min={fv.min().date()} max={fv.max().date()}")
    OUT["panel"] = {
        "shape": list(panel.shape),
        "start": str(panel.index[0]),
        "end": str(panel.index[-1]),
        "nan_cells": n_gaps,
        "symbols": len(symbols),
    }
    return panel


# --------------------------------------------------------------------------- #
# The replication under test
# --------------------------------------------------------------------------- #


def tema_series(values, period: int) -> np.ndarray:
    """Full TEMA series, one value per input bar, prefix-stable.

    Identical structure to the reference: three chained prefix-stable EMAs.
    """
    a = np.asarray(values, dtype=float)
    k = 2.0 / (period + 1.0)

    def ema(x: np.ndarray) -> np.ndarray:
        out = np.empty(len(x), dtype=float)
        out[0] = x[0]
        for i in range(1, len(x)):
            out[i] = k * x[i] + (1.0 - k) * out[i - 1]
        return out

    e1 = ema(a)
    e2 = ema(e1)
    e3 = ema(e2)
    return 3.0 * e1 - 3.0 * e2 + e3


def verify_tema_replication(panel: pd.DataFrame, periods=(20, 50, 100)) -> dict:
    """Compare my vectorised TEMA against the reference, per symbol, per period."""
    worst = {}
    rng = np.random.default_rng(0)
    syms = list(panel.columns)
    check_syms = list(rng.choice(syms, size=min(8, len(syms)), replace=False))
    for p in periods:
        worst_abs = 0.0
        worst_rel = 0.0
        for s in check_syms:
            obs = panel[s].dropna()          # the bars the streaming feed would see
            if len(obs) < p + 10:
                continue
            vals = obs.to_numpy()
            mine = tema_series(vals, p)
            # Reference: the strategy is fed the bar history ending at some bar, so
            # the reference value at index j is `tema(vals[:j+1])`. Compare that against
            # my series at the SAME index j. (Prefix-stability is what makes this a
            # valid equivalence, so it is also being tested by this comparison.)
            for j in (len(vals) - 1, len(vals) - 2, len(vals) - 5, 400, 300, 250, 150):
                if j < p + 2 or j >= len(vals):
                    continue
                ref = ref_tema(list(vals[: j + 1]), p)
                got = mine[j]
                if np.isnan(ref):
                    continue
                worst_abs = max(worst_abs, abs(got - ref))
                worst_rel = max(worst_rel, abs(got - ref) / max(abs(ref), 1e-9))
        worst[p] = {"max_abs": worst_abs, "max_rel": worst_rel}
        print(f"period={p:>3}  max|Δ| = {worst_abs:.3e}   max rel = {worst_rel:.3e}")
    OUT["tema_replication"] = {str(k): v for k, v in worst.items()}
    # assert exactness to float noise
    assert max(v["max_rel"] for v in worst.values()) < 1e-10, "TEMA replication mismatch"
    return worst


def verify_source_signal(panel: pd.DataFrame) -> dict:
    """Call the real `TemaStrategy.signal` and confirm it is `close > tema`."""
    strat = TemaStrategy(TemaConfig(period=20))
    s = list(panel.columns)[0]
    obs = panel[s].dropna().to_numpy()
    rows = []
    for end in (300, 800, 1500, len(obs)):
        buf = obs[:end]
        sig = strat.signal(buf, buf, buf, buf)
        t = ref_tema(buf, 20)
        expect = 1 if buf[-1] > t else -1
        rows.append({"bars": end, "signal": int(sig), "expected": expect, "tema": t})
    ok = all(r["signal"] == r["expected"] for r in rows)
    print("\nsource signal check:", json.dumps(rows, indent=1))
    print("source signal == (close > tema):", ok)
    # warmup
    w = strat.warmup([1, 2, 3])
    print("warmup(period=20):", w)
    OUT["source_signal"] = {"matches": bool(ok), "rows": rows, "warmup": w}
    assert ok
    return OUT["source_signal"]


def main() -> None:
    panel = audit_panel()
    verify_tema_replication(panel)
    verify_source_signal(panel)
    with open("research/agent_tema/audit.json", "w") as f:
        json.dump(OUT, f, indent=2, default=str)
    print("\nAUDIT OK")


if __name__ == "__main__":
    main()
