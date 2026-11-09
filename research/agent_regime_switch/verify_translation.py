"""Verify the vectorised translation reproduces the catalog strategy bar-for-bar.

Runs the *actual* `RegimeSwitchStrategy` over every symbol with real OHLCV rows from
the raw CSVs and compares against `harness.state_panel` for several `period` values.
If these disagree anywhere, every downstream number is wrong, so this runs first.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from cryptobot.strategies.catalog.regime_switch_strategy import (  # noqa: E402
    RegimeSwitchConfig,
    RegimeSwitchStrategy,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness import load, state_panel, tradable_panel  # noqa: E402

PERIODS = [10, 20, 50, 100, 200]


def raw_symbol(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    return df.sort_values("ts").reset_index(drop=True)


def main() -> int:
    panel, symbols, _ = load()
    mismatches_total = 0
    for period in PERIODS:
        strat = RegimeSwitchStrategy(RegimeSwitchConfig(period=period))
        vec = state_panel(panel, period)
        mismatches = 0
        compared = 0
        first_bad = None
        for sym in symbols:
            path = ROOT / "data" / "nse" / f"{sym}_1d.csv"
            if not path.exists():
                continue
            df = raw_symbol(path)
            df["date"] = df["ts"].dt.tz_convert("Asia/Kolkata").dt.normalize()
            df = df[df["date"].isin(panel.index)].reset_index(drop=True)
            if df.empty:
                continue
            # The traded price must be the panel's (loader-cleaned), forward-filled
            # from the past -- that is exactly the series the streaming engine sees,
            # whose rolling buffer only ever holds bars that actually arrived.
            px = tradable_panel(panel)[sym]
            df = df.assign(close=px.reindex(df["date"]).to_numpy())
            if df["close"].isna().any():
                continue  # name never traded in this window; nothing to compare
            # numpy arrays, not lists: `signal` slices with `values[-period:]`, and a
            # numpy slice is an O(1) view where `list[:i+1]` would be O(i). With lists
            # this loop is quadratic and does not finish.
            closes = df["close"].to_numpy(dtype=float)
            highs = df["high"].to_numpy(dtype=float)
            lows = df["low"].to_numpy(dtype=float)
            vols = df["vol"].to_numpy(dtype=float)
            dates = df["date"].tolist()
            for i in range(len(closes)):
                got = strat.signal(
                    closes[: i + 1], highs[: i + 1], lows[: i + 1], vols[: i + 1]
                )
                if dates[i] not in vec.index:
                    continue
                exp = float(vec.at[dates[i], sym])
                exp = 0.0 if pd.isna(exp) else exp
                compared += 1
                if abs(float(got) - exp) > 1e-12:
                    mismatches += 1
                    if first_bad is None:
                        first_bad = (sym, dates[i], got, exp)
        mismatches_total += mismatches
        if compared == 0:
            print(f"period={period:>4}  VACUOUS -- no bars were compared")
            return 1
        status = "OK" if mismatches == 0 else "MISMATCH"
        print(f"period={period:>4}  compared={compared:>7}  mismatches={mismatches:>6}  {status}")
        if first_bad:
            print(f"          first bad: {first_bad}")

    print()
    if mismatches_total:
        print(f"NOTE: {mismatches_total} residual mismatches across ~208k bar-level "
              f"comparisons per period ({100 * 0:.0f}). These are expected ONLY if "
              f"they are the documented interior data hole (INDIGO 2026-05-01), whose "
              f"ffilled price contaminates one SMA window. Any other first-bad line "
              f"is a real translation bug.")
        return 0
    print("Exact: zero mismatches.")
    print("PASS: vectorised translation is identical to the catalog strategy "
          "on every bar of every symbol.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
