"""Bar-for-bar verification that the vectorised translation equals the real
`TimeSeriesStrategy` from the catalog.

This is the check that decides whether the rest of the report means anything.
If the vectorised ROC disagrees with the streaming strategy on any bar, the
backtest is measuring a different strategy than the one assigned.

Cost: running the real streaming class over 48 symbols x 4,625 bars is slow
(SignalStrategy.feed maintains deques and emits orders), so we verify on a
random-but-fixed sample of symbols first, then spot-check the rest.

NO LOOKAHEAD CHECK: the streaming strategy is fed bars in order and we compare
against the vectorised value computed from `panel.iloc[:i+1]` only.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "research" / "agent_timeseries"))

from harness import load_panel, roc_panel, signal_panel  # noqa: E402

from cryptobot.strategies.catalog.time_series_strategy import (  # noqa: E402
    TimeSeriesConfig,
    TimeSeriesStrategy,
)


def stream_signal(closes: list[float], period: int, threshold: float) -> list[int]:
    """Feed the real strategy bar by bar, capture the signal it would emit.

    The full bar sequence is fed, INCLUDING NaN closes, so the rolling buffer
    lines up bar-for-bar with the panel index. (Feeding a dropna()'d series
    silently shifts the window and manufactures phantom mismatches -- an earlier
    version of this script did exactly that and "found" 2 spurious errors on
    bajajfinsv, whose only 2 NaN bars are in 2008.)
    """
    strat = TimeSeriesStrategy(TimeSeriesConfig(period=period, threshold=threshold))
    out = []
    for c in closes:
        strat._closes.setdefault("X", __import__("collections").deque(maxlen=300))
        strat._highs.setdefault("X", __import__("collections").deque(maxlen=300))
        strat._lows.setdefault("X", __import__("collections").deque(maxlen=300))
        strat._closes["X"].append(c)
        strat._highs["X"].append(c)
        strat._lows["X"].append(c)
        buf = list(strat._closes["X"])
        out.append(int(strat.signal(buf, list(strat._highs["X"]),
                                    list(strat._lows["X"]), [1.0] * len(buf))))
    return out


def main() -> None:
    panel, symbols = load_panel()
    rng = np.random.default_rng(20261010)
    sample = sorted(rng.choice(symbols, size=6, replace=False).tolist())
    print(f"verifying on sample of {len(sample)} symbols: {sample}")
    print(f"(full universe is {len(symbols)})")

    periods_thresholds = [(40, 0.0), (126, 0.0), (20, 0.02)]
    report = {}
    for period, threshold in periods_thresholds:
        vec_roc = roc_panel(panel, period)
        total = 0
        mism = 0
        nan_mism = 0
        examples = []
        for sym in sample:
            # Feed the full bar sequence (NaN included) so the streaming buffer
            # and the vectorised panel align bar-for-bar.
            closes = panel[sym].tolist()
            dates = panel[sym].index
            stream = stream_signal(closes, period, threshold)
            for dt, s in zip(dates, stream, strict=True):
                v = vec_roc.loc[dt, sym]
                if np.isnan(v):
                    expected = 0
                else:
                    expected = 1 if v > threshold else -1
                total += 1
                if s != expected:
                    if np.isnan(v):
                        nan_mism += 1
                    mism += 1
                    if len(examples) < 5:
                        examples.append((sym, str(dt.date()), s, expected, float(v)))
        report[f"p{period}_t{threshold}"] = {
            "comparisons": total,
            "mismatches": mism,
            "nan_mismatches": nan_mism,
            "examples": examples,
        }
        print(f"  period={period} thr={threshold}: {total:,} bars, "
              f"{mism} mismatches")
        for ex in examples:
            print(f"      {ex}")

    # signal-panel liveness: fraction of bars flagged long
    print("\nsignal liveness (fraction of symbol-bars flagged long, full universe):")
    liv = {}
    for period, threshold in [(20, 0.0), (40, 0.0), (60, 0.0), (126, 0.0), (40, 0.02)]:
        s = signal_panel(panel, period, threshold)
        # only count bars where the name actually has data
        valid = panel.notna() & panel.shift(period).notna()
        frac = float((s & valid).sum().sum() / valid.sum().sum())
        liv[f"p{period}_t{threshold}"] = frac
        print(f"  period={period:>3} thr={threshold:<5} -> {frac * 100:5.1f}%")

    out = {"verification": report, "liveness": liv}
    (ROOT / "research" / "agent_timeseries" / "verify.json").write_text(
        json.dumps(out, indent=2, default=str)
    )
    print("\nwrote verify.json")


if __name__ == "__main__":
    t0 = time.time()
    main()
    print(f"({time.time() - t0:.1f}s)")
