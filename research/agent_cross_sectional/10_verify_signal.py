"""Step 10 — prove the vectorised signal is identical to the catalog class.

The whole run hangs off this. If `build_score`'s signal panel disagreed with
`CrossSectionalStrategy.signal` by even one bar, every downstream number would be
about a different strategy than the one I was assigned.

The catalog class is stateless given `closes`, and `roc(closes, period)` reads
only `closes[-1]` and `closes[-period-1]`, so feeding the full close history up
to and including bar *t* reproduces exactly what the streaming engine sees at *t*.
"""

from __future__ import annotations

import sys

sys.path.insert(0, "src")
sys.path.insert(0, "research/agent_cross_sectional")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from common import strategy_signal  # noqa: E402

from cryptobot.strategies.catalog.cross_sectional_strategy import (  # noqa: E402
    CrossSectionalConfig,
    CrossSectionalStrategy,
)
from nsealgo.data.loader import load_universe  # noqa: E402

panel, symbols, _ = load_universe("data/nse")
print(f"panel {panel.shape}")

ok_all = True
for period, threshold in [(20, 0.015), (60, 0.05), (126, 0.08)]:
    strat = CrossSectionalStrategy(
        CrossSectionalConfig(period=period, threshold=threshold)
    )
    assert strat.warmup([]) == period
    vec = strategy_signal(panel, period, threshold)

    mismatches = 0
    compared = 0
    first_bad = None
    for sym in symbols:
        closes = panel[sym].to_numpy(dtype=float)
        ref = np.array(
            [strat.signal(closes[: t + 1].tolist(), None, None, None)
             for t in range(len(closes))]
        )
        got = vec[sym].to_numpy(dtype=float)
        # A NaN inside the ROC window makes the catalog class read NaN, which is
        # outside its warmup contract — exclude those bars from the comparison.
        finite_window = (
            pd.Series(np.isfinite(closes).astype(int))
            .rolling(period + 1).sum()
            .eq(period + 1)
            .to_numpy()
        )
        ok = np.isfinite(ref) & finite_window
        compared += int(ok.sum())
        bad = np.flatnonzero(ok & (ref != got))
        if len(bad):
            mismatches += len(bad)
            if first_bad is None:
                i = int(bad[0])
                first_bad = (sym, str(panel.index[i].date()), float(ref[i]), float(got[i]))

    status = (
        "IDENTICAL"
        if mismatches == 0
        else f"MISMATCH n={mismatches} first={first_bad}"
    )
    ok_all &= mismatches == 0
    print(
        f"  period={period:<4} thr={threshold:<6} "
        f"bars compared={compared:>8,}  -> {status}"
    )

print(f"\nVERDICT: {'vectorised signal == catalog class' if ok_all else 'FAILED'}\n")

print("Signal state distribution (fraction of name-bars):")
for period, threshold in [(20, 0.015), (60, 0.05), (126, 0.08)]:
    sig = strategy_signal(panel, period, threshold)
    for label, idx in [("TRAIN", panel.loc["2016":"2023"].index),
                       ("TEST ", panel.loc["2024":].index)]:
        s = sig.loc[idx].to_numpy()
        print(
            f"  period={period:<4} thr={threshold:<6} {label}  "
            f"long {(s > 0).mean() * 100:5.1f}%  "
            f"flat {(s == 0).mean() * 100:5.1f}%  "
            f"short {(s < 0).mean() * 100:5.1f}%"
        )
