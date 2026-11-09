"""Step 0 (mandatory): data audit + cost sanity check. Prints only."""

from __future__ import annotations

import pandas as pd
from common import COST, TEST_END, load_panel


def main() -> None:
    pd.set_option("display.width", 200)

    panel, symbols, report = load_panel()
    print(report.describe())
    print(f"\nsymbols kept      : {len(symbols)}")
    print(f"panel shape       : {panel.shape}")
    print(f"index             : {panel.index.min().date()} -> {panel.index.max().date()}")
    print(f"tz                : {panel.index.tz}")

    # Per-symbol coverage over the two protocol windows.
    print("\n--- coverage ---")
    for lo, hi, tag in (
        (pd.Timestamp("2016-01-01", tz="Asia/Kolkata"),
         pd.Timestamp("2023-12-31", tz="Asia/Kolkata"), "TRAIN"),
        (pd.Timestamp("2024-01-01", tz="Asia/Kolkata"), TEST_END, "TEST "),
    ):
        sub = panel.loc[(panel.index >= lo) & (panel.index <= hi)]
        n = sub.notna().sum()
        print(f"{tag} {lo.date()}..{hi.date()}: {sub.shape[0]:>5} bars, "
              f"names w/ >=90% coverage: {int((n / sub.shape[0] >= 0.90).sum()):>3}/"
              f"{len(symbols)}, min bars {int(n.min())}")

    # NaN structure matters: the panel is not fully rectangular, so a naive
    # pct_change on a forward-filled panel would be a look-ahead.
    tot = panel.size
    print(f"\nNaN cells         : {int(panel.isna().sum().sum()):,}/{tot:,} "
          f"({panel.isna().sum().sum() / tot * 100:.2f}%)")
    fully = [c for c in panel.columns if panel[c].notna().all()]
    print(f"fully dense names : {len(fully)}/{len(symbols)}")

    print("\n--- cost sanity check (brief §3) ---")
    from decimal import Decimal

    for n in (50_000, 100_000, 500_000):
        print(f"  Rs {n:>7,} round trip (statutory) : "
              f"{COST.round_trip_bps(Decimal(n))} bps")
    print(f"  Rs   100,000 all-in (+ 2x5bps slip) : "
          f"{COST.all_in_round_trip_bps(Decimal(100_000))} bps")
    print("  brief expects ~11.9 bps at Rs 1L/side")

    print("\n--- market context, equal-weight proxy ---")
    mkt = panel.pct_change(fill_method=None).mean(axis=1)
    for tag, lo, hi in (
        ("TRAIN", "2016-01-01", "2023-12-31"),
        ("TEST ", "2024-01-01", "2026-10-01"),
    ):
        r = mkt.loc[(mkt.index >= lo) & (mkt.index <= hi)].fillna(0.0)
        eq = (1 + r).cumprod()
        yrs = len(r) / 244
        print(f"  {tag}: {len(r):>5} bars, cum {eq.iloc[-1] - 1:>8.2%}, "
              f"CAGR {eq.iloc[-1] ** (1 / yrs) - 1:>7.2%}")


if __name__ == "__main__":
    main()
