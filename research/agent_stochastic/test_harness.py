"""Regression tests for the two harness bugs found during this run.

Run: .venv/bin/python research/agent_stochastic/test_harness.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, "src")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import signal_panel  # noqa: E402

from cryptobot.strategies.catalog.stochastic_strategy import (  # noqa: E402
    StochasticConfig,
    StochasticStrategy,
)


def _catalog(kv: float, lower: float, upper: float) -> float:
    """Reference: the catalog's exact if/if chain."""
    if kv != kv:
        return 0.0
    if kv <= lower:
        return 1.0
    if kv >= upper:
        return -1.0
    return 0.0


def test_branch_order_matches_catalog() -> None:
    """BUG 1: the `upper` branch must not overwrite the `lower` branch.

    The catalog checks `k <= lower` FIRST and returns immediately. A chained
    `.mask(k<=lower, 1).mask(k>=upper, -1)` lets the SECOND mask win, which
    inverts the result whenever both conditions hold (only possible when
    `upper <= lower`). This silently corrupted the `upper` sweep.
    """
    grid = [0.0, 10.0, 19.9, 20.0, 20.1, 29.9, 30.0, 30.1, 50.0, 79.9, 80.0, 100.0]
    for lower, upper in ((20.0, 80.0), (30.0, 70.0), (20.0, 20.0),
                         (30.0, 10.0), (30.0, 20.0), (10.0, 80.0)):
        k = pd.DataFrame({"a": grid})
        mine = signal_panel(k, lower, upper)["a"].tolist()
        ref = [_catalog(v, lower, upper) for v in grid]
        bad = [(v, m, r) for v, m, r in zip(grid, mine, ref, strict=True)
                if m != r]
        assert not bad, f"lower={lower} upper={upper}: {bad}"


def test_matches_catalog_strategy_object() -> None:
    """End-to-end against the real strategy class, including warmup NaN."""
    rng = np.random.default_rng(7)
    closes = list(np.cumsum(rng.normal(0, 1, 200)) + 100.0)
    highs = [c * 1.01 for c in closes]
    lows = [c * 0.99 for c in closes]
    vols = [1000.0] * 200

    for period, lower, upper in ((14, 20.0, 80.0), (5, 20.0, 80.0),
                                 (14, 10.0, 80.0), (14, 30.0, 70.0),
                                 (21, 20.0, 80.0)):
        strat = StochasticStrategy(
            StochasticConfig(period=period, lower=lower, upper=upper))
        w = strat.warmup(closes)
        emitted = []
        for i in range(len(closes)):
            s = strat.signal(closes[: i + 1], highs[: i + 1], lows[: i + 1],
                             vols[: i + 1])
            emitted.append(0.0 if i < w - 1 else float(s))

        from common import stoch_k_panel
        k = stoch_k_panel(
            pd.DataFrame({"a": highs}), pd.DataFrame({"a": lows}),
            pd.DataFrame({"a": closes}), period)
        mine = signal_panel(k, lower, upper).values[:, 0].tolist()
        assert emitted == mine, f"period={period} lower={lower} upper={upper}"


def test_long_only_book_ignores_upper() -> None:
    """BUG-adjacent: `upper` can only ever matter via the -1 (short) branch.

    For any `upper` strictly greater than `lower`, the set of names whose signal
    is +1 is IDENTICAL, so a long-only book cannot distinguish them. Asserted
    here so the report's claim is machine-checked rather than asserted in prose.
    """
    rng = np.random.default_rng(11)
    vals = rng.uniform(0, 100, 500)
    k = pd.DataFrame({f"s{i}": vals for i in range(5)})
    lower = 20.0
    longs = []
    for upper in (50.0, 70.0, 80.0, 95.0, 99.0):
        longs.append(set(zip(k.columns, (signal_panel(k, lower, upper) > 0),
                                  strict=True)))
    first = longs[0]
    for u, s in zip((50.0, 70.0, 80.0, 95.0, 99.0), longs, strict=True):
        assert s == first, f"upper={u} changed the long set"


if __name__ == "__main__":
    for fn in (test_branch_order_matches_catalog,
               test_matches_catalog_strategy_object,
               test_long_only_book_ignores_upper):
        fn()
        print(f"PASS {fn.__name__}")
    print("\nall harness regression tests passed")
