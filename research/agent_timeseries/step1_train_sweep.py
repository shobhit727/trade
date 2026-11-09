"""TRAIN-only sweep over the 5 declared variants. Selection happens here.

TEST is never loaded in this script.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research" / "agent_timeseries"))

from harness import (  # noqa: E402
    ENGINE_SHA,
    TRAIN_END,
    TRAIN_START,
    buy_and_hold,
    fmt_row,
    load_panel,
    metrics_of,
    run_window,
    score_from_signal,
)

VARIANTS = [
    ("V1 period=40 thr=0.00 (CATALOG DEFAULT)", 40, 0.00),
    ("V2 period=20 thr=0.00", 20, 0.00),
    ("V3 period=60 thr=0.00", 60, 0.00),
    ("V4 period=126 thr=0.00", 126, 0.00),
    ("V5 period=40 thr=0.02", 40, 0.02),
]


def main() -> None:
    panel, symbols = load_panel()
    print(f"ENGINE_SHA = {ENGINE_SHA}")
    print(f"TRAIN window {TRAIN_START.date()} -> {TRAIN_END.date()}\n")

    rows = []
    for label, period, thr in VARIANTS:
        score = score_from_signal(panel, period, thr)
        res = run_window(panel, score, TRAIN_START, TRAIN_END)
        m = metrics_of(res)
        m["variant"] = label
        m["period"] = period
        m["threshold"] = thr
        rows.append(m)
        print(fmt_row(label, m))

    bh = buy_and_hold(panel, TRAIN_START, TRAIN_END)
    print(fmt_row("BENCH buy-and-hold", bh))

    rows.sort(key=lambda r: -r["sharpe"])
    print("\nTRAIN rank by Sharpe:")
    for i, r in enumerate(rows, 1):
        print(f"  {i}. {r['variant']:<45} Sharpe {r['sharpe']:>6.2f}  "
              f"CAGR {r['cagr'] * 100:>7.2f}%")
    winner = rows[0]
    print(f"\nWINNER (TRAIN Sharpe): {winner['variant']}")

    out = {"engine_sha": ENGINE_SHA, "rows": rows, "buy_hold": bh,
           "winner": winner["variant"]}
    (ROOT / "research" / "agent_timeseries" / "train_sweep.json").write_text(
        json.dumps(out, indent=2, default=str)
    )
    (ROOT / "research" / "agent_timeseries" / "selected_variant.txt").write_text(
        winner["variant"]
    )
    print("wrote train_sweep.json + selected_variant.txt")


if __name__ == "__main__":
    main()
