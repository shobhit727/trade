"""Reconnaissance: audit the panel, then measure how often each Donchian variant
is actually long. Run BEFORE the parameter budget is spent.

Usage: .venv/bin/python research/agent_donchian/recon.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (  # noqa: E402
    TEST_END,
    TEST_START,
    TRAIN_END,
    TRAIN_START,
    breakout_signal,
    literal_signal,
    liveness,
    load_all,
)

PERIODS = (10, 20, 55, 100)


def main() -> None:
    close, high, low, symbols, report = load_all()
    print(report)
    print(f"universe={len(symbols)}  {close.index[0].date()} -> {close.index[-1].date()}"
          f"  bars={len(close)}")
    print("OHLC rebuild == load_universe close panel: OK (asserted)\n")

    # Prove the degeneracy claim numerically rather than by argument.
    c, h = close, high
    inc_high = h.rolling(20, min_periods=20).max()
    strict = c >= inc_high
    hi_eq_close = (c == h)
    print("--- why the as-shipped signal is degenerate (period=20) ---")
    print(f"  bars where close >= max(high[-20:])        : {int(strict.sum().sum()):>9,}")
    print(f"  bars where close == high (same day)         : {int(hi_eq_close.sum().sum()):>9,}")
    both = int((strict & hi_eq_close).sum().sum())
    print(f"  both (i.e. the long signal firing)          : {both:>9,}")
    print(f"  total name-bars                             : {int(c.size):>9,}")
    print(f"  => long-fire rate                           : {both / c.size:.6%}\n")

    windows = [
        ("TRAIN", str(TRAIN_START.date()), str(TRAIN_END.date())),
        ("TEST", str(TEST_START.date()), str(TEST_END.date())),
        ("FULL", str(close.index[0].date()), str(close.index[-1].date())),
    ]

    print("--- signal liveness: fraction of name-bars long / short / flat ---")
    print(f"{'variant':<26}" + "".join(f"{w[0]:>26}" for w in windows))
    print(f"{'':<26}" + "".join(f"{'long / short / flat':>26}" for _ in windows))
    rows = []
    for p in PERIODS:
        lit = literal_signal(close, high, low, p)
        bro = breakout_signal(close, high, low, p)
        for name, sig in ((f"literal p={p}", lit), (f"breakout p={p}", bro)):
            cells = ""
            for _, lo, hi in windows:
                f_long, f_short, f_flat = liveness(sig, lo, hi)
                cells += f"{f_long:>9.2%}{f_short:>8.2%}{f_flat:>8.2%}"
            rows.append((f"{name:<26}" + cells, name, sig))
    for line, _, _ in rows:
        print(line)
    print()


if __name__ == "__main__":
    main()
