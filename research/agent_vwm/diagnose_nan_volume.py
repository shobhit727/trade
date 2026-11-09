"""Why is `avg_vol` NaN for `indigo`? Quantify volume missingness panel-wide.

The previous script showed every signal difference concentrated on `indigo`, with a
*real* volume observation but a NaN 20/63/126-day mean. That points at scattered
NaN volume prints: `rolling(period).mean()` with `min_periods=period` yields NaN if
ANY of the window's values is NaN, and the strategy then returns 0 forever after.

If that is the mechanism, the correct reading is not "volume values matter" but
"one missing print silently disables the strategy for that name".
"""

from __future__ import annotations

import glob
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research/agent_vwm")

from common import (  # noqa: E402
    TEST_END,
    TEST_START,
    TRAIN_END,
    TRAIN_START,
    avg_volume_panel,
    load_panels,
)


def main() -> None:
    px, vol, _ = load_panels()

    print("=" * 74)
    print("A. Missing volume in the CLEANED panel")
    print("=" * 74)
    miss = vol.isna()
    per = miss.sum().sort_values(ascending=False)
    per = per[per > 0]
    print(f"  symbols with ANY missing volume: {len(per)} of {vol.shape[1]}")
    print(f"  total missing cells: {int(miss.to_numpy().sum()):,} "
          f"/ {vol.size:,} = {miss.to_numpy().mean():.4%}")
    if len(per):
        print("  by symbol:")
        for s, n in per.items():
            print(f"    {s:<12} {n:>5}")

    print()
    print("=" * 74)
    print("B. RAW files: are these blanks in the CSV, or introduced by cleaning?")
    print("=" * 74)
    raw_blank = {}
    for f in sorted(glob.glob("data/nse/*_1d.csv")):
        sym = f.split("/")[-1][: -len("_1d.csv")]
        d = pd.read_csv(f)
        n_blank = int(d["vol"].isna().sum())
        if n_blank:
            raw_blank[sym] = n_blank
    if raw_blank:
        for s, n in sorted(raw_blank.items(), key=lambda kv: -kv[1]):
            print(f"    {s:<12} {n:>5} blank vol cells in the raw CSV")
    else:
        print("    none -- every raw CSV has vol populated on every row")

    print()
    print("=" * 74)
    print("C. CONSEQUENCE: how long is each variant silenced by NaN windows?")
    print("=" * 74)
    for period in (20, 63, 126, 252):
        avg = avg_volume_panel(vol, period)
        dead = avg.isna()
        rows = dead.any(axis=1)
        print(f"  period={period:>3}: avg_vol is NaN on {int(dead.to_numpy().sum()):>6,} "
              f"cells; {int(rows.sum()):>5} calendar dates have >=1 silenced name")
        if per.index.size:
            top = dead[list(per.index)].sum().sort_values(ascending=False)
            top = top[top > 0]
            for s, n in top.head(5).items():
                print(f"      {s:<12} silenced on {n:>5} dates "
                      f"({n / len(vol):.2%} of the panel)")

    print()
    print("=" * 74)
    print("D. Are the missing volumes concentrated in TEST? (window-stability check)")
    print("=" * 74)
    for name, (s, e) in {
        "TRAIN": (TRAIN_START, TRAIN_END),
        "TEST": (TEST_START, TEST_END),
    }.items():
        v = vol.loc[(vol.index >= s) & (vol.index <= e)]
        m = int(v.isna().to_numpy().sum())
        print(f"  {name}: {m:>5} missing volume cells "
              f"({m / v.size:.4%} of {v.size:,})")

    print()
    print("=" * 74)
    print("E. Sanity: is `indigo` volume blank *between* real prints?")
    print("=" * 74)
    if "indigo" in vol.columns:
        s = vol["indigo"]
        na = s.index[s.isna()]
        print(f"  indigo: {len(na)} missing dates, range "
              f"{na.min().date()} .. {na.max().date()}" if len(na) else "  none")
        print(na[:12].strftime("%Y-%m-%d").tolist() if len(na) else "")
        # run lengths of consecutive missing
        v = s.isna().to_numpy()
        if v.any():
            new = np.empty(v.size, dtype=bool)
            new[0] = True
            np.not_equal(v[1:], v[:-1], out=new[1:])
            rid = np.cumsum(new) - 1
            lens = np.bincount(rid)
            miss_runs = lens[(np.bincount(rid) > 0) & v[np.searchsorted(rid, np.arange(lens.size))]
                             ] if False else lens[(np.unique(rid)[v[np.cumsum(new) - 1]])]
            print(f"  missing-run lengths: {sorted(set(miss_runs.tolist()))}")
            print(f"  longest missing run: {int(miss_runs.max())} bars")

    print()
    print("=" * 74)
    print("F. Volume integer check — is `vol` a share count or a rupee notional?")
    print("=" * 74)
    med = vol.median()
    print("  median daily vol, 5 symbols:")
    for s in list(vol.columns)[:5]:
        print(f"    {s:<12} {med[s]:>15,.0f} shares   "
              f"median close Rs {px[s].median():>10,.1f}  "
              f"=> notional Rs {med[s] * px[s].median():>18,.0f}")
    print("  (a share count, not rupee turnover -- the loader has no value field)")


if __name__ == "__main__":
    main()
